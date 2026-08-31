import base64

from fastapi.testclient import TestClient


def _setup(api_client: TestClient) -> tuple[dict, str, dict]:
    enrolled = api_client.post(
        "/api/v1/edge-devices",
        json={"name": "commissioning-edge", "max_concurrent_streams": 2},
    ).json()
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "commissioning-camera", "source_uri": "webcam:0"},
    ).json()
    return enrolled["device"], enrolled["token"], camera


def test_commissioning_scores_stream_and_publishes_verified_preview(
    api_client: TestClient,
) -> None:
    device, token, camera = _setup(api_client)
    created = api_client.post(
        "/api/v1/camera-commissioning-runs",
        json={"camera_id": camera["id"], "edge_device_id": device["id"]},
    )
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "queued"
    assert run["metrics"] is None

    claim = api_client.post(
        "/api/v1/agent/camera-commissioning-runs/claim",
        json={"worker_id": "quality-worker"},
        headers={"X-Device-Token": token},
    )
    assert claim.status_code == 200
    assert claim.json()["source_uri"] == "webcam:0"

    jpeg = b"\xff\xd8commissioning-preview\xff\xd9"
    result = api_client.post(
        f"/api/v1/agent/camera-commissioning-runs/{run['id']}/result",
        json={
            "worker_id": "quality-worker",
            "metrics": {
                "frame_count": 60,
                "read_failures": 0,
                "width": 1920,
                "height": 1080,
                "observed_fps": 20,
                "brightness_mean": 110,
                "contrast_mean": 45,
                "sharpness_mean": 180,
                "frozen_frame_ratio": 0.02,
                "black_frame_ratio": 0,
            },
            "preview_jpeg_base64": base64.b64encode(jpeg).decode(),
        },
        headers={"X-Device-Token": token},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "passed"
    assert body["readiness_score"] == 100
    assert body["findings"][0]["key"] == "quality"
    assert api_client.get(f"/api/v1/cameras/{camera['id']}/preview").content == jpeg


def test_commissioning_flags_dark_blurry_frozen_stream(api_client: TestClient) -> None:
    device, token, camera = _setup(api_client)
    run = api_client.post(
        "/api/v1/camera-commissioning-runs",
        json={"camera_id": camera["id"], "edge_device_id": device["id"]},
    ).json()
    api_client.post(
        "/api/v1/agent/camera-commissioning-runs/claim",
        json={"worker_id": "quality-worker"},
        headers={"X-Device-Token": token},
    )
    result = api_client.post(
        f"/api/v1/agent/camera-commissioning-runs/{run['id']}/result",
        json={
            "worker_id": "quality-worker",
            "metrics": {
                "frame_count": 30,
                "read_failures": 0,
                "width": 320,
                "height": 240,
                "observed_fps": 3,
                "brightness_mean": 8,
                "contrast_mean": 4,
                "sharpness_mean": 2,
                "frozen_frame_ratio": 1,
                "black_frame_ratio": 1,
            },
        },
        headers={"X-Device-Token": token},
    )
    body = result.json()
    assert body["status"] == "needs_attention"
    assert body["readiness_score"] == 0
    assert {finding["key"] for finding in body["findings"]} >= {
        "resolution",
        "fps",
        "dark",
        "blur",
        "frozen",
        "black_frames",
    }


def test_commissioning_enforces_one_run_and_exact_edge_identity(
    api_client: TestClient,
) -> None:
    device, token, camera = _setup(api_client)
    other = api_client.post(
        "/api/v1/edge-devices",
        json={"name": "other-commissioning-edge", "max_concurrent_streams": 1},
    ).json()
    payload = {"camera_id": camera["id"], "edge_device_id": device["id"]}
    run = api_client.post("/api/v1/camera-commissioning-runs", json=payload)
    assert run.status_code == 201
    assert (
        api_client.post("/api/v1/camera-commissioning-runs", json=payload).status_code
        == 409
    )

    wrong_claim = api_client.post(
        "/api/v1/agent/camera-commissioning-runs/claim",
        json={"worker_id": "wrong-edge-worker"},
        headers={"X-Device-Token": other["token"]},
    )
    assert wrong_claim.status_code == 204

    claim = api_client.post(
        "/api/v1/agent/camera-commissioning-runs/claim",
        json={"worker_id": "correct-edge-worker"},
        headers={"X-Device-Token": token},
    )
    assert claim.status_code == 200

    wrong_result = api_client.post(
        f"/api/v1/agent/camera-commissioning-runs/{run.json()['id']}/result",
        json={"worker_id": "correct-edge-worker", "error": "forged"},
        headers={"X-Device-Token": other["token"]},
    )
    assert wrong_result.status_code == 409
