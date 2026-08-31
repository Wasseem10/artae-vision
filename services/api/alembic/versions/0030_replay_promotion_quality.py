"""Add reviewer consensus, dataset replay builds, and deployment promotions.

Revision ID: 0030_replay_promotion_quality
Revises: 0029_active_evidence_learning
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_replay_promotion_quality"
down_revision: str | None = "0029_active_evidence_learning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence_sampling_policies") as batch:
        batch.add_column(
            sa.Column("required_reviews", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column(
                "require_adjudication", sa.Boolean(), nullable=False, server_default=sa.true()
            )
        )
    with op.batch_alter_table("evidence_review_samples") as batch:
        batch.add_column(
            sa.Column("consensus_status", sa.String(20), nullable=False, server_default="pending")
        )
        batch.add_column(sa.Column("adjudicated_by", sa.String(255)))
        batch.add_column(sa.Column("adjudicated_at", sa.DateTime(timezone=True)))

    op.create_table(
        "evidence_review_votes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sample_id",
            sa.String(36),
            sa.ForeignKey("evidence_review_samples.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("reasoning", sa.String(2000), nullable=False),
        sa.Column("environment_tags", sa.JSON(), nullable=False),
        sa.Column("reviewer", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sample_id", "reviewer", name="uq_review_vote_sample_reviewer"),
    )
    op.create_index(
        "ix_evidence_review_votes_organization_id", "evidence_review_votes", ["organization_id"]
    )
    op.create_index("ix_evidence_review_votes_sample_id", "evidence_review_votes", ["sample_id"])
    op.create_index(
        "ix_review_votes_sample_created", "evidence_review_votes", ["sample_id", "created_at"]
    )

    op.create_table(
        "dataset_replay_builds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("evidence_dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "suite_id",
            sa.String(36),
            sa.ForeignKey("replay_suites.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("evaluation_ids", sa.JSON(), nullable=False),
        sa.Column("skipped_samples", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_dataset_replay_builds_organization_id", "dataset_replay_builds", ["organization_id"]
    )
    op.create_index("ix_dataset_replay_builds_dataset_id", "dataset_replay_builds", ["dataset_id"])

    promotion_status = sa.Enum(
        "READY", "APPROVED", "REJECTED", "ROLLED_BACK", name="promotionstatus", native_enum=False
    )
    op.create_table(
        "deployment_promotions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("evidence_dataset_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "camera_id",
            sa.String(36),
            sa.ForeignKey("cameras.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id", sa.String(36), sa.ForeignKey("rules.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "candidate_plan_id",
            sa.String(36),
            sa.ForeignKey("visual_agent_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "baseline_plan_id",
            sa.String(36),
            sa.ForeignKey("visual_agent_plans.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "candidate_run_id",
            sa.String(36),
            sa.ForeignKey("replay_suite_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "baseline_run_id",
            sa.String(36),
            sa.ForeignKey("replay_suite_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("status", promotion_status, nullable=False),
        sa.Column("comparison", sa.JSON(), nullable=False),
        sa.Column("rollback_metadata", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(255)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.String(2000)),
        sa.Column("rolled_back_by", sa.String(255)),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
        sa.Column("rollback_reason", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("organization_id", "camera_id", "rule_id"):
        op.create_index(f"ix_deployment_promotions_{column}", "deployment_promotions", [column])
    op.create_index(
        "ix_deployment_promotions_org_created",
        "deployment_promotions",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("deployment_promotions")
    op.drop_table("dataset_replay_builds")
    op.drop_table("evidence_review_votes")
    with op.batch_alter_table("evidence_review_samples") as batch:
        batch.drop_column("adjudicated_at")
        batch.drop_column("adjudicated_by")
        batch.drop_column("consensus_status")
    with op.batch_alter_table("evidence_sampling_policies") as batch:
        batch.drop_column("require_adjudication")
        batch.drop_column("required_reviews")
