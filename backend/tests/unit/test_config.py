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


@pytest.mark.parametrize(
    "configured,expected",
    [
        ("https://Example.com", "https://example.com"),
        ("http://Example.com:80", "http://example.com"),
        ("https://Example.com:443", "https://example.com"),
        ("http://Example.com:443", "http://example.com:443"),
        ("https://Example.com:80", "https://example.com:80"),
        ("https://Example.com:8443", "https://example.com:8443"),
        ("http://[::1]:80", "http://[::1]"),
        ("https://[::1]:8443", "https://[::1]:8443"),
    ],
)
def test_app_origin_stores_browser_canonical_origin(
    configured: str, expected: str
) -> None:
    assert Settings(_env_file=None, app_origin=configured).app_origin == expected


@pytest.mark.parametrize(
    "configured",
    [
        "https://example.com/",
        "https://example.com/path",
        "https://example.com?x=1",
        "https://example.com?",
        "https://example.com#fragment",
        "https://example.com#",
        "https://example.com\\path",
        "https://example.com\\",
    ],
)
def test_app_origin_rejects_path_query_and_fragment(configured: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_origin=configured)


def test_jwt_secret_required_without_environment_or_env_file(monkeypatch):
    from pydantic import ValidationError

    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("secret", ["", "short", "я" * 15])
def test_jwt_secret_requires_at_least_32_bytes(secret):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret=secret)


def test_production_http_configuration_rejected_at_startup(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="HTTPS"):
        with TestClient(app):
            pass
