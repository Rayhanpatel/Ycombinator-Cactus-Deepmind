"""
Voice Handler — microphone capture, audio playback, and VAD.

NOTE: NOT on the web-server path. The browser does mic capture client-side
via getUserMedia in web/app.js, and src/main.py receives PCM16 LE bytes
over the WebSocket. This module is kept for the standalone CLI (src/agent.py)
and as a fallback if you ever go browser-less.

Provides a simple interface for recording audio from the microphone,
detecting when the user stops speaking (VAD), and saving/loading audio files.

Usage:
    from src.voice_handler import VoiceHandler
    handler = VoiceHandler()
    audio = handler.record_until_silence()
    handler.save_audio(audio, "output.wav")
"""

import logging
import struct
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

from src.config import cfg

try:
    import sounddevice as sd
    import soundfile as sf
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    logger.warning("sounddevice/soundfile not installed. Audio I/O disabled.")


class VoiceHandler:
    """
    Manages voice input/output for the agent.

    Methods:
        record_until_silence() → np.ndarray  (16kHz mono PCM)
        record_duration(seconds) → np.ndarray
        save_audio(audio, path)
        load_audio(path) → np.ndarray
        audio_to_pcm_list(audio) → list[int]  (for Cactus FFI)
    """

    def __init__(self, sample_rate: int = None):
        self.sample_rate = sample_rate or cfg.AUDIO_SAMPLE_RATE
        self.channels = 1  # Mono for Cactus/Whisper

    def record_duration(self, seconds: float = 5.0) -> np.ndarray:
        """Record audio for a fixed duration. Returns float32 numpy array."""
        if not AUDIO_AVAILABLE:
            raise RuntimeError("Audio libraries not available")

        logger.info(f"🎙️ Recording for {seconds}s…")
        audio = sd.rec(
            int(seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
        )
        sd.wait()
        logger.info("🎙️ Recording complete.")
        return audio.flatten()

    def record_until_silence(
        self,
        silence_threshold: float = 0.02,
        silence_duration: float = 1.5,
        max_duration: float = 30.0,
        chunk_size: int = 1024,
    ) -> np.ndarray:
        """
        Record audio until the user stops speaking.

        Args:
            silence_threshold: RMS level below which audio is "silence"
            silence_duration: Seconds of silence before stopping
            max_duration: Maximum recording length (safety cap)
            chunk_size: Samples per chunk
        """
        if not AUDIO_AVAILABLE:
            raise RuntimeError("Audio libraries not available")

        logger.info("🎙️ Listening… (speak now)")
        frames = []
        silent_chunks = 0
        chunks_for_silence = int(silence_duration * self.sample_rate / chunk_size)
        max_chunks = int(max_duration * self.sample_rate / chunk_size)

        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=chunk_size,
        )

        with stream:
            for i in range(max_chunks):
                chunk, _ = stream.read(chunk_size)
                frames.append(chunk.flatten())

                # RMS energy check
                rms = np.sqrt(np.mean(chunk ** 2))
                if rms < silence_threshold:
                    silent_chunks += 1
                else:
                    silent_chunks = 0

                if silent_chunks >= chunks_for_silence and len(frames) > chunks_for_silence:
                    break

        audio = np.concatenate(frames)
        duration = len(audio) / self.sample_rate
        logger.info(f"🎙️ Captured {duration:.1f}s of audio.")
        return audio

    def save_audio(self, audio: np.ndarray, path: str) -> Path:
        """Save audio array to a WAV file."""
        filepath = Path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(filepath), audio, self.sample_rate)
        logger.debug(f"💾 Audio saved to {filepath}")
        return filepath

    def load_audio(self, path: str) -> np.ndarray:
        """Load a WAV file and return as float32 numpy array."""
        audio, sr = sf.read(path, dtype="float32")
        if sr != self.sample_rate:
            logger.warning(f"Sample rate mismatch: file={sr}, expected={self.sample_rate}")
        if len(audio.shape) > 1:
            audio = audio[:, 0]  # Take first channel
        return audio

    @staticmethod
    def audio_to_pcm_list(audio: np.ndarray) -> list[int]:
        """
        Convert float32 audio to int16 PCM list for Cactus FFI.

        Cactus's `pcm_data` parameter expects `list[int]` of signed 16-bit samples.
        """
        int16_audio = (audio * 32767).astype(np.int16)
        return int16_audio.tolist()

    @property
    def is_available(self) -> bool:
        return AUDIO_AVAILABLE
