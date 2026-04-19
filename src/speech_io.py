from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from src.config import cfg

try:
    import numpy as np
    import torch
    from scipy.signal import resample_poly
    from silero_vad import load_silero_vad
    from faster_whisper import WhisperModel
    from kokoro import KPipeline

    SPEECH_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency-gated
    np = None
    torch = None
    resample_poly = None
    load_silero_vad = None
    WhisperModel = None
    KPipeline = None
    SPEECH_IMPORT_ERROR = exc

VAD_SR = 16000
VAD_FRAME_SAMPLES = 512
TTS_SR = 24000


class SpeechBackendUnavailable(RuntimeError):
    pass


@dataclass
class FinalizedUtterance:
    audio: Any
    start_s: float | None = None
    end_s: float | None = None


@dataclass
class FeedResult:
    speech_started: bool = False
    speech_ended: bool = False
    utterances: list[FinalizedUtterance] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


def pcm16_bytes_to_float32(pcm16_bytes: bytes, *, channels: int = 1):
    if np is None:
        raise SpeechBackendUnavailable("NumPy is unavailable")
    audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio


def resample_audio(audio, *, src_sr: int, dst_sr: int):
    if np is None or resample_poly is None:
        raise SpeechBackendUnavailable("SciPy is unavailable")
    if src_sr == dst_sr:
        return audio.astype(np.float32, copy=False)
    return resample_poly(audio, up=dst_sr, down=src_sr).astype(np.float32, copy=False)


def float32_to_pcm16_bytes(audio) -> bytes:
    clipped = audio.clip(-1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


class SpeechService:
    def __init__(self) -> None:
        self._ready = False
        self._error: str | None = None
        self._vad_model = None
        self._stt_model = None
        self._tts_pipeline = None
        self._load_lock = threading.Lock()
        self._stt_lock = threading.Lock()
        self._tts_lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def error(self) -> str | None:
        return self._error

    def ensure_ready(self) -> None:
        if self._ready:
            return
        if SPEECH_IMPORT_ERROR is not None:
            self._error = str(SPEECH_IMPORT_ERROR)
            raise SpeechBackendUnavailable(
                "Speech dependencies are unavailable. Install the updated requirements and macOS TTS prerequisites."
            ) from SPEECH_IMPORT_ERROR

        with self._load_lock:
            if self._ready:
                return
            try:
                self._vad_model = load_silero_vad()
                self._stt_model = WhisperModel(
                    cfg.SPEECH_STT_MODEL,
                    device=cfg.SPEECH_STT_DEVICE,
                    compute_type=cfg.SPEECH_STT_COMPUTE_TYPE,
                )
                self._tts_pipeline = KPipeline(lang_code=cfg.SPEECH_TTS_LANG_CODE)
                self._ready = True
                self._error = None
            except Exception as exc:
                self._error = str(exc)
                raise

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "ready": self._ready,
            "error": self._error,
            "stt_model": cfg.SPEECH_STT_MODEL,
            "tts_voice": cfg.SPEECH_TTS_VOICE,
            "language": cfg.SPEECH_LANGUAGE,
        }

    def create_stream(self) -> "StreamSpeechIO":
        self.ensure_ready()
        return StreamSpeechIO(self)

    def transcribe(self, audio_16k) -> str:
        self.ensure_ready()
        with self._stt_lock:
            segments, _info = self._stt_model.transcribe(
                audio_16k,
                language=cfg.SPEECH_LANGUAGE,
                word_timestamps=True,
                condition_on_previous_text=False,
                vad_filter=False,
            )
            segment_list = list(segments)
        return " ".join(
            segment.text.strip() for segment in segment_list if segment.text and segment.text.strip()
        ).strip()

    def synthesize_pcm16(self, text: str, *, out_sr: int = 48000) -> tuple[bytes, int]:
        self.ensure_ready()
        chunks = []
        with self._tts_lock:
            generator = self._tts_pipeline(text, voice=cfg.SPEECH_TTS_VOICE, speed=1.0)
            for _graphemes, _phonemes, audio in generator:
                chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return b"", out_sr
        waveform = np.concatenate(chunks).astype(np.float32, copy=False)
        if out_sr != TTS_SR:
            waveform = resample_audio(waveform, src_sr=TTS_SR, dst_sr=out_sr)
        return float32_to_pcm16_bytes(waveform), out_sr


class StreamSpeechIO:
    def __init__(self, service: SpeechService) -> None:
        self.service = service
        self._pending = np.empty(0, dtype=np.float32)
        self._pre_roll = deque(maxlen=10)
        self._utterance_parts: list[Any] = []
        self._current_sample = 0
        self._in_speech = False
        self._current_start_s: float | None = None
        self._silence_run_samples = 0
        self._speech_run_samples = 0
        self._last_rms_dbfs = -96.0
        self._last_speech_prob = 0.0
        self._noise_floor_dbfs = -72.0
        self._speech_starts = 0
        self._speech_ends = 0
        self._utterances_finalized = 0
        self._short_segments_dropped = 0
        self._min_silence_samples = int(VAD_SR * cfg.ROKID_VAD_MIN_SILENCE_MS / 1000)
        self._min_speech_samples = int(VAD_SR * cfg.ROKID_VAD_MIN_SPEECH_MS / 1000)
        self._speech_pad_samples = int(VAD_SR * cfg.ROKID_VAD_SPEECH_PAD_MS / 1000)

    def _speech_prob(self, frame) -> float:
        if torch is None:
            raise SpeechBackendUnavailable("Torch is unavailable")
        frame_tensor = torch.from_numpy(frame.copy())
        with torch.no_grad():
            score = self.service._vad_model(frame_tensor, VAD_SR)
        return float(score.item())

    def _frame_rms_dbfs(self, frame) -> float:
        rms = math.sqrt(float(np.mean(frame * frame)))
        if rms <= 1e-7:
            return -96.0
        return max(-96.0, min(0.0, 20.0 * math.log10(rms)))

    def _update_noise_floor(self, rms_dbfs: float) -> None:
        if self._in_speech:
            return
        alpha = 0.18 if rms_dbfs < self._noise_floor_dbfs else 0.04
        self._noise_floor_dbfs = ((1.0 - alpha) * self._noise_floor_dbfs) + (alpha * rms_dbfs)
        self._noise_floor_dbfs = max(-96.0, min(-12.0, self._noise_floor_dbfs))

    def _start_gate_dbfs(self) -> float:
        return max(cfg.ROKID_AUDIO_GATE_MIN_DBFS, self._noise_floor_dbfs + cfg.ROKID_AUDIO_GATE_DB_OFFSET)

    def _end_gate_dbfs(self) -> float:
        return max(cfg.ROKID_AUDIO_GATE_MIN_DBFS - 4.0, self._noise_floor_dbfs + cfg.ROKID_AUDIO_END_GATE_DB_OFFSET)

    def _debug_snapshot(self) -> dict[str, Any]:
        return {
            "in_speech": self._in_speech,
            "speech_prob": round(self._last_speech_prob, 4),
            "rms_dbfs": round(self._last_rms_dbfs, 1),
            "noise_floor_dbfs": round(self._noise_floor_dbfs, 1),
            "start_gate_dbfs": round(self._start_gate_dbfs(), 1),
            "end_gate_dbfs": round(self._end_gate_dbfs(), 1),
            "silence_ms": round((self._silence_run_samples / VAD_SR) * 1000, 1),
            "speech_ms": round((self._speech_run_samples / VAD_SR) * 1000, 1),
            "speech_starts": self._speech_starts,
            "speech_ends": self._speech_ends,
            "utterances_finalized": self._utterances_finalized,
            "short_segments_dropped": self._short_segments_dropped,
        }

    def _reset_active_speech(self) -> None:
        self._in_speech = False
        self._current_start_s = None
        self._utterance_parts = []
        self._pre_roll.clear()
        self._silence_run_samples = 0
        self._speech_run_samples = 0

    def _start_segment(self) -> None:
        pre_roll_frames = len(self._pre_roll)
        self._in_speech = True
        self._speech_starts += 1
        self._silence_run_samples = 0
        self._utterance_parts = list(self._pre_roll)
        self._speech_run_samples = len(self._utterance_parts) * VAD_FRAME_SAMPLES
        start_sample = max(0, self._current_sample - (pre_roll_frames * VAD_FRAME_SAMPLES))
        self._current_start_s = start_sample / VAD_SR
        self._pre_roll.clear()

    def _finalize_segment(self, result: FeedResult) -> None:
        total_samples = self._speech_run_samples
        trim_samples = max(0, self._silence_run_samples - self._speech_pad_samples)
        kept_samples = max(0, total_samples - trim_samples)

        if kept_samples < self._min_speech_samples:
            self._short_segments_dropped += 1
            self._reset_active_speech()
            return

        utterance_audio = np.concatenate(self._utterance_parts).astype(np.float32, copy=False)
        if trim_samples > 0 and trim_samples < utterance_audio.shape[0]:
            utterance_audio = utterance_audio[:-trim_samples]
        if utterance_audio.size < self._min_speech_samples:
            self._short_segments_dropped += 1
            self._reset_active_speech()
            return

        end_sample = max(0, self._current_sample - trim_samples)
        result.speech_ended = True
        result.utterances.append(
            FinalizedUtterance(
                audio=utterance_audio,
                start_s=self._current_start_s,
                end_s=end_sample / VAD_SR,
            )
        )
        self._speech_ends += 1
        self._utterances_finalized += 1
        self._reset_active_speech()

    def feed_pcm16(self, pcm16_bytes: bytes, *, src_sr: int, channels: int = 1) -> FeedResult:
        audio = pcm16_bytes_to_float32(pcm16_bytes, channels=channels)
        audio = resample_audio(audio, src_sr=src_sr, dst_sr=VAD_SR)
        result = FeedResult()

        if audio.size == 0:
            return result

        self._pending = np.concatenate([self._pending, audio])
        while self._pending.shape[0] >= VAD_FRAME_SAMPLES:
            frame = self._pending[:VAD_FRAME_SAMPLES]
            self._pending = self._pending[VAD_FRAME_SAMPLES:]
            self._current_sample += VAD_FRAME_SAMPLES
            self._last_rms_dbfs = self._frame_rms_dbfs(frame)
            self._update_noise_floor(self._last_rms_dbfs)
            self._last_speech_prob = self._speech_prob(frame)

            if not self._in_speech:
                self._pre_roll.append(frame.copy())

            start_candidate = self._last_speech_prob >= cfg.ROKID_VAD_START_THRESHOLD or (
                self._last_speech_prob >= cfg.ROKID_VAD_END_THRESHOLD
                and self._last_rms_dbfs >= self._start_gate_dbfs()
            )
            speech_continues = self._last_speech_prob >= cfg.ROKID_VAD_END_THRESHOLD or (
                self._last_rms_dbfs >= self._end_gate_dbfs()
            )

            if not self._in_speech and start_candidate:
                self._start_segment()
                result.speech_started = True
                continue

            if self._in_speech:
                self._utterance_parts.append(frame.copy())
                self._speech_run_samples += VAD_FRAME_SAMPLES
                if speech_continues:
                    self._silence_run_samples = 0
                else:
                    self._silence_run_samples += VAD_FRAME_SAMPLES

                if self._silence_run_samples >= self._min_silence_samples:
                    self._finalize_segment(result)

        result.debug = self._debug_snapshot()
        return result

    def reset(self) -> None:
        self._pending = np.empty(0, dtype=np.float32)
        self._pre_roll.clear()
        self._utterance_parts = []
        self._current_sample = 0
        self._in_speech = False
        self._current_start_s = None
        self._silence_run_samples = 0
        self._speech_run_samples = 0
        self._last_rms_dbfs = -96.0
        self._last_speech_prob = 0.0
        self._noise_floor_dbfs = -72.0
        self._speech_starts = 0
        self._speech_ends = 0
        self._utterances_finalized = 0
        self._short_segments_dropped = 0
