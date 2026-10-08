# Task 20 — Event Cancellation and Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Реализация только по отдельной execution-команде после review plan.

**Status:** Декомпозиция и решения опроса утверждены 2026-10-08; файл ожидает review перед implementation.

**Goal:** Organizer отменяет будущее PUBLISHED событие; public page показывает CANCELLED, CONFIRMED/WAITLIST участники получают snapshot cancellation email, дальнейшие registration/check-in/email операции учитывают отмену.

**Architecture:** Cancel use-case получает Event FOR UPDATE, проверяет owner/state/time, обновляет Event и snapshot получателей в одной transaction. После commit использует TransitionDispatcher Task 19. Registration rows не переводятся массово в CANCELLED; cancellation и delivery/check-in сериализуются Event lock.

**Tech Stack:** Existing FastAPI/SQLAlchemy/PostgreSQL, notification runtime/transition dispatcher, React/MUI/TanStack Query, pytest/Vitest/Playwright.

**Spec:** [technical-design.md](../specs/technical-design.md), §§8, 11, 18–23, 34–35, 37–39; [ADR-004](../../adr/004-notification-delivery.md). Дополнение lifecycle contract по опросу: отмена только до starts_at; repeat cancel → 409 EVENT_CANCELLED.

## Task / PR boundary

**Dependencies:** [Task 19](19-2026-10-08-event-reschedule.md) merged (включая Tasks 17–18 runtime); existing public CANCELLED rendering и check-in/registration status guards.

**Branch:** `feat/event-cancellation`.

**Scope:** POST cancel API/use-case, snapshot dispatch, organizer confirmation UI/cache updates, race/integration/browser/email tests. Один vertical-slice PR.

**Out of scope:** Participant registration cancellation, массовое изменение Registration status/tickets/check-ins, restore/delete Event, отмена после начала, automatic retry/guaranteed delivery/outbox, unrelated live dashboard changes.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) и AC ниже; UI screenshot и SMTP runtime evidence.

## Required context / Global constraints

- Spec/ADR sections выше, Task 19 Interfaces для TransitionNotice/Dispatcher и best-effort dispatch; Tasks 17–18 delivery recheck contracts.
- [engineering.md](../../agent-rules/engineering.md): Architecture, Clock, PostgreSQL, Lock ordering, Check-in, Email tasks, Generated API, TDD, Secrets, Canonical commands, Scope restrictions.
- [development-process.md](../../development-process.md): §§4–7; [development-log.md](../../agent-rules/development-log.md) перед implementation.
- Existing events/models.py, service.py, router.py, schemas.py; registrations/checkin.py/service.py; frontend event-detail-page.tsx/api.ts/public-event-page.tsx и existing registration actions.
- Redis/SMTP failure не откатывает успешный Event commit. Transition tasks используют snapshot и одну SMTP попытку, не confirmation/reminder filters.

## Interfaces / Acceptance criteria

- Add service `cancel_owned_event(session: Session, clock: Clock, owner_id: UUID, event_id: UUID, *, notification_dispatcher: TransitionDispatcher) -> Event`; production dependency обязательна.
- Add `POST /api/events/{event_id}/cancel`, no request body, authenticated owner + existing CSRF/Origin rules; success 200 EventResponse, no-store. Event state check order: missing → 404 EVENT_NOT_FOUND; foreign owner → 403 EVENT_NOT_OWNER; CANCELLED → 409 EVENT_CANCELLED; DRAFT → 409 EVENT_NOT_PUBLISHED; PUBLISHED now >= starts_at → 409 EVENT_ALREADY_STARTED. Existing auth/validation/unavailability errors сохраняются.
- Event FOR UPDATE до state/time checks; clock.now() после lock. PUBLISHED → CANCELLED, cancelled_at == updated_at == now; published_at/schedule_updated_at/slug/capacity сохраняются. Никакие Registration columns не изменяются.
- Snapshot CONFIRMED/WAITLIST recipients и Event data собираются до commit под Event lock; EVENT_CANCELLED notice использует existing Task 19 interface. Rollback/commit failure → no enqueue. Enqueue failure → safe log + success 200; следующие recipients dispatch продолжается.
- Repeat cancel всегда 409 EVENT_CANCELLED, без новых timestamps и enqueue, даже после начала Event.
- Cancellation email русский plain text: отмена, snapshot название/расписание/timezone/public link; одна SMTP попытка, без retries. Recipient snapshot не меняется из-за более поздних registration/user changes.
- Check-in/Event FOR SHARE и cancel/FOR UPDATE сериализуются. Если check-in commit раньше cancel — checked_in_at сохраняется; если cancel commit первым — check-in отклоняется EVENT_CANCELLED. Событие для race находится в pre-start check-in window.
- Confirmation/reminder, queued до cancel и начатые после него, не отправляют письмо. Delivery уже удерживающая Event FOR SHARE может завершиться раньше cancel; cancellation ждёт её commit.
- Registration/reactivation/capacity/schedule изменения после cancel отклоняются existing guards. Public page доступна с CANCELLED; нет новых registrations/check-in CTA для отменённого Event. История registrations сохраняется.
- Frontend `cancelEvent(eventId: string) -> Promise<EventResponse>` через existing client/generated schema; detail page button «Отменить мероприятие» только PUBLISHED с confirmation dialog. Повторная mutation во время pending запрещена; success записывает detail, invalidates mine/public/own-registration queries по existing keys. Ошибки 403/404/409/503 отображаются, API остаётся authoritative для time guard.
- Форма переноса/capacity/check-in actions исчезают после cancelled response; перезагрузка public page подтверждает статус. Новый SSE lifecycle signal не добавляется в этот PR.

## Review Focus / Test strategy

Create unit/test_event_cancellation.py, integration/test_event_cancellation.py, frontend event-cancellation.test.tsx и e2e/event-cancellation.spec.ts; extend transition unit tests и notification smoke.

- TDD owner/state/error precedence, now == starts_at, repeat no mutations/mail, timestamps/unchanged fields.
- PostgreSQL recipient snapshot CONFIRMED/WAITLIST excluding CANCELLED, commit-before-enqueue, rollback no-enqueue, enqueue exception success; no bulk Registration update.
- PostgreSQL races: cancellation vs check-in, confirmation/reminder held Event lock, register; explicit barriers/events, без sleep как доказательства serialization.
- Existing endpoint regressions: cancelled registration/check-in/capacity/schedule rejects; sent reminder/ticket/history не очищаются Event cancellation.
- RTL dialog/pending/errors/cache result и removal actions. Playwright owner cancel → public CANCELLED → participant/check-in rejects; SMTP sink получает matching notice для обоих active statuses. Tests выполняются на отдельных fixtures/projects.

## Execution steps / Verification

- [ ] От updated master создать branch/worktree/log по approved execution prompt.
- [ ] Unit RED: `uv run --frozen --project backend pytest backend/tests/unit/test_event_cancellation.py backend/tests/unit/test_transition_notifications.py -q`.
- [ ] Cancel service/router до GREEN; use existing dispatcher и rollback/error patterns, без дополнительных notification tables.
- [ ] PostgreSQL: `uv run --frozen --project backend pytest backend/tests/integration/test_event_cancellation.py backend/tests/integration/test_checkin.py backend/tests/integration/test_confirmation_email.py backend/tests/integration/test_reminder_email.py -q`, только disposable TEST_DATABASE_URL.
- [ ] `make api-generate`; проверить committed generated diff новой операции. RTL RED/GREEN: `cd frontend && corepack pnpm exec vitest run src/features/events/event-cancellation.test.tsx src/features/events/event-pages.test.tsx src/features/events/check-in-page.test.tsx`.
- [ ] Browser cancellation и real SMTP smoke включить в make verify ровно один раз; использовать existing isolated stack cleanup и E2E auth/rate isolation.
- [ ] `make check`, review/fixes, финальный `make verify`; expected exit 0 для всех gates включая cancellation/check-in race tests и runtime notification smoke.
- [ ] UI screenshot, actual verification evidence/limitations в log, staged secrets review и один PR. Известные ограничения: best-effort transition emails, возможные duplicates при SMTP ambiguity; никаких claims exactly-once.
