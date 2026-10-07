# Task 11 — My Registrations Implementation Plan (Day 3)

> **For agentic workers:** Использовать superpowers:executing-plans. Начинать implementation только по отдельной команде пользователя.

**Status:** Реализован 2026-10-07; независимый review без замечаний, make verify exit 0.

**Task:** Список регистраций текущего участника.

**Goal:** `/me/registrations` показывает собственные registrations и позволяет перейти к Event или отменить активную регистрацию.

**Architecture:** Read use-case выбирает own registrations с event summary и актуальной FIFO position. Protected participant page переиспользует Task 09 cancellation; query keys включают current user. Public event content остаётся отдельным anonymous contract.

**Tech Stack:** Существующий backend/frontend stack и quality tools.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 7, 15–16, 34–36; [Task 08](08-2026-10-06-event-registration.md), [Task 09](09-2026-10-06-registration-cancel.md).

## Global Constraints

- Rules/gates: [engineering.md](../../agent-rules/engineering.md), [development-process.md](../../development-process.md), [development-log rules](../../agent-rules/development-log.md).
- Список включает CONFIRMED/WAITLIST/CANCELLED, ordering `updated_at DESC, id DESC`; position 1-based среди WAITLIST одного Event.
- RegistrationResponse и cancellation contract не дублируются/не меняются; email/check-in/SSE не добавляются.

## Task / PR boundary

**Dependencies:** Task 09 merged; Task 10 не требуется. Параллельная реализация не предполагается: Task 11 и 09 меняют общий frontend registration module.

**Branch:** `feat/my-registrations`, новый worktree от updated master, один PR.

**Scope:** `GET /api/me/registrations`; own list DTO/event summary; protected route; account link; states, formatted own tickets/position, cancellation и query synchronization.

**Out of scope:** Organizer participants list, search/filters, новая pagination, Event cancellation, polling/SSE, dashboard.

**Acceptance criteria:**

- GET → 200 массив только текущего user, включая CANCELLED; пустой → `[]`. Auth required, no-store; другой user не влияет на selection и ticket exposure.
- Ordering `updated_at DESC, id DESC`, включая deterministic tie-break; timestamps остаются internal и не меняют RegistrationResponse contract.
- Each item содержит registration и safe event summary для public link/schedule; private owner/email/auth data отсутствуют.
- Position учитывает WAITLIST всех участников данного Event, не только current user; CONFIRMED/CANCELLED → null; SQL row/position snapshot согласован, без per-row N+1.
- UI показывает CONFIRMED ticket, WAITLIST position, CANCELLED history, empty/loading/error/retry; Event schedule отображается в его IANA timezone существующим formatter.
- Direct navigation/reload работают; anonymous → login; account page содержит «Мои регистрации».
- Cancellation обновляет list и own detail; после promotion refetch/reload показывает CONFIRMED. Re-registration по public link возвращает существующую запись в активное состояние.
- Logout/account switch и delayed list/own GET не раскрывают старые registrations и не заменяют успешную mutation stale состоянием.

**Test strategy:** PostgreSQL selection/ordering/position/privacy; RTL controllable promises для cancellation/account switch/delayed GET; Playwright direct route, cancellation/reload и second-user isolation.

**Verification:** Baseline `make check`/`make test`; targeted tests; `make api-generate`; `make check`; `make test`; финальный `make verify` с participant list flow. Screenshot list без credentials; secrets review согласно общим rules.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс own-read isolation, history/position contract и browser list/cancel/reload.

## API / Files / interfaces

- `GET /api/me/registrations` → `list[MyRegistrationResponse]`, без pagination.
- `MyRegistrationResponse = {registration: RegistrationResponse, event: RegistrationEventSummary}`.
- `RegistrationEventSummary = {id: UUID, title: str, slug: str, starts_at: datetime, ends_at: datetime, timezone: str, status: Literal['PUBLISHED','FINISHED','CANCELLED']}`. FINISHED вычисляется Clock как в public Event contract. DRAFT не раскрывается: impossible production registration/DRAFT fixture не включается в list.
- Create `backend/app/registrations/read_service.py`; extend `schemas.py`, `repository.py`, `router.py` (separate `/api/me` router); include router in `backend/app/main.py`.
- Create tests `backend/tests/integration/test_my_registrations.py`; create `frontend/src/features/registrations/my-registrations-page.tsx`, `my-registrations-page.test.tsx`; extend registrations/api.ts, `frontend/src/app.tsx`, account-page.tsx и account-page.test.tsx; regenerate schema; create `frontend/e2e/my-registrations.spec.ts`.

**Consumes:** Task 08 RegistrationResponse, `registrationKeys.detail`, getMyRegistration; Task 09 `cancelRegistration`; useSession/auth phase, `formatEventTime`.

**Produces:** `list_my_registrations(session: Session, clock: Clock, user_id: UUID) -> list[MyRegistrationResponse]` — read-only; `registrationKeys.mine(userId)` = `['registrations', userId, 'mine']`; `getMyRegistrations(signal?): Promise<MyRegistrationResponse[]>`, `requiresAuth: true`.

Общая frontend synchronization helper `applyRegistrationMutation(client: QueryClient, userId: string, saved: RegistrationResponse): Promise<void>` в registrations/api.ts отменяет exact own-detail и mine in-flight queries до записи response. Own detail получает saved; existing mine item заменяется, список invalidates для серверного ordering/позиции. Оба consumers (panel и list) используют helper. Helper не создаёт поддельный list без event summary; auth generation/SessionChangedError существующего клиента сохраняется. Automatic recovery не запускается на public calls.

## Review Focus / test assertions

| Test | Assertions |
|---|---|
| `test_list_isolation_and_cancelled_history` | только own user_id/ticket; CANCELLED включён; другой user отсутствует |
| `test_order_and_global_event_waitlist_position` | order updated_at/id DESC; own WAITLIST rank учитывает других users, другой Event не учитывается |
| `test_event_summary_privacy_and_finished` | exact safe fields; now==ends_at → FINISHED; DB Event status не меняется |
| `account switch cannot show previous list` | другой query key; delayed old promise не публикует private data |
| `cancel success survives delayed list GET` | list и public own detail остаются CANCELLED; stale GET не возвращает active UI |

Дополнительно: empty, request error/retry, formatted ticket, timezone display, expired access recovery, unauthenticated access.

## Execution steps

- [x] 1. После implementation команды/merge 09 создать branch/worktree, baseline, log до кода.
- [x] 2. Написать integration tests таблицы Review Focus и API auth/empty cases; `make test` → RED (новый GET отсутствует), записать причину.
- [x] 3. Реализовать DTO, SQL own read/position snapshot и router до GREEN `make test`; commit backend/tests.
- [x] 4. Выполнить `make api-generate`; добавить RTL list states, account switch, cancellation/cache tests. `cd frontend && corepack pnpm exec vitest run src/features/registrations/my-registrations-page.test.tsx` → RED.
- [x] 5. Реализовать page/auth gating/route/account link и reusable mutation synchronization; повторить RTL до GREEN; также выполнить `cd frontend && corepack pnpm exec vitest run src/features/registrations/event-registration-panel.test.tsx src/features/auth/account-page.test.tsx`; commit frontend/generated types.
- [x] 6. Playwright `my-registrations`: own direct route/reload, cancel/reload, promotion refetch, login другим user без старых rows; setup ждёт целевой heading, test login rate budget изолирован при необходимости.
- [x] 7. Review, `make check`, финальный `make verify`, screenshot, journal evidence и staged secrets check; один PR.
