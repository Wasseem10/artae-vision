from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings loaded from VIDEO_INTEL_* variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VIDEO_INTEL_",
        extra="ignore",
    )

    camera_index: int = Field(default=0, ge=0)
    camera_width: int = Field(default=1280, gt=0)
    camera_height: int = Field(default=720, gt=0)
    camera_fps: int = Field(default=30, gt=0)
    camera_open_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    camera_read_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    camera_reconnect_attempts: int = Field(default=5, ge=0, le=100)
    camera_reconnect_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    continuous_recording_enabled: bool = False
    continuous_recording_archive_enabled: bool = False
    continuous_recording_directory: Path = Path("artifacts/recordings")
    continuous_recording_spool_directory: Path = Path("artifacts/recording-upload-spool")
    continuous_recording_segment_seconds: float = Field(default=60, ge=10, le=3600)
    continuous_recording_retention_hours: float = Field(default=2, gt=0, le=24 * 365)
    continuous_recording_max_bytes: int = Field(
        default=10 * 1024 * 1024 * 1024,
        ge=100 * 1024 * 1024,
    )
    continuous_recording_queue_size: int = Field(default=120, ge=1, le=10000)

    model_name: str = Field(default="yolo26n.pt", min_length=1)
    pose_model_name: str = Field(default="yolo11n-pose.pt", min_length=1)
    confidence_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    device: str | None = None

    window_title: str = Field(
        default="AI Video Intelligence - Webcam Detection",
        min_length=1,
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    observer_enabled: bool = False
    observer_rule: str = Field(
        default="Describe important visible activity in this chronological frame window.",
        min_length=1,
        max_length=4000,
    )
    observer_sample_fps: float = Field(default=1.0, gt=0, le=30)
    observer_window_frames: int = Field(default=8, ge=2, le=60)
    observer_overlap_frames: int = Field(default=4, ge=0, le=59)
    observer_frame_width: int = Field(default=320, ge=96, le=1920)
    observer_frame_height: int = Field(default=180, ge=54, le=1080)
    observer_sheet_columns: int = Field(default=4, ge=1, le=10)
    observer_queue_size: int = Field(default=2, ge=1, le=20)
    observer_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    observer_provider: Literal["dry_run", "gemini", "qwen"] = "dry_run"
    observer_dry_run_trigger_every: int = Field(default=3, ge=1, le=10000)
    observer_max_requests_per_minute: int = Field(default=1, ge=1, le=600)
    observer_max_requests_per_day: int = Field(default=20, ge=1, le=1000000)
    replay_max_requests_per_minute: int = Field(default=20, ge=1, le=600)
    replay_max_requests_per_day: int = Field(default=20, ge=1, le=1000000)
    observer_show_sheet: bool = True
    observer_artifact_mode: Literal["none", "triggered", "all"] = "triggered"
    observer_artifacts_directory: Path = Path("artifacts/observer")
    qwen_api_key: SecretStr | None = None
    qwen_base_url: AnyHttpUrl = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = Field(default="qwen3.7-flash", min_length=1, max_length=120)
    gemini_api_key: SecretStr | None = None
    gemini_base_url: AnyHttpUrl = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = Field(default="gemini-3.5-flash-lite", min_length=1, max_length=120)
    gemini_verifier_model: str = Field(default="gemini-3.7-flash", min_length=1, max_length=120)

    agent_source: str = Field(default="webcam:0", min_length=1)
    camera_id: str = Field(default="camera-1", min_length=1)
    zone_name: str = Field(default="loading-zone", min_length=1)
    zone_points: str = Field(default="0.20,0.20;0.80,0.20;0.80,0.90;0.20,0.90")
    dwell_rule_id: str = Field(default="person-dwell", min_length=1)
    dwell_seconds: float = Field(default=10.0, gt=0)
    tracking_absence_grace_seconds: float = Field(default=1.0, ge=0)
    evidence_pre_seconds: float = Field(default=2.0, ge=0, le=30)
    evidence_post_seconds: float = Field(default=5.0, ge=0, le=120)
    events_directory: Path = Path("artifacts/events")
    offline_outbox_path: Path = Path("artifacts/offline/event-outbox.db")
    webhook_url: AnyHttpUrl | None = None
    webhook_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    control_plane_url: AnyHttpUrl | None = None
    control_plane_agent_key: SecretStr | None = None
    control_plane_device_token: SecretStr | None = None
    control_plane_camera_ref: str | None = Field(default=None, min_length=1, max_length=120)
    control_plane_rule_ref: str | None = Field(default=None, min_length=1, max_length=120)
    worker_id: str | None = Field(default=None, min_length=1, max_length=120)
    worker_poll_seconds: float = Field(default=2.0, ge=0.25, le=60)
    worker_telemetry_seconds: float = Field(default=0.5, ge=0.1, le=10)
    worker_heartbeat_seconds: float = Field(default=2.0, ge=0.25, le=30)
    worker_preview_fps: float = Field(default=8.0, ge=0.1, le=10)
    worker_preview_width: int = Field(default=960, ge=160, le=1920)
    worker_preview_jpeg_quality: int = Field(default=75, ge=30, le=95)
    worker_max_cameras: int = Field(default=1, ge=1, le=32)
    camera_discovery_max_devices: int = Field(default=100, ge=1, le=500)
    camera_onboarding_timeout_seconds: float = Field(default=10, ge=2, le=60)
    replay_input_price_per_million_usd: float = Field(default=0, ge=0)
    replay_output_price_per_million_usd: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_observer(self) -> "Settings":
        if self.continuous_recording_archive_enabled and not self.continuous_recording_enabled:
            raise ValueError("Recording archive upload requires continuous recording")
        if self.continuous_recording_archive_enabled and self.control_plane_url is None:
            raise ValueError("Recording archive upload requires the control-plane URL")
        if self.observer_overlap_frames >= self.observer_window_frames:
            raise ValueError("observer overlap must be smaller than the window")
        if self.observer_enabled and self.observer_provider == "qwen" and self.qwen_api_key is None:
            raise ValueError("VIDEO_INTEL_QWEN_API_KEY is required when observer is enabled")
        if (
            self.observer_enabled
            and self.observer_provider == "gemini"
            and self.gemini_api_key is None
        ):
            raise ValueError("VIDEO_INTEL_GEMINI_API_KEY is required when observer is enabled")
        return self


@lru_cache
def get_settings() -> Settings:
    """Create settings once per process."""

    return Settings()
