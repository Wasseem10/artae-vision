import asyncio
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.execution_plans import plan_job
from video_intelligence_api.models import Zone
from video_intelligence_api.rule_compiler import (
    OpenAIRuleProvider,
    ProviderRuleCandidate,
    RuleCompilerProviderError,
    compile_rule_prompt,
)

AGENT_KEY = "test-agent-key-123456789"
DASHBOARD_KEY = "test-dashboard-key-12345"
EVAL_CASES = Path(__file__).parents[1] / "evals" / "rule_compiler_cases.json"


def deterministic_settings() -> ApiSettings:
    return ApiSettings(
        environment="test",
        database_url="sqlite+aiosqlite://",
        agent_key=AGENT_KEY,
        dashboard_key=DASHBOARD_KEY,
        rule_compiler_provider="deterministic",
    )


def test_deterministic_rule_compiler_eval_cases() -> None:
    cases = json.loads(EVAL_CASES.read_text(encoding="utf-8"))
    for case in cases:
        zones = [
            Zone(
                id=f"zone-{index}",
                camera_id="camera-1",
                name=name,
                points=[
                    {"x": 0.0, "y": 0.0},
                    {"x": 1.0, "y": 0.0},
                    {"x": 1.0, "y": 1.0},
                ],
            )
            for index, name in enumerate(case["zones"])
        ]
        result = asyncio.run(
            compile_rule_prompt(deterministic_settings(), case["prompt"], zones)
        )

        assert result.candidate.status == case["expected_status"], case["name"]
        if case["expected_status"] == "compiled":
            assert result.compiled_rule is not None
            assert result.compiled_rule.object_class == case["expected_object_class"]
            assert result.compiled_rule.zone_name == case["expected_zone"]
            assert result.compiled_rule.rule_type == case["expected_rule_type"]
            if "expected_duration_seconds" in case:
                assert (
                    result.compiled_rule.duration_seconds
                    == case["expected_duration_seconds"]
                )
            if "expected_confirmation_seconds" in case:
                assert (
                    result.compiled_rule.confirmation_seconds
                    == case["expected_confirmation_seconds"]
                )
            default_confidence = (
                0.7 if result.compiled_rule.rule_type == "semantic_vision" else 0.4
            )
            assert result.compiled_rule.minimum_confidence == case.get(
                "expected_minimum_confidence", default_confidence
            )
            if "expected_strategy" in case:
                assert (
                    plan_job(result.compiled_rule).strategy == case["expected_strategy"]
                )
        else:
            assert result.compiled_rule is None
            assert result.candidate.clarification_question


def test_auto_provider_falls_back_and_discloses_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(
        _provider: OpenAIRuleProvider, _prompt: str, _zones: list[Zone]
    ) -> ProviderRuleCandidate:
        raise RuleCompilerProviderError("simulated provider outage")

    monkeypatch.setattr(OpenAIRuleProvider, "compile", unavailable)
    settings = deterministic_settings().model_copy(
        update={
            "rule_compiler_provider": "auto",
            "openai_api_key": SecretStr("test-openai-key"),
        }
    )
    zones = [
        Zone(
            id="zone-1",
            camera_id="camera-1",
            name="loading-zone",
            points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}],
        )
    ]

    result = asyncio.run(
        compile_rule_prompt(
            settings,
            "Alert me if a person remains in the loading zone for 30 seconds.",
            zones,
        )
    )

    assert result.provider == "deterministic"
    assert result.compiled_rule is not None
    assert "deterministic compiler" in result.warnings[0]


def test_explicit_openai_provider_requires_a_key() -> None:
    settings = deterministic_settings().model_copy(
        update={"rule_compiler_provider": "openai"}
    )

    with pytest.raises(RuleCompilerProviderError, match="OPENAI_API_KEY"):
        asyncio.run(compile_rule_prompt(settings, "valid prompt text", []))


def test_provider_cannot_invent_a_camera_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hallucinated_zone(
        _provider: OpenAIRuleProvider, _prompt: str, _zones: list[Zone]
    ) -> ProviderRuleCandidate:
        return ProviderRuleCandidate(
            status="compiled",
            rule_type="zone_dwell",
            object_class="person",
            zone_name="imaginary-zone",
            duration_seconds=30,
            explanation="Candidate returned by the simulated provider.",
        )

    monkeypatch.setattr(OpenAIRuleProvider, "compile", hallucinated_zone)
    settings = deterministic_settings().model_copy(
        update={
            "rule_compiler_provider": "auto",
            "openai_api_key": SecretStr("test-openai-key"),
        }
    )
    zones = [
        Zone(
            id="zone-1",
            camera_id="camera-1",
            name="loading-zone",
            points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}],
        )
    ]

    result = asyncio.run(compile_rule_prompt(settings, "valid prompt text", zones))

    assert result.compiled_rule is None
    assert result.candidate.status == "needs_clarification"
    assert "Available geometry" in result.candidate.clarification_question


def _camera_and_zone(client: TestClient) -> tuple[dict, dict]:
    camera = client.post(
        "/api/v1/cameras",
        json={"name": "compiler-camera", "source_uri": "0"},
    ).json()
    zone = client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "loading-zone",
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.9, "y": 0.1},
                {"x": 0.9, "y": 0.9},
            ],
        },
    ).json()
    return camera, zone


def test_compile_review_accept_and_activate_lifecycle(api_client: TestClient) -> None:
    camera, zone = _camera_and_zone(api_client)
    response = api_client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": "Alert me if a person remains in the loading zone for 30 seconds.",
        },
    )

    assert response.status_code == 201
    compilation = response.json()
    assert compilation["status"] == "ready_for_review"
    assert compilation["provider"] == "deterministic"
    assert compilation["compiler_version"] == "camera-job/3"
    assert compilation["compiled_rule"] == {
        "schema_version": 2,
        "rule_type": "zone_dwell",
        "object_class": "person",
        "zone_id": zone["id"],
        "zone_name": "loading-zone",
        "duration_seconds": 30.0,
        "minimum_confidence": 0.4,
        "absence_grace_seconds": 1.0,
    }
    assert compilation["execution_plan"]["strategy"] == "deterministic_tracking"
    assert compilation["execution_plan"]["provider_requests"] is False

    accepted = api_client.post(
        f"/api/v1/rule-compilations/{compilation['id']}/accept",
        json={},
    )
    assert accepted.status_code == 201
    rule = accepted.json()
    assert rule["status"] == "draft"
    assert rule["spec_version"] == 2
    assert rule["spec"] == compilation["compiled_rule"]
    assert rule["execution_plan"] == compilation["execution_plan"]
    assert rule["zone_id"] == zone["id"]

    stored = api_client.get(f"/api/v1/rule-compilations/{compilation['id']}").json()
    assert stored["status"] == "accepted"
    assert stored["accepted_rule_id"] == rule["id"]
    assert stored["reviewed_at"] is not None

    activated = api_client.patch(
        f"/api/v1/rules/{rule['id']}/status",
        json={"status": "active"},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"


def test_clarification_creates_a_new_revision(api_client: TestClient) -> None:
    camera, _ = _camera_and_zone(api_client)
    first = api_client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": "Alert me if a person remains in the loading zone.",
        },
    ).json()

    assert first["status"] == "needs_clarification"
    assert "duration" in first["clarification_question"]

    clarified = api_client.post(
        f"/api/v1/rule-compilations/{first['id']}/clarifications",
        json={"answer": "30 seconds"},
    )
    assert clarified.status_code == 201
    revision = clarified.json()
    assert revision["status"] == "ready_for_review"
    assert revision["revision"] == 2
    assert revision["parent_id"] == first["id"]
    assert revision["compiled_rule"]["duration_seconds"] == 30.0


def test_clarification_resolves_an_ambiguous_choice(api_client: TestClient) -> None:
    camera, _ = _camera_and_zone(api_client)
    first = api_client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": (
                "Alert me if a person or truck remains in the loading zone "
                "for 30 seconds."
            ),
        },
    ).json()

    assert first["status"] == "needs_clarification"
    revision = api_client.post(
        f"/api/v1/rule-compilations/{first['id']}/clarifications",
        json={"answer": "Use person"},
    ).json()

    assert revision["status"] == "ready_for_review"
    assert revision["compiled_rule"]["object_class"] == "person"


def test_compiler_creates_full_frame_semantic_job_without_manual_zone(
    api_client: TestClient,
) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "camera-without-zones", "source_uri": "webcam:0"},
    ).json()
    response = api_client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": "Alert me when a person is not wearing a hard hat.",
        },
    )

    assert response.status_code == 201
    compilation = response.json()
    assert compilation["status"] == "ready_for_review"
    assert compilation["compiled_rule"]["rule_type"] == "semantic_vision"
    assert compilation["compiled_rule"]["schema_version"] == 3
    assert compilation["compiled_rule"]["instruction"] == (
        "Alert me when a person is not wearing a hard hat."
    )
    assert compilation["compiled_rule"]["zone_name"] == "Full frame (automatic)"
    assert compilation["compiled_rule"]["minimum_confidence"] == 0.7
    assert compilation["execution_plan"]["strategy"] == "semantic_window"
    assert compilation["execution_plan"]["provider_requests"] is True
    assert not any(
        stage["id"] == "object_detection"
        for stage in compilation["execution_plan"]["stages"]
    )

    accepted = api_client.post(
        f"/api/v1/rule-compilations/{compilation['id']}/accept", json={}
    )
    assert accepted.status_code == 201
    rule = accepted.json()
    assert rule["spec"]["confirmation_windows"] == 1
    assert rule["spec"]["cooldown_seconds"] == 60.0

    activated = api_client.patch(
        f"/api/v1/rules/{rule['id']}/status", json={"status": "active"}
    )
    assert activated.status_code == 200

    assignment = api_client.get(
        f"/api/v1/agent/config?camera_ref={camera['id']}",
        headers={"X-Agent-Key": AGENT_KEY},
    ).json()
    assert assignment["rules"][0]["spec"]["rule_type"] == "semantic_vision"
    assert assignment["rules"][0]["execution_plan"]["strategy"] == "semantic_window"

    started = api_client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "running"},
    )
    assert started.status_code == 200
    claimed = api_client.post(
        "/api/v1/agent/assignments/claim",
        json={"worker_id": "semantic-edge"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert claimed.status_code == 200
    assert claimed.json()["capture_source_uri"] == "webcam:0"
    assert claimed.json()["publish_url"].endswith(f"camera-{camera['id']}")

    event_id = str(uuid.uuid4())
    event = api_client.post(
        "/api/v1/agent/events",
        headers={"X-Agent-Key": AGENT_KEY},
        json={
            "schema_version": 2,
            "id": event_id,
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
            "occurred_at": "2026-08-21T12:00:00Z",
            "clip_path": "artifacts/events/hard-hat.mp4",
            "details": {
                "summary": "A worker is visible without a hard hat.",
                "first_frame": 4,
            },
        },
    )
    assert event.status_code == 201
    assert event.json()["event_type"] == "semantic_vision"
    assert event.json()["details"]["first_frame"] == 4
    alerts = api_client.get("/api/v1/alerts").json()
    assert any(alert["event_id"] == event.json()["id"] for alert in alerts)


@pytest.mark.parametrize(
    ("prompt", "expected_type"),
    [
        ("Alert when a person enters the loading zone.", "zone_entry"),
        ("Alert when a person exits the loading zone.", "zone_exit"),
        ("Alert when at least 3 people are in the loading zone.", "count_threshold"),
    ],
)
def test_compiler_supports_generic_polygon_jobs(
    api_client: TestClient, prompt: str, expected_type: str
) -> None:
    camera, _ = _camera_and_zone(api_client)

    response = api_client.post(
        "/api/v1/rule-compilations",
        json={"camera_id": camera["id"], "prompt": prompt},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["compiled_rule"]["schema_version"] == 2
    assert body["compiled_rule"]["rule_type"] == expected_type
    if expected_type == "count_threshold":
        assert body["compiled_rule"]["threshold"] == 3
        assert body["compiled_rule"]["comparison"] == "at_least"


def test_line_crossing_requires_and_resolves_line_geometry(
    api_client: TestClient,
) -> None:
    camera, _ = _camera_and_zone(api_client)
    line = api_client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "door line",
            "geometry_type": "line",
            "points": [{"x": 0.5, "y": 0.1}, {"x": 0.5, "y": 0.9}],
        },
    ).json()

    compilation = api_client.post(
        "/api/v1/rule-compilations",
        json={
            "camera_id": camera["id"],
            "prompt": "Alert when a person crosses the door line.",
        },
    ).json()

    assert compilation["status"] == "ready_for_review"
    assert compilation["compiled_rule"]["rule_type"] == "line_crossing"
    assert compilation["compiled_rule"]["line_id"] == line["id"]
    accepted = api_client.post(
        f"/api/v1/rule-compilations/{compilation['id']}/accept", json={}
    )
    assert accepted.status_code == 201
    assert accepted.json()["spec"]["line_name"] == "door line"
    rule = accepted.json()
    assert (
        api_client.patch(
            f"/api/v1/rules/{rule['id']}/status", json={"status": "active"}
        ).status_code
        == 200
    )
    assignment = api_client.get(
        f"/api/v1/agent/config?camera_ref={camera['id']}",
        headers={"X-Agent-Key": AGENT_KEY},
    ).json()
    assert assignment["rules"][0]["spec"]["rule_type"] == "line_crossing"
    assert assignment["rules"][0]["zone"]["geometry_type"] == "line"


def test_capability_registry_and_activation_rejection(api_client: TestClient) -> None:
    registry = api_client.get("/api/v1/capabilities")
    assert registry.status_code == 200
    assert "line_crossing" in registry.json()["event_types"]
    assert "person" in registry.json()["detector"]["object_classes"]
    assert (
        registry.json()["routing_strategies"]["semantic_window"]["provider_requests"]
        is True
    )

    camera, zone = _camera_and_zone(api_client)
    rule = api_client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": "unknown-class",
            "name": "Unknown custom class",
            "object_class": "forklift",
            "duration_seconds": 5,
        },
    ).json()
    activated = api_client.patch(
        f"/api/v1/rules/{rule['id']}/status", json={"status": "active"}
    )
    assert activated.status_code == 409
    assert "cannot identify 'forklift'" in activated.json()["detail"]
