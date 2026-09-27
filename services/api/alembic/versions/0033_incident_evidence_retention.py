"""Add explicit retention and review state for incident evidence.

Revision ID: 0033_incident_evidence_retention
Revises: 0032_operational_health_watchdog
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_incident_evidence_retention"
down_revision: str | None = "0032_operational_health_watchdog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence_assets") as batch:
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("reviewed_by", sa.String(length=255)))
        batch.add_column(sa.Column("expired_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("retention_error", sa.String(length=1000)))
        batch.create_index(
            "ix_evidence_assets_retention", ["status", "legal_hold", "expires_at"]
        )


def downgrade() -> None:
    with op.batch_alter_table("evidence_assets") as batch:
        batch.drop_index("ix_evidence_assets_retention")
        batch.drop_column("retention_error")
        batch.drop_column("expired_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("reviewed_at")
        batch.drop_column("legal_hold")
        batch.drop_column("expires_at")
