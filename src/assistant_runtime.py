from __future__ import annotations

import asyncio
import ast
import base64
import json
import logging
import os
import re
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import WebSocket

from src.findings_store import FindingsStore
from src.kb_store import get_kb_store
from src.session_log import log_event
from src.tools import HVACToolDispatcher, get_tools_json

logger = logging.getLogger(__name__)

TOOL_NAMES = {"query_kb", "log_finding", "flag_safety", "flag_scope_change", "close_job"}

_TOOL_CALL_PAREN = re.compile(
    r"(?:<\|tool_call(?:_start)?\|>\s*(?:call\s*:\s*)?)?"
    r"\b(" + "|".join(TOOL_NAMES) + r")\s*\((.*?)\)"
    r"(?:\s*<\|tool_call_end\|>)?",
    flags=re.DOTALL,
)
_TOOL_CALL_CURLY = re.compile(
    r"(?:<\|tool_call(?:_start)?\|>\s*(?:call\s*:\s*)?)?"
    r"\b(" + "|".join(TOOL_NAMES) + r")\s*\{(.*?)\}"
    r"(?:\s*<\|tool_call_end\|>)?",
    flags=re.DOTALL,
)

EventListener = Callable[[dict[str, Any]], Awaitable[None]]


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
    cleaned = args_raw.replace('<|"|>', '"')
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
    return _TOOL_CALL_CURLY.sub("", _TOOL_CALL_PAREN.sub("", text)).strip()


def save_pcm_as_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav", dir="/tmp")
    os.close(fd)
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
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


def decode_data_url_b64(value: str) -> bytes:
    if not value:
        return b""
    if value.startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value)
    except Exception:
        return b""


class AssistantSession:
    MIN_AUDIO_BYTES = 3200
    HISTORY_KEEP_LAST = 10

    def __init__(
        self,
        *,
        engine: Any,
        system_prompt: str,
        gen_options: dict[str, Any],
        emit: EventListener,
        cactus_complete: Callable[..., str],
        cactus_stop: Callable[[int], Any],
    ) -> None:
        self.engine = engine
        self.system_prompt = system_prompt
        self.gen_options = gen_options
        self._emit = emit
        self._cactus_complete = cactus_complete
        self._cactus_stop = cactus_stop

        self.sid = "shared"
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        self.dispatcher = HVACToolDispatcher(findings_store=FindingsStore())
        self._temp_files: list[str] = []
        self.turn_count = 0
        self.connected_at = time.time()
        self.cancel_requested = False

    async def emit(self, payload: dict[str, Any]) -> None:
        await self._emit(payload)

    async def emit_ready(self) -> None:
        await self.emit({"type": "ready", "kb_entries": get_kb_store().entry_count})
        await self.emit_session_state()

    async def emit_session_state(self) -> None:
        await self.emit({"type": "session", "state": self.dispatcher.findings.snapshot()})

    def add_user_text(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_user_multimodal(
        self,
        content: str,
        *,
        pcm_bytes: bytes | None = None,
        jpeg_bytes: bytes | None = None,
    ) -> None:
        if pcm_bytes is not None and len(pcm_bytes) < self.MIN_AUDIO_BYTES:
            raise ValueError(
                f"Audio too short ({len(pcm_bytes)} bytes < {self.MIN_AUDIO_BYTES}) — "
                "hold the mic for at least a moment."
            )
        message: dict[str, Any] = {"role": "user", "content": content or "<multimodal>"}
        if pcm_bytes:
            wav_path = save_pcm_as_wav(pcm_bytes)
            message["audio"] = [wav_path]
            self._temp_files.append(wav_path)
        if jpeg_bytes:
            jpg_path = save_jpeg(jpeg_bytes)
            message["images"] = [jpg_path]
            self._temp_files.append(jpg_path)
        self.messages.append(message)

    def pop_last_user_message(self) -> None:
        for idx in range(len(self.messages) - 1, -1, -1):
            if self.messages[idx].get("role") == "user":
                del self.messages[idx]
                break

    def cleanup_turn_files(self) -> None:
        for path in self._temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._temp_files.clear()

    def _strip_history_file_refs(self) -> None:
        for message in self.messages:
            message.pop("images", None)
            message.pop("audio", None)

    def _trim_history(self) -> None:
        if len(self.messages) <= 1 + self.HISTORY_KEEP_LAST:
            return
        self.messages = [self.messages[0]] + self.messages[-self.HISTORY_KEEP_LAST:]
        logger.info("History trimmed to %s messages", len(self.messages))

    def reset(self) -> None:
        self.cleanup_turn_files()
        self.messages = [self.messages[0]]
        self.dispatcher = HVACToolDispatcher(findings_store=FindingsStore())
        self.cancel_requested = False

    async def cancel(self) -> None:
        self.cancel_requested = True
        try:
            self._cactus_stop(self.engine.handle)
            log_event("cancel", sid=self.sid)
        except Exception as exc:
            logger.warning("cactus_stop failed: %s", exc)

    async def _complete_once(
        self,
        pass_idx: int = 0,
        *,
        source: str = "browser",
        turn_id: str | None = None,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        token_queue: asyncio.Queue[str] = asyncio.Queue()

        def on_token(token: str, _token_id: int) -> None:
            loop.call_soon_threadsafe(token_queue.put_nowait, token)

        last_message = self.messages[-1] if self.messages else {}
        has_audio = bool(last_message.get("audio"))
        has_image = bool(last_message.get("images"))

        t_start = time.time()
        log_event(
            "complete_start",
            sid=self.sid,
            pass_idx=pass_idx,
            msg_count=len(self.messages),
            has_audio=has_audio,
            has_image=has_image,
            source=source,
            turn_id=turn_id,
        )

        async with self.engine.lock:
            task = loop.run_in_executor(
                None,
                lambda: self._cactus_complete(
                    self.engine.handle,
                    json.dumps(self.messages),
                    json.dumps(self.gen_options),
                    get_tools_json(),
                    on_token,
                    None,
                ),
            )
            while not task.done():
                try:
                    token = await asyncio.wait_for(token_queue.get(), timeout=0.05)
                    await self.emit({"type": "token", "token": token, "source": source, "turn_id": turn_id})
                except asyncio.TimeoutError:
                    pass
            while not token_queue.empty():
                await self.emit({
                    "type": "token",
                    "token": token_queue.get_nowait(),
                    "source": source,
                    "turn_id": turn_id,
                })
            raw = await task

        wall_ms = (time.time() - t_start) * 1000
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            log_event(
                "complete_end",
                sid=self.sid,
                pass_idx=pass_idx,
                wall_ms=round(wall_ms, 1),
                error="bad_json",
                source=source,
                turn_id=turn_id,
            )
            return {"response": "", "function_calls": []}

        parsed["_wall_ms"] = round(wall_ms, 1)
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
            source=source,
            turn_id=turn_id,
        )
        return parsed

    async def _dispatch_calls(
        self,
        function_calls: list[dict[str, Any]],
        *,
        turn_id: str | None = None,
        pass_idx: int | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        tool_messages: list[dict[str, Any]] = []
        tool_trace: list[dict[str, Any]] = []
        for call in function_calls:
            name = call.get("name", "")
            arguments = call.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            t0 = time.time()
            result_json = self.dispatcher.execute(name, arguments)
            exec_ms = (time.time() - t0) * 1000
            try:
                result_parsed = json.loads(result_json)
            except json.JSONDecodeError:
                result_parsed = {"raw": result_json}
            log_event(
                "tool_call",
                sid=self.sid,
                name=(name or "").strip(),
                args_preview=json.dumps(arguments, default=str)[:120],
                result_preview=json.dumps(result_parsed, default=str)[:200],
                exec_ms=round(exec_ms, 2),
                pass_idx=pass_idx,
                turn_id=turn_id,
            )
            tool_trace.append({
                "name": (name or "").strip(),
                "exec_ms": round(exec_ms, 2),
            })
            tool_messages.append({
                "role": "tool",
                "content": json.dumps({"name": name, "content": result_json}),
            })
            await self.emit({
                "type": "tool_call",
                "name": name,
                "arguments": arguments,
                "result": result_parsed,
            })
        return tool_messages, tool_trace

    async def run_turn(
        self,
        *,
        source: str = "browser",
        max_passes: int = 3,
        turn_id: str | None = None,
    ) -> None:
        self.turn_count += 1
        turn_t0 = time.time()
        final_text = ""
        ttft: float | None = None
        decode_tps: float | None = None
        passes_done = 0
        self.cancel_requested = False
        trace: dict[str, Any] = {
            "passes": [],
            "tool_calls": [],
        }

        for pass_idx in range(max_passes):
            if self.cancel_requested:
                logger.info("turn %s cancelled before pass %s", self.turn_count, pass_idx)
                break
            passes_done = pass_idx + 1
            result = await self._complete_once(pass_idx=pass_idx, source=source, turn_id=turn_id)
            if self.cancel_requested:
                logger.info("turn %s cancelled mid-turn after pass %s", self.turn_count, pass_idx)
                break

            assistant_text = result.get("response", "") or ""
            function_calls = result.get("function_calls") or []
            trace["passes"].append({
                "pass_idx": pass_idx,
                "wall_ms": result.get("_wall_ms"),
                "ttft_ms": result.get("time_to_first_token_ms"),
                "total_ms": result.get("total_ms"),
                "decode_tps": result.get("decode_tps"),
                "prefill_tps": result.get("prefill_tps"),
                "prefill_tokens": result.get("prefill_tokens"),
                "decode_tokens": result.get("decode_tokens"),
                "n_function_calls": len(function_calls),
                "response_len": len(assistant_text),
            })
            if pass_idx == 0:
                ttft = result.get("time_to_first_token_ms")
                decode_tps = result.get("decode_tps")

            if not function_calls and assistant_text:
                function_calls = parse_tool_calls_from_text(assistant_text)
                if function_calls:
                    assistant_text = strip_tool_call_text(assistant_text)
                    logger.info("[pass %s] parsed %s tool call(s) from plain text", pass_idx, len(function_calls))

            self.messages.append({"role": "assistant", "content": assistant_text})
            if assistant_text:
                final_text = (final_text + "\n" + assistant_text).strip() if final_text else assistant_text

            if not function_calls:
                break

            tool_messages, tool_trace = await self._dispatch_calls(
                function_calls,
                turn_id=turn_id,
                pass_idx=pass_idx,
            )
            trace["tool_calls"].extend(tool_trace)
            self.messages.extend(tool_messages)
            await self.emit_session_state()

        trace["passes_done"] = passes_done
        trace["turn_total_ms"] = round((time.time() - turn_t0) * 1000, 1)
        await self.emit({
            "type": "assistant_end",
            "text": final_text,
            "ttft_ms": ttft,
            "decode_tps": decode_tps,
            "source": source,
            "turn_id": turn_id,
            "trace": trace,
        })
        log_event(
            "turn_end",
            sid=self.sid,
            turn_idx=self.turn_count,
            passes=passes_done,
            total_ms=trace["turn_total_ms"],
            history_len=len(self.messages),
            final_text_len=len(final_text),
            source=source,
            turn_id=turn_id,
        )
        self._strip_history_file_refs()
        self._trim_history()
        self.cleanup_turn_files()


class SharedAssistantRuntime:
    def __init__(
        self,
        *,
        engine: Any,
        system_prompt: str,
        gen_options: dict[str, Any],
        cactus_complete: Callable[..., str],
        cactus_stop: Callable[[int], Any],
    ) -> None:
        self._web_clients: set[WebSocket] = set()
        self._event_listeners: set[EventListener] = set()
        self._web_lock = asyncio.Lock()
        self._turn_lock = asyncio.Lock()
        self._current_turn_task: asyncio.Task[None] | None = None
        self._is_generating = False

        self.session = AssistantSession(
            engine=engine,
            system_prompt=system_prompt,
            gen_options=gen_options,
            emit=self.broadcast,
            cactus_complete=cactus_complete,
            cactus_stop=cactus_stop,
        )

    @property
    def is_generating(self) -> bool:
        return self._is_generating

    async def connect_websocket(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._web_lock:
            self._web_clients.add(ws)
        await ws.send_text(json.dumps({"type": "ready", "kb_entries": get_kb_store().entry_count}))
        await ws.send_text(json.dumps({"type": "session", "state": self.session.dispatcher.findings.snapshot()}))

    async def disconnect_websocket(self, ws: WebSocket) -> None:
        async with self._web_lock:
            self._web_clients.discard(ws)

    def add_listener(self, listener: EventListener) -> None:
        self._event_listeners.add(listener)

    def remove_listener(self, listener: EventListener) -> None:
        self._event_listeners.discard(listener)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        if payload.get("type") == "assistant_end":
            self._is_generating = False
        recipients: list[WebSocket]
        async with self._web_lock:
            recipients = list(self._web_clients)

        failed: list[WebSocket] = []
        if recipients:
            message = json.dumps(payload)
            for ws in recipients:
                try:
                    await ws.send_text(message)
                except Exception:
                    failed.append(ws)

        if failed:
            async with self._web_lock:
                for ws in failed:
                    self._web_clients.discard(ws)

        listeners = list(self._event_listeners)
        for listener in listeners:
            try:
                await listener(payload)
            except Exception:
                logger.exception("Event listener failed for payload %s", payload.get("type"))

    async def cancel_current_turn(self) -> None:
        await self.session.cancel()
        task = self._current_turn_task
        if task and task is not asyncio.current_task():
            try:
                await task
            except Exception:
                pass

    async def reset(self) -> None:
        async with self._turn_lock:
            self.session.reset()
            self.session.engine.reset_and_rewarm()
            self._is_generating = False
            await self.session.emit_session_state()
            await self.session.emit({"type": "ready", "kb_entries": get_kb_store().entry_count})

    async def _run_submission(
        self,
        *,
        source: str,
        add_message: Callable[[], None],
        user_text: str | None = None,
        interrupt: bool = False,
        turn_id: str | None = None,
    ) -> None:
        if interrupt and self._current_turn_task and not self._current_turn_task.done():
            await self.cancel_current_turn()

        submit_t0 = time.time()
        log_event(
            "turn_submit",
            sid=self.session.sid,
            source=source,
            turn_id=turn_id,
            interrupt=interrupt,
            text_len=len(user_text or ""),
        )
        async with self._turn_lock:
            if user_text and source != "browser":
                await self.broadcast({
                    "type": "user_turn",
                    "source": source,
                    "text": user_text,
                    "turn_id": turn_id,
                })

            self._is_generating = True
            self._current_turn_task = asyncio.current_task()
            try:
                log_event(
                    "turn_start",
                    sid=self.session.sid,
                    source=source,
                    turn_id=turn_id,
                    queue_wait_ms=round((time.time() - submit_t0) * 1000, 1),
                )
                add_message()
                await self.session.run_turn(source=source, turn_id=turn_id)
            except ValueError as exc:
                logger.info("Rejected turn: %s", exc)
                log_event(
                    "turn_error",
                    sid=self.session.sid,
                    error=str(exc),
                    cause="guard_rail",
                    source=source,
                    turn_id=turn_id,
                )
                await self.broadcast({"type": "error", "message": str(exc), "source": source, "turn_id": turn_id})
                await self.broadcast({"type": "assistant_end", "text": "", "source": source, "turn_id": turn_id})
            except Exception as turn_err:
                logger.exception("Turn failed: %s", turn_err)
                log_event(
                    "turn_error",
                    sid=self.session.sid,
                    error=str(turn_err),
                    cause="model_crash",
                    source=source,
                    turn_id=turn_id,
                )
                self.session.pop_last_user_message()
                self.session._strip_history_file_refs()
                self.session.cleanup_turn_files()
                self.session.engine.reset_and_rewarm()
                await self.broadcast({
                    "type": "error",
                    "message": f"Completion failed: {turn_err}",
                    "source": source,
                    "turn_id": turn_id,
                })
                await self.broadcast({"type": "assistant_end", "text": "", "source": source, "turn_id": turn_id})
            finally:
                self._is_generating = False
                self._current_turn_task = None

    async def handle_browser_message(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        log_event(
            "msg_in",
            sid=self.session.sid,
            msg_type=kind,
            text_len=len(msg.get("content") or ""),
            has_audio=bool(msg.get("pcm_b64")),
            has_image=bool(msg.get("jpeg_b64")),
            source="browser",
        )

        if kind == "text":
            content = (msg.get("content") or "").strip()
            if not content:
                return
            await self._run_submission(
                source="browser",
                add_message=lambda: self.session.add_user_text(content),
            )
            return

        if kind == "audio":
            pcm = decode_data_url_b64(msg.get("pcm_b64") or "")
            if not pcm:
                return
            prompt = (
                msg.get("content")
                or "A technician just spoke. Listen to the audio, identify the HVAC symptom "
                   "and brand/model if mentioned, and call the appropriate tool."
            )
            await self._run_submission(
                source="browser",
                add_message=lambda: self.session.add_user_multimodal(prompt, pcm_bytes=pcm),
            )
            return

        if kind == "multimodal":
            pcm = decode_data_url_b64(msg.get("pcm_b64") or "")
            jpeg = decode_data_url_b64(msg.get("jpeg_b64") or "")
            if not pcm and not jpeg:
                await self.broadcast({"type": "error", "message": "multimodal requires pcm_b64 and/or jpeg_b64"})
                return
            prompt = (
                msg.get("content")
                or "A technician is pointing their camera at an HVAC unit and describing what they see. "
                   "Use the image + audio together: identify brand/model if visible, extract symptoms "
                   "from speech, and call the appropriate tool."
            )
            await self._run_submission(
                source="browser",
                add_message=lambda: self.session.add_user_multimodal(
                    prompt,
                    pcm_bytes=pcm or None,
                    jpeg_bytes=jpeg or None,
                ),
            )
            return

        if kind == "reset":
            await self.reset()
            return

        if kind == "cancel":
            await self.cancel_current_turn()
            return

        if kind == "ping":
            await self.broadcast({"type": "pong"})
            return

        await self.broadcast({"type": "error", "message": f"Unknown type: {kind}"})

    async def submit_rokid_turn(
        self,
        text: str,
        *,
        jpeg_bytes: bytes | None = None,
        interrupt: bool = True,
        turn_id: str | None = None,
    ) -> None:
        clean = (text or "").strip()
        if not clean:
            return
        prompt = (
            "A technician is speaking through Rokid glasses. Treat the transcription as the user's live speech. "
            "Use the image together with the utterance when provided."
        )
        await self._run_submission(
            source="rokid",
            user_text=clean,
            interrupt=interrupt,
            turn_id=turn_id,
            add_message=lambda: self.session.add_user_multimodal(
                f"{prompt}\n\nUser transcript: {clean}",
                jpeg_bytes=jpeg_bytes,
            ),
        )
