"""Add non-secret connector configuration for Telegram chat routing.

Revision ID: 0019_telegram_connectors
Revises: 0018_edge_fleet
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_telegram_connectors"
down_revision: str | None = "0018_edge_fleet"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "integration_connectors",
        sa.Column(
            "configuration",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("integration_connectors", "configuration")
