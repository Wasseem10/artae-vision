import argparse
import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from video_intelligence_api.admin import create_organization, grant_membership
from video_intelligence_api.models import OrganizationMembership, UserIdentity

ORG_ID = "30000000-0000-0000-0000-000000000003"


def test_admin_cli_helpers_create_organization_and_membership(
    api_client: TestClient,
) -> None:
    database = api_client.app.state.database
    organization_args = argparse.Namespace(
        id=ORG_ID,
        slug="provisioned-org",
        name="Provisioned Organization",
        external_id="idp-org-3",
    )
    assert asyncio.run(create_organization(organization_args, database)) == 0

    membership_args = argparse.Namespace(
        organization_id=ORG_ID,
        issuer="https://identity.example.test/",
        subject="user-3",
        role="admin",
        email="user3@example.test",
        display_name="User Three",
    )
    assert asyncio.run(grant_membership(membership_args, database)) == 0

    async def read_membership() -> tuple[str, str]:
        async with database.session_factory() as session:
            membership, identity = (
                await session.execute(
                    select(OrganizationMembership, UserIdentity)
                    .join(
                        UserIdentity, UserIdentity.id == OrganizationMembership.user_id
                    )
                    .where(OrganizationMembership.organization_id == ORG_ID)
                )
            ).one()
            return membership.role.value, identity.email or ""

    assert asyncio.run(read_membership()) == ("admin", "user3@example.test")
