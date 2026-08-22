"""Add durable managed camera-agent state.

Revision ID: 0002_managed_agents
Revises: 0001_control_plane
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_managed_agents"
down_revision: str | None = "0001_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camera_agents",
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column(
            "desired_status",
            sa.Enum("STOPPED", "RUNNING", name="agentdesiredstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "observed_status",
            sa.Enum(
                "STOPPED",
                "WAITING",
                "STARTING",
                "RUNNING",
                "STOPPING",
                "ERROR",
                name="agentobservedstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("inference_latency_ms", sa.Float(), nullable=True),
        sa.Column("frame_width", sa.Integer(), nullable=True),
        sa.Column("frame_height", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("camera_id"),
    )


def downgrade() -> None:
    op.drop_table("camera_agents")
