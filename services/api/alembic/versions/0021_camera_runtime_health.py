"""Add production camera runtime health and restart state.

Revision ID: 0021_camera_runtime_health
Revises: 0020_replay_calibration_metadata
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_camera_runtime_health"
down_revision: str | None = "0020_replay_calibration_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("camera_agents", sa.Column("last_frame_at", sa.DateTime(timezone=True)))
    op.add_column(
        "camera_agents",
        sa.Column("frames_processed", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "camera_agents",
        sa.Column("reconnect_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "camera_agents",
        sa.Column(
            "recording_state",
            sa.String(length=20),
            nullable=False,
            server_default="disabled",
        ),
    )
    op.add_column(
        "camera_agents",
        sa.Column(
            "recording_segments_completed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "camera_agents",
        sa.Column(
            "recording_dropped_frames",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("camera_agents", sa.Column("recording_error", sa.String(length=1000)))
    op.add_column(
        "camera_agents",
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("camera_agents", sa.Column("next_retry_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("camera_agents", "next_retry_at")
    op.drop_column("camera_agents", "failure_count")
    op.drop_column("camera_agents", "reconnect_count")
    op.drop_column("camera_agents", "recording_error")
    op.drop_column("camera_agents", "recording_dropped_frames")
    op.drop_column("camera_agents", "recording_segments_completed")
    op.drop_column("camera_agents", "recording_state")
    op.drop_column("camera_agents", "frames_processed")
    op.drop_column("camera_agents", "last_frame_at")
