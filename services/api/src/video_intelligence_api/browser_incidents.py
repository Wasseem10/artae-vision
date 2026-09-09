"""Execute bounded browser incident actions in the account transaction.

Model tools request actions; these receipts describe actual persisted effects.
Evidence references point to tenant-owned recordings, never model-provided URLs.
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from video_intelligence_api.models import Event, RecordingSegment, RecordingSegmentStatus


def incident_actions(event, run):
    actions = run.tool_actions if run else []
    preservation = next((a for a in actions if a.get("tool") == "preserve_evidence"), {})
    notification = next((a for a in actions if a.get("tool") == "notify_responder"), {})
    before = max(0, min(int(preservation.get("seconds_before", 5)), 30))
    after = max(0, min(int(preservation.get("seconds_after", 10)), 60))
    return {
        "evidence": {
            "status": "awaiting_recording",
            "start_seconds": max(0, event.occurred_at_seconds - before),
            "end_seconds": event.occurred_at_seconds + after,
            "recording_ids": [],
        },
        "notification": {
            "channel": "in_app", "status": "saved",
            "message": str(notification.get("message") or event.details["summary"])[:500],
            "priority": notification.get("priority", "high" if event.event_type == "person_fall" else "low"),
        },
    }


async def reconcile_browser_evidence(session, camera, rule):
    """Link ready evidence both when an event arrives and when later uploads finish.

    Lock events so a concurrent upload cannot overwrite a human review. The
    recording retention policy still applies; this does not create a legal hold.
    """
    origin = (rule.spec or {}).get("browser_started_at")
    origin = datetime.fromisoformat(origin) if origin else camera.created_at
    events = (await session.scalars(select(Event).where(
        Event.camera_id == camera.id,
    ).with_for_update())).all()
    for event in events:
        evidence = (event.details or {}).get("evidence")
        if not evidence:
            continue
        rows = (await session.scalars(select(RecordingSegment).where(
            RecordingSegment.camera_id == camera.id,
            RecordingSegment.organization_id == camera.organization_id,
            RecordingSegment.status == RecordingSegmentStatus.READY,
            RecordingSegment.started_at < origin + timedelta(seconds=evidence["end_seconds"]),
            RecordingSegment.ended_at > origin + timedelta(seconds=evidence["start_seconds"]),
        ).order_by(RecordingSegment.started_at))).all()
        event.details = {**event.details, "evidence": {
            **evidence,
            "status": "available" if rows else "awaiting_recording",
            "recording_ids": [row.id for row in rows],
            "retention": "account_recording_policy",
        }}
