from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.router import get_clock
from app.common.clock import FixedClock
from app.main import app

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def guard(client):
    token = client.get("/api/auth/csrf").json()["csrf_token"]
    return {"Origin": "http://localhost:8080", "X-CSRF-Token": token}


def setup_session(client):
    headers = guard(client)
    body = {"email": "alice@example.com", "password": "a long password"}
    user = client.post("/api/auth/register", headers=headers, json=body).json()
    assert client.post("/api/auth/login", headers=headers, json=body).status_code == 200
    return user, headers


def parsed_cookies(response):
    result = {}
    for value in response.headers.get_list("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(value)
        result.update(parsed)
    return result


def test_refresh_renews_only_access_and_restores_me_with_expired_access(auth_client):
    user, headers = setup_session(auth_client)
    original = next(
        cookie for cookie in auth_client.cookies.jar if cookie.name == "refresh_token"
    )
    before = (original.value, original.expires, original.path)
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        NOW + timedelta(seconds=900)
    )
    assert auth_client.get("/api/auth/me").status_code == 401
    response = auth_client.post("/api/auth/refresh", headers=headers)
    assert response.status_code == 200
    assert response.json() == user
    assert response.headers["cache-control"] == "no-store"
    cookies = parsed_cookies(response)
    assert set(cookies) == {"access_token"}
    assert cookies["access_token"]["max-age"] == "900"
    assert cookies["access_token"]["path"] == "/api/"
    assert cookies["access_token"]["httponly"] is True
    assert cookies["access_token"]["samesite"].lower() == "lax"
    assert cookies["access_token"]["domain"] == ""
    assert cookies["access_token"]["secure"] == ""
    assert auth_client.get("/api/auth/me").json() == user
    after = next(
        cookie for cookie in auth_client.cookies.jar if cookie.name == "refresh_token"
    )
    preserved = (after.value, after.expires, after.path) == before
    assert preserved, "refresh lifetime/token must remain unchanged"
    assert cookies["access_token"].value not in response.text


@pytest.mark.parametrize(
    "kind", ["missing", "tampered", "expired", "access", "missing-user"]
)
def test_invalid_refresh_clears_both_original_paths(auth_client, auth_database, kind):
    user, headers = setup_session(auth_client)
    if kind == "missing":
        auth_client.cookies.delete("refresh_token")
    elif kind == "tampered":
        auth_client.cookies.set(
            "refresh_token",
            "tampered",
            domain="testserver.local",
            path="/api/auth/refresh",
        )
    elif kind == "expired":
        app.dependency_overrides[get_clock] = lambda: FixedClock(
            NOW + timedelta(days=30)
        )
    elif kind == "access":
        auth_client.cookies.set(
            "refresh_token",
            auth_client.cookies.get("access_token"),
            domain="testserver.local",
            path="/api/auth/refresh",
        )
    else:
        with Session(auth_database) as session:
            session.execute(delete(User).where(User.id == UUID(user["id"])))
            session.commit()
    response = auth_client.post("/api/auth/refresh", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REFRESH_INVALID"
    assert response.json()["error"]["details"] == {}
    assert response.headers["cache-control"] == "no-store"
    cookies = parsed_cookies(response)
    assert set(cookies) == {"access_token", "refresh_token"}
    for name, path in [
        ("access_token", "/api/"),
        ("refresh_token", "/api/auth/refresh"),
    ]:
        assert cookies[name]["max-age"] == "0"
        assert cookies[name]["path"] == path
        assert cookies[name]["expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
        assert cookies[name]["httponly"] is True
        assert cookies[name]["domain"] == ""
    assert auth_client.cookies.get("access_token") is None
    assert auth_client.cookies.get("refresh_token") is None
    assert auth_client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("failure", ["missing-csrf", "wrong-csrf", "foreign-origin"])
def test_refresh_security_guard_prevents_renewal(auth_client, failure):
    _, headers = setup_session(auth_client)
    if failure == "missing-csrf":
        headers.pop("X-CSRF-Token")
    elif failure == "wrong-csrf":
        headers["X-CSRF-Token"] = "wrong"
    else:
        headers["Origin"] += ".evil.test"
    response = auth_client.post("/api/auth/refresh", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_INVALID"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("offset,status", [(2591999, 200), (2592000, 401)])
def test_refresh_http_exact_expiry_boundary(auth_client, offset, status):
    _, headers = setup_session(auth_client)
    app.dependency_overrides[get_clock] = lambda: FixedClock(
        NOW + timedelta(seconds=offset)
    )
    assert auth_client.post("/api/auth/refresh", headers=headers).status_code == status


def test_production_refresh_and_invalid_cleanup_keep_secure(auth_database, monkeypatch):
    from fastapi.testclient import TestClient

    from app.common.config import get_settings
    from app.db.session import get_session

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("APP_ORIGIN", "https://testserver")
    get_settings.cache_clear()

    def session():
        with Session(auth_database) as value:
            yield value

    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app, base_url="https://testserver") as client:
            headers = {
                "Origin": "https://testserver",
                "X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"],
            }
            body = {"email": "alice@example.com", "password": "a long password"}
            assert (
                client.post(
                    "/api/auth/register", headers=headers, json=body
                ).status_code
                == 201
            )
            assert (
                client.post("/api/auth/login", headers=headers, json=body).status_code
                == 200
            )
            renewed = client.post("/api/auth/refresh", headers=headers)
            assert renewed.status_code == 200
            assert set(parsed_cookies(renewed)) == {"access_token"}
            assert parsed_cookies(renewed)["access_token"]["secure"] is True
            client.cookies.delete("refresh_token")
            invalid = client.post("/api/auth/refresh", headers=headers)
            assert invalid.status_code == 401
            for cookie in parsed_cookies(invalid).values():
                assert cookie["secure"] is True
                assert cookie["samesite"].lower() == "lax"
            assert client.cookies.get("access_token") is None
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
