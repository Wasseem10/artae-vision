"""Deterministic camera-stream quality assessment and remediation guidance."""

from dataclasses import dataclass
from typing import Literal

from video_intelligence_api.schemas import (
    CameraCommissioningFinding,
    CameraCommissioningMetrics,
)


@dataclass(frozen=True, slots=True)
class CommissioningAssessment:
    score: int
    ready: bool
    findings: tuple[CameraCommissioningFinding, ...]


def assess_camera(metrics: CameraCommissioningMetrics) -> CommissioningAssessment:
    score = 100
    findings: list[CameraCommissioningFinding] = []

    def add(
        key: str,
        severity: Literal["info", "warning", "error"],
        penalty: int,
        message: str,
        guidance: str,
    ) -> None:
        nonlocal score
        score -= penalty
        findings.append(
            CameraCommissioningFinding(
                key=key,
                severity=severity,
                message=message,
                guidance=guidance,
            )
        )

    if metrics.frame_count < 10:
        add(
            "frames",
            "error",
            45,
            "Too few frames were delivered.",
            "Check power, RTSP credentials, codec support, and network reachability.",
        )
    attempts = metrics.frame_count + metrics.read_failures
    if attempts and metrics.read_failures / attempts > 0.1:
        add(
            "delivery",
            "error",
            25,
            "The stream dropped more than 10% of sampled reads.",
            "Check camera bitrate, Wi-Fi signal, switch errors, and edge-to-camera packet loss.",
        )
    if metrics.width < 640 or metrics.height < 360:
        add(
            "resolution",
            "warning",
            20,
            "Resolution is below 640x360.",
            (
                "Select a higher-resolution ONVIF profile or move the camera closer "
                "to the monitored area."
            ),
        )
    if metrics.observed_fps < 5:
        add(
            "fps",
            "warning",
            15,
            "Observed frame rate is below 5 FPS.",
            "Increase camera frame rate or reduce network/decoder load before temporal tracking.",
        )
    if metrics.brightness_mean < 35:
        add(
            "dark",
            "error",
            25,
            "The scene is too dark for dependable visual decisions.",
            "Add lighting, enable the camera low-light mode, or reposition away from unlit areas.",
        )
    elif metrics.brightness_mean > 225:
        add(
            "overexposed",
            "warning",
            15,
            "The scene is strongly overexposed.",
            "Reduce exposure or reposition the camera away from direct light and reflections.",
        )
    if metrics.contrast_mean < 18:
        add(
            "contrast",
            "warning",
            12,
            "Scene contrast is very low.",
            (
                "Improve lighting direction or camera exposure so subjects separate "
                "from the background."
            ),
        )
    if metrics.sharpness_mean < 45:
        add(
            "blur",
            "warning",
            18,
            "Frames appear soft or blurred.",
            "Clean and refocus the lens, shorten exposure, or reduce camera vibration.",
        )
    if metrics.frozen_frame_ratio > 0.95:
        add(
            "frozen",
            "error",
            25,
            "Nearly every sampled frame was identical.",
            "Confirm the camera is sending live video rather than a frozen encoder frame.",
        )
    if metrics.black_frame_ratio > 0.2:
        add(
            "black_frames",
            "error",
            30,
            "More than 20% of sampled frames were effectively black.",
            "Check privacy masks, night mode, lens obstruction, and stream stability.",
        )
    score = max(0, min(100, score))
    ready = score >= 80 and not any(item.severity == "error" for item in findings)
    if not findings:
        findings.append(
            CameraCommissioningFinding(
                key="quality",
                severity="info",
                message="Stream delivery and basic image quality passed commissioning.",
                guidance=(
                    "Proceed to scenario-specific replay calibration before making accuracy claims."
                ),
            )
        )
    return CommissioningAssessment(score=score, ready=ready, findings=tuple(findings))
