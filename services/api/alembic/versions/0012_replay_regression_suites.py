"""Add durable replay regression suites and historical runs.

Revision ID: 0012_replay_regression_suites
Revises: 0011_replay_upload_progress
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_replay_regression_suites"
down_revision: str | None = "0011_replay_upload_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replay_suites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("evaluation_ids", sa.JSON(), nullable=False),
        sa.Column("minimum_macro_f1", sa.Float(), nullable=False),
        sa.Column("minimum_macro_recall", sa.Float(), nullable=False),
        sa.Column("maximum_false_positives", sa.Integer(), nullable=False),
        sa.Column("maximum_estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("require_pricing", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_replay_suites_organization_id"),
        "replay_suites",
        ["organization_id"],
    )
    op.create_index(
        "ix_replay_suites_organization_created",
        "replay_suites",
        ["organization_id", "created_at"],
    )
    op.create_table(
        "replay_suite_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_ids", sa.JSON(), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "PASSED",
                "FAILED",
                name="replaysuiterunstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("gate_results", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suite_id"], ["replay_suites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_replay_suite_runs_organization_id"),
        "replay_suite_runs",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_replay_suite_runs_suite_id"),
        "replay_suite_runs",
        ["suite_id"],
    )
    op.create_index(
        "ix_replay_suite_runs_suite_created",
        "replay_suite_runs",
        ["suite_id", "created_at"],
    )
    op.create_index(
        "ix_replay_suite_runs_organization_status",
        "replay_suite_runs",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_replay_suite_runs_organization_status", table_name="replay_suite_runs")
    op.drop_index("ix_replay_suite_runs_suite_created", table_name="replay_suite_runs")
    op.drop_index(op.f("ix_replay_suite_runs_suite_id"), table_name="replay_suite_runs")
    op.drop_index(op.f("ix_replay_suite_runs_organization_id"), table_name="replay_suite_runs")
    op.drop_table("replay_suite_runs")
    op.drop_index("ix_replay_suites_organization_created", table_name="replay_suites")
    op.drop_index(op.f("ix_replay_suites_organization_id"), table_name="replay_suites")
    op.drop_table("replay_suites")
