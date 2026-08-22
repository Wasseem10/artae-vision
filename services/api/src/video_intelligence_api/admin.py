from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from video_intelligence_api.config import get_api_settings
from video_intelligence_api.database import Database
from video_intelligence_api.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    UserIdentity,
    new_id,
)

logger = logging.getLogger(__name__)


async def create_organization(args: argparse.Namespace, database: Database) -> int:
    organization = Organization(
        id=args.id or new_id(),
        slug=args.slug,
        name=args.name,
        external_id=args.external_id,
    )
    async with database.session_factory() as session:
        session.add(organization)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.error("Organization ID, slug, or external ID already exists")
            return 1
    logger.info("Created organization: id=%s slug=%s", organization.id, organization.slug)
    return 0


async def grant_membership(args: argparse.Namespace, database: Database) -> int:
    async with database.session_factory() as session:
        organization = await session.get(Organization, args.organization_id)
        if organization is None:
            logger.error("Organization not found: %s", args.organization_id)
            return 1
        identity = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.issuer == args.issuer,
                UserIdentity.subject == args.subject,
            )
        )
        if identity is None:
            identity = UserIdentity(
                id=new_id(),
                issuer=args.issuer,
                subject=args.subject,
                email=args.email,
                display_name=args.display_name,
            )
            session.add(identity)
            await session.flush()
        membership = await session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == identity.id,
            )
        )
        role = OrganizationRole(args.role)
        if membership is None:
            membership = OrganizationMembership(
                id=new_id(),
                organization_id=organization.id,
                user_id=identity.id,
                role=role,
            )
            session.add(membership)
        else:
            membership.role = role
        await session.commit()
    logger.info(
        "Granted membership: organization=%s subject=%s role=%s",
        organization.id,
        identity.subject,
        membership.role.value,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision trusted identity records.")
    commands = parser.add_subparsers(dest="command", required=True)
    organization = commands.add_parser("create-organization")
    organization.add_argument("--id", help="Stable UUID placed in the OIDC org claim")
    organization.add_argument("--slug", required=True)
    organization.add_argument("--name", required=True)
    organization.add_argument("--external-id")
    membership = commands.add_parser("grant-membership")
    membership.add_argument("--organization-id", required=True)
    membership.add_argument("--issuer", required=True)
    membership.add_argument("--subject", required=True)
    membership.add_argument(
        "--role", choices=[role.value for role in OrganizationRole], required=True
    )
    membership.add_argument("--email")
    membership.add_argument("--display-name")
    return parser


async def run(args: argparse.Namespace) -> int:
    database = Database(get_api_settings().database_url)
    try:
        if args.command == "create-organization":
            return await create_organization(args, database)
        return await grant_membership(args, database)
    finally:
        await database.dispose()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
