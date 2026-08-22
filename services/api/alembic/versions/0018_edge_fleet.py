"""Add edge station profiles, signed config revisions, and update deployments.

Revision ID: 0018_edge_fleet
Revises: 0017_multicamera_sites
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_edge_fleet"
down_revision: str | None = "0017_multicamera_sites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edge_station_profiles",
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("os_name", sa.String(120), nullable=False),
        sa.Column("architecture", sa.String(80), nullable=False),
        sa.Column("cpu_count", sa.Integer(), nullable=False),
        sa.Column("memory_mb", sa.Integer(), nullable=False),
        sa.Column("accelerator", sa.String(255)),
        sa.Column("storage_available_mb", sa.Integer(), nullable=False),
        sa.Column("worker_version", sa.String(80), nullable=False),
        sa.Column("health_status", sa.String(20), nullable=False),
        sa.Column("offline_queue_depth", sa.Integer(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index(
        "ix_edge_station_profiles_organization_id",
        "edge_station_profiles",
        ["organization_id"],
    )
    op.create_table(
        "edge_config_bundles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "revision", name="uq_edge_config_device_revision"),
    )
    op.create_index(
        "ix_edge_config_bundles_organization_id",
        "edge_config_bundles",
        ["organization_id"],
    )
    op.create_index("ix_edge_config_bundles_device_id", "edge_config_bundles", ["device_id"])
    op.create_table(
        "edge_update_deployments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("from_version", sa.String(80), nullable=False),
        sa.Column("target_version", sa.String(80), nullable=False),
        sa.Column("rollback_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(1000)),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_edge_update_deployments_organization_id",
        "edge_update_deployments",
        ["organization_id"],
    )
    op.create_index(
        "ix_edge_update_deployments_device_id",
        "edge_update_deployments",
        ["device_id"],
    )
    op.create_index(
        "ix_edge_updates_device_created",
        "edge_update_deployments",
        ["device_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("edge_update_deployments")
    op.drop_table("edge_config_bundles")
    op.drop_table("edge_station_profiles")
