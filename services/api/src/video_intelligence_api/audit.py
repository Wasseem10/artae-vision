from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from video_intelligence_api.models import AuditLog, new_id

logger = logging.getLogger(__name__)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def audit_operator_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Record authenticated operator mutations without retaining request bodies or secrets."""
    request_id = new_id()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    actor = getattr(request.state, "actor", None)
    if actor is None or request.method not in MUTATING_METHODS:
        return response

    request_path = request.url.path
    action = f"{request.method} {request_path}"
    segments = [segment for segment in request_path.split("/") if segment]
    resource_type = segments[2] if len(segments) > 2 and segments[:2] == ["api", "v1"] else None
    resource_id = next(
        (
            str(value)
            for key, value in request.path_params.items()
            if key.endswith("_id") or key.endswith("_ref")
        ),
        None,
    )
    client_host = request.client.host if request.client else None
    record = AuditLog(
        id=new_id(),
        organization_id=actor.organization_id,
        actor_subject=actor.subject,
        actor_issuer=actor.issuer,
        actor_role=actor.role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status_code=response.status_code,
        request_id=request_id,
        client_host=client_host,
        details={"query_keys": sorted(request.query_params.keys())},
    )
    try:
        async with request.app.state.database.session_factory() as session:
            session.add(record)
            await session.commit()
    except Exception:
        logger.exception("Could not persist operator audit record: request_id=%s", request_id)
    return response
