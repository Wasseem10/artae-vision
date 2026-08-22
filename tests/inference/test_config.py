import pytest
from pydantic import ValidationError
from video_intelligence_inference.config import Settings


def test_settings_reads_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIDEO_INTEL_CAMERA_INDEX", "1")
    monkeypatch.setenv("VIDEO_INTEL_CONFIDENCE_THRESHOLD", "0.6")

    settings = Settings(_env_file=None)

    assert settings.camera_index == 1
    assert settings.confidence_threshold == 0.6


def test_settings_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, confidence_threshold=1.1)


def test_settings_allow_dry_run_observer_without_qwen_key() -> None:
    settings = Settings(
        _env_file=None, observer_enabled=True, observer_provider="dry_run"
    )

    assert settings.qwen_api_key is None


def test_settings_require_qwen_key_for_qwen_observer() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, observer_enabled=True, observer_provider="qwen")


def test_settings_require_gemini_key_for_gemini_observer() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, observer_enabled=True, observer_provider="gemini")


def test_settings_accept_gemini_observer_with_key() -> None:
    settings = Settings(
        _env_file=None,
        observer_enabled=True,
        observer_provider="gemini",
        gemini_api_key="test-key",
    )

    assert settings.gemini_model == "gemini-3.5-flash-lite"


def test_settings_reject_observer_overlap_equal_to_window() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, observer_window_frames=10, observer_overlap_frames=10)
