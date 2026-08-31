"""Add edge-executed ONVIF camera discovery runs.

Revision ID: 0023_camera_discovery
Revises: 0022_recording_archive
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0023_camera_discovery"
down_revision: str | None = "0022_recording_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camera_discovery_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("edge_device_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "COMPLETED",
                "FAILED",
                name="cameradiscoverystatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("devices", sa.JSON(), nullable=False),
        sa.Column("worker_id", sa.String(length=120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(length=1000)),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["edge_device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_camera_discovery_runs_organization_id",
        "camera_discovery_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_camera_discovery_runs_edge_device_id",
        "camera_discovery_runs",
        ["edge_device_id"],
    )
    op.create_index(
        "ix_camera_discovery_device_status",
        "camera_discovery_runs",
        ["edge_device_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_camera_discovery_device_status", table_name="camera_discovery_runs")
    op.drop_index("ix_camera_discovery_runs_edge_device_id", table_name="camera_discovery_runs")
    op.drop_index("ix_camera_discovery_runs_organization_id", table_name="camera_discovery_runs")
    op.drop_table("camera_discovery_runs")
