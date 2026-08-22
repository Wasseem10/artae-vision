"""Add sites, camera placement, and cross-camera entity sightings.

Revision ID: 0017_multicamera_sites
Revises: 0016_visual_skills_scene_memory
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_multicamera_sites"
down_revision: str | None = "0016_visual_skills_scene_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_sites_organization_name"),
    )
    op.create_index("ix_sites_organization_id", "sites", ["organization_id"])

    op.create_table(
        "site_areas",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("site_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("area_type", sa.String(80), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "name", name="uq_site_areas_site_name"),
    )
    op.create_index("ix_site_areas_organization_id", "site_areas", ["organization_id"])
    op.create_index("ix_site_areas_site_id", "site_areas", ["site_id"])

    op.create_table(
        "camera_placements",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("site_id", sa.String(36), nullable=False),
        sa.Column("area_id", sa.String(36)),
        sa.Column("camera_id", sa.String(36), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("heading_degrees", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["area_id"], ["site_areas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_id", name="uq_camera_placements_camera"),
    )
    for name, columns in (
        ("ix_camera_placements_organization_id", ["organization_id"]),
        ("ix_camera_placements_site_id", ["site_id"]),
        ("ix_camera_placements_area_id", ["area_id"]),
        ("ix_camera_placements_camera_id", ["camera_id"]),
    ):
        op.create_index(name, "camera_placements", columns)

    op.create_table(
        "entity_sightings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("camera_id", sa.String(36), nullable=False),
        sa.Column("area_id", sa.String(36)),
        sa.Column("event_id", sa.String(36)),
        sa.Column("entity_key", sa.String(255), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("bounding_box", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["area_id"], ["site_areas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "camera_id", "entity_key", "occurred_at", name="uq_entity_sighting_camera_time"
        ),
    )
    for name, columns in (
        ("ix_entity_sightings_organization_id", ["organization_id"]),
        ("ix_entity_sightings_camera_id", ["camera_id"]),
        ("ix_entity_sightings_area_id", ["area_id"]),
        ("ix_entity_sightings_event_id", ["event_id"]),
        ("ix_entity_sightings_entity_occurred", ["organization_id", "entity_key", "occurred_at"]),
    ):
        op.create_index(name, "entity_sightings", columns)


def downgrade() -> None:
    op.drop_table("entity_sightings")
    op.drop_table("camera_placements")
    op.drop_table("site_areas")
    op.drop_table("sites")
