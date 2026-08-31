import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from video_intelligence_api.auth import Actor, get_current_actor
from video_intelligence_api.models import OrganizationRole, ReplaySuiteRunStatus
from video_intelligence_api.routes.promotions import _comparison

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}
ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def camera_rule_recording(client: TestClient, suffix: str) -> tuple[dict, dict]:
    camera = client.post(
        "/api/v1/cameras",
        json={"name": f"promotion-{suffix}", "source_uri": "webcam:0"},
    ).json()
    compilation = client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": "Alert me when a person is not wearing a hard hat.",
        },
    ).json()
    rule = client.post(
        f"/api/v1/rule-compilations/{compilation['id']}/accept", json={}
    ).json()
    client.patch(f"/api/v1/rules/{rule['id']}/status", json={"status": "active"})
    started = datetime.now(UTC) - timedelta(minutes=5)
    segment_id = str(uuid.uuid4())
    segment = client.post(
        f"/api/v1/agent/cameras/{camera['id']}/recordings",
        headers=AGENT_HEADERS,
        json={
            "segment_id": segment_id,
            "source_key": segment_id,
            "source_filename": f"{suffix}.mp4",
            "started_at": started.isoformat(),
            "ended_at": (started + timedelta(minutes=5)).isoformat(),
            "duration_seconds": 300,
            "frame_count": 9000,
            "fps": 30,
            "width": 1920,
            "height": 1080,
        },
    ).json()
    uploaded = client.put(
        f"/api/v1/agent/recordings/{segment['id']}/content",
        headers={**AGENT_HEADERS, "Content-Type": "video/mp4"},
        content=b"field-replay-video",
    )
    assert uploaded.status_code == 200
    client.post("/api/v1/active-learning/agent/reconcile", headers=AGENT_HEADERS)
    return camera, rule


def labeled_dataset(client: TestClient, suffix: str) -> tuple[dict, dict, dict]:
    camera, rule = camera_rule_recording(client, suffix)
    sample = next(
        item
        for item in client.get("/api/v1/active-learning/queue").json()
        if item["camera_id"] == camera["id"] and item["recording_id"]
    )
    labeled = client.post(
        f"/api/v1/active-learning/queue/{sample['id']}/label",
        json={
            "actual_outcome": "no_event",
            "reasoning": "No matching event is visible.",
        },
    )
    assert labeled.status_code == 200
    dataset = client.post(
        "/api/v1/active-learning/datasets",
        json={"name": f"dataset-{suffix}", "rule_id": rule["id"], "max_samples": 20},
    ).json()
    dataset = client.post(
        f"/api/v1/active-learning/datasets/{dataset['id']}/freeze"
    ).json()
    return camera, rule, dataset


def passed_suite_run(
    client: TestClient, suite_id: str, evaluation_ids: list[str]
) -> dict:
    run = client.post(f"/api/v1/evaluation-suites/{suite_id}/runs")
    assert run.status_code == 200
    for evaluation_id in evaluation_ids:
        scored = client.post(
            f"/api/v1/evaluations/{evaluation_id}/score",
            json={"predicted_intervals": [], "provider_requests": 0},
        )
        assert scored.status_code == 200
    runs = client.get(f"/api/v1/evaluation-suites/{suite_id}/runs").json()
    completed = next(item for item in runs if item["id"] == run.json()["id"])
    assert completed["status"] == "passed"
    return completed


def actor(subject: str) -> Actor:
    return Actor(
        subject=subject,
        organization_id=ORGANIZATION_ID,
        role=OrganizationRole.OWNER,
        issuer="test",
    )


def test_comparison_rejects_accuracy_regression_even_when_candidate_run_passed() -> (
    None
):
    baseline = SimpleNamespace(
        status=ReplaySuiteRunStatus.PASSED,
        metrics={"macro_f1": 0.95, "macro_recall": 0.94, "false_positives": 0},
    )
    candidate = SimpleNamespace(
        status=ReplaySuiteRunStatus.PASSED,
        metrics={"macro_f1": 0.82, "macro_recall": 0.81, "false_positives": 0},
    )
    comparison = _comparison(candidate, baseline)
    assert comparison["promotion_gate_passed"] is False
    assert comparison["recommendation"] == "reject_regression"


def test_high_risk_review_requires_consensus_then_independent_adjudication(
    api_client: TestClient,
) -> None:
    camera, rule = camera_rule_recording(api_client, "consensus")
    policy = api_client.put(
        f"/api/v1/active-learning/rules/{rule['id']}/policy",
        json={
            "enabled": True,
            "normal_sample_interval_seconds": 900,
            "daily_limit": 100,
            "review_sla_hours": 24,
            "retention_days": 30,
            "required_reviews": 2,
            "require_adjudication": True,
        },
    )
    assert policy.status_code == 200
    sample = next(
        item
        for item in api_client.get("/api/v1/active-learning/queue").json()
        if item["camera_id"] == camera["id"] and item["recording_id"]
    )

    api_client.app.dependency_overrides[get_current_actor] = lambda: actor(
        "reviewer-one"
    )
    first = api_client.post(
        f"/api/v1/active-learning/queue/{sample['id']}/label",
        json={"actual_outcome": "no_event", "reasoning": "No event is visible."},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "reviewing"
    assert first.json()["review_count"] == 1

    api_client.app.dependency_overrides[get_current_actor] = lambda: actor(
        "reviewer-two"
    )
    second = api_client.post(
        f"/api/v1/active-learning/queue/{sample['id']}/label",
        json={"actual_outcome": "event", "reasoning": "A target event is visible."},
    )
    assert second.status_code == 200
    assert second.json()["status"] == "disputed"

    voter_cannot_adjudicate = api_client.post(
        f"/api/v1/active-learning/queue/{sample['id']}/adjudicate",
        json={"actual_outcome": "no_event", "reasoning": "Final evidence assessment."},
    )
    assert voter_cannot_adjudicate.status_code == 409
    api_client.app.dependency_overrides[get_current_actor] = lambda: actor(
        "adjudicator"
    )
    final = api_client.post(
        f"/api/v1/active-learning/queue/{sample['id']}/adjudicate",
        json={"actual_outcome": "no_event", "reasoning": "Final evidence assessment."},
    )
    assert final.status_code == 200
    assert final.json()["status"] == "labeled"
    assert final.json()["consensus_status"] == "adjudicated"
    api_client.app.dependency_overrides.pop(get_current_actor, None)


def test_frozen_dataset_builds_replays_and_controls_promotion_rollback(
    api_client: TestClient,
) -> None:
    _, rule, dataset = labeled_dataset(api_client, "promotion")
    build = api_client.post(f"/api/v1/promotions/datasets/{dataset['id']}/replay-suite")
    assert build.status_code == 201
    assert len(build.json()["evaluation_ids"]) == 1
    duplicate = api_client.post(
        f"/api/v1/promotions/datasets/{dataset['id']}/replay-suite"
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == build.json()["id"]

    baseline_run = passed_suite_run(
        api_client, build.json()["suite_id"], build.json()["evaluation_ids"]
    )
    baseline_plan = api_client.post(
        "/api/v1/agent-plans", json={"rule_id": rule["id"]}
    ).json()
    api_client.post(f"/api/v1/agent-plans/{baseline_plan['id']}/simulate")
    approved = api_client.post(
        f"/api/v1/agent-plans/{baseline_plan['id']}/approve",
        json={"regression_run_id": baseline_run["id"]},
    )
    assert approved.status_code == 200

    candidate_plan = api_client.post(
        "/api/v1/agent-plans", json={"rule_id": rule["id"]}
    ).json()
    api_client.post(f"/api/v1/agent-plans/{candidate_plan['id']}/simulate")
    candidate_run = passed_suite_run(
        api_client, build.json()["suite_id"], build.json()["evaluation_ids"]
    )
    promotion = api_client.post(
        "/api/v1/promotions",
        json={
            "dataset_id": dataset["id"],
            "candidate_plan_id": candidate_plan["id"],
            "candidate_run_id": candidate_run["id"],
            "baseline_run_id": baseline_run["id"],
        },
    )
    assert promotion.status_code == 201
    assert promotion.json()["comparison"]["promotion_gate_passed"] is True
    promoted = api_client.post(
        f"/api/v1/promotions/{promotion.json()['id']}/approve",
        json={
            "reasoning": "Candidate passed the frozen field dataset without regression."
        },
    )
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "approved"
    rolled_back = api_client.post(
        f"/api/v1/promotions/{promotion.json()['id']}/rollback",
        json={
            "reasoning": "Restore the previous known-good plan after deployment review."
        },
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"
    plans = api_client.get("/api/v1/agent-plans").json()
    restored = next(item for item in plans if item["id"] == baseline_plan["id"])
    assert restored["status"] == "approved"
