from __future__ import annotations

import hashlib
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
    utc_now,
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


def _claimed_role(claims: dict[str, Any], claim_name: str) -> OrganizationRole:
    try:
        return OrganizationRole(str(claims.get(claim_name, "viewer")).lower())
    except ValueError:
        # Provider-level roles such as Supabase's `authenticated` are not application roles.
        return OrganizationRole.VIEWER


def _personal_workspace_details(
    issuer: str, subject: str, email: str | None, display_name: str | None
) -> tuple[str, str, str]:
    digest = hashlib.sha256(f"{issuer}\0{subject}".encode()).hexdigest()
    label = (display_name or (email.split("@", maxsplit=1)[0] if email else None) or "My")[:140]
    return f"workspace-{digest[:20]}", f"{label}'s workspace", f"oidc:{digest}"


async def get_current_actor(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDependency,
    x_dashboard_key: Annotated[str | None, Header()] = None,
) -> Actor:
    settings = request.app.state.settings
    expected = settings.dashboard_key.get_secret_value()
    development_key_valid = x_dashboard_key is not None and hmac.compare_digest(
        x_dashboard_key, expected
    )
    if settings.dashboard_auth_mode in {"development", "hybrid"} and development_key_valid:
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
    if settings.dashboard_auth_mode == "development":
        raise _unauthorized()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = await anyio.to_thread.run_sync(
            _decode_oidc_token, credentials.credentials, request.app
        )
        subject = str(claims["sub"])
    except (InvalidTokenError, PyJWKClientError, KeyError, ValueError) as exc:
        raise _unauthorized("Invalid or incomplete access token") from exc
    issuer = settings.oidc_issuer or ""
    email = str(claims["email"]) if claims.get("email") else None
    display_name = str(claims["name"]) if claims.get("name") else None
    identity = await session.scalar(
        select(UserIdentity).where(
            UserIdentity.issuer == issuer,
            UserIdentity.subject == subject,
        )
    )
    if identity is None:
        identity = UserIdentity(
            id=new_id(),
            issuer=issuer,
            subject=subject,
            email=email,
            display_name=display_name,
        )
        session.add(identity)
        await session.flush()
    else:
        identity.email = email or identity.email
        identity.display_name = display_name or identity.display_name
        identity.last_seen_at = utc_now()

    organization_claim = claims.get(settings.oidc_organization_claim)
    organization_id = str(organization_claim).strip() if organization_claim else ""
    membership: OrganizationMembership | None = None
    organization: Organization | None = None

    if organization_id:
        organization = await session.scalar(
            select(Organization).where(
                Organization.id == organization_id,
                Organization.enabled.is_(True),
            )
        )
        if organization is None:
            raise HTTPException(
                status_code=403, detail="Organization is not provisioned or enabled"
            )
    else:
        membership = await session.scalar(
            select(OrganizationMembership)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.user_id == identity.id,
                Organization.enabled.is_(True),
            )
            .order_by(OrganizationMembership.created_at.asc())
        )
        if membership is not None:
            organization_id = membership.organization_id

    if identity is not None:
        membership = membership or await session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == identity.id,
            )
        )

    if not organization_id:
        if not settings.oidc_auto_provision_organizations:
            raise HTTPException(status_code=403, detail="User does not have a workspace")
        slug, name, external_id = _personal_workspace_details(
            issuer, subject, identity.email, identity.display_name
        )
        organization = await session.scalar(
            select(Organization).where(Organization.external_id == external_id)
        )
        if organization is None:
            organization = Organization(
                id=new_id(), slug=slug, name=name, external_id=external_id, enabled=True
            )
            session.add(organization)
            await session.flush()
        organization_id = organization.id
        membership = OrganizationMembership(
            id=new_id(),
            organization_id=organization_id,
            user_id=identity.id,
            role=OrganizationRole.OWNER,
        )
        session.add(membership)

    if membership is None:
        if not settings.oidc_auto_provision_memberships:
            raise HTTPException(status_code=403, detail="User is not a member of this organization")
        membership = OrganizationMembership(
            id=new_id(),
            organization_id=organization_id,
            user_id=identity.id,
            role=_claimed_role(claims, settings.oidc_role_claim),
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
    if settings.dashboard_auth_mode in {"development", "hybrid"}:
        if not hmac.compare_digest(token, settings.dashboard_key.get_secret_value()):
            if settings.dashboard_auth_mode == "development":
                return None
        else:
            return Actor(
                subject="local-dashboard-operator",
                organization_id=settings.development_organization_id,
                role=OrganizationRole.OWNER,
                issuer="local-development",
            )
    try:
        claims = await anyio.to_thread.run_sync(_decode_oidc_token, token, websocket.app)
        issuer = settings.oidc_issuer or ""
        subject = str(claims["sub"])
        async with websocket.app.state.database.session_factory() as session:
            statement = (
                select(OrganizationMembership, UserIdentity)
                .join(UserIdentity, UserIdentity.id == OrganizationMembership.user_id)
                .join(Organization, Organization.id == OrganizationMembership.organization_id)
                .where(
                    UserIdentity.issuer == issuer,
                    UserIdentity.subject == subject,
                    Organization.enabled.is_(True),
                )
                .order_by(OrganizationMembership.created_at.asc())
            )
            organization_claim = claims.get(settings.oidc_organization_claim)
            if organization_claim:
                statement = statement.where(
                    OrganizationMembership.organization_id == str(organization_claim)
                )
            row = (await session.execute(statement)).first()
        if row is None:
            return None
        membership, identity = row
        return Actor(
            subject=subject,
            organization_id=membership.organization_id,
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
