from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvidenceWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VIDEO_INTEL_EVIDENCE_",
        extra="ignore",
    )

    control_plane_url: AnyHttpUrl = "http://127.0.0.1:8000"
    agent_key: SecretStr = Field(min_length=16)
    worker_id: str | None = Field(default=None, min_length=1, max_length=120)
    poll_seconds: float = Field(default=2, ge=0.25, le=60)
    request_timeout_seconds: float = Field(default=30, gt=0, le=300)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> EvidenceWorkerSettings:
    return EvidenceWorkerSettings()
