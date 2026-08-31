from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from video_intelligence_api.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class CameraStatus(enum.StrEnum):
    OFFLINE = "offline"
    ONLINE = "online"
    ERROR = "error"
    DISABLED = "disabled"


class SourceType(enum.StrEnum):
    WEBCAM = "webcam"
    FILE = "file"
    RTSP = "rtsp"


class GeometryType(enum.StrEnum):
    POLYGON = "polygon"
    LINE = "line"


class RuleStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class RuleCompilationStatus(enum.StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_REVIEW = "ready_for_review"
    ACCEPTED = "accepted"


class AgentDesiredStatus(enum.StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"


class AgentObservedStatus(enum.StrEnum):
    STOPPED = "stopped"
    WAITING = "waiting"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class EvidenceStatus(enum.StrEnum):
    AWAITING_UPLOAD = "awaiting_upload"
    QUEUED = "queued"
    INDEXING = "indexing"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class RecordingSegmentStatus(enum.StrEnum):
    LOCAL_ONLY = "local_only"
    READY = "ready"
    EXPIRED = "expired"
    FAILED = "failed"


class CameraDiscoveryStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CameraOnboardingStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CameraCommissioningStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    NEEDS_ATTENTION = "needs_attention"
    FAILED = "failed"


class VerificationStatus(enum.StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class AccuracyLabelOutcome(enum.StrEnum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    TRUE_NEGATIVE = "true_negative"


class AccuracyGateStatus(enum.StrEnum):
    COLLECTING = "collecting"
    READY = "ready"
    FAILING = "failing"
    DRIFTING = "drifting"


class ReviewSampleKind(enum.StrEnum):
    CANDIDATE = "candidate"
    NORMAL = "normal"
    UNCERTAIN = "uncertain"
    CHALLENGING = "challenging"


class ReviewSampleStatus(enum.StrEnum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    REVIEWING = "reviewing"
    DISPUTED = "disputed"
    LABELED = "labeled"
    SKIPPED = "skipped"


class DatasetVersionStatus(enum.StrEnum):
    DRAFT = "draft"
    FROZEN = "frozen"
    EXPORTED = "exported"


class PromotionStatus(enum.StrEnum):
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class OperationalHealthResource(enum.StrEnum):
    CAMERA = "camera"
    EDGE_DEVICE = "edge_device"


class OperationalHealthSeverity(enum.StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class EvidenceSearchStatus(enum.StrEnum):
    QUEUED = "queued"
    SEARCHING = "searching"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class AlertStatus(enum.StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertDeliveryStatus(enum.StrEnum):
    QUEUED = "queued"
    DELIVERING = "delivering"
    RETRYING = "retrying"
    DELIVERED = "delivered"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class OrganizationRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class EdgeDeviceStatus(enum.StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ReplayEvaluationStatus(enum.StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    SCORED = "scored"
    FAILED = "failed"


class ReplaySuiteRunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class VisualAgentPlanStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class ConnectorType(enum.StrEnum):
    MOCK = "mock"
    GENERIC_WEBHOOK = "generic_webhook"
    MESSAGING_WEBHOOK = "messaging_webhook"
    TICKET_WEBHOOK = "ticket_webhook"
    TELEGRAM = "telegram"


class ActionRiskLevel(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionApprovalMode(enum.StrEnum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class ActionExecutionStatus(enum.StrEnum):
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    DEAD_LETTERED = "dead_lettered"
    DENIED = "denied"
    SUPPRESSED = "suppressed"


class ContextSourceType(enum.StrEnum):
    SIMULATED_ACCESS_CONTROL = "simulated_access_control"
    GENERIC_EVENT_FEED = "generic_event_feed"


class CorrelationType(enum.StrEnum):
    COUNT_EXCEEDS_AUTHORIZATIONS = "count_exceeds_authorizations"


class CorrelationEvaluationStatus(enum.StrEnum):
    PENDING = "pending"
    MATCHED = "matched"
    CLEAR = "clear"
    FAILED = "failed"


class SceneItemKind(enum.StrEnum):
    REGION = "region"
    EQUIPMENT = "equipment"
    DISPLAY = "display"
    TRACKED_ENTITY = "tracked_entity"
    OTHER = "other"


class SceneReviewStatus(enum.StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SceneMemorySource(enum.StrEnum):
    AUTOMATIC = "automatic"
    OPERATOR = "operator"


class EdgeHealthStatus(enum.StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class EdgeUpdateStatus(enum.StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    APPLYING = "applying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_memberships_member"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("user_identities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[OrganizationRole] = mapped_column(
        Enum(OrganizationRole, native_enum=False, length=20), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EdgeDevice(Base):
    """An organization-owned inference host with a non-recoverable credential."""

    __tablename__ = "edge_devices"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_edge_devices_organization_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[EdgeDeviceStatus] = mapped_column(
        Enum(EdgeDeviceStatus, native_enum=False, length=20),
        nullable=False,
        default=EdgeDeviceStatus.ACTIVE,
    )
    max_concurrent_streams: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    credential_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_fingerprint: Mapped[str] = mapped_column(String(16), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_worker_id: Mapped[str | None] = mapped_column(String(120))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_cameras_organization_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    edge_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="SET NULL"), index=True
    )
    credential_encrypted: Mapped[str | None] = mapped_column(String(4000))
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=20), nullable=False
    )
    status: Mapped[CameraStatus] = mapped_column(
        Enum(CameraStatus, native_enum=False, length=20),
        nullable=False,
        default=CameraStatus.OFFLINE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CameraAgent(Base):
    """Durable operator intent plus the latest state reported by an edge worker."""

    __tablename__ = "camera_agents"

    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True
    )
    desired_status: Mapped[AgentDesiredStatus] = mapped_column(
        Enum(AgentDesiredStatus, native_enum=False, length=20),
        nullable=False,
        default=AgentDesiredStatus.STOPPED,
    )
    observed_status: Mapped[AgentObservedStatus] = mapped_column(
        Enum(AgentObservedStatus, native_enum=False, length=20),
        nullable=False,
        default=AgentObservedStatus.STOPPED,
    )
    worker_id: Mapped[str | None] = mapped_column(String(120))
    edge_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="SET NULL"), index=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_frame_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fps: Mapped[float | None] = mapped_column(Float)
    inference_latency_ms: Mapped[float | None] = mapped_column(Float)
    frame_width: Mapped[int | None] = mapped_column(Integer)
    frame_height: Mapped[int | None] = mapped_column(Integer)
    frames_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reconnect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recording_state: Mapped[str] = mapped_column(String(20), nullable=False, default="disabled")
    recording_segments_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recording_dropped_frames: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    recording_error: Mapped[str | None] = mapped_column(String(1000))
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class OperationalHealthIncident(Base):
    """Durable, self-resolving camera and edge reliability incident."""

    __tablename__ = "operational_health_incidents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "active_key",
            name="uq_operational_health_active_key",
        ),
        CheckConstraint(
            "(camera_id IS NOT NULL AND edge_device_id IS NULL) OR "
            "(camera_id IS NULL AND edge_device_id IS NOT NULL)",
            name="ck_operational_health_one_resource",
        ),
        Index(
            "ix_operational_health_organization_status",
            "organization_id",
            "status",
            "last_detected_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str | None] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), index=True
    )
    edge_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), index=True
    )
    resource_type: Mapped[OperationalHealthResource] = mapped_column(
        Enum(OperationalHealthResource, native_enum=False, length=20), nullable=False
    )
    condition: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[OperationalHealthSeverity] = mapped_column(
        Enum(OperationalHealthSeverity, native_enum=False, length=20), nullable=False
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, native_enum=False, length=20),
        nullable=False,
        default=AlertStatus.OPEN,
    )
    active_key: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str] = mapped_column(String(1000), nullable=False)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RecordingSegment(Base):
    """Tenant-owned historical camera segment optionally archived from an edge host."""

    __tablename__ = "recording_segments"
    __table_args__ = (
        UniqueConstraint("camera_id", "source_key", name="uq_recording_camera_source_key"),
        Index("ix_recording_segments_camera_started", "camera_id", "started_at"),
        Index("ix_recording_segments_retention", "status", "legal_hold", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edge_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="SET NULL"), index=True
    )
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    frame_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fps: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RecordingSegmentStatus] = mapped_column(
        Enum(RecordingSegmentStatus, native_enum=False, length=20),
        nullable=False,
        default=RecordingSegmentStatus.LOCAL_ONLY,
    )
    storage_uri: Mapped[str | None] = mapped_column(String(2048))
    media_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CameraDiscoveryRun(Base):
    """A bounded WS-Discovery scan executed by one enrolled edge device."""

    __tablename__ = "camera_discovery_runs"
    __table_args__ = (
        Index("ix_camera_discovery_device_status", "edge_device_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edge_device_id: Mapped[str] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CameraDiscoveryStatus] = mapped_column(
        Enum(CameraDiscoveryStatus, native_enum=False, length=20),
        nullable=False,
        default=CameraDiscoveryStatus.QUEUED,
    )
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    devices: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CameraOnboardingRun(Base):
    """Credentialed ONVIF profile resolution and preview verification on one edge."""

    __tablename__ = "camera_onboarding_runs"
    __table_args__ = (
        Index("ix_camera_onboarding_device_status", "edge_device_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edge_device_id: Mapped[str] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discovery_run_id: Mapped[str] = mapped_column(
        ForeignKey("camera_discovery_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_name: Mapped[str] = mapped_column(String(120), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    credential_encrypted: Mapped[str | None] = mapped_column(String(4000))
    verify_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[CameraOnboardingStatus] = mapped_column(
        Enum(CameraOnboardingStatus, native_enum=False, length=20),
        nullable=False,
        default=CameraOnboardingStatus.QUEUED,
    )
    profiles: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    selected_profile_token: Mapped[str | None] = mapped_column(String(255))
    camera_id: Mapped[str | None] = mapped_column(
        ForeignKey("cameras.id", ondelete="SET NULL"), index=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CameraCommissioningRun(Base):
    """Edge-executed stream quality assessment that never activates inference."""

    __tablename__ = "camera_commissioning_runs"
    __table_args__ = (
        Index("ix_camera_commissioning_camera_created", "camera_id", "created_at"),
        Index("ix_camera_commissioning_device_status", "edge_device_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edge_device_id: Mapped[str] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CameraCommissioningStatus] = mapped_column(
        Enum(CameraCommissioningStatus, native_enum=False, length=24),
        nullable=False,
        default=CameraCommissioningStatus.QUEUED,
    )
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    maximum_frames: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    readiness_score: Mapped[int | None] = mapped_column(Integer)
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AuditLog(Base):
    """Append-only record of authenticated operator mutations."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_organization_created", "organization_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_role: Mapped[OrganizationRole] = mapped_column(
        Enum(OrganizationRole, native_enum=False, length=20), nullable=False
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(120))
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    client_host: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class Zone(Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("camera_id", "name", name="uq_zones_camera_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    geometry_type: Mapped[GeometryType] = mapped_column(
        Enum(GeometryType, native_enum=False, length=20),
        nullable=False,
        default=GeometryType.POLYGON,
    )
    points: Mapped[list[dict[str, float]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("camera_id", "key", name="uq_rules_camera_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zone_id: Mapped[str] = mapped_column(
        ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False, default="object_dwell")
    object_class: Mapped[str] = mapped_column(String(80), nullable=False, default="person")
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    minimum_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.25)
    absence_grace_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[RuleStatus] = mapped_column(
        Enum(RuleStatus, native_enum=False, length=20),
        nullable=False,
        default=RuleStatus.DRAFT,
    )
    original_prompt: Mapped[str | None] = mapped_column(String(2000))
    spec_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    spec: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RuleCompilation(Base):
    """Versioned natural-language interpretation awaiting explicit operator review."""

    __tablename__ = "rule_compilations"
    __table_args__ = (Index("ix_rule_compilations_camera_created", "camera_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("rule_compilations.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prompt: Mapped[str] = mapped_column(String(2000), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_model: Mapped[str | None] = mapped_column(String(120))
    compiler_version: Mapped[str] = mapped_column(String(40), nullable=False, default="rule-ir/1")
    status: Mapped[RuleCompilationStatus] = mapped_column(
        Enum(RuleCompilationStatus, native_enum=False, length=30), nullable=False
    )
    compiled_rule: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(String(2000), nullable=False)
    clarification_question: Mapped[str | None] = mapped_column(String(1000))
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    accepted_rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("rules.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_camera_occurred_at", "camera_id", "occurred_at"),
        Index("ix_events_rule_occurred_at", "rule_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_event_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("rules.id", ondelete="SET NULL"), nullable=True
    )
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    object_class: Mapped[str] = mapped_column(String(80), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(120), nullable=False)
    entered_at_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    dwell_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    clip_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False, length=20),
        nullable=False,
        default=VerificationStatus.NOT_REQUIRED,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class VerificationCase(Base):
    """One durable proposer-verifier decision for a semantic camera event."""

    __tablename__ = "verification_cases"
    __table_args__ = (
        Index("ix_verification_cases_organization_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False, length=20), nullable=False
    )
    proposer_model: Mapped[str | None] = mapped_column(String(120))
    verifier_model: Mapped[str | None] = mapped_column(String(120))
    proposer_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    verifier_confidence: Mapped[float | None] = mapped_column(Float)
    proposal_summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    verifier_summary: Mapped[str | None] = mapped_column(String(1000))
    reasoning: Mapped[str] = mapped_column(String(2000), nullable=False)
    decision_source: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class FieldAccuracyLabel(Base):
    """Human-grounded live outcome used to score one camera/job pair."""

    __tablename__ = "field_accuracy_labels"
    __table_args__ = (
        Index("ix_field_accuracy_labels_rule_created", "rule_id", "created_at"),
        Index("ix_field_accuracy_labels_organization_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verification_case_id: Mapped[str | None] = mapped_column(
        ForeignKey("verification_cases.id", ondelete="CASCADE"), unique=True
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
    recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("recording_segments.id", ondelete="SET NULL"), index=True
    )
    outcome: Mapped[AccuracyLabelOutcome] = mapped_column(
        Enum(AccuracyLabelOutcome, native_enum=False, length=30), nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    environment_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RuleAccuracyPolicy(Base):
    """Per-job field promotion thresholds and permanent manual-only control."""

    __tablename__ = "rule_accuracy_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    minimum_positive_labels: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    minimum_negative_labels: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    minimum_challenging_labels: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    minimum_precision: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    minimum_recall: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    rolling_window_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    manual_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class FieldAccuracySnapshot(Base):
    """Immutable rolling live-accuracy gate result after one new human label."""

    __tablename__ = "field_accuracy_snapshots"
    __table_args__ = (
        Index("ix_field_accuracy_snapshots_rule_created", "rule_id", "created_at"),
        Index(
            "ix_field_accuracy_snapshots_organization_status",
            "organization_id",
            "gate_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    window_size: Mapped[int] = mapped_column(Integer, nullable=False)
    label_count: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False)
    challenging_count: Mapped[int] = mapped_column(Integer, nullable=False)
    true_positives: Mapped[int] = mapped_column(Integer, nullable=False)
    false_positives: Mapped[int] = mapped_column(Integer, nullable=False)
    false_negatives: Mapped[int] = mapped_column(Integer, nullable=False)
    true_negatives: Mapped[int] = mapped_column(Integer, nullable=False)
    precision: Mapped[float | None] = mapped_column(Float)
    recall: Mapped[float | None] = mapped_column(Float)
    f1: Mapped[float | None] = mapped_column(Float)
    gate_status: Mapped[AccuracyGateStatus] = mapped_column(
        Enum(AccuracyGateStatus, native_enum=False, length=20), nullable=False
    )
    automatic_release_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recommendations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EvidenceSamplingPolicy(Base):
    """Per-job controls for bounded background evidence sampling."""

    __tablename__ = "evidence_sampling_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    normal_sample_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=900
    )
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    review_sla_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    required_reviews: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    require_adjudication: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EvidenceReviewSample(Base):
    """One deduplicated review unit sourced from a proposal or ordinary footage."""

    __tablename__ = "evidence_review_samples"
    __table_args__ = (
        UniqueConstraint("organization_id", "dedup_key", name="uq_review_sample_org_dedup"),
        Index("ix_review_samples_org_status_priority", "organization_id", "status", "priority"),
        Index("ix_review_samples_rule_created", "rule_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verification_case_id: Mapped[str | None] = mapped_column(
        ForeignKey("verification_cases.id", ondelete="CASCADE"), unique=True
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), index=True
    )
    recording_id: Mapped[str | None] = mapped_column(
        ForeignKey("recording_segments.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[ReviewSampleKind] = mapped_column(
        Enum(ReviewSampleKind, native_enum=False, length=20), nullable=False
    )
    status: Mapped[ReviewSampleStatus] = mapped_column(
        Enum(ReviewSampleStatus, native_enum=False, length=20),
        nullable=False,
        default=ReviewSampleStatus.QUEUED,
    )
    priority: Mapped[float] = mapped_column(Float, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    environment_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    label_id: Mapped[str | None] = mapped_column(
        ForeignKey("field_accuracy_labels.id", ondelete="SET NULL"), unique=True
    )
    consensus_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    adjudicated_by: Mapped[str | None] = mapped_column(String(255))
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EvidenceDatasetVersion(Base):
    """Immutable-on-freeze manifest of reviewed evidence."""

    __tablename__ = "evidence_dataset_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", "version", name="uq_dataset_org_name_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DatasetVersionStatus] = mapped_column(
        Enum(DatasetVersionStatus, native_enum=False, length=20),
        nullable=False,
        default=DatasetVersionStatus.DRAFT,
    )
    selection: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    balance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EvidenceDatasetSample(Base):
    __tablename__ = "evidence_dataset_samples"
    __table_args__ = (UniqueConstraint("dataset_id", "sample_id", name="uq_dataset_sample"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_dataset_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_review_samples.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    label_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EvidenceReviewVote(Base):
    """Independent reviewer judgment retained before consensus or adjudication."""

    __tablename__ = "evidence_review_votes"
    __table_args__ = (
        UniqueConstraint("sample_id", "reviewer", name="uq_review_vote_sample_reviewer"),
        Index("ix_review_votes_sample_created", "sample_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_review_samples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    reasoning: Mapped[str] = mapped_column(String(2000), nullable=False)
    environment_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DatasetReplayBuild(Base):
    """Idempotent mapping from one frozen dataset to executable replay baselines."""

    __tablename__ = "dataset_replay_builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("replay_suites.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    evaluation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    skipped_samples: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DeploymentPromotion(Base):
    """Immutable comparison and explicit production promotion/rollback decision."""

    __tablename__ = "deployment_promotions"
    __table_args__ = (
        Index("ix_deployment_promotions_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_plan_id: Mapped[str] = mapped_column(
        ForeignKey("visual_agent_plans.id", ondelete="RESTRICT"), nullable=False
    )
    baseline_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("visual_agent_plans.id", ondelete="SET NULL")
    )
    candidate_run_id: Mapped[str] = mapped_column(
        ForeignKey("replay_suite_runs.id", ondelete="RESTRICT"), nullable=False
    )
    baseline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("replay_suite_runs.id", ondelete="SET NULL")
    )
    status: Mapped[PromotionStatus] = mapped_column(
        Enum(PromotionStatus, native_enum=False, length=20),
        nullable=False,
        default=PromotionStatus.READY,
    )
    comparison: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rollback_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(String(2000))
    rolled_back_by: Mapped[str | None] = mapped_column(String(255))
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rollback_reason: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AlertChannel(Base):
    """A reusable outbound webhook; the signing secret is encrypted at rest."""

    __tablename__ = "alert_channels"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_alert_channels_organization_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    webhook_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    signing_secret_encrypted: Mapped[str] = mapped_column(String(1000), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RuleAlertChannel(Base):
    """Per-job routing, noise control, and optional delayed escalation."""

    __tablename__ = "rule_alert_channels"
    __table_args__ = (
        UniqueConstraint("rule_id", "channel_id", name="uq_rule_alert_channels_route"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("alert_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Alert(Base):
    """Operator-visible incident state created exactly once for each event."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, native_enum=False, length=20),
        nullable=False,
        default=AlertStatus.OPEN,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(120))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AlertDelivery(Base):
    """Durable, leased delivery attempt state for one alert/channel pair."""

    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("alert_id", "channel_id", name="uq_alert_deliveries_route"),
        Index("ix_alert_deliveries_claim", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("alert_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[AlertDeliveryStatus] = mapped_column(
        Enum(AlertDeliveryStatus, native_enum=False, length=20),
        nullable=False,
        default=AlertDeliveryStatus.QUEUED,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(1000))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EvidenceAsset(Base):
    """A completed event clip plus its asynchronous intelligence-provider state."""

    __tablename__ = "evidence_assets"
    __table_args__ = (Index("ix_evidence_assets_status_updated", "status", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[EvidenceStatus] = mapped_column(
        Enum(EvidenceStatus, native_enum=False, length=30),
        nullable=False,
        default=EvidenceStatus.AWAITING_UPLOAD,
    )
    storage_uri: Mapped[str | None] = mapped_column(String(2048))
    media_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="artae_labs")
    external_index_id: Mapped[str | None] = mapped_column(String(200))
    external_video_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EvidenceSearch(Base):
    """A durable natural-language search request and its timecoded result snapshot."""

    __tablename__ = "evidence_searches"
    __table_args__ = (Index("ix_evidence_searches_status_updated", "status", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query: Mapped[str] = mapped_column(String(1000), nullable=False)
    camera_id: Mapped[str | None] = mapped_column(
        ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True
    )
    limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[EvidenceSearchStatus] = mapped_column(
        Enum(EvidenceSearchStatus, native_enum=False, length=30), nullable=False
    )
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ReplayEvaluation(Base):
    """A reproducible labeled-video evaluation of one compiled camera job."""

    __tablename__ = "replay_evaluations"
    __table_args__ = (
        Index(
            "ix_replay_evaluations_organization_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_replay_evaluations_scenario_source",
            "scenario_key",
            "source_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compilation_id: Mapped[str] = mapped_column(
        ForeignKey("rule_compilations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    prompt: Mapped[str] = mapped_column(String(2000), nullable=False)
    scenario_key: Mapped[str | None] = mapped_column(String(80))
    scenario_variant: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unclassified"
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="unclassified")
    environment_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    execution_strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    compiled_rule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    execution_plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    expected_intervals: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    predicted_intervals: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[ReplayEvaluationStatus] = mapped_column(
        Enum(ReplayEvaluationStatus, native_enum=False, length=20),
        nullable=False,
        default=ReplayEvaluationStatus.DRAFT,
    )
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_progress_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ReplaySuite(Base):
    """A tenant-owned collection of replay baselines and deterministic gates."""

    __tablename__ = "replay_suites"
    __table_args__ = (
        Index("ix_replay_suites_organization_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    evaluation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    minimum_macro_f1: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    minimum_macro_recall: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    maximum_false_positives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximum_estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    require_pricing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ReplaySuiteRun(Base):
    """An immutable aggregate result for one execution of a replay suite."""

    __tablename__ = "replay_suite_runs"
    __table_args__ = (
        Index("ix_replay_suite_runs_suite_created", "suite_id", "created_at"),
        Index(
            "ix_replay_suite_runs_organization_status",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("replay_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluation_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[ReplaySuiteRunStatus] = mapped_column(
        Enum(ReplaySuiteRunStatus, native_enum=False, length=20),
        nullable=False,
        default=ReplaySuiteRunStatus.QUEUED,
    )
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    gate_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class VisualAgentPlan(Base):
    """Versioned, reviewable instructions that turn one camera rule into a safe agent."""

    __tablename__ = "visual_agent_plans"
    __table_args__ = (
        UniqueConstraint("camera_id", "revision", name="uq_visual_agent_plans_camera_revision"),
        Index("ix_visual_agent_plans_organization_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compilation_id: Mapped[str | None] = mapped_column(
        ForeignKey("rule_compilations.id", ondelete="SET NULL"), nullable=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("visual_agent_plans.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[VisualAgentPlanStatus] = mapped_column(
        Enum(VisualAgentPlanStatus, native_enum=False, length=20),
        nullable=False,
        default=VisualAgentPlanStatus.DRAFT,
    )
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    unsupported_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    regression_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("replay_suite_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class VisualAgentSimulation(Base):
    """A side-effect-free execution trace for operator review before deployment."""

    __tablename__ = "visual_agent_simulations"
    __table_args__ = (Index("ix_visual_agent_simulations_plan_created", "plan_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("visual_agent_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class IntegrationConnector(Base):
    """Tenant-owned connector with encrypted credentials and explicit write scopes."""

    __tablename__ = "integration_connectors"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name", name="uq_integration_connectors_organization_name"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    connector_type: Mapped[ConnectorType] = mapped_column(
        Enum(ConnectorType, native_enum=False, length=30), nullable=False
    )
    endpoint_url: Mapped[str | None] = mapped_column(String(2048))
    credential_encrypted: Mapped[str] = mapped_column(String(4000), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class RuleActionBinding(Base):
    """A validated mapping from a visual rule to one guarded connector action."""

    __tablename__ = "rule_action_bindings"
    __table_args__ = (
        UniqueConstraint(
            "rule_id", "connector_id", "action_type", name="uq_rule_action_bindings_action"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("integration_connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[ActionRiskLevel] = mapped_column(
        Enum(ActionRiskLevel, native_enum=False, length=20), nullable=False
    )
    approval_mode: Mapped[ActionApprovalMode] = mapped_column(
        Enum(ActionApprovalMode, native_enum=False, length=20), nullable=False
    )
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    payload_template: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ActionExecution(Base):
    """Durable, idempotent, approval-aware execution of one connector action."""

    __tablename__ = "action_executions"
    __table_args__ = (
        UniqueConstraint("event_id", "binding_id", name="uq_action_executions_event_binding"),
        UniqueConstraint("idempotency_key", name="uq_action_executions_idempotency_key"),
        Index("ix_action_executions_claim", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    binding_id: Mapped[str] = mapped_column(
        ForeignKey("rule_action_bindings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("integration_connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[ActionRiskLevel] = mapped_column(
        Enum(ActionRiskLevel, native_enum=False, length=20), nullable=False
    )
    status: Mapped[ActionExecutionStatus] = mapped_column(
        Enum(ActionExecutionStatus, native_enum=False, length=30), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manual_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    worker_id: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(1000))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denied_by: Mapped[str | None] = mapped_column(String(255))
    denied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denial_reason: Mapped[str | None] = mapped_column(String(500))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ContextSource(Base):
    """Tenant-owned read/query source that emits normalized time-stamped observations."""

    __tablename__ = "context_sources"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_context_sources_organization_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[ContextSourceType] = mapped_column(
        Enum(ContextSourceType, native_enum=False, length=40), nullable=False
    )
    endpoint_url: Mapped[str | None] = mapped_column(String(2048))
    credential_encrypted: Mapped[str | None] = mapped_column(String(4000))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ContextObservation(Base):
    """A vendor-neutral external fact used for temporal correlation."""

    __tablename__ = "context_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "source_event_id", name="uq_context_observations_source_event"
        ),
        Index("ix_context_observations_source_occurred", "source_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("context_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entity_key: Mapped[str | None] = mapped_column(String(255))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RuleCorrelationPolicy(Base):
    """Deterministic windowed join between one visual rule and one context source."""

    __tablename__ = "rule_correlation_policies"
    __table_args__ = (
        UniqueConstraint(
            "rule_id", "source_id", "correlation_type", name="uq_rule_correlation_policy"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("context_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    correlation_type: Mapped[CorrelationType] = mapped_column(
        Enum(CorrelationType, native_enum=False, length=50), nullable=False
    )
    observation_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="access_granted"
    )
    visual_count_field: Mapped[str] = mapped_column(
        String(80), nullable=False, default="person_count"
    )
    window_before_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    window_after_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class CorrelationEvaluation(Base):
    """Durable outcome of joining a visual event with external observations."""

    __tablename__ = "correlation_evaluations"
    __table_args__ = (
        UniqueConstraint("event_id", "policy_id", name="uq_correlation_evaluation_event_policy"),
        Index("ix_correlation_evaluations_due", "status", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("rule_correlation_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("context_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CorrelationEvaluationStatus] = mapped_column(
        Enum(CorrelationEvaluationStatus, native_enum=False, length=20), nullable=False
    )
    visual_count: Mapped[int] = mapped_column(Integer, nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    explanation: Mapped[str | None] = mapped_column(String(1000))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SceneMemoryItem(Base):
    """A stable region, equipment item, display, or tracked entity learned from video."""

    __tablename__ = "scene_memory_items"
    __table_args__ = (
        UniqueConstraint("camera_id", "stable_key", name="uq_scene_memory_camera_key"),
        Index("ix_scene_memory_camera_last_seen", "camera_id", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stable_key: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[SceneItemKind] = mapped_column(
        Enum(SceneItemKind, native_enum=False, length=30), nullable=False
    )
    bounding_box: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    current_state: Mapped[str] = mapped_column(String(160), nullable=False, default="observed")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    relationships: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[SceneMemorySource] = mapped_column(
        Enum(SceneMemorySource, native_enum=False, length=20), nullable=False
    )
    review_status: Mapped[SceneReviewStatus] = mapped_column(
        Enum(SceneReviewStatus, native_enum=False, length=20), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SceneChange(Base):
    """Auditable state transition for one scene-memory item."""

    __tablename__ = "scene_changes"
    __table_args__ = (Index("ix_scene_changes_camera_occurred", "camera_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("scene_memory_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_state: Mapped[str | None] = mapped_column(String(160))
    new_state: Mapped[str] = mapped_column(String(160), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Site(Base):
    """Tenant-owned physical site used to organize cameras and operational areas."""

    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_sites_organization_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SiteArea(Base):
    """Normalized rectangle on a simple site layout."""

    __tablename__ = "site_areas"
    __table_args__ = (UniqueConstraint("site_id", "name", name="uq_site_areas_site_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[str] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    area_type: Mapped[str] = mapped_column(String(80), nullable=False, default="operational")
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CameraPlacement(Base):
    """Camera marker on a site layout, optionally assigned to one area."""

    __tablename__ = "camera_placements"
    __table_args__ = (UniqueConstraint("camera_id", name="uq_camera_placements_camera"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[str] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    area_id: Mapped[str | None] = mapped_column(
        ForeignKey("site_areas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    heading_degrees: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EntitySighting(Base):
    """One privacy-conscious sighting used to reconstruct a cross-camera journey."""

    __tablename__ = "entity_sightings"
    __table_args__ = (
        Index(
            "ix_entity_sightings_entity_occurred",
            "organization_id",
            "entity_key",
            "occurred_at",
        ),
        UniqueConstraint(
            "camera_id", "entity_key", "occurred_at", name="uq_entity_sighting_camera_time"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    camera_id: Mapped[str] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True
    )
    area_id: Mapped[str | None] = mapped_column(
        ForeignKey("site_areas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    bounding_box: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EdgeStationProfile(Base):
    """Latest hardware, software, queue, and sync health reported by an edge station."""

    __tablename__ = "edge_station_profiles"

    device_id: Mapped[str] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    os_name: Mapped[str] = mapped_column(String(120), nullable=False)
    architecture: Mapped[str] = mapped_column(String(80), nullable=False)
    cpu_count: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    accelerator: Mapped[str | None] = mapped_column(String(255))
    storage_available_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_version: Mapped[str] = mapped_column(String(80), nullable=False)
    health_status: Mapped[EdgeHealthStatus] = mapped_column(
        Enum(EdgeHealthStatus, native_enum=False, length=20), nullable=False
    )
    offline_queue_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class EdgeConfigBundle(Base):
    """Immutable signed configuration revision assigned to one edge station."""

    __tablename__ = "edge_config_bundles"
    __table_args__ = (
        UniqueConstraint("device_id", "revision", name="uq_edge_config_device_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class EdgeUpdateDeployment(Base):
    """Audited desired software update and its edge-reported result."""

    __tablename__ = "edge_update_deployments"
    __table_args__ = (Index("ix_edge_updates_device_created", "device_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        ForeignKey("edge_devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_version: Mapped[str] = mapped_column(String(80), nullable=False)
    target_version: Mapped[str] = mapped_column(String(80), nullable=False)
    rollback_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[EdgeUpdateStatus] = mapped_column(
        Enum(EdgeUpdateStatus, native_enum=False, length=20), nullable=False
    )
    error: Mapped[str | None] = mapped_column(String(1000))
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
