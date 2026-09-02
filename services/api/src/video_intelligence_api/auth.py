from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, timedelta
from typing import Annotated, Any

import anyio
import jwt
from fastapi import Depends, Header, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _identity_for_claims(
    session: AsyncSession,
    *,
    issuer: str,
    subject: str,
    email: str | None,
    display_name: str | None,
) -> UserIdentity:
    """Create or refresh one OIDC identity without racing parallel page requests."""
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        now = utc_now()
        candidate = postgres_insert(UserIdentity).values(
            id=new_id(),
            issuer=issuer,
            subject=subject,
            email=email,
            display_name=display_name,
            created_at=now,
            last_seen_at=now,
        )
        statement = candidate.on_conflict_do_update(
            constraint="uq_user_identities_issuer_subject",
            set_={
                "email": func.coalesce(candidate.excluded.email, UserIdentity.email),
                "display_name": func.coalesce(
                    candidate.excluded.display_name, UserIdentity.display_name
                ),
                "last_seen_at": now,
            },
        ).returning(UserIdentity.id)
        identity_id = await session.scalar(statement)
        identity = await session.get(UserIdentity, identity_id)
        if identity is None:  # pragma: no cover - defensive guard for a broken DB transaction
            raise RuntimeError("OIDC identity upsert did not return a row")
        return identity

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
        if email and email != identity.email:
            identity.email = email
        if display_name and display_name != identity.display_name:
            identity.display_name = display_name
        # A page can make several authenticated polling requests per second.
        # Updating this row for every request serializes otherwise read-only
        # traffic on SQLite and can starve camera telemetry/event writes.
        now = utc_now()
        last_seen_at = identity.last_seen_at
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        if now - last_seen_at >= timedelta(minutes=1):
            identity.last_seen_at = now
    return identity


async def _personal_organization(
    session: AsyncSession, *, slug: str, name: str, external_id: str
) -> Organization:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        now = utc_now()
        candidate = postgres_insert(Organization).values(
            id=new_id(),
            slug=slug,
            name=name,
            external_id=external_id,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        organization_id = await session.scalar(
            candidate.on_conflict_do_update(
                index_elements=[Organization.external_id],
                set_={"enabled": True, "updated_at": now},
            ).returning(Organization.id)
        )
        organization = await session.get(Organization, organization_id)
        if organization is None:  # pragma: no cover - defensive guard
            raise RuntimeError("Personal workspace upsert did not return a row")
        return organization

    organization = await session.scalar(
        select(Organization).where(Organization.external_id == external_id)
    )
    if organization is None:
        organization = Organization(
            id=new_id(), slug=slug, name=name, external_id=external_id, enabled=True
        )
        session.add(organization)
        await session.flush()
    return organization


async def _membership_for_actor(
    session: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    role: OrganizationRole,
) -> OrganizationMembership:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        candidate = postgres_insert(OrganizationMembership).values(
            id=new_id(),
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            created_at=utc_now(),
        )
        membership_id = await session.scalar(
            candidate.on_conflict_do_nothing(
                constraint="uq_organization_memberships_member"
            ).returning(OrganizationMembership.id)
        )
        if membership_id is not None:
            membership = await session.get(OrganizationMembership, membership_id)
        else:
            membership = await session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id == user_id,
                )
            )
        if membership is None:  # pragma: no cover - defensive guard
            raise RuntimeError("Workspace membership upsert did not return a row")
        return membership

    membership = OrganizationMembership(
        id=new_id(),
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )
    session.add(membership)
    return membership


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

    identity = await _identity_for_claims(
        session,
        issuer=issuer,
        subject=subject,
        email=email,
        display_name=display_name,
    )

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
        organization = await _personal_organization(
            session, slug=slug, name=name, external_id=external_id
        )
        organization_id = organization.id
        membership = await _membership_for_actor(
            session,
            organization_id=organization_id,
            user_id=identity.id,
            role=OrganizationRole.OWNER,
        )

    if membership is None:
        if not settings.oidc_auto_provision_memberships:
            raise HTTPException(status_code=403, detail="User is not a member of this organization")
        membership = await _membership_for_actor(
            session,
            organization_id=organization_id,
            user_id=identity.id,
            role=_claimed_role(claims, settings.oidc_role_claim),
        )
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
