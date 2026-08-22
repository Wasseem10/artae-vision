from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ArtaeLabsSettings(BaseSettings):
    """Validated settings for the internal Artae Labs API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ARTAE_LABS_",
        extra="ignore",
    )

    api_key: SecretStr = Field(min_length=1)
    index_id: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str = Field(
        default="https://api.cadere.studio/api/v1/labs",
        min_length=8,
    )
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    poll_interval_seconds: float = Field(default=5.0, gt=0, le=60)
    indexing_timeout_seconds: float = Field(default=900.0, gt=0, le=7200)
