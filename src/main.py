"""
HVAC Copilot — FastAPI server running Gemma 4 via Cactus on the MacBook.

Serves:
  GET  /              → static web UI (web/index.html + app.js)
  GET  /healthz       → liveness
  WS   /ws/session    → per-tech session (text turns, tool calls, streaming tokens)

The Cactus handle is loaded once at startup. Completions are serialized with
an asyncio Lock because the underlying C state is single-threaded.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.cactus import cactus_init, cactus_complete, cactus_destroy
from src.config import cfg
from src.findings_store import FindingsStore
from src.kb_store import get_kb_store
from src.tools import HVACToolDispatcher, get_tools_json

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hvac.main")

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
WEIGHTS_DIR = REPO_ROOT / "cactus" / "weights" / "gemma-4-e4b-it"

SYSTEM_PROMPT = (
    "You are HVACCopilot — an on-device coach for HVAC field technicians running on Gemma 4. "
    "You see what the tech sees and hear what they describe. Be concise — they are working with their hands.\n\n"
    "Tool-use rules (follow strictly):\n"
    "1. The MOMENT a tech describes ANY symptom with a brand/model, CALL query_kb FIRST. "
    "Do NOT ask clarifying questions first. Do NOT guess. Call query_kb, then summarize the top match.\n"
    "2. If the tech mentions gas smell, sulfur, rotten-egg smell, arcing, electrical burning, smoke, or CO symptoms "
    "(headache, dizziness, nausea near the unit), CALL flag_safety with level='stop' IMMEDIATELY — even before query_kb.\n"
    "3. When the tech confirms a diagnosis (e.g. 'capacitor is bulged', 'contactor is pitted'), "
    "CALL log_finding to record it.\n"
    "4. When the tech spots additional work beyond the ticket (e.g. 'contactor also needs replacing'), "
    "CALL flag_scope_change.\n"
    "5. When the tech says they're done ('job's finished', 'cooling is normal', 'unit's running'), CALL close_job.\n\n"
    "Tools available:\n"
    "  • query_kb(query, equipment_model?) — search 10 curated HVAC cases for the top match.\n"
    "  • log_finding(location, issue, severity, part_number?, notes?)\n"
    "  • flag_safety(hazard, immediate_action, level)\n"
    "  • flag_scope_change(original_scope, new_scope, reason, estimated_extra_time_minutes?)\n"
    "  • close_job(summary, parts_used, follow_up_required, follow_up_notes?)\n\n"
    "After any tool call returns, summarize the result for the tech in 1-2 sentences. "
    "Name the part, the confirming test, and the first safety step. Do not dump the raw JSON."
)

GEN_OPTIONS = {
    "max_tokens": cfg.MAX_TOKENS,
    "temperature": cfg.TEMPERATURE,
}

TOOL_NAMES = {"query_kb", "log_finding", "flag_safety", "flag_scope_change", "close_job"}

# Form A: `name(arg=value, ...)`, optionally wrapped in <|tool_call_start|>...<|tool_call_end|>.
_TOOL_CALL_PAREN = re.compile(
    r"(?:<\|tool_call(?:_start)?\|>\s*(?:call\s*:\s*)?)?"
    r"\b(" + "|".join(TOOL_NAMES) + r")\s*\((.*?)\)"
    r"(?:\s*<\|tool_call_end\|>)?",
    flags=re.DOTALL,
)

# Form B (malformed emission we've seen from Gemma 4): `name{arg: value, ...}`.
# Curly braces + colons instead of parens + equals.
_TOOL_CALL_CURLY = re.compile(
    r"(?:<\|tool_call(?:_start)?\|>\s*(?:call\s*:\s*)?)?"
    r"\b(" + "|".join(TOOL_NAMES) + r")\s*\{(.*?)\}"
    r"(?:\s*<\|tool_call_end\|>)?",
    flags=re.DOTALL,
)


def _parse_kwargs_paren(args_raw: str) -> dict[str, Any] | None:
    try:
        node = ast.parse(f"_f({args_raw})", mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Call):
        return None
    out: dict[str, Any] = {}
    for kw in node.keywords:
        if kw.arg is None:
            continue
        try:
            out[kw.arg] = ast.literal_eval(kw.value)
        except Exception:
            try:
                out[kw.arg] = ast.unparse(kw.value)
            except Exception:
                pass
    return out


def _parse_kwargs_curly(args_raw: str) -> dict[str, Any] | None:
    # Convert `key: value, key2: value2` to `key=value, key2=value2`, with value quoted if needed.
    # Strip out any stray `<|"|>` escaping the model emits.
    cleaned = args_raw.replace("<|\"|>", '"')
    # Split top-level by commas — naive but works for our small schema.
    pairs: list[str] = []
    depth = 0
    buf = ""
    in_str = False
    str_ch = ""
    for ch in cleaned:
        if in_str:
            buf += ch
            if ch == str_ch:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            str_ch = ch
            buf += ch
            continue
        if ch in "[{(":
            depth += 1
        elif ch in "]})":
            depth -= 1
        if ch == "," and depth == 0:
            pairs.append(buf)
            buf = ""
            continue
        buf += ch
    if buf.strip():
        pairs.append(buf)

    out: dict[str, Any] = {}
    for pair in pairs:
        if ":" not in pair:
            continue
        k, _, v = pair.partition(":")
        key = k.strip().strip('"').strip("'")
        val = v.strip()
        try:
            out[key] = ast.literal_eval(val)
        except Exception:
            out[key] = val.strip('"').strip("'")
    return out or None


def parse_tool_calls_from_text(text: str) -> list[dict[str, Any]]:
    """
    Fallback parser: Gemma 4 on Cactus sometimes emits tool calls without
    the <|tool_call_start|> sentinels, and occasionally in a curly-brace form.
    Extract them regardless. Dedupes by (name, arguments).
    """
    calls: list[dict[str, Any]] = []
    seen: set[str] = set()

    for match in _TOOL_CALL_PAREN.finditer(text):
        name = match.group(1)
        args = _parse_kwargs_paren(match.group(2).strip())
        if args is None or name not in TOOL_NAMES:
            continue
        key = name + json.dumps(args, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        calls.append({"name": name, "arguments": args})

    for match in _TOOL_CALL_CURLY.finditer(text):
        name = match.group(1)
        args = _parse_kwargs_curly(match.group(2).strip())
        if args is None or name not in TOOL_NAMES:
            continue
        key = name + json.dumps(args, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        calls.append({"name": name, "arguments": args})

    return calls


def strip_tool_call_text(text: str) -> str:
    """Remove tool-call expressions from assistant text so the UI doesn't show the raw call."""
    return _TOOL_CALL_CURLY.sub("", _TOOL_CALL_PAREN.sub("", text)).strip()


class EngineHandle:
    """Single shared Cactus handle, serialized via asyncio lock."""

    def __init__(self) -> None:
        self._handle: int | None = None
        self._lock = asyncio.Lock()

    def load(self, model_path: Path) -> None:
        t0 = time.time()
        logger.info(f"Loading Gemma 4 E4B from {model_path}…")
        self._handle = cactus_init(str(model_path), None, False)
        if self._handle is None:
            raise RuntimeError("cactus_init returned None")
        logger.info(f"Loaded in {time.time() - t0:.1f}s")

    def unload(self) -> None:
        if self._handle is not None:
            cactus_destroy(self._handle)
            self._handle = None

    @property
    def handle(self) -> int:
        if self._handle is None:
            raise RuntimeError("Cactus handle not initialized")
        return self._handle

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock


engine = EngineHandle()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    get_kb_store()  # warm the KB cache
    engine.load(WEIGHTS_DIR)
    yield
    # shutdown
    engine.unload()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return JSONResponse({
        "ok": True,
        "kb_entries": get_kb_store().entry_count,
        "model_loaded": engine._handle is not None,
        "model": "gemma-4-E4B-it",
    })


# NOTE: static mount at "/" is added at the END of this file, AFTER the @app.websocket
# route is registered, otherwise StaticFiles catches WebSocket scopes and errors with
# AssertionError (scope["type"] == "http"). Do not reorder.


# ── WebSocket session ────────────────────────────────────────────


class Session:
    """Per-connection state: conversation history + dispatcher."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.dispatcher = HVACToolDispatcher(findings_store=FindingsStore())

    async def send(self, payload: dict[str, Any]) -> None:
        await self.ws.send_text(json.dumps(payload))

    async def send_session_state(self) -> None:
        await self.send({"type": "session", "state": self.dispatcher.findings.snapshot()})

    def add_user_text(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_user_audio_bytes(self, raw: bytes) -> list[int]:
        """Return pcm int list for cactus_complete's pcm_data argument."""
        self.messages.append({"role": "user", "content": "<audio>"})
        return list(raw)

    def reset(self) -> None:
        self.messages = [self.messages[0]]  # keep system prompt
        self.dispatcher = HVACToolDispatcher(findings_store=FindingsStore())

    async def _complete_once(self, pcm_bytes: bytes | None) -> dict[str, Any]:
        """Run one cactus_complete with token streaming to the client. Returns parsed JSON."""
        loop = asyncio.get_running_loop()
        token_queue: asyncio.Queue[str] = asyncio.Queue()

        def on_token(tok: str, _id: int) -> None:
            loop.call_soon_threadsafe(token_queue.put_nowait, tok)

        async with engine.lock:
            task = loop.run_in_executor(
                None,
                lambda: cactus_complete(
                    engine.handle,
                    json.dumps(self.messages),
                    json.dumps(GEN_OPTIONS),
                    get_tools_json(),
                    on_token,
                    list(pcm_bytes) if pcm_bytes else None,
                ),
            )
            while not task.done():
                try:
                    tok = await asyncio.wait_for(token_queue.get(), timeout=0.05)
                    await self.send({"type": "token", "token": tok})
                except asyncio.TimeoutError:
                    pass
            while not token_queue.empty():
                await self.send({"type": "token", "token": token_queue.get_nowait()})
            raw = await task

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"response": "", "function_calls": []}

    async def _dispatch_calls(self, function_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute a batch of function calls and stream tool_call events. Returns tool role messages."""
        tool_messages: list[dict[str, Any]] = []
        for call in function_calls:
            name = call.get("name", "")
            args = call.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result_json = self.dispatcher.execute(name, args)
            try:
                result_parsed = json.loads(result_json)
            except json.JSONDecodeError:
                result_parsed = {"raw": result_json}
            tool_messages.append({
                "role": "tool",
                "content": json.dumps({"name": name, "content": result_json}),
            })
            await self.send({
                "type": "tool_call",
                "name": name,
                "arguments": args,
                "result": result_parsed,
            })
        return tool_messages

    async def run_turn(self, pcm_bytes: bytes | None = None, max_passes: int = 3) -> None:
        """
        Execute a full assistant turn: completion → (execute tools → completion) loop,
        capped at max_passes so a runaway model can't spin. Streams tokens to the client.
        """
        final_text = ""
        ttft: float | None = None
        decode_tps: float | None = None
        pcm_for_pass: bytes | None = pcm_bytes

        for pass_idx in range(max_passes):
            result = await self._complete_once(pcm_for_pass)
            pcm_for_pass = None  # audio goes in on the first pass only

            assistant_text = result.get("response", "") or ""
            function_calls = result.get("function_calls") or []
            if pass_idx == 0:
                ttft = result.get("time_to_first_token_ms")
                decode_tps = result.get("decode_tps")

            if not function_calls and assistant_text:
                function_calls = parse_tool_calls_from_text(assistant_text)
                if function_calls:
                    assistant_text = strip_tool_call_text(assistant_text)
                    logger.info(f"[pass {pass_idx}] parsed {len(function_calls)} tool call(s) from plain text")

            self.messages.append({"role": "assistant", "content": assistant_text})
            if assistant_text:
                final_text = (final_text + "\n" + assistant_text).strip() if final_text else assistant_text

            if not function_calls:
                break

            tool_messages = await self._dispatch_calls(function_calls)
            self.messages.extend(tool_messages)
            await self.send_session_state()

        await self.send({
            "type": "assistant_end",
            "text": final_text,
            "ttft_ms": ttft,
            "decode_tps": decode_tps,
        })


@app.websocket("/ws/session")
async def ws_session(ws: WebSocket) -> None:
    await ws.accept()
    session = Session(ws)
    logger.info("WS connected")
    try:
        await session.send({"type": "ready", "kb_entries": get_kb_store().entry_count})

        while True:
            msg_raw = await ws.receive_text()
            try:
                msg = json.loads(msg_raw)
            except json.JSONDecodeError:
                await session.send({"type": "error", "message": "Bad JSON"})
                continue

            kind = msg.get("type")

            if kind == "text":
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                session.add_user_text(content)
                await session.run_turn()

            elif kind == "audio":
                # Raw PCM16 LE bytes base64-encoded.
                b64 = msg.get("pcm_b64") or ""
                try:
                    pcm = base64.b64decode(b64) if b64 else b""
                except Exception:
                    await session.send({"type": "error", "message": "Bad audio base64"})
                    continue
                if not pcm:
                    continue
                session.add_user_audio_bytes(pcm)
                await session.run_turn(pcm_bytes=pcm)

            elif kind == "reset":
                session.reset()
                await session.send_session_state()
                await session.send({"type": "ready"})

            elif kind == "ping":
                await session.send({"type": "pong"})

            else:
                await session.send({"type": "error", "message": f"Unknown type: {kind}"})

    except WebSocketDisconnect:
        logger.info("WS disconnected")
    except Exception as e:
        logger.exception(f"WS error: {e}")
        try:
            await session.send({"type": "error", "message": str(e)})
        except Exception:
            pass


# Mount the static UI LAST so it doesn't swallow the /ws/session WebSocket route.
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
