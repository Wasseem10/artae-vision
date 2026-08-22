"""Publish a finite MP4 to a camera's MediaMTX path with FFmpeg."""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import httpx

from video_intelligence_inference.logging_config import configure_logging

logger = logging.getLogger(__name__)


class PublisherError(RuntimeError):
    """Raised when the demo publisher cannot be configured or started."""


def build_ffmpeg_command(
    ffmpeg: str,
    source: Path,
    publish_url: str,
    *,
    loop: bool,
) -> list[str]:
    """Build an argument list without invoking a shell or interpolating commands."""
    command = [ffmpeg, "-hide_banner", "-loglevel", "warning"]
    if loop:
        command.extend(["-stream_loop", "-1"])
    command.extend(
        [
            "-re",
            "-i",
            str(source),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "30",
            "-f",
            "rtsp",
            "-rtsp_transport",
            "tcp",
            publish_url,
        ]
    )
    return command


def provision_publish_url(api_url: str, camera_id: str, timeout_seconds: float = 10) -> str:
    endpoint = f"{api_url.rstrip('/')}/api/v1/cameras/{quote(camera_id, safe='')}/stream"
    try:
        response = httpx.put(endpoint, timeout=timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PublisherError("Could not provision the camera stream through the API") from exc
    publish_url = response.json().get("publish_url")
    if not isinstance(publish_url, str) or not publish_url:
        raise PublisherError("This camera is an RTSP proxy and does not accept a file publisher")
    return publish_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Loop an MP4 into MediaMTX so the dashboard has a live test stream."
    )
    parser.add_argument("source", type=Path, help="MP4 file to publish")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--camera-id", help="Camera UUID registered in the control plane")
    target.add_argument("--publish-url", help="RTSP publisher URL returned by the API")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable or full path")
    parser.add_argument("--once", action="store_true", help="Stop at the end instead of looping")
    parser.add_argument("--log-level", default="INFO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level.upper())
    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise PublisherError(f"Video file does not exist: {source}")
    ffmpeg = shutil.which(args.ffmpeg) if Path(args.ffmpeg).name == args.ffmpeg else args.ffmpeg
    if not ffmpeg or not Path(ffmpeg).is_file():
        raise PublisherError(
            "FFmpeg was not found. Install it or pass --ffmpeg with its full path."
        )
    publish_url = args.publish_url or provision_publish_url(args.api_url, args.camera_id)
    command = build_ffmpeg_command(ffmpeg, source, publish_url, loop=not args.once)
    logger.info("Publishing %s to %s; press Ctrl+C to stop", source.name, publish_url)
    try:
        return subprocess.run(command, check=False).returncode
    except KeyboardInterrupt:
        logger.info("Publisher stopped")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
