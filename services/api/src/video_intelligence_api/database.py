from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Database:
    """Own the async SQLAlchemy engine and create one session per request."""

    def __init__(self, database_url: str) -> None:
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if database_url.startswith("postgresql+psycopg://"):
            # Vercel uses Supabase's transaction-mode Supavisor pool. A later
            # request can land on a different server connection, so psycopg's
            # automatic prepared-statement cache must be disabled.
            engine_options["connect_args"] = {"prepare_threshold": None}
        self.engine: AsyncEngine = create_async_engine(database_url, **engine_options)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
