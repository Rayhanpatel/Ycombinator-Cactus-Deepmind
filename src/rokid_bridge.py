from __future__ import annotations

import asyncio
import io
import json
import logging
import socket
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any, AsyncIterator

from src.config import cfg
from src.session_log import log_event
from src.speech_io import (
    FeedResult,
    FinalizedUtterance,
    SPEECH_IMPORT_ERROR,
    SpeechBackendUnavailable,
    SpeechService,
    float32_to_pcm16_bytes,
    np,
    pcm16_bytes_to_float32,
    resample_audio,
)

try:  # pragma: no cover - dependency-gated
    from aiortc import MediaStreamTrack, RTCPeerConnection, RTCRtpReceiver, RTCSessionDescription
    from aiortc.rtcdatachannel import RTCDataChannel
    from av import AudioFrame, AudioResampler
    from PIL import Image

    AIORTC_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency-gated
    MediaStreamTrack = object
    RTCPeerConnection = None
    RTCRtpReceiver = None
    RTCSessionDescription = None
    RTCDataChannel = None
    AudioFrame = None
    AudioResampler = None
    Image = None
    AIORTC_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)

JPEG_QUALITY = 82
PREVIEW_FPS = 4.0
DEFAULT_AUDIO_SR = 48000
LOCAL_IP_CACHE_TTL_S = 30.0
_LOCAL_IP_CACHE: list[str] = []
_LOCAL_IP_CACHE_AT = 0.0
_LOCAL_IP_LAST_FAILURE_AT = 0.0


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_sdp(raw: str) -> str:
    unified = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not unified:
        return ""
    return "\r\n".join(unified.splitlines()) + "\r\n"


def parse_offer_sdp(raw_body: str) -> str:
    raw_body = raw_body.strip()
    if not raw_body:
        return ""
    if raw_body.startswith("{"):
        payload = json.loads(raw_body)
        if isinstance(payload, dict):
            return normalize_sdp(str(payload.get("sdp", "")))
    return normalize_sdp(raw_body)


def encode_jpeg(rgb_frame: Any, *, width: int | None = None) -> bytes:
    image = Image.fromarray(rgb_frame)
    if width and image.width > width:
        height = max(1, round(width * (image.height / image.width)))
        image = image.resize((width, height))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return output.getvalue()


def local_ipv4_addresses() -> list[str]:
    global _LOCAL_IP_CACHE
    global _LOCAL_IP_CACHE_AT
    global _LOCAL_IP_LAST_FAILURE_AT

    now = time.monotonic()
    if _LOCAL_IP_CACHE and (now - _LOCAL_IP_CACHE_AT) < LOCAL_IP_CACHE_TTL_S:
        return list(_LOCAL_IP_CACHE)
    if not _LOCAL_IP_CACHE and _LOCAL_IP_LAST_FAILURE_AT and (now - _LOCAL_IP_LAST_FAILURE_AT) < LOCAL_IP_CACHE_TTL_S:
        return []

    addresses: set[str] = set()
    for target in ("8.8.8.8", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 80))
                ip = sock.getsockname()[0]
                if ip and not ip.startswith("127."):
                    addresses.add(ip)
        except OSError:
            continue

    try:
        hostname = socket.gethostname()
        if hostname:
            for family, _, _, _, sockaddr in socket.getaddrinfo(
                hostname,
                None,
                family=socket.AF_INET,
                type=socket.SOCK_DGRAM,
            ):
                if family != socket.AF_INET:
                    continue
                ip = sockaddr[0]
                if ip and not ip.startswith("127."):
                    addresses.add(ip)
    except OSError as exc:
        if not addresses and (now - _LOCAL_IP_LAST_FAILURE_AT) >= LOCAL_IP_CACHE_TTL_S:
            logger.warning("rokid: could not resolve local IPv4 addresses: %s", exc)
            _LOCAL_IP_LAST_FAILURE_AT = now

    resolved = sorted(addresses)
    if resolved:
        _LOCAL_IP_CACHE = resolved
        _LOCAL_IP_CACHE_AT = now
        return list(resolved)
    return list(_LOCAL_IP_CACHE)


def hud_text(text: str, *, limit: int = 180) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


@dataclass
class RokidTurnTrace:
    turn_id: str
    session_token: int
    speech_started_at: float | None
    speech_finalized_at: float
    utterance_start_s: float | None
    utterance_end_s: float | None
    utterance_duration_ms: float | None
    utterance_samples: int
    transcript: str = ""
    assistant_text: str = ""
    stt_started_at: float | None = None
    stt_finished_at: float | None = None
    submit_started_at: float | None = None
    assistant_finished_at: float | None = None
    tts_started_at: float | None = None
    tts_finished_at: float | None = None
    audio_enqueued_at: float | None = None
    audio_expected_finish_at: float | None = None
    audio_duration_ms: float | None = None
    runtime_trace: dict[str, Any] = field(default_factory=dict)

    def summary(self, *, outcome: str) -> dict[str, Any]:
        def delta_ms(start: float | None, end: float | None) -> float | None:
            if start is None or end is None:
                return None
            return round((end - start) * 1000, 1)

        tool_calls = self.runtime_trace.get("tool_calls") or []
        return {
            "turn_id": self.turn_id,
            "session_token": self.session_token,
            "outcome": outcome,
            "utterance_duration_ms": round(self.utterance_duration_ms, 1) if self.utterance_duration_ms is not None else None,
            "utterance_samples": self.utterance_samples,
            "speech_to_finalize_ms": delta_ms(self.speech_started_at, self.speech_finalized_at),
            "stt_ms": delta_ms(self.stt_started_at, self.stt_finished_at),
            "submit_to_assistant_ms": delta_ms(self.submit_started_at, self.assistant_finished_at),
            "tts_synth_ms": delta_ms(self.tts_started_at, self.tts_finished_at),
            "assistant_to_audio_enqueue_ms": delta_ms(self.assistant_finished_at, self.audio_enqueued_at),
            "audio_playback_ms": round(self.audio_duration_ms, 1) if self.audio_duration_ms is not None else None,
            "speech_to_audio_enqueue_ms": delta_ms(self.speech_started_at, self.audio_enqueued_at),
            "speech_to_audio_finish_ms": delta_ms(self.speech_started_at, self.audio_expected_finish_at),
            "llm_ttft_ms": self.runtime_trace.get("ttft_ms"),
            "llm_turn_total_ms": self.runtime_trace.get("turn_total_ms"),
            "llm_passes_done": self.runtime_trace.get("passes_done"),
            "tool_total_ms": round(sum(float(call.get("exec_ms") or 0.0) for call in tool_calls), 1) if tool_calls else 0.0,
            "tool_calls": tool_calls,
            "passes": self.runtime_trace.get("passes") or [],
            "transcript": self.transcript,
            "assistant_text": self.assistant_text,
        }


class AudioFrameConverter:
    def __init__(self) -> None:
        self._resampler: AudioResampler | None = None
        self._resampler_rate: int | None = None
        self._source_format: str | None = None
        self._source_layout: str | None = None

    def convert(self, frame: Any) -> tuple[bytes, int, dict[str, Any]]:
        sample_rate = int(getattr(frame, "sample_rate", 0) or getattr(frame, "rate", 0) or DEFAULT_AUDIO_SR)
        frame_format = getattr(getattr(frame, "format", None), "name", "") or "unknown"
        frame_layout = getattr(getattr(frame, "layout", None), "name", "") or "unknown"
        channels = int(getattr(getattr(frame, "layout", None), "nb_channels", 0) or 0)

        if (
            self._resampler is None
            or self._resampler_rate != sample_rate
            or self._source_format != frame_format
            or self._source_layout != frame_layout
        ):
            self._resampler = AudioResampler(format="s16", layout="mono", rate=sample_rate)
            self._resampler_rate = sample_rate
            self._source_format = frame_format
            self._source_layout = frame_layout

        out_frames = self._resampler.resample(frame)
        if not out_frames:
            return b"", sample_rate, {
                "frame_format": frame_format,
                "frame_layout": frame_layout,
                "frame_channels": channels,
                "frame_sample_rate": sample_rate,
            }

        chunks: list[bytes] = []
        for out_frame in out_frames:
            array = np.asarray(out_frame.to_ndarray()).reshape(-1)
            if array.dtype != np.int16:
                if np.issubdtype(array.dtype, np.floating):
                    array = (array.clip(-1.0, 1.0) * 32767.0).astype(np.int16)
                else:
                    max_val = max(abs(int(np.iinfo(array.dtype).min)), int(np.iinfo(array.dtype).max))
                    array = (array.astype(np.float32) / max_val * 32767.0).astype(np.int16)
            chunks.append(array.astype(np.int16, copy=False).tobytes())

        return b"".join(chunks), sample_rate, {
            "frame_format": frame_format,
            "frame_layout": frame_layout,
            "frame_channels": channels,
            "frame_sample_rate": sample_rate,
        }


class SynthAudioTrack(MediaStreamTrack):  # pragma: no cover - exercised via runtime
    kind = "audio"

    def __init__(self, sample_rate: int = DEFAULT_AUDIO_SR, frame_samples: int = 960) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._buffer = np.empty(0, dtype=np.int16)
        self._pts = 0
        self._time_base = Fraction(1, sample_rate)
        self._started_at: float | None = None

    async def recv(self) -> AudioFrame:
        if self._started_at is None:
            self._started_at = time.monotonic()

        target_time = self._pts / self.sample_rate
        elapsed = time.monotonic() - self._started_at
        if target_time > elapsed:
            await asyncio.sleep(target_time - elapsed)

        while self._buffer.shape[0] < self.frame_samples:
            try:
                chunk = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._buffer = np.concatenate([self._buffer, chunk])

        if self._buffer.shape[0] >= self.frame_samples:
            samples = self._buffer[: self.frame_samples]
            self._buffer = self._buffer[self.frame_samples :]
        else:
            samples = np.zeros(self.frame_samples, dtype=np.int16)
            if self._buffer.size:
                samples[: self._buffer.size] = self._buffer
                self._buffer = np.empty(0, dtype=np.int16)

        frame = AudioFrame(format="s16", layout="mono", samples=self.frame_samples)
        frame.sample_rate = self.sample_rate
        frame.pts = self._pts
        frame.time_base = self._time_base
        frame.planes[0].update(samples.tobytes())
        self._pts += self.frame_samples
        return frame

    def enqueue_pcm16(self, pcm_bytes: bytes, sample_rate: int) -> float:
        if not pcm_bytes:
            return 0.0
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).copy()
        if sample_rate != self.sample_rate:
            audio = pcm16_bytes_to_float32(samples.tobytes())
            audio = resample_audio(audio, src_sr=sample_rate, dst_sr=self.sample_rate)
            samples = np.frombuffer(float32_to_pcm16_bytes(audio), dtype=np.int16).copy()
        self._queue.put_nowait(samples)
        return samples.shape[0] / self.sample_rate

    def clear(self) -> None:
        self._buffer = np.empty(0, dtype=np.int16)
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class RokidBridgeManager:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.runtime.add_listener(self.handle_runtime_event)

        self._available = AIORTC_IMPORT_ERROR is None and SPEECH_IMPORT_ERROR is None and np is not None
        self._state_lock = asyncio.Lock()
        self._preview_condition = asyncio.Condition()
        self._state: dict[str, Any] = {
            "available": self._available,
            "dependency_error": str(AIORTC_IMPORT_ERROR or SPEECH_IMPORT_ERROR or ""),
            "session_active": False,
            "connection_state": "idle",
            "ice_connection_state": "new",
            "control_channel_state": "closed",
            "session_started_at": None,
            "device_name": "",
            "display_text": "",
            "status_text": "",
            "last_pong_id": "",
            "preview_sequence": 0,
            "preview_width": 0,
            "preview_height": 0,
            "last_frame_at": None,
            "audio_frames_seen": 0,
            "audio_input_format": "",
            "audio_input_layout": "",
            "audio_input_channels": 0,
            "audio_input_sample_rate": 0,
            "speech_state": "idle",
            "speech_backend_ready": False,
            "speech_backend_error": "",
            "speech_debug": {},
            "ignored_utterances_while_busy": 0,
            "last_user_text": "",
            "last_assistant_text": "",
            "last_latency_trace": {},
            "tts_playing": False,
            "recent_events": [],
            "session_url_examples": [],
            "preview_url": "/api/rokid/preview/latest.jpg?seq=0",
            "preview_stream_url": "/api/rokid/preview/stream.mjpg",
            "server_time": utc_now(),
        }
        self._preview_jpeg: bytes | None = None
        self._assistant_jpeg: bytes | None = None
        self._current_peer: RTCPeerConnection | None = None
        self._control_channel: RTCDataChannel | None = None
        self._current_session_token = 0
        self._speech_service = SpeechService()
        self._speech_stream = None
        self._speech_queue: asyncio.Queue[tuple[str, FinalizedUtterance]] | None = None
        self._speech_worker: asyncio.Task[None] | None = None
        self._tts_track: SynthAudioTrack | None = None
        self._tts_task: asyncio.Task[None] | None = None
        self._tts_finish_task: asyncio.Task[None] | None = None
        self._tts_token = 0
        self._audio_converter = AudioFrameConverter() if AudioResampler is not None else None
        self._speech_started_at: float | None = None
        self._turn_trace_counter = 0
        self._turn_traces: dict[str, RokidTurnTrace] = {}

    async def prewarm(self) -> None:
        if not self._available:
            return
        try:
            await asyncio.to_thread(self._speech_service.ensure_ready)
            await self._mutate_state(
                speech_backend_ready=True,
                speech_backend_error="",
            )
        except Exception as exc:
            await self._mutate_state(
                speech_backend_ready=False,
                speech_backend_error=str(exc),
                dependency_error=str(exc),
            )

    def snapshot(self) -> dict[str, Any]:
        return {**self._state, "server_time": utc_now()}

    def _next_turn_id(self, session_token: int) -> str:
        self._turn_trace_counter += 1
        return f"rokid-{session_token}-{self._turn_trace_counter}"

    def _create_turn_trace(self, session_token: int, utterance: FinalizedUtterance) -> RokidTurnTrace:
        now = time.perf_counter()
        utterance_duration_ms: float | None = None
        if utterance.start_s is not None and utterance.end_s is not None:
            utterance_duration_ms = max(0.0, (utterance.end_s - utterance.start_s) * 1000)
        trace = RokidTurnTrace(
            turn_id=self._next_turn_id(session_token),
            session_token=session_token,
            speech_started_at=self._speech_started_at,
            speech_finalized_at=now,
            utterance_start_s=utterance.start_s,
            utterance_end_s=utterance.end_s,
            utterance_duration_ms=utterance_duration_ms,
            utterance_samples=int(getattr(utterance.audio, "shape", [0])[0] if utterance.audio is not None else 0),
        )
        self._turn_traces[trace.turn_id] = trace
        return trace

    def _turn_trace(self, turn_id: str | None) -> RokidTurnTrace | None:
        if not turn_id:
            return None
        return self._turn_traces.get(turn_id)

    async def _finish_turn_trace(
        self,
        turn_id: str | None,
        *,
        outcome: str,
        assistant_text: str | None = None,
        runtime_trace: dict[str, Any] | None = None,
    ) -> None:
        trace = self._turn_trace(turn_id)
        if trace is None:
            return
        if assistant_text is not None:
            trace.assistant_text = assistant_text
        if runtime_trace is not None:
            trace.runtime_trace = runtime_trace
        summary = trace.summary(outcome=outcome)
        log_event("rokid_trace", **summary)
        await self._mutate_state(
            session_token=trace.session_token,
            last_latency_trace=summary,
            message=f"Turn trace ready: {turn_id}",
        )
        self._turn_traces.pop(trace.turn_id, None)

    async def _broadcast_state(self) -> None:
        await self.runtime.broadcast({"type": "rokid_state", "state": self.snapshot()})

    async def _mutate_state(self, *, message: str | None = None, session_token: int | None = None, **changes: Any) -> None:
        async with self._state_lock:
            if session_token is not None and session_token != self._current_session_token:
                return
            self._state.update(changes)
            if message:
                recent_events = list(self._state.get("recent_events") or [])
                recent_events.append({"timestamp": utc_now(), "message": message})
                self._state["recent_events"] = recent_events[-40:]
            self._state["session_url_examples"] = [
                f"http://{ip}:{cfg.ROKID_PUBLIC_PORT}/session" for ip in local_ipv4_addresses()
            ]
            self._state["preview_url"] = f"/api/rokid/preview/latest.jpg?seq={self._state['preview_sequence']}"
            self._state["preview_stream_url"] = "/api/rokid/preview/stream.mjpg"
            self._state["server_time"] = utc_now()
        await self._broadcast_state()

    async def _set_preview(self, preview_jpeg: bytes, assistant_jpeg: bytes, *, width: int, height: int, session_token: int) -> None:
        async with self._state_lock:
            if session_token != self._current_session_token:
                return
            self._preview_jpeg = preview_jpeg
            self._assistant_jpeg = assistant_jpeg
            self._state["preview_sequence"] = int(self._state["preview_sequence"]) + 1
            self._state["preview_width"] = width
            self._state["preview_height"] = height
            self._state["last_frame_at"] = utc_now()
        async with self._preview_condition:
            self._preview_condition.notify_all()
        await self._broadcast_state()

    async def iter_mjpeg_preview(self) -> AsyncIterator[bytes]:
        boundary = b"--frame"
        last_sequence = -1
        while True:
            async with self._state_lock:
                sequence = int(self._state["preview_sequence"])
                jpeg_bytes = self._preview_jpeg
            if jpeg_bytes is None or sequence == last_sequence:
                async with self._preview_condition:
                    await self._preview_condition.wait()
                continue
            last_sequence = sequence
            headers = (
                boundary
                + b"\r\n"
                + b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpeg_bytes)}\r\n".encode()
                + b"Cache-Control: no-store\r\n\r\n"
            )
            yield headers + jpeg_bytes + b"\r\n"

    async def latest_preview(self) -> bytes | None:
        return self._preview_jpeg

    async def _begin_session(self, pc: RTCPeerConnection) -> tuple[int, RTCPeerConnection | None]:
        async with self._state_lock:
            previous_peer = self._current_peer
            self._current_peer = pc
            self._control_channel = None
            self._current_session_token += 1
            token = self._current_session_token
            self._speech_queue = asyncio.Queue()
            self._speech_started_at = None
            self._turn_traces.clear()
            self._speech_stream = self._speech_service.create_stream() if self._speech_service.ready else None
            self._tts_track = SynthAudioTrack()
            self._state.update(
                session_active=True,
                connection_state="connecting",
                ice_connection_state="new",
                control_channel_state="closed",
                session_started_at=utc_now(),
                device_name="",
                last_pong_id="",
                audio_frames_seen=0,
                audio_input_format="",
                audio_input_layout="",
                audio_input_channels=0,
                audio_input_sample_rate=0,
                speech_state="listening",
                tts_playing=False,
                last_user_text="",
                last_assistant_text="",
                speech_backend_ready=self._speech_service.ready,
                speech_backend_error=self._speech_service.error or "",
                speech_debug={},
                ignored_utterances_while_busy=0,
                last_latency_trace={},
            )
        if self._speech_queue is not None:
            self._speech_worker = asyncio.create_task(self._speech_worker_loop(token, self._speech_queue))
        await self._mutate_state(message="Incoming Rokid session offer", session_token=token)
        return token, previous_peer

    async def _finish_session(self, session_token: int, *, connection_state: str, ice_connection_state: str | None = None, message: str | None = None) -> None:
        pending_turn_ids = list(self._turn_traces)
        if self._speech_worker is not None:
            self._speech_worker.cancel()
            self._speech_worker = None
        if self._tts_task is not None:
            self._tts_task.cancel()
            self._tts_task = None
        if self._tts_finish_task is not None:
            self._tts_finish_task.cancel()
            self._tts_finish_task = None
        self._stop_tts_output()
        async with self._state_lock:
            if session_token != self._current_session_token:
                return
            self._current_peer = None
            self._control_channel = None
            self._speech_stream = None
            self._speech_queue = None
            self._speech_started_at = None
            self._tts_track = None
            self._state["session_active"] = False
            self._state["connection_state"] = connection_state
            if ice_connection_state is not None:
                self._state["ice_connection_state"] = ice_connection_state
            self._state["control_channel_state"] = "closed"
            self._state["speech_state"] = "idle"
            self._state["tts_playing"] = False
            if message:
                recent_events = list(self._state.get("recent_events") or [])
                recent_events.append({"timestamp": utc_now(), "message": message})
                self._state["recent_events"] = recent_events[-40:]
        await self._broadcast_state()
        for turn_id in pending_turn_ids:
            await self._finish_turn_trace(turn_id, outcome="session_closed")

    async def _set_control_channel(self, channel: RTCDataChannel, session_token: int) -> bool:
        async with self._state_lock:
            if session_token != self._current_session_token:
                return False
            self._control_channel = channel
            self._state["control_channel_state"] = channel.readyState
        await self._broadcast_state()
        return True

    async def _clear_control_channel(self, channel: RTCDataChannel, session_token: int) -> None:
        async with self._state_lock:
            if session_token != self._current_session_token or self._control_channel is not channel:
                return
            self._control_channel = None
            self._state["control_channel_state"] = "closed"
        await self._mutate_state(message="Control channel closed", session_token=session_token)

    async def send_control(self, payload: dict[str, Any]) -> None:
        message = json.dumps(payload)
        async with self._state_lock:
            channel = self._control_channel
            if channel is None or channel.readyState != "open":
                raise RuntimeError("Control channel is not open")
            command_type = str(payload.get("type", "")).strip()
            if command_type == "display_text":
                self._state["display_text"] = str(payload.get("text", "")).strip()
            elif command_type == "status":
                self._state["status_text"] = str(payload.get("text", "")).strip()
            elif command_type == "clear_display":
                self._state["display_text"] = ""
        channel.send(message)
        await self._mutate_state(message=f"Sent control: {payload.get('type', 'unknown')}")

    async def _sync_initial_controls(self, channel: RTCDataChannel, session_token: int) -> None:
        async with self._state_lock:
            if session_token != self._current_session_token:
                return
            payloads: list[dict[str, Any]] = []
            display_text = str(self._state["display_text"]).strip()
            status_text = str(self._state["status_text"]).strip()
            if display_text:
                payloads.append({"type": "display_text", "text": display_text})
            if status_text:
                payloads.append({"type": "status", "text": status_text})
        for payload in payloads:
            with suppress(Exception):
                channel.send(json.dumps(payload))

    async def _handle_data_message(self, message: str, session_token: int) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            await self._mutate_state(session_token=session_token, message=f"Wearable sent text: {message[:80]}")
            return

        if not isinstance(payload, dict):
            return

        message_type = str(payload.get("type", "")).strip()
        if message_type == "wearable_ready":
            device_name = str(payload.get("device", "")).strip()
            await self._mutate_state(
                session_token=session_token,
                message=f"Wearable ready: {device_name or 'unknown device'}",
                device_name=device_name,
            )
            return
        if message_type == "pong":
            pong_id = str(payload.get("id", "")).strip()
            await self._mutate_state(
                session_token=session_token,
                message=f"Received pong{f' ({pong_id})' if pong_id else ''}",
                last_pong_id=pong_id,
            )
            return
        await self._mutate_state(session_token=session_token, message=f"Wearable message: {message_type or message[:80]}")

    async def _handle_speech_start(self, session_token: int) -> None:
        log_event("rokid_speech_start", session_token=session_token)
        await self._mutate_state(
            session_token=session_token,
            speech_state="listening",
            status_text="Listening…",
            message="Speech detected",
        )
        with suppress(Exception):
            await self.send_control({"type": "status", "text": "Listening…"})

    def _assistant_busy(self) -> bool:
        return self.runtime.is_generating or bool(self._state.get("tts_playing"))

    async def _speech_worker_loop(self, session_token: int, queue: asyncio.Queue[tuple[str, FinalizedUtterance]]) -> None:
        while True:
            turn_id, utterance = await queue.get()
            trace = self._turn_trace(turn_id)
            try:
                if self._assistant_busy():
                    log_event("rokid_turn_ignored", turn_id=turn_id, reason="assistant_busy", session_token=session_token)
                    await self._mutate_state(
                        session_token=session_token,
                        ignored_utterances_while_busy=int(self._state.get("ignored_utterances_while_busy", 0)) + 1,
                        message="Ignored utterance while assistant busy",
                    )
                    await self._finish_turn_trace(turn_id, outcome="ignored_while_busy")
                    continue
                if trace is not None:
                    trace.stt_started_at = time.perf_counter()
                log_event("rokid_stt_start", turn_id=turn_id, session_token=session_token)
                text = await asyncio.to_thread(self._speech_service.transcribe, utterance.audio)
                if trace is not None:
                    trace.stt_finished_at = time.perf_counter()
                    trace.transcript = text
                log_event(
                    "rokid_stt_end",
                    turn_id=turn_id,
                    session_token=session_token,
                    stt_ms=trace.summary(outcome="pending").get("stt_ms") if trace is not None else None,
                    transcript_len=len(text),
                    transcript_preview=text[:160],
                )
                if not text:
                    await self._finish_turn_trace(turn_id, outcome="empty_transcript")
                    continue
                if self._assistant_busy():
                    log_event("rokid_turn_ignored", turn_id=turn_id, reason="assistant_busy_after_stt", session_token=session_token)
                    await self._mutate_state(
                        session_token=session_token,
                        ignored_utterances_while_busy=int(self._state.get("ignored_utterances_while_busy", 0)) + 1,
                        message="Ignored transcribed utterance while assistant busy",
                    )
                    await self._finish_turn_trace(turn_id, outcome="ignored_after_stt")
                    continue
                async with self._state_lock:
                    assistant_jpeg = self._assistant_jpeg
                if trace is not None:
                    trace.submit_started_at = time.perf_counter()
                await self._mutate_state(
                    session_token=session_token,
                    speech_state="thinking",
                    last_user_text=text,
                    status_text="Thinking…",
                    message=f"Transcribed: {text[:80]}",
                )
                with suppress(Exception):
                    await self.send_control({"type": "status", "text": "Thinking…"})
                    await self.send_control({"type": "display_text", "text": hud_text(text)})
                log_event("rokid_turn_submit", turn_id=turn_id, session_token=session_token, transcript_len=len(text))
                await self.runtime.submit_rokid_turn(text, jpeg_bytes=assistant_jpeg, interrupt=False, turn_id=turn_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("rokid speech worker failed: %s", exc)
                log_event("rokid_turn_error", turn_id=turn_id, session_token=session_token, error=str(exc), stage="speech_worker")
                await self._mutate_state(
                    session_token=session_token,
                    speech_backend_ready=False,
                    speech_backend_error=str(exc),
                    speech_state="idle",
                    message=f"Speech worker error: {exc}",
                )
                await self._finish_turn_trace(turn_id, outcome="speech_worker_error")

    async def _consume_video(self, track: MediaStreamTrack, session_token: int) -> None:
        min_interval = 1 / PREVIEW_FPS if PREVIEW_FPS > 0 else 0
        next_frame_after = 0.0
        loop = asyncio.get_running_loop()
        try:
            while True:
                frame = await track.recv()
                now = loop.time()
                if now < next_frame_after:
                    continue
                next_frame_after = now + min_interval
                rgb_frame = frame.to_ndarray(format="rgb24")
                preview_jpeg = await asyncio.to_thread(encode_jpeg, rgb_frame)
                assistant_jpeg = await asyncio.to_thread(encode_jpeg, rgb_frame, width=224)
                await self._set_preview(
                    preview_jpeg,
                    assistant_jpeg,
                    width=frame.width,
                    height=frame.height,
                    session_token=session_token,
                )
        except Exception:
            logger.info("rokid: video track ended")

    async def _consume_audio(self, track: MediaStreamTrack, session_token: int) -> None:
        frames_seen = 0
        last_debug: dict[str, Any] = {}
        busy_drop_active = False
        try:
            while True:
                frame = await track.recv()
                frames_seen += 1
                if frames_seen % 25 == 0:
                    await self._mutate_state(
                        session_token=session_token,
                        audio_frames_seen=frames_seen,
                        speech_debug=last_debug,
                    )
                if self._speech_stream is None:
                    continue
                pcm16_bytes, sample_rate, audio_meta = self._audio_converter.convert(frame)
                if not pcm16_bytes:
                    if frames_seen % 25 == 0:
                        await self._mutate_state(
                            session_token=session_token,
                            audio_input_format=audio_meta.get("frame_format", ""),
                            audio_input_layout=audio_meta.get("frame_layout", ""),
                            audio_input_channels=audio_meta.get("frame_channels", 0),
                            audio_input_sample_rate=audio_meta.get("frame_sample_rate", 0),
                        )
                    continue
                if self._assistant_busy():
                    if not busy_drop_active:
                        self._speech_stream.reset()
                        self._speech_started_at = None
                        last_debug = {}
                        busy_drop_active = True
                    if frames_seen % 25 == 0:
                        await self._mutate_state(
                            session_token=session_token,
                            audio_input_format=audio_meta.get("frame_format", ""),
                            audio_input_layout=audio_meta.get("frame_layout", ""),
                            audio_input_channels=audio_meta.get("frame_channels", 0),
                            audio_input_sample_rate=audio_meta.get("frame_sample_rate", 0),
                            speech_debug=last_debug,
                        )
                    continue
                busy_drop_active = False
                result: FeedResult = self._speech_stream.feed_pcm16(pcm16_bytes, src_sr=sample_rate, channels=1)
                last_debug = result.debug
                if result.speech_started:
                    self._speech_started_at = time.perf_counter()
                    asyncio.create_task(self._handle_speech_start(session_token))
                    await self._mutate_state(
                        session_token=session_token,
                        speech_debug=result.debug,
                        audio_input_format=audio_meta.get("frame_format", ""),
                        audio_input_layout=audio_meta.get("frame_layout", ""),
                        audio_input_channels=audio_meta.get("frame_channels", 0),
                        audio_input_sample_rate=audio_meta.get("frame_sample_rate", 0),
                    )
                elif result.speech_ended or result.utterances:
                    await self._mutate_state(
                        session_token=session_token,
                        speech_debug=result.debug,
                        audio_input_format=audio_meta.get("frame_format", ""),
                        audio_input_layout=audio_meta.get("frame_layout", ""),
                        audio_input_channels=audio_meta.get("frame_channels", 0),
                        audio_input_sample_rate=audio_meta.get("frame_sample_rate", 0),
                        message=f"Speech finalized ({len(result.utterances)} utterance{'s' if len(result.utterances) != 1 else ''})",
                    )
                elif frames_seen % 25 == 0:
                    await self._mutate_state(
                        session_token=session_token,
                        speech_debug=result.debug,
                        audio_input_format=audio_meta.get("frame_format", ""),
                        audio_input_layout=audio_meta.get("frame_layout", ""),
                        audio_input_channels=audio_meta.get("frame_channels", 0),
                        audio_input_sample_rate=audio_meta.get("frame_sample_rate", 0),
                    )
                if self._speech_queue is not None:
                    for utterance in result.utterances:
                        trace = self._create_turn_trace(session_token, utterance)
                        log_event(
                            "rokid_utterance_finalized",
                            turn_id=trace.turn_id,
                            session_token=session_token,
                            utterance_start_s=utterance.start_s,
                            utterance_end_s=utterance.end_s,
                            utterance_duration_ms=round(trace.utterance_duration_ms, 1) if trace.utterance_duration_ms is not None else None,
                            utterance_samples=trace.utterance_samples,
                            speech_to_finalize_ms=trace.summary(outcome="pending").get("speech_to_finalize_ms"),
                        )
                        await self._speech_queue.put((trace.turn_id, utterance))
                    if result.utterances:
                        self._speech_started_at = None
        except Exception:
            logger.info("rokid: audio track ended")
        finally:
            await self._mutate_state(session_token=session_token, audio_frames_seen=frames_seen)

    def _prefer_video_codec(self, transceiver: Any, mime_type: str) -> None:
        try:
            capabilities = RTCRtpReceiver.getCapabilities("video")
        except Exception:
            logger.exception("rokid: failed to read video capabilities")
            return
        if capabilities is None:
            return
        preferences = [codec for codec in capabilities.codecs if codec.mimeType.lower() == mime_type.lower()]
        if preferences:
            transceiver.setCodecPreferences(preferences)

    async def handle_offer(self, raw_body: str) -> str:
        if not self._available:
            raise RuntimeError(str(AIORTC_IMPORT_ERROR or SPEECH_IMPORT_ERROR or "Rokid bridge unavailable"))
        try:
            await asyncio.to_thread(self._speech_service.ensure_ready)
            await self._mutate_state(speech_backend_ready=True, speech_backend_error="")
        except Exception as exc:
            await self._mutate_state(
                speech_backend_ready=False,
                speech_backend_error=str(exc),
                dependency_error=str(exc),
            )
            raise RuntimeError(str(exc)) from exc

        offer_sdp = parse_offer_sdp(raw_body)
        if not offer_sdp:
            raise ValueError("Missing SDP offer")

        offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
        pc = RTCPeerConnection()
        session_token, previous_peer = await self._begin_session(pc)

        if previous_peer is not None:
            with suppress(Exception):
                await previous_peer.close()

        video_transceiver = pc.addTransceiver("video", direction="recvonly")
        self._prefer_video_codec(video_transceiver, "video/H264")
        pc.addTransceiver("audio", direction="sendrecv")
        if self._tts_track is not None:
            pc.addTrack(self._tts_track)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            state = pc.connectionState
            await self._mutate_state(
                session_token=session_token,
                message=f"Peer connection: {state}",
                connection_state=state,
            )
            if state in {"failed", "closed"}:
                with suppress(Exception):
                    await pc.close()
                await self._finish_session(
                    session_token,
                    connection_state=state,
                    ice_connection_state=pc.iceConnectionState,
                    message="Peer connection closed",
                )

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange() -> None:
            await self._mutate_state(
                session_token=session_token,
                message=f"ICE: {pc.iceConnectionState}",
                ice_connection_state=pc.iceConnectionState,
            )

        @pc.on("datachannel")
        def on_datachannel(channel: RTCDataChannel) -> None:
            async def register_channel() -> None:
                assigned = await self._set_control_channel(channel, session_token)
                if not assigned:
                    channel.close()
                    return
                await self._mutate_state(
                    session_token=session_token,
                    message=f"Control channel opened: {channel.label}",
                    control_channel_state=channel.readyState,
                )
                if channel.readyState == "open":
                    await self._sync_initial_controls(channel, session_token)

            asyncio.create_task(register_channel())

            @channel.on("open")
            def on_open() -> None:
                asyncio.create_task(
                    self._mutate_state(
                        session_token=session_token,
                        message="Control channel ready",
                        control_channel_state=channel.readyState,
                    )
                )
                asyncio.create_task(self._sync_initial_controls(channel, session_token))

            @channel.on("message")
            def on_message(message: Any) -> None:
                if isinstance(message, str):
                    asyncio.create_task(self._handle_data_message(message, session_token))
                else:
                    asyncio.create_task(
                        self._mutate_state(
                            session_token=session_token,
                            message="Ignoring non-text data channel message",
                        )
                    )

            @channel.on("close")
            def on_close() -> None:
                asyncio.create_task(self._clear_control_channel(channel, session_token))

        @pc.on("track")
        def on_track(track: MediaStreamTrack) -> None:
            asyncio.create_task(self._mutate_state(session_token=session_token, message=f"Remote {track.kind} track active"))
            if track.kind == "video":
                asyncio.create_task(self._consume_video(track, session_token))
            elif track.kind == "audio":
                asyncio.create_task(self._consume_audio(track, session_token))

        try:
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
        except Exception as exc:
            logger.exception("rokid: failed to negotiate session")
            with suppress(Exception):
                await pc.close()
            await self._finish_session(session_token, connection_state="failed", message=f"Negotiation failed: {exc}")
            raise

        await self._mutate_state(
            session_token=session_token,
            message="Answered Rokid session offer",
            connection_state=pc.connectionState,
            ice_connection_state=pc.iceConnectionState,
        )
        return normalize_sdp(pc.localDescription.sdp)

    async def disconnect(self) -> None:
        async with self._state_lock:
            peer = self._current_peer
        if peer is not None:
            await peer.close()

    def _stop_tts_output(self) -> None:
        self._tts_token += 1
        if self._tts_track is not None:
            self._tts_track.clear()
        if self._tts_finish_task is not None:
            self._tts_finish_task.cancel()
            self._tts_finish_task = None

    async def _mark_tts_finished_after(self, duration_s: float, token: int, turn_id: str | None) -> None:
        await asyncio.sleep(duration_s)
        if token != self._tts_token:
            return
        trace = self._turn_trace(turn_id)
        if trace is not None:
            trace.audio_expected_finish_at = time.perf_counter()
        log_event(
            "rokid_audio_playback_expected_end",
            turn_id=turn_id,
            audio_playback_ms=round(duration_s * 1000, 1),
        )
        await self._mutate_state(tts_playing=False, speech_state="listening", status_text="Listening…")
        with suppress(Exception):
            await self.send_control({"type": "status", "text": "Listening…"})
        await self._finish_turn_trace(turn_id, outcome="played")

    async def _speak_text(self, text: str, *, turn_id: str | None, runtime_trace: dict[str, Any] | None = None) -> None:
        token = self._tts_token
        try:
            trace = self._turn_trace(turn_id)
            if trace is not None:
                trace.assistant_text = text
                trace.runtime_trace = runtime_trace or {}
                trace.tts_started_at = time.perf_counter()
            log_event("rokid_tts_start", turn_id=turn_id, text_len=len(text))
            pcm_bytes, sample_rate = await asyncio.to_thread(self._speech_service.synthesize_pcm16, text, out_sr=DEFAULT_AUDIO_SR)
            if token != self._tts_token or self._tts_track is None:
                return
            if trace is not None:
                trace.tts_finished_at = time.perf_counter()
            duration = self._tts_track.enqueue_pcm16(pcm_bytes, sample_rate)
            if trace is not None:
                trace.audio_enqueued_at = time.perf_counter()
                trace.audio_duration_ms = duration * 1000
            log_event(
                "rokid_tts_end",
                turn_id=turn_id,
                tts_synth_ms=trace.summary(outcome="pending").get("tts_synth_ms") if trace is not None else None,
                audio_bytes=len(pcm_bytes),
                audio_duration_ms=round(duration * 1000, 1),
            )
            await self._mutate_state(tts_playing=duration > 0, speech_state="speaking", last_assistant_text=text)
            if duration > 0:
                log_event("rokid_audio_enqueued", turn_id=turn_id, audio_duration_ms=round(duration * 1000, 1))
                self._tts_finish_task = asyncio.create_task(self._mark_tts_finished_after(duration, token, turn_id))
            else:
                await self._finish_turn_trace(turn_id, outcome="assistant_ready_no_audio", assistant_text=text, runtime_trace=runtime_trace or {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("rokid tts failed: %s", exc)
            log_event("rokid_tts_error", turn_id=turn_id, error=str(exc))
            await self._mutate_state(
                speech_backend_ready=False,
                speech_backend_error=str(exc),
                tts_playing=False,
                speech_state="idle",
                message=f"TTS error: {exc}",
            )
            await self._finish_turn_trace(turn_id, outcome="tts_error", assistant_text=text, runtime_trace=runtime_trace or {})

    async def handle_runtime_event(self, payload: dict[str, Any]) -> None:
        event_type = payload.get("type")
        if event_type == "user_turn" and payload.get("source") == "rokid":
            turn_id = payload.get("turn_id")
            await self._mutate_state(last_user_text=payload.get("text", ""), speech_state="thinking")
            with suppress(Exception):
                await self.send_control({"type": "display_text", "text": hud_text(payload.get("text", ""))})
                await self.send_control({"type": "status", "text": "Thinking…"})
            log_event("rokid_llm_turn_started", turn_id=turn_id, transcript_len=len(payload.get("text") or ""))
            return

        if event_type == "token":
            if self._state.get("session_active"):
                await self._mutate_state(speech_state="thinking", status_text="Thinking…")
            return

        if event_type == "assistant_end":
            text = (payload.get("text") or "").strip()
            turn_id = payload.get("turn_id")
            runtime_trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
            if not self._state.get("session_active"):
                return
            trace = self._turn_trace(turn_id)
            if trace is not None:
                trace.assistant_finished_at = time.perf_counter()
                trace.assistant_text = text
                trace.runtime_trace = runtime_trace
            log_event(
                "rokid_assistant_final",
                turn_id=turn_id,
                text_len=len(text),
                ttft_ms=payload.get("ttft_ms"),
                llm_turn_total_ms=runtime_trace.get("turn_total_ms"),
            )
            self._stop_tts_output()
            if not text:
                await self._mutate_state(tts_playing=False, speech_state="listening", status_text="Listening…")
                with suppress(Exception):
                    await self.send_control({"type": "status", "text": "Listening…"})
                await self._finish_turn_trace(turn_id, outcome="assistant_empty", runtime_trace=runtime_trace)
                return
            with suppress(Exception):
                await self.send_control({"type": "display_text", "text": hud_text(text)})
                await self.send_control({"type": "status", "text": "Speaking…"})
            self._tts_task = asyncio.create_task(self._speak_text(text, turn_id=turn_id, runtime_trace=runtime_trace))
            return

        if event_type == "error" and self._state.get("session_active"):
            turn_id = payload.get("turn_id")
            await self._mutate_state(speech_state="idle", status_text="Error")
            with suppress(Exception):
                await self.send_control({"type": "status", "text": "Error"})
            log_event("rokid_runtime_error", turn_id=turn_id, error=payload.get("message", "unknown"))
            await self._finish_turn_trace(turn_id, outcome="runtime_error")
