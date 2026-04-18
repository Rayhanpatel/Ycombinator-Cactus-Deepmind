"""Tests for the agent orchestrator."""

from src.config import Config


def test_config_defaults():
    """Config should have sensible defaults."""
    c = Config()
    assert c.MAX_TOKENS == 512
    assert c.TEMPERATURE == 0.7
    assert c.AUDIO_SAMPLE_RATE == 16000
    assert "gemma" in c.CACTUS_LLM_MODEL.lower()


def test_config_validation_no_keys():
    """Validation should flag missing API keys."""
    c = Config()
    c.CACTUS_API_KEY = ""
    c.ENABLE_CLOUD_FALLBACK = True
    c.GEMINI_API_KEY = ""
    issues = c.validate()
    assert len(issues) >= 1
