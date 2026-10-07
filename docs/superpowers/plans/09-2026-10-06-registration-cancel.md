# Task 09 — Registration Cancellation + FIFO Promotion Implementation Plan (Day 3)

> **For agentic workers:** Использовать superpowers:executing-plans. Начинать checklist только по отдельной implementation команде пользователя.

**Status:** Implementation выполнена; make verify exit 0 на 2026-10-07; [PR #11](https://github.com/nbaishev/event-registration/pull/11) создан.

**Task:** Отмена регистрации с атомарным FIFO promotion.

**Goal:** Cancellation CONFIRMED освобождает место и в той же транзакции подтверждает первого участника очереди.

**Architecture:** Cancellation use-case владеет Event lock и одной транзакцией отмены/promotion. Общий `fill_available_slots` вычисляет свободные места и меняет первые WAITLIST под Registration locks; commit выполняет caller. Task 10 переиспользует этот use-case.

**Tech Stack:** Существующий backend/frontend stack, PostgreSQL integration, Fixed Clock, RTL и Playwright.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 7–8, 11, 13, 15–16, 33–35, 38; [ADR-002](../../adr/002-postgresql-concurrency.md).

## Global Constraints

- Общие правила: [engineering.md](../../agent-rules/engineering.md), [development-process.md](../../development-process.md), [development-log rules](../../agent-rules/development-log.md).
- FIFO строго `ORDER BY waitlisted_at ASC, id ASC`; Event → Registration; promotion только PUBLISHED и `now < starts_at`.
- У cancellation и promotion один commit; `fill_available_slots` не начинает отдельную session/transaction и не commit.
- Schema и ticket contract принадлежат [Task 08](08-2026-10-06-event-registration.md); check-in race/SSE — Day 4, email delivery — Day 5.

## Task / PR boundary

**Dependencies:** Task 08 merged.

**Branch:** `feat/registration-cancel`, новый worktree от updated master; один vertical-slice PR.

**Scope:** DELETE own registration; cancellation transitions; `fill_available_slots`; FIFO position после изменения очереди; cancellation UI и end-to-end re-registration.

**Out of scope:** Capacity PATCH, Event cancellation, check-in endpoint/race, email, stats/SSE, participant list.

**Acceptance criteria:**

- DELETE блокирует Event, затем own Registration. Success → 200 CANCELLED; отсутствие или уже CANCELLED → 404 REGISTRATION_NOT_FOUND.
- Event CANCELLED → 409 EVENT_CANCELLED; `now >= ends_at` → 409 EVENT_FINISHED; `starts_at <= now < ends_at` → 409 EVENT_ALREADY_STARTED. Event errors предшествуют registration lookup result.
- CONFIRMED с checked_in_at → 409 TICKET_ALREADY_CHECKED_IN; fixture проверяет guard без реализации check-in.
- CONFIRMED cancellation очищает confirmed/waitlisted/ticket/ticket-issued/check-in/notification fields, ставит cancelled_at/updated_at = now; после flush вызывает promotion. WAITLIST cancellation очищает очередь и notification state, не вызывает promotion.
- Promotion подтверждает первые N WAITLIST по FIFO, включая id tie-break, ставит confirmed_at/ticket_issued_at/updated_at = now, очищает waitlisted_at и выдаёт новый ticket с NULL notification flags.
- Promotion для DRAFT/CANCELLED/started Event — no-op; shortage очереди не создаёт лишних rows. Уже существующие confirmed/tickets не меняются.
- Failure после cancellation или после первого из нескольких promotions откатывает все изменения и сохраняет capacity invariant.
- Два конкурентных DELETE одной registration → один 200, один 404; cancellation/register race не теряет места и не превышает capacity.
- Re-registration после реального DELETE переиспользует row; при WAITLIST становится последней, при CONFIRMED получает новый ticket. Repeat DELETE → 404.
- UI cancel → CANCELLED; очередь/refetch показывают новую position и CONFIRMED promoted user после reload, без обещания realtime.

**Test strategy:** TDD transitions/time guards; PostgreSQL FIFO, atomic rollback, concurrency; Fixed Clock; RTL mutation/cache/errors; Playwright с двумя participant contexts.

**Verification:** Baseline `make check` + `make test`; targeted tests; `make api-generate`; `make check`; `make test`; финальный `make verify` с cancellation/promotion E2E. При отдельной browser диагностике — `make e2e`. Проверить screenshots и staged diff согласно общим правилам.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс доказанные FIFO и atomic cancellation/promotion, browser cancel/re-register scenario.

## Files / interfaces

- Modify: `backend/app/registrations/service.py`, `repository.py`, `router.py`; create `backend/app/registrations/promotion.py`.
- Create tests: `backend/tests/unit/test_registration_cancel.py`, `backend/tests/integration/test_registration_cancel.py`, `backend/tests/integration/test_waitlist_promotion.py`.
- Modify: `frontend/src/features/registrations/api.ts`, `event-registration-panel.tsx`, `.test.tsx`, generated `frontend/src/api/schema.d.ts`, `frontend/e2e/event-registration.spec.ts`.
- Persistent schema не меняется; обнаруженное schema requirement оформляется миграцией по engineering rules, не правкой уже merged revision.

**Consumes:** Task 08 Registration/RegistrationResponse, `confirm_registration(session, registration, now)`, `count_confirmed`, own query key и ticket contract; Event lock helper.

**Produces:**

- `cancel_registration(session: Session, clock: Clock, user_id: UUID, event_id: UUID) -> RegistrationResponse` — owns commit/rollback и snapshot.
- `promotion.fill_available_slots(session: Session, event: Event, now: datetime) -> list[UUID]` — caller уже удерживает Event FOR UPDATE; возвращает promoted ids, no commit. Временное значение берёт caller через Clock после Event lock и передаёт одинаковое для всей mutation.
- `repository.find_waitlist_for_update(session: Session, event_id: UUID, limit: int) -> list[Registration]` — FIFO ordering, `FOR UPDATE`, без `SKIP LOCKED` (оно могло бы обойти первого участника).
- `cancelRegistration(eventId): Promise<RegistrationResponse>` — DELETE singular `/api/events/{event_id}/registration`, `requiresAuth: true`.

Нет промежуточного commit между cancellation/count/promotion. Регистрации, выбранные SQL под lock, должны отражать актуальное состояние, включая flush отменяемой row. API no-store и существующий error envelope; DRAFT fixture не получает mutation через production API (404 EVENT_NOT_FOUND).

## Review Focus / test assertions

| Test | Assertions |
|---|---|
| `test_fifo_timestamp_tie` | promotion order = `(waitlisted_at, id)`; другой Event не затронут |
| `test_cancel_rolls_back_failed_promotion` | cancelled target и все promoted rows после failure равны исходному snapshot |
| `test_waitlist_cancel_does_not_promote` | target CANCELLED; other statuses/tickets не изменены; remaining positions сдвинуты |
| `test_double_cancel_and_register_race` | double DELETE 200/404; race totals валидны; confirmed <= capacity |
| `cancel success survives delayed GET` | UI/cache остаются CANCELLED после stale response; повторная регистрация доступна |

Дополнительно: no-op promotion для DRAFT/CANCELLED/now==starts_at; несколько free slots и shortage; DELETE boundary ends_at; checked-in fixture; auth/CSRF/Origin без mutation; re-registration обеих веток.

## Execution steps

- [x] 1. После implementation команды и merge 08 создать branch/worktree, baseline `make check`/`make test`, task log до кода.
- [x] 2. Добавить unit tests cancellation state и promotion guards с Fixed Clock; запустить `uv run --frozen --project backend pytest backend/tests/unit/test_registration_cancel.py -q`, подтвердить RED.
- [x] 3. Реализовать cancellation/promotion interfaces; повторить unit command до GREEN.
- [x] 4. Добавить PostgreSQL tests Review Focus/API error matrix и тест failures после первого promotion; выполнить `make test`, записать RED для отсутствующей гарантии.
- [x] 5. Реализовать repository selection/flush и DELETE router до GREEN `make test`; commit backend cancellation/FIFO с tests.
- [x] 6. Выполнить `make api-generate`; добавить RTL cancellation success, errors, repeated DELETE, delayed GET, re-registration. Запустить `cd frontend && corepack pnpm exec vitest run src/features/registrations/event-registration-panel.test.tsx`, подтвердить RED.
- [x] 7. Добавить cancel action и exact-query cancellation/cache update; повторить RTL до GREEN; commit UI/generated contract.
- [x] 8. Расширить `event-registration` Playwright: A CONFIRMED, B WAITLIST, A cancel, B reload CONFIRMED; A re-register WAITLIST; B cancel, A reload CONFIRMED с новым ticket.
- [x] 9. Review, `make check`, финальный `make verify`, screenshots, actual verification в журнале и staged secrets check; один PR.
