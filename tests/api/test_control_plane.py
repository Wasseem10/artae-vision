import hashlib
import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

AGENT_KEY = "test-agent-key-123456789"
DASHBOARD_KEY = "test-dashboard-key-12345"


def create_active_rule(client: TestClient) -> tuple[dict, dict, dict]:
    camera_response = client.post(
        "/api/v1/cameras",
        json={
            "name": "camera-1",
            "source_uri": "rtsp://operator:secret@10.0.0.8/live",
        },
    )
    assert camera_response.status_code == 201
    camera = camera_response.json()

    zone_response = client.post(
        "/api/v1/zones",
        json={
            "camera_id": camera["id"],
            "name": "loading-zone",
            "points": [
                {"x": 0.2, "y": 0.2},
                {"x": 0.8, "y": 0.2},
                {"x": 0.8, "y": 0.9},
                {"x": 0.2, "y": 0.9},
            ],
        },
    )
    assert zone_response.status_code == 201
    zone = zone_response.json()

    rule_response = client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": "person-dwell",
            "name": "Person remains in loading zone",
            "duration_seconds": 10,
            "original_prompt": (
                "Alert me if a person enters the loading zone and remains "
                "there for more than 10 seconds."
            ),
        },
    )
    assert rule_response.status_code == 201
    rule = rule_response.json()
    assert rule["status"] == "draft"

    activation = client.patch(
        f"/api/v1/rules/{rule['id']}/status",
        json={"status": "active"},
    )
    assert activation.status_code == 200
    rule = activation.json()
    return camera, zone, rule


def event_payload(event_id: str | None = None) -> dict:
    return {
        "schema_version": 1,
        "id": event_id or str(uuid.uuid4()),
        "event_type": "object_dwell",
        "rule_id": "person-dwell",
        "camera_id": "camera-1",
        "track_id": 7,
        "object_class": "person",
        "zone_name": "loading-zone",
        "entered_at_seconds": 1.0,
        "occurred_at_seconds": 11.0,
        "dwell_seconds": 10.0,
        "confidence": 0.91,
        "occurred_at": datetime.now(UTC).isoformat(),
        "clip_path": "artifacts/events/clips/example.mp4",
    }


def test_camera_zone_and_rule_lifecycle(api_client: TestClient) -> None:
    camera, zone, rule = create_active_rule(api_client)

    assert camera["source_type"] == "rtsp"
    assert camera["source_uri"] == "rtsp://***:***@10.0.0.8/live"
    assert zone["camera_id"] == camera["id"]
    assert rule["camera_id"] == camera["id"]
    assert rule["status"] == "active"
    assert len(api_client.get("/api/v1/cameras").json()) == 1
    assert len(api_client.get(f"/api/v1/zones?camera_id={camera['id']}").json()) == 1

    unauthorized = api_client.get("/api/v1/agent/config?camera_ref=camera-1")
    assert unauthorized.status_code == 401
    agent_config = api_client.get(
        "/api/v1/agent/config?camera_ref=camera-1",
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert agent_config.status_code == 200
    config_body = agent_config.json()
    assert config_body["source_uri"] == "rtsp://operator:secret@10.0.0.8/live"
    assert config_body["rules"][0]["id"] == rule["id"]
    assert config_body["rules"][0]["zone"]["id"] == zone["id"]


def test_agent_event_is_authenticated_idempotent_and_broadcast(
    api_client: TestClient,
) -> None:
    camera, _, rule = create_active_rule(api_client)
    payload = event_payload()

    unauthorized = api_client.post("/api/v1/agent/events", json=payload)
    assert unauthorized.status_code == 401

    with api_client.websocket_connect(
        f"/api/v1/ws/events?token={DASHBOARD_KEY}"
    ) as websocket:
        assert websocket.receive_json() == {"type": "connected"}
        created = api_client.post(
            "/api/v1/agent/events",
            json=payload,
            headers={"X-Agent-Key": AGENT_KEY},
        )
        assert created.status_code == 201
        broadcast = websocket.receive_json()

    body = created.json()
    assert body["camera_id"] == camera["id"]
    assert body["rule_id"] == rule["id"]
    assert broadcast["type"] == "event.created"
    assert broadcast["data"]["source_event_id"] == payload["id"]

    duplicate = api_client.post(
        "/api/v1/agent/events",
        json=payload,
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert duplicate.status_code == 200
    events = api_client.get("/api/v1/events").json()
    assert len(events) == 1


def test_event_from_draft_rule_is_rejected(api_client: TestClient) -> None:
    _, _, rule = create_active_rule(api_client)
    pause = api_client.patch(
        f"/api/v1/rules/{rule['id']}/status",
        json={"status": "paused"},
    )
    assert pause.status_code == 200

    response = api_client.post(
        "/api/v1/agent/events",
        json=event_payload(),
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Rule is not active"


def test_evidence_upload_index_lifecycle_and_search(api_client: TestClient) -> None:
    camera, _, _ = create_active_rule(api_client)
    payload = event_payload()
    event = api_client.post(
        "/api/v1/agent/events",
        json=payload,
        headers={"X-Agent-Key": AGENT_KEY},
    ).json()

    awaiting = api_client.get("/api/v1/evidence").json()
    assert awaiting[0]["event_id"] == event["id"]
    assert awaiting[0]["status"] == "awaiting_upload"
    assert awaiting[0]["content_url"] is None

    clip = b"small-mp4-evidence"
    upload = api_client.put(
        f"/api/v1/agent/events/{payload['id']}/clip",
        content=clip,
        headers={
            "X-Agent-Key": AGENT_KEY,
            "Content-Type": "video/mp4",
            "X-Evidence-Duration-Seconds": "7.5",
        },
    )
    assert upload.status_code == 200
    asset = upload.json()
    assert asset["status"] == "queued"
    assert asset["size_bytes"] == len(clip)
    assert asset["sha256"] == hashlib.sha256(clip).hexdigest()
    assert asset["duration_seconds"] == 7.5
    assert api_client.get(asset["content_url"]).content == clip

    unauthorized = api_client.post(
        "/api/v1/agent/evidence/index-assignments/claim",
        json={"worker_id": "evidence-1"},
    )
    assert unauthorized.status_code == 401
    claim = api_client.post(
        "/api/v1/agent/evidence/index-assignments/claim",
        json={"worker_id": "evidence-1"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert claim.status_code == 200
    assert claim.json()["asset_id"] == asset["id"]

    indexed = api_client.post(
        f"/api/v1/agent/evidence/{asset['id']}/index-result",
        json={
            "worker_id": "evidence-1",
            "status": "ready",
            "external_index_id": "idx-1",
            "external_video_id": "video-1",
        },
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert indexed.status_code == 200
    assert indexed.json()["status"] == "ready"

    created_search = api_client.post(
        "/api/v1/evidence/searches",
        json={"query": "person in the loading zone", "camera_id": camera["id"]},
    )
    assert created_search.status_code == 201
    assert created_search.json()["status"] == "queued"
    search_id = created_search.json()["id"]
    search_claim = api_client.post(
        "/api/v1/agent/evidence/search-assignments/claim",
        json={"worker_id": "evidence-1"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert search_claim.json()["search_id"] == search_id
    completed = api_client.post(
        f"/api/v1/agent/evidence/searches/{search_id}/result",
        json={
            "worker_id": "evidence-1",
            "status": "completed",
            "latency_ms": 12,
            "results": [
                {
                    "video_id": "video-1",
                    "time_start": 1.25,
                    "time_end": 4.5,
                    "similarity": 0.94,
                    "summary": "A person remains in the loading zone.",
                }
            ],
        },
        headers={"X-Agent-Key": AGENT_KEY},
    )
    body = completed.json()
    assert body["status"] == "completed"
    assert body["results"][0]["time_start"] == 1.25
    result_url = body["results"][0]["content_url"]
    assert (
        result_url.split("?", maxsplit=1)[0]
        == asset["content_url"].split("?", maxsplit=1)[0]
    )
    assert api_client.get(result_url).content == clip


def test_search_falls_back_to_local_metadata_without_indexed_clips(
    api_client: TestClient,
) -> None:
    create_active_rule(api_client)
    payload = event_payload()
    api_client.post(
        "/api/v1/agent/events",
        json=payload,
        headers={"X-Agent-Key": AGENT_KEY},
    )
    api_client.put(
        f"/api/v1/agent/events/{payload['id']}/clip",
        content=b"local-clip",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "video/mp4"},
    )

    response = api_client.post(
        "/api/v1/evidence/searches",
        json={"query": "show the person near loading zone"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "local_metadata"
    assert body["status"] == "completed"
    assert body["results"][0]["camera_name"] == "camera-1"
    assert "local metadata" in body["last_error"].lower()


def test_health_and_openapi(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/health/live").json() == {"status": "ok"}
    assert api_client.get("/api/v1/health/ready").json() == {"status": "ok"}
    assert api_client.get("/openapi.json").status_code == 200


def test_browser_origin_is_explicitly_allowed(api_client: TestClient) -> None:
    response = api_client.options(
        "/api/v1/cameras",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_stream_gateway_keeps_rtsp_credentials_out_of_browser_contract(
    api_client: TestClient,
) -> None:
    camera_response = api_client.post(
        "/api/v1/cameras",
        json={
            "name": "secure-rtsp-camera",
            "source_uri": "rtsp://operator:secret@10.0.0.8/live",
        },
    )
    camera = camera_response.json()

    provision = api_client.put(f"/api/v1/cameras/{camera['id']}/stream")

    assert provision.status_code == 200
    stream = provision.json()
    assert stream["mode"] == "proxy"
    assert stream["configured"] is True
    assert stream["ready"] is True
    assert stream["readers"] == 1
    assert stream["path"] == f"camera-{camera['id']}"
    assert stream["publish_url"] is None
    assert stream["whep_url"].endswith(f"camera-{camera['id']}/whep")
    assert "operator" not in str(stream)
    assert "secret" not in str(stream)

    status_response = api_client.get(f"/api/v1/cameras/{camera['id']}/stream")
    assert status_response.status_code == 200
    assert status_response.json()["ready"] is True


def test_file_camera_gets_a_publisher_url(api_client: TestClient) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "demo-file", "source_uri": "artifacts/person-smoke.mp4"},
    ).json()

    stream = api_client.put(f"/api/v1/cameras/{camera['id']}/stream").json()

    assert stream["mode"] == "publisher"
    assert stream["publish_url"] == f"rtsp://127.0.0.1:8554/camera-{camera['id']}"


def test_managed_agent_requires_at_least_one_active_job(api_client: TestClient) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "camera-without-jobs", "source_uri": "webcam:0"},
    ).json()

    response = api_client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "running"},
    )

    assert response.status_code == 409
    assert "at least one rule" in response.json()["detail"]


def test_managed_agent_claim_telemetry_and_stop_lifecycle(
    api_client: TestClient,
) -> None:
    camera, zone, first_rule = create_active_rule(api_client)
    second_rule = api_client.post(
        "/api/v1/rules",
        json={
            "camera_id": camera["id"],
            "zone_id": zone["id"],
            "key": "truck-dwell",
            "name": "Truck remains in loading zone",
            "object_class": "truck",
            "duration_seconds": 5,
        },
    ).json()
    second_activation = api_client.patch(
        f"/api/v1/rules/{second_rule['id']}/status",
        json={"status": "active"},
    )
    assert second_activation.status_code == 200

    initial = api_client.get(f"/api/v1/cameras/{camera['id']}/agent")
    assert initial.json()["observed_status"] == "stopped"
    started = api_client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "running"},
    )
    assert started.status_code == 200
    assert started.json()["observed_status"] == "waiting"
    deployment_change = api_client.patch(
        f"/api/v1/rules/{first_rule['id']}/status",
        json={"status": "paused"},
    )
    assert deployment_change.status_code == 409
    assert "Stop the camera agent" in deployment_change.json()["detail"]

    unauthorized = api_client.post(
        "/api/v1/agent/assignments/claim", json={"worker_id": "edge-1"}
    )
    assert unauthorized.status_code == 401
    claim = api_client.post(
        "/api/v1/agent/assignments/claim",
        json={"worker_id": "edge-1"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert claim.status_code == 200
    assignment = claim.json()
    assert assignment["camera_id"] == camera["id"]
    assert assignment["analysis_source_uri"].endswith(f"camera-{camera['id']}")
    assert "operator" not in assignment["analysis_source_uri"]
    assert len(assignment["rules"]) == 2
    assert {rule["object_class"] for rule in assignment["rules"]} == {"person", "truck"}
    assert {rule["zone"]["name"] for rule in assignment["rules"]} == {"loading-zone"}

    telemetry = {
        "worker_id": "edge-1",
        "camera_id": camera["id"],
        "observed_status": "running",
        "fps": 14.5,
        "inference_latency_ms": 42.1,
        "frame_width": 1280,
        "frame_height": 720,
        "detections": [
            {
                "x1": 0.1,
                "y1": 0.2,
                "x2": 0.4,
                "y2": 0.8,
                "label": "person",
                "confidence": 0.93,
                "track_id": 7,
            }
        ],
        "analysis_state": "complete",
        "analysis_sequence": 4,
        "analysis_triggered": False,
        "analysis_confidence": 0.88,
        "analysis_summary": "No hard-hat violation is visible.",
        "analysis_requests_today": 4,
        "analysis_request_limit_day": 20,
        "analysis_request_limit_minute": 1,
        "frames_processed": 321,
        "reconnect_count": 2,
        "recording_state": "recording",
        "recording_segments_completed": 7,
        "recording_dropped_frames": 3,
    }
    with api_client.websocket_connect(
        f"/api/v1/ws/events?token={DASHBOARD_KEY}"
    ) as websocket:
        assert websocket.receive_json() == {"type": "connected"}
        heartbeat = api_client.post(
            "/api/v1/agent/telemetry",
            json=telemetry,
            headers={"X-Agent-Key": AGENT_KEY},
        )
        broadcast = websocket.receive_json()
    assert heartbeat.status_code == 200
    assert heartbeat.json()["observed_status"] == "running"
    assert heartbeat.json()["health_status"] == "healthy"
    assert heartbeat.json()["frames_processed"] == 321
    assert heartbeat.json()["reconnect_count"] == 2
    assert heartbeat.json()["recording_state"] == "recording"
    assert heartbeat.json()["recording_segments_completed"] == 7
    assert heartbeat.json()["recording_dropped_frames"] == 3
    assert heartbeat.json()["last_frame_at"] is not None
    assert (
        api_client.get(f"/api/v1/cameras/{camera['id']}").json()["status"] == "online"
    )
    assert broadcast["type"] == "agent.telemetry"
    assert broadcast["data"]["detections"][0]["track_id"] == 7
    assert broadcast["data"]["analysis_state"] == "complete"
    assert broadcast["data"]["analysis_requests_today"] == 4

    stopping = api_client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "stopped"},
    )
    assert stopping.json()["observed_status"] == "stopping"
    telemetry["observed_status"] = "stopped"
    telemetry["detections"] = []
    stopped = api_client.post(
        "/api/v1/agent/telemetry",
        json=telemetry,
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert stopped.json()["desired_status"] == "stopped"
    assert stopped.json()["observed_status"] == "stopped"
    assert stopped.json()["worker_id"] is None
    assert stopped.json()["health_status"] == "offline"
    assert (
        api_client.get(f"/api/v1/cameras/{camera['id']}").json()["status"] == "offline"
    )
    deployment_change = api_client.patch(
        f"/api/v1/rules/{first_rule['id']}/status",
        json={"status": "paused"},
    )
    assert deployment_change.status_code == 200


def test_failed_camera_uses_server_side_restart_backoff(api_client: TestClient) -> None:
    camera, _zone, _rule = create_active_rule(api_client)
    api_client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "running"},
    )
    claim = api_client.post(
        "/api/v1/agent/assignments/claim",
        json={"worker_id": "edge-1"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert claim.status_code == 200

    failed = api_client.post(
        "/api/v1/agent/telemetry",
        json={
            "worker_id": "edge-1",
            "camera_id": camera["id"],
            "observed_status": "error",
            "error": "RTSP reconnect budget exhausted",
        },
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert failed.status_code == 200
    assert failed.json()["health_status"] == "error"
    assert failed.json()["failure_count"] == 1
    assert failed.json()["next_retry_at"] is not None
    assert api_client.get(f"/api/v1/cameras/{camera['id']}").json()["status"] == "error"

    immediate_retry = api_client.post(
        "/api/v1/agent/assignments/claim",
        json={"worker_id": "edge-1"},
        headers={"X-Agent-Key": AGENT_KEY},
    )
    assert immediate_retry.status_code == 204

    api_client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "stopped"},
    )
    restarted = api_client.put(
        f"/api/v1/cameras/{camera['id']}/agent",
        json={"desired_status": "running"},
    )
    assert restarted.json()["failure_count"] == 0
    assert restarted.json()["next_retry_at"] is None
    assert (
        api_client.post(
            "/api/v1/agent/assignments/claim",
            json={"worker_id": "edge-1"},
            headers={"X-Agent-Key": AGENT_KEY},
        ).status_code
        == 200
    )
