"""Add replay execution progress fields.

Revision ID: 0011_replay_upload_progress
Revises: 0010_replay_runner
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_replay_upload_progress"
down_revision: str | None = "0010_replay_runner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("replay_evaluations") as batch_op:
        batch_op.add_column(
            sa.Column("processed_seconds", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("last_progress_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("replay_evaluations") as batch_op:
        batch_op.drop_column("last_progress_at")
        batch_op.drop_column("progress_percent")
        batch_op.drop_column("processed_seconds")
