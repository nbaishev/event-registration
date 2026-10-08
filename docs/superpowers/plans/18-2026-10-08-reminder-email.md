# Task 18 — Reminder Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Checklist выполняется только по отдельному execution prompt.

**Status:** Декомпозиция и решения утверждены 2026-10-08; этот файл ожидает review перед implementation.

**Goal:** Eligible CONFIRMED регистрация получает один reminder за сутки до начала, а SMTP failure восстанавливается следующим scanner run.

**Architecture:** Второй Beat scanner использует существующий notification runtime Task 17. Delivery в новой session получает Event FOR SHARE → Registration FOR UPDATE, повторно проверяет все temporal predicates, отправляет plain-text SMTP под locks и commit reminder_sent_at.

**Tech Stack:** Существующие Python/SQLAlchemy/PostgreSQL, Celery/Beat/Redis, SMTP adapter, pytest, Docker Compose; новые dependencies/services не нужны.

**Spec:** [technical-design.md](../specs/technical-design.md), §§11, 20–22, 37–39; [ADR-004](../../adr/004-notification-delivery.md).

## Task / PR boundary

**Dependencies:** [Task 17](17-2026-10-08-confirmation-email.md) merged; existing confirmed_at/schedule_updated_at/reset_state.

**Branch:** `feat/reminder-email`.

**Scope:** Reminder scanner/delivery/rendering, boundary/recovery tests, Compose smoke. Один independently reviewable PR.

**Out of scope:** Published reschedule/cancel API/UI, second reminder после переноса, automatic retries, persistent delivery history, schema changes.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) и AC этого plan; общий workflow/gate не заменять локальными tests.

## Required context / Global constraints

- Только spec/ADR sections выше; Task 17 Interfaces, инфраструктура и tests как execution context, не весь предыдущий плановый каталог.
- [engineering.md](../../agent-rules/engineering.md): Architecture, Clock, PostgreSQL, Lock ordering, Registration invariants, Email tasks, TDD, Canonical commands, Secrets, Scope restrictions.
- [development-process.md](../../development-process.md): §§4–7; [development-log.md](../../agent-rules/development-log.md) перед implementation.
- Relevant notification files Task 17 и registrations/service.py reset_state. Не добавлять missing lifecycle API в эту задачу; schedule changes в тестах допустимы через fixtures.

## Interfaces / Acceptance criteria

- Extend notifications/repository.py: `find_reminder_candidates(session: Session, now: datetime) -> list[tuple[UUID, UUID]]`.
- Extend notifications/service.py: `deliver_reminder(session: Session, clock: Clock, sender: MailSender, event_id: UUID, registration_id: UUID, app_origin: str) -> bool`; exception для SMTP/DB failure, False при missing/ineligible, True после success commit.
- Extend rendering.py: `render_reminder_email(recipient: str, event: Event, registration: Registration, app_origin: str) -> MailMessage`; русский plain text, актуальное расписание/timezone, ticket и public link, безопасный статический subject.
- Extend tasks.py/celery_app.py: scan_reminder каждые 300s, send_reminder(event_id: str, registration_id: str), без automatic retry/result backend.
- Единый eligibility predicate применяется scanner и delivery: Registration CONFIRMED; reminder_sent_at NULL; Event PUBLISHED; confirmed_at <= starts_at - 24h; schedule_updated_at <= starts_at - 24h; starts_at <= now + 24h; now < starts_at. Наличие confirmation_email_sent_at не является условием reminder.
- Delivery в новой transaction: Event FOR SHARE → Registration FOR UPDATE → clock.now() после locks → все eligibility checks и membership → актуальные данные → SMTP → reminder_sent_at = clock.now() → commit. SMTP failure rollback, очередной scan повторяет только до starts_at.
- Ровно 24h eligible; now == starts_at ineligible. Late confirmation/publication менее 24h excluded. Scanner не sends и не mutates.
- После успешно отправленного reminder любой reschedule сохраняет reminder_sent_at; второго reminder нет. При cancellation/re-registration existing reset создаёт новую eligibility попытку.
- Pending task после cancel, late reschedule, ухода за пределы window или начала Event не отправляет письмо. Concurrent tasks при success дают один SMTP send.

## Review Focus / Test strategy

Create unit/test_reminder_email.py и integration/test_reminder_email.py; extend rendering tests и scripts/verify_notifications.py.

- FixedClock матрица: starts_at - 24h ± microsecond, starts_at; confirmed_at и schedule_updated_at на cutoff и после него; DRAFT/CANCELLED/WAITLIST; already sent.
- PostgreSQL: stale enqueue recheck под locks, duplicate workers, failure → later scan recovery; current timezone/ticket в body.
- Re-registration reset и late promotion получают только подходящий reminder; sent reminder + fixture reschedule далеко в будущее не даёт второй.
- Compose smoke enqueue reminder scan через Redis для eligible fixture, проверяет worker/SMTP body и committed timestamp. Temporal tests не ждут реальное время и не используют sleep; bounded polling только runtime readiness/sink.

## Execution steps / Verification

- [ ] Updated master → новая branch/worktree/log по approved prompt.
- [ ] TDD RED unit: `uv run --frozen --project backend pytest backend/tests/unit/test_reminder_email.py backend/tests/unit/test_notification_rendering.py -q`.
- [ ] Implement shared eligibility/repository/delivery/rendering до GREEN; scanner task wiring и Beat entry.
- [ ] PostgreSQL RED/GREEN: `uv run --frozen --project backend pytest backend/tests/integration/test_reminder_email.py backend/tests/integration/test_confirmation_email.py backend/tests/integration/test_registration_cancel.py -q`, только isolated TEST_DATABASE_URL.
- [ ] Extend existing notification smoke; каждый сценарий запускается один раз в make verify. Eligibility fixtures используют controlled timestamps; не ждать Beat interval.
- [ ] `make check`, review/fixes, финальный `make verify` с confirmation и reminder smoke. Expected exit 0 и все обязательные gates без skips.
- [ ] Записать фактический evidence/limitations в log, staged secrets review; один PR. Новых API/generated schema изменений не ожидается.
