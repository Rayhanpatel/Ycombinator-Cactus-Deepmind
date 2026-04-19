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
import os
import re
import tempfile
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.cactus import cactus_init, cactus_complete, cactus_destroy, cactus_prefill, cactus_reset, cactus_stop
from src.config import cfg
from src.findings_store import FindingsStore
from src.kb_store import get_kb_store
from src.session_log import log_event, log_file_path, log_file_name, recent_events, summary as log_summary
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
    "5. When the tech says they're done ('job's finished', 'cooling is normal', 'unit's running'), CALL close_job.\n"
    "6. ESCALATION: only call search_online_hvac when query_kb returned zero or irrelevant results "
    "for a RARE / uncommon unit, OR when the tech explicitly says 'look online', 'check Reddit', "
    "'any field reports'. NEVER chain search_online_hvac after a successful query_kb. "
    "This tool is the only part of the app that makes a network call — use it sparingly.\n\n"
    "Tools available:\n"
    "  • query_kb(query, equipment_model?) — search the curated HVAC KB for the top match.\n"
    "  • log_finding(location, issue, severity, part_number?, notes?)\n"
    "  • flag_safety(hazard, immediate_action, level)\n"
    "  • flag_scope_change(original_scope, new_scope, reason, estimated_extra_time_minutes?)\n"
    "  • close_job(summary, parts_used, follow_up_required, follow_up_notes?)\n"
    "  • search_online_hvac(query) — ESCALATION ONLY. Online technician forums.\n\n"
    "After any tool call returns, summarize the result for the tech in 1-2 sentences. "
    "Name the part, the confirming test, and the first safety step. Do not dump the raw JSON."
)

# max_tokens is capped at 220 regardless of cfg.MAX_TOKENS — replies longer
# than ~4 sentences drag the turn past the user's attention budget and
# invite the user to start talking over the model.
GEN_OPTIONS = {
    "max_tokens": min(cfg.MAX_TOKENS, 220),
    "temperature": cfg.TEMPERATURE,
}

TOOL_NAMES = {"query_kb", "log_finding", "flag_safety", "flag_scope_change", "close_job", "search_online_hvac"}

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


def save_pcm_as_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    """Wrap raw PCM16 LE mono bytes in a proper WAV header and return the file path.
    Cactus's `audio` message field wants file paths, not raw buffers."""
    fd, path = tempfile.mkstemp(suffix=".wav", dir="/tmp")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)
    return path


def save_jpeg(jpeg_bytes: bytes) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg", dir="/tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(jpeg_bytes)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
    return path


def decode_data_url_b64(s: str) -> bytes:
    """Accept either a bare base64 string or a data:image/jpeg;base64,... URL."""
    if not s:
        return b""
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s)
    except Exception:
        return b""


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

    def prefill_system(self) -> None:
        """Warm the KV cache with the system prompt + tool schemas so the
        first user turn starts decoding immediately."""
        if self._handle is None:
            raise RuntimeError("Cactus handle not initialized")
        t0 = time.time()
        try:
            cactus_prefill(
                self._handle,
                json.dumps([{"role": "system", "content": SYSTEM_PROMPT}]),
                json.dumps(GEN_OPTIONS),
                get_tools_json(),
                None,
            )
            dur_ms = (time.time() - t0) * 1000
            logger.info(f"System prompt prefilled in {dur_ms / 1000:.2f}s")
            log_event(
                "prefill_startup",
                duration_ms=round(dur_ms, 1),
                system_chars=len(SYSTEM_PROMPT),
                tools_chars=len(get_tools_json()),
            )
        except Exception as e:
            logger.warning(f"cactus_prefill skipped: {e}")
            log_event("prefill_startup_error", error=str(e))

    def unload(self) -> None:
        if self._handle is not None:
            cactus_destroy(self._handle)
            self._handle = None

    def reset_and_rewarm(self) -> None:
        """Clear the KV cache after a failed completion and re-prefill the
        system prompt so the next turn starts fresh."""
        if self._handle is None:
            return
        try:
            cactus_reset(self._handle)
            logger.info("KV cache reset after error")
        except Exception as e:
            logger.warning(f"cactus_reset failed: {e}")
        try:
            self.prefill_system()
        except Exception as e:
            logger.warning(f"prefill after reset failed: {e}")

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
    engine.prefill_system()
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


@app.get("/logs/summary")
async def logs_summary():
    return JSONResponse(log_summary())


@app.get("/logs/recent")
async def logs_recent(n: int = 100):
    return JSONResponse({
        "file": log_file_name(),
        "events": recent_events(n),
    })


@app.get("/logs/download")
async def logs_download():
    path = log_file_path()
    return FileResponse(
        path=str(path),
        media_type="application/x-ndjson",
        filename=log_file_name(),
    )


# NOTE: static mount at "/" is added at the END of this file, AFTER the @app.websocket
# route is registered, otherwise StaticFiles catches WebSocket scopes and errors with
# AssertionError (scope["type"] == "http"). Do not reorder.


# ── WebSocket session ────────────────────────────────────────────


class Session:
    """Per-connection state: conversation history + dispatcher + per-turn temp files."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.sid = hex(id(self))[-8:]  # short id for correlating log events
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.dispatcher = HVACToolDispatcher(findings_store=FindingsStore())
        self._temp_files: list[str] = []
        self.turn_count = 0
        self.connected_at = time.time()
        self.cancel_requested = False  # flipped by a `cancel` WS message

    async def send(self, payload: dict[str, Any]) -> None:
        await self.ws.send_text(json.dumps(payload))

    async def send_session_state(self) -> None:
        await self.send({"type": "session", "state": self.dispatcher.findings.snapshot()})

    def add_user_text(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    # Audio shorter than ~100 ms @ 16 kHz mono PCM16 (3200 bytes) is almost
    # always a user who tapped the mic by accident. A 44-byte WAV header with
    # no frames makes Cactus's C audio decoder throw "Could not open WAV file",
    # which then kills the whole turn. Reject early.
    MIN_AUDIO_BYTES = 3200

    def add_user_multimodal(
        self,
        content: str,
        pcm_bytes: bytes | None = None,
        jpeg_bytes: bytes | None = None,
    ) -> None:
        """Append a user message carrying audio and/or image via file-path fields —
        the canonical Gemma 4 + Cactus multimodal format. Caller should run
        cleanup_turn_files() once the turn is done.

        Raises ValueError if audio is provided but too short to be meaningful.
        """
        if pcm_bytes is not None and len(pcm_bytes) < self.MIN_AUDIO_BYTES:
            raise ValueError(
                f"Audio too short ({len(pcm_bytes)} bytes < {self.MIN_AUDIO_BYTES}) — "
                "hold the mic for at least a moment."
            )
        msg: dict[str, Any] = {"role": "user", "content": content or "<multimodal>"}
        if pcm_bytes:
            wav_path = save_pcm_as_wav(pcm_bytes)
            msg["audio"] = [wav_path]
            self._temp_files.append(wav_path)
        if jpeg_bytes:
            jpg_path = save_jpeg(jpeg_bytes)
            msg["images"] = [jpg_path]
            self._temp_files.append(jpg_path)
        self.messages.append(msg)

    def pop_last_user_message(self) -> None:
        """Remove the most recently-added user message. Used to roll back after
        a completion error so the conversation history stays consistent."""
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].get("role") == "user":
                del self.messages[i]
                break

    def cleanup_turn_files(self) -> None:
        """Best-effort delete of temp files registered this turn.

        Must be called AFTER _strip_history_file_refs — otherwise Cactus on
        the next turn re-reads the now-deleted paths still in self.messages
        and crashes with 'Failed to load image' or 'Could not open WAV file'.
        """
        for p in self._temp_files:
            try:
                os.unlink(p)
            except OSError:
                pass
        self._temp_files.clear()

    def _strip_history_file_refs(self) -> None:
        """Remove `images` / `audio` fields from every message in history.

        Rationale: after a turn completes, the temp files referenced by those
        fields will be deleted. Leaving the paths in the message history would
        break the NEXT turn's cactus_complete prefill. Also cuts context cost:
        each image is ~256 vision tokens and we don't want them re-processed
        on every subsequent turn.
        """
        for m in self.messages:
            m.pop("images", None)
            m.pop("audio", None)

    def _strip_history_tool_messages(self) -> None:
        """Remove `tool` role messages from completed turns.

        A single query_kb result is ~1000-2000 tokens of JSON (part numbers,
        procedures, safety notes across 3 KB hits). Keeping those messages
        in self.messages means every subsequent turn's prefill re-processes
        them — measured TTFT jumped from ~10s to 41s over a session as tool
        results piled up. The tool result was fully consumed by the follow-up
        pass inside THIS turn; future turns don't need it.

        Only call AFTER run_turn's multi-pass loop finishes — during a turn,
        pass 2 MUST see the tool result from pass 1.
        """
        before = len(self.messages)
        self.messages = [m for m in self.messages if m.get("role") != "tool"]
        dropped = before - len(self.messages)
        if dropped:
            logger.debug(f"Dropped {dropped} tool message(s) from history")

    # Keep the system prompt + the last N messages. Multi-turn coherence
    # needs SOME history, but unbounded growth blows up prefill time —
    # we measured TTFT going from ~4s to ~10s as turns accumulated.
    HISTORY_KEEP_LAST = 10

    def _trim_history(self) -> None:
        """Keep system prompt + last N exchanges to bound prefill cost."""
        if len(self.messages) <= 1 + self.HISTORY_KEEP_LAST:
            return
        system = self.messages[0]
        tail = self.messages[-self.HISTORY_KEEP_LAST:]
        self.messages = [system] + tail
        logger.info(f"History trimmed to {len(self.messages)} messages")

    def reset(self) -> None:
        self.cleanup_turn_files()
        self.messages = [self.messages[0]]  # keep system prompt
        self.dispatcher = HVACToolDispatcher(findings_store=FindingsStore())

    async def _complete_once(self, pass_idx: int = 0) -> dict[str, Any]:
        """Run one cactus_complete with token streaming to the client. Returns parsed JSON.
        Audio + images are carried inside self.messages via `audio` / `images` fields;
        we no longer thread raw PCM through the pcm_data parameter."""
        loop = asyncio.get_running_loop()
        token_queue: asyncio.Queue[str] = asyncio.Queue()

        def on_token(tok: str, _id: int) -> None:
            loop.call_soon_threadsafe(token_queue.put_nowait, tok)

        last_msg = self.messages[-1] if self.messages else {}
        has_audio = "audio" in last_msg and bool(last_msg.get("audio"))
        has_image = "images" in last_msg and bool(last_msg.get("images"))

        t_start = time.time()
        log_event(
            "complete_start",
            sid=self.sid,
            pass_idx=pass_idx,
            msg_count=len(self.messages),
            has_audio=has_audio,
            has_image=has_image,
        )

        async with engine.lock:
            task = loop.run_in_executor(
                None,
                lambda: cactus_complete(
                    engine.handle,
                    json.dumps(self.messages),
                    json.dumps(GEN_OPTIONS),
                    get_tools_json(),
                    on_token,
                    None,
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

        wall_ms = (time.time() - t_start) * 1000
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            log_event("complete_end", sid=self.sid, pass_idx=pass_idx, wall_ms=round(wall_ms, 1), error="bad_json")
            return {"response": "", "function_calls": []}

        log_event(
            "complete_end",
            sid=self.sid,
            pass_idx=pass_idx,
            wall_ms=round(wall_ms, 1),
            ttft_ms=parsed.get("time_to_first_token_ms"),
            total_ms=parsed.get("total_ms"),
            decode_tps=parsed.get("decode_tps"),
            prefill_tps=parsed.get("prefill_tps"),
            prefill_tokens=parsed.get("prefill_tokens"),
            decode_tokens=parsed.get("decode_tokens"),
            ram_usage_mb=parsed.get("ram_usage_mb"),
            response_len=len(parsed.get("response") or ""),
            n_function_calls=len(parsed.get("function_calls") or []),
            cloud_handoff=parsed.get("cloud_handoff"),
        )
        return parsed

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
            t0 = time.time()
            result_json = self.dispatcher.execute(name, args)
            exec_ms = (time.time() - t0) * 1000
            try:
                result_parsed = json.loads(result_json)
            except json.JSONDecodeError:
                result_parsed = {"raw": result_json}
            log_event(
                "tool_call",
                sid=self.sid,
                name=(name or "").strip(),
                args_preview=json.dumps(args, default=str)[:120],
                result_preview=json.dumps(result_parsed, default=str)[:200],
                exec_ms=round(exec_ms, 2),
            )
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

    async def run_turn(self, max_passes: int = 3) -> None:
        """
        Execute a full assistant turn: completion → (execute tools → completion) loop,
        capped at max_passes so a runaway model can't spin. Streams tokens to the client.
        Any audio/image files registered for this turn are cleaned up at the end.
        """
        self.turn_count += 1
        turn_t0 = time.time()
        final_text = ""
        ttft: float | None = None
        decode_tps: float | None = None
        passes_done = 0
        self.cancel_requested = False  # fresh flag per turn

        for pass_idx in range(max_passes):
            if self.cancel_requested:
                logger.info(f"turn {self.turn_count} cancelled before pass {pass_idx}")
                break
            passes_done = pass_idx + 1
            result = await self._complete_once(pass_idx=pass_idx)
            if self.cancel_requested:
                logger.info(f"turn {self.turn_count} cancelled mid-turn after pass {pass_idx}")
                break

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
        log_event(
            "turn_end",
            sid=self.sid,
            turn_idx=self.turn_count,
            passes=passes_done,
            total_ms=round((time.time() - turn_t0) * 1000, 1),
            history_len=len(self.messages),
            final_text_len=len(final_text),
        )
        # Order matters: strip refs from history FIRST so next turn's prefill
        # doesn't try to re-open files we're about to delete. Then drop
        # completed tool-role messages (they were fully consumed by the
        # follow-up pass in this same turn and only bloat prefill from here on).
        self._strip_history_file_refs()
        self._strip_history_tool_messages()
        self._trim_history()
        self.cleanup_turn_files()


@app.websocket("/ws/session")
async def ws_session(ws: WebSocket) -> None:
    await ws.accept()
    session = Session(ws)
    logger.info(f"WS connected sid={session.sid}")
    log_event("ws_connect", sid=session.sid)
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
            log_event(
                "msg_in",
                sid=session.sid,
                msg_type=kind,
                text_len=len(msg.get("content") or ""),
                has_audio=bool(msg.get("pcm_b64")),
                has_image=bool(msg.get("jpeg_b64")),
            )

            # Per-message try so one bad turn (empty audio, model crash) can't
            # kill the whole WS loop. Every branch MUST go through here.
            try:
                if kind == "text":
                    content = (msg.get("content") or "").strip()
                    if not content:
                        continue
                    session.add_user_text(content)
                    await session.run_turn()

                elif kind == "audio":
                    pcm = decode_data_url_b64(msg.get("pcm_b64") or "")
                    if not pcm:
                        continue
                    prompt = (
                        msg.get("content")
                        or "A technician just spoke. Listen to the audio, identify the HVAC symptom "
                           "and brand/model if mentioned, and call the appropriate tool."
                    )
                    session.add_user_multimodal(prompt, pcm_bytes=pcm)
                    await session.run_turn()

                elif kind == "multimodal":
                    pcm = decode_data_url_b64(msg.get("pcm_b64") or "")
                    jpeg = decode_data_url_b64(msg.get("jpeg_b64") or "")
                    if not pcm and not jpeg:
                        await session.send({"type": "error", "message": "multimodal requires pcm_b64 and/or jpeg_b64"})
                        continue
                    prompt = (
                        msg.get("content")
                        or "A technician is pointing their camera at an HVAC unit and describing what they see. "
                           "Use the image + audio together: identify brand/model if visible, extract symptoms "
                           "from speech, and call the appropriate tool."
                    )
                    session.add_user_multimodal(prompt, pcm_bytes=pcm or None, jpeg_bytes=jpeg or None)
                    await session.run_turn()

                elif kind == "reset":
                    session.reset()
                    engine.reset_and_rewarm()
                    await session.send_session_state()
                    await session.send({"type": "ready"})

                elif kind == "cancel":
                    # User hit Stop (or toggled hands-free off) while the model
                    # was still generating. Signal Cactus to abort the current
                    # completion AND set the flag so run_turn's multi-pass
                    # loop doesn't kick off another completion after this one.
                    session.cancel_requested = True
                    try:
                        cactus_stop(engine.handle)
                        logger.info(f"sid={session.sid} cactus_stop signalled")
                        log_event("cancel", sid=session.sid)
                    except Exception as e:
                        logger.warning(f"cactus_stop failed: {e}")

                elif kind == "ping":
                    await session.send({"type": "pong"})

                else:
                    await session.send({"type": "error", "message": f"Unknown type: {kind}"})

            except ValueError as ve:
                # Guard-rail rejection (e.g. empty audio). Client-side input problem,
                # not a model crash. No state to clean up — add_user_multimodal
                # throws before appending.
                logger.info(f"Rejected turn: {ve}")
                log_event("turn_error", sid=session.sid, error=str(ve), cause="guard_rail")
                await session.send({"type": "error", "message": str(ve)})
                await session.send({"type": "assistant_end", "text": ""})

            except Exception as turn_err:
                # Model/infra crash mid-turn. Roll back the user message we
                # appended, strip any dead file refs, delete temp files,
                # reset the KV cache, and let the user try again without
                # reconnecting.
                logger.exception(f"Turn failed: {turn_err}")
                log_event("turn_error", sid=session.sid, error=str(turn_err), cause="model_crash")
                session.pop_last_user_message()
                session._strip_history_file_refs()
                session._strip_history_tool_messages()
                session.cleanup_turn_files()
                engine.reset_and_rewarm()
                await session.send({"type": "error", "message": f"Completion failed: {turn_err}"})
                await session.send({"type": "assistant_end", "text": ""})

    except WebSocketDisconnect:
        logger.info(f"WS disconnected sid={session.sid}")
        log_event(
            "ws_disconnect",
            sid=session.sid,
            duration_s=round(time.time() - session.connected_at, 1),
            turn_count=session.turn_count,
        )
    except Exception as e:
        logger.exception(f"WS error: {e}")
        log_event("ws_error", sid=session.sid, error=str(e))
        try:
            await session.send({"type": "error", "message": str(e)})
        except Exception:
            pass


# Mount the static UI LAST so it doesn't swallow the /ws/session WebSocket route.
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
