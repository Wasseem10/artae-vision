"""Non-blocking actions triggered by camera events."""

from __future__ import annotations

import logging
import math
import subprocess
import tempfile
import threading
import time
import uuid
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
        retry_interval_seconds: float = 5.0,
    ) -> None:
        if retry_interval_seconds <= 0:
            raise ValueError("Outbox retry interval must be positive")
        self._webhook_url = webhook_url
        self._headers = dict(headers or {})
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._outbox = DurableJsonOutbox(outbox_path) if outbox_path else None
        self._retry_interval_seconds = retry_interval_seconds
        self._claim_owner = uuid.uuid4().hex
        self._claim_lease_seconds = max(60.0, timeout_seconds * 6)
        self._retry_stop = threading.Event()
        self._retry_wake = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="webhook")
        self._futures: list[Future[None]] = []
        if self._outbox is not None and self._webhook_url:
            future = self._executor.submit(self._run_outbox_loop)
            future.add_done_callback(self._report_result)
            self._futures.append(future)

    def submit(self, event: EventRecord) -> None:
        if not self._webhook_url:
            return
        if self._outbox is not None:
            self._outbox.put(event.id, event.to_dict())
            self._retry_wake.set()
            return
        future = self._executor.submit(self._deliver, event)
        future.add_done_callback(self._report_result)
        self._futures.append(future)

    def close(self) -> None:
        self._retry_stop.set()
        self._retry_wake.set()
        self._executor.shutdown(wait=True)
        self._client.close()

    def _run_outbox_loop(self) -> None:
        """Retry the durable queue while idle, using the existing single executor worker."""
        while not self._retry_stop.is_set():
            self._retry_wake.clear()
            if self._retry_stop.is_set():
                return
            try:
                self._flush_pending()
            except Exception:
                logger.exception("Outbox flush failed; queued events will be retried")
            if self._retry_stop.is_set():
                return
            self._retry_wake.wait(self._retry_interval_seconds)

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
        for _ in range(100):
            if self._retry_stop.is_set():
                return
            claimed = self._outbox.claim_pending(
                self._claim_owner,
                lease_seconds=self._claim_lease_seconds,
            )
            if not claimed:
                return
            record = claimed[0]
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
            self._outbox.fail(
                record.record_id,
                str(exc),
                owner_id=self._claim_owner,
                retry_delay_seconds=self._retry_interval_seconds,
            )
            logger.warning(
                "Control-plane unavailable; event retained offline: event=%s attempts=%d",
                record.record_id,
                record.attempts + 1,
            )
            return False
        if not self._outbox.acknowledge(record.record_id, owner_id=self._claim_owner):
            logger.warning(
                "Delivered event was no longer leased by this worker: event=%s", record.record_id
            )
            return True
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
    """Upload completed MP4 clips; optionally spool jobs until FastAPI accepts them."""

    def __init__(
        self,
        api_base_url: str | None,
        *,
        agent_key: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        transcode_clip: bool = True,
        outbox_path: Path | None = None,
        clips_directory: Path | None = None,
        retention_hours: float | None = None,
        retry_interval_seconds: float = 5.0,
        retry_max_seconds: float = 300.0,
        claim_lease_seconds: float | None = None,
    ) -> None:
        if not math.isfinite(retry_interval_seconds) or retry_interval_seconds <= 0:
            raise ValueError("Evidence retry interval must be finite and positive")
        if not math.isfinite(retry_max_seconds) or retry_max_seconds < retry_interval_seconds:
            raise ValueError("Evidence retry maximum must be at least the retry interval")
        if retention_hours is not None:
            if not math.isfinite(retention_hours) or retention_hours <= 0:
                raise ValueError("Evidence retention must be finite and positive")
            if outbox_path is None or clips_directory is None:
                raise ValueError("Evidence retention requires an outbox and clips directory")
        self._api_base_url = api_base_url.rstrip("/") if api_base_url else None
        self._headers = dict(headers or {})
        if agent_key:
            self._headers.setdefault("X-Agent-Key", agent_key)
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)
        self._transcode_clip = transcode_clip
        self._outbox = DurableJsonOutbox(outbox_path) if outbox_path else None
        self._clips_directory = clips_directory
        self._retention_hours = retention_hours
        self._retry_interval_seconds = retry_interval_seconds
        self._retry_max_seconds = retry_max_seconds
        self._claim_owner = uuid.uuid4().hex
        self._claim_lease_seconds = (
            claim_lease_seconds
            if claim_lease_seconds is not None
            else max(120.0, timeout_seconds * 4)
        )
        if not math.isfinite(self._claim_lease_seconds) or self._claim_lease_seconds <= 0:
            raise ValueError("Evidence claim lease must be finite and positive")
        self._retry_stop = threading.Event()
        self._retry_wake = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evidence-upload")
        self._futures: list[Future[None]] = []
        if self._outbox is not None and self._api_base_url:
            pending = self._outbox.count()
            if pending:
                logger.info("Recovering queued evidence uploads: pending=%d", pending)
            future = self._executor.submit(self._run_outbox_loop)
            future.add_done_callback(self._report_result)
            self._futures.append(future)

    def submit(self, event_id: str, path: Path, *, duration_seconds: float) -> None:
        if not self._api_base_url:
            return
        if not math.isfinite(duration_seconds) or duration_seconds < 0:
            raise ValueError("Evidence duration must be finite and nonnegative")
        if self._outbox is not None:
            self._outbox.put(
                event_id,
                {
                    "event_id": event_id,
                    "path": str(path.expanduser().resolve()),
                    "duration_seconds": duration_seconds,
                },
            )
            self._retry_wake.set()
            return
        future = self._executor.submit(self._upload, event_id, path, duration_seconds)
        future.add_done_callback(self._report_result)
        self._futures.append(future)

    def close(self) -> None:
        self._retry_stop.set()
        self._retry_wake.set()
        self._executor.shutdown(wait=True)
        self._client.close()

    def _run_outbox_loop(self) -> None:
        last_prune_at = float("-inf")
        while not self._retry_stop.is_set():
            self._retry_wake.clear()
            if self._retry_stop.is_set():
                return
            try:
                self._flush_pending()
            except Exception:
                logger.exception("Evidence upload queue failed; queued clips will be retried")
            if self._retention_hours is not None and time.monotonic() - last_prune_at >= 60:
                try:
                    assert self._outbox is not None and self._clips_directory is not None
                    removed = self._outbox.prune_acknowledged_evidence(
                        self._clips_directory, retention_hours=self._retention_hours
                    )
                    if removed:
                        logger.info("Pruned acknowledged incident clips: count=%d", removed)
                except Exception:
                    logger.exception("Evidence retention sweep failed; clips were kept")
                finally:
                    last_prune_at = time.monotonic()
            if self._retry_stop.is_set():
                return
            self._retry_wake.wait(self._retry_interval_seconds)

    def _flush_pending(self) -> None:
        if self._outbox is None or not self._api_base_url:
            return
        for _ in range(100):
            if self._retry_stop.is_set():
                return
            claimed = self._outbox.claim_pending(
                self._claim_owner,
                lease_seconds=self._claim_lease_seconds,
            )
            if not claimed:
                return
            if not self._upload_claimed(claimed[0]):
                return

    def _upload_claimed(self, record: OutboxRecord) -> bool:
        assert self._outbox is not None
        event_id = record.record_id
        source = Path(str(record.payload["path"]))
        duration_seconds = float(record.payload["duration_seconds"])
        renewal_stop = threading.Event()
        claim_lost = threading.Event()
        renewal = threading.Thread(
            target=self._renew_claim,
            args=(event_id, renewal_stop, claim_lost),
            name="evidence-lease-renewal",
            daemon=True,
        )
        renewal.start()
        upload_path: Path | None = None
        error: Exception | None = None
        try:
            upload_path = self._cached_h264(source) if self._transcode_clip else source
            if claim_lost.is_set():
                raise RuntimeError("Evidence upload claim was lost during transcoding")
            self._put_clip(event_id, upload_path, duration_seconds)
        except (
            httpx.HTTPError,
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            RuntimeError,
            ValueError,
        ) as exc:
            error = exc
        finally:
            renewal_stop.set()
            renewal.join()

        if claim_lost.is_set():
            logger.error("Evidence upload claim lost: event=%s", event_id)
            return False
        if error is not None:
            delay = min(
                self._retry_max_seconds,
                self._retry_interval_seconds * (2 ** min(record.attempts, 10)),
            )
            self._outbox.fail(
                event_id,
                str(error),
                owner_id=self._claim_owner,
                retry_delay_seconds=delay,
            )
            logger.warning(
                "Evidence upload deferred: event=%s attempts=%d pending=%d retry_in=%.1fs error=%s",
                event_id,
                record.attempts + 1,
                self._outbox.count(),
                delay,
                error,
            )
            return False
        try:
            acknowledged = self._outbox.acknowledge_evidence(
                event_id,
                source,
                owner_id=self._claim_owner,
                cache_path=upload_path if upload_path != source else None,
            )
        except FileNotFoundError:
            # The API accepted the bytes, but the local source disappeared before
            # we could record an immutable cleanup receipt. Clear the accepted
            # queue job without claiming that any local file is safe to delete.
            acknowledged = self._outbox.acknowledge(event_id, owner_id=self._claim_owner)
            logger.error(
                "Evidence source disappeared after API acceptance: event=%s path=%s",
                event_id,
                source,
            )
        except OSError:
            logger.exception(
                "Evidence uploaded but source receipt could not be saved: event=%s", event_id
            )
            return False
        if not acknowledged:
            logger.warning("Evidence upload succeeded after claim changed: event=%s", event_id)
            return False
        if upload_path is not None and upload_path != source:
            try:
                upload_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Evidence upload cache cleanup failed: event=%s", event_id)
        logger.info("Evidence uploaded: event=%s", event_id)
        return True

    def _renew_claim(
        self,
        event_id: str,
        renewal_stop: threading.Event,
        claim_lost: threading.Event,
    ) -> None:
        assert self._outbox is not None
        interval = min(10.0, self._claim_lease_seconds / 3)
        while not renewal_stop.wait(interval):
            try:
                held = self._outbox.renew_claim(
                    event_id,
                    self._claim_owner,
                    lease_seconds=self._claim_lease_seconds,
                )
            except Exception:
                logger.exception("Evidence claim renewal failed: event=%s", event_id)
                claim_lost.set()
                return
            if not held:
                claim_lost.set()
                return

    def _cached_h264(self, source: Path) -> Path:
        target = source.with_name(f"{source.stem}.upload.mp4")
        if target.is_file() and target.stat().st_size > 0:
            return target
        temporary = _transcode_h264(source)
        temporary.replace(target)
        return target

    def _put_clip(self, event_id: str, path: Path, duration_seconds: float) -> None:
        assert self._api_base_url is not None
        url = f"{self._api_base_url}/agent/events/{event_id}/clip"
        headers = {
            **self._headers,
            "Content-Type": "video/mp4",
            "X-Evidence-Duration-Seconds": f"{duration_seconds:.3f}",
        }
        with path.open("rb") as clip:
            response = self._client.put(url, headers=headers, content=clip)
        response.raise_for_status()

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
        subprocess.run(command, check=True, capture_output=True, timeout=600)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target
