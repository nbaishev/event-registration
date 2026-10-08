from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from threading import Event as Signal
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.common.clock import FixedClock
from app.events.models import Event, EventStatus
from app.notifications.repository import find_reminder_candidates
from app.notifications.service import deliver_reminder
from app.registrations.models import Registration
from app.registrations.service import cancel_registration, register_for_event

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)
ORIGIN = "https://events.example.com"


class RecordingSender:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


@pytest.fixture
def confirmed(auth_database):
    owner, guest, event_id, registration_id = [uuid4() for _ in range(4)]
    with Session(auth_database) as session:
        session.add_all(
            [
                User(
                    id=id,
                    email=f"{id}@example.com",
                    password_hash="unused",
                    created_at=NOW,
                    updated_at=NOW,
                )
                for id in (owner, guest)
            ]
        )
        session.flush()
        session.add(
            Event(
                id=event_id,
                owner_id=owner,
                title="Конференция",
                description="",
                slug=f"event-{event_id}",
                starts_at=NOW + timedelta(days=1),
                ends_at=NOW + timedelta(days=1, hours=2),
                timezone="Asia/Bishkek",
                capacity=1,
                status=EventStatus.PUBLISHED,
                published_at=NOW,
                schedule_updated_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add(
            Registration(
                id=registration_id,
                event_id=event_id,
                user_id=guest,
                status="CONFIRMED",
                confirmed_at=NOW,
                ticket_code="7K4P9Q2M8RTA",
                ticket_issued_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()
    return event_id, registration_id, guest


def candidates(db, now=NOW):
    with Session(db) as session:
        return find_reminder_candidates(session, now)


def timestamp(db, id):
    with Session(db) as session:
        return session.get(Registration, id).reminder_sent_at


def deliver(db, ids, sender, clock=None):
    with Session(db) as session:
        return deliver_reminder(
            session, clock or FixedClock(NOW), sender, ids[0], ids[1], ORIGIN
        )


@pytest.mark.parametrize(
    "change",
    [
        "draft",
        "event_cancel",
        "waiting",
        "cancelled",
        "sent",
        "started",
        "eligible",
        "confirmation_sent",
        "outside",
        "late_confirmation",
        "late_schedule",
    ],
)
def test_scanner_selection(auth_database, confirmed, change):
    e, r, _ = confirmed
    with Session(auth_database) as s:
        event, row = s.get(Event, e), s.get(Registration, r)
        if change == "draft":
            event.status = "DRAFT"
        if change == "event_cancel":
            event.status = "CANCELLED"
        if change == "started":
            event.starts_at = NOW
        if change == "outside":
            event.starts_at += timedelta(microseconds=1)
        if change == "late_confirmation":
            row.confirmed_at += timedelta(microseconds=1)
        if change == "late_schedule":
            event.schedule_updated_at += timedelta(microseconds=1)
        if change == "confirmation_sent":
            row.confirmation_email_sent_at = NOW
        if change == "sent":
            row.reminder_sent_at = NOW
        if change in ("waiting", "cancelled"):
            from app.registrations.service import reset_state

            reset_state(row, NOW)
            row.status = "WAITLIST" if change == "waiting" else "CANCELLED"
            if change == "waiting":
                row.waitlisted_at = NOW
            else:
                row.cancelled_at = NOW
        s.commit()
    assert candidates(auth_database) == (
        [(e, r)] if change in ("eligible", "confirmation_sent") else []
    )


def test_send_current_data_and_commit_timestamp(auth_database, confirmed):
    sender = RecordingSender()
    with Session(auth_database) as s:
        s.get(Registration, confirmed[1]).ticket_code = "23456789ABCD"
        s.get(User, confirmed[2]).email = "updated@example.com"
        s.get(Event, confirmed[0]).title = "Актуальное название"
        s.get(Event, confirmed[0]).timezone = "Europe/Berlin"
        s.commit()

    class AdvancingClock:
        def __init__(self):
            self.calls = 0

        def now(self):
            self.calls += 1
            return NOW + timedelta(seconds=self.calls)

    assert deliver(auth_database, confirmed, sender, AdvancingClock())
    assert timestamp(auth_database, confirmed[1]) == NOW + timedelta(seconds=2)
    assert sender.messages[0].recipient == "updated@example.com"
    assert "2345-6789-ABCD" in sender.messages[0].body
    assert "Актуальное название" in sender.messages[0].body
    assert "Europe/Berlin" in sender.messages[0].body
    assert "2026-10-09 14:00" in sender.messages[0].body
    assert not deliver(auth_database, confirmed, sender)
    assert len(sender.messages) == 1 and candidates(auth_database) == []


@pytest.mark.parametrize(
    "change",
    [
        "event_cancel",
        "registration_cancel",
        "started",
        "outside",
        "late_schedule",
        "late_confirmation",
        "missing_event",
        "missing_registration",
        "foreign",
    ],
)
def test_queued_delivery_rechecks(auth_database, confirmed, change):
    assert candidates(auth_database) == [confirmed[:2]]
    e, r, user = confirmed
    with Session(auth_database) as s:
        if change == "event_cancel":
            s.get(Event, e).status = "CANCELLED"
        if change == "started":
            s.get(Event, e).starts_at = NOW
        if change == "outside":
            s.get(Event, e).starts_at += timedelta(microseconds=1)
        if change == "late_schedule":
            s.get(Event, e).schedule_updated_at += timedelta(microseconds=1)
        if change == "late_confirmation":
            s.get(Registration, r).confirmed_at += timedelta(microseconds=1)
        s.commit()
    if change == "registration_cancel":
        with Session(auth_database) as s:
            cancel_registration(s, FixedClock(NOW), user, e)
    if change in ("missing_event", "foreign"):
        e = uuid4()
    if change == "missing_registration":
        r = uuid4()
    sender = RecordingSender()
    assert not deliver(auth_database, (e, r), sender)
    assert sender.messages == []
    assert timestamp(auth_database, confirmed[1]) is None


def test_foreign_registration_belongs_to_other_locked_event(auth_database, confirmed):
    with Session(auth_database) as s:
        original = s.get(Event, confirmed[0])
        other = Event(
            id=uuid4(),
            owner_id=original.owner_id,
            title="Other",
            description="",
            slug="other",
            starts_at=original.starts_at,
            ends_at=original.ends_at,
            timezone="UTC",
            capacity=1,
            status="PUBLISHED",
            schedule_updated_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        s.add(other)
        s.commit()
        other_id = other.id
    sender = RecordingSender()
    assert not deliver(auth_database, (other_id, confirmed[1]), sender)
    assert sender.messages == []


def test_smtp_failure_scan_recovers(auth_database, confirmed):
    class FailedSender:
        def send(self, message):
            raise OSError("offline")

    with pytest.raises(OSError):
        deliver(auth_database, confirmed, FailedSender())
    assert timestamp(auth_database, confirmed[1]) is None
    assert candidates(auth_database) == [confirmed[:2]]
    assert deliver(auth_database, confirmed, RecordingSender())


def test_commit_failure_retains_duplicate_risk(auth_database, confirmed, monkeypatch):
    sender = RecordingSender()
    with Session(auth_database) as s:

        def fail():
            raise RuntimeError("commit unavailable")

        monkeypatch.setattr(s, "commit", fail)
        with pytest.raises(RuntimeError):
            deliver_reminder(s, FixedClock(NOW), sender, *confirmed[:2], ORIGIN)
        assert not s.in_transaction()
    assert timestamp(auth_database, confirmed[1]) is None
    assert deliver(auth_database, confirmed, sender)
    assert len(sender.messages) == 2


def test_reregistration_sends_new_ticket(auth_database, confirmed):
    sender = RecordingSender()
    assert deliver(auth_database, confirmed, sender)
    with Session(auth_database) as s:
        cancel_registration(s, FixedClock(NOW), confirmed[2], confirmed[0])
        register_for_event(s, FixedClock(NOW), confirmed[2], confirmed[0])
    assert deliver(auth_database, confirmed, sender)
    assert len(sender.messages) == 2
    assert "7K4P-9Q2M-8RTA" not in sender.messages[1].body


@pytest.mark.parametrize("source", ["cancel", "capacity"])
@pytest.mark.parametrize("late", [False, True])
def test_promoted_registration_uses_scanner(auth_database, confirmed, source, late):
    user = uuid4()
    promotion_time = NOW + timedelta(microseconds=1) if late else NOW
    with Session(auth_database) as s:
        s.add(
            User(
                id=user,
                email="waiting@example.com",
                password_hash="unused",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        s.commit()
        waiting = register_for_event(s, FixedClock(NOW), user, confirmed[0])
        assert waiting.status == "WAITLIST"
        if source == "cancel":
            cancel_registration(
                s, FixedClock(promotion_time), confirmed[2], confirmed[0]
            )
        else:
            from app.events import repository
            from app.registrations.promotion import fill_available_slots

            event = repository.find_event_for_update(s, confirmed[0])
            event.capacity = 2
            s.flush()
            fill_available_slots(s, event, promotion_time)
            s.commit()
    assert ((confirmed[0], waiting.id) in candidates(auth_database)) is (not late)
    sender = RecordingSender()
    assert deliver(auth_database, (confirmed[0], waiting.id), sender) is (not late)
    if not late:
        assert sender.messages[0].recipient == "waiting@example.com"


def test_duplicate_workers_one_send_and_locks_through_smtp(auth_database, confirmed):
    barrier = Barrier(2)
    sender = RecordingSender()

    def send(message):
        # Both locks remain held during external SMTP.
        for table, id in (("events", confirmed[0]), ("registrations", confirmed[1])):
            with (
                pytest.raises(OperationalError) as error,
                auth_database.begin() as conn,
            ):
                conn.execute(
                    text(f"SELECT id FROM {table} WHERE id=:id FOR UPDATE NOWAIT"),
                    {"id": id},
                )
            assert error.value.orig.sqlstate == "55P03"
        sender.messages.append(message)

    sender.send = send

    def attempt():
        barrier.wait(timeout=5)
        return deliver(auth_database, confirmed, sender)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt) for _ in range(2)]
        assert sorted(f.result(timeout=10) for f in futures) == [False, True]
    assert len(sender.messages) == 1
    assert timestamp(auth_database, confirmed[1]) == NOW


def test_clock_and_state_read_after_event_lock(auth_database, confirmed):
    ready = Signal()
    pid = []
    sender = RecordingSender()
    with Session(auth_database) as locked:
        row = locked.scalar(
            select(Event).where(Event.id == confirmed[0]).with_for_update()
        )
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))

        def attempt():
            with Session(auth_database) as s:
                pid.append(s.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return deliver_reminder(
                    s, FixedClock(NOW), sender, *confirmed[:2], ORIGIN
                )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(attempt)
            try:
                assert ready.wait(5)
                deadline = monotonic() + 5
                with auth_database.connect() as monitor:
                    while monotonic() < deadline:
                        if blocker in monitor.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": pid[0]}
                        ):
                            break
                    else:
                        pytest.fail("Delivery did not wait for Event lock")
                row.starts_at = NOW
                locked.commit()
            finally:
                locked.rollback()
            assert future.result(timeout=10) is False
    assert sender.messages == []


def test_different_registrations_can_send_independently(auth_database, confirmed):
    user_id, row_id = uuid4(), uuid4()
    with Session(auth_database) as s:
        s.add(
            User(
                id=user_id,
                email="second@example.com",
                password_hash="unused",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        s.flush()
        s.add(
            Registration(
                id=row_id,
                event_id=confirmed[0],
                user_id=user_id,
                status="CONFIRMED",
                confirmed_at=NOW,
                ticket_code="23456789ABCD",
                ticket_issued_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        s.commit()
    barrier = Barrier(2)
    sender = RecordingSender()

    def send(message):
        barrier.wait(timeout=5)
        sender.messages.append(message)

    sender.send = send
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(deliver, auth_database, (confirmed[0], id), sender)
            for id in (confirmed[1], row_id)
        ]
        assert all(f.result(timeout=10) for f in futures)
    assert len(sender.messages) == 2


def test_clock_is_sampled_after_registration_lock(auth_database, confirmed):
    ready, clock_called = Signal(), Signal()
    pid = []
    current = [NOW]

    class MovingClock:
        def now(self):
            clock_called.set()
            return current[0]

    sender = RecordingSender()
    with Session(auth_database) as locked:
        locked.scalar(
            select(Registration)
            .where(Registration.id == confirmed[1])
            .with_for_update()
        )
        blocker = locked.scalar(text("SELECT pg_backend_pid()"))

        def attempt():
            with Session(auth_database) as s:
                pid.append(s.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return deliver_reminder(
                    s, MovingClock(), sender, *confirmed[:2], ORIGIN
                )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(attempt)
            try:
                assert ready.wait(5)
                deadline = monotonic() + 5
                with auth_database.connect() as monitor:
                    while monotonic() < deadline:
                        if blocker in monitor.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": pid[0]}
                        ):
                            break
                    else:
                        pytest.fail("Delivery did not wait for Registration lock")
                assert not clock_called.is_set()
                current[0] = NOW + timedelta(days=1)
                locked.commit()
            finally:
                locked.rollback()
            assert future.result(timeout=10) is False
    assert clock_called.is_set() and sender.messages == []


def test_sent_reminder_reschedule_never_sends_second(auth_database, confirmed):
    sender = RecordingSender()
    assert deliver(auth_database, confirmed, sender)
    with Session(auth_database) as s:
        event = s.get(Event, confirmed[0])
        event.starts_at += timedelta(days=7)
        event.ends_at += timedelta(days=7)
        event.schedule_updated_at = NOW
        s.commit()
    later = NOW + timedelta(days=7)
    assert candidates(auth_database, later) == []
    assert not deliver(auth_database, confirmed, sender, FixedClock(later))
    assert len(sender.messages) == 1


def test_late_reregistration_has_no_reminder(auth_database, confirmed):
    late = NOW + timedelta(microseconds=1)
    with Session(auth_database) as s:
        cancel_registration(s, FixedClock(late), confirmed[2], confirmed[0])
        register_for_event(s, FixedClock(late), confirmed[2], confirmed[0])
    assert candidates(auth_database, late) == []
    sender = RecordingSender()
    assert not deliver(auth_database, confirmed, sender, FixedClock(late))
    assert sender.messages == []


def test_failure_after_start_is_not_recovered(auth_database, confirmed):
    class FailedSender:
        def send(self, message):
            raise OSError("offline")

    with pytest.raises(OSError):
        deliver(auth_database, confirmed, FailedSender())
    at_start = NOW + timedelta(days=1)
    assert candidates(auth_database, at_start) == []
    assert not deliver(
        auth_database, confirmed, RecordingSender(), FixedClock(at_start)
    )
