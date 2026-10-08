# Task 19 — Published Event Reschedule and Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Реализация только по отдельному execution prompt после review файла.

**Status:** Решения опроса утверждены пользователем 2026-10-08; plan подготовлен для review, implementation не начата.

**Goal:** Organizer переносит будущее PUBLISHED событие, а его CONFIRMED/WAITLIST участники получают plain-text уведомление о конкретном переносе.

**Architecture:** Existing PATCH под Event FOR UPDATE допускает либо capacity-only, либо schedule-only request. Schedule persistence и snapshot получателей создаются в одной transaction; после commit dispatch в Celery по одному письму на получателя. Task использует snapshot, не перечитывает Event/Registration и не имеет automatic retries.

**Tech Stack:** Existing FastAPI/SQLAlchemy/PostgreSQL, notification runtime Tasks 17–18, React/MUI/TanStack Query, pytest/Vitest/Playwright.

**Spec:** [technical-design.md](../specs/technical-design.md), §§8–9, 11, 22–23, 34–37, 38–39; [ADR-004](../../adr/004-notification-delivery.md). Утверждённое расширение прежнего capacity-only scope, исторические планы не переписывать.

## Task / PR boundary

**Dependencies:** [Task 17](17-2026-10-08-confirmation-email.md), [Task 18](18-2026-10-08-reminder-email.md) merged; existing published capacity PATCH и timezone UI utilities.

**Branch:** `feat/event-reschedule`.

**Scope:** Schedule-only PATCH, atomic update, after-commit snapshot dispatch, organizer schedule form/cache updates, reminder regressions и end-to-end SMTP verification. Один vertical-slice PR.

**Out of scope:** Published text/slug editing, смешанный schedule/capacity PATCH, Event cancellation, guaranteed delivery, second reminder, delivery history/outbox, unrelated refactoring.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) + AC ниже, UI screenshots и реальный email smoke.

## Required context / Global constraints

- Указанные spec/ADR sections; Task 17 Interfaces и Task 18 eligibility; Task 10 Contract/Interfaces для capacity compatibility.
- [engineering.md](../../agent-rules/engineering.md): Architecture, Clock, PostgreSQL, Lock ordering, Email tasks, Generated API, TDD, Secrets, Canonical commands, Scope restrictions.
- [development-process.md](../../development-process.md): §§4–7; [development-log.md](../../agent-rules/development-log.md) при implementation.
- Existing events/service.py patch_owned_event/patch_published_capacity, repository.py transaction boundaries, schemas.py EventPatchRequest; frontend events/api.ts, event-detail-page.tsx, event-time.ts и cache keys.
- Event FOR UPDATE сериализует schedule update с registration/cancellation/promotion и confirmation/reminder Event FOR SHARE. Не переносить commit в router; SMTP никогда не в HTTP request.

## Interfaces / data flow

- Existing `PATCH /api/events/{event_id}` и EventPatchRequest/EventResponse wire shapes сохраняются. PUBLISHED supplied fields: ровно {capacity} либо непустое подмножество {starts_at, ends_at, timezone}. Любое другое/смешанное supplied поле → 409 EVENT_NOT_EDITABLE целиком, даже равное прежнему значению. Existing schema null/invalid datetime/timezone → 422 VALIDATION_ERROR.
- Extend `patch_owned_event` optional keyword `notification_dispatcher: TransitionDispatcher | None`; HTTP dependency всегда передаёт production dispatcher. Tests explicitly inject spy/no-op; production wiring не допускает silent disabled dispatch.
- Create `notifications/transitions.py`: immutable `TransitionNotice(kind: Literal['EVENT_RESCHEDULED', 'EVENT_CANCELLED'], event_id: UUID, occurred_at: datetime, recipient: str, title: str, slug: str, starts_at: datetime, ends_at: datetime, timezone: str)` и `TransitionDispatcher.enqueue(notice: TransitionNotice) -> None`. JSON payload: UUID string и ISO aware datetimes; содержит только необходимый snapshot, без credentials/ticket/body.
- Recipient query в notifications/repository.py join Registration/User под Event lock, statuses CONFIRMED/WAITLIST; результат `(email)` по одной existing Event/User registration. Snapshot отражает получателей на commit перехода, включая email в тот момент. Изменения recipient/status после commit не подавляют и не меняют snapshot письмо.
- После flush Event собрать notices с новым schedule, commit, затем enqueue каждый notice. Helper `dispatch_transition_notices(dispatcher, notices) -> None` ловит exception каждого enqueue, безопасно логирует kind/event_id и продолжает остальных; commit success возвращает 200 даже при enqueue failure. Snapshot не сохраняется в DB и может потеряться по ADR-004.
- Extend tasks.py `send_transition_notice(payload)`; reconstruct notice, render/send один раз через existing SMTP adapter, failure log + task failure без retry. Не применять confirmation/reminder PUBLISHED guard к snapshot transitions.
- Frontend create `event-schedule-form.tsx`: отдельная форма PUBLISHED schedule, только три schedule fields; reuse event-time utilities, сохранить seconds и DST choice. Detail page выводит форму для PUBLISHED, capacity form остаётся отдельной. Existing DRAFT edit не расширяется для published text/slug.

## Acceptance criteria

1. Ownership/not-found/CANCELLED guards сохраняют existing 403 EVENT_NOT_OWNER, 404 EVENT_NOT_FOUND, 409 EVENT_CANCELLED. Для schedule request old starts_at <= now → 409 EVENT_ALREADY_STARTED.
2. Merge supplied schedule с existing values; new starts_at > now, ends_at > starts_at, valid IANA timezone. Invalid interval/future boundary → 422 VALIDATION_ERROR, ни update, ни dispatch.
3. Фактическое изменение starts_at/ends_at/timezone устанавливает schedule_updated_at и updated_at одним clock.now(); published_at, slug, ticket/email/reminder state сохраняются.
4. Schedule-only no-op возвращает 200 без timestamps mutation/dispatch; state/time guards проверяются до no-op. DRAFT edits сохраняют прежнее поведение и никогда не enqueue.
5. Event update и snapshot recipients происходят под одной Event transaction. Rollback/commit failure → no dispatch. Enqueue после успешного commit; safe failure logging не меняет response.
6. Письмо EVENT_RESCHEDULED содержит snapshot нового расписания, timezone, название и public link. Только snapshot CONFIRMED/WAITLIST recipients; CANCELLED исключены. Два последовательных переноса создают два независимых notices; очередность доставки не гарантируется.
7. Existing reminder_sent_at не очищается; перенос <24h не создаёт reminder; уже sent reminder не повторяется после дальнего переноса. Pending confirmation/reminder tasks используют новое состояние после locks.
8. Capacity-only PATCH/FIFO promotion и DRAFT text/schedule/slug behavior не регрессируют. Mixed PATCH rejects до изменений.
9. UI отправляет только фактически изменённые schedule fields, показывает errors/pending и новое расписание; protected detail/mine и public event queries invalidated по existing keys. Не добавлять SSE signal как новый контракт этого PR.

## Review Focus / Test strategy

Create unit/test_event_reschedule.py, integration/test_event_reschedule.py, unit/test_transition_notifications.py; frontend event-schedule-form.test.tsx и e2e/event-reschedule.spec.ts. Extend notification smoke для real after-commit dispatch через API.

- TDD old/new start boundary, invalid interval/timezone, schedule-only no-op, mixed/forbidden fields, ownership, DRAFT no-email.
- PostgreSQL commit/rollback и recipient statuses; queue spy убеждается, что другой session видит committed schedule в enqueue callback. Enqueue exception не отменяет change, остальные recipients продолжаются.
- Concurrent reschedule vs registration/confirmation/reminder; consistent snapshot и новый reminder predicate. Не доказывать PostgreSQL locks SQLite/mocks.
- Delayed notices двух переносов сохраняют свои dates/recipient snapshots; SMTP failure one attempt; no secret/recipient/payload logging.
- RTL timezone/DST/seconds, cache updates, pending/error; browser organizer schedule → public schedule, SMTP sink получает matching snapshot; capacity/DRAFT regressions.

## Execution steps / Verification

- [ ] Новые branch/worktree/log от updated master; read Required context only.
- [ ] Unit RED: `uv run --frozen --project backend pytest backend/tests/unit/test_event_reschedule.py backend/tests/unit/test_transition_notifications.py -q`.
- [ ] Implement transaction/snapshot/dispatcher/task до GREEN; точечно изменить прежние published schedule rejection tests только для нового approved contract.
- [ ] Integration: `uv run --frozen --project backend pytest backend/tests/integration/test_event_reschedule.py backend/tests/integration/test_event_capacity.py backend/tests/integration/test_reminder_email.py -q` на isolated TEST_DATABASE_URL.
- [ ] RTL RED/GREEN: `cd frontend && corepack pnpm exec vitest run src/features/events/event-schedule-form.test.tsx src/features/events/event-pages.test.tsx src/features/events/event-capacity-form.test.tsx`.
- [ ] Add Playwright/SMTP smoke в verification grouping ровно один раз; `make api-generate` только если OpenAPI изменился, generated files вручную не редактировать.
- [ ] `make check`, review/fixes, финальный `make verify`; expected exit 0 включая runtime snapshot mail, reminder и существующие browser gates.
- [ ] Screenshot формы/результата, actual evidence/limitations в log, staged secrets review и один PR.
