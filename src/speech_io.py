from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from src.config import cfg

try:
    import numpy as np
    from scipy.signal import resample_poly
    from silero_vad import VADIterator, load_silero_vad
    from faster_whisper import WhisperModel
    from kokoro import KPipeline

    SPEECH_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency-gated
    np = None
    resample_poly = None
    VADIterator = None
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
    utterances: list[FinalizedUtterance] = field(default_factory=list)


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
        self._vad = VADIterator(
            self.service._vad_model,
            sampling_rate=VAD_SR,
            threshold=0.5,
            min_silence_duration_ms=300,
            speech_pad_ms=80,
        )
        self._pending = np.empty(0, dtype=np.float32)
        self._pre_roll = deque(maxlen=10)
        self._utterance_parts: list[Any] = []
        self._in_speech = False
        self._current_start_s: float | None = None

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

            if not self._in_speech:
                self._pre_roll.append(frame.copy())

            event = self._vad(frame, return_seconds=True)
            if event and "start" in event and not self._in_speech:
                self._in_speech = True
                self._current_start_s = float(event["start"])
                self._utterance_parts = list(self._pre_roll)
                result.speech_started = True
                continue

            if self._in_speech:
                self._utterance_parts.append(frame.copy())

            if event and "end" in event and self._in_speech:
                utterance_audio = np.concatenate(self._utterance_parts).astype(np.float32, copy=False)
                result.utterances.append(
                    FinalizedUtterance(
                        audio=utterance_audio,
                        start_s=self._current_start_s,
                        end_s=float(event["end"]),
                    )
                )
                self._in_speech = False
                self._current_start_s = None
                self._utterance_parts = []
                self._pre_roll.clear()

        return result

    def reset(self) -> None:
        self._vad.reset_states()
        self._pending = np.empty(0, dtype=np.float32)
        self._pre_roll.clear()
        self._utterance_parts = []
        self._in_speech = False
        self._current_start_s = None
