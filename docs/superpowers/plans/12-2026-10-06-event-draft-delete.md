# Task 12 — Empty Draft Event Deletion Implementation Plan (Day 3)

> **For agentic workers:** Использовать superpowers:executing-plans. Implementation только по отдельной команде пользователя.

**Status:** Реализован 2026-10-07; независимый review без замечаний, финальный `make verify` exit 0. PR #14 merged в master (`298c33b`). Evidence: [development log](../../development-log/2026-10-07-event-draft-delete.md).

**Task:** Физическое удаление DRAFT без registrations.

**Goal:** Owner удаляет свой черновик только если в нём отсутствуют любые Registration rows.

**Architecture:** Delete use-case блокирует Event, проверяет owner/status и реальный SQL registration count, затем удаляет Event одним commit. UI подтверждает действие и после success переходит в owner list, исключая stale detail resurrection.

**Tech Stack:** Существующий Event/Registration stack, PostgreSQL, RTL, Playwright.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 10–11, 34, 38; scope deletion отнесён к Day 3 в [Task 05](05-2026-10-05-event-draft-create.md) / [Task 07](07-2026-10-05-event-publish.md).

## Global Constraints

- Rules/gates: [engineering.md](../../agent-rules/engineering.md); lifecycle: [development-process.md](../../development-process.md); journal: [development-log rules](../../agent-rules/development-log.md).
- Удаление только `status == DRAFT AND registration_count == 0`; count включает CANCELLED; cascade registrations не добавляется.
- Event FOR UPDATE сериализует delete с publish/PATCH и будущими registration mutations.

## Task / PR boundary

**Dependencies:** Task 08 merged; Tasks 09–11 не требуются. При последовательном выполнении использовать master со всеми уже merged задачами.

**Branch:** `feat/event-draft-delete`, новый worktree от updated master; один PR.

**Scope:** DELETE Event, actual SQL registration count, delete control/dialog для DRAFT, organizer navigation/cache cleanup, tests.

**Out of scope:** PUBLISHED/CANCELLED deletion, cascade registrations, Event cancellation, reschedule/email, unrelated Event refactor.

**Acceptance criteria:**

- Owner DELETE DRAFT с zero registrations → 204 без body; Event физически отсутствует в DB.
- Missing → 404 EVENT_NOT_FOUND; чужой → 403 EVENT_NOT_OWNER; PUBLISHED/CANCELLED или DRAFT с любой registration → 409 EVENT_NOT_DELETABLE, без mutation.
- Valid fixture CANCELLED Registration на DRAFT блокирует deletion, несмотря на zero active count. Counts не подменяются constants или confirmed-only query.
- Repeat DELETE после success → 404 EVENT_NOT_FOUND.
- Concurrent delete/publish соответствует одному lock order: delete first → publish 404; publish first → delete 409, Event PUBLISHED сохранён. Success обоих невозможен.
- UI DRAFT action требует подтверждения; dismissal не делает DELETE. Во время mutation повторный submit disabled, ошибка сохраняет Event и даёт retry.
- После success organizer list/reload не показывают Event; stale detail response не возвращает удалённую запись. Direct removed detail → not found.

**Test strategy:** TDD eligibility/guards; PostgreSQL count/FK/delete-publish ordering; HTTP auth/CSRF/Origin; RTL confirmation/error/cache; Playwright create DRAFT → delete → list/reload.

**Verification:** Baseline `make check`/`make test`; targeted tests; `make api-generate`; `make check`; `make test`; финальный `make verify` с deletion browser flow и прежними Event regressions. Проверки общего gate не заменяются manual smoke.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс actual count, serialized delete/publish и browser deletion/reload.

## Files / interfaces

- Modify: `backend/app/events/service.py`, `repository.py`, `router.py`; add `registrations.repository.count_registrations(session: Session, event_id: UUID) -> int` (all statuses, no commit).
- Create tests: `backend/tests/unit/test_event_delete.py`, `backend/tests/integration/test_event_delete.py`.
- Modify frontend events/api.ts, event-detail-page.tsx, event-pages.test.tsx; regenerate schema; extend `frontend/e2e/event-drafts.spec.ts` с отдельным deletion scenario.
- Schema changes не требуются: Task 08 FK уже препятствует orphan/cascade removal; не изменять merged migration.

**Consumes:** existing Event FOR UPDATE, CurrentUser/Session/Clock при необходимости существующих dependencies; Task 08 Registration table; eventKeys.detail/mine, existing ApiError.

**Produces:** `delete_owned_event(session: Session, owner_id: UUID, event_id: UUID) -> None` — locks/checks/delete/commit, rollback on failure; DELETE `/api/events/{event_id}` → 204, existing error envelope/no-store; `deleteEvent(eventId): Promise<void>` с `requiresAuth: true`, без JSON parsing empty response.

UI success отменяет exact owner detail и mine in-flight queries, удаляет detail cache, invalidates mine и navigates `/organizer/events`. Существующий generic API client проверить на 204 до изменения; если поддержка отсутствует, добавить только необходимую handling с regression test в client.test.ts. UI delete confirmation — существующие MUI Dialog/Button, без нового generic subsystem.

## Review Focus / test assertions

| Test | Assertions |
|---|---|
| `test_cancelled_row_prevents_draft_delete` | 409 EVENT_NOT_DELETABLE; Event и Registration сохранены |
| `test_delete_publish_lock_orders` | только один success; состояния обоих порядков соответствуют AC |
| `test_delete_authorization_and_repeat` | other owner 403; first own 204 empty; repeat 404; CSRF reject без delete |
| `dismiss delete confirmation` | запрос DELETE отсутствует, Event остаётся |
| `delete success survives delayed detail GET` | list без Event, detail cache не resurrected; direct reload not found |

## Execution steps

- [x] 1. По implementation команде после merge 08 создать branch/worktree, baseline и task log до кода.
- [x] 2. Написать unit eligibility/ownership tests; `uv run --frozen --project backend pytest backend/tests/unit/test_event_delete.py -q` → RED.
- [x] 3. Реализовать delete service/all-status count до GREEN unit command.
- [x] 4. Добавить PostgreSQL tests Review Focus, DRAFT zero-count/WAITLIST/CONFIRMED/CANCELLED fixtures и CSRF/Origin checks; `make test` → RED для HTTP/persistence guarantees.
- [x] 5. Подключить DELETE router и transactional persistence до GREEN `make test`; commit backend/tests.
- [x] 6. Выполнить `make api-generate`; написать RTL dialog dismissal/confirm/pending/error/204/delayed-GET tests; `cd frontend && corepack pnpm exec vitest run src/features/events/event-pages.test.tsx` → RED.
- [x] 7. Реализовать delete wrapper/action/cache cleanup; повторить RTL до GREEN; client.test.ts regression только если изменён 204 handling; commit frontend/generated schema.
- [x] 8. Playwright `event-drafts` deletion: создать отдельный DRAFT, подтвердить удаление, list/reload без Event, direct old detail not found; существующий create/edit scenario сохраняется.
- [x] 9. Review, `make check`, финальный `make verify`, screenshots, journal actual results и staged secrets review; один PR. Полнота Day 3 оценивается после merge Tasks 08–12 и проверки интеграционного master; check-in race/SSE/email tests остаются Day 4–5.
