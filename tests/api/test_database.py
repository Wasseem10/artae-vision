from typing import Any

import video_intelligence_api.database as database_module


def test_psycopg_disables_prepared_statements_for_transaction_poolers(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}
    engine = object()

    def fake_create_async_engine(url: str, **options: object) -> object:
        captured["url"] = url
        captured["options"] = options
        return engine

    monkeypatch.setattr(
        database_module, "create_async_engine", fake_create_async_engine
    )
    monkeypatch.setattr(
        database_module, "async_sessionmaker", lambda *args, **kwargs: object()
    )

    database_module.Database("postgresql+psycopg://user:pass@pooler.test:6543/postgres")

    assert captured["options"] == {
        "pool_pre_ping": True,
        "connect_args": {"prepare_threshold": None},
    }


def test_sqlite_waits_for_concurrent_local_writes(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    engine = object()

    def fake_create_async_engine(url: str, **options: object) -> object:
        captured["options"] = options
        return engine

    monkeypatch.setattr(
        database_module, "create_async_engine", fake_create_async_engine
    )
    monkeypatch.setattr(
        database_module, "async_sessionmaker", lambda *args, **kwargs: object()
    )

    database_module.Database("sqlite+aiosqlite:///test.db")

    assert captured["options"] == {
        "pool_pre_ping": True,
        "connect_args": {"timeout": 30},
    }
