"""Account-owned browser inference sessions; never grants an edge-device credential.

Browser observations are explicitly client-reported, not independently verified.
They create an in-app alert only. External recipients/physical actions are not
accepted in these payloads. Recording uploads reuse the tenant archive pipeline.
"""

import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Literal
from uuid import UUID

import anyio

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.auth import ActorDependency, EditorDependency
from video_intelligence_api.browser_incidents import incident_actions, reconcile_browser_evidence
from video_intelligence_api.browser_vision import decode_frame, inspect_frames
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
logger = logging.getLogger(__name__)


class SessionCreate(BaseModel):
    id: UUID
    job: Literal["presence", "fall", "custom"]
    name: str = Field(min_length=1, max_length=80)
    started_at: AwareDatetime | None = None
    agent_id: UUID | None = None
    prompt: str = Field(default="", max_length=500)
    check_interval_seconds: int = Field(default=60, ge=5, le=3600)
    confirmation_count: int = Field(default=1, ge=1, le=3)


class SavedJobCreate(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=80)
    job: Literal["presence", "fall", "custom"]
    prompt: str = Field(default="", max_length=500)


@router.get("/jobs")
async def list_saved_jobs(session: SessionDependency, actor: ActorDependency):
    rows = (await session.execute(select(Camera, Rule).join(Rule, Rule.camera_id == Camera.id).where(
        Camera.organization_id == actor.organization_id,
        Camera.source_uri.startswith("browser-job:"),
    ).order_by(Camera.created_at.desc()).limit(100))).all()
    return [{"id": c.id, "name": c.name, "job": r.key.removeprefix("browser-template-"),
             "prompt": (r.spec or {}).get("visual_prompt", "")} for c, r in rows]


@router.post("/jobs")
async def save_browser_job(payload: SavedJobCreate, session: SessionDependency, actor: EditorDependency):
    if payload.job == "custom" and not payload.prompt.strip():
        raise HTTPException(422, "Describe a visible condition to watch for")
    camera = await session.get(Camera, str(payload.id))
    if camera:
        camera = await tenant_camera(session, actor, camera.id)
        if camera is None or not camera.source_uri.startswith("browser-job:"):
            raise HTTPException(404, "Saved job not found")
        rule = await session.scalar(select(Rule).where(Rule.camera_id == camera.id))
        if not rule or rule.key != f"browser-template-{payload.job}" or camera.name != payload.name.strip() or (rule.spec or {}).get("visual_prompt", "") != payload.prompt:
            raise HTTPException(409, "Job identity already exists with another configuration")
        return {"id": camera.id, "name": camera.name, "job": payload.job, "prompt": (rule.spec or {}).get("visual_prompt", "")}
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
                     original_prompt=payload.prompt or f"Show an in-app alert for {payload.job}",
                     spec={"browser_template": True, "visual_prompt": payload.prompt}))
    await session.commit()
    return {"id": camera.id, "name": camera.name, "job": payload.job, "prompt": payload.prompt}


class BrowserObservation(BaseModel):
    id: UUID
    at_seconds: float = Field(ge=0, le=3600, allow_inf_nan=False)
    landmark_visibility: float = Field(ge=0, le=1, allow_inf_nan=False)


class IncidentReview(BaseModel):
    outcome: Literal["acknowledged", "resolved", "false_alarm"]


class VisualFrame(BaseModel):
    at_seconds: float = Field(ge=0, le=3600, allow_inf_nan=False)
    jpeg: str = Field(min_length=20, max_length=250000)


class VisualCheck(BaseModel):
    id: UUID
    frames: list[VisualFrame] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_frames(self):
        times = [frame.at_seconds for frame in self.frames]
        if times != sorted(times) or times[-1] - times[0] > 10:
            raise ValueError("Frames must be chronological and cover at most ten seconds")
        for frame in self.frames:
            decode_frame(frame.jpeg)
        return self


@router.post("/{camera_id}/analyze")
async def analyze_browser_frames(camera_id: str, payload: VisualCheck, request: Request,
                                 session: SessionDependency, actor: EditorDependency):
    camera, rule = await owned_session(camera_id, session, actor)
    settings = request.app.state.settings
    if rule.key != "browser-custom":
        raise HTTPException(422, "Choose a custom visual job for cloud frame analysis")
    if not settings.strands_enabled:
        raise HTTPException(503, "AWS visual analysis is not configured")
    rule = await session.scalar(select(Rule).where(Rule.id == rule.id).with_for_update())
    spec = dict(rule.spec or {})
    if spec.get("visual_check_id") == str(payload.id) and spec.get("visual_result"):
        return spec["visual_result"]
    now = utc_now()
    if spec.get("visual_busy_until") and datetime.fromisoformat(spec["visual_busy_until"]) > now:
        raise HTTPException(429, "A visual check is still running; wait for its result")
    if int(spec.get("visual_checks", 0)) >= 720:
        raise HTTPException(429, "This run has reached its 720 visual-check limit")
    # Reserve capacity in PostgreSQL before a paid model call. Never trust a
    # client timer as the only rate/concurrency control.
    rule.spec = {**spec, "visual_checks": int(spec.get("visual_checks", 0)) + 1,
                 "visual_busy_until": (now + timedelta(seconds=70)).isoformat()}
    await session.commit()
    try:
        with anyio.fail_after(30):
            decision, usage = await anyio.to_thread.run_sync(partial(
                inspect_frames, rule.original_prompt, payload.frames, settings,
                request.headers.get("x-vercel-oidc-token"),
            ), abandon_on_cancel=True)
    except Exception as exc:
        # Never turn an unavailable model into a positive detection or a silent
        # negative. The browser must show the failure and stop this custom job.
        logger.exception("AWS visual check failed for camera=%s", camera.id)
        raise HTTPException(503, "AWS could not analyze these frames. Detection stopped; retry shortly.") from exc
    rule = await session.scalar(select(Rule).where(Rule.id == rule.id).with_for_update().execution_options(populate_existing=True))
    spec = dict(rule.spec or {})
    at = payload.frames[-1].at_seconds
    confirmation_count = int(spec.get("confirmation_count", 1))
    match_streak = int(spec.get("visual_match_streak", 0)) + 1 if decision.status == "match" else 0
    spec["visual_match_streak"] = match_streak
    prior = spec.get("visual_last_match_seconds")
    confirmed = decision.status == "match" and match_streak >= confirmation_count
    create_alert = confirmed and (prior is None or at - float(prior) >= 30)
    result = {"status": decision.status, "summary": decision.summary, "frames_analyzed": len(payload.frames),
              "model": settings.strands_model_id, "event": None,
              "confirmed": confirmed, "match_streak": match_streak, "confirmation_count": confirmation_count,
              "cooldown": confirmed and not create_alert}
    if create_alert:
        count = await session.scalar(select(func.count()).select_from(Event).where(Event.camera_id == camera.id))
        if count >= 20:
            raise HTTPException(429, "The session reached its 20-alert limit")
        event = Event(id=new_id(), source_event_id=str(payload.id), schema_version=1, camera_id=camera.id,
                      rule_id=rule.id, event_type="visual_match", track_id=0, object_class="visual condition",
                      zone_name="Full frame", entered_at_seconds=payload.frames[0].at_seconds,
                      occurred_at_seconds=at, dwell_seconds=max(0, at-payload.frames[0].at_seconds),
                      confidence=0, clip_uri="", occurred_at=now, verification_status=VerificationStatus.UNCERTAIN,
                      raw_payload={"frame_times": [f.at_seconds for f in payload.frames]}, details={
                          "source": "bedrock_vision", "summary": decision.summary, "model": settings.strands_model_id,
                          "independently_verified": False, "requires_human": True,
                          "confidence_meaning": "No calibrated probability is reported",
                          "frame_count": len(payload.frames), "usage": usage,
                      })
        run = await coordinate_incident(event, camera, rule, settings,
                                        oidc_token=request.headers.get("x-vercel-oidc-token"))
        if run:
            event.details = {**event.details, "strands_agent": run.model_dump(mode="json")}
        event.details = {**event.details, **incident_actions(event, run), "review": {"status": "open", "outcome": None}}
        session.add(event)
        await session.flush()
        session.add(Alert(id=new_id(), event_id=event.id, created_at=now, updated_at=now))
        await reconcile_browser_evidence(session, camera, rule)
        result["event"] = EventRead.model_validate(event).model_dump(mode="json")
        spec["visual_last_match_seconds"] = at
        spec["visual_match_streak"] = 0
    rule.spec = {**spec, "visual_check_id": str(payload.id), "visual_result": result,
                 "visual_busy_until": (utc_now() + timedelta(seconds=3)).isoformat()}
    await session.commit()
    return result


async def owned_session(camera_id: str, session, actor):
    camera = await tenant_camera(session, actor, camera_id)
    if camera is None or not camera.source_uri.startswith("browser:"):
        raise HTTPException(404, "Browser session not found")
    rule = await session.scalar(select(Rule).where(Rule.camera_id == camera.id))
    if rule is None or rule.key not in {"browser-presence", "browser-fall", "browser-custom"}:
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
        "prompt": (rule.spec or {}).get("visual_prompt", ""),
        "check_interval_seconds": (rule.spec or {}).get("check_interval_seconds", 60),
        "confirmation_count": (rule.spec or {}).get("confirmation_count", 1),
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
    if payload.job == "custom" and not payload.prompt.strip():
        raise HTTPException(422, "Describe a visible condition to watch for")
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
        if payload.job == "custom" and (template_rule.spec or {}).get("visual_prompt") != payload.prompt:
            raise HTTPException(409, "Run does not match the saved agent's visual condition")
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
    title = "Custom visual condition" if payload.job == "custom" else "Possible fall" if payload.job == "fall" else "Person in view"
    rule = Rule(
        id=new_id(),
        camera_id=camera.id,
        zone_id=zone.id,
        key=f"browser-{payload.job}",
        name=title,
        duration_seconds=1,
        minimum_confidence=0.6,
        status=RuleStatus.PAUSED,
        original_prompt=payload.prompt if payload.job == "custom" else f"Show an in-app alert: {title} (browser pose analysis).",
        spec={"browser_started_at": payload.started_at.isoformat() if payload.started_at else None,
              "browser_agent_id": str(payload.agent_id) if payload.agent_id else None,
              "visual_prompt": payload.prompt,
              "check_interval_seconds": payload.check_interval_seconds,
              "confirmation_count": payload.confirmation_count,
              "visual_match_streak": 0},
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


@router.get("/{camera_id}/events", response_model=list[EventRead])
async def session_observations(
    camera_id: str,
    session: SessionDependency,
    actor: ActorDependency,
):
    camera, _ = await owned_session(camera_id, session, actor)
    # Account replay must include uncertain candidates and closed false alarms.
    # The general event feed deliberately filters unverified observations out.
    return list((await session.scalars(
        select(Event).where(Event.camera_id == camera.id).order_by(Event.occurred_at).limit(100)
    )).all())


@router.post("/{camera_id}/events", response_model=EventRead)
async def record_observation(
    camera_id: str,
    payload: BrowserObservation,
    request: Request,
    session: SessionDependency,
    actor: EditorDependency,
):
    camera, rule = await owned_session(camera_id, session, actor)
    if rule.key == "browser-custom":
        raise HTTPException(422, "Custom jobs require server-side image analysis, not client observations")
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
