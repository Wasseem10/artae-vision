"""Account-owned browser inference sessions; never grants an edge-device credential.

Browser observations are explicitly client-reported, not independently verified.
They create an in-app alert only. External recipients/physical actions are not
accepted in these payloads. Recording uploads reuse the tenant archive pipeline.
"""

from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.browser_incidents import incident_actions, reconcile_browser_evidence
from video_intelligence_api.dependencies import SessionDependency, SettingsDependency
from video_intelligence_api.models import (
    Alert,
    AlertStatus,
    Camera,
    Event,
    Rule,
    RuleStatus,
    SourceType,
    VerificationStatus,
    Zone,
    new_id,
    utc_now,
)
from video_intelligence_api.routes.recordings import (
    report_recording_segment,
    upload_recording_content,
)
from video_intelligence_api.schemas import EventRead, RecordingSegmentReport
from video_intelligence_api.security import EdgePrincipal
from video_intelligence_api.strands_orchestrator import coordinate_incident
from video_intelligence_api.tenancy import tenant_camera

router = APIRouter(prefix="/browser-sessions", tags=["browser monitoring"])


class SessionCreate(BaseModel):
    id: UUID
    job: Literal["presence", "fall"]
    name: str = Field(min_length=1, max_length=80)
    started_at: AwareDatetime | None = None
    agent_id: UUID | None = None


class SavedJobCreate(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=80)
    job: Literal["presence", "fall"]


@router.get("/jobs")
async def list_saved_jobs(session: SessionDependency, actor: ActorDependency):
    rows = (await session.execute(select(Camera, Rule).join(Rule, Rule.camera_id == Camera.id).where(
        Camera.organization_id == actor.organization_id,
        Camera.source_uri.startswith("browser-job:"),
    ).order_by(Camera.created_at.desc()).limit(100))).all()
    return [{"id": c.id, "name": c.name, "job": r.key.removeprefix("browser-template-")} for c, r in rows]


@router.post("/jobs")
async def save_browser_job(payload: SavedJobCreate, session: SessionDependency, actor: EditorDependency):
    camera = await session.get(Camera, str(payload.id))
    if camera:
        camera = await tenant_camera(session, actor, camera.id)
        if camera is None or not camera.source_uri.startswith("browser-job:"):
            raise HTTPException(404, "Saved job not found")
        rule = await session.scalar(select(Rule).where(Rule.camera_id == camera.id))
        if not rule or rule.key != f"browser-template-{payload.job}" or camera.name != payload.name.strip():
            raise HTTPException(409, "Job identity already exists with another configuration")
        return {"id": camera.id, "name": camera.name, "job": payload.job}
    count = await session.scalar(select(func.count()).select_from(Camera).where(
        Camera.organization_id == actor.organization_id, Camera.source_uri.startswith("browser-job:"),
    ))
    if count >= 100:
        raise HTTPException(429, "Your workspace has reached its 100 saved-job limit")
    if not payload.name.strip():
        raise HTTPException(422, "Give your agent a name")
    camera = Camera(id=str(payload.id), organization_id=actor.organization_id, name=payload.name.strip(),
                    source_type=SourceType.WEBCAM, source_uri=f"browser-job:{payload.id}")
    session.add(camera)
    await session.flush()
    zone = Zone(id=new_id(), camera_id=camera.id, name="Full frame", points=[
        {"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1},
    ])
    session.add(zone)
    await session.flush()
    session.add(Rule(id=new_id(), camera_id=camera.id, zone_id=zone.id,
                     key=f"browser-template-{payload.job}", name=camera.name, duration_seconds=1,
                     minimum_confidence=.6, status=RuleStatus.PAUSED,
                     original_prompt=f"Show an in-app alert for {payload.job}", spec={"browser_template": True}))
    await session.commit()
    return {"id": camera.id, "name": camera.name, "job": payload.job}


class BrowserObservation(BaseModel):
    id: UUID
    at_seconds: float = Field(ge=0, le=3600, allow_inf_nan=False)
    landmark_visibility: float = Field(ge=0, le=1, allow_inf_nan=False)


class IncidentReview(BaseModel):
    outcome: Literal["acknowledged", "resolved", "false_alarm"]


async def owned_session(camera_id: str, session, actor):
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None or not camera.source_uri.startswith("browser:"):
        raise HTTPException(404, "Browser session not found")
    rule = await session.scalar(select(Rule).where(Rule.camera_id == camera.id))
    if rule is None or rule.key not in {"browser-presence", "browser-fall"}:
        raise HTTPException(404, "Browser job not found")
    return camera, rule


def session_read(camera, rule):
    return {
        "id": camera.id,
        "name": camera.name,
        "job": rule.key.removeprefix("browser-"),
        "created_at": (rule.spec or {}).get("browser_started_at") or camera.created_at,
        "rule_id": rule.id,
        "agent_id": (rule.spec or {}).get("browser_agent_id"),
    }


@router.get("")
async def list_sessions(session: SessionDependency, actor: ActorDependency):
    rows = (
        await session.execute(
            select(Camera, Rule)
            .join(Rule, Rule.camera_id == Camera.id)
            .where(
                Camera.organization_id == actor.organization_id,
                Camera.source_uri.startswith("browser:"),
            )
            .order_by(Camera.created_at.desc())
            .limit(50)
        )
    ).all()
    return [session_read(camera, rule) for camera, rule in rows]


@router.post("")
async def create_session(
    payload: SessionCreate, session: SessionDependency, actor: EditorDependency
):
    existing = await session.get(Camera, str(payload.id))
    if existing:
        camera, rule = await owned_session(str(payload.id), session, actor)
        if rule.key != f"browser-{payload.job}":
            raise HTTPException(409, "Session already uses another job")
        return session_read(camera, rule)
    if payload.agent_id:
        template = await tenant_camera(session, actor, str(payload.agent_id))
        template_rule = await session.scalar(select(Rule).where(Rule.camera_id == str(payload.agent_id)))
        if not template or not template.source_uri.startswith("browser-job:") or not template_rule:
            raise HTTPException(404, "Saved agent not found")
        if template_rule.key != f"browser-template-{payload.job}":
            raise HTTPException(409, "Run does not match the saved agent's job")
    count = await session.scalar(
        select(func.count())
        .select_from(Camera)
        .where(
            Camera.organization_id == actor.organization_id,
            Camera.source_uri.startswith("browser:"),
            Camera.created_at >= utc_now() - timedelta(days=1),
        )
    )
    if count >= 50:
        raise HTTPException(429, "Daily browser session limit reached (50)")
    camera = Camera(
        id=str(payload.id),
        organization_id=actor.organization_id,
        name=f"{payload.name} · {str(payload.id)[:8]}",
        source_type=SourceType.WEBCAM,
        source_uri=f"browser:{payload.id}",
    )
    zone = Zone(
        id=new_id(),
        camera_id=camera.id,
        name="Full frame",
        points=[
            {"x": 0, "y": 0},
            {"x": 1, "y": 0},
            {"x": 1, "y": 1},
            {"x": 0, "y": 1},
        ],
    )
    title = "Possible fall" if payload.job == "fall" else "Person in view"
    rule = Rule(
        id=new_id(),
        camera_id=camera.id,
        zone_id=zone.id,
        key=f"browser-{payload.job}",
        name=title,
        duration_seconds=1,
        minimum_confidence=0.6,
        status=RuleStatus.PAUSED,
        original_prompt=f"Show an in-app alert: {title} (browser pose analysis).",
        spec={"browser_started_at": payload.started_at.isoformat() if payload.started_at else None,
              "browser_agent_id": str(payload.agent_id) if payload.agent_id else None},
    )
    # These models use FK IDs, not ORM relationships. Flush parents explicitly;
    # SQLite without FK enforcement previously hid the PostgreSQL ordering bug.
    session.add(camera)
    await session.flush()
    session.add(zone)
    await session.flush()
    session.add(rule)
    await session.commit()
    await session.refresh(camera)
    return session_read(camera, rule)


@router.post("/{camera_id}/events", response_model=EventRead)
async def record_observation(
    camera_id: str,
    payload: BrowserObservation,
    request: Request,
    session: SessionDependency,
    actor: EditorDependency,
):
    camera, rule = await owned_session(camera_id, session, actor)
    existing = await session.scalar(select(Event).where(Event.source_event_id == str(payload.id)))
    if existing:
        if existing.camera_id != camera.id:
            raise HTTPException(409, "Event identity conflicts")
        return existing
    count = await session.scalar(
        select(func.count()).select_from(Event).where(Event.camera_id == camera.id)
    )
    if count >= 20:
        raise HTTPException(429, "This session has reached its 20-event limit")
    fall = rule.key == "browser-fall"
    summary = (
        "Possible fall: upright posture, downward movement and sustained horizontal posture. "
        "A person must review this observation."
        if fall
        else "A person was visible for at least one second."
    )
    now = utc_now()
    event = Event(
        id=new_id(),
        source_event_id=str(payload.id),
        schema_version=1,
        camera_id=camera.id,
        rule_id=rule.id,
        event_type="person_fall" if fall else "object_dwell",
        track_id=1,
        object_class="person",
        zone_name="Full frame",
        entered_at_seconds=max(0, payload.at_seconds - 1),
        occurred_at_seconds=payload.at_seconds,
        dwell_seconds=1,
        confidence=payload.landmark_visibility,
        clip_uri="",
        occurred_at=now,
        verification_status=VerificationStatus.NOT_REQUIRED,
        raw_payload=payload.model_dump(mode="json"),
        details={
            "summary": summary,
            "source": "browser_pose",
            "independently_verified": False,
            "confidence_meaning": "Landmark visibility, not probability of a fall",
            "model": "MediaPipe Pose Landmarker Lite",
            "job": rule.key,
        },
    )
    run = await coordinate_incident(
        event, camera, rule, request.app.state.settings,
        oidc_token=request.headers.get("x-vercel-oidc-token"),
    )
    if run:
        event.details = {**event.details, "strands_agent": run.model_dump(mode="json")}
    event.details = {
        **event.details,
        "review": {"status": "open", "outcome": None},
        # All browser fall candidates require a person, regardless of the model's opinion.
        "requires_human": fall or bool(run and run.requires_human),
        **incident_actions(event, run),
    }
    try:
        session.add(event)
        await session.flush()
        # In-app only; never execute client-supplied destinations.
        session.add(Alert(id=new_id(), event_id=event.id, created_at=now, updated_at=now))
        await reconcile_browser_evidence(session, camera, rule)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        duplicate = await session.scalar(
            select(Event).where(
                Event.source_event_id == str(payload.id), Event.camera_id == camera_id
            )
        )
        if duplicate is None:
            raise
        return duplicate
    await session.refresh(event)
    return event


@router.patch("/{camera_id}/events/{source_event_id}/review", response_model=EventRead)
async def review_browser_incident(
    camera_id: str,
    source_event_id: UUID,
    payload: IncidentReview,
    session: SessionDependency,
    actor: EditorDependency,
):
    """Persist a human decision; never mark the detector/model as independently verified."""
    await owned_session(camera_id, session, actor)
    event = await session.scalar(
        select(Event).where(
            Event.camera_id == camera_id, Event.source_event_id == str(source_event_id)
        ).with_for_update()
    )
    if event is None:
        raise HTTPException(404, "Incident not found")
    alert = await session.scalar(select(Alert).where(Alert.event_id == event.id))
    if alert is None:
        raise HTTPException(409, "Incident alert is not ready")
    previous = (event.details or {}).get("review", {})
    if previous.get("outcome") == payload.outcome:
        return event
    if alert.status == AlertStatus.RESOLVED:
        raise HTTPException(409, "This incident has already been closed")
    now = utc_now()
    alert.acknowledged_at = alert.acknowledged_at or now
    alert.acknowledged_by = alert.acknowledged_by or actor.subject
    alert.status = (
        AlertStatus.ACKNOWLEDGED if payload.outcome == "acknowledged" else AlertStatus.RESOLVED
    )
    if alert.status == AlertStatus.RESOLVED:
        alert.resolved_at, alert.resolved_by = now, actor.subject
    alert.updated_at = now
    review = {
        "status": alert.status.value,
        "outcome": payload.outcome,
        "reviewed_at": now.isoformat(),
        "reviewed_by": actor.subject,
    }
    event.details = {
        **(event.details or {}),
        "review": review,
        "review_history": [*(event.details or {}).get("review_history", []), review],
    }
    await session.commit()
    await session.refresh(event)
    return event


@router.post("/{camera_id}/recordings")
async def report_browser_recording(
    camera_id: str,
    payload: RecordingSegmentReport,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
):
    await owned_session(camera_id, session, actor)
    if payload.duration_seconds > 15 or payload.width > 1920 or payload.height > 1920:
        raise HTTPException(422, "Browser recordings must be short segments (15 seconds maximum)")
    return await report_recording_segment(
        camera_id, payload, session, settings, EdgePrincipal(None, actor.organization_id)
    )


@router.put("/{camera_id}/recordings/{recording_id}/content")
async def upload_browser_recording(
    camera_id: str,
    recording_id: str,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    actor: EditorDependency,
):
    from video_intelligence_api.models import RecordingSegment

    camera, rule = await owned_session(camera_id, session, actor)
    segment = await session.get(RecordingSegment, recording_id)
    if segment is None or segment.camera_id != camera_id:
        raise HTTPException(404, "Recording not found")
    result = await upload_recording_content(
        recording_id, request, session, settings, EdgePrincipal(None, actor.organization_id)
    )
    await reconcile_browser_evidence(session, camera, rule)
    await session.commit()
    return result
