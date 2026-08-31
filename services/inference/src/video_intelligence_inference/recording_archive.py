"""Durable-enough background archive upload for completed edge recording segments."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import TracebackType

import httpx

from video_intelligence_inference.continuous_recording import SegmentManifest

logger = logging.getLogger(__name__)


class BackgroundRecordingArchiveUploader:
    """Spool and upload finalized recording segments without blocking inference."""

    def __init__(
        self,
        api_base_url: str | None,
        *,
        enabled: bool,
        headers: dict[str, str] | None,
        spool_directory: Path,
        timeout_seconds: float = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/") if api_base_url else None
        self._enabled = enabled and self._api_base_url is not None
        self._headers = dict(headers or {})
        self._spool_directory = spool_directory.expanduser().resolve()
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="recording-archive")
        self._futures: list[Future[None]] = []

    def __enter__(self) -> BackgroundRecordingArchiveUploader:
        if self._enabled:
            self._spool_directory.mkdir(parents=True, exist_ok=True)
            self._recover_spooled_uploads()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def submit(self, path: Path, manifest: SegmentManifest) -> None:
        if not self._enabled:
            return
        video_path = self._spool_directory / f"{manifest.segment_id}.mp4"
        manifest_path = self._spool_directory / f"{manifest.segment_id}.json"
        if not video_path.exists():
            try:
                os.link(path, video_path)
            except OSError:
                shutil.copy2(path, video_path)
        manifest_path.write_text(
            json.dumps(asdict(manifest), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._schedule(video_path, manifest_path, manifest)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        self._client.close()

    def _recover_spooled_uploads(self) -> None:
        for manifest_path in sorted(self._spool_directory.glob("*.json")):
            video_path = manifest_path.with_suffix(".mp4")
            if not video_path.is_file():
                logger.error("Recording spool manifest has no video: %s", manifest_path.name)
                continue
            try:
                manifest = SegmentManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.error("Invalid recording spool manifest %s: %s", manifest_path.name, exc)
                continue
            self._schedule(video_path, manifest_path, manifest)

    def _schedule(
        self,
        video_path: Path,
        manifest_path: Path,
        manifest: SegmentManifest,
    ) -> None:
        future = self._executor.submit(self._upload, video_path, manifest_path, manifest)
        future.add_done_callback(self._reported)
        self._futures.append(future)

    def _upload(
        self,
        video_path: Path,
        manifest_path: Path,
        manifest: SegmentManifest,
    ) -> None:
        assert self._api_base_url is not None
        duration_seconds = max(
            0.0,
            manifest.source_end_seconds - manifest.source_start_seconds,
        )
        payload = {
            "segment_id": manifest.segment_id,
            "source_key": manifest.source_key,
            "source_filename": manifest.filename,
            "started_at": manifest.started_at,
            "ended_at": manifest.completed_at,
            "duration_seconds": duration_seconds,
            "frame_count": manifest.frame_count,
            "fps": manifest.fps,
            "width": manifest.width,
            "height": manifest.height,
        }
        report_url = f"{self._api_base_url}/agent/cameras/{manifest.camera_id}/recordings"
        upload_url = f"{self._api_base_url}/agent/recordings/{manifest.segment_id}/content"
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                report = self._client.post(report_url, json=payload, headers=self._headers)
                report.raise_for_status()
                with video_path.open("rb") as video:
                    upload = self._client.put(
                        upload_url,
                        content=video,
                        headers={**self._headers, "Content-Type": "video/mp4"},
                    )
                upload.raise_for_status()
                video_path.unlink(missing_ok=True)
                manifest_path.unlink(missing_ok=True)
                logger.info(
                    "Recording archived: camera=%s segment=%s bytes=%d",
                    manifest.camera_id,
                    manifest.segment_id,
                    int(upload.json().get("size_bytes") or 0),
                )
                return
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt < 4:
                    time.sleep(0.5 * (2**attempt))
        assert last_error is not None
        raise last_error

    @staticmethod
    def _reported(future: Future[None]) -> None:
        error = future.exception()
        if error is not None:
            logger.error("Recording archive upload failed; spool retained: %s", error)
