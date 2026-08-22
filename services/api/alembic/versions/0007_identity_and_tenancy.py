"""Add organizations, OIDC identities, memberships, and tenant ownership.

Revision ID: 0007_identity_and_tenancy
Revises: 0006_durable_alerts
Create Date: 2026-08-18
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0007_identity_and_tenancy"
down_revision: str | None = "0006_durable_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOCAL_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    now = datetime.now(UTC)
    organizations = op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
        sa.UniqueConstraint("slug"),
    )
    op.bulk_insert(
        organizations,
        [
            {
                "id": LOCAL_ORGANIZATION_ID,
                "slug": "local-development",
                "name": "Local Development",
                "external_id": None,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.create_table(
        "user_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "OWNER",
                "ADMIN",
                "OPERATOR",
                "VIEWER",
                name="organizationrole",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_identities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_memberships_member"
        ),
    )
    op.create_index(
        op.f("ix_organization_memberships_organization_id"),
        "organization_memberships",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_memberships_user_id"),
        "organization_memberships",
        ["user_id"],
        unique=False,
    )

    for table_name in ("cameras", "alert_channels", "evidence_searches"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "organization_id",
                    sa.String(length=36),
                    server_default=LOCAL_ORGANIZATION_ID,
                    nullable=False,
                )
            )
            batch_op.create_foreign_key(
                f"fk_{table_name}_organization_id",
                "organizations",
                ["organization_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_index(
                op.f(f"ix_{table_name}_organization_id"), ["organization_id"], unique=False
            )
            batch_op.alter_column("organization_id", server_default=None)

    naming_convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    dialect = op.get_bind().dialect.name
    with op.batch_alter_table(
        "cameras", naming_convention=naming_convention if dialect == "sqlite" else None
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_cameras_name" if dialect == "sqlite" else "cameras_name_key",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_cameras_organization_name", ["organization_id", "name"]
        )
    with op.batch_alter_table(
        "alert_channels", naming_convention=naming_convention if dialect == "sqlite" else None
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_alert_channels_name" if dialect == "sqlite" else "alert_channels_name_key",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_alert_channels_organization_name", ["organization_id", "name"]
        )


def downgrade() -> None:
    with op.batch_alter_table("alert_channels") as batch_op:
        batch_op.drop_constraint("uq_alert_channels_organization_name", type_="unique")
        batch_op.create_unique_constraint("uq_alert_channels_name", ["name"])
    with op.batch_alter_table("cameras") as batch_op:
        batch_op.drop_constraint("uq_cameras_organization_name", type_="unique")
        batch_op.create_unique_constraint("uq_cameras_name", ["name"])
    for table_name in ("evidence_searches", "alert_channels", "cameras"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(op.f(f"ix_{table_name}_organization_id"))
            batch_op.drop_constraint(f"fk_{table_name}_organization_id", type_="foreignkey")
            batch_op.drop_column("organization_id")
    op.drop_index(
        op.f("ix_organization_memberships_user_id"), table_name="organization_memberships"
    )
    op.drop_index(
        op.f("ix_organization_memberships_organization_id"),
        table_name="organization_memberships",
    )
    op.drop_table("organization_memberships")
    op.drop_table("user_identities")
    op.drop_table("organizations")
