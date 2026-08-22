"""Bounded host supervisor for concurrently leased managed cameras."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import cv2
import httpx
import numpy as np
from pydantic import BaseModel, Field, ValidationError

from video_intelligence_inference.agent import run as run_agent
from video_intelligence_inference.config import Settings, get_settings
from video_intelligence_inference.control_credentials import control_plane_headers
from video_intelligence_inference.control_plane import ResolvedAgentConfig, resolve_rule_config
from video_intelligence_inference.hardware import collect_edge_profile
from video_intelligence_inference.logging_config import configure_logging
from video_intelligence_inference.replay import ReplayOutput, run_replay
from video_intelligence_inference.telemetry import FrameTelemetry

logger = logging.getLogger(__name__)


class WorkerError(RuntimeError):
    """Raised when the worker cannot communicate with its control plane."""


class _Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class _Zone(BaseModel):
    id: str = "legacy-zone"
    name: str
    geometry_type: str = "polygon"
    points: list[_Point] = Field(min_length=2)


class _Rule(BaseModel):
    id: str
    key: str = "legacy-job"
    rule_type: str = "object_dwell"
    object_class: str
    duration_seconds: float = Field(ge=0)
    minimum_confidence: float = Field(ge=0, le=1)
    absence_grace_seconds: float = Field(ge=0)
    zone: _Zone
    spec: dict[str, object] | None = None


class Assignment(BaseModel):
    worker_id: str
    camera_id: str
    camera_name: str
    analysis_source_uri: str
    capture_source_uri: str | None = None
    publish_url: str | None = None
    rules: list[_Rule] = Field(min_length=1)


class ReplayAssignment(BaseModel):
    worker_id: str
    evaluation_id: str
    source_uri: str
    duration_seconds: float = Field(gt=0)
    rule: dict[str, object]


def assignment_config(assignment: Assignment) -> ResolvedAgentConfig:
    return ResolvedAgentConfig(
        camera_id=assignment.camera_id,
        source_uri=assignment.capture_source_uri or assignment.analysis_source_uri,
        rules=tuple(resolve_rule_config(rule.model_dump()) for rule in assignment.rules),
    )


def _headers(
    agent_key: str | None,
    headers: Mapping[str, str] | None,
) -> dict[str, str]:
    resolved = dict(headers or {})
    if agent_key is not None:
        resolved.setdefault("X-Agent-Key", agent_key)
    return resolved


class ManagedReporter:
    """Send latest-only frame telemetry without blocking capture or inference."""

    def __init__(
        self,
        base_url: str,
        agent_key: str | None,
        assignment: Assignment,
        *,
        headers: Mapping[str, str] | None = None,
        interval_seconds: float,
        preview_fps: float = 2.0,
        preview_width: int = 960,
        preview_jpeg_quality: int = 75,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/api/v1/agent/telemetry"
        self._preview_url = (
            base_url.rstrip("/") + f"/api/v1/agent/cameras/{assignment.camera_id}/preview"
        )
        self._headers = _headers(agent_key, headers)
        self._assignment = assignment
        self._interval_seconds = interval_seconds
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="telemetry")
        self._future: Future[dict] | None = None
        self._last_submitted = 0.0
        self._preview_interval_seconds = 1.0 / preview_fps
        self._preview_width = preview_width
        self._preview_jpeg_quality = preview_jpeg_quality
        self._last_preview_submitted = 0.0
        self._preview_future: Future[None] | None = None
        self.stop_requested = threading.Event()

    def starting(self) -> None:
        self._send(self._payload("starting"))

    def submit(self, frame: FrameTelemetry) -> None:
        now = time.monotonic()
        if now - self._last_submitted < self._interval_seconds:
            return
        if self._future is not None and not self._future.done():
            return
        self._last_submitted = now
        payload = self._payload(
            "running",
            fps=frame.fps,
            inference_latency_ms=frame.inference_latency_ms,
            frame_width=frame.frame_width,
            frame_height=frame.frame_height,
            detections=[detection.to_dict() for detection in frame.detections],
            analysis_state=frame.analysis_state,
            analysis_sequence=frame.analysis_sequence,
            analysis_triggered=frame.analysis_triggered,
            analysis_confidence=frame.analysis_confidence,
            analysis_summary=frame.analysis_summary,
            analysis_error=frame.analysis_error,
            analysis_requests_today=frame.analysis_requests_today,
            analysis_request_limit_day=frame.analysis_request_limit_day,
            analysis_request_limit_minute=frame.analysis_request_limit_minute,
        )
        self._future = self._executor.submit(self._send, payload)
        self._future.add_done_callback(self._reported)

    def submit_preview(self, frame: np.ndarray) -> None:
        """Encode and upload a bounded latest-only JPEG without blocking on HTTP."""
        now = time.monotonic()
        if now - self._last_preview_submitted < self._preview_interval_seconds:
            return
        if self._preview_future is not None and not self._preview_future.done():
            return

        height, width = frame.shape[:2]
        if width > self._preview_width:
            target_height = max(1, round(height * self._preview_width / width))
            frame = cv2.resize(
                frame,
                (self._preview_width, target_height),
                interpolation=cv2.INTER_AREA,
            )
        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, self._preview_jpeg_quality],
        )
        if not success:
            logger.warning("Could not encode native camera preview")
            return

        self._last_preview_submitted = now
        self._preview_future = self._executor.submit(self._send_preview, encoded.tobytes())
        self._preview_future.add_done_callback(self._preview_reported)

    def finish(self, observed_status: str, error: str | None = None) -> None:
        self._executor.shutdown(wait=True)
        try:
            self._send(self._payload(observed_status, error=error))
        finally:
            self._client.close()

    def _payload(self, observed_status: str, **values: object) -> dict[str, object]:
        return {
            "worker_id": self._assignment.worker_id,
            "camera_id": self._assignment.camera_id,
            "observed_status": observed_status,
            "detections": [],
            **values,
        }

    def _send(self, payload: dict[str, object]) -> dict:
        response = self._client.post(self._url, json=payload, headers=self._headers)
        response.raise_for_status()
        body = response.json()
        if body.get("desired_status") == "stopped":
            self.stop_requested.set()
        return body

    def _send_preview(self, jpeg: bytes) -> None:
        response = self._client.put(
            self._preview_url,
            content=jpeg,
            headers={**self._headers, "Content-Type": "image/jpeg"},
        )
        response.raise_for_status()

    @staticmethod
    def _reported(future: Future[dict]) -> None:
        error = future.exception()
        if error is not None:
            logger.warning("Telemetry delivery failed: %s", error)

    @staticmethod
    def _preview_reported(future: Future[None]) -> None:
        error = future.exception()
        if error is not None:
            logger.warning("Preview delivery failed: %s", error)


@dataclass(slots=True)
class ActiveCamera:
    assignment: Assignment
    reporter: ManagedReporter
    future: Future[str]


def claim_assignment(
    client: httpx.Client,
    base_url: str,
    agent_key: str | None,
    worker_id: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> Assignment | None:
    response = client.post(
        base_url.rstrip("/") + "/api/v1/agent/assignments/claim",
        json={"worker_id": worker_id},
        headers=_headers(agent_key, headers),
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return Assignment.model_validate(response.json())


def claim_replay_assignment(
    client: httpx.Client,
    base_url: str,
    agent_key: str | None,
    worker_id: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> ReplayAssignment | None:
    response = client.post(
        base_url.rstrip("/") + "/api/v1/agent/evaluations/claim",
        json={"worker_id": worker_id},
        headers=_headers(agent_key, headers),
    )
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return ReplayAssignment.model_validate(response.json())


def report_replay_result(
    client: httpx.Client,
    base_url: str,
    assignment: ReplayAssignment,
    settings: Settings,
    *,
    headers: Mapping[str, str],
    output: ReplayOutput | None = None,
    error: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "worker_id": assignment.worker_id,
        "predicted_intervals": (
            [interval.to_dict() for interval in output.intervals] if output else []
        ),
        "provider_requests": output.provider_requests if output else 0,
        "input_tokens": output.input_tokens if output else 0,
        "output_tokens": output.output_tokens if output else 0,
        "input_price_per_million_usd": settings.replay_input_price_per_million_usd,
        "output_price_per_million_usd": settings.replay_output_price_per_million_usd,
        "error": error,
    }
    response = client.post(
        base_url.rstrip("/") + f"/api/v1/agent/evaluations/{assignment.evaluation_id}/result",
        json=payload,
        headers=headers,
    )
    response.raise_for_status()


def report_replay_progress(
    client: httpx.Client,
    base_url: str,
    assignment: ReplayAssignment,
    processed_seconds: float,
    *,
    headers: Mapping[str, str],
) -> None:
    response = client.post(
        base_url.rstrip("/") + f"/api/v1/agent/evaluations/{assignment.evaluation_id}/heartbeat",
        json={
            "worker_id": assignment.worker_id,
            "processed_seconds": processed_seconds,
        },
        headers=headers,
    )
    response.raise_for_status()


def _run_camera(
    settings: Settings,
    assignment: Assignment,
    reporter: ManagedReporter,
    run_camera: Callable[..., int],
) -> str:
    outcome = "stopped"
    failure: str | None = None
    try:
        reporter.starting()
        run_camera(
            settings,
            display=False,
            resolved_config=assignment_config(assignment),
            publish_url=assignment.publish_url,
            on_frame=reporter.submit,
            on_preview=reporter.submit_preview,
            should_stop=reporter.stop_requested.is_set,
        )
    except Exception as exc:
        outcome = "error"
        failure = str(exc)
        logger.exception("Managed camera failed: camera=%s", assignment.camera_id)
    try:
        reporter.finish(outcome, failure)
    except httpx.HTTPError:
        logger.exception("Could not report managed camera outcome: camera=%s", assignment.camera_id)
    return outcome


def run_worker(
    settings: Settings,
    *,
    once: bool = False,
    max_assignments: int | None = None,
    transport: httpx.BaseTransport | None = None,
    run_camera: Callable[..., int] = run_agent,
    run_replay_job: Callable[..., ReplayOutput] = run_replay,
) -> int:
    if settings.control_plane_url is None:
        raise WorkerError("VIDEO_INTEL_CONTROL_PLANE_URL is required")
    auth_headers = control_plane_headers(settings)
    if not auth_headers:
        raise WorkerError(
            "VIDEO_INTEL_CONTROL_PLANE_DEVICE_TOKEN is required; the agent key is local-only"
        )
    if once:
        max_assignments = 1
    base_url = str(settings.control_plane_url)
    worker_id = settings.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    capacity = settings.worker_max_cameras
    logger.info("Managed worker ready: worker=%s capacity=%d", worker_id, capacity)
    started = 0
    failed = 0
    active: dict[str, ActiveCamera] = {}
    executor = ThreadPoolExecutor(max_workers=capacity, thread_name_prefix="camera-agent")

    try:
        with httpx.Client(timeout=settings.webhook_timeout_seconds, transport=transport) as client:
            if settings.control_plane_device_token is not None:
                try:
                    profile_response = client.post(
                        base_url.rstrip("/") + "/api/v1/agent/fleet/profile",
                        json=collect_edge_profile(settings.offline_outbox_path),
                        headers=auth_headers,
                    )
                    profile_response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning("Could not report edge hardware profile: %s", exc)
            while True:
                for camera_id, task in list(active.items()):
                    if not task.future.done():
                        continue
                    if task.future.result() == "error":
                        failed += 1
                    del active[camera_id]

                if max_assignments is not None and started >= max_assignments and not active:
                    return 1 if failed else 0

                claim_failed = False
                claimed_any = False
                while len(active) < capacity and (
                    max_assignments is None or started < max_assignments
                ):
                    try:
                        assignment = claim_assignment(
                            client,
                            base_url,
                            None,
                            worker_id,
                            headers=auth_headers,
                        )
                    except httpx.HTTPError as exc:
                        logger.warning("Could not claim work: %s", exc)
                        claim_failed = True
                        break
                    if assignment is None:
                        break
                    if assignment.camera_id in active:
                        logger.error("Control plane returned a duplicate active camera lease")
                        break
                    logger.info(
                        "Claimed camera: camera=%s name=%s jobs=%d slot=%d/%d",
                        assignment.camera_id,
                        assignment.camera_name,
                        len(assignment.rules),
                        len(active) + 1,
                        capacity,
                    )
                    reporter = ManagedReporter(
                        base_url,
                        None,
                        assignment,
                        headers=auth_headers,
                        interval_seconds=settings.worker_telemetry_seconds,
                        preview_fps=settings.worker_preview_fps,
                        preview_width=settings.worker_preview_width,
                        preview_jpeg_quality=settings.worker_preview_jpeg_quality,
                        timeout_seconds=settings.webhook_timeout_seconds,
                        transport=transport,
                    )
                    future = executor.submit(
                        _run_camera,
                        settings,
                        assignment,
                        reporter,
                        run_camera,
                    )
                    active[assignment.camera_id] = ActiveCamera(assignment, reporter, future)
                    started += 1
                    claimed_any = True

                if (
                    not active
                    and not claimed_any
                    and not claim_failed
                    and (max_assignments is None or started < max_assignments)
                ):
                    try:
                        replay_assignment = claim_replay_assignment(
                            client,
                            base_url,
                            None,
                            worker_id,
                            headers=auth_headers,
                        )
                    except (httpx.HTTPError, ValidationError) as exc:
                        logger.warning("Could not claim replay work: %s", exc)
                        claim_failed = True
                    else:
                        if replay_assignment is not None:
                            started += 1
                            claimed_any = True
                            logger.info(
                                "Claimed replay evaluation: evaluation=%s source=%s",
                                replay_assignment.evaluation_id,
                                replay_assignment.source_uri,
                            )
                            try:
                                progress_step = max(1.0, replay_assignment.duration_seconds / 100)
                                last_reported_progress = -progress_step

                                def submit_replay_progress(
                                    processed_seconds: float,
                                    assignment: ReplayAssignment = replay_assignment,
                                    report_step: float = progress_step,
                                ) -> None:
                                    nonlocal last_reported_progress
                                    if processed_seconds - last_reported_progress < report_step:
                                        return
                                    report_replay_progress(
                                        client,
                                        base_url,
                                        assignment,
                                        processed_seconds,
                                        headers=auth_headers,
                                    )
                                    last_reported_progress = processed_seconds

                                replay_output = run_replay_job(
                                    settings,
                                    source_uri=replay_assignment.source_uri,
                                    duration_seconds=replay_assignment.duration_seconds,
                                    rule=resolve_rule_config(replay_assignment.rule),
                                    on_progress=submit_replay_progress,
                                )
                                report_replay_result(
                                    client,
                                    base_url,
                                    replay_assignment,
                                    settings,
                                    headers=auth_headers,
                                    output=replay_output,
                                )
                            except Exception as exc:
                                failed += 1
                                logger.exception(
                                    "Replay evaluation failed: evaluation=%s",
                                    replay_assignment.evaluation_id,
                                )
                                try:
                                    report_replay_result(
                                        client,
                                        base_url,
                                        replay_assignment,
                                        settings,
                                        headers=auth_headers,
                                        error=str(exc),
                                    )
                                except httpx.HTTPError:
                                    logger.exception(
                                        "Could not report replay failure: evaluation=%s",
                                        replay_assignment.evaluation_id,
                                    )

                if once and started == 0 and not active and not claim_failed:
                    return 0
                if claim_failed and once:
                    return 1
                if active or not claimed_any:
                    time.sleep(settings.worker_poll_seconds)
    finally:
        for task in active.values():
            task.reporter.stop_requested.set()
        executor.shutdown(wait=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claim cameras from FastAPI and run a bounded concurrent supervisor."
    )
    parser.add_argument("--once", action="store_true", help="Handle at most one claim")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = get_settings()
    except ValidationError as error:
        configure_logging("ERROR")
        logger.error("Invalid configuration:\n%s", error)
        return 2
    configure_logging(settings.log_level)
    try:
        return run_worker(settings, once=args.once)
    except (WorkerError, ValidationError) as error:
        logger.error("Worker configuration error: %s", error)
        return 2
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
