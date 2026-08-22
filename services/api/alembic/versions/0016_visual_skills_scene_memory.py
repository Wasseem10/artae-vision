"""Add automatic scene memory and change history.

Revision ID: 0016_visual_skills_scene_memory
Revises: 0015_external_context
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_visual_skills_scene_memory"
down_revision: str | None = "0015_external_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scene_memory_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("camera_id", sa.String(36), nullable=False),
        sa.Column("stable_key", sa.String(160), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "REGION",
                "EQUIPMENT",
                "DISPLAY",
                "TRACKED_ENTITY",
                "OTHER",
                name="sceneitemkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("bounding_box", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("current_state", sa.String(160), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("relationships", sa.JSON(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("AUTOMATIC", "OPERATOR", name="scenememorysource", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "review_status",
            sa.Enum(
                "PROPOSED",
                "CONFIRMED",
                "REJECTED",
                name="scenereviewstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_id", "stable_key", name="uq_scene_memory_camera_key"),
    )
    for name, columns in (
        ("ix_scene_memory_items_organization_id", ["organization_id"]),
        ("ix_scene_memory_items_camera_id", ["camera_id"]),
        ("ix_scene_memory_camera_last_seen", ["camera_id", "last_seen_at"]),
    ):
        op.create_index(name, "scene_memory_items", columns)

    op.create_table(
        "scene_changes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("camera_id", sa.String(36), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(36)),
        sa.Column("previous_state", sa.String(160)),
        sa.Column("new_state", sa.String(160), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["scene_memory_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_scene_changes_organization_id", ["organization_id"]),
        ("ix_scene_changes_camera_id", ["camera_id"]),
        ("ix_scene_changes_item_id", ["item_id"]),
        ("ix_scene_changes_event_id", ["event_id"]),
        ("ix_scene_changes_camera_occurred", ["camera_id", "occurred_at"]),
    ):
        op.create_index(name, "scene_changes", columns)


def downgrade() -> None:
    op.drop_table("scene_changes")
    op.drop_table("scene_memory_items")
