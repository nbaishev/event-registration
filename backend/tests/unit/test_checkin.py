from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.common.clock import FixedClock
from app.common.errors import AppError
from app.registrations import checkin
from app.registrations.schemas import CheckInRequest

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "value", ["7K4P9Q2M8RTA", " 7k4p-9q2m-8rta ", "\t7k4p 9q2m 8rta\n"]
)
def test_normalization(value):
    assert CheckInRequest(ticket_code=value).ticket_code == "7K4P9Q2M8RTA"


@pytest.mark.parametrize(
    "value",
    [
        None,
        123456789234,
        True,
        [],
        "",
        "7K4P9Q2M8RT",
        "7K4P9Q2M8RTAA",
        "7K4P9Q2M8RT0",
        "7K4P9Q2M8RTI",
        "7K4P\t9Q2M8RTA",
        "7K4P\u00a09Q2M8RTA",
    ],
)
def test_invalid_codes(value):
    with pytest.raises(ValidationError):
        CheckInRequest(ticket_code=value)


def test_missing_code():
    with pytest.raises(ValidationError):
        CheckInRequest()


@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "EVENT_NOT_FOUND"),
        ("owner", "EVENT_NOT_OWNER"),
        ("draft", "CHECKIN_NOT_OPEN"),
        ("cancelled", "EVENT_CANCELLED"),
        ("early", "CHECKIN_NOT_OPEN"),
        ("end", "EVENT_FINISHED"),
        ("unknown", "TICKET_NOT_FOUND"),
        ("duplicate", "TICKET_ALREADY_CHECKED_IN"),
    ],
)
def test_guards(monkeypatch, case, code):
    owner = uuid4()
    event = SimpleNamespace(
        id=uuid4(),
        owner_id=owner,
        status="PUBLISHED",
        starts_at=NOW + timedelta(hours=2),
        ends_at=NOW + timedelta(hours=3),
    )
    if case == "owner":
        event.owner_id = uuid4()
        event.status = "CANCELLED"
    if case in ("draft", "cancelled"):
        event.status = case.upper()
        event.ends_at = NOW
    if case == "early":
        event.starts_at += timedelta(microseconds=1)
    if case == "end":
        event.ends_at = NOW
    monkeypatch.setattr(
        checkin.events,
        "find_event_for_share",
        lambda *_: None if case == "missing" else event,
    )
    monkeypatch.setattr(checkin.repository, "mark_checked_in", lambda *_: None)
    monkeypatch.setattr(
        checkin.repository,
        "find_confirmed_ticket",
        lambda *_: SimpleNamespace(checked_in_at=NOW) if case == "duplicate" else None,
    )
    with pytest.raises(AppError) as error:
        checkin.check_in(MagicMock(), FixedClock(NOW), owner, event.id, "7K4P9Q2M8RTA")
    assert error.value.code == code
