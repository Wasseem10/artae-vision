from collections.abc import AsyncIterator

from sqlalchemy import event
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
        elif database_url.startswith("sqlite+"):
            # The local camera worker, alert worker, and browser all access the
            # same file. Give short-lived writes time to finish instead of
            # immediately surfacing "database is locked" to the operator.
            engine_options["connect_args"] = {"timeout": 30}
        self.engine: AsyncEngine = create_async_engine(database_url, **engine_options)
        if database_url.startswith("sqlite+") and hasattr(self.engine, "sync_engine"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def configure_sqlite_connection(dbapi_connection: object, _record: object) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()

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
