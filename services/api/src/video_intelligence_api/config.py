from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OBJECT_CLASSES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]

DEFAULT_EVENT_TYPES = [
    "zone_dwell",
    "zone_presence",
    "zone_entry",
    "zone_exit",
    "count_threshold",
    "line_crossing",
    "semantic_vision",
]

DEVELOPMENT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


class ApiSettings(BaseSettings):
    """Validated control-plane settings loaded from `VIDEO_INTEL_API_*`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VIDEO_INTEL_API_",
        extra="ignore",
        populate_by_name=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default=(
            "postgresql+psycopg://video_intelligence:video_intelligence@"
            "localhost:5432/video_intelligence"
        ),
        min_length=8,
        validation_alias=AliasChoices("VIDEO_INTEL_API_DATABASE_URL", "POSTGRES_URL"),
    )
    agent_key: SecretStr = Field(min_length=16)
    edge_auth_mode: Literal["development", "device"] = "development"
    dashboard_key: SecretStr = Field(min_length=16)
    dashboard_auth_mode: Literal["development", "hybrid", "oidc"] = "development"
    development_organization_id: str = DEVELOPMENT_ORGANIZATION_ID
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_organization_claim: str = "org_id"
    oidc_role_claim: str = "role"
    oidc_algorithms: list[str] = Field(default_factory=lambda: ["RS256", "ES256"])
    oidc_auto_provision_memberships: bool = False
    oidc_auto_provision_organizations: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:3000", "http://localhost:3000"]
    )
    media_gateway_api_url: str = "http://127.0.0.1:9997"
    media_gateway_webrtc_url: str = "http://127.0.0.1:8889"
    media_gateway_rtsp_url: str = "rtsp://127.0.0.1:8554"
    media_gateway_mode: Literal["mediamtx", "disabled"] = "mediamtx"
    media_gateway_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    preview_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    preview_ttl_seconds: float = Field(default=10.0, ge=1, le=120)
    agent_lease_seconds: int = Field(default=10, ge=5, le=300)
    agent_restart_backoff_base_seconds: int = Field(default=5, ge=1, le=3600)
    agent_restart_backoff_max_seconds: int = Field(default=300, ge=1, le=86400)
    camera_discovery_lease_seconds: int = Field(default=30, ge=5, le=300)
    camera_onboarding_lease_seconds: int = Field(default=60, ge=10, le=600)
    camera_commissioning_lease_seconds: int = Field(default=90, ge=10, le=600)
    operational_health_camera_grace_seconds: int = Field(default=30, ge=1, le=3600)
    operational_health_camera_stale_seconds: int = Field(default=20, ge=5, le=3600)
    operational_health_frame_stale_seconds: int = Field(default=15, ge=5, le=3600)
    operational_health_edge_stale_seconds: int = Field(default=30, ge=5, le=3600)
    replay_lease_seconds: int = Field(default=900, ge=60, le=3600)
    replay_directory: Path = Path("artifacts/replays")
    replay_max_bytes: int = Field(default=512 * 1024 * 1024, ge=1024, le=10 * 1024**3)
    evidence_directory: Path = Path("artifacts/evidence")
    evidence_max_bytes: int = Field(default=512 * 1024 * 1024, ge=1024, le=10 * 1024**3)
    evidence_lease_seconds: int = Field(default=1800, ge=10, le=7200)
    recording_archive_directory: Path = Path("artifacts/recording-archive")
    recording_upload_max_bytes: int = Field(
        default=1024 * 1024 * 1024,
        ge=1024,
        le=20 * 1024**3,
    )
    recording_retention_hours: int = Field(default=2, ge=1, le=24 * 3650)
    recording_storage_backend: Literal["local", "s3", "supabase"] = "local"
    media_signing_key: SecretStr | None = Field(default=None, min_length=32)
    media_url_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    redis_url: str | None = None
    object_storage_endpoint: str | None = None
    object_storage_bucket: str | None = None
    object_storage_region: str = "us-east-1"
    object_storage_access_key: SecretStr | None = None
    object_storage_secret_key: SecretStr | None = None
    object_storage_session_token: SecretStr | None = None
    object_storage_force_path_style: bool = True
    object_storage_presign_seconds: int = Field(default=300, ge=30, le=3600)
    supabase_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VIDEO_INTEL_API_SUPABASE_URL", "SUPABASE_URL"),
    )
    supabase_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "VIDEO_INTEL_API_SUPABASE_SECRET_KEY",
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
    )
    backup_target: Path | None = None
    retention_policy_configured: bool = False
    alert_encryption_key: SecretStr | None = None
    camera_encryption_key: SecretStr | None = None
    alert_lease_seconds: int = Field(default=60, ge=10, le=600)
    alert_retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    alert_retry_max_seconds: int = Field(default=900, ge=1, le=86400)
    rule_compiler_provider: Literal["auto", "deterministic", "openai"] = "auto"
    openai_api_key: SecretStr | None = None
    openai_rule_compiler_model: str = Field(default="gpt-5-mini", min_length=1, max_length=120)
    detector_model: str = Field(default="yolo26n.pt", min_length=1, max_length=255)
    object_classes: list[str] = Field(default_factory=lambda: list(DEFAULT_OBJECT_CLASSES))
    event_types: list[str] = Field(default_factory=lambda: list(DEFAULT_EVENT_TYPES))

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        """Use the async psycopg driver for Vercel's standard Postgres URLs."""
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgresql://")

        if value.startswith("postgresql+psycopg://"):
            parsed = urlsplit(value)
            query = urlencode(
                [(name, item) for name, item in parse_qsl(parsed.query) if name != "supa"]
            )
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))
        return value

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "ApiSettings":
        if self.agent_restart_backoff_max_seconds < self.agent_restart_backoff_base_seconds:
            raise ValueError("Agent restart maximum backoff must be at least the base backoff")
        asymmetric_algorithms = {
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
            "ES512",
            "EdDSA",
        }
        if not self.oidc_algorithms or not set(self.oidc_algorithms) <= asymmetric_algorithms:
            raise ValueError("OIDC algorithms must use an explicit asymmetric allowlist")
        if self.dashboard_auth_mode in {"hybrid", "oidc"} and not all(
            [self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url]
        ):
            raise ValueError("OIDC issuer, audience, and JWKS URL are required in OIDC mode")
        if self.recording_storage_backend == "s3" and not self.object_storage_bucket:
            raise ValueError("S3 recording storage requires an object-storage bucket")
        if self.recording_storage_backend == "supabase" and not all(
            [self.object_storage_bucket, self.supabase_url, self.supabase_secret_key]
        ):
            raise ValueError(
                "Supabase recording storage requires a bucket, URL, and server secret key"
            )
        if (self.object_storage_access_key is None) != (self.object_storage_secret_key is None):
            raise ValueError("Object-storage access and secret keys must be configured together")
        if self.environment == "production":
            if self.dashboard_auth_mode != "oidc":
                raise ValueError("Production requires OIDC dashboard authentication")
            if self.edge_auth_mode != "device":
                raise ValueError("Production requires per-device edge authentication")
            if self.media_signing_key is None:
                raise ValueError("Production requires a media signing key")
            if self.alert_encryption_key is None:
                raise ValueError("Production requires an alert encryption key")
            if self.camera_encryption_key is None:
                raise ValueError("Production requires a camera encryption key")
        return self


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
