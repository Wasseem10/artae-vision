import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
from video_intelligence_api.models import (
    AgentDesiredStatus,
    AgentObservedStatus,
    Camera,
    CameraAgent,
    EdgeDevice,
    utc_now,
)

AGENT_KEY = "test-agent-key-123456789"


def _evaluate(api_client: TestClient) -> dict:
    response = api_client.post(
        "/api/v1/agent/operational-health/evaluate",
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert response.status_code == 200
    return response.json()


def test_watchdog_opens_acknowledges_and_auto_resolves_camera_incident(
    api_client: TestClient,
) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Health camera", "source_uri": "webcam:0"},
    ).json()

    async def make_stale() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            stale = utc_now() - timedelta(minutes=5)
            session.add(
                CameraAgent(
                    camera_id=camera["id"],
                    desired_status=AgentDesiredStatus.RUNNING,
                    observed_status=AgentObservedStatus.RUNNING,
                    last_heartbeat_at=stale,
                    last_frame_at=stale,
                )
            )
            await session.commit()

    asyncio.run(make_stale())
    evaluation = _evaluate(api_client)
    assert evaluation["opened_incidents"] == 1
    assert evaluation["active_incidents"] == 1

    incidents = api_client.get("/api/v1/operational-health/incidents").json()
    assert len(incidents) == 1
    assert incidents[0]["condition"] == "camera_heartbeat_stale"
    assert incidents[0]["severity"] == "critical"

    repeated = _evaluate(api_client)
    assert repeated["opened_incidents"] == 0
    repeated_incidents = api_client.get("/api/v1/operational-health/incidents").json()
    assert len(repeated_incidents) == 1
    assert repeated_incidents[0]["occurrence_count"] == 2

    acknowledged = api_client.post(
        f"/api/v1/operational-health/incidents/{incidents[0]['id']}/acknowledge"
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "acknowledged"

    async def recover() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            agent = await session.get(CameraAgent, camera["id"])
            assert agent is not None
            agent.last_heartbeat_at = utc_now()
            agent.last_frame_at = utc_now()
            await session.commit()

    asyncio.run(recover())
    recovered = _evaluate(api_client)
    assert recovered["resolved_incidents"] == 1
    resolved = api_client.get(
        "/api/v1/operational-health/incidents?status=resolved"
    ).json()
    assert resolved[0]["status"] == "resolved"
    assert resolved[0]["resolved_by"] == "system:operational-health-watchdog"


def test_watchdog_monitors_only_edge_stations_attached_to_cameras(
    api_client: TestClient,
) -> None:
    attached = api_client.post(
        "/api/v1/edge-devices",
        json={"name": "Attached edge", "max_concurrent_streams": 2},
    ).json()["device"]
    api_client.post(
        "/api/v1/edge-devices",
        json={"name": "Unused edge", "max_concurrent_streams": 2},
    )
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "Pinned camera", "source_uri": "rtsp://camera.test/live"},
    ).json()

    async def pin_and_age() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            camera_row = await session.get(Camera, camera["id"])
            device = await session.get(EdgeDevice, attached["id"])
            assert camera_row is not None and device is not None
            camera_row.edge_device_id = device.id
            device.created_at = utc_now() - timedelta(minutes=5)
            await session.commit()

    asyncio.run(pin_and_age())
    assert _evaluate(api_client)["opened_incidents"] == 1
    incidents = api_client.get(
        "/api/v1/operational-health/incidents?status=open"
    ).json()
    assert len(incidents) == 1
    assert incidents[0]["condition"] == "edge_never_connected"
    assert incidents[0]["resource_name"] == "Attached edge"
