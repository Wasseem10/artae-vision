"""Add self-resolving operational health incidents.

Revision ID: 0026_operational_health_incidents
Revises: 0025_camera_commissioning
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_operational_health_incidents"
down_revision: str | None = "0025_camera_commissioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_health_incidents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36)),
        sa.Column("edge_device_id", sa.String(length=36)),
        sa.Column(
            "resource_type",
            sa.Enum(
                "CAMERA",
                "EDGE_DEVICE",
                name="operationalhealthresource",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("condition", sa.String(length=80), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "WARNING",
                "CRITICAL",
                name="operationalhealthseverity",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "ACKNOWLEDGED",
                "RESOLVED",
                name="alertstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("active_key", sa.String(length=255)),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("detail", sa.String(length=1000), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by", sa.String(length=255)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(camera_id IS NOT NULL AND edge_device_id IS NULL) OR "
            "(camera_id IS NULL AND edge_device_id IS NOT NULL)",
            name="ck_operational_health_one_resource",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edge_device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "active_key",
            name="uq_operational_health_active_key",
        ),
    )
    op.create_index(
        "ix_operational_health_incidents_organization_id",
        "operational_health_incidents",
        ["organization_id"],
    )
    op.create_index(
        "ix_operational_health_incidents_camera_id",
        "operational_health_incidents",
        ["camera_id"],
    )
    op.create_index(
        "ix_operational_health_incidents_edge_device_id",
        "operational_health_incidents",
        ["edge_device_id"],
    )
    op.create_index(
        "ix_operational_health_organization_status",
        "operational_health_incidents",
        ["organization_id", "status", "last_detected_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_health_organization_status",
        table_name="operational_health_incidents",
    )
    op.drop_index(
        "ix_operational_health_incidents_edge_device_id",
        table_name="operational_health_incidents",
    )
    op.drop_index(
        "ix_operational_health_incidents_camera_id",
        table_name="operational_health_incidents",
    )
    op.drop_index(
        "ix_operational_health_incidents_organization_id",
        table_name="operational_health_incidents",
    )
    op.drop_table("operational_health_incidents")
