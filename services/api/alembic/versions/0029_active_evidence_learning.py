"""Add active evidence sampling, review queue, and dataset versions.

Revision ID: 0029_active_evidence_learning
Revises: 0028_field_accuracy_learning
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_active_evidence_learning"
down_revision: str | None = "0028_field_accuracy_learning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    sample_kind = sa.Enum(
        "CANDIDATE",
        "NORMAL",
        "UNCERTAIN",
        "CHALLENGING",
        name="reviewsamplekind",
        native_enum=False,
    )
    sample_status = sa.Enum(
        "QUEUED", "ASSIGNED", "LABELED", "SKIPPED", name="reviewsamplestatus", native_enum=False
    )
    dataset_status = sa.Enum(
        "DRAFT", "FROZEN", "EXPORTED", name="datasetversionstatus", native_enum=False
    )
    op.create_table(
        "evidence_sampling_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "camera_id",
            sa.String(36),
            sa.ForeignKey("cameras.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            sa.String(36),
            sa.ForeignKey("rules.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("normal_sample_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("review_sla_hours", sa.Integer(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("organization_id", "camera_id", "rule_id"):
        op.create_index(
            f"ix_evidence_sampling_policies_{column}", "evidence_sampling_policies", [column]
        )
    op.create_table(
        "evidence_review_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
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
            "verification_case_id",
            sa.String(36),
            sa.ForeignKey("verification_cases.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id", ondelete="SET NULL")),
        sa.Column(
            "recording_id",
            sa.String(36),
            sa.ForeignKey("recording_segments.id", ondelete="SET NULL"),
        ),
        sa.Column("kind", sample_kind, nullable=False),
        sa.Column("status", sample_status, nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("model_context", sa.JSON(), nullable=False),
        sa.Column("environment_tags", sa.JSON(), nullable=False),
        sa.Column("assigned_to", sa.String(255)),
        sa.Column("assigned_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column(
            "label_id",
            sa.String(36),
            sa.ForeignKey("field_accuracy_labels.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "dedup_key", name="uq_review_sample_org_dedup"),
    )
    for column in ("organization_id", "camera_id", "rule_id", "event_id", "recording_id"):
        op.create_index(f"ix_evidence_review_samples_{column}", "evidence_review_samples", [column])
    op.create_index(
        "ix_review_samples_org_status_priority",
        "evidence_review_samples",
        ["organization_id", "status", "priority"],
    )
    op.create_index(
        "ix_review_samples_rule_created", "evidence_review_samples", ["rule_id", "created_at"]
    )
    op.create_table(
        "evidence_dataset_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", dataset_status, nullable=False),
        sa.Column("selection", sa.JSON(), nullable=False),
        sa.Column("balance", sa.JSON(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True)),
        sa.Column("exported_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "name", "version", name="uq_dataset_org_name_version"
        ),
    )
    op.create_index(
        "ix_evidence_dataset_versions_organization_id",
        "evidence_dataset_versions",
        ["organization_id"],
    )
    op.create_table(
        "evidence_dataset_samples",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("evidence_dataset_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sample_id",
            sa.String(36),
            sa.ForeignKey("evidence_review_samples.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("label_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_id", "sample_id", name="uq_dataset_sample"),
    )
    op.create_index(
        "ix_evidence_dataset_samples_dataset_id", "evidence_dataset_samples", ["dataset_id"]
    )
    op.create_index(
        "ix_evidence_dataset_samples_sample_id", "evidence_dataset_samples", ["sample_id"]
    )


def downgrade() -> None:
    op.drop_table("evidence_dataset_samples")
    op.drop_table("evidence_dataset_versions")
    op.drop_table("evidence_review_samples")
    op.drop_table("evidence_sampling_policies")
