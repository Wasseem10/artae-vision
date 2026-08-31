"""Add closed-loop field accuracy labels and gate snapshots.

Revision ID: 0028_field_accuracy_learning
Revises: 0027_live_verification_cases
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_field_accuracy_learning"
down_revision: str | None = "0027_live_verification_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    outcome = sa.Enum(
        "TRUE_POSITIVE",
        "FALSE_POSITIVE",
        "FALSE_NEGATIVE",
        "TRUE_NEGATIVE",
        name="accuracylabeloutcome",
        native_enum=False,
    )
    gate_status = sa.Enum(
        "COLLECTING",
        "READY",
        "FAILING",
        "DRIFTING",
        name="accuracygatestatus",
        native_enum=False,
    )
    op.create_table(
        "rule_accuracy_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("minimum_positive_labels", sa.Integer(), nullable=False),
        sa.Column("minimum_negative_labels", sa.Integer(), nullable=False),
        sa.Column("minimum_challenging_labels", sa.Integer(), nullable=False),
        sa.Column("minimum_precision", sa.Float(), nullable=False),
        sa.Column("minimum_recall", sa.Float(), nullable=False),
        sa.Column("rolling_window_size", sa.Integer(), nullable=False),
        sa.Column("manual_only", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id"),
    )
    for column in ("organization_id", "camera_id", "rule_id"):
        op.create_index(
            f"ix_rule_accuracy_policies_{column}", "rule_accuracy_policies", [column]
        )
    op.create_table(
        "field_accuracy_labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("verification_case_id", sa.String(length=36)),
        sa.Column("event_id", sa.String(length=36)),
        sa.Column("recording_id", sa.String(length=36)),
        sa.Column("outcome", outcome, nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("environment_tags", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recording_id"], ["recording_segments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["verification_case_id"], ["verification_cases.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verification_case_id"),
    )
    for column in ("organization_id", "camera_id", "rule_id", "event_id", "recording_id"):
        op.create_index(f"ix_field_accuracy_labels_{column}", "field_accuracy_labels", [column])
    op.create_index(
        "ix_field_accuracy_labels_rule_created",
        "field_accuracy_labels",
        ["rule_id", "created_at"],
    )
    op.create_index(
        "ix_field_accuracy_labels_organization_created",
        "field_accuracy_labels",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "field_accuracy_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("window_size", sa.Integer(), nullable=False),
        sa.Column("label_count", sa.Integer(), nullable=False),
        sa.Column("positive_count", sa.Integer(), nullable=False),
        sa.Column("negative_count", sa.Integer(), nullable=False),
        sa.Column("challenging_count", sa.Integer(), nullable=False),
        sa.Column("true_positives", sa.Integer(), nullable=False),
        sa.Column("false_positives", sa.Integer(), nullable=False),
        sa.Column("false_negatives", sa.Integer(), nullable=False),
        sa.Column("true_negatives", sa.Integer(), nullable=False),
        sa.Column("precision", sa.Float()),
        sa.Column("recall", sa.Float()),
        sa.Column("f1", sa.Float()),
        sa.Column("gate_status", gate_status, nullable=False),
        sa.Column("automatic_release_allowed", sa.Boolean(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "camera_id", "rule_id"):
        op.create_index(
            f"ix_field_accuracy_snapshots_{column}", "field_accuracy_snapshots", [column]
        )
    op.create_index(
        "ix_field_accuracy_snapshots_rule_created",
        "field_accuracy_snapshots",
        ["rule_id", "created_at"],
    )
    op.create_index(
        "ix_field_accuracy_snapshots_organization_status",
        "field_accuracy_snapshots",
        ["organization_id", "gate_status"],
    )


def downgrade() -> None:
    op.drop_table("field_accuracy_snapshots")
    op.drop_table("field_accuracy_labels")
    op.drop_table("rule_accuracy_policies")
