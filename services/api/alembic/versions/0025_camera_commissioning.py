"""Add durable edge camera commissioning runs.

Revision ID: 0025_camera_commissioning
Revises: 0024_camera_onboarding
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_camera_commissioning"
down_revision: str | None = "0024_camera_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camera_commissioning_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("edge_device_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "PASSED",
                "NEEDS_ATTENTION",
                "FAILED",
                name="cameracommissioningstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("maximum_frames", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("readiness_score", sa.Integer()),
        sa.Column("worker_id", sa.String(length=120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(length=1000)),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edge_device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_camera_commissioning_runs_organization_id",
        "camera_commissioning_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_camera_commissioning_runs_camera_id", "camera_commissioning_runs", ["camera_id"]
    )
    op.create_index(
        "ix_camera_commissioning_runs_edge_device_id",
        "camera_commissioning_runs",
        ["edge_device_id"],
    )
    op.create_index(
        "ix_camera_commissioning_camera_created",
        "camera_commissioning_runs",
        ["camera_id", "created_at"],
    )
    op.create_index(
        "ix_camera_commissioning_device_status",
        "camera_commissioning_runs",
        ["edge_device_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_camera_commissioning_device_status", table_name="camera_commissioning_runs")
    op.drop_index("ix_camera_commissioning_camera_created", table_name="camera_commissioning_runs")
    op.drop_index(
        "ix_camera_commissioning_runs_edge_device_id", table_name="camera_commissioning_runs"
    )
    op.drop_index("ix_camera_commissioning_runs_camera_id", table_name="camera_commissioning_runs")
    op.drop_index(
        "ix_camera_commissioning_runs_organization_id", table_name="camera_commissioning_runs"
    )
    op.drop_table("camera_commissioning_runs")
