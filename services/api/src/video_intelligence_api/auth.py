from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated, Any

import anyio
import jwt
from fastapi import Depends, Header, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from sqlalchemy import select

from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    UserIdentity,
    new_id,
)

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Actor:
    subject: str
    organization_id: str
    role: OrganizationRole
    issuer: str
    email: str | None = None
    display_name: str | None = None


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_oidc_token(token: str, application: Any) -> dict[str, Any]:
    settings = application.state.settings
    if not settings.oidc_issuer or not settings.oidc_audience or not settings.oidc_jwks_url:
        raise _unauthorized("OIDC authentication is not fully configured")
    client = getattr(application.state, "oidc_jwks_client", None)
    if client is None:
        client = PyJWKClient(settings.oidc_jwks_url, cache_keys=True)
        application.state.oidc_jwks_client = client
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=settings.oidc_algorithms,
        audience=settings.oidc_audience,
        issuer=settings.oidc_issuer,
        options={"require": ["exp", "iat", "sub"]},
    )


async def get_current_actor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDependency,
    x_dashboard_key: Annotated[str | None, Header()] = None,
) -> Actor:
    settings = request.app.state.settings
    if settings.dashboard_auth_mode == "development":
        expected = settings.dashboard_key.get_secret_value()
        if x_dashboard_key is None or not hmac.compare_digest(x_dashboard_key, expected):
            raise _unauthorized()
        organization = await session.scalar(
            select(Organization).where(
                Organization.id == settings.development_organization_id,
                Organization.enabled.is_(True),
            )
        )
        if organization is None:
            raise HTTPException(status_code=403, detail="Development organization is unavailable")
        actor = Actor(
            subject="local-dashboard-operator",
            organization_id=settings.development_organization_id,
            role=OrganizationRole.OWNER,
            issuer="local-development",
        )
        request.state.actor = actor
        return actor

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = await anyio.to_thread.run_sync(
            _decode_oidc_token, credentials.credentials, request.app
        )
        subject = str(claims["sub"])
        organization_id = str(claims[settings.oidc_organization_claim])
        role = OrganizationRole(str(claims.get(settings.oidc_role_claim, "viewer")).lower())
    except (InvalidTokenError, PyJWKClientError, KeyError, ValueError) as exc:
        raise _unauthorized("Invalid or incomplete access token") from exc
    organization = await session.scalar(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.enabled.is_(True),
        )
    )
    if organization is None:
        raise HTTPException(status_code=403, detail="Organization is not provisioned or enabled")
    issuer = settings.oidc_issuer or ""
    identity = await session.scalar(
        select(UserIdentity).where(
            UserIdentity.issuer == issuer,
            UserIdentity.subject == subject,
        )
    )
    membership = None
    if identity is not None:
        membership = await session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == identity.id,
            )
        )
    if membership is None and not settings.oidc_auto_provision_memberships:
        raise HTTPException(status_code=403, detail="User is not a member of this organization")
    if identity is None:
        identity = UserIdentity(
            id=new_id(),
            issuer=issuer,
            subject=subject,
            email=str(claims["email"]) if claims.get("email") else None,
            display_name=str(claims["name"]) if claims.get("name") else None,
        )
        session.add(identity)
    if membership is None:
        membership = OrganizationMembership(
            id=new_id(),
            organization_id=organization_id,
            user_id=identity.id,
            role=role,
        )
        session.add(membership)
        await session.commit()
    actor = Actor(
        subject=subject,
        organization_id=organization_id,
        role=membership.role,
        issuer=issuer,
        email=identity.email,
        display_name=identity.display_name,
    )
    request.state.actor = actor
    return actor


async def authenticate_websocket(websocket: WebSocket, token: str | None) -> Actor | None:
    if token is None:
        return None
    settings = websocket.app.state.settings
    if settings.dashboard_auth_mode == "development":
        if not hmac.compare_digest(token, settings.dashboard_key.get_secret_value()):
            return None
        return Actor(
            subject="local-dashboard-operator",
            organization_id=settings.development_organization_id,
            role=OrganizationRole.OWNER,
            issuer="local-development",
        )
    try:
        claims = await anyio.to_thread.run_sync(_decode_oidc_token, token, websocket.app)
        organization_id = str(claims[settings.oidc_organization_claim])
        issuer = settings.oidc_issuer or ""
        subject = str(claims["sub"])
        async with websocket.app.state.database.session_factory() as session:
            row = (
                await session.execute(
                    select(OrganizationMembership, UserIdentity)
                    .join(UserIdentity, UserIdentity.id == OrganizationMembership.user_id)
                    .join(
                        Organization,
                        Organization.id == OrganizationMembership.organization_id,
                    )
                    .where(
                        OrganizationMembership.organization_id == organization_id,
                        UserIdentity.issuer == issuer,
                        UserIdentity.subject == subject,
                        Organization.enabled.is_(True),
                    )
                )
            ).first()
        if row is None:
            return None
        membership, identity = row
        return Actor(
            subject=subject,
            organization_id=organization_id,
            role=membership.role,
            issuer=issuer,
            email=identity.email,
            display_name=identity.display_name,
        )
    except (InvalidTokenError, PyJWKClientError, KeyError, ValueError):
        return None


async def require_editor(actor: Annotated[Actor, Depends(get_current_actor)]) -> Actor:
    if actor.role == OrganizationRole.VIEWER:
        raise HTTPException(status_code=403, detail="This action requires operator access")
    return actor


async def require_admin(actor: Annotated[Actor, Depends(get_current_actor)]) -> Actor:
    if actor.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise HTTPException(status_code=403, detail="This action requires administrator access")
    return actor


ActorDependency = Annotated[Actor, Depends(get_current_actor)]
EditorDependency = Annotated[Actor, Depends(require_editor)]
AdminDependency = Annotated[Actor, Depends(require_admin)]
