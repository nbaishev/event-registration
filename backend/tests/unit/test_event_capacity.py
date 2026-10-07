from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.common.clock import FixedClock
from app.common.errors import AppError
from app.events import service
from app.events.models import EventStatus
from app.events.schemas import EventPatchRequest
from app.registrations import repository as registrations

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


@pytest.fixture
def event(monkeypatch):
    row = SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        status=EventStatus.PUBLISHED,
        capacity=3,
        starts_at=NOW + timedelta(hours=1),
        updated_at=NOW - timedelta(hours=1),
        title="Original",
        description="Description",
        timezone="UTC",
        ends_at=NOW + timedelta(hours=2),
        regenerate_slug=False,
    )
    monkeypatch.setattr(service.repository, "find_event_for_update", lambda *_: row)
    monkeypatch.setattr(registrations, "count_confirmed", lambda *_: 2)
    return row


@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "EVENT_NOT_FOUND"),
        ("other", "EVENT_NOT_OWNER"),
        ("cancelled", "EVENT_CANCELLED"),
        ("start", "EVENT_ALREADY_STARTED"),
        ("past", "EVENT_ALREADY_STARTED"),
        ("below", "CAPACITY_BELOW_CONFIRMED"),
    ],
)
def test_capacity_guards(monkeypatch, event, case, code):
    if case == "missing":
        monkeypatch.setattr(
            service.repository, "find_event_for_update", lambda *_: None
        )
    if case == "cancelled":
        event.status = EventStatus.CANCELLED
    if case in {"start", "past"}:
        event.starts_at = NOW - timedelta(seconds=case == "past")
    owner = uuid4() if case == "other" else event.owner_id
    with pytest.raises(AppError) as error:
        service.patch_owned_event(
            MagicMock(),
            FixedClock(NOW),
            owner,
            event.id,
            EventPatchRequest(capacity=1 if case == "below" else 2),
        )
    assert error.value.code == code
    assert event.capacity == 3
    assert event.updated_at == NOW - timedelta(hours=1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Original"),
        ("description", "Description"),
        ("timezone", "UTC"),
        ("starts_at", NOW + timedelta(hours=1)),
        ("ends_at", NOW + timedelta(hours=2)),
        ("regenerate_slug", False),
        ("regenerate_slug", True),
    ],
)
def test_mixed_published_patch_rejects_supplied_fields(event, field, value):
    with pytest.raises(AppError) as error:
        service.patch_owned_event(
            MagicMock(),
            FixedClock(NOW),
            event.owner_id,
            event.id,
            EventPatchRequest(**{"capacity": 2, field: value}),
        )
    assert error.value.code == "EVENT_NOT_EDITABLE"
    assert event.capacity == 3


@pytest.mark.parametrize("started", [False, True])
def test_equal_capacity_is_noop(monkeypatch, event, started):
    if started:
        event.starts_at = NOW

    def forbidden(*_):
        pytest.fail("No-op must not count or promote registrations")

    monkeypatch.setattr(registrations, "count_confirmed", forbidden)
    result = service.patch_owned_event(
        MagicMock(),
        FixedClock(NOW),
        event.owner_id,
        event.id,
        EventPatchRequest(capacity=3),
    )
    assert result.capacity == 3
    assert result.updated_at == NOW - timedelta(hours=1)


def test_decrease_to_confirmed_count(event):
    result = service.patch_owned_event(
        MagicMock(),
        FixedClock(NOW),
        event.owner_id,
        event.id,
        EventPatchRequest(capacity=2),
    )
    assert result.capacity == 2
    assert result.updated_at == NOW


@pytest.mark.parametrize("capacity", [0, -1, True, False, None, "2", 1.5, 2147483648])
def test_capacity_validation(capacity):
    with pytest.raises(ValidationError):
        EventPatchRequest(capacity=capacity)
