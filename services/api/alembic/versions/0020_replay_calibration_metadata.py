"""Add replay calibration scenario and evidence-source metadata.

Revision ID: 0020_replay_calibration_metadata
Revises: 0019_telegram_connectors
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_replay_calibration_metadata"
down_revision: str | None = "0019_telegram_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "replay_evaluations",
        sa.Column("scenario_key", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "replay_evaluations",
        sa.Column(
            "scenario_variant",
            sa.String(length=20),
            nullable=False,
            server_default="unclassified",
        ),
    )
    op.add_column(
        "replay_evaluations",
        sa.Column(
            "source_kind",
            sa.String(length=20),
            nullable=False,
            server_default="unclassified",
        ),
    )
    op.add_column(
        "replay_evaluations",
        sa.Column(
            "environment_tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.create_index(
        "ix_replay_evaluations_scenario_source",
        "replay_evaluations",
        ["scenario_key", "source_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_replay_evaluations_scenario_source", table_name="replay_evaluations")
    op.drop_column("replay_evaluations", "environment_tags")
    op.drop_column("replay_evaluations", "source_kind")
    op.drop_column("replay_evaluations", "scenario_variant")
    op.drop_column("replay_evaluations", "scenario_key")
