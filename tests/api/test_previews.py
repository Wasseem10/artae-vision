from fastapi.testclient import TestClient

AGENT_KEY = "test-agent-key-123456789"


def test_native_preview_upload_and_authenticated_read(api_client: TestClient) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "native-preview", "source_uri": "webcam:0"},
    ).json()
    jpeg = b"\xff\xd8small-jpeg-preview\xff\xd9"

    upload = api_client.put(
        f"/api/v1/agent/cameras/{camera['id']}/preview",
        content=jpeg,
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "image/jpeg"},
    )
    read = api_client.get(f"/api/v1/cameras/{camera['id']}/preview")

    assert upload.status_code == 204
    assert read.status_code == 200
    assert read.content == jpeg
    assert read.headers["content-type"] == "image/jpeg"
    assert read.headers["cache-control"] == "no-store, max-age=0"


def test_native_preview_rejects_non_jpeg_content(api_client: TestClient) -> None:
    camera = api_client.post(
        "/api/v1/cameras",
        json={"name": "bad-preview", "source_uri": "webcam:0"},
    ).json()

    response = api_client.put(
        f"/api/v1/agent/cameras/{camera['id']}/preview",
        content=b"not-an-image",
        headers={"X-Agent-Key": AGENT_KEY, "Content-Type": "image/jpeg"},
    )

    assert response.status_code == 400
    assert "valid JPEG" in response.json()["detail"]
