import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.database import Base, Database
from video_intelligence_api.main import create_app
from video_intelligence_api.media_gateway import MediaGatewayClient
from video_intelligence_api.models import Organization

AGENT_KEY = "test-agent-key-123456789"
DASHBOARD_KEY = "test-dashboard-key-12345"
ALERT_ENCRYPTION_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
MEDIA_SIGNING_KEY = "test-media-signing-key-at-least-32-characters"
DEVELOPMENT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


async def create_schema(database: Database) -> None:
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with database.session_factory() as session:
        session.add(
            Organization(
                id=DEVELOPMENT_ORGANIZATION_ID,
                slug="local-development",
                name="Local Development",
            )
        )
        await session.commit()


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'control-plane.db').as_posix()}"
    settings = ApiSettings(
        environment="test",
        database_url=database_url,
        agent_key=AGENT_KEY,
        dashboard_key=DASHBOARD_KEY,
        alert_encryption_key=ALERT_ENCRYPTION_KEY,
        media_signing_key=MEDIA_SIGNING_KEY,
        evidence_directory=tmp_path / "evidence",
        recording_archive_directory=tmp_path / "recordings",
        recording_upload_max_bytes=1024,
        recording_retention_hours=1,
        replay_directory=tmp_path / "replays",
        replay_max_bytes=1024,
    )
    database = Database(database_url)
    asyncio.run(create_schema(database))
    configured_paths: dict[str, dict] = {}

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        path_name = path.rsplit("/", maxsplit=1)[-1]
        if path.startswith("/v3/config/paths/get/"):
            if path_name not in configured_paths:
                return httpx.Response(404)
            return httpx.Response(200, json=configured_paths[path_name])
        if path.startswith(("/v3/config/paths/add/", "/v3/config/paths/patch/")):
            configured_paths[path_name] = json.loads(request.content)
            return httpx.Response(200)
        if path.startswith("/v3/paths/get/"):
            if path_name not in configured_paths:
                return httpx.Response(404)
            return httpx.Response(
                200, json={"ready": True, "readers": [{"id": "reader-1"}]}
            )
        return httpx.Response(404)

    media_gateway = MediaGatewayClient(
        "http://media-gateway.test",
        transport=httpx.MockTransport(gateway_handler),
    )
    app = create_app(settings, database, media_gateway)
    with TestClient(app) as client:
        client.headers.update({"X-Dashboard-Key": DASHBOARD_KEY})
        yield client
