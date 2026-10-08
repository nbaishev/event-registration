from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.common.clock import FixedClock
from app.common.errors import AppError
from app.events import service
from app.events.schemas import EventPatchRequest

NOW = datetime(2026, 10, 9, 12, tzinfo=UTC)


@pytest.fixture
def event(monkeypatch):
    event = SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        status="PUBLISHED",
        capacity=3,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=2),
        timezone="UTC",
        title="Conference",
        slug="conference",
        description="Text",
        published_at=NOW - timedelta(days=1),
        schedule_updated_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    monkeypatch.setattr(service.repository, "find_event_for_update", lambda *_: event)
    return event


def patch(event, body, session=None, dispatcher=None, owner=None):
    return service.patch_owned_event(
        session or MagicMock(),
        FixedClock(NOW),
        owner or event.owner_id,
        event.id,
        EventPatchRequest(**body),
        notification_dispatcher=dispatcher,
    )


@pytest.mark.parametrize(
    "body",
    [
        {"timezone": "Asia/Bishkek"},
        {"starts_at": NOW + timedelta(days=1)},
        {"ends_at": NOW + timedelta(days=3)},
    ],
)
def test_partial_schedule_updates_timestamps(event, monkeypatch, body):
    monkeypatch.setattr(service, "find_transition_recipients", lambda *_: [])
    old_publish = event.published_at
    patch(event, body, dispatcher=SimpleNamespace(enqueue=lambda notice: None))
    for key, value in body.items():
        assert getattr(event, key) == value
    assert event.updated_at == event.schedule_updated_at == NOW
    assert event.published_at == old_publish and event.slug == "conference"


@pytest.mark.parametrize(
    "body,code",
    [
        ({"starts_at": NOW}, "VALIDATION_ERROR"),
        ({"starts_at": NOW - timedelta(microseconds=1)}, "VALIDATION_ERROR"),
        ({"ends_at": NOW + timedelta(days=2)}, "VALIDATION_ERROR"),
        ({"starts_at": NOW + timedelta(days=3)}, "VALIDATION_ERROR"),
        ({"timezone": "UTC", "capacity": 3}, "EVENT_NOT_EDITABLE"),
        ({"timezone": "UTC", "title": "Conference"}, "EVENT_NOT_EDITABLE"),
        ({"timezone": "UTC", "regenerate_slug": False}, "EVENT_NOT_EDITABLE"),
    ],
)
def test_reject_before_mutation(event, body, code):
    old = vars(event).copy()
    with pytest.raises(AppError) as error:
        patch(event, body)
    assert error.value.code == code and vars(event) == old


@pytest.mark.parametrize("started", [False, True])
def test_noop_checks_old_start(event, started):
    if started:
        event.starts_at = NOW
    session = MagicMock()
    dispatcher = MagicMock()
    old = vars(event).copy()
    if started:
        with pytest.raises(AppError) as error:
            patch(event, {"timezone": "UTC"}, session, dispatcher)
        assert error.value.code == "EVENT_ALREADY_STARTED"
    else:
        patch(event, {"timezone": "UTC"}, session, dispatcher)
    assert vars(event) == old
    session.commit.assert_not_called()
    dispatcher.enqueue.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {"timezone": None},
        {"timezone": "Invalid/Zone"},
        {"starts_at": "2026-10-10T12:00:00"},
    ],
)
def test_invalid_schedule_schema(body):
    with pytest.raises(ValidationError):
        EventPatchRequest(**body)
