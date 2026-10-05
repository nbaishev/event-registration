from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.passwords import hash_password
from app.auth.service import login_user
from app.auth.tokens import verify_token
from app.common.clock import FixedClock
from app.common.config import get_settings
from app.common.errors import AppError


def test_login_service_normalizes_email_and_preserves_password(monkeypatch):
    from app.auth import repository

    clock = FixedClock(datetime(2026, 10, 4, 12, tzinfo=UTC))
    user = User(
        id=uuid4(),
        email="alice@example.com",
        password_hash=hash_password(" a long password "),
        created_at=clock.now(),
        updated_at=clock.now(),
    )

    def lookup(session, email):
        assert email == "alice@example.com"
        return user

    monkeypatch.setattr(repository, "find_user_by_email", lookup)
    returned, pair = login_user(
        Mock(spec=Session),
        clock,
        get_settings(),
        " ALICE@EXAMPLE.COM ",
        " a long password ",
    )
    assert returned is user
    assert verify_token(pair.access, "access", clock, get_settings()) == user.id


@pytest.mark.parametrize("exists", [False, True])
def test_login_service_invalid_credentials_never_return_tokens(monkeypatch, exists):
    from app.auth import repository

    clock = FixedClock(datetime(2026, 10, 4, 12, tzinfo=UTC))
    user = User(
        id=uuid4(),
        email="alice@example.com",
        password_hash=hash_password(" a long password "),
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    monkeypatch.setattr(
        repository, "find_user_by_email", lambda *_: user if exists else None
    )
    with pytest.raises(AppError) as caught:
        login_user(
            Mock(spec=Session),
            clock,
            get_settings(),
            "alice@example.com",
            "wrong password",
        )
    assert caught.value.status == 401
    assert caught.value.code == "AUTH_INVALID_CREDENTIALS"
