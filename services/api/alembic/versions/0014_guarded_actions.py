"""Add guarded connector and action execution runtime.

Revision ID: 0014_guarded_actions
Revises: 0013_visual_agent_plans
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_guarded_actions"
down_revision: str | None = "0013_visual_agent_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_connectors",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "connector_type",
            sa.Enum(
                "MOCK",
                "GENERIC_WEBHOOK",
                "MESSAGING_WEBHOOK",
                "TICKET_WEBHOOK",
                name="connectortype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("endpoint_url", sa.String(2048)),
        sa.Column("credential_encrypted", sa.String(4000), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_integration_connectors_organization_name"
        ),
    )
    op.create_index(
        "ix_integration_connectors_organization_id", "integration_connectors", ["organization_id"]
    )

    op.create_table(
        "rule_action_bindings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("connector_id", sa.String(36), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", name="actionrisklevel", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "approval_mode",
            sa.Enum("AUTOMATIC", "MANUAL", name="actionapprovalmode", native_enum=False),
            nullable=False,
        ),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("payload_template", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["integration_connectors.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_id", "connector_id", "action_type", name="uq_rule_action_bindings_action"
        ),
    )
    op.create_index(
        "ix_rule_action_bindings_organization_id", "rule_action_bindings", ["organization_id"]
    )
    op.create_index("ix_rule_action_bindings_rule_id", "rule_action_bindings", ["rule_id"])
    op.create_index(
        "ix_rule_action_bindings_connector_id", "rule_action_bindings", ["connector_id"]
    )

    op.create_table(
        "action_executions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("alert_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("connector_id", sa.String(36), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column(
            "risk_level",
            sa.Enum("LOW", "MEDIUM", "HIGH", name="actionrisklevel", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "AWAITING_APPROVAL",
                "QUEUED",
                "RUNNING",
                "RETRYING",
                "SUCCEEDED",
                "DEAD_LETTERED",
                "DENIED",
                "SUPPRESSED",
                name="actionexecutionstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("manual_retry_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_id", sa.String(120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_status_code", sa.Integer()),
        sa.Column("last_error", sa.String(1000)),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("denied_by", sa.String(255)),
        sa.Column("denied_at", sa.DateTime(timezone=True)),
        sa.Column("denial_reason", sa.String(500)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["binding_id"], ["rule_action_bindings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["integration_connectors.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "binding_id", name="uq_action_executions_event_binding"),
        sa.UniqueConstraint("idempotency_key", name="uq_action_executions_idempotency_key"),
    )
    for name, columns in (
        ("ix_action_executions_organization_id", ["organization_id"]),
        ("ix_action_executions_alert_id", ["alert_id"]),
        ("ix_action_executions_event_id", ["event_id"]),
        ("ix_action_executions_binding_id", ["binding_id"]),
        ("ix_action_executions_connector_id", ["connector_id"]),
        ("ix_action_executions_claim", ["status", "next_attempt_at"]),
    ):
        op.create_index(name, "action_executions", columns)


def downgrade() -> None:
    op.drop_table("action_executions")
    op.drop_table("rule_action_bindings")
    op.drop_table("integration_connectors")
