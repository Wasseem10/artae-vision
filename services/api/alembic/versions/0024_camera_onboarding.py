"""Add credentialed ONVIF onboarding and edge-pinned camera credentials.

Revision ID: 0024_camera_onboarding
Revises: 0023_camera_discovery
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_camera_onboarding"
down_revision: str | None = "0023_camera_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cameras") as batch:
        batch.add_column(sa.Column("edge_device_id", sa.String(length=36)))
        batch.add_column(sa.Column("credential_encrypted", sa.String(length=4000)))
        batch.create_foreign_key(
            "fk_cameras_edge_device_id",
            "edge_devices",
            ["edge_device_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_cameras_edge_device_id", "cameras", ["edge_device_id"])
    op.create_table(
        "camera_onboarding_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("edge_device_id", sa.String(length=36), nullable=False),
        sa.Column("discovery_run_id", sa.String(length=36), nullable=False),
        sa.Column("camera_name", sa.String(length=120), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
        sa.Column("credential_encrypted", sa.String(length=4000)),
        sa.Column("verify_tls", sa.Boolean(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "COMPLETED",
                "FAILED",
                name="cameraonboardingstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("profiles", sa.JSON(), nullable=False),
        sa.Column("selected_profile_token", sa.String(length=255)),
        sa.Column("camera_id", sa.String(length=36)),
        sa.Column("worker_id", sa.String(length=120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(length=1000)),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edge_device_id"], ["edge_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"], ["camera_discovery_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_camera_onboarding_runs_organization_id",
        "camera_onboarding_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_camera_onboarding_runs_edge_device_id",
        "camera_onboarding_runs",
        ["edge_device_id"],
    )
    op.create_index(
        "ix_camera_onboarding_runs_discovery_run_id",
        "camera_onboarding_runs",
        ["discovery_run_id"],
    )
    op.create_index(
        "ix_camera_onboarding_runs_camera_id",
        "camera_onboarding_runs",
        ["camera_id"],
    )
    op.create_index(
        "ix_camera_onboarding_device_status",
        "camera_onboarding_runs",
        ["edge_device_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_camera_onboarding_device_status", table_name="camera_onboarding_runs")
    op.drop_index("ix_camera_onboarding_runs_camera_id", table_name="camera_onboarding_runs")
    op.drop_index("ix_camera_onboarding_runs_discovery_run_id", table_name="camera_onboarding_runs")
    op.drop_index("ix_camera_onboarding_runs_edge_device_id", table_name="camera_onboarding_runs")
    op.drop_index("ix_camera_onboarding_runs_organization_id", table_name="camera_onboarding_runs")
    op.drop_table("camera_onboarding_runs")
    op.drop_index("ix_cameras_edge_device_id", table_name="cameras")
    with op.batch_alter_table("cameras") as batch:
        batch.drop_constraint("fk_cameras_edge_device_id", type_="foreignkey")
        batch.drop_column("credential_encrypted")
        batch.drop_column("edge_device_id")
