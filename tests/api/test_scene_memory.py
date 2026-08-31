from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}


def create_camera(client: TestClient, name: str = "scene-camera") -> dict:
    return client.post("/api/v1/cameras", json={"name": name, "source_uri": "0"}).json()


def scene_payload(camera_id: str, state: str = "on") -> dict:
    return {
        "camera_id": camera_id,
        "occurred_at": datetime.now(UTC).isoformat(),
        "observations": [
            {
                "stable_key": "treadmill-display-1",
                "label": "Treadmill display 1",
                "kind": "display",
                "bounding_box": {"x": 0.2, "y": 0.1, "width": 0.2, "height": 0.2},
                "description": "The first treadmill console.",
                "state": state,
                "confidence": 0.91,
                "attributes": {"row": 1},
                "relationships": [{"type": "part_of", "target": "treadmill-1"}],
            }
        ],
    }


def test_visual_skill_registry_explains_fallback_and_benchmarks(
    api_client: TestClient,
) -> None:
    response = api_client.get("/api/v1/visual-skills")
    assert response.status_code == 200
    skills = {skill["id"]: skill for skill in response.json()["skills"]}
    assert skills["ppe_compliance"]["fallback_executor"] == "Temporal VLM windows"
    assert skills["ppe_compliance"]["status"] == "fallback_only"
    assert skills["change_anomaly"]["temporal_support"] == ["transition", "sequence"]
    assert "source-frame" in skills["ocr_text"]["output_contract"]
    assert "replay gate" in skills["pose_action"]["benchmark_policy"]
    assert len(skills) == 8


def test_agent_scene_observations_upsert_state_and_append_changes(
    api_client: TestClient,
) -> None:
    camera = create_camera(api_client)
    created = api_client.post(
        "/api/v1/agent/scene-memory",
        headers=AGENT_HEADERS,
        json=scene_payload(camera["id"]),
    )
    assert created.status_code == 200, created.text
    item = created.json()[0]
    assert item["review_status"] == "proposed"
    assert item["source"] == "automatic"
    assert item["relationships"][0]["target"] == "treadmill-1"
    assert (
        len(api_client.get(f"/api/v1/cameras/{camera['id']}/scene-changes").json()) == 1
    )

    same = scene_payload(camera["id"])
    same["occurred_at"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    api_client.post("/api/v1/agent/scene-memory", headers=AGENT_HEADERS, json=same)
    assert (
        len(api_client.get(f"/api/v1/cameras/{camera['id']}/scene-changes").json()) == 1
    )

    changed = scene_payload(camera["id"], "off")
    changed["occurred_at"] = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
    updated = api_client.post(
        "/api/v1/agent/scene-memory", headers=AGENT_HEADERS, json=changed
    ).json()[0]
    assert updated["id"] == item["id"]
    assert updated["current_state"] == "off"
    changes = api_client.get(f"/api/v1/cameras/{camera['id']}/scene-changes").json()
    assert len(changes) == 2
    assert changes[0]["previous_state"] == "on"
    assert changes[0]["new_state"] == "off"

    reviewed = api_client.patch(
        f"/api/v1/scene-memory/{item['id']}",
        json={"review_status": "confirmed", "label": "Front treadmill display"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "confirmed"
    assert reviewed.json()["source"] == "operator"
    assert reviewed.json()["reviewed_by"] == "local-dashboard-operator"


def test_demo_discovery_requires_no_operator_drawn_geometry(
    api_client: TestClient,
) -> None:
    camera = create_camera(api_client, "automatic-discovery")
    response = api_client.post(
        f"/api/v1/cameras/{camera['id']}/scene-memory/demo-discovery",
        json={},
    )
    assert response.status_code == 201
    assert {item["kind"] for item in response.json()} == {"region", "display"}
    assert all(item["review_status"] == "proposed" for item in response.json())
