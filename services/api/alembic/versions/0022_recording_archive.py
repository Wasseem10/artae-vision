"""Add historical recording archive catalog.

Revision ID: 0022_recording_archive
Revises: 0021_camera_runtime_health
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_recording_archive"
down_revision: str | None = "0021_camera_runtime_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recording_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("edge_device_id", sa.String(length=36)),
        sa.Column("source_key", sa.String(length=200), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("frame_count", sa.BigInteger(), nullable=False),
        sa.Column("fps", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "LOCAL_ONLY",
                "READY",
                "EXPIRED",
                "FAILED",
                name="recordingsegmentstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("storage_uri", sa.String(length=2048)),
        sa.Column("media_type", sa.String(length=120)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("legal_hold", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edge_device_id"], ["edge_devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_id", "source_key", name="uq_recording_camera_source_key"),
    )
    op.create_index(
        "ix_recording_segments_organization_id",
        "recording_segments",
        ["organization_id"],
    )
    op.create_index("ix_recording_segments_camera_id", "recording_segments", ["camera_id"])
    op.create_index(
        "ix_recording_segments_edge_device_id",
        "recording_segments",
        ["edge_device_id"],
    )
    op.create_index(
        "ix_recording_segments_camera_started",
        "recording_segments",
        ["camera_id", "started_at"],
    )
    op.create_index(
        "ix_recording_segments_retention",
        "recording_segments",
        ["status", "legal_hold", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_recording_segments_retention", table_name="recording_segments")
    op.drop_index("ix_recording_segments_camera_started", table_name="recording_segments")
    op.drop_index("ix_recording_segments_edge_device_id", table_name="recording_segments")
    op.drop_index("ix_recording_segments_camera_id", table_name="recording_segments")
    op.drop_index("ix_recording_segments_organization_id", table_name="recording_segments")
    op.drop_table("recording_segments")
