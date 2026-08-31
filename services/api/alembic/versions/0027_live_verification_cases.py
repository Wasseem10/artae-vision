"""Add live proposer-verifier cases.

Revision ID: 0027_live_verification_cases
Revises: 0026_operational_health_incidents
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_live_verification_cases"
down_revision: str | None = "0026_operational_health_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    verification_status = sa.Enum(
        "NOT_REQUIRED",
        "PENDING",
        "CONFIRMED",
        "REJECTED",
        "UNCERTAIN",
        name="verificationstatus",
        native_enum=False,
    )
    with op.batch_alter_table("events") as batch:
        batch.add_column(
            sa.Column(
                "verification_status",
                verification_status,
                nullable=False,
                server_default="NOT_REQUIRED",
            )
        )
        batch.add_column(sa.Column("verified_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("verified_by", sa.String(length=255)))

    op.create_table(
        "verification_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("status", verification_status, nullable=False),
        sa.Column("proposer_model", sa.String(length=120)),
        sa.Column("verifier_model", sa.String(length=120)),
        sa.Column("proposer_confidence", sa.Float(), nullable=False),
        sa.Column("verifier_confidence", sa.Float()),
        sa.Column("proposal_summary", sa.String(length=1000), nullable=False),
        sa.Column("verifier_summary", sa.String(length=1000)),
        sa.Column("reasoning", sa.String(length=2000), nullable=False),
        sa.Column("decision_source", sa.String(length=40), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        "ix_verification_cases_organization_id",
        "verification_cases",
        ["organization_id"],
    )
    op.create_index(
        "ix_verification_cases_organization_status",
        "verification_cases",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_cases_organization_status",
        table_name="verification_cases",
    )
    op.drop_index(
        "ix_verification_cases_organization_id",
        table_name="verification_cases",
    )
    op.drop_table("verification_cases")
    with op.batch_alter_table("events") as batch:
        batch.drop_column("verified_by")
        batch.drop_column("verified_at")
        batch.drop_column("verification_status")
