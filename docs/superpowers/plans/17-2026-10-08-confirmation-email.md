# Task 17 — Confirmation / Ticket Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Выполнять checklist по отдельной execution-команде пользователя; сейчас implementation не начинается.

**Status:** Декомпозиция и решения опроса утверждены пользователем 2026-10-08. Файл подготовлен для review перед implementation; approval самого файла ещё не получен.

**Goal:** CONFIRMED участник получает письмо с актуальным ticket code после регистрации, re-registration или FIFO promotion; scanner восстанавливает неотправленные письма.

**Architecture:** Celery Beat enqueue scanner каждые 300 секунд; scanner выбирает PostgreSQL candidates и enqueue delivery tasks. Delivery use-case в новой session блокирует Event FOR SHARE, затем Registration FOR UPDATE, повторяет проверки, отправляет SMTP и сохраняет confirmation_email_sent_at одним commit. Promotion использует тот же pipeline, без отдельного признака происхождения confirmation.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/PostgreSQL, Celery/Beat, Redis broker, стандартные smtplib/email, pytest, Docker Compose. Celery dependency и Redis transport фиксируются backend/uv.lock; отдельный result backend не нужен.

**Spec:** [technical-design.md](../specs/technical-design.md), §§7, 11, 13, 16–17, 19, 21, 37–39; [ADR-004](../../adr/004-notification-delivery.md).

## Task / PR boundary

**Dependencies:** Merged registration, cancellation, re-registration, capacity/FIFO promotion и ticket generation; существующие Clock и quality gates.

**Branch:** `feat/confirmation-email`.

**Scope:** Рабочий confirmation vertical slice вместе с Redis/worker/Beat/SMTP configuration, plain-text rendering и изолированным delivery smoke. Один PR.

**Out of scope:** Reminder, reschedule/cancellation emails, отдельное promotion письмо/state, QR/PDF/HTML, UI notification settings, outbox, EmailDelivery subsystem, unrelated refactoring.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md), engineering quality gate и Acceptance criteria этого файла. Реализация и PR только после отдельного execution prompt.

## Required context / Global constraints

- Этот plan; указанные выше sections spec и ADR-004.
- [engineering.md](../../agent-rules/engineering.md): Architecture, Clock, PostgreSQL, Lock ordering, Registration invariants, Email tasks, Secrets, TDD, Canonical commands, Scope restrictions; Migrations только при persistent schema change.
- [development-process.md](../../development-process.md): §§4–7; [development-log.md](../../agent-rules/development-log.md) перед implementation.
- Existing files: registrations/models.py, service.py: reset_state/confirm_registration, promotion.py, events/models.py, db/session.py, common/config.py и clock.py; Compose/verification только для инфраструктуры этой задачи.
- PostgreSQL — источник истины; Redis только Celery. Scanner не отправляет SMTP и не устанавливает timestamps. Clock внедряется в use-case, SystemClock создаётся entrypoint.
- Без новой Ticket/EmailDelivery table и outbox. Существующих columns достаточно; каждый новый persistent index требует migration. Индексы без подтверждённой необходимости не добавлять.
- Следовать lifecycle/checks/log/secrets правилам по ссылкам, не дублировать их реализацию.

## Interfaces / file responsibilities

- Create `backend/app/notifications/contracts.py`: immutable `MailMessage(recipient: str, subject: str, body: str)` и `MailSender.send(message: MailMessage) -> None`; exception означает неуспех.
- Create `backend/app/notifications/rendering.py`: `render_ticket_email(recipient: str, event: Event, registration: Registration, app_origin: str) -> MailMessage`. Русский plain text: название, начало/окончание в Event.timezone с UTC offset/IANA name, ticket_code, ссылка APP_ORIGIN/events/{slug}. Subject без вставки непроверенного пользовательского текста в SMTP headers.
- Create `backend/app/notifications/smtp.py`: SMTP adapter; заголовки собираются через EmailMessage, recipient/from не интерполируются в raw headers.
- Create `backend/app/notifications/repository.py`: `find_confirmation_candidates(session: Session, now: datetime) -> list[tuple[UUID, UUID]]`, tuples `(event_id, registration_id)`. Selection filters ниже; join Event и Registration. Candidate session закрывается до enqueue.
- Create `backend/app/notifications/service.py`: `deliver_confirmation(session: Session, clock: Clock, sender: MailSender, event_id: UUID, registration_id: UUID, app_origin: str) -> bool`; False для missing/ineligible, True после успешного send/commit. Входная session новая и без заранее загруженных ORM объектов; Registration должен принадлежать locked Event.
- Create `backend/app/notifications/celery_app.py`, `tasks.py`: Celery app без result backend; JSON serialization; `scan_confirmation` enqueue `send_confirmation(event_id: str, registration_id: str)`. Task adapters создают session/clock/sender и делегируют business logic. Оба UUID передаются строками; email/ticket не попадают в confirmation payload.
- Create `backend/app/notifications/__init__.py`; modify config.py, backend/pyproject.toml/uv.lock, compose.yaml, compose.test.yaml, .env.example, scripts/verification.py. Новые test files: unit/test_confirmation_email.py, unit/test_notification_rendering.py, unit/test_smtp.py, integration/test_confirmation_email.py и `scripts/verify_notifications.py` для Compose smoke.
- Settings: `REDIS_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, optional `SMTP_USERNAME`/`SMTP_PASSWORD` (SecretStr), `SMTP_SECURITY` enum none/starttls/tls, `SMTP_TIMEOUT_SECONDS` positive, default 10. Credentials задаются парой; auth только после TLS для starttls/tls. Local defaults: test sink, port 1025, security none, no credentials. Production credentials вне Git.
- Compose: redis, worker, beat используют один backend image; worker/beat получают DB/broker/SMTP env явно. Один Beat; FastAPI сохраняет один uvicorn worker для SSE. Local SMTP sink — Mailpit; только test/development, наружу SMTP не публикуется. Container image tags закрепить явно при implementation, не использовать latest. Test sink HTTP API доступен verifier через localhost ephemeral port.

## Acceptance criteria

1. Beat расписание confirmation scan — каждые 300 секунд. Scanner выбирает только Registration CONFIRMED, confirmation_email_sent_at NULL, Event PUBLISHED, now < starts_at; SMTP не вызывается.
2. Delivery locks строго Event FOR SHARE → Registration FOR UPDATE. После locks заново получает clock.now() и проверяет filters scanner, принадлежность Event и ticket_code NOT NULL. Email/Event/ticket читаются под locks; отсутствующие rows пропускаются.
3. Registration/Event locks удерживаются через SMTP до commit. После success timestamp — clock.now(); commit сохраняет его. SMTP/DB failure rollback; timestamp не установлен, следующий scan восстанавливает доставку.
4. Task не использует automatic retry. Повторный scan после старта не enqueue; queued task после старта/отмены повторно проверяет состояние и не отправляет письмо.
5. Duplicate concurrent tasks сериализуются по Registration; после успешного commit второй send отсутствует. Риск SMTP accepted → crash/commit failure → duplicate сознательно сохраняется по ADR-004.
6. Promotion после registration cancellation и capacity increase становится eligible без direct post-commit enqueue из registration service. Re-registration отправляет новый ticket; письмо не выдаётся WAITLIST/CANCELLED.
7. SMTP adapter поддерживает none/starttls/tls, optional auth и bounded timeout; failure не пишет credentials, recipient, body или ticket в logs. Безопасный failure log содержит task kind и Event/Registration IDs.
8. `make up` запускает Redis, worker и Beat. Worker выполняет task из broker и отправляет письмо в local sink. `make verify` проверяет этот путь автоматически на isolated stack; отсутствие worker/SMTP не считается успешным skip.

## Review Focus / Test strategy

TDD unit predicates/rendering/SMTP security; настоящий PostgreSQL для serialization. Проверять observable SMTP calls и committed state, а не только наличие locks в mock.

- Scanner исключает DRAFT/CANCELLED, WAITLIST/CANCELLED, sent registration, now == starts_at.
- Delivery state изменился после enqueue: event cancel, registration cancel, re-registration с новым ticket, starts_at boundary; актуальный ticket проверяется по отправленному body.
- Два workers одной регистрации: только один send при success; different registrations могут обрабатываться независимо.
- SMTP failure → timestamp NULL → следующий scan/send success. DB commit failure после SMTP фиксирует известный duplicate risk, не утверждать exactly-once.
- Promotion обоих источников и reset_state regressions; чужой registration_id не отправляет письмо.
- Реальная SMTP adapter integration в sink: recipient, subject, plain text/timezone/ticket/link, timeout/TLS/auth unit tests; malicious title не создаёт дополнительные headers.
- Concurrency coordination — barriers/events, без sleep как доказательства locking/time boundaries.

## Execution steps / Verification

- [ ] Создать branch/worktree и development log по approved execution prompt; baseline только согласно engineering workflow.
- [ ] Написать unit tests → RED: `uv run --frozen --project backend pytest backend/tests/unit/test_confirmation_email.py backend/tests/unit/test_notification_rendering.py backend/tests/unit/test_smtp.py -q`.
- [ ] Contracts/rendering/config/SMTP adapter и confirmation predicate/use-case до GREEN; не менять registration business flow ради email.
- [ ] PostgreSQL RED/GREEN: `uv run --frozen --project backend pytest backend/tests/integration/test_confirmation_email.py backend/tests/integration/test_waitlist_promotion.py backend/tests/integration/test_registration_cancel.py -q`. TEST_DATABASE_URL только отдельной disposable PostgreSQL, fixture очищает schema.
- [ ] Подключить Celery/Beat/Compose, dependency lock и .env.example. Add verify_notifications.py: isolated Event/User/Registration fixture, enqueue scanner через real broker, bounded poll sink/state, assertion ticket email; не ждать пять минут Beat. Отдельный unit assertion подтверждает Beat interval 300s. Smoke вызывается ровно один раз из make verify после stack readiness; fixtures исключены из других browser scenarios и cleanup гарантирован.
- [ ] `make check`; review git diff и fixes; финальный `make verify` после review с реальным delivery smoke. Expected: exit 0, все существующие gates плюс notification smoke успешны. Не запускать make test промежуточно.
- [ ] Evidence/known limitations в log; staged diff secrets review; один PR со ссылкой на plan. Код/конфигурация после успешного verify требуют релевантной повторной проверки.
