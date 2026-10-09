from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.common.clock import FixedClock
from app.common.errors import AppError
from app.events import service

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
        timezone="Asia/Bishkek",
        title="Conference",
        slug="conference",
        published_at=NOW - timedelta(days=1),
        schedule_updated_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
        cancelled_at=None,
    )
    monkeypatch.setattr(service.repository, "find_event_for_update", lambda *_: event)
    monkeypatch.setattr(
        service,
        "find_transition_recipients",
        lambda *_: ["one@example.com", "two@example.com"],
    )
    return event


def cancel(event, session=None, dispatcher=None, owner=None, clock=None):
    return service.cancel_owned_event(
        session or MagicMock(),
        clock or FixedClock(NOW),
        owner or event.owner_id,
        event.id,
        notification_dispatcher=dispatcher or MagicMock(),
    )


def test_cancel_snapshot_after_commit_and_unchanged_fields(event):
    before = vars(event).copy()
    committed, notices = [], []
    session = MagicMock()
    session.commit.side_effect = lambda: committed.append(True)

    def enqueue(notice):
        assert committed == [True]
        notices.append(notice)

    saved = cancel(event, session, SimpleNamespace(enqueue=enqueue))
    assert saved is event
    assert vars(event) == before | {
        "status": "CANCELLED",
        "cancelled_at": NOW,
        "updated_at": NOW,
    }
    assert [n.recipient for n in notices] == ["one@example.com", "two@example.com"]
    assert all(
        n.kind == "EVENT_CANCELLED"
        and n.occurred_at == NOW
        and n.starts_at == before["starts_at"]
        for n in notices
    )


@pytest.mark.parametrize(
    "state,start,foreign,code,status",
    [
        ("PUBLISHED", NOW, False, "EVENT_ALREADY_STARTED", 409),
        (
            "PUBLISHED",
            NOW - timedelta(microseconds=1),
            False,
            "EVENT_ALREADY_STARTED",
            409,
        ),
        ("DRAFT", NOW, False, "EVENT_NOT_PUBLISHED", 409),
        ("CANCELLED", NOW, False, "EVENT_CANCELLED", 409),
        ("CANCELLED", NOW + timedelta(days=1), False, "EVENT_CANCELLED", 409),
        ("CANCELLED", NOW, True, "EVENT_NOT_OWNER", 403),
    ],
)
def test_error_precedence_without_mutations(event, state, start, foreign, code, status):
    event.status, event.starts_at = state, start
    before = vars(event).copy()
    session, dispatcher = MagicMock(), MagicMock()
    with pytest.raises(AppError) as error:
        cancel(event, session, dispatcher, uuid4() if foreign else None)
    assert (error.value.code, error.value.status) == (code, status)
    assert vars(event) == before
    session.commit.assert_not_called()
    dispatcher.enqueue.assert_not_called()


def test_missing_event(event, monkeypatch):
    monkeypatch.setattr(service.repository, "find_event_for_update", lambda *_: None)
    with pytest.raises(AppError) as error:
        cancel(event)
    assert error.value.code == "EVENT_NOT_FOUND"


def test_clock_read_only_after_lock(event, monkeypatch):
    locked = []
    monkeypatch.setattr(
        service.repository,
        "find_event_for_update",
        lambda *_: locked.append(True) or event,
    )

    class Clock:
        def now(self):
            assert locked == [True]
            return NOW

    cancel(event, clock=Clock())


def test_failed_commit_never_enqueues(event):
    session, dispatcher = MagicMock(), MagicMock()
    session.commit.side_effect = OperationalError("injected", {}, Exception())
    with pytest.raises(AppError) as error:
        cancel(event, session, dispatcher)
    assert error.value.code == "SERVICE_UNAVAILABLE"
    session.rollback.assert_called_once()
    dispatcher.enqueue.assert_not_called()
