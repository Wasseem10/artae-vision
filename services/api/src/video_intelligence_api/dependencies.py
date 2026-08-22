from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from video_intelligence_api.config import ApiSettings
from video_intelligence_api.database import Database
from video_intelligence_api.media_gateway import MediaGateway


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


def get_media_gateway(request: Request) -> MediaGateway:
    return request.app.state.media_gateway


async def get_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    async for session in database.session():
        yield session


SessionDependency = Annotated[AsyncSession, Depends(get_session)]
SettingsDependency = Annotated[ApiSettings, Depends(get_settings)]
MediaGatewayDependency = Annotated[MediaGateway, Depends(get_media_gateway)]
