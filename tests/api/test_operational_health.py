import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from video_intelligence_api.models import (
    AgentDesiredStatus,
    AgentObservedStatus,
    AlertChannel,
    Camera,
    CameraAgent,
    EdgeDevice,
    OperationalHealthDelivery,
    OperationalHealthIncident,
    Organization,
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


def _create_channel(api_client: TestClient) -> dict:
    response = api_client.post(
        "/api/v1/alert-channels",
        json={
            "name": "pilot outage webhook",
            "webhook_url": "https://responder.example.test/outage",
            "signing_secret": "pilot-outage-signing-secret",
            "max_attempts": 3,
        },
    )
    assert response.status_code == 201
    return response.json()


def _stale_camera(api_client: TestClient) -> dict:
    camera = api_client.post(
        "/api/v1/cameras", json={"name": "Pilot living room", "source_uri": "webcam:0"}
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
    return camera


def _age_incident(api_client: TestClient, incident_id: str) -> None:
    async def age() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            incident = await session.get(OperationalHealthIncident, incident_id)
            assert incident is not None
            incident.first_detected_at = utc_now() - timedelta(minutes=3)
            await session.commit()

    asyncio.run(age())


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


def test_prolonged_outage_is_opt_in_deduplicated_and_has_separate_human_ack(
    api_client: TestClient,
) -> None:
    camera = _stale_camera(api_client)
    channel = _create_channel(api_client)
    api_client.app.state.settings.alert_lease_seconds = 10
    assert (
        api_client.patch(
            f"/api/v1/alert-channels/{channel['id']}", json={"timeout_seconds": 60}
        ).status_code
        == 200
    )
    assert _evaluate(api_client)["opened_incidents"] == 1
    incident = api_client.get("/api/v1/operational-health/incidents").json()[0]
    _age_incident(api_client, incident["id"])
    assert _evaluate(api_client)["active_incidents"] == 1
    assert (
        api_client.get("/api/v1/operational-health/incidents").json()[0]["deliveries"]
        == []
    )

    path = f"/api/v1/cameras/{camera['id']}/health-alert-routes"
    unauthorized = api_client.post(
        path,
        headers={"X-Dashboard-Key": ""},
        json={"channel_id": channel["id"]},
    )
    assert unauthorized.status_code == 401
    assert (
        api_client.post(
            path, json={"channel_id": channel["id"], "outage_after_seconds": 59}
        ).status_code
        == 422
    )
    created = api_client.post(path, json={"channel_id": channel["id"]})
    assert created.status_code == 201
    assert created.json()["outage_after_seconds"] == 120
    assert api_client.get(path).json() == [created.json()]
    assert api_client.post(path, json={"channel_id": channel["id"]}).status_code == 409

    assert _evaluate(api_client)["active_incidents"] == 1

    async def change_symptom() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            agent = await session.get(CameraAgent, camera["id"])
            assert agent is not None
            agent.observed_status = AgentObservedStatus.ERROR
            agent.last_error = "Camera read failed"
            await session.commit()

    asyncio.run(change_symptom())
    assert _evaluate(api_client)["active_incidents"] == 1
    changed = api_client.get("/api/v1/operational-health/incidents").json()[0]
    assert changed["condition"] == "camera_runtime_error"
    deliveries = changed["deliveries"]
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "queued"

    claim_path = "/api/v1/agent/operational-health/deliveries/claim"
    claim = api_client.post(
        claim_path,
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "outage-worker"},
    )
    assert claim.status_code == 200
    assignment = claim.json()

    async def lease_expiration() -> datetime:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            delivery = await session.get(
                OperationalHealthDelivery, assignment["delivery_id"]
            )
            assert delivery is not None and delivery.lease_expires_at is not None
            return delivery.lease_expires_at

    lease = asyncio.run(lease_expiration())
    if lease.tzinfo is None:
        lease = lease.replace(tzinfo=UTC)
    assert lease >= utc_now() + timedelta(seconds=85)
    assert assignment["incident_id"] == incident["id"]
    assert assignment["payload"]["type"] == "video.monitoring.unavailable"
    assert assignment["payload"]["camera"]["id"] == camera["id"]
    assert "signing_secret" in assignment
    assert "signing_secret" not in api_client.get(path).text
    assert (
        "signing_secret"
        not in api_client.get("/api/v1/operational-health/incidents").text
    )

    result_path = f"/api/v1/agent/operational-health/deliveries/{assignment['delivery_id']}/result"
    wrong_worker = api_client.post(
        result_path,
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "other", "outcome": "delivered", "status_code": 200},
    )
    assert wrong_worker.status_code == 409
    delivered = api_client.post(
        result_path,
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "outage-worker", "outcome": "delivered", "status_code": 200},
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"
    before_ack = api_client.get("/api/v1/operational-health/incidents").json()[0]
    assert before_ack["acknowledged_at"] is None
    assert before_ack["acknowledged_by"] is None

    acknowledged = api_client.post(
        f"/api/v1/operational-health/incidents/{incident['id']}/acknowledge",
        json={"acknowledged_by": "spoofed-responder"},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged_by"] == "local-dashboard-operator"
    assert acknowledged.json()["acknowledged_at"] is not None
    assert (
        api_client.post(
            claim_path,
            headers={"X-Agent-Key": AGENT_KEY},
            json={"worker_id": "outage-worker"},
        ).status_code
        == 204
    )


def test_transient_or_recovered_outage_never_notifies_and_route_removal_suppresses(
    api_client: TestClient,
) -> None:
    camera = _stale_camera(api_client)
    channel = _create_channel(api_client)
    path = f"/api/v1/cameras/{camera['id']}/health-alert-routes"
    route = api_client.post(path, json={"channel_id": channel["id"]}).json()
    assert _evaluate(api_client)["opened_incidents"] == 1
    incident = api_client.get("/api/v1/operational-health/incidents").json()[0]
    assert incident["deliveries"] == []

    async def recover() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            agent = await session.get(CameraAgent, camera["id"])
            assert agent is not None
            agent.last_heartbeat_at = utc_now()
            agent.last_frame_at = utc_now()
            await session.commit()

    asyncio.run(recover())
    assert _evaluate(api_client)["resolved_incidents"] == 1
    assert (
        api_client.get("/api/v1/operational-health/incidents").json()[0]["deliveries"]
        == []
    )

    async def fail_again() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            agent = await session.get(CameraAgent, camera["id"])
            assert agent is not None
            agent.last_heartbeat_at = utc_now() - timedelta(minutes=5)
            agent.last_frame_at = utc_now() - timedelta(minutes=5)
            await session.commit()

    asyncio.run(fail_again())
    assert _evaluate(api_client)["opened_incidents"] == 1
    current = api_client.get("/api/v1/operational-health/incidents?status=open").json()[
        0
    ]
    assert current["id"] != incident["id"]
    _age_incident(api_client, current["id"])
    _evaluate(api_client)
    assert (
        len(
            api_client.get("/api/v1/operational-health/incidents?status=open").json()[
                0
            ]["deliveries"]
        )
        == 1
    )
    assert api_client.delete(f"{path}/{route['id']}").status_code == 204
    assert api_client.get(path).json() == []
    current = api_client.get("/api/v1/operational-health/incidents?status=open").json()[
        0
    ]
    assert current["deliveries"][0]["status"] == "suppressed"
    assert _evaluate(api_client)["active_incidents"] == 1
    assert (
        api_client.post(
            "/api/v1/agent/operational-health/deliveries/claim",
            headers={"X-Agent-Key": AGENT_KEY},
            json={"worker_id": "outage-worker"},
        ).status_code
        == 204
    )


def test_health_route_rejects_foreign_tenant_channel_and_acknowledgment(
    api_client: TestClient,
) -> None:
    camera = _stale_camera(api_client)
    channel = _create_channel(api_client)
    _evaluate(api_client)
    incident_id = api_client.get("/api/v1/operational-health/incidents").json()[0]["id"]

    async def move_to_other_tenant() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            session.add(
                Organization(
                    id="00000000-0000-0000-0000-000000000099",
                    slug="foreign-tenant",
                    name="Foreign tenant",
                )
            )
            await session.flush()
            foreign_channel = await session.get(AlertChannel, channel["id"])
            assert foreign_channel is not None
            foreign_channel.organization_id = "00000000-0000-0000-0000-000000000099"
            incident = await session.get(OperationalHealthIncident, incident_id)
            assert incident is not None
            incident.organization_id = "00000000-0000-0000-0000-000000000099"
            await session.commit()

    asyncio.run(move_to_other_tenant())
    assert (
        api_client.post(
            f"/api/v1/cameras/{camera['id']}/health-alert-routes",
            json={"channel_id": channel["id"]},
        ).status_code
        == 404
    )
    assert (
        api_client.post(
            f"/api/v1/operational-health/incidents/{incident_id}/acknowledge"
        ).status_code
        == 404
    )


def test_health_delivery_never_crosses_camera_incident_channel_tenants(
    api_client: TestClient,
) -> None:
    camera = _stale_camera(api_client)
    channel = _create_channel(api_client)
    api_client.post(
        f"/api/v1/cameras/{camera['id']}/health-alert-routes",
        json={"channel_id": channel["id"]},
    )
    _evaluate(api_client)
    incident_id = api_client.get("/api/v1/operational-health/incidents").json()[0]["id"]
    _age_incident(api_client, incident_id)
    foreign_id = "00000000-0000-0000-0000-000000000099"
    local_id = camera["organization_id"]

    async def move_channel(organization_id: str) -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            if organization_id == foreign_id:
                session.add(Organization(id=foreign_id, slug="other", name="Other"))
                await session.flush()
            channel_row = await session.get(AlertChannel, channel["id"])
            assert channel_row is not None
            channel_row.organization_id = organization_id
            await session.commit()

    asyncio.run(move_channel(foreign_id))
    _evaluate(api_client)
    assert (
        api_client.get("/api/v1/operational-health/incidents").json()[0]["deliveries"]
        == []
    )
    asyncio.run(move_channel(local_id))
    _evaluate(api_client)
    assert (
        len(
            api_client.get("/api/v1/operational-health/incidents").json()[0][
                "deliveries"
            ]
        )
        == 1
    )

    async def move_incident() -> None:
        database = api_client.app.state.database
        async with database.session_factory() as session:
            incident = await session.get(OperationalHealthIncident, incident_id)
            assert incident is not None
            incident.organization_id = foreign_id
            await session.commit()

    asyncio.run(move_incident())
    assert (
        api_client.post(
            "/api/v1/agent/operational-health/deliveries/claim",
            headers={"X-Agent-Key": AGENT_KEY},
            json={"worker_id": "pilot-worker"},
        ).status_code
        == 204
    )


def test_health_delivery_retries_then_acknowledgment_suppresses_pending_attempt(
    api_client: TestClient,
) -> None:
    camera = _stale_camera(api_client)
    channel = _create_channel(api_client)
    api_client.post(
        f"/api/v1/cameras/{camera['id']}/health-alert-routes",
        json={"channel_id": channel["id"]},
    )
    _evaluate(api_client)
    incident_id = api_client.get("/api/v1/operational-health/incidents").json()[0]["id"]
    _age_incident(api_client, incident_id)
    _evaluate(api_client)
    claim = api_client.post(
        "/api/v1/agent/operational-health/deliveries/claim",
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "pilot-worker"},
    ).json()
    result = api_client.post(
        f"/api/v1/agent/operational-health/deliveries/{claim['delivery_id']}/result",
        headers={"X-Agent-Key": AGENT_KEY},
        json={
            "worker_id": "pilot-worker",
            "outcome": "retryable",
            "status_code": 503,
            "error": "Webhook returned HTTP 503",
        },
    )
    assert result.status_code == 200
    assert result.json()["status"] == "retrying"
    assert result.json()["attempt_count"] == 1
    acknowledged = api_client.post(
        f"/api/v1/operational-health/incidents/{incident_id}/acknowledge"
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["deliveries"][0]["status"] == "suppressed"
    assert acknowledged.json()["deliveries"][0]["attempt_count"] == 1
    assert (
        api_client.post(
            "/api/v1/agent/operational-health/deliveries/claim",
            headers={"X-Agent-Key": AGENT_KEY},
            json={"worker_id": "pilot-worker"},
        ).status_code
        == 204
    )


@pytest.mark.parametrize("transition", ["route_removed", "acknowledged", "recovered"])
def test_in_flight_health_delivery_becomes_terminal_when_outage_ends(
    api_client: TestClient, transition: str
) -> None:
    camera = _stale_camera(api_client)
    channel = _create_channel(api_client)
    route_path = f"/api/v1/cameras/{camera['id']}/health-alert-routes"
    route = api_client.post(route_path, json={"channel_id": channel["id"]}).json()
    _evaluate(api_client)
    incident_id = api_client.get("/api/v1/operational-health/incidents").json()[0]["id"]
    _age_incident(api_client, incident_id)
    _evaluate(api_client)
    claim = api_client.post(
        "/api/v1/agent/operational-health/deliveries/claim",
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "pilot-worker"},
    ).json()

    if transition == "route_removed":
        assert api_client.delete(f"{route_path}/{route['id']}").status_code == 204
    elif transition == "acknowledged":
        assert (
            api_client.post(
                f"/api/v1/operational-health/incidents/{incident_id}/acknowledge"
            ).status_code
            == 200
        )
    else:

        async def recover() -> None:
            database = api_client.app.state.database
            async with database.session_factory() as session:
                agent = await session.get(CameraAgent, camera["id"])
                assert agent is not None
                agent.last_heartbeat_at = utc_now()
                agent.last_frame_at = utc_now()
                await session.commit()

        asyncio.run(recover())
        assert _evaluate(api_client)["resolved_incidents"] == 1

    incident = api_client.get("/api/v1/operational-health/incidents").json()[0]
    assert incident["deliveries"][0]["status"] == "suppressed"
    assert "outcome unknown" in incident["deliveries"][0]["last_error"]
    assert (
        api_client.post(
            "/api/v1/agent/operational-health/deliveries/claim",
            headers={"X-Agent-Key": AGENT_KEY},
            json={"worker_id": "pilot-worker"},
        ).status_code
        == 204
    )
    late_result = api_client.post(
        f"/api/v1/agent/operational-health/deliveries/{claim['delivery_id']}/result",
        headers={"X-Agent-Key": AGENT_KEY},
        json={"worker_id": "pilot-worker", "outcome": "retryable", "status_code": 503},
    )
    assert late_result.status_code == 409
