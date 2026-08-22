AGENT_KEY = "test-agent-key-123456789"


def _accepted_rule(api_client, camera_id: str, prompt: str) -> dict:
    compilation = api_client.post(
        "/api/v1/rule-compilations",
        json={"camera_id": camera_id, "prompt": prompt},
    )
    assert compilation.status_code == 201, compilation.text
    accepted = api_client.post(
        f"/api/v1/rule-compilations/{compilation.json()['id']}/accept",
        json={},
    )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()


def _passed_gate(api_client, camera_id: str) -> dict:
    evaluation = api_client.post(
        "/api/v1/evaluations",
        json={
            "name": "No-entry safety baseline",
            "camera_id": camera_id,
            "source_uri": "fixtures/no-entry.mp4",
            "prompt": "Alert me when a person enters the entrance.",
            "duration_seconds": 10,
            "expected_intervals": [],
        },
    ).json()
    suite = api_client.post(
        "/api/v1/evaluation-suites",
        json={
            "name": "Agent deployment gate",
            "evaluation_ids": [evaluation["id"]],
            "minimum_macro_f1": 1,
            "minimum_macro_recall": 1,
            "maximum_false_positives": 0,
            "maximum_estimated_cost_usd": 0,
            "require_pricing": False,
        },
    ).json()
    run = api_client.post(f"/api/v1/evaluation-suites/{suite['id']}/runs").json()
    assignment = api_client.post(
        "/api/v1/agent/evaluations/claim",
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "agent-plan-gate-worker"},
    ).json()
    api_client.post(
        f"/api/v1/agent/evaluations/{assignment['evaluation_id']}/result",
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "agent-plan-gate-worker", "predicted_intervals": []},
    )
    passed = api_client.get(f"/api/v1/evaluation-suites/runs/{run['id']}").json()
    assert passed["status"] == "passed"
    return passed


def test_visual_agent_plan_is_simulated_gated_versioned_and_reversible(
    api_client,
) -> None:
    camera = api_client.post(
        "/api/v1/cameras", json={"name": "Plan Camera", "source_uri": "0"}
    ).json()
    api_client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "entrance",
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
        },
    )
    rule = _accepted_rule(
        api_client, camera["id"], "Alert me when a person enters the entrance."
    )

    created_response = api_client.post(
        "/api/v1/agent-plans", json={"rule_id": rule["id"]}
    )
    assert created_response.status_code == 201, created_response.text
    first = created_response.json()
    assert first["revision"] == 1
    assert first["status"] == "draft"
    assert [node["kind"] for node in first["plan"]["nodes"]] == [
        "observe",
        "observe",
        "observe",
        "decide",
        "verify",
        "act",
    ]
    assert first["unsupported_capabilities"] == []

    blocked = api_client.post(
        f"/api/v1/agent-plans/{first['id']}/approve",
        json={"regression_run_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert blocked.status_code == 409
    assert "simulation" in blocked.text

    simulated = api_client.post(f"/api/v1/agent-plans/{first['id']}/simulate")
    assert simulated.status_code == 201, simulated.text
    assert all(not step["side_effect_performed"] for step in simulated.json()["trace"])
    assert "No alerts" in simulated.json()["summary"]

    gate = _passed_gate(api_client, camera["id"])
    approved = api_client.post(
        f"/api/v1/agent-plans/{first['id']}/approve",
        json={"regression_run_id": gate["id"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    second = api_client.post("/api/v1/agent-plans", json={"rule_id": rule["id"]}).json()
    assert second["revision"] == 2
    assert second["parent_id"] == first["id"]
    api_client.post(f"/api/v1/agent-plans/{second['id']}/simulate")
    api_client.post(
        f"/api/v1/agent-plans/{second['id']}/approve",
        json={"regression_run_id": gate["id"]},
    )
    versions = api_client.get(f"/api/v1/agent-plans?camera_id={camera['id']}").json()
    assert [version["status"] for version in versions] == ["approved", "superseded"]

    restored = api_client.post(f"/api/v1/agent-plans/{first['id']}/rollback")
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "approved"


def test_visual_agent_plan_exposes_missing_external_connectors(api_client) -> None:
    camera = api_client.post(
        "/api/v1/cameras", json={"name": "Connector Camera", "source_uri": "0"}
    ).json()
    rule = _accepted_rule(
        api_client,
        camera["id"],
        "Monitor tailgating, check the access control badge swipe, and lock the door.",
    )
    plan = api_client.post("/api/v1/agent-plans", json={"rule_id": rule["id"]}).json()

    assert set(plan["unsupported_capabilities"]) == {
        "query.access_control",
        "action.external_system",
    }
    api_client.post(f"/api/v1/agent-plans/{plan['id']}/simulate")
    blocked = api_client.post(
        f"/api/v1/agent-plans/{plan['id']}/approve",
        json={"regression_run_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert blocked.status_code == 409
    assert "missing capabilities" in blocked.text
