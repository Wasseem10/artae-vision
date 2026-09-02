import uuid

from fastapi.testclient import TestClient

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}


def semantic_camera_and_rule(client: TestClient, suffix: str) -> tuple[dict, dict]:
    camera = client.post(
        "/api/v1/cameras",
        json={"name": f"verification-{suffix}", "source_uri": "webcam:0"},
    ).json()
    compilation = client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": "Alert me when a person is not wearing a hard hat.",
        },
    ).json()
    rule = client.post(
        f"/api/v1/rule-compilations/{compilation['id']}/accept",
        json={},
    ).json()
    client.patch(f"/api/v1/rules/{rule['id']}/status", json={"status": "active"})
    return camera, rule


def semantic_event(
    camera: dict,
    rule: dict,
    *,
    independent_verification: dict | None = None,
) -> dict:
    details: dict[str, object] = {
        "summary": "A worker appears to be missing a hard hat.",
        "proposer_model": "gemini-proposer",
    }
    if independent_verification is not None:
        details["independent_verification"] = independent_verification
    return {
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
        "confidence": 0.91,
        "occurred_at": "2026-08-23T12:00:00Z",
        "clip_path": "artifacts/events/proposal.mp4",
        "details": details,
    }


def test_pending_semantic_event_is_quarantined_until_operator_confirms(
    api_client: TestClient,
) -> None:
    camera, rule = semantic_camera_and_rule(api_client, "manual")
    payload = semantic_event(camera, rule)
    created = api_client.post(
        "/api/v1/agent/events",
        headers=AGENT_HEADERS,
        json=payload,
    )
    assert created.status_code == 201
    assert created.json()["verification_status"] == "pending"
    assert api_client.get("/api/v1/events").json() == []
    assert api_client.get("/api/v1/alerts").json() == []

    clip = api_client.put(
        f"/api/v1/agent/events/{payload['id']}/clip",
        content=b"reviewable-video",
        headers={**AGENT_HEADERS, "Content-Type": "video/mp4"},
    )
    assert clip.status_code == 200
    case = api_client.get("/api/v1/verification-cases?status=pending").json()[0]
    assert case["evidence_content_url"]
    assert api_client.get(case["evidence_content_url"]).content == b"reviewable-video"

    decision = api_client.post(
        f"/api/v1/verification-cases/{case['id']}/decision",
        json={
            "status": "confirmed",
            "reasoning": "The worker's uncovered head is directly visible in the clip.",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "confirmed"
    assert decision.json()["decision_source"] == "operator"
    assert decision.json()["event"]["verification_status"] == "confirmed"
    assert len(api_client.get("/api/v1/events").json()) == 1
    assert len(api_client.get("/api/v1/alerts").json()) == 1
    duplicate = api_client.post(
        f"/api/v1/verification-cases/{case['id']}/decision",
        json={"status": "confirmed", "reasoning": "Confirmed again."},
    )
    assert duplicate.status_code == 200
    assert len(api_client.get("/api/v1/alerts").json()) == 1
    too_late = api_client.post(
        f"/api/v1/verification-cases/{case['id']}/decision",
        json={"status": "rejected", "reasoning": "Attempted late reversal."},
    )
    assert too_late.status_code == 409


def test_specialized_pose_fall_event_is_released_to_alerts_without_vlm_review(
    api_client: TestClient,
) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "fall-camera", "source_uri": "webcam:0"},
    ).json()
    compilation = api_client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": "Alert me if a person falls to the ground.",
        },
    ).json()
    assert compilation["execution_plan"]["strategy"] == "specialized_pose"
    rule = api_client.post(
        f"/api/v1/rule-compilations/{compilation['id']}/accept",
        json={},
    ).json()
    api_client.patch(f"/api/v1/rules/{rule['id']}/status", json={"status": "active"})

    event = api_client.post(
        "/api/v1/agent/events",
        headers=AGENT_HEADERS,
        json={
            "schema_version": 2,
            "id": str(uuid.uuid4()),
            "event_type": "person_fall",
            "rule_id": rule["id"],
            "camera_id": camera["id"],
            "track_id": 9,
            "object_class": "person",
            "zone_name": "Full frame (automatic)",
            "entered_at_seconds": 1,
            "occurred_at_seconds": 2,
            "dwell_seconds": 1,
            "confidence": 0.9,
            "occurred_at": "2026-08-23T12:00:00Z",
            "clip_path": "artifacts/events/fall.mp4",
            "details": {
                "visual_skill": "pose_action",
                "decision_source": "local_pose_state_machine",
                "summary": "A tracked person rapidly descended and remained down.",
            },
        },
    )

    assert event.status_code == 201, event.text
    assert event.json()["verification_status"] == "not_required"
    assert event.json()["event_type"] == "person_fall"
    assert len(api_client.get("/api/v1/alerts").json()) == 1


def test_distinct_verifier_stays_manual_until_field_gate_passes(
    api_client: TestClient,
) -> None:
    camera, rule = semantic_camera_and_rule(api_client, "automatic-confirm")
    payload = semantic_event(
        camera,
        rule,
        independent_verification={
            "status": "confirmed",
            "triggered": True,
            "confidence": 0.94,
            "summary": "The worker's head is visibly uncovered.",
            "verifier_model": "gemini-verifier",
        },
    )
    event = api_client.post(
        "/api/v1/agent/events", headers=AGENT_HEADERS, json=payload
    ).json()
    assert event["verification_status"] == "pending"
    case = api_client.get("/api/v1/verification-cases?status=pending").json()[0]
    assert case["decision_source"] == "field_gate_required"
    assert case["verifier_model"] == "gemini-verifier"
    assert api_client.get("/api/v1/alerts").json() == []


def test_rejection_and_non_independent_verifier_never_release_alerts(
    api_client: TestClient,
) -> None:
    camera, rule = semantic_camera_and_rule(api_client, "suppression")
    rejected_payload = semantic_event(
        camera,
        rule,
        independent_verification={
            "status": "rejected",
            "triggered": False,
            "confidence": 0.96,
            "summary": "A hard hat remains visibly in place.",
            "verifier_model": "gemini-verifier",
        },
    )
    rejected = api_client.post(
        "/api/v1/agent/events", headers=AGENT_HEADERS, json=rejected_payload
    ).json()
    assert rejected["verification_status"] == "pending"
    rejected_case = api_client.get("/api/v1/verification-cases?status=pending").json()[0]
    rejected_decision = api_client.post(
        f"/api/v1/verification-cases/{rejected_case['id']}/decision",
        json={
            "status": "rejected",
            "reasoning": "The hard hat remains visible throughout the clip.",
        },
    )
    assert rejected_decision.status_code == 200

    same_model_payload = semantic_event(
        camera,
        rule,
        independent_verification={
            "status": "confirmed",
            "triggered": True,
            "confidence": 0.99,
            "summary": "Claimed confirmation from the same model.",
            "verifier_model": "gemini-proposer",
        },
    )
    uncertain = api_client.post(
        "/api/v1/agent/events", headers=AGENT_HEADERS, json=same_model_payload
    ).json()
    assert uncertain["verification_status"] == "uncertain"
    assert api_client.get("/api/v1/events").json() == []
    assert api_client.get("/api/v1/alerts").json() == []
    cases = api_client.get("/api/v1/verification-cases").json()
    assert {item["status"] for item in cases} == {"rejected", "uncertain"}


def test_field_labels_unlock_release_and_accuracy_drift_locks_it_again(
    api_client: TestClient,
) -> None:
    camera, rule = semantic_camera_and_rule(api_client, "field-gate")
    initial = api_client.get("/api/v1/field-accuracy/rules").json()[0]
    assert initial["latest_snapshot"] is None
    assert initial["policy"]["minimum_positive_labels"] == 5
    assert initial["policy"]["minimum_negative_labels"] == 5

    for index in range(10):
        payload = semantic_event(camera, rule)
        event = api_client.post(
            "/api/v1/agent/events", headers=AGENT_HEADERS, json=payload
        ).json()
        case = next(
            item
            for item in api_client.get("/api/v1/verification-cases").json()
            if item["event_id"] == event["id"]
        )
        positive = index < 5
        environment_tags: list[str] = []
        if index == 0:
            environment_tags = ["low_light"]
        elif index == 5:
            environment_tags = ["partial_occlusion"]
        decision = api_client.post(
            f"/api/v1/verification-cases/{case['id']}/decision",
            json={
                "status": "confirmed" if positive else "rejected",
                "reasoning": "Direct field evidence supports this ground-truth label.",
                "environment_tags": environment_tags,
            },
        )
        assert decision.status_code == 200
        assert decision.json()["accuracy_label"] is not None

    ready = api_client.get("/api/v1/field-accuracy/rules").json()[0]
    snapshot = ready["latest_snapshot"]
    assert snapshot["gate_status"] == "ready"
    assert snapshot["automatic_release_allowed"] is True
    assert snapshot["positive_count"] == 5
    assert snapshot["negative_count"] == 5
    assert snapshot["challenging_count"] == 2
    assert snapshot["precision"] == 1
    assert snapshot["recall"] == 1

    manual_policy = api_client.put(
        f"/api/v1/field-accuracy/rules/{rule['id']}/policy",
        json={"manual_only": True},
    )
    assert manual_policy.status_code == 200
    assert manual_policy.json()["latest_snapshot"]["gate_status"] == "ready"
    assert manual_policy.json()["latest_snapshot"]["automatic_release_allowed"] is False
    automatic_policy = api_client.put(
        f"/api/v1/field-accuracy/rules/{rule['id']}/policy",
        json={"manual_only": False},
    )
    assert automatic_policy.status_code == 200
    assert automatic_policy.json()["latest_snapshot"]["automatic_release_allowed"] is True

    auto_payload = semantic_event(
        camera,
        rule,
        independent_verification={
            "status": "confirmed",
            "triggered": True,
            "confidence": 0.97,
            "summary": "A missing hard hat is visible.",
            "verifier_model": "gemini-verifier",
        },
    )
    auto_event = api_client.post(
        "/api/v1/agent/events", headers=AGENT_HEADERS, json=auto_payload
    ).json()
    assert auto_event["verification_status"] == "confirmed"
    auto_case = next(
        item
        for item in api_client.get("/api/v1/verification-cases").json()
        if item["event_id"] == auto_event["id"]
    )
    audit = api_client.post(
        f"/api/v1/field-accuracy/verification-cases/{auto_case['id']}/audit",
        json={
            "actual_outcome": "no_event",
            "reasoning": "The audited alert was a false alarm caused by head occlusion.",
            "environment_tags": ["partial_occlusion"],
        },
    )
    assert audit.status_code == 201
    assert audit.json()["outcome"] == "false_positive"
    drifted = api_client.get("/api/v1/field-accuracy/rules").json()[0]
    assert drifted["latest_snapshot"]["gate_status"] == "drifting"
    assert drifted["latest_snapshot"]["automatic_release_allowed"] is False

    next_event = api_client.post(
        "/api/v1/agent/events",
        headers=AGENT_HEADERS,
        json=semantic_event(
            camera,
            rule,
            independent_verification=auto_payload["details"]["independent_verification"],
        ),
    ).json()
    assert next_event["verification_status"] == "pending"

    missed = api_client.post(
        "/api/v1/field-accuracy/misses",
        json={
            "rule_id": rule["id"],
            "occurred_at": "2026-08-23T13:00:00Z",
            "reasoning": "The event was visible in the archived camera recording.",
            "environment_tags": ["far_distance"],
        },
    )
    assert missed.status_code == 201
    assert missed.json()["outcome"] == "false_negative"
