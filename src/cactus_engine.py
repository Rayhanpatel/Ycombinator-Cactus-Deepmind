"""
Cactus Engine Wrapper — manages on-device model lifecycle and inference.

Wraps the Cactus Python FFI for:
  - Model initialization & teardown
  - Chat completion (text + audio)
  - Transcription (file & streaming)
  - Function / tool calling
  - Cloud handoff detection

Usage:
    from src.cactus_engine import CactusEngine
    engine = CactusEngine()
    engine.initialize()
    result = engine.complete("What is the weather today?")
    engine.shutdown()
"""

import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ── Cactus SDK imports (available after `cactus build --python`) ──
# These come from the Cactus repo's src/ directory once built.
try:
    from src.downloads import ensure_model
    from src.cactus import (
        cactus_init,
        cactus_complete,
        cactus_destroy,
        cactus_reset,
        cactus_transcribe,
        cactus_vad,
    )
    CACTUS_AVAILABLE = True
except ImportError:
    logger.warning(
        "Cactus SDK not found. Run `scripts/setup_cactus.sh` first. "
        "Falling back to stub mode for development."
    )
    CACTUS_AVAILABLE = False

from src.config import cfg


class CactusEngine:
    """
    High-level wrapper around the Cactus on-device inference engine.

    Lifecycle:
        engine = CactusEngine()
        engine.initialize()        # loads model weights
        result = engine.complete(...)
        engine.shutdown()          # frees memory
    """

    def __init__(self):
        self._llm_handle: Optional[int] = None
        self._transcription_handle: Optional[int] = None
        self._initialized = False

    # ── Lifecycle ─────────────────────────────────────────────

    def initialize(self) -> None:
        """Download weights (if needed) and load the on-device model."""
        if not CACTUS_AVAILABLE:
            logger.error("Cannot initialize — Cactus SDK not installed.")
            return

        logger.info("⏳ Downloading / verifying model weights…")
        llm_weights = ensure_model(cfg.CACTUS_LLM_MODEL)
        logger.info(f"✅ LLM weights ready at {llm_weights}")

        logger.info("🔧 Initializing Cactus Engine…")
        self._llm_handle = cactus_init(str(llm_weights), None, False)
        self._initialized = True
        logger.info("🚀 Cactus Engine ready.")

    def initialize_transcription(self) -> None:
        """Load the transcription model (Whisper / Parakeet)."""
        if not CACTUS_AVAILABLE:
            return

        stt_weights = ensure_model(cfg.CACTUS_TRANSCRIPTION_MODEL)
        self._transcription_handle = cactus_init(str(stt_weights), None, False)
        logger.info(f"🎙️ Transcription model ready ({cfg.CACTUS_TRANSCRIPTION_MODEL})")

    def shutdown(self) -> None:
        """Free model memory."""
        if self._llm_handle is not None:
            cactus_destroy(self._llm_handle)
            self._llm_handle = None
        if self._transcription_handle is not None:
            cactus_destroy(self._transcription_handle)
            self._transcription_handle = None
        self._initialized = False
        logger.info("🛑 Cactus Engine shut down.")

    def reset(self) -> None:
        """Clear the KV cache without reloading weights."""
        if self._llm_handle is not None:
            cactus_reset(self._llm_handle)

    # ── Completion ────────────────────────────────────────────

    def complete(
        self,
        user_message: str,
        system_prompt: str = "You are a helpful voice assistant.",
        tools_json: Optional[str] = None,
        on_token: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        """
        Run a chat completion on-device.

        Returns the parsed JSON result dict with keys:
          success, response, cloud_handoff, function_calls,
          confidence, timing stats, etc.
        """
        if not self._initialized:
            return {"success": False, "error": "Engine not initialized"}

        messages = json.dumps([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ])

        options = json.dumps({
            "max_tokens": cfg.MAX_TOKENS,
            "temperature": cfg.TEMPERATURE,
        })

        raw = cactus_complete(
            self._llm_handle,
            messages,
            options,
            tools_json,
            on_token,
        )
        result = json.loads(raw)

        # Log performance stats
        if result.get("success"):
            logger.debug(
                f"⚡ TTFT={result.get('time_to_first_token_ms', '?')}ms | "
                f"Total={result.get('total_time_ms', '?')}ms | "
                f"Decode={result.get('decode_tps', '?')} tok/s | "
                f"Cloud={result.get('cloud_handoff', False)}"
            )

        return result

    def complete_with_audio(
        self,
        pcm_data: list[int],
        system_prompt: str = "You are a helpful voice assistant. Listen to the audio and respond.",
        tools_json: Optional[str] = None,
    ) -> dict:
        """
        Run a multimodal completion with raw audio input.
        Gemma 4 processes audio natively — no separate transcription step needed.

        Args:
            pcm_data: Raw PCM audio as a list of int16 samples (16kHz, mono).
        """
        if not self._initialized:
            return {"success": False, "error": "Engine not initialized"}

        messages = json.dumps([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "<audio>"},
        ])

        options = json.dumps({
            "max_tokens": cfg.MAX_TOKENS,
            "temperature": cfg.TEMPERATURE,
        })

        raw = cactus_complete(
            self._llm_handle,
            messages,
            options,
            tools_json,
            None,
            pcm_data,
        )
        return json.loads(raw)

    # ── Transcription ─────────────────────────────────────────

    def transcribe(self, audio_path: str) -> dict:
        """
        Transcribe an audio file using the dedicated transcription model.

        Returns dict with 'response' (full text) and 'segments' (timestamped).
        """
        if self._transcription_handle is None:
            return {"success": False, "error": "Transcription model not loaded"}

        raw = cactus_transcribe(
            self._transcription_handle,
            audio_path,
            None,  # prompt
            None,  # options
            None,  # callback
            None,  # pcm_data
        )
        return json.loads(raw)

    # ── VAD ───────────────────────────────────────────────────

    def detect_voice_activity(self, audio_path: str) -> dict:
        """Run Voice Activity Detection on an audio file."""
        if self._transcription_handle is None:
            return {"success": False, "error": "Transcription model not loaded"}

        raw = cactus_vad(self._transcription_handle, audio_path, None, None)
        return json.loads(raw)

    # ── Properties ────────────────────────────────────────────

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_available(self) -> bool:
        return CACTUS_AVAILABLE
