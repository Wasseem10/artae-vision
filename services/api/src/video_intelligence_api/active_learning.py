"""Bounded active-evidence sampling and dataset manifest helpers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.models import (
    Camera,
    Event,
    EvidenceReviewSample,
    EvidenceSamplingPolicy,
    FieldAccuracyLabel,
    RecordingSegment,
    RecordingSegmentStatus,
    ReviewSampleKind,
    ReviewSampleStatus,
    Rule,
    VerificationCase,
    VerificationStatus,
    new_id,
    utc_now,
)

DEFAULT_INTERVAL_SECONDS = 900
DEFAULT_DAILY_LIMIT = 100
DEFAULT_SLA_HOURS = 24
DEFAULT_RETENTION_DAYS = 30


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_manifest(items: list[dict[str, object]]) -> tuple[str, str]:
    body = "\n".join(json.dumps(item, sort_keys=True, separators=(",", ":")) for item in items)
    if body:
        body += "\n"
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


async def reconcile_samples(session: AsyncSession) -> dict[str, int]:
    """Create bounded review work from proposals and routine archived footage."""
    now = utc_now()
    result = {
        "candidate_samples_created": 0,
        "normal_samples_created": 0,
        "labels_synchronized": 0,
        "expired_samples_skipped": 0,
    }
    expired = list(
        (
            await session.scalars(
                select(EvidenceReviewSample).where(
                    EvidenceReviewSample.status.in_(
                        [
                            ReviewSampleStatus.QUEUED,
                            ReviewSampleStatus.ASSIGNED,
                            ReviewSampleStatus.REVIEWING,
                            ReviewSampleStatus.DISPUTED,
                        ]
                    ),
                    EvidenceReviewSample.expires_at < now,
                )
            )
        ).all()
    )
    for sample in expired:
        sample.status = ReviewSampleStatus.SKIPPED
        sample.updated_at = now
    result["expired_samples_skipped"] = len(expired)

    sync_rows = (
        await session.execute(
            select(EvidenceReviewSample, FieldAccuracyLabel)
            .join(
                FieldAccuracyLabel,
                FieldAccuracyLabel.verification_case_id
                == EvidenceReviewSample.verification_case_id,
            )
            .where(EvidenceReviewSample.label_id.is_(None))
        )
    ).all()
    for sample, label in sync_rows:
        sample.label_id = label.id
        sample.status = ReviewSampleStatus.LABELED
        sample.consensus_status = "existing_label"
        sample.environment_tags = list(label.environment_tags)
        sample.updated_at = now
    result["labels_synchronized"] = len(sync_rows)

    policies = {
        policy.rule_id: policy
        for policy in (await session.scalars(select(EvidenceSamplingPolicy))).all()
    }
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    created_today_rows = (
        await session.execute(
            select(EvidenceReviewSample.rule_id, func.count())
            .where(EvidenceReviewSample.created_at >= day_start)
            .group_by(EvidenceReviewSample.rule_id)
        )
    ).all()
    created_today = Counter({rule_id: int(count) for rule_id, count in created_today_rows})

    case_rows = (
        await session.execute(
            select(VerificationCase, Event, Camera, Rule)
            .join(Event, Event.id == VerificationCase.event_id)
            .join(Camera, Camera.id == Event.camera_id)
            .join(Rule, Rule.id == Event.rule_id)
            .outerjoin(
                EvidenceReviewSample,
                EvidenceReviewSample.verification_case_id == VerificationCase.id,
            )
            .where(EvidenceReviewSample.id.is_(None))
            .order_by(VerificationCase.created_at.desc())
            .limit(500)
        )
    ).all()
    for case, event, camera, rule in case_rows:
        policy = policies.get(rule.id)
        if policy is not None and not policy.enabled:
            continue
        limit = policy.daily_limit if policy else DEFAULT_DAILY_LIMIT
        if created_today[rule.id] >= limit:
            continue
        tags = list(event.details.get("environment_tags") or [])
        if tags:
            kind, priority = ReviewSampleKind.CHALLENGING, 0.95
        elif case.status in {VerificationStatus.PENDING, VerificationStatus.UNCERTAIN}:
            kind, priority = ReviewSampleKind.UNCERTAIN, 1.0
        else:
            kind, priority = ReviewSampleKind.CANDIDATE, 0.75
        retention = policy.retention_days if policy else DEFAULT_RETENTION_DAYS
        existing_label = await session.scalar(
            select(FieldAccuracyLabel).where(FieldAccuracyLabel.verification_case_id == case.id)
        )
        session.add(
            EvidenceReviewSample(
                id=new_id(),
                organization_id=camera.organization_id,
                camera_id=camera.id,
                rule_id=rule.id,
                verification_case_id=case.id,
                event_id=event.id,
                recording_id=None,
                kind=kind,
                status=ReviewSampleStatus.LABELED if existing_label else ReviewSampleStatus.QUEUED,
                priority=priority,
                dedup_key=digest(f"case:{case.id}"),
                model_context={
                    "proposer_model": case.proposer_model,
                    "verifier_model": case.verifier_model,
                    "rule_spec_version": rule.spec_version,
                    "rule_spec": rule.spec or {},
                    "proposer_confidence": case.proposer_confidence,
                    "verifier_confidence": case.verifier_confidence,
                },
                environment_tags=list(existing_label.environment_tags) if existing_label else tags,
                label_id=existing_label.id if existing_label else None,
                expires_at=now + timedelta(days=retention),
                created_at=now,
                updated_at=now,
            )
        )
        created_today[rule.id] += 1
        result["candidate_samples_created"] += 1

    recording_rows = (
        await session.execute(
            select(RecordingSegment, Camera, Rule)
            .join(Camera, Camera.id == RecordingSegment.camera_id)
            .join(Rule, Rule.camera_id == Camera.id)
            .where(
                RecordingSegment.status == RecordingSegmentStatus.READY,
                Rule.rule_type == "semantic_vision",
            )
            .order_by(RecordingSegment.started_at.desc())
            .limit(1000)
        )
    ).all()
    existing_keys = set((await session.scalars(select(EvidenceReviewSample.dedup_key))).all())
    for recording, camera, rule in recording_rows:
        policy = policies.get(rule.id)
        if policy is not None and not policy.enabled:
            continue
        limit = policy.daily_limit if policy else DEFAULT_DAILY_LIMIT
        if created_today[rule.id] >= limit:
            continue
        interval = policy.normal_sample_interval_seconds if policy else DEFAULT_INTERVAL_SECONDS
        bucket = int(recording.started_at.timestamp()) // interval
        key = digest(f"normal:{rule.id}:{bucket}")
        if key in existing_keys:
            continue
        retention = policy.retention_days if policy else DEFAULT_RETENTION_DAYS
        recording_expiry = recording.expires_at
        if recording_expiry.tzinfo is None:
            recording_expiry = recording_expiry.replace(tzinfo=UTC)
        session.add(
            EvidenceReviewSample(
                id=new_id(),
                organization_id=camera.organization_id,
                camera_id=camera.id,
                rule_id=rule.id,
                recording_id=recording.id,
                kind=ReviewSampleKind.NORMAL,
                status=ReviewSampleStatus.QUEUED,
                priority=0.35,
                dedup_key=key,
                model_context={
                    "rule_spec_version": rule.spec_version,
                    "rule_spec": rule.spec or {},
                    "recording_sha256": recording.sha256,
                    "sample_interval_seconds": interval,
                },
                environment_tags=[],
                expires_at=min(recording_expiry, now + timedelta(days=retention)),
                created_at=now,
                updated_at=now,
            )
        )
        existing_keys.add(key)
        created_today[rule.id] += 1
        result["normal_samples_created"] += 1
    await session.commit()
    return result
