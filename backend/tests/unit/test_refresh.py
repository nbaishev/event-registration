from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.models import User
from app.auth.tokens import issue_tokens, verify_token
from app.common.clock import FixedClock
from app.common.config import get_settings
from app.common.errors import AppError

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def refresh(session, token, clock):
    assert hasattr(service, "refresh_access"), "refresh use-case missing"
    return service.refresh_access(session, token, clock, get_settings())


@pytest.mark.parametrize("offset,valid", [(2591999, True), (2592000, False)])
def test_refresh_exact_expiry_boundary_with_clock(monkeypatch, offset, valid):
    from app.auth import repository

    user = User(
        id=uuid4(),
        email="alice@example.com",
        password_hash="unused",
        created_at=NOW,
        updated_at=NOW,
    )
    monkeypatch.setattr(repository, "find_user_by_id", lambda *_: user)
    token = issue_tokens(user.id, FixedClock(NOW), get_settings()).refresh
    clock = FixedClock(NOW + timedelta(seconds=offset))
    if valid:
        returned, access = refresh(Mock(spec=Session), token, clock)
        assert returned is user
        assert verify_token(access, "access", clock, get_settings()) == user.id
        with pytest.raises(AppError):
            verify_token(
                access,
                "access",
                FixedClock(clock.now() + timedelta(seconds=900)),
                get_settings(),
            )
    else:
        with pytest.raises(AppError) as caught:
            refresh(Mock(spec=Session), token, clock)
        assert caught.value.code == "AUTH_REFRESH_INVALID"
        assert caught.value.status == 401


@pytest.mark.parametrize(
    "kind", ["missing", "tampered", "access", "expired", "unknown-user"]
)
def test_invalid_refresh_and_missing_user_have_one_safe_error(monkeypatch, kind):
    from app.auth import repository

    user = User(
        id=uuid4(),
        email="alice@example.com",
        password_hash="unused",
        created_at=NOW,
        updated_at=NOW,
    )
    monkeypatch.setattr(
        repository,
        "find_user_by_id",
        lambda *_: None if kind == "unknown-user" else user,
    )
    pair = issue_tokens(user.id, FixedClock(NOW), get_settings())
    token = {"missing": "", "tampered": "tampered", "access": pair.access}.get(
        kind, pair.refresh
    )
    clock = FixedClock(NOW + timedelta(days=30) if kind == "expired" else NOW)
    with pytest.raises(AppError) as caught:
        refresh(Mock(spec=Session), token, clock)
    assert caught.value.status == 401
    assert caught.value.code == "AUTH_REFRESH_INVALID"
    assert token not in str(caught.value) if token else True
