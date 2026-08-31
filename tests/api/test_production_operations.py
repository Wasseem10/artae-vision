from video_intelligence_api.config import ApiSettings

AGENT_KEY = "test-agent-key-123456789"


def test_production_readiness_explains_every_unfinished_requirement(api_client) -> None:
    response = api_client.get("/api/v1/production/readiness")

    assert response.status_code == 200
    report = response.json()
    assert report["ready"] is False
    assert report["environment"] == "test"
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["media_security"]["passed"] is True
    assert checks["object_storage"]["passed"] is False
    assert "retention" in report["blocking_checks"]
    assert all(item["guidance"] for item in report["checks"])


def test_internal_metrics_require_agent_auth_and_use_prometheus_format(
    api_client,
) -> None:
    assert api_client.get("/api/v1/agent/metrics").status_code == 401

    response = api_client.get(
        "/api/v1/agent/metrics",
        headers={"X-Agent-Key": AGENT_KEY},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "video_intelligence_cameras_total 0" in response.text
    assert "video_intelligence_cameras_error 0" in response.text
    assert "video_intelligence_agents_stale 0" in response.text
    assert "video_intelligence_camera_reconnects_total 0" in response.text
    assert "video_intelligence_recording_errors 0" in response.text
    assert "video_intelligence_recording_dropped_frames_total 0" in response.text
    assert "video_intelligence_recording_archive_ready 0" in response.text
    assert "video_intelligence_recording_legal_holds 0" in response.text
    assert "video_intelligence_camera_discovery_queued 0" in response.text
    assert "video_intelligence_edge_offline_queue_depth 0" in response.text


def test_hosted_readiness_configuration_can_be_completed() -> None:
    settings = ApiSettings(
        environment="production",
        database_url="postgresql+psycopg://service:secret@database/video",
        agent_key="production-agent-key-123",
        edge_auth_mode="device",
        dashboard_key="production-dashboard-key-123",
        dashboard_auth_mode="oidc",
        oidc_issuer="https://identity.test/",
        oidc_audience="video-api",
        oidc_jwks_url="https://identity.test/jwks.json",
        media_signing_key="production-media-signing-key-123456789",
        alert_encryption_key="production-alert-key",
        camera_encryption_key="production-camera-key",
        redis_url="rediss://redis.test/0",
        object_storage_endpoint="https://objects.test",
        object_storage_bucket="private-evidence",
        recording_storage_backend="s3",
        backup_target="backups/control-plane",
        retention_policy_configured=True,
        cors_origins=["https://console.test"],
    )
    assert settings.environment == "production"
    assert settings.retention_policy_configured is True
