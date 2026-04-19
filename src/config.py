"""
Configuration — loads environment variables and provides defaults.

Usage:
    from src.config import cfg
    print(cfg.CACTUS_LLM_MODEL)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


class Config:
    """Centralized configuration pulled from environment variables."""

    # ── API Keys ──────────────────────────────────────────────
    CACTUS_API_KEY: str = os.getenv("CACTUS_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # ── Model Selection ───────────────────────────────────────
    CACTUS_LLM_MODEL: str = os.getenv("CACTUS_LLM_MODEL", "google/gemma-4-E4B-it")
    CACTUS_FUNCTION_MODEL: str = os.getenv("CACTUS_FUNCTION_MODEL", "google/functiongemma-270m-it")
    CACTUS_TRANSCRIPTION_MODEL: str = os.getenv("CACTUS_TRANSCRIPTION_MODEL", "openai/whisper-small")

    # ── Generation Parameters ─────────────────────────────────
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "512"))
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))

    # ── Cloud Fallback ────────────────────────────────────────
    ENABLE_CLOUD_FALLBACK: bool = os.getenv("ENABLE_CLOUD_FALLBACK", "true").lower() == "true"
    CLOUD_HANDOFF_THRESHOLD: float = float(os.getenv("CLOUD_HANDOFF_THRESHOLD", "0.5"))

    # ── Audio ─────────────────────────────────────────────────
    AUDIO_SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    VAD_SENSITIVITY: float = float(os.getenv("VAD_SENSITIVITY", "0.5"))
    SPEECH_LANGUAGE: str = os.getenv("SPEECH_LANGUAGE", "en")
    SPEECH_STT_MODEL: str = os.getenv("SPEECH_STT_MODEL", "small.en")
    SPEECH_STT_DEVICE: str = os.getenv("SPEECH_STT_DEVICE", "cpu")
    SPEECH_STT_COMPUTE_TYPE: str = os.getenv("SPEECH_STT_COMPUTE_TYPE", "int8")
    SPEECH_TTS_LANG_CODE: str = os.getenv("SPEECH_TTS_LANG_CODE", "a")
    SPEECH_TTS_VOICE: str = os.getenv("SPEECH_TTS_VOICE", "af_heart")
    ROKID_PUBLIC_PORT: int = int(os.getenv("ROKID_PUBLIC_PORT", os.getenv("PORT", "8000")))

    # ── Paths ─────────────────────────────────────────────────
    PROJECT_ROOT: Path = _project_root
    WEIGHTS_DIR: Path = _project_root / "weights"
    RECORDINGS_DIR: Path = _project_root / "recordings"

    def validate(self) -> list[str]:
        """Return a list of missing-but-required configuration items."""
        issues = []
        if not self.CACTUS_API_KEY:
            issues.append("CACTUS_API_KEY is not set")
        if self.ENABLE_CLOUD_FALLBACK and not self.GEMINI_API_KEY:
            issues.append("GEMINI_API_KEY is not set (required when ENABLE_CLOUD_FALLBACK=true)")
        return issues

    def __repr__(self) -> str:
        return (
            f"Config(\n"
            f"  LLM_MODEL={self.CACTUS_LLM_MODEL}\n"
            f"  FUNCTION_MODEL={self.CACTUS_FUNCTION_MODEL}\n"
            f"  TRANSCRIPTION_MODEL={self.CACTUS_TRANSCRIPTION_MODEL}\n"
            f"  MAX_TOKENS={self.MAX_TOKENS}\n"
            f"  TEMPERATURE={self.TEMPERATURE}\n"
            f"  CLOUD_FALLBACK={self.ENABLE_CLOUD_FALLBACK}\n"
            f")"
        )


# Singleton instance — import this everywhere
cfg = Config()
