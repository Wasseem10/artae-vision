import httpx
import pytest
from video_intelligence_inference.control_plane import (
    ControlPlaneConfigError,
    fetch_agent_config,
)


def camera_payload(*, rule_count: int = 1) -> dict:
    rule = {
        "id": "rule-id",
        "key": "person-dwell",
        "rule_type": "object_dwell",
        "object_class": "person",
        "duration_seconds": 30.0,
        "minimum_confidence": 0.4,
        "absence_grace_seconds": 1.5,
        "zone": {
            "id": "zone-id",
            "name": "loading-zone",
            "points": [
                {"x": 0.2, "y": 0.2},
                {"x": 0.8, "y": 0.2},
                {"x": 0.8, "y": 0.9},
            ],
        },
    }
    return {
        "camera_id": "camera-id",
        "camera_name": "camera-1",
        "source_uri": "rtsp://camera/live",
        "source_type": "rtsp",
        "rules": [rule | {"id": f"rule-{index}"} for index in range(rule_count)],
    }


def test_fetch_agent_config_authenticates_and_resolves_rules() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Agent-Key"] == "agent-secret"
        assert request.url.params["camera_ref"] == "camera-1"
        return httpx.Response(200, json=camera_payload())

    config = fetch_agent_config(
        "http://control-plane:8000",
        agent_key="agent-secret",
        camera_ref="camera-1",
        transport=httpx.MockTransport(handler),
    )

    assert config.camera_id == "camera-id"
    assert config.source_uri == "rtsp://camera/live"
    assert len(config.rules) == 1
    assert config.rules[0].rule_id == "rule-0"
    assert config.rules[0].duration_seconds == 30
    assert config.rules[0].zone.name == "loading-zone"


def test_fetch_agent_config_returns_multiple_active_rules() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=camera_payload(rule_count=2))
    )

    config = fetch_agent_config(
        "http://control-plane:8000",
        agent_key="agent-secret",
        camera_ref="camera-1",
        transport=transport,
    )

    assert [rule.rule_id for rule in config.rules] == ["rule-0", "rule-1"]


def test_fetch_agent_config_can_filter_to_one_rule() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=camera_payload(rule_count=2))
    )

    config = fetch_agent_config(
        "http://control-plane:8000",
        agent_key="agent-secret",
        camera_ref="camera-1",
        rule_ref="rule-1",
        transport=transport,
    )

    assert [rule.rule_id for rule in config.rules] == ["rule-1"]


def test_fetch_agent_config_requires_at_least_one_supported_rule() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=camera_payload(rule_count=0))
    )

    with pytest.raises(ControlPlaneConfigError, match="No active supported camera job"):
        fetch_agent_config(
            "http://control-plane:8000",
            agent_key="agent-secret",
            camera_ref="camera-1",
            transport=transport,
        )


def test_fetch_agent_config_resolves_semantic_vision_job() -> None:
    payload = camera_payload()
    payload["rules"] = [
        {
            "id": "semantic-rule",
            "key": "missing-hard-hat",
            "rule_type": "semantic_vision",
            "object_class": "visual_event",
            "duration_seconds": 0,
            "minimum_confidence": 0.75,
            "absence_grace_seconds": 1,
            "zone": {
                "id": "full-frame-zone",
                "name": "Full frame (automatic)",
                "points": [
                    {"x": 0, "y": 0},
                    {"x": 1, "y": 0},
                    {"x": 1, "y": 1},
                    {"x": 0, "y": 1},
                ],
            },
            "spec": {
                "schema_version": 3,
                "rule_type": "semantic_vision",
                "instruction": "Alert me when a person is not wearing a hard hat.",
                "object_class": "visual_event",
                "zone_id": "full-frame-zone",
                "zone_name": "Full frame (automatic)",
                "minimum_confidence": 0.75,
                "absence_grace_seconds": 1,
                "confirmation_windows": 2,
                "cooldown_seconds": 120,
            },
            "execution_plan": {
                "schema_version": 1,
                "strategy": "semantic_window",
                "provider_requests": True,
            },
        }
    ]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    config = fetch_agent_config(
        "http://control-plane:8000",
        agent_key="agent-secret",
        camera_ref="camera-1",
        transport=transport,
    )

    rule = config.rules[0]
    assert rule.rule_type == "semantic_vision"
    assert rule.instruction == "Alert me when a person is not wearing a hard hat."
    assert rule.confirmation_windows == 2
    assert rule.cooldown_seconds == 120
    assert rule.execution_strategy == "semantic_window"
