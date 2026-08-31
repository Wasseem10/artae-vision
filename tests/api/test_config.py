import pytest
from video_intelligence_api.config import ApiSettings


def test_settings_use_vercel_supabase_integration_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VIDEO_INTEL_API_DATABASE_URL", raising=False)
    monkeypatch.delenv("VIDEO_INTEL_API_SUPABASE_URL", raising=False)
    monkeypatch.delenv("VIDEO_INTEL_API_SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv(
        "POSTGRES_URL",
        "postgresql://database-user:database-password@database.test/postgres",
    )
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "server-secret")

    settings = ApiSettings(
        agent_key="test-agent-key-123456789",
        dashboard_key="test-dashboard-key-12345",
    )

    assert settings.database_url == (
        "postgresql+psycopg://database-user:database-password@database.test/postgres"
    )
    assert settings.supabase_url == "https://project-ref.supabase.co"
    assert settings.supabase_secret_key is not None
    assert settings.supabase_secret_key.get_secret_value() == "server-secret"


@pytest.mark.parametrize(
    ("input_url", "expected_url"),
    [
        ("postgres://user:pass@host/db", "postgresql+psycopg://user:pass@host/db"),
        (
            "postgresql://user:pass@host/db?sslmode=require&supa=base-pooler.x",
            "postgresql+psycopg://user:pass@host/db?sslmode=require",
        ),
        ("sqlite+aiosqlite:///test.db", "sqlite+aiosqlite:///test.db"),
    ],
)
def test_database_url_normalization(input_url: str, expected_url: str) -> None:
    settings = ApiSettings(
        agent_key="test-agent-key-123456789",
        dashboard_key="test-dashboard-key-12345",
        database_url=input_url,
    )

    assert settings.database_url == expected_url
