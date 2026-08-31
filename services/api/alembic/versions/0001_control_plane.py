"""Create cameras, zones, rules, and events.

Revision ID: 0001_control_plane
Revises:
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_control_plane"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic's default version column is too short for later descriptive revision IDs.
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    op.create_table(
        "cameras",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_uri", sa.String(length=2048), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum("WEBCAM", "FILE", "RTSP", name="sourcetype", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OFFLINE",
                "ONLINE",
                "ERROR",
                "DISABLED",
                name="camerastatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "zones",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("points", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_id", "name", name="uq_zones_camera_name"),
    )
    op.create_index("ix_zones_camera_id", "zones", ["camera_id"])
    op.create_table(
        "rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("zone_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("object_class", sa.String(length=80), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("minimum_confidence", sa.Float(), nullable=False),
        sa.Column("absence_grace_seconds", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "ACTIVE", "PAUSED", name="rulestatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("original_prompt", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_id", "key", name="uq_rules_camera_key"),
    )
    op.create_index("ix_rules_camera_id", "rules", ["camera_id"])
    op.create_index("ix_rules_zone_id", "rules", ["zone_id"])
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_event_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=True),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("object_class", sa.String(length=80), nullable=False),
        sa.Column("zone_name", sa.String(length=120), nullable=False),
        sa.Column("entered_at_seconds", sa.Float(), nullable=False),
        sa.Column("occurred_at_seconds", sa.Float(), nullable=False),
        sa.Column("dwell_seconds", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clip_uri", sa.String(length=2048), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_event_id"),
    )
    op.create_index("ix_events_camera_occurred_at", "events", ["camera_id", "occurred_at"])
    op.create_index("ix_events_rule_occurred_at", "events", ["rule_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_events_rule_occurred_at", table_name="events")
    op.drop_index("ix_events_camera_occurred_at", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_rules_zone_id", table_name="rules")
    op.drop_index("ix_rules_camera_id", table_name="rules")
    op.drop_table("rules")
    op.drop_index("ix_zones_camera_id", table_name="zones")
    op.drop_table("zones")
    op.drop_table("cameras")
