"""Add opt-in, durable outbound notifications for camera outages.

Revision ID: 0031_health_outage_routes
Revises: 0030_replay_promotion_quality
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_health_outage_routes"
down_revision: str | None = "0030_replay_promotion_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_health_routes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("outage_after_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["alert_channels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("camera_id", "channel_id", name="uq_operational_health_route"),
    )
    op.create_index(
        "ix_operational_health_routes_camera_id", "operational_health_routes", ["camera_id"]
    )
    op.create_index(
        "ix_operational_health_routes_channel_id", "operational_health_routes", ["channel_id"]
    )
    op.create_table(
        "operational_health_deliveries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "DELIVERING",
                "RETRYING",
                "DELIVERED",
                "FAILED",
                "SUPPRESSED",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_id", sa.String(length=120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_status_code", sa.Integer()),
        sa.Column("last_error", sa.String(length=1000)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["operational_health_incidents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["alert_channels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("incident_id", "channel_id", name="uq_operational_health_delivery"),
    )
    op.create_index(
        "ix_operational_health_deliveries_incident_id",
        "operational_health_deliveries",
        ["incident_id"],
    )
    op.create_index(
        "ix_operational_health_deliveries_channel_id",
        "operational_health_deliveries",
        ["channel_id"],
    )
    op.create_index(
        "ix_operational_health_deliveries_claim",
        "operational_health_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_health_deliveries_claim", table_name="operational_health_deliveries"
    )
    op.drop_index(
        "ix_operational_health_deliveries_channel_id", table_name="operational_health_deliveries"
    )
    op.drop_index(
        "ix_operational_health_deliveries_incident_id", table_name="operational_health_deliveries"
    )
    op.drop_table("operational_health_deliveries")
    op.drop_index("ix_operational_health_routes_channel_id", table_name="operational_health_routes")
    op.drop_index("ix_operational_health_routes_camera_id", table_name="operational_health_routes")
    op.drop_table("operational_health_routes")
