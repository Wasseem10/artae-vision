"""Add versioned camera-job specs and generalized scene/event fields.

Revision ID: 0005_universal_event_engine
Revises: 0004_natural_language_rules
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_universal_event_engine"
down_revision: str | None = "0004_natural_language_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "zones",
        sa.Column(
            "geometry_type",
            sa.Enum("POLYGON", "LINE", name="geometrytype", native_enum=False),
            server_default="POLYGON",
            nullable=False,
        ),
    )
    op.add_column("rules", sa.Column("spec", sa.JSON(), nullable=True))
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(
            sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False)
        )
        batch_op.alter_column("track_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.alter_column("track_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("details")
    op.drop_column("rules", "spec")
    op.drop_column("zones", "geometry_type")
