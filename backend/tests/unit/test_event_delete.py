from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.common.errors import AppError
from app.events import service
from app.events.models import EventStatus
from app.registrations import repository as registrations


@pytest.fixture
def event(monkeypatch):
    row = SimpleNamespace(id=uuid4(), owner_id=uuid4(), status=EventStatus.DRAFT)
    monkeypatch.setattr(service.repository, "find_event_for_update", lambda *_: row)
    return row


@pytest.mark.parametrize(
    "case,status,code",
    [
        ("missing", 404, "EVENT_NOT_FOUND"),
        ("other", 403, "EVENT_NOT_OWNER"),
        ("published", 409, "EVENT_NOT_DELETABLE"),
        ("cancelled", 409, "EVENT_NOT_DELETABLE"),
        ("registration", 409, "EVENT_NOT_DELETABLE"),
    ],
)
def test_delete_guards_roll_back_without_deleting(
    monkeypatch, event, case, status, code
):
    if case == "missing":
        monkeypatch.setattr(
            service.repository, "find_event_for_update", lambda *_: None
        )
    if case in {"published", "cancelled"}:
        event.status = EventStatus(case.upper())
    monkeypatch.setattr(
        registrations,
        "count_registrations",
        lambda *_: int(case == "registration"),
        raising=False,
    )
    session = MagicMock()
    with pytest.raises(AppError) as failure:
        service.delete_owned_event(
            session, uuid4() if case == "other" else event.owner_id, event.id
        )
    assert (failure.value.status, failure.value.code) == (status, code)
    session.delete.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_empty_draft_deleted_in_one_commit(monkeypatch, event):
    monkeypatch.setattr(
        registrations, "count_registrations", lambda *_: 0, raising=False
    )
    session = MagicMock()
    assert service.delete_owned_event(session, event.owner_id, event.id) is None
    session.delete.assert_called_once_with(event)
    session.commit.assert_called_once()


@pytest.mark.parametrize("step", ["count", "delete", "commit"])
def test_database_failure_rolls_back(monkeypatch, event, step):
    monkeypatch.setattr(
        registrations, "count_registrations", lambda *_: 0, raising=False
    )
    session = MagicMock()
    failure = OperationalError("statement", {}, Exception("unavailable"))
    if step == "count":

        def fail(*_):
            raise failure

        monkeypatch.setattr(registrations, "count_registrations", fail)
    else:
        getattr(session, step).side_effect = failure
    with pytest.raises(AppError) as error:
        service.delete_owned_event(session, event.owner_id, event.id)
    assert (error.value.status, error.value.code) == (503, "SERVICE_UNAVAILABLE")
    session.rollback.assert_called_once()
