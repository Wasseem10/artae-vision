"""Policy and finalization helpers for live semantic event verification."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.alerting import enqueue_event_alert
from video_intelligence_api.correlations import enqueue_event_correlations
from video_intelligence_api.models import Camera, Event, Rule, VerificationStatus
from video_intelligence_api.scene_memory import SceneObservationData, apply_scene_observations


@dataclass(frozen=True, slots=True)
class VerificationAssessment:
    status: VerificationStatus
    proposer_model: str | None
    verifier_model: str | None
    verifier_confidence: float | None
    proposal_summary: str
    verifier_summary: str | None
    reasoning: str
    decision_source: str


def _text(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned[:maximum] if cleaned else None


def _confidence(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if 0 <= number <= 1 else None


def assess_semantic_event(rule: Rule, details: dict[str, object]) -> VerificationAssessment:
    """Accept only an explicit decision from a distinct, sufficiently confident model."""
    proposer_model = _text(details.get("proposer_model"), maximum=120)
    proposal_summary = _text(details.get("summary"), maximum=1000) or rule.name
    raw_verification = details.get("independent_verification")
    if not isinstance(raw_verification, dict):
        return VerificationAssessment(
            status=VerificationStatus.PENDING,
            proposer_model=proposer_model,
            verifier_model=None,
            verifier_confidence=None,
            proposal_summary=proposal_summary,
            verifier_summary=None,
            reasoning="No independent verifier result was supplied; operator review is required.",
            decision_source="operator_required",
        )

    verifier_model = _text(raw_verification.get("verifier_model"), maximum=120)
    verifier_confidence = _confidence(raw_verification.get("confidence"))
    verifier_summary = _text(raw_verification.get("summary"), maximum=1000)
    declared_status = _text(raw_verification.get("status"), maximum=40)
    triggered = raw_verification.get("triggered")
    models_are_independent = bool(
        proposer_model
        and verifier_model
        and proposer_model.casefold() != verifier_model.casefold()
    )
    if not models_are_independent:
        reasoning = (
            "The verifier was missing or used the proposer model; operator review is required."
        )
        status = VerificationStatus.UNCERTAIN
    elif verifier_confidence is None or verifier_confidence < rule.minimum_confidence:
        reasoning = (
            "The independent verifier did not reach the rule's minimum confidence; "
            "operator review is required."
        )
        status = VerificationStatus.UNCERTAIN
    elif declared_status == "confirmed" and triggered is True:
        reasoning = "A distinct verifier independently confirmed the visible event."
        status = VerificationStatus.CONFIRMED
    elif declared_status == "rejected" and triggered is False:
        reasoning = "A distinct verifier rejected the proposed visible event."
        status = VerificationStatus.REJECTED
    else:
        reasoning = "The independent verifier result was inconclusive; operator review is required."
        status = VerificationStatus.UNCERTAIN
    return VerificationAssessment(
        status=status,
        proposer_model=proposer_model,
        verifier_model=verifier_model,
        verifier_confidence=verifier_confidence,
        proposal_summary=proposal_summary,
        verifier_summary=verifier_summary,
        reasoning=reasoning,
        decision_source="automatic_verifier" if status in {
            VerificationStatus.CONFIRMED,
            VerificationStatus.REJECTED,
        } else "operator_required",
    )


def scene_observations(details: dict[str, object]) -> list[SceneObservationData]:
    raw = details.get("scene_observations")
    if not isinstance(raw, list) or not raw:
        return []
    return [SceneObservationData.model_validate(value) for value in raw]


async def finalize_confirmed_event(
    session: AsyncSession,
    event: Event,
    camera: Camera,
) -> None:
    """Release a confirmed event to scene memory, correlation, alerts, and actions."""
    observations = scene_observations(event.details)
    if observations:
        await apply_scene_observations(
            session,
            organization_id=camera.organization_id,
            camera_id=camera.id,
            observations=observations,
            occurred_at=event.occurred_at,
            event_id=event.id,
        )
    if not await enqueue_event_correlations(session, event):
        await enqueue_event_alert(session, event)


__all__ = [
    "VerificationAssessment",
    "assess_semantic_event",
    "finalize_confirmed_event",
    "scene_observations",
]
