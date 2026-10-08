"""Real broker → worker → SMTP delivery on the disposable verification stack."""

import http.cookiejar
import json
import os
import sys
import time
import urllib.request
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth.models import User
from app.auth.passwords import hash_password
from app.common.clock import SystemClock
from app.events.models import Event
from app.notifications.tasks import scan_confirmation, scan_reminder
from app.registrations.models import Registration
from app.registrations.tickets import generate_ticket_code


def sink_json(path: str) -> Any:
    with urllib.request.urlopen(
        os.environ["MAILPIT_URL"] + path, timeout=5
    ) as response:
        return json.load(response)


def verify_notifications(kind: str = "confirmation") -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"], hide_parameters=True)
    owner_id, user_id, event_id, registration_id = (uuid4() for _ in range(4))
    recipient = f"notification-smoke-{user_id}@example.com"
    ticket = generate_ticket_code()
    formatted = f"{ticket[:4]}-{ticket[4:8]}-{ticket[8:]}"
    now = SystemClock().now()
    reminder = kind == "reminder"
    reschedule = kind == "reschedule"
    password = "smoke-" + uuid4().hex
    starts = now + timedelta(hours=23) if reminder else now + timedelta(days=2)
    cutoff = starts - timedelta(hours=24)
    subject = (
        "Напоминание о мероприятии — ваш билет"
        if reminder
        else "Подтверждение регистрации — ваш билет"
    )
    if reschedule:
        subject = "Изменение расписания мероприятия"
    slug = f"notification-smoke-{event_id}"
    message_ids: list[str] = []
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    User(
                        id=id,
                        email=email,
                        password_hash=hash_password(password)
                        if id == owner_id
                        else "unused-smoke-fixture",
                        created_at=now,
                        updated_at=now,
                    )
                    for id, email in (
                        (owner_id, f"smoke-owner-{owner_id}@example.com"),
                        (user_id, recipient),
                    )
                ]
            )
            session.flush()
            session.add(
                Event(
                    id=event_id,
                    owner_id=owner_id,
                    title="Проверка доставки билета",
                    description="",
                    slug=slug,
                    starts_at=starts,
                    ends_at=starts + timedelta(hours=2),
                    timezone="Asia/Bishkek",
                    capacity=1,
                    status="PUBLISHED",
                    schedule_updated_at=cutoff,
                    published_at=cutoff,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add(
                Registration(
                    id=registration_id,
                    event_id=event_id,
                    user_id=user_id,
                    status="CONFIRMED",
                    confirmed_at=cutoff,
                    ticket_code=ticket,
                    ticket_issued_at=cutoff,
                    confirmation_email_sent_at=now if reminder or reschedule else None,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        # Scanner is executed by the actual worker; eager mode is never enabled.
        if reschedule:
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
            )
            origin = os.environ["APP_ORIGIN"]
            with opener.open(origin + "/api/auth/csrf", timeout=5) as response:
                csrf = json.load(response)["csrf_token"]

            def api_request(path: str, method: str, body: dict[str, str]) -> Any:
                request = urllib.request.Request(
                    origin + path,
                    method=method,
                    data=json.dumps(body).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Origin": origin,
                        "X-CSRF-Token": csrf,
                    },
                )
                with opener.open(request, timeout=10) as response:
                    return json.load(response)

            api_request(
                "/api/auth/login",
                "POST",
                {"email": f"smoke-owner-{owner_id}@example.com", "password": password},
            )
            starts += timedelta(days=1)
            saved = api_request(
                f"/api/events/{event_id}",
                "PATCH",
                {
                    "starts_at": starts.isoformat(),
                    "ends_at": (starts + timedelta(hours=2)).isoformat(),
                },
            )
            assert saved["starts_at"] == starts.isoformat().replace("+00:00", "Z")
        else:
            scanner = scan_reminder if reminder else scan_confirmation
            scanner.delay()
        deadline = time.monotonic() + 45
        received: dict[str, Any] | None = None
        sent = False
        while time.monotonic() < deadline:
            for message in sink_json("/api/v1/messages")["messages"]:
                if any(to["Address"] == recipient for to in message["To"]):
                    message_ids.append(message["ID"])
                    received = sink_json(f"/api/v1/message/{message['ID']}")
            with Session(engine) as session:
                row = session.get(Registration, registration_id)
                sent = reschedule or (
                    row is not None
                    and (
                        row.reminder_sent_at
                        if reminder
                        else row.confirmation_email_sent_at
                    )
                    is not None
                )
            if received is not None and sent:
                break
            time.sleep(0.2)  # Bounded readiness polling, not a business time assertion.
        if received is None or not sent:
            raise RuntimeError("Notification broker/worker/SMTP smoke timed out")
        assert received["Subject"] == subject
        assert "Проверка доставки билета" in received["Text"]
        if reschedule:
            from zoneinfo import ZoneInfo

            expected = starts.astimezone(ZoneInfo("Asia/Bishkek")).strftime(
                "%Y-%m-%d %H:%M"
            )
            assert expected in received["Text"]
            assert formatted not in received["Text"]
            with Session(engine) as session:
                saved_event = session.get(Event, event_id)
                assert saved_event is not None and saved_event.starts_at == starts
        else:
            assert formatted in received["Text"]
        assert f"{os.environ['APP_ORIGIN']}/events/{slug}" in received["Text"]
        assert "Asia/Bishkek" in received["Text"] and "UTC+06:00" in received["Text"]
        assert received["HTML"] == ""
        print(
            f"Notification {kind} smoke: real broker, worker, SMTP, ticket and committed timestamp passed."
        )
    finally:
        # Delete only this smoke's rows; it runs before browser scenarios.
        with engine.begin() as connection:
            connection.execute(
                delete(Registration).where(Registration.id == registration_id)
            )
            connection.execute(delete(Event).where(Event.id == event_id))
            connection.execute(delete(User).where(User.id.in_([owner_id, user_id])))
        engine.dispose()
        if message_ids:
            request = urllib.request.Request(
                os.environ["MAILPIT_URL"] + "/api/v1/messages",
                data=json.dumps({"IDs": list(set(message_ids))}).encode(),
                headers={"Content-Type": "application/json"},
                method="DELETE",
            )
            with urllib.request.urlopen(request, timeout=5):
                pass


if __name__ == "__main__":
    verify_notifications()
    verify_notifications("reminder")
    verify_notifications("reschedule")
