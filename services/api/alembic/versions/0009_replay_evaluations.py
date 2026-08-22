"""Add durable labeled-video replay evaluations.

Revision ID: 0009_replay_evaluations
Revises: 0008_edge_devices_and_audit
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_replay_evaluations"
down_revision: str | None = "0008_edge_devices_and_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replay_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("compilation_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("source_uri", sa.String(length=2048), nullable=False),
        sa.Column("prompt", sa.String(length=2000), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("execution_strategy", sa.String(length=40), nullable=False),
        sa.Column("compiled_rule", sa.JSON(), nullable=False),
        sa.Column("execution_plan", sa.JSON(), nullable=False),
        sa.Column("expected_intervals", sa.JSON(), nullable=False),
        sa.Column("predicted_intervals", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("provider_requests", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "SCORED", name="replayevaluationstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["compilation_id"], ["rule_compilations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_replay_evaluations_organization_id"),
        "replay_evaluations",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_replay_evaluations_camera_id"),
        "replay_evaluations",
        ["camera_id"],
    )
    op.create_index(
        op.f("ix_replay_evaluations_compilation_id"),
        "replay_evaluations",
        ["compilation_id"],
    )
    op.create_index(
        "ix_replay_evaluations_organization_created",
        "replay_evaluations",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_replay_evaluations_organization_created", table_name="replay_evaluations")
    op.drop_index(op.f("ix_replay_evaluations_compilation_id"), table_name="replay_evaluations")
    op.drop_index(op.f("ix_replay_evaluations_camera_id"), table_name="replay_evaluations")
    op.drop_index(op.f("ix_replay_evaluations_organization_id"), table_name="replay_evaluations")
    op.drop_table("replay_evaluations")
