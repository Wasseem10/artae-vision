"""Add normalized external observations and temporal correlations.

Revision ID: 0015_external_context
Revises: 0014_guarded_actions
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_external_context"
down_revision: str | None = "0014_guarded_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "context_sources",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "SIMULATED_ACCESS_CONTROL",
                "GENERIC_EVENT_FEED",
                name="contextsourcetype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("endpoint_url", sa.String(2048)),
        sa.Column("credential_encrypted", sa.String(4000)),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_context_sources_organization_name"),
    )
    op.create_index("ix_context_sources_organization_id", "context_sources", ["organization_id"])

    op.create_table(
        "context_observations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("source_event_id", sa.String(160), nullable=False),
        sa.Column("observation_type", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entity_key", sa.String(255)),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["context_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id", "source_event_id", name="uq_context_observations_source_event"
        ),
    )
    op.create_index(
        "ix_context_observations_organization_id", "context_observations", ["organization_id"]
    )
    op.create_index("ix_context_observations_source_id", "context_observations", ["source_id"])
    op.create_index(
        "ix_context_observations_source_occurred",
        "context_observations",
        ["source_id", "occurred_at"],
    )

    op.create_table(
        "rule_correlation_policies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column(
            "correlation_type",
            sa.Enum(
                "COUNT_EXCEEDS_AUTHORIZATIONS",
                name="correlationtype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("observation_type", sa.String(80), nullable=False),
        sa.Column("visual_count_field", sa.String(80), nullable=False),
        sa.Column("window_before_seconds", sa.Float(), nullable=False),
        sa.Column("window_after_seconds", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["context_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_id", "source_id", "correlation_type", name="uq_rule_correlation_policy"
        ),
    )
    for name, columns in (
        ("ix_rule_correlation_policies_organization_id", ["organization_id"]),
        ("ix_rule_correlation_policies_rule_id", ["rule_id"]),
        ("ix_rule_correlation_policies_source_id", ["source_id"]),
    ):
        op.create_index(name, "rule_correlation_policies", columns)

    op.create_table(
        "correlation_evaluations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "MATCHED",
                "CLEAR",
                "FAILED",
                name="correlationevaluationstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("visual_count", sa.Integer(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("explanation", sa.String(1000)),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["policy_id"], ["rule_correlation_policies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["context_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "policy_id", name="uq_correlation_evaluation_event_policy"),
    )
    for name, columns in (
        ("ix_correlation_evaluations_organization_id", ["organization_id"]),
        ("ix_correlation_evaluations_event_id", ["event_id"]),
        ("ix_correlation_evaluations_policy_id", ["policy_id"]),
        ("ix_correlation_evaluations_source_id", ["source_id"]),
        ("ix_correlation_evaluations_due", ["status", "due_at"]),
    ):
        op.create_index(name, "correlation_evaluations", columns)


def downgrade() -> None:
    op.drop_table("correlation_evaluations")
    op.drop_table("rule_correlation_policies")
    op.drop_table("context_observations")
    op.drop_table("context_sources")
