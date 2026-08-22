"""Add durable evidence assets and asynchronous searches.

Revision ID: 0003_searchable_evidence
Revises: 0002_managed_agents
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_searchable_evidence"
down_revision: str | None = "0002_managed_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "AWAITING_UPLOAD",
                "QUEUED",
                "INDEXING",
                "READY",
                "UNAVAILABLE",
                "FAILED",
                name="evidencestatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("storage_uri", sa.String(length=2048), nullable=True),
        sa.Column("media_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_index_id", sa.String(length=200), nullable=True),
        sa.Column("external_video_id", sa.String(length=200), nullable=True),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
        sa.UniqueConstraint("external_video_id"),
    )
    op.create_index(
        "ix_evidence_assets_status_updated",
        "evidence_assets",
        ["status", "updated_at"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO evidence_assets
                (id, event_id, status, provider, retry_count, created_at, updated_at)
            SELECT
                source_event_id, id, 'AWAITING_UPLOAD', 'artae_labs', 0, created_at, created_at
            FROM events
            """
        )
    )
    op.create_table(
        "evidence_searches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.String(length=1000), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=True),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "SEARCHING",
                "COMPLETED",
                "UNAVAILABLE",
                "FAILED",
                name="evidencesearchstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evidence_searches_status_updated",
        "evidence_searches",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_searches_status_updated", table_name="evidence_searches")
    op.drop_table("evidence_searches")
    op.drop_index("ix_evidence_assets_status_updated", table_name="evidence_assets")
    op.drop_table("evidence_assets")
