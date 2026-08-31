import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Annotated

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Header
from fastapi.testclient import TestClient
from pydantic import ValidationError
from video_intelligence_api.auth import Actor, get_current_actor
from video_intelligence_api.config import ApiSettings
from video_intelligence_api.media_access import (
    evidence_signature_is_valid,
    signed_evidence_url,
)
from video_intelligence_api.models import Organization, OrganizationRole

ORG_A = "10000000-0000-0000-0000-000000000001"
ORG_B = "20000000-0000-0000-0000-000000000002"


def test_production_settings_fail_closed_without_oidc_and_signing_keys() -> None:
    with pytest.raises(ValidationError, match="Production requires OIDC"):
        ApiSettings(
            environment="production",
            agent_key="production-agent-key-123",
            dashboard_key="production-dashboard-key-123",
        )
    with pytest.raises(ValidationError, match="asymmetric allowlist"):
        ApiSettings(
            agent_key="development-agent-key-123",
            dashboard_key="development-dashboard-key-123",
            oidc_algorithms=["HS256"],
        )
    with pytest.raises(ValidationError, match="per-device edge authentication"):
        ApiSettings(
            environment="production",
            agent_key="production-agent-key-123",
            dashboard_key="production-dashboard-key-123",
            dashboard_auth_mode="oidc",
            oidc_issuer="https://identity.test/",
            oidc_audience="video-api",
            oidc_jwks_url="https://identity.test/jwks.json",
            media_signing_key="production-media-signing-key-123456789",
            alert_encryption_key="production-alert-key",
        )


async def seed_organizations(client: TestClient) -> None:
    database = client.app.state.database
    async with database.session_factory() as session:
        session.add_all(
            [
                Organization(id=ORG_A, slug="tenant-a", name="Tenant A"),
                Organization(id=ORG_B, slug="tenant-b", name="Tenant B"),
            ]
        )
        await session.commit()


def install_test_actor_override(client: TestClient) -> None:
    async def actor_override(
        x_test_organization: Annotated[str, Header()],
        x_test_role: Annotated[str, Header()] = "owner",
    ) -> Actor:
        return Actor(
            subject=f"test-user-{x_test_organization}",
            organization_id=x_test_organization,
            role=OrganizationRole(x_test_role),
            issuer="test-suite",
        )

    client.app.dependency_overrides[get_current_actor] = actor_override


def tenant_headers(organization_id: str, role: str = "owner") -> dict[str, str]:
    return {"X-Test-Organization": organization_id, "X-Test-Role": role}


def test_camera_and_child_resources_are_isolated_by_organization(
    api_client: TestClient,
) -> None:
    asyncio.run(seed_organizations(api_client))
    install_test_actor_override(api_client)
    try:
        camera_a = api_client.post(
            "/api/v1/cameras",
            headers=tenant_headers(ORG_A),
            json={"name": "front-door", "source_uri": "webcam:0"},
        ).json()
        assert camera_a["organization_id"] == ORG_A

        assert (
            api_client.get("/api/v1/cameras", headers=tenant_headers(ORG_B)).json()
            == []
        )
        hidden = api_client.get(
            f"/api/v1/cameras/{camera_a['id']}", headers=tenant_headers(ORG_B)
        )
        assert hidden.status_code == 404
        cross_tenant_zone = api_client.post(
            "/api/v1/zones",
            headers=tenant_headers(ORG_B),
            json={
                "camera_id": camera_a["id"],
                "name": "stolen-zone",
                "points": [
                    {"x": 0.1, "y": 0.1},
                    {"x": 0.9, "y": 0.1},
                    {"x": 0.9, "y": 0.9},
                ],
            },
        )
        assert cross_tenant_zone.status_code == 404

        same_name_b = api_client.post(
            "/api/v1/cameras",
            headers=tenant_headers(ORG_B),
            json={"name": "front-door", "source_uri": "webcam:0"},
        )
        assert same_name_b.status_code == 201
        assert same_name_b.json()["organization_id"] == ORG_B

        channel_a = api_client.post(
            "/api/v1/alert-channels",
            headers=tenant_headers(ORG_A),
            json={
                "name": "incident-system",
                "webhook_url": "https://tenant-a.example.test/hooks",
                "signing_secret": "tenant-a-signing-secret",
            },
        )
        assert channel_a.status_code == 201
        assert (
            api_client.get(
                "/api/v1/alert-channels", headers=tenant_headers(ORG_B)
            ).json()
            == []
        )
        channel_b = api_client.post(
            "/api/v1/alert-channels",
            headers=tenant_headers(ORG_B),
            json={
                "name": "incident-system",
                "webhook_url": "https://tenant-b.example.test/hooks",
                "signing_secret": "tenant-b-signing-secret",
            },
        )
        assert channel_b.status_code == 201
        operator_admin_denied = api_client.post(
            "/api/v1/alert-channels",
            headers=tenant_headers(ORG_A, "operator"),
            json={
                "name": "admin-only",
                "webhook_url": "https://tenant-a.example.test/admin",
                "signing_secret": "tenant-a-signing-secret",
            },
        )
        assert operator_admin_denied.status_code == 403
    finally:
        api_client.app.dependency_overrides.pop(get_current_actor, None)


def test_oidc_token_validation_and_viewer_write_denial(api_client: TestClient) -> None:
    asyncio.run(seed_organizations(api_client))
    settings = api_client.app.state.settings
    settings.dashboard_auth_mode = "oidc"
    settings.oidc_issuer = "https://identity.example.test/"
    settings.oidc_audience = "video-intelligence-api"
    settings.oidc_jwks_url = "https://identity.example.test/.well-known/jwks.json"
    settings.oidc_algorithms = ["RS256"]
    settings.oidc_auto_provision_memberships = True
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class StaticJwksClient:
        def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
            assert token
            return SimpleNamespace(key=private_key.public_key())

    api_client.app.state.oidc_jwks_client = StaticJwksClient()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "oidc-user-1",
            "org_id": ORG_A,
            "role": "viewer",
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    try:
        identity = api_client.get(
            "/api/v1/identity/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert identity.status_code == 200
        assert identity.json()["organization_id"] == ORG_A
        assert identity.json()["role"] == "viewer"

        denied = api_client.post(
            "/api/v1/cameras",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "viewer-camera", "source_uri": "webcam:0"},
        )
        assert denied.status_code == 403
        invalid = api_client.get(
            "/api/v1/identity/me", headers={"Authorization": "Bearer invalid-token"}
        )
        assert invalid.status_code == 401
        missing = api_client.get("/api/v1/identity/me", headers={"X-Dashboard-Key": ""})
        assert missing.status_code == 401
    finally:
        settings.dashboard_auth_mode = "development"
        settings.oidc_auto_provision_memberships = False
        del api_client.app.state.oidc_jwks_client


def test_oidc_signup_creates_and_reuses_a_personal_workspace(api_client: TestClient) -> None:
    settings = api_client.app.state.settings
    settings.dashboard_auth_mode = "oidc"
    settings.oidc_issuer = "https://project.supabase.test/auth/v1"
    settings.oidc_audience = "authenticated"
    settings.oidc_jwks_url = "https://project.supabase.test/auth/v1/.well-known/jwks.json"
    settings.oidc_algorithms = ["ES256"]
    settings.oidc_auto_provision_organizations = True
    private_key = ec.generate_private_key(ec.SECP256R1())

    class StaticJwksClient:
        def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
            assert token
            return SimpleNamespace(key=private_key.public_key())

    api_client.app.state.oidc_jwks_client = StaticJwksClient()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "supabase-user-1",
            "role": "authenticated",
            "email": "owner@example.com",
            "iss": settings.oidc_issuer,
            "aud": settings.oidc_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "test-key"},
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        first = api_client.get("/api/v1/identity/me", headers=headers)
        assert first.status_code == 200
        assert first.json()["role"] == "owner"
        assert first.json()["email"] == "owner@example.com"
        organization_id = first.json()["organization_id"]

        created = api_client.post(
            "/api/v1/cameras",
            headers=headers,
            json={"name": "Saved camera", "source_uri": "webcam:0"},
        )
        assert created.status_code == 201

        second = api_client.get("/api/v1/identity/me", headers=headers)
        assert second.status_code == 200
        assert second.json()["organization_id"] == organization_id
        cameras = api_client.get("/api/v1/cameras", headers=headers)
        assert cameras.status_code == 200
        assert [camera["name"] for camera in cameras.json()] == ["Saved camera"]
    finally:
        settings.dashboard_auth_mode = "development"
        settings.oidc_auto_provision_organizations = False
        del api_client.app.state.oidc_jwks_client


def test_signed_evidence_url_rejects_tampering_and_expiration(
    api_client: TestClient,
) -> None:
    settings = api_client.app.state.settings
    url = signed_evidence_url("evidence-1", ORG_A, settings)
    assert url is not None
    query = url.split("?", maxsplit=1)[1]
    values = dict(part.split("=", maxsplit=1) for part in query.split("&"))
    expires = int(values["expires"])
    signature = values["signature"]

    assert evidence_signature_is_valid(
        "evidence-1", ORG_A, expires, signature, settings
    )
    assert not evidence_signature_is_valid(
        "evidence-1", ORG_B, expires, signature, settings
    )
    assert not evidence_signature_is_valid(
        "evidence-2", ORG_A, expires, signature, settings
    )
    assert not evidence_signature_is_valid("evidence-1", ORG_A, 0, signature, settings)
