from pathlib import Path

import httpx
import pytest
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.recording_storage import (
    RecordingStorageError,
    S3RecordingStorage,
    SupabaseRecordingStorage,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str, dict]] = []
        self.deletes: list[tuple[str, str]] = []

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict,
    ) -> None:
        self.uploads.append((filename, bucket, key, ExtraArgs))

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict,
        ExpiresIn: int,
    ) -> str:
        assert operation == "get_object"
        return (
            f"https://objects.test/{Params['Bucket']}/{Params['Key']}?ttl={ExpiresIn}"
        )

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.deletes.append((Bucket, Key))


def test_s3_recording_storage_upload_sign_and_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeS3Client()
    monkeypatch.setattr(
        "video_intelligence_api.recording_storage.boto3.client", lambda **_: fake
    )
    settings = ApiSettings(
        agent_key="test-agent-key-123456789",
        dashboard_key="test-dashboard-key-12345",
        recording_storage_backend="s3",
        object_storage_endpoint="https://objects.test",
        object_storage_bucket="private-video",
        object_storage_access_key="access-key",
        object_storage_secret_key="secret-key",
    )
    source = tmp_path / "segment.mp4"
    source.write_bytes(b"video")
    storage = S3RecordingStorage(settings)

    uri = storage.put(
        source,
        organization_id="org-1",
        camera_id="camera-1",
        recording_id="recording-1",
        media_type="video/mp4",
    )

    assert uri == "s3://private-video/recordings/org-1/camera-1/recording-1.mp4"
    assert fake.uploads[0][1:] == (
        "private-video",
        "recordings/org-1/camera-1/recording-1.mp4",
        {"ContentType": "video/mp4"},
    )
    assert storage.download_url(uri) == (
        "https://objects.test/private-video/recordings/org-1/camera-1/recording-1.mp4?ttl=300"
    )
    assert storage.delete(uri) is True
    assert fake.deletes == [
        ("private-video", "recordings/org-1/camera-1/recording-1.mp4")
    ]


def test_s3_storage_rejects_uri_from_another_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "video_intelligence_api.recording_storage.boto3.client",
        lambda **_: FakeS3Client(),
    )
    storage = S3RecordingStorage(
        ApiSettings(
            agent_key="test-agent-key-123456789",
            dashboard_key="test-dashboard-key-12345",
            recording_storage_backend="s3",
            object_storage_bucket="private-video",
        )
    )
    with pytest.raises(RecordingStorageError, match="outside the configured bucket"):
        storage.delete("s3://other-bucket/recording.mp4")


def test_supabase_recording_storage_upload_sign_and_delete(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "/object/sign/" in request.url.path:
            return httpx.Response(200, json={"signedURL": "/object/sign/private-video/clip?token=x"})
        return httpx.Response(200, json={"ok": True})

    settings = ApiSettings(
        agent_key="test-agent-key-123456789",
        dashboard_key="test-dashboard-key-12345",
        recording_storage_backend="supabase",
        object_storage_bucket="private-video",
        supabase_url="https://project.supabase.co",
        supabase_secret_key="server-secret-key",
    )
    storage = SupabaseRecordingStorage(settings)
    storage.client.close()
    storage.client = httpx.Client(
        base_url="https://project.supabase.co/storage/v1",
        transport=httpx.MockTransport(handler),
    )
    source = tmp_path / "segment.mp4"
    source.write_bytes(b"video")

    uri = storage.put(
        source,
        organization_id="org-1",
        camera_id="camera-1",
        recording_id="recording-1",
        media_type="video/mp4",
    )

    assert uri == "supabase://private-video/recordings/org-1/camera-1/recording-1.mp4"
    assert storage.download_url(uri) == (
        "https://project.supabase.co/storage/v1/object/sign/private-video/clip?token=x"
    )
    assert storage.delete(uri) is True
    assert [request.method for request in requests] == ["POST", "POST", "DELETE"]
