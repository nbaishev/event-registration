from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.common.clock import FixedClock
from app.common.errors import AppError
from app.events.models import EventStatus
from app.registrations import service

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "EVENT_NOT_FOUND"),
        ("draft", "EVENT_NOT_FOUND"),
        ("owner", "OWNER_CANNOT_REGISTER"),
        ("cancelled", "EVENT_CANCELLED"),
        ("start", "EVENT_ALREADY_STARTED"),
        ("end", "EVENT_FINISHED"),
        ("duplicate", "ALREADY_REGISTERED"),
    ],
)
def test_guards_leave_database_unchanged(monkeypatch, case, code):
    user_id, event_id = uuid4(), uuid4()
    event = SimpleNamespace(
        id=event_id,
        owner_id=uuid4(),
        status=EventStatus.PUBLISHED,
        starts_at=NOW + timedelta(hours=1),
        ends_at=NOW + timedelta(hours=2),
    )
    if case == "draft":
        event.status = EventStatus.DRAFT
    if case == "owner":
        event.owner_id = user_id
    if case == "cancelled":
        event.status = EventStatus.CANCELLED
    if case == "start":
        event.starts_at = NOW
    if case == "end":
        event.ends_at = NOW
    monkeypatch.setattr(
        service.events,
        "find_event_for_update",
        lambda *_: None if case == "missing" else event,
    )
    monkeypatch.setattr(
        service.repository,
        "find_registration_for_update",
        lambda *_: SimpleNamespace(status="CONFIRMED") if case == "duplicate" else None,
    )
    session = MagicMock()
    with pytest.raises(AppError) as error:
        service.register_for_event(session, FixedClock(NOW), user_id, event_id)
    assert error.value.code == code
    session.commit.assert_not_called()
    session.add.assert_not_called()
    session.rollback.assert_called_once()
