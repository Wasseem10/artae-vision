"""Add edge-device credentials, capacity ownership, and operator audit logs.

Revision ID: 0008_edge_devices_and_audit
Revises: 0007_identity_and_tenancy
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_edge_devices_and_audit"
down_revision: str | None = "0007_identity_and_tenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edge_devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "REVOKED", name="edgedevicestatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("max_concurrent_streams", sa.Integer(), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=False),
        sa.Column("credential_fingerprint", sa.String(length=16), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_worker_id", sa.String(length=120), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_edge_devices_organization_name"),
    )
    op.create_index(
        op.f("ix_edge_devices_organization_id"),
        "edge_devices",
        ["organization_id"],
        unique=False,
    )
    with op.batch_alter_table("camera_agents") as batch_op:
        batch_op.add_column(sa.Column("edge_device_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_camera_agents_edge_device_id",
            "edge_devices",
            ["edge_device_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_camera_agents_edge_device_id"), ["edge_device_id"], unique=False
        )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=False),
        sa.Column("actor_issuer", sa.String(length=500), nullable=False),
        sa.Column(
            "actor_role",
            sa.Enum(
                "OWNER",
                "ADMIN",
                "OPERATOR",
                "VIEWER",
                name="organizationrole",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=120), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("client_host", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
    op.create_index(op.f("ix_audit_logs_organization_id"), "audit_logs", ["organization_id"])
    op.create_index(op.f("ix_audit_logs_request_id"), "audit_logs", ["request_id"])
    op.create_index(
        "ix_audit_logs_organization_created",
        "audit_logs",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_organization_created", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_request_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_organization_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_table("audit_logs")
    with op.batch_alter_table("camera_agents") as batch_op:
        batch_op.drop_index(op.f("ix_camera_agents_edge_device_id"))
        batch_op.drop_constraint("fk_camera_agents_edge_device_id", type_="foreignkey")
        batch_op.drop_column("edge_device_id")
    op.drop_index(op.f("ix_edge_devices_organization_id"), table_name="edge_devices")
    op.drop_table("edge_devices")
