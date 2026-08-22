import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

AGENT_HEADERS = {"X-Agent-Key": "test-agent-key-123456789"}


def create_camera(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/v1/cameras",
        json={"name": name, "source_uri": "0"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_site_map_cross_camera_journey_and_idempotent_sightings(
    api_client: TestClient,
) -> None:
    camera_one = create_camera(api_client, "Entry camera")
    camera_two = create_camera(api_client, "Exit camera")
    site = api_client.post(
        "/api/v1/sites",
        json={"name": "Orlando facility", "description": "Test site"},
    ).json()
    entry = api_client.post(
        f"/api/v1/sites/{site['id']}/areas",
        json={
            "name": "Lobby",
            "area_type": "access",
            "x": 0.05,
            "y": 0.1,
            "width": 0.35,
            "height": 0.8,
        },
    ).json()
    exit_area = api_client.post(
        f"/api/v1/sites/{site['id']}/areas",
        json={
            "name": "Dispatch",
            "area_type": "operations",
            "x": 0.55,
            "y": 0.1,
            "width": 0.4,
            "height": 0.8,
        },
    ).json()
    for camera, area, x in (
        (camera_one, entry, 0.2),
        (camera_two, exit_area, 0.8),
    ):
        placement = api_client.put(
            f"/api/v1/sites/{site['id']}/cameras/{camera['id']}/placement",
            json={"area_id": area["id"], "x": x, "y": 0.5, "heading_degrees": 90},
        )
        assert placement.status_code == 200, placement.text

    first_seen = datetime.now(UTC)
    payloads = (
        (camera_one, first_seen, "blue jacket"),
        (camera_two, first_seen + timedelta(seconds=35), "carrying a parcel"),
    )
    first_response = None
    for camera, occurred_at, note in payloads:
        response = api_client.post(
            "/api/v1/agent/entity-sightings",
            headers=AGENT_HEADERS,
            json={
                "camera_id": camera["id"],
                "entity_key": "anonymous-track-a7",
                "label": "Person with parcel",
                "bounding_box": {"x": 0.2, "y": 0.2, "width": 0.25, "height": 0.6},
                "confidence": 0.93,
                "attributes": {"note": note},
                "occurred_at": occurred_at.isoformat(),
            },
        )
        assert response.status_code == 201, response.text
        first_response = first_response or response

    duplicate = api_client.post(
        "/api/v1/agent/entity-sightings",
        headers=AGENT_HEADERS,
        json={
            "camera_id": camera_one["id"],
            "entity_key": "anonymous-track-a7",
            "label": "Person with parcel",
            "bounding_box": {"x": 0.2, "y": 0.2, "width": 0.25, "height": 0.6},
            "confidence": 0.93,
            "attributes": {"note": "blue jacket"},
            "occurred_at": first_seen.isoformat(),
        },
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first_response.json()["id"]

    journey = api_client.get("/api/v1/entities/anonymous-track-a7/journey").json()
    assert [item["camera_name"] for item in journey] == ["Entry camera", "Exit camera"]
    assert [item["area_name"] for item in journey] == ["Lobby", "Dispatch"]

    site_map = api_client.get(f"/api/v1/sites/{site['id']}/map").json()
    assert len(site_map["areas"]) == 2
    assert len(site_map["placements"]) == 2
    assert len(site_map["recent_sightings"]) == 2


def test_unified_investigation_searches_events_scene_text_and_entities(
    api_client: TestClient,
) -> None:
    camera = create_camera(api_client, "Investigation camera")
    demo_map = api_client.post(
        f"/api/v1/cameras/{camera['id']}/operations/demo",
        json={},
    )
    assert demo_map.status_code == 201, demo_map.text
    assert len(demo_map.json()["areas"]) == 3

    zone = api_client.post(
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
    rule = api_client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": "parcel-loading-event",
            "name": "Parcel enters loading zone",
            "duration_seconds": 1,
            "original_prompt": "Alert when a parcel enters the loading zone.",
        },
    ).json()
    api_client.patch(f"/api/v1/rules/{rule['id']}/status", json={"status": "active"})
    occurred_at = datetime.now(UTC)
    event = api_client.post(
        "/api/v1/agent/events",
        headers=AGENT_HEADERS,
        json={
            "schema_version": 1,
            "id": str(uuid.uuid4()),
            "event_type": "object_dwell",
            "rule_id": rule["id"],
            "camera_id": camera["id"],
            "track_id": 4,
            "object_class": "parcel",
            "zone_name": "loading-zone",
            "entered_at_seconds": 1,
            "occurred_at_seconds": 2,
            "dwell_seconds": 1,
            "confidence": 0.9,
            "occurred_at": occurred_at.isoformat(),
            "clip_path": "artifacts/events/clips/parcel.mp4",
            "details": {"color": "red"},
        },
    )
    assert event.status_code == 201, event.text

    scene = api_client.post(
        "/api/v1/agent/scene-memory",
        headers=AGENT_HEADERS,
        json={
            "camera_id": camera["id"],
            "occurred_at": (occurred_at + timedelta(seconds=1)).isoformat(),
            "observations": [
                {
                    "stable_key": "controller-display",
                    "label": "Controller display",
                    "kind": "display",
                    "bounding_box": {"x": 0.7, "y": 0.1, "width": 0.2, "height": 0.2},
                    "description": "Production controller",
                    "state": "warning",
                    "confidence": 0.94,
                    "attributes": {"text": "FAULT 42"},
                }
            ],
        },
    )
    assert scene.status_code == 200, scene.text
    sighting = api_client.post(
        "/api/v1/agent/entity-sightings",
        headers=AGENT_HEADERS,
        json={
            "camera_id": camera["id"],
            "entity_key": "anonymous-parcel-red",
            "label": "Red parcel",
            "bounding_box": {"x": 0.3, "y": 0.2, "width": 0.2, "height": 0.2},
            "confidence": 0.88,
            "attributes": {"destination": "dispatch"},
            "occurred_at": (occurred_at + timedelta(seconds=2)).isoformat(),
        },
    )
    assert sighting.status_code == 201

    event_results = api_client.post(
        "/api/v1/investigations/search", json={"query": "red loading-zone"}
    ).json()["results"]
    assert any(result["kind"] == "event" for result in event_results)
    scene_results = api_client.post(
        "/api/v1/investigations/search", json={"query": "FAULT 42"}
    ).json()["results"]
    assert any(result["kind"] == "scene" for result in scene_results)
    entity_results = api_client.post(
        "/api/v1/investigations/search", json={"query": "dispatch red parcel"}
    ).json()["results"]
    assert any(result["kind"] == "entity" for result in entity_results)
