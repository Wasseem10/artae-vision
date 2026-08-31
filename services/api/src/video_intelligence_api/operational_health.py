"""Deterministic camera and edge-station reliability conditions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from video_intelligence_api.config import ApiSettings
from video_intelligence_api.models import (
    AgentDesiredStatus,
    AgentObservedStatus,
    Camera,
    CameraAgent,
    EdgeDevice,
    EdgeDeviceStatus,
    OperationalHealthResource,
    OperationalHealthSeverity,
)


@dataclass(frozen=True, slots=True)
class HealthCondition:
    active_key: str
    organization_id: str
    resource_type: OperationalHealthResource
    camera_id: str | None
    edge_device_id: str | None
    condition: str
    severity: OperationalHealthSeverity
    title: str
    detail: str
    diagnostics: dict[str, Any]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _age(now: datetime, value: datetime | None) -> float | None:
    return max(0.0, (now - _aware(value)).total_seconds()) if value else None


def camera_conditions(
    camera: Camera,
    agent: CameraAgent | None,
    settings: ApiSettings,
    now: datetime,
) -> list[HealthCondition]:
    if agent is None or agent.desired_status != AgentDesiredStatus.RUNNING:
        return []
    runtime: HealthCondition | None = None
    heartbeat_age = _age(now, agent.last_heartbeat_at)
    frame_age = _age(now, agent.last_frame_at)
    request_age = _age(now, agent.updated_at) or 0
    diagnostics = {
        "observed_status": agent.observed_status.value,
        "heartbeat_age_seconds": heartbeat_age,
        "last_frame_age_seconds": frame_age,
        "failure_count": agent.failure_count,
        "reconnect_count": agent.reconnect_count,
    }
    base = {
        "active_key": f"camera:{camera.id}:runtime",
        "organization_id": camera.organization_id,
        "resource_type": OperationalHealthResource.CAMERA,
        "camera_id": camera.id,
        "edge_device_id": None,
        "diagnostics": diagnostics,
    }
    if agent.observed_status == AgentObservedStatus.ERROR:
        runtime = HealthCondition(
            **base,
            condition="camera_runtime_error",
            severity=OperationalHealthSeverity.CRITICAL,
            title=f"{camera.name} analysis failed",
            detail=agent.last_error or "The camera worker reported a runtime error.",
        )
    elif (
        heartbeat_age is not None
        and heartbeat_age > settings.operational_health_camera_stale_seconds
    ):
        runtime = HealthCondition(
            **base,
            condition="camera_heartbeat_stale",
            severity=OperationalHealthSeverity.CRITICAL,
            title=f"{camera.name} stopped checking in",
            detail=(
                f"No worker heartbeat for {round(heartbeat_age)} seconds. "
                "The requested monitoring job may not be running."
            ),
        )
    elif (
        agent.last_heartbeat_at is None
        and request_age > settings.operational_health_camera_grace_seconds
    ):
        runtime = HealthCondition(
            **base,
            condition="camera_never_started",
            severity=OperationalHealthSeverity.CRITICAL,
            title=f"{camera.name} did not start",
            detail="Monitoring was requested, but no edge worker has checked in.",
        )
    elif (
        agent.observed_status == AgentObservedStatus.RUNNING
        and frame_age is not None
        and frame_age > settings.operational_health_frame_stale_seconds
    ):
        runtime = HealthCondition(
            **base,
            condition="camera_video_stalled",
            severity=OperationalHealthSeverity.CRITICAL,
            title=f"{camera.name} video stalled",
            detail=(
                f"The worker is alive, but no video frame arrived for {round(frame_age)} seconds."
            ),
        )
    elif (
        agent.observed_status == AgentObservedStatus.RUNNING
        and agent.last_frame_at is None
        and request_age > settings.operational_health_camera_grace_seconds
    ):
        runtime = HealthCondition(
            **base,
            condition="camera_no_video",
            severity=OperationalHealthSeverity.CRITICAL,
            title=f"{camera.name} has no video",
            detail="The worker is running, but the camera has not delivered a frame.",
        )

    conditions = [runtime] if runtime else []
    if agent.recording_state == "error":
        conditions.append(
            HealthCondition(
                active_key=f"camera:{camera.id}:recording",
                organization_id=camera.organization_id,
                resource_type=OperationalHealthResource.CAMERA,
                camera_id=camera.id,
                edge_device_id=None,
                condition="camera_recording_error",
                severity=OperationalHealthSeverity.WARNING,
                title=f"{camera.name} recording failed",
                detail=agent.recording_error or "Continuous recording reported an error.",
                diagnostics={
                    "recording_state": agent.recording_state,
                    "segments_completed": agent.recording_segments_completed,
                    "dropped_frames": agent.recording_dropped_frames,
                },
            )
        )
    return conditions


def edge_condition(
    device: EdgeDevice,
    settings: ApiSettings,
    now: datetime,
) -> HealthCondition | None:
    if device.status != EdgeDeviceStatus.ACTIVE:
        return None
    last_seen_age = _age(now, device.last_seen_at)
    created_age = _age(now, device.created_at) or 0
    if last_seen_age is None and created_age <= settings.operational_health_camera_grace_seconds:
        return None
    if (
        last_seen_age is not None
        and last_seen_age <= settings.operational_health_edge_stale_seconds
    ):
        return None
    never_connected = device.last_seen_at is None
    return HealthCondition(
        active_key=f"edge:{device.id}:connectivity",
        organization_id=device.organization_id,
        resource_type=OperationalHealthResource.EDGE_DEVICE,
        camera_id=None,
        edge_device_id=device.id,
        condition="edge_never_connected" if never_connected else "edge_offline",
        severity=OperationalHealthSeverity.CRITICAL,
        title=f"{device.name} is offline",
        detail=(
            "The enrolled edge station has never connected."
            if never_connected
            else f"The edge station has not checked in for {round(last_seen_age or 0)} seconds."
        ),
        diagnostics={
            "last_seen_age_seconds": last_seen_age,
            "last_worker_id": device.last_worker_id,
        },
    )
