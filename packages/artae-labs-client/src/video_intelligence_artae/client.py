import logging
import mimetypes
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import httpx

from video_intelligence_artae.config import ArtaeLabsSettings
from video_intelligence_artae.models import (
    LabsIndex,
    LabsVideo,
    SearchResponse,
    UploadTarget,
)

logger = logging.getLogger(__name__)

TERMINAL_SUCCESS_STATES = {"completed", "ready"}
TERMINAL_FAILURE_STATES = {"failed", "error"}


class ArtaeLabsError(RuntimeError):
    """Base error raised for expected Artae Labs integration failures."""


class ArtaeLabsRequestError(ArtaeLabsError):
    """Raised when an Artae Labs or presigned-upload request fails."""


class ArtaeLabsIndexingError(ArtaeLabsError):
    """Raised when asynchronous video indexing fails."""


class ArtaeLabsTimeoutError(ArtaeLabsError):
    """Raised when indexing does not finish within the configured timeout."""


class ArtaeLabsClient:
    """Small synchronous client for the Labs ingestion and search contract."""

    def __init__(
        self,
        settings: ArtaeLabsSettings,
        *,
        api_transport: httpx.BaseTransport | None = None,
        upload_transport: httpx.BaseTransport | None = None,
    ) -> None:
        base_url = settings.base_url.rstrip("/") + "/"
        api_key = settings.api_key.get_secret_value()
        self._settings = settings
        self._api = httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=settings.request_timeout_seconds,
            transport=api_transport,
        )
        # Presigned upload URLs point at object storage. This client deliberately
        # has no Labs authentication header, preventing credential leakage.
        self._uploads = httpx.Client(
            timeout=settings.request_timeout_seconds,
            transport=upload_transport,
        )

    def __enter__(self) -> "ArtaeLabsClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._api.close()
        self._uploads.close()

    def create_index(self, name: str, description: str | None = None) -> LabsIndex:
        payload: dict[str, str] = {"name": name}
        if description:
            payload["description"] = description
        response = self._request("POST", "indexes", json=payload)
        return LabsIndex.model_validate(response.json())

    def upload_video(
        self,
        *,
        index_id: str,
        video_path: Path | str,
        title: str | None = None,
        analysis_role: Literal["source", "reference_edit"] = "source",
    ) -> LabsVideo:
        path = Path(video_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Video file does not exist: {path}")

        content_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
        init_response = self._request(
            "POST",
            f"indexes/{index_id}/upload-init",
            json={
                "filename": path.name,
                "content_type": content_type,
                "size_bytes": path.stat().st_size,
            },
        )
        target = UploadTarget.model_validate(init_response.json())

        logger.info("Uploading video bytes to Artae Labs object storage: %s", path.name)
        upload_response = self._uploads.put(
            target.upload_url,
            headers={"Content-Type": content_type},
            content=_file_chunks(path),
        )
        if not upload_response.is_success:
            raise ArtaeLabsRequestError(
                f"Presigned upload failed with HTTP {upload_response.status_code}."
            )

        complete_response = self._request(
            "POST",
            f"indexes/{index_id}/upload-complete",
            json={
                "upload_key": target.upload_key,
                "title": title or path.stem,
                "analysis_role": analysis_role,
            },
        )
        video = LabsVideo.model_validate(complete_response.json())
        logger.info("Artae Labs accepted video %s with status=%s", video.id, video.status)
        return video

    def get_video(self, video_id: str) -> LabsVideo:
        response = self._request("GET", f"videos/{video_id}")
        return LabsVideo.model_validate(response.json())

    def wait_until_ready(
        self,
        video_id: str,
        *,
        poll_interval_seconds: float | None = None,
        timeout_seconds: float | None = None,
    ) -> LabsVideo:
        interval = (
            self._settings.poll_interval_seconds
            if poll_interval_seconds is None
            else poll_interval_seconds
        )
        timeout = (
            self._settings.indexing_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        if interval < 0:
            raise ValueError("poll_interval_seconds must be zero or greater.")
        if timeout <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        deadline = time.monotonic() + timeout
        last_status = "unknown"

        while time.monotonic() < deadline:
            video = self.get_video(video_id)
            last_status = video.status.lower()
            logger.info(
                "Artae Labs indexing: video=%s status=%s progress=%d%%",
                video.id,
                video.status,
                video.status_progress,
            )
            if last_status in TERMINAL_SUCCESS_STATES:
                return video
            if last_status in TERMINAL_FAILURE_STATES:
                raise ArtaeLabsIndexingError(
                    video.error_message or f"Indexing failed for video {video.id}."
                )
            time.sleep(interval)

        raise ArtaeLabsTimeoutError(
            f"Video {video_id} did not finish indexing within {timeout:.1f}s "
            f"(last status: {last_status})."
        )

    def search(
        self,
        *,
        index_id: str,
        query: str,
        modality: Literal[
            "visual",
            "audio",
            "transcription",
            "ocr",
            "semantic_event",
            "edit_anchor",
            "all",
        ] = "all",
        limit: int = 10,
        deep_listen: bool = False,
    ) -> SearchResponse:
        response = self._request(
            "POST",
            "search",
            json={
                "index_id": index_id,
                "query": query,
                "modality": modality,
                "limit": limit,
                "deep_listen": deep_listen,
            },
        )
        return SearchResponse.model_validate(response.json())

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._api.request(method, path.lstrip("/"), **kwargs)
        except httpx.HTTPError as exc:
            raise ArtaeLabsRequestError(f"Artae Labs request failed: {exc}") from exc

        if response.is_success:
            return response

        detail = _response_detail(response)
        raise ArtaeLabsRequestError(f"Artae Labs returned HTTP {response.status_code}: {detail}")


def _file_chunks(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            yield chunk


def _response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500] or response.reason_phrase
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body
        return str(detail)[:500]
    return str(body)[:500]
