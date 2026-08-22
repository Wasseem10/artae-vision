"""Add leased replay-run lifecycle fields.

Revision ID: 0010_replay_runner
Revises: 0009_replay_evaluations
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_replay_runner"
down_revision: str | None = "0009_replay_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("replay_evaluations") as batch_op:
        batch_op.add_column(sa.Column("worker_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_error", sa.String(length=1000)))


def downgrade() -> None:
    with op.batch_alter_table("replay_evaluations") as batch_op:
        batch_op.drop_column("last_error")
        batch_op.drop_column("started_at")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("worker_id")
