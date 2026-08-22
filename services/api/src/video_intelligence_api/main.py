from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from video_intelligence_api import __version__
from video_intelligence_api.audit import audit_operator_request
from video_intelligence_api.config import ApiSettings, get_api_settings
from video_intelligence_api.database import Database
from video_intelligence_api.media_gateway import (
    DisabledMediaGateway,
    MediaGateway,
    MediaGatewayClient,
)
from video_intelligence_api.previews import PreviewStore
from video_intelligence_api.routes import (
    actions,
    agent_plans,
    agents,
    alerts,
    audit_logs,
    cameras,
    capabilities,
    context,
    devices,
    evaluations,
    event_stream,
    events,
    evidence,
    fleet,
    health,
    identity,
    operations,
    previews,
    production,
    rule_compilations,
    rules,
    scene_memory,
    streams,
    zones,
)
from video_intelligence_api.websockets import EventConnectionManager

logger = logging.getLogger(__name__)


def create_app(
    settings: ApiSettings | None = None,
    database: Database | None = None,
    media_gateway: MediaGateway | None = None,
) -> FastAPI:
    resolved_settings = settings or get_api_settings()
    resolved_database = database or Database(resolved_settings.database_url)
    resolved_media_gateway = media_gateway
    if resolved_media_gateway is None:
        resolved_media_gateway = (
            DisabledMediaGateway()
            if resolved_settings.media_gateway_mode == "disabled"
            else MediaGatewayClient(
                resolved_settings.media_gateway_api_url,
                timeout_seconds=resolved_settings.media_gateway_timeout_seconds,
            )
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Control-plane API starting: environment=%s", resolved_settings.environment)
        yield
        await app.state.media_gateway.close()
        await app.state.database.dispose()
        logger.info("Control-plane API stopped")

    application = FastAPI(
        title="AI Video Intelligence Control Plane",
        version=__version__,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = resolved_database
    application.state.media_gateway = resolved_media_gateway
    application.state.event_connections = EventConnectionManager()
    application.state.preview_store = PreviewStore()
    application.middleware("http")(audit_operator_request)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        health.router,
        identity.router,
        devices.router,
        fleet.router,
        audit_logs.router,
        capabilities.router,
        cameras.router,
        streams.router,
        previews.router,
        agents.router,
        actions.router,
        context.router,
        scene_memory.router,
        operations.router,
        production.router,
        agent_plans.router,
        alerts.router,
        zones.router,
        rule_compilations.router,
        rules.router,
        events.router,
        evidence.router,
        evaluations.router,
        evaluations.suite_router,
        evaluations.agent_router,
        event_stream.router,
    ):
        application.include_router(router, prefix="/api/v1")

    @application.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "video-intelligence-api", "docs": "/docs"}

    return application


def run_server() -> int:
    settings = get_api_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
    return 0
