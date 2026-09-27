"""Persist the latest successful operational-health evaluation.

Revision ID: 0032_operational_health_watchdog
Revises: 0031_health_outage_routes
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032_operational_health_watchdog"
down_revision: str | None = "0031_health_outage_routes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_health_watchdog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_successful_evaluation_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_operational_health_watchdog_singleton"),
    )


def downgrade() -> None:
    op.drop_table("operational_health_watchdog")
