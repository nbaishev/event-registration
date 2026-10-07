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
        ("cancelled", "EVENT_CANCELLED"),
        ("start", "EVENT_ALREADY_STARTED"),
        ("end", "EVENT_FINISHED"),
        ("absent", "REGISTRATION_NOT_FOUND"),
        ("repeat", "REGISTRATION_NOT_FOUND"),
        ("checked", "TICKET_ALREADY_CHECKED_IN"),
    ],
)
def test_cancel_guards(monkeypatch, case, code):
    event = SimpleNamespace(
        id=uuid4(),
        status=EventStatus.PUBLISHED,
        starts_at=NOW + timedelta(hours=1),
        ends_at=NOW + timedelta(hours=2),
    )
    if case in ("draft", "cancelled"):
        event.status = EventStatus.DRAFT if case == "draft" else EventStatus.CANCELLED
    if case == "start":
        event.starts_at = NOW
    if case == "end":
        event.ends_at = NOW
    row = SimpleNamespace(
        status="CANCELLED" if case == "repeat" else "CONFIRMED",
        checked_in_at=NOW if case == "checked" else None,
    )
    monkeypatch.setattr(
        service.events,
        "find_event_for_update",
        lambda *_: None if case == "missing" else event,
    )
    monkeypatch.setattr(
        service.repository,
        "find_registration_for_update",
        lambda *_: None if case == "absent" else row,
    )
    with pytest.raises(AppError) as error:
        service.cancel_registration(MagicMock(), FixedClock(NOW), uuid4(), event.id)
    assert error.value.code == code
    assert row.status == ("CANCELLED" if case == "repeat" else "CONFIRMED")


@pytest.mark.parametrize("status", ["CONFIRMED", "WAITLIST"])
def test_cancel_clears_state(monkeypatch, status):
    event = SimpleNamespace(
        id=uuid4(),
        status=EventStatus.PUBLISHED,
        starts_at=NOW + timedelta(hours=1),
        ends_at=NOW + timedelta(hours=2),
        capacity=1,
    )
    row = SimpleNamespace(
        status=status,
        confirmed_at=NOW,
        waitlisted_at=NOW,
        cancelled_at=None,
        ticket_code="old",
        ticket_issued_at=NOW,
        checked_in_at=None,
        confirmation_email_sent_at=NOW,
        reminder_sent_at=NOW,
        updated_at=NOW - timedelta(minutes=1),
    )
    monkeypatch.setattr(service.events, "find_event_for_update", lambda *_: event)
    monkeypatch.setattr(
        service.repository, "find_registration_for_update", lambda *_: row
    )
    monkeypatch.setattr(service.repository, "read_snapshot", lambda *_: row)
    monkeypatch.setattr(service.repository, "count_confirmed", lambda *_: 0)
    # No queued rows: the state reset itself remains the real operation.
    monkeypatch.setattr(service.repository, "find_waitlist_for_update", lambda *_: [])
    result = service.cancel_registration(
        MagicMock(), FixedClock(NOW), uuid4(), event.id
    )
    assert result.status == "CANCELLED"
    assert result.cancelled_at == result.updated_at == NOW
    for field in (
        "confirmed_at",
        "waitlisted_at",
        "ticket_code",
        "ticket_issued_at",
        "checked_in_at",
        "confirmation_email_sent_at",
        "reminder_sent_at",
    ):
        assert getattr(result, field) is None


@pytest.mark.parametrize(
    "status,starts",
    [
        ("DRAFT", NOW + timedelta(hours=1)),
        ("CANCELLED", NOW + timedelta(hours=1)),
        ("PUBLISHED", NOW),
    ],
)
def test_promotion_guard(monkeypatch, status, starts):
    from app.registrations import promotion

    event = SimpleNamespace(id=uuid4(), status=status, starts_at=starts, capacity=1)

    def forbidden(*_):
        pytest.fail("Ineligible event must not allocate seats")

    monkeypatch.setattr(service.repository, "count_confirmed", forbidden)
    assert promotion.fill_available_slots(MagicMock(), event, NOW) == []


@pytest.mark.parametrize("status", [403, 404, 409, 503])
def test_cancellation_errors_are_no_store(status):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.common.csrf import AuthSecurityMiddleware
    from app.common.errors import app_error_handler

    probe = FastAPI()
    probe.add_middleware(AuthSecurityMiddleware)
    probe.add_exception_handler(AppError, app_error_handler)

    @probe.delete("/api/events/probe/registration")
    def fail():
        raise AppError(status, "PROBE_ERROR", "Private registration error.")

    with TestClient(probe) as client:
        headers = {}
        if status != 403:
            client.cookies.set("csrf_token", "token")
            headers = {"Origin": "http://localhost:8080", "X-CSRF-Token": "token"}
        response = client.delete("/api/events/probe/registration", headers=headers)
    assert response.status_code == status
    assert response.headers.get("cache-control") == "no-store"
