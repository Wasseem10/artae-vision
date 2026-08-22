"""Tenant-scoped, append-only operator audit history."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from video_intelligence_api.auth import AdminDependency
from video_intelligence_api.dependencies import SessionDependency
from video_intelligence_api.models import AuditLog
from video_intelligence_api.schemas import AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["audit logs"])


@router.get("", response_model=list[AuditLogRead])
async def list_audit_logs(
    session: SessionDependency,
    actor: AdminDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AuditLog]:
    return list(
        (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.organization_id == actor.organization_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
