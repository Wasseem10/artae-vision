import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}


def semantic_camera_and_rule(client: TestClient) -> tuple[dict, dict]:
    camera = client.post(
        "/api/v1/cameras",
        json={"name": "active-learning-camera", "source_uri": "webcam:0"},
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
    return camera, rule


def create_proposal(client: TestClient, camera: dict, rule: dict) -> dict:
    response = client.post(
        "/api/v1/agent/events",
        headers=AGENT_HEADERS,
        json={
            "schema_version": 2,
            "id": str(uuid.uuid4()),
            "event_type": "semantic_vision",
            "rule_id": rule["id"],
            "camera_id": camera["id"],
            "track_id": None,
            "object_class": "visual_event",
            "zone_name": "Full frame (automatic)",
            "entered_at_seconds": 1,
            "occurred_at_seconds": 10,
            "dwell_seconds": 9,
            "confidence": 0.73,
            "occurred_at": datetime.now(UTC).isoformat(),
            "clip_path": "artifacts/events/active.mp4",
            "details": {
                "summary": "A package may have been left behind.",
                "proposer_model": "proposer-v1",
            },
        },
    )
    assert response.status_code == 201
    return response.json()


def create_recording(client: TestClient, camera: dict) -> dict:
    started = datetime.now(UTC) - timedelta(minutes=5)
    segment_id = str(uuid.uuid4())
    reported = client.post(
        f"/api/v1/agent/cameras/{camera['id']}/recordings",
        headers=AGENT_HEADERS,
        json={
            "segment_id": segment_id,
            "source_key": segment_id,
            "source_filename": "normal.mp4",
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
        f"/api/v1/agent/recordings/{reported['id']}/content",
        headers={**AGENT_HEADERS, "Content-Type": "video/mp4"},
        content=b"normal-video",
    )
    assert uploaded.status_code == 200
    return uploaded.json()


def test_reconcile_deduplicates_assigns_and_labels_normal_footage(
    api_client: TestClient,
) -> None:
    camera, rule = semantic_camera_and_rule(api_client)
    create_proposal(api_client, camera, rule)
    create_recording(api_client, camera)

    first = api_client.post(
        "/api/v1/active-learning/agent/reconcile", headers=AGENT_HEADERS
    )
    assert first.status_code == 200
    assert first.json()["candidate_samples_created"] == 1
    assert first.json()["normal_samples_created"] == 1
    second = api_client.post(
        "/api/v1/active-learning/agent/reconcile", headers=AGENT_HEADERS
    ).json()
    assert second["candidate_samples_created"] == 0
    assert second["normal_samples_created"] == 0

    queue = api_client.get("/api/v1/active-learning/queue").json()
    assert {item["kind"] for item in queue} == {"uncertain", "normal"}
    normal = next(item for item in queue if item["kind"] == "normal")
    assigned = api_client.post(
        f"/api/v1/active-learning/queue/{normal['id']}/assign", json={}
    )
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "assigned"
    assert assigned.json()["assigned_to"]
    labeled = api_client.post(
        f"/api/v1/active-learning/queue/{normal['id']}/label",
        json={
            "actual_outcome": "no_event",
            "reasoning": "Routine footage contains no matching package event.",
        },
    )
    assert labeled.status_code == 200
    assert labeled.json()["label"]["outcome"] == "true_negative"


def test_balanced_dataset_freeze_and_integrity_checked_export(
    api_client: TestClient,
) -> None:
    camera, rule = semantic_camera_and_rule(api_client)
    create_recording(api_client, camera)
    api_client.post("/api/v1/active-learning/agent/reconcile", headers=AGENT_HEADERS)
    sample = api_client.get("/api/v1/active-learning/queue").json()[0]
    api_client.post(
        f"/api/v1/active-learning/queue/{sample['id']}/label",
        json={
            "actual_outcome": "no_event",
            "reasoning": "No target behavior is visible.",
        },
    )
    created = api_client.post(
        "/api/v1/active-learning/datasets",
        json={"name": "package-baseline", "rule_id": rule["id"], "max_samples": 20},
    )
    assert created.status_code == 201
    assert created.json()["sample_count"] == 1
    assert created.json()["balance"] == {"true_negative": 1}
    dataset_id = created.json()["id"]
    assert (
        api_client.get(
            f"/api/v1/active-learning/datasets/{dataset_id}/export"
        ).status_code
        == 409
    )
    frozen = api_client.post(f"/api/v1/active-learning/datasets/{dataset_id}/freeze")
    assert frozen.status_code == 200
    assert frozen.json()["manifest_sha256"]
    exported = api_client.get(f"/api/v1/active-learning/datasets/{dataset_id}/export")
    assert exported.status_code == 200
    assert exported.headers["x-manifest-sha256"] == frozen.json()["manifest_sha256"]
    row = exported.json()
    assert row["dataset"] == {"name": "package-baseline", "version": 1}
    assert row["label"]["outcome"] == "true_negative"


def test_sampling_policy_is_tenant_scoped_and_configurable(
    api_client: TestClient,
) -> None:
    _, rule = semantic_camera_and_rule(api_client)
    updated = api_client.put(
        f"/api/v1/active-learning/rules/{rule['id']}/policy",
        json={
            "enabled": True,
            "normal_sample_interval_seconds": 300,
            "daily_limit": 25,
            "review_sla_hours": 8,
            "retention_days": 14,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["normal_sample_interval_seconds"] == 300
    assert updated.json()["review_sla_hours"] == 8
