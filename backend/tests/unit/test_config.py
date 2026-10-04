import pytest

from app.common.config import Settings


def test_component_credentials_preserve_reserved_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "local@password/a:?#%")
    monkeypatch.setenv("POSTGRES_USER", "user@local")
    monkeypatch.setenv("POSTGRES_DB", "db/local")
    monkeypatch.setenv("DB_HOST", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = Settings(_env_file=None).sqlalchemy_url
    assert url.host == "postgres"
    assert url.username == "user@local"
    assert url.password == "local@password/a:?#%"
    assert url.database == "db/local"


def test_explicit_database_url_overrides_components() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://test_user:development@127.0.0.1:1234/test_db",
        db_host="unused",
    )
    assert settings.sqlalchemy_url.host == "127.0.0.1"
    assert settings.sqlalchemy_url.port == 1234
    assert settings.sqlalchemy_url.database == "test_db"
