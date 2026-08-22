import json
import threading

import httpx
import numpy as np
from video_intelligence_inference.config import Settings
from video_intelligence_inference.replay import ReplayInterval, ReplayOutput
from video_intelligence_inference.telemetry import FrameTelemetry, NormalizedDetection
from video_intelligence_inference.worker import (
    Assignment,
    ManagedReporter,
    assignment_config,
    run_worker,
)


def assignment_payload() -> dict:
    return {
        "worker_id": "edge-1",
        "camera_id": "camera-1",
        "camera_name": "Front door",
        "analysis_source_uri": "rtsp://127.0.0.1:8554/camera-camera-1",
        "rules": [
            {
                "id": "rule-1",
                "object_class": "person",
                "duration_seconds": 5,
                "minimum_confidence": 0.3,
                "absence_grace_seconds": 1,
                "zone": {
                    "name": "door",
                    "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
                },
            },
            {
                "id": "rule-2",
                "object_class": "truck",
                "duration_seconds": 10,
                "minimum_confidence": 0.4,
                "absence_grace_seconds": 1,
                "zone": {
                    "name": "yard",
                    "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}],
                },
            },
        ],
    }


def test_assignment_converts_to_existing_agent_configuration() -> None:
    config = assignment_config(Assignment.model_validate(assignment_payload()))

    assert config.camera_id == "camera-1"
    assert config.source_uri.endswith("camera-camera-1")
    assert [rule.rule_id for rule in config.rules] == ["rule-1", "rule-2"]
    assert config.rules[0].zone.name == "door"
    assert len(config.rules[0].zone.points) == 3


def test_assignment_prefers_direct_capture_when_it_also_publishes() -> None:
    assignment = Assignment.model_validate(
        assignment_payload()
        | {
            "capture_source_uri": "webcam:0",
            "publish_url": "rtsp://127.0.0.1:8554/camera-camera-1",
        }
    )

    config = assignment_config(assignment)

    assert config.source_uri == "webcam:0"
    assert assignment.publish_url == "rtsp://127.0.0.1:8554/camera-camera-1"


def test_reporter_sends_normalized_live_detections_off_the_frame_thread() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"desired_status": "running"})

    reporter = ManagedReporter(
        "http://control.test",
        "agent-secret",
        Assignment.model_validate(assignment_payload()),
        interval_seconds=0.1,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    reporter.starting()
    reporter.submit(
        FrameTelemetry(
            fps=12,
            inference_latency_ms=40,
            frame_width=640,
            frame_height=480,
            detections=(NormalizedDetection(0.1, 0.2, 0.4, 0.9, "person", 0.8, 2),),
            analysis_state="complete",
            analysis_sequence=3,
            analysis_triggered=False,
            analysis_confidence=0.91,
            analysis_summary="No person is missing required PPE.",
            analysis_requests_today=3,
            analysis_request_limit_day=20,
            analysis_request_limit_minute=1,
        )
    )
    reporter.finish("stopped")

    assert [request["observed_status"] for request in requests] == [
        "starting",
        "running",
        "stopped",
    ]
    assert requests[1]["detections"][0]["track_id"] == 2
    assert requests[1]["analysis_state"] == "complete"
    assert requests[1]["analysis_summary"] == "No person is missing required PPE."
    assert requests[1]["analysis_requests_today"] == 3


def test_reporter_uploads_bounded_jpeg_preview() -> None:
    previews: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/preview"):
            previews.append(request)
            return httpx.Response(204)
        return httpx.Response(200, json={"desired_status": "running"})

    reporter = ManagedReporter(
        "http://control.test",
        "agent-secret",
        Assignment.model_validate(assignment_payload()),
        interval_seconds=0.1,
        preview_fps=2,
        preview_width=320,
        preview_jpeg_quality=70,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    reporter.submit_preview(np.zeros((480, 640, 3), dtype=np.uint8))
    reporter.finish("stopped")

    assert len(previews) == 1
    assert previews[0].headers["content-type"] == "image/jpeg"
    assert previews[0].content.startswith(b"\xff\xd8")
    assert previews[0].content.endswith(b"\xff\xd9")


def test_worker_runs_two_camera_assignments_concurrently() -> None:
    assignments = [
        assignment_payload()
        | {"camera_id": f"camera-{index}", "camera_name": f"Camera {index}"}
        for index in (1, 2)
    ]
    claim_lock = threading.Lock()
    barrier = threading.Barrier(2)
    running_together: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Device-Token"] == "vid1.device.test-secret"
        if request.url.path.endswith("/assignments/claim"):
            with claim_lock:
                if assignments:
                    return httpx.Response(200, json=assignments.pop(0))
            return httpx.Response(204)
        if request.url.path.endswith("/evaluations/claim"):
            return httpx.Response(204)
        return httpx.Response(200, json={"desired_status": "running"})

    def camera_stub(settings: Settings, **kwargs: object) -> int:
        config = kwargs["resolved_config"]
        barrier.wait(timeout=2)
        running_together.append(config.camera_id)  # type: ignore[union-attr]
        return 1

    result = run_worker(
        Settings(
            control_plane_url="http://control.test",
            control_plane_device_token="vid1.device.test-secret",
            worker_id="edge-1",
            worker_max_cameras=2,
            worker_poll_seconds=0.25,
        ),
        max_assignments=2,
        transport=httpx.MockTransport(handler),
        run_camera=camera_stub,
    )

    assert result == 0
    assert set(running_together) == {"camera-1", "camera-2"}


def test_idle_worker_claims_and_reports_replay_evaluation() -> None:
    result_payloads: list[dict] = []
    heartbeat_payloads: list[dict] = []
    replay_claimed = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal replay_claimed
        if request.url.path.endswith("/assignments/claim"):
            return httpx.Response(204)
        if request.url.path.endswith("/evaluations/claim"):
            if replay_claimed:
                return httpx.Response(204)
            replay_claimed = True
            return httpx.Response(
                200,
                json={
                    "worker_id": "edge-1",
                    "evaluation_id": "evaluation-1",
                    "source_uri": "fixture.mp4",
                    "duration_seconds": 20,
                    "rule": Assignment.model_validate(assignment_payload())
                    .rules[0]
                    .model_dump(),
                },
            )
        if request.url.path.endswith("/result"):
            result_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={})
        if request.url.path.endswith("/heartbeat"):
            heartbeat_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={})
        return httpx.Response(404)

    def replay_stub(*_args, **kwargs) -> ReplayOutput:
        kwargs["on_progress"](0)
        kwargs["on_progress"](10)
        return ReplayOutput(
            intervals=(ReplayInterval(5, 8, detected_at_seconds=6, confidence=0.9),),
            provider_requests=2,
            input_tokens=1000,
            output_tokens=100,
        )

    result = run_worker(
        Settings(
            control_plane_url="http://control.test",
            control_plane_device_token="vid1.device.test-secret",
            worker_id="edge-1",
            worker_poll_seconds=0.25,
            replay_input_price_per_million_usd=0.1,
            replay_output_price_per_million_usd=0.5,
        ),
        max_assignments=1,
        transport=httpx.MockTransport(handler),
        run_replay_job=replay_stub,
    )

    assert result == 0
    assert result_payloads[0]["predicted_intervals"][0]["start_seconds"] == 5
    assert result_payloads[0]["provider_requests"] == 2
    assert result_payloads[0]["input_price_per_million_usd"] == 0.1
    assert [payload["processed_seconds"] for payload in heartbeat_payloads] == [0, 10]
