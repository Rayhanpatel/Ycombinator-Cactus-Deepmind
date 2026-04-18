"""Tests for the Cactus engine wrapper."""

from src.cactus_engine import CactusEngine


def test_engine_not_initialized():
    """Engine should return error when not initialized."""
    engine = CactusEngine()
    result = engine.complete("test")
    assert result["success"] is False
    assert "not initialized" in result["error"]


def test_engine_availability():
    """Engine should report SDK availability."""
    engine = CactusEngine()
    # Will be False in CI/test environments without the SDK built
    assert isinstance(engine.is_available, bool)
    assert isinstance(engine.is_initialized, bool)
    assert engine.is_initialized is False
