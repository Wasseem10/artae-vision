"""Non-blocking actions triggered by camera events."""

from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from types import TracebackType

import httpx
import imageio_ffmpeg

from video_intelligence_inference.events import EventRecord
from video_intelligence_inference.outbox import DurableJsonOutbox, OutboxRecord

logger = logging.getLogger(__name__)


class BackgroundWebhookDispatcher:
    """Deliver event JSON away from the time-sensitive frame-processing loop."""

    def __init__(
        self,
        webhook_url: str | None,
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        headers: Mapping[str, str] | None = None,
        outbox_path: Path | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._headers = dict(headers or {})
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._outbox = DurableJsonOutbox(outbox_path) if outbox_path else None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="webhook")
        self._futures: list[Future[None]] = []
        if self._outbox is not None:
            self._futures.append(self._executor.submit(self._flush_pending))

    def submit(self, event: EventRecord) -> None:
        if not self._webhook_url:
            return
        if self._outbox is not None:
            self._outbox.put(event.id, event.to_dict())
            future = self._executor.submit(self._flush_pending)
        else:
            future = self._executor.submit(self._deliver, event)
        future.add_done_callback(self._report_result)
        self._futures.append(future)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        self._client.close()

    def _deliver(self, event: EventRecord) -> None:
        response = self._client.post(
            self._webhook_url,
            json=event.to_dict(),
            headers=self._headers,
        )
        response.raise_for_status()
        logger.info("Webhook delivered: event=%s status=%d", event.id, response.status_code)

    def _flush_pending(self) -> None:
        if self._outbox is None or not self._webhook_url:
            return
        for record in self._outbox.pending():
            if not self._deliver_record(record):
                break

    def _deliver_record(self, record: OutboxRecord) -> bool:
        assert self._outbox is not None
        try:
            response = self._client.post(
                self._webhook_url,
                json=record.payload,
                headers=self._headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self._outbox.fail(record.record_id, str(exc))
            logger.warning(
                "Control-plane unavailable; event retained offline: event=%s attempts=%d",
                record.record_id,
                record.attempts + 1,
            )
            return False
        self._outbox.acknowledge(record.record_id)
        logger.info("Buffered event synchronized: event=%s", record.record_id)
        return True

    @staticmethod
    def _report_result(future: Future[None]) -> None:
        exception = future.exception()
        if exception is not None:
            logger.error("Webhook delivery failed: %s", exception)

    def __enter__(self) -> BackgroundWebhookDispatcher:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class BackgroundEvidenceUploader:
    """Upload completed MP4 clips after their event metadata reaches FastAPI."""

    def __init__(
        self,
        api_base_url: str | None,
        *,
        agent_key: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        transcode_clip: bool = True,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/") if api_base_url else None
        self._headers = dict(headers or {})
        if agent_key:
            self._headers.setdefault("X-Agent-Key", agent_key)
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._transcode_clip = transcode_clip
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evidence-upload")
        self._futures: list[Future[None]] = []

    def submit(self, event_id: str, path: Path, *, duration_seconds: float) -> None:
        if not self._api_base_url:
            return
        future = self._executor.submit(self._upload, event_id, path, duration_seconds)
        future.add_done_callback(self._report_result)
        self._futures.append(future)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        self._client.close()

    def _upload(self, event_id: str, path: Path, duration_seconds: float) -> None:
        url = f"{self._api_base_url}/agent/events/{event_id}/clip"
        headers = {
            **self._headers,
            "Content-Type": "video/mp4",
            "X-Evidence-Duration-Seconds": f"{duration_seconds:.3f}",
        }
        upload_path = _transcode_h264(path) if self._transcode_clip else path
        try:
            for attempt in range(5):
                with upload_path.open("rb") as clip:
                    response = self._client.put(url, headers=headers, content=clip)
                if response.status_code != 404:
                    response.raise_for_status()
                    logger.info(
                        "Evidence uploaded: event=%s bytes=%d",
                        event_id,
                        upload_path.stat().st_size,
                    )
                    return
                if attempt < 4:
                    time.sleep(0.2 * (2**attempt))
            response.raise_for_status()
        finally:
            if upload_path != path:
                upload_path.unlink(missing_ok=True)

    @staticmethod
    def _report_result(future: Future[None]) -> None:
        exception = future.exception()
        if exception is not None:
            logger.error("Evidence upload failed: %s", exception)

    def __enter__(self) -> BackgroundEvidenceUploader:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _transcode_h264(source: Path) -> Path:
    """Create a fast-start H.264 MP4 that modern browsers can seek and decode."""
    with tempfile.NamedTemporaryFile(
        prefix=f"{source.stem}-browser-",
        suffix=".mp4",
        dir=source.parent,
        delete=False,
    ) as temporary:
        target = Path(temporary.name)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(target),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target
