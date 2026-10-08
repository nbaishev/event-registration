"""Real broker → worker → SMTP delivery on the disposable verification stack."""

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
from app.common.clock import SystemClock
from app.events.models import Event
from app.notifications.tasks import scan_confirmation
from app.registrations.models import Registration
from app.registrations.tickets import generate_ticket_code


def sink_json(path: str) -> Any:
    with urllib.request.urlopen(
        os.environ["MAILPIT_URL"] + path, timeout=5
    ) as response:
        return json.load(response)


def verify_notifications() -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"], hide_parameters=True)
    owner_id, user_id, event_id, registration_id = (uuid4() for _ in range(4))
    recipient = f"notification-smoke-{user_id}@example.com"
    ticket = generate_ticket_code()
    formatted = f"{ticket[:4]}-{ticket[4:8]}-{ticket[8:]}"
    now = SystemClock().now()
    slug = f"notification-smoke-{event_id}"
    message_ids: list[str] = []
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    User(
                        id=id,
                        email=email,
                        password_hash="unused-smoke-fixture",
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
                    starts_at=now + timedelta(days=2),
                    ends_at=now + timedelta(days=2, hours=2),
                    timezone="Asia/Bishkek",
                    capacity=1,
                    status="PUBLISHED",
                    schedule_updated_at=now,
                    published_at=now,
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
                    confirmed_at=now,
                    ticket_code=ticket,
                    ticket_issued_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        # Scanner is executed by the actual worker; eager mode is never enabled.
        scan_confirmation.delay()
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
                sent = row is not None and row.confirmation_email_sent_at is not None
            if received is not None and sent:
                break
            time.sleep(0.2)  # Bounded readiness polling, not a business time assertion.
        if received is None or not sent:
            raise RuntimeError("Notification broker/worker/SMTP smoke timed out")
        assert received["Subject"] == "Подтверждение регистрации — ваш билет"
        assert "Проверка доставки билета" in received["Text"]
        assert formatted in received["Text"]
        assert f"{os.environ['APP_ORIGIN']}/events/{slug}" in received["Text"]
        assert "Asia/Bishkek" in received["Text"] and "UTC+06:00" in received["Text"]
        assert received["HTML"] == ""
        print(
            "Notification smoke: real broker, worker, SMTP, ticket and committed timestamp passed."
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
