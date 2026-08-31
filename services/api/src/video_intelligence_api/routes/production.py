from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select

from video_intelligence_api.auth import AdminDependency
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    AgentDesiredStatus,
    AgentObservedStatus,
    Alert,
    AlertStatus,
    Camera,
    CameraAgent,
    CameraDiscoveryRun,
    CameraDiscoveryStatus,
    CameraStatus,
    EdgeHealthStatus,
    EdgeStationProfile,
    Event,
    OperationalHealthIncident,
    RecordingSegment,
    RecordingSegmentStatus,
    utc_now,
)
from video_intelligence_api.security import require_agent_key

router = APIRouter(tags=["production operations"])


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    key: str
    label: str
    passed: bool
    guidance: str

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "key": self.key,
            "label": self.label,
            "passed": self.passed,
            "guidance": self.guidance,
        }


@router.get("/production/readiness")
async def production_readiness(
    settings: SettingsDependency,
    actor: AdminDependency,
) -> dict[str, object]:
    """Explain every remaining hosted-production prerequisite without exposing secrets."""
    del actor
    cors_is_restricted = bool(settings.cors_origins) and "*" not in settings.cors_origins
    object_storage_ready = bool(
        settings.object_storage_bucket
        and settings.recording_storage_backend in {"s3", "supabase"}
        and (
            settings.recording_storage_backend == "s3"
            or (settings.supabase_url and settings.supabase_secret_key)
        )
    )
    checks = [
        ReadinessCheck(
            "environment",
            "Production environment selected",
            settings.environment == "production",
            "Set VIDEO_INTEL_API_ENVIRONMENT=production for the hosted deployment.",
        ),
        ReadinessCheck(
            "database",
            "PostgreSQL database",
            settings.database_url.startswith("postgresql"),
            "Use a managed or backed-up PostgreSQL database, not SQLite.",
        ),
        ReadinessCheck(
            "identity",
            "OIDC login configured",
            settings.dashboard_auth_mode == "oidc"
            and all([settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url]),
            "Choose an identity provider and configure issuer, audience, and JWKS URL.",
        ),
        ReadinessCheck(
            "edge_auth",
            "Per-device edge authentication",
            settings.edge_auth_mode == "device",
            "Set edge auth mode to device and enroll each station independently.",
        ),
        ReadinessCheck(
            "media_security",
            "Signed media access",
            settings.media_signing_key is not None,
            "Set a unique 32+ character media signing key in the secret manager.",
        ),
        ReadinessCheck(
            "alert_security",
            "Encrypted alert credentials",
            settings.alert_encryption_key is not None,
            "Set a unique alert encryption key in the secret manager.",
        ),
        ReadinessCheck(
            "camera_security",
            "Encrypted camera credentials",
            settings.camera_encryption_key is not None,
            "Set a unique camera encryption key in the secret manager.",
        ),
        ReadinessCheck(
            "cors",
            "Restricted browser origins",
            cors_is_restricted,
            "Allow only the exact production dashboard origins.",
        ),
        ReadinessCheck(
            "redis",
            "Redis event fan-out",
            bool(settings.redis_url),
            "Select a Redis provider and configure its TLS connection URL.",
        ),
        ReadinessCheck(
            "object_storage",
            "Durable evidence object storage",
            object_storage_ready,
            "Select the S3 recording backend and configure a private bucket.",
        ),
        ReadinessCheck(
            "backups",
            "Database backup target",
            settings.backup_target is not None,
            "Choose an encrypted backup destination and test a restore.",
        ),
        ReadinessCheck(
            "retention",
            "Approved retention policy",
            settings.retention_policy_configured,
            "Approve retention periods for video, events, audit logs, and identity data.",
        ),
    ]
    return {
        "ready": all(check.passed for check in checks),
        "environment": settings.environment,
        "checks": [check.as_dict() for check in checks],
        "blocking_checks": [check.key for check in checks if not check.passed],
    }


@router.get("/agent/metrics", dependencies=[Depends(require_agent_key)])
async def prometheus_metrics(
    session: SessionDependency,
) -> Response:
    """Small, dependency-free Prometheus endpoint for the internal service network."""

    async def count(model: type[object], *conditions: object) -> int:
        statement = select(func.count()).select_from(model)
        if conditions:
            statement = statement.where(*conditions)
        return int((await session.scalar(statement)) or 0)

    values = {
        "video_intelligence_cameras_total": await count(Camera),
        "video_intelligence_cameras_online": await count(
            Camera, Camera.status == CameraStatus.ONLINE
        ),
        "video_intelligence_cameras_error": await count(
            Camera, Camera.status == CameraStatus.ERROR
        ),
        "video_intelligence_agents_running": await count(
            CameraAgent, CameraAgent.observed_status == AgentObservedStatus.RUNNING
        ),
        "video_intelligence_agents_stale": await count(
            CameraAgent,
            CameraAgent.desired_status == AgentDesiredStatus.RUNNING,
            CameraAgent.lease_expires_at < utc_now(),
        ),
        "video_intelligence_agents_retry_backoff": await count(
            CameraAgent, CameraAgent.next_retry_at > utc_now()
        ),
        "video_intelligence_camera_reconnects_total": int(
            (await session.scalar(select(func.coalesce(func.sum(CameraAgent.reconnect_count), 0))))
            or 0
        ),
        "video_intelligence_recording_errors": await count(
            CameraAgent, CameraAgent.recording_state == "error"
        ),
        "video_intelligence_recording_dropped_frames_total": int(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(CameraAgent.recording_dropped_frames), 0))
                )
            )
            or 0
        ),
        "video_intelligence_recording_archive_ready": await count(
            RecordingSegment, RecordingSegment.status == RecordingSegmentStatus.READY
        ),
        "video_intelligence_recording_legal_holds": await count(
            RecordingSegment, RecordingSegment.legal_hold.is_(True)
        ),
        "video_intelligence_camera_discovery_queued": await count(
            CameraDiscoveryRun,
            CameraDiscoveryRun.status == CameraDiscoveryStatus.QUEUED,
        ),
        "video_intelligence_camera_discovery_failed": await count(
            CameraDiscoveryRun,
            CameraDiscoveryRun.status == CameraDiscoveryStatus.FAILED,
        ),
        "video_intelligence_alerts_open": await count(Alert, Alert.status == AlertStatus.OPEN),
        "video_intelligence_operational_health_active": await count(
            OperationalHealthIncident,
            OperationalHealthIncident.status != AlertStatus.RESOLVED,
        ),
        "video_intelligence_events_total": await count(Event),
        "video_intelligence_edge_stations_healthy": await count(
            EdgeStationProfile,
            EdgeStationProfile.health_status == EdgeHealthStatus.HEALTHY,
        ),
        "video_intelligence_edge_offline_queue_depth": int(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(EdgeStationProfile.offline_queue_depth), 0))
                )
            )
            or 0
        ),
    }
    lines = [
        "# HELP video_intelligence_build_info Static service build marker.",
        "# TYPE video_intelligence_build_info gauge",
        'video_intelligence_build_info{service="api"} 1',
    ]
    for key, value in values.items():
        lines.extend([f"# TYPE {key} gauge", f"{key} {value}"])
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")
