"""Add versioned visual-agent plans and safe simulations.

Revision ID: 0013_visual_agent_plans
Revises: 0012_replay_regression_suites
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_visual_agent_plans"
down_revision: str | None = "0012_replay_regression_suites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visual_agent_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("compilation_id", sa.String(length=36)),
        sa.Column("parent_id", sa.String(length=36)),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.String(length=2000), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "APPROVED", "SUPERSEDED", name="visualagentplanstatus", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("required_capabilities", sa.JSON(), nullable=False),
        sa.Column("unsupported_capabilities", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.String(length=255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("regression_run_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["compilation_id"], ["rule_compilations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["visual_agent_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["regression_run_id"], ["replay_suite_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("camera_id", "revision", name="uq_visual_agent_plans_camera_revision"),
    )
    op.create_index(
        "ix_visual_agent_plans_organization_id", "visual_agent_plans", ["organization_id"]
    )
    op.create_index("ix_visual_agent_plans_camera_id", "visual_agent_plans", ["camera_id"])
    op.create_index("ix_visual_agent_plans_rule_id", "visual_agent_plans", ["rule_id"])
    op.create_index(
        "ix_visual_agent_plans_organization_created",
        "visual_agent_plans",
        ["organization_id", "created_at"],
    )
    op.create_table(
        "visual_agent_simulations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("trace", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["visual_agent_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_visual_agent_simulations_organization_id",
        "visual_agent_simulations",
        ["organization_id"],
    )
    op.create_index("ix_visual_agent_simulations_plan_id", "visual_agent_simulations", ["plan_id"])
    op.create_index(
        "ix_visual_agent_simulations_plan_created",
        "visual_agent_simulations",
        ["plan_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("visual_agent_simulations")
    op.drop_table("visual_agent_plans")
