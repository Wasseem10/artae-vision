"""Add versioned natural-language rule compilations.

Revision ID: 0004_natural_language_rules
Revises: 0003_searchable_evidence
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_natural_language_rules"
down_revision: str | None = "0003_searchable_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rules",
        sa.Column("spec_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_table(
        "rule_compilations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.String(length=2000), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_model", sa.String(length=120), nullable=True),
        sa.Column("compiler_version", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "NEEDS_CLARIFICATION",
                "READY_FOR_REVIEW",
                "ACCEPTED",
                name="rulecompilationstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("compiled_rule", sa.JSON(), nullable=True),
        sa.Column("explanation", sa.String(length=2000), nullable=False),
        sa.Column("clarification_question", sa.String(length=1000), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("accepted_rule_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["accepted_rule_id"], ["rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["rule_compilations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rule_compilations_camera_created",
        "rule_compilations",
        ["camera_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rule_compilations_camera_created", table_name="rule_compilations")
    op.drop_table("rule_compilations")
    op.drop_column("rules", "spec_version")
