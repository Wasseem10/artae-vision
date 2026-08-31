"""Private local and S3-compatible storage backends for historical recordings."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import boto3
import httpx
from botocore.client import Config

from video_intelligence_api.config import ApiSettings


class RecordingStorageError(RuntimeError):
    """Raised when recording content cannot be stored, read, or deleted."""


class RecordingStorage(Protocol):
    def put(
        self,
        source: Path,
        *,
        organization_id: str,
        camera_id: str,
        recording_id: str,
        media_type: str,
    ) -> str: ...

    def local_path(self, storage_uri: str) -> Path | None: ...

    def download_url(self, storage_uri: str) -> str | None: ...

    def delete(self, storage_uri: str) -> bool: ...


class LocalRecordingStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def put(
        self,
        source: Path,
        *,
        organization_id: str,
        camera_id: str,
        recording_id: str,
        media_type: str,
    ) -> str:
        del media_type
        directory = self.root / organization_id / camera_id
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{recording_id}.mp4"
        source.replace(destination)
        return str(destination)

    def local_path(self, storage_uri: str) -> Path | None:
        path = Path(storage_uri).expanduser().resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            return None
        return path

    def download_url(self, storage_uri: str) -> str | None:
        del storage_uri
        return None

    def delete(self, storage_uri: str) -> bool:
        path = self.local_path(storage_uri)
        if path is None:
            return False
        path.unlink()
        return True


class S3RecordingStorage:
    def __init__(self, settings: ApiSettings) -> None:
        if not settings.object_storage_bucket:
            raise RecordingStorageError("S3 recording storage requires an object-storage bucket")
        self.bucket = settings.object_storage_bucket
        self.presign_seconds = settings.object_storage_presign_seconds
        kwargs: dict[str, object] = {
            "service_name": "s3",
            "region_name": settings.object_storage_region,
            "config": Config(
                signature_version="s3v4",
                s3={
                    "addressing_style": (
                        "path" if settings.object_storage_force_path_style else "virtual"
                    )
                },
            ),
        }
        if settings.object_storage_endpoint:
            kwargs["endpoint_url"] = settings.object_storage_endpoint
        if settings.object_storage_access_key:
            kwargs["aws_access_key_id"] = settings.object_storage_access_key.get_secret_value()
        if settings.object_storage_secret_key:
            kwargs["aws_secret_access_key"] = settings.object_storage_secret_key.get_secret_value()
        if settings.object_storage_session_token:
            kwargs["aws_session_token"] = settings.object_storage_session_token.get_secret_value()
        self.client = boto3.client(**kwargs)

    def _key(self, organization_id: str, camera_id: str, recording_id: str) -> str:
        return f"recordings/{organization_id}/{camera_id}/{recording_id}.mp4"

    def _parse(self, storage_uri: str) -> str:
        parsed = urlsplit(storage_uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket or not parsed.path.strip("/"):
            raise RecordingStorageError("Recording object URI is outside the configured bucket")
        return parsed.path.lstrip("/")

    def put(
        self,
        source: Path,
        *,
        organization_id: str,
        camera_id: str,
        recording_id: str,
        media_type: str,
    ) -> str:
        key = self._key(organization_id, camera_id, recording_id)
        try:
            self.client.upload_file(
                str(source),
                self.bucket,
                key,
                ExtraArgs={"ContentType": media_type},
            )
        except Exception as exc:
            raise RecordingStorageError("Recording upload to object storage failed") from exc
        return f"s3://{self.bucket}/{key}"

    def local_path(self, storage_uri: str) -> Path | None:
        del storage_uri
        return None

    def download_url(self, storage_uri: str) -> str | None:
        key = self._parse(storage_uri)
        try:
            return str(
                self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=self.presign_seconds,
                )
            )
        except Exception as exc:
            raise RecordingStorageError("Recording playback URL could not be signed") from exc

    def delete(self, storage_uri: str) -> bool:
        key = self._parse(storage_uri)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise RecordingStorageError("Recording object could not be deleted") from exc
        return True


class SupabaseRecordingStorage:
    """Private Supabase Storage accessed only with a server-side secret key."""

    def __init__(self, settings: ApiSettings) -> None:
        if not settings.object_storage_bucket or not settings.supabase_url:
            raise RecordingStorageError("Supabase recording storage is incomplete")
        if settings.supabase_secret_key is None:
            raise RecordingStorageError("Supabase recording storage requires a server secret")
        self.bucket = settings.object_storage_bucket
        self.base_url = settings.supabase_url.rstrip("/")
        self.presign_seconds = settings.object_storage_presign_seconds
        secret = settings.supabase_secret_key.get_secret_value()
        self.client = httpx.Client(
            base_url=f"{self.base_url}/storage/v1",
            headers={"Authorization": f"Bearer {secret}", "apikey": secret},
            timeout=60,
        )

    def _key(self, organization_id: str, camera_id: str, recording_id: str) -> str:
        return f"recordings/{organization_id}/{camera_id}/{recording_id}.mp4"

    def _parse(self, storage_uri: str) -> str:
        parsed = urlsplit(storage_uri)
        if (
            parsed.scheme != "supabase"
            or parsed.netloc != self.bucket
            or not parsed.path.strip("/")
        ):
            raise RecordingStorageError("Recording object URI is outside the configured bucket")
        return parsed.path.lstrip("/")

    def put(
        self,
        source: Path,
        *,
        organization_id: str,
        camera_id: str,
        recording_id: str,
        media_type: str,
    ) -> str:
        key = self._key(organization_id, camera_id, recording_id)
        try:
            with source.open("rb") as content:
                response = self.client.post(
                    f"/object/{self.bucket}/{key}",
                    headers={"Content-Type": media_type, "x-upsert": "false"},
                    content=content,
                )
            response.raise_for_status()
        except Exception as exc:
            raise RecordingStorageError("Recording upload to Supabase Storage failed") from exc
        return f"supabase://{self.bucket}/{key}"

    def local_path(self, storage_uri: str) -> Path | None:
        del storage_uri
        return None

    def download_url(self, storage_uri: str) -> str | None:
        key = self._parse(storage_uri)
        try:
            response = self.client.post(
                f"/object/sign/{self.bucket}/{key}",
                json={"expiresIn": self.presign_seconds},
            )
            response.raise_for_status()
            signed_path = str(response.json()["signedURL"])
            if signed_path.startswith("http://") or signed_path.startswith("https://"):
                return signed_path
            return f"{self.base_url}/storage/v1{signed_path}"
        except Exception as exc:
            raise RecordingStorageError("Recording playback URL could not be signed") from exc

    def delete(self, storage_uri: str) -> bool:
        key = self._parse(storage_uri)
        try:
            response = self.client.delete(f"/object/{self.bucket}/{key}")
            response.raise_for_status()
        except Exception as exc:
            raise RecordingStorageError("Recording object could not be deleted") from exc
        return True


def recording_storage(settings: ApiSettings) -> RecordingStorage:
    if settings.recording_storage_backend == "supabase":
        return SupabaseRecordingStorage(settings)
    if settings.recording_storage_backend == "s3":
        return S3RecordingStorage(settings)
    return LocalRecordingStorage(settings.recording_archive_directory)
