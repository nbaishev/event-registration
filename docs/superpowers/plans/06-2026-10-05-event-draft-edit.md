# Task 06 — Event Draft Editing (Day 2)

> **For agentic workers:** План утверждён пользователем. Начинать implementation только после отдельной команды пользователя; выполнять через superpowers:executing-plans.

**Status:** PR #7 is open for review; implementation and independent review completed; final `make verify` passed.

**Goal:** Owner меняет черновик, а сохранённые значения сохраняются после reload без изменения ownership/status.

**Architecture:** DRAFT PATCH выполняется в одной transaction под Event FOR UPDATE с validation итогового состояния. React edit form использует generated types и обновляет detail/list cache после success.

**Tech Stack:** Существующий stack из [Product Spec](../specs/technical-design.md#3-стек).

**Spec:** [technical-design.md](../specs/technical-design.md), sections 5, 8–11, 32, 34, 36–38.

**Task / PR boundary:** Одна измеримая задача, один PR; branch `feat/event-draft-edit` от актуального `master` после merge dependencies.

## Global Constraints

- Product Spec — источник требований; решения опроса зафиксированы в разделе «Утверждённые решения» и уточняют не определённые в spec детали.
- Реализация остаётся в существующем modular monolith: router → service/use-case → repository/database. Business rules не помещаются в React components или routers.
- PostgreSQL — источник истины; persistent schema changes выполняются через Alembic. `create_all()` не используется как deployment strategy.
- Event содержит поля и DB constraints section 5: `capacity >= 1`, `ends_at > starts_at`, FK User и unique slug. Mutable counters в Event не добавляются.
- Persisted EventStatus: DRAFT/PUBLISHED/CANCELLED. FINISHED — effective состояние PUBLISHED при `now >= ends_at`, без отдельного persisted status.
- Owner определяется `owner_id` существующего User; отдельные organizer/participant roles не вводятся.
- Business time берётся через Clock; timestamps хранятся как timezone-aware UTC. Boundary tests используют Fixed/Fake Clock без sleep.
- Slug генерируется backend, globally unique, lowercase `a-z`/`0-9`/`-` с random suffix; после publish immutable.
- PATCH и publish получают Event `FOR UPDATE` и повторно проверяют owner/state/time под lock. Порядок будущих locks — Event → Registration; locking behavior проверяется на настоящем PostgreSQL.
- Защищённые endpoints используют существующую access-cookie auth dependency; unsafe requests — double-submit CSRF и exact Origin. Frontend защищённые calls явно ставят `requiresAuth: true`; public calls не зависят от auth phase.
- FastAPI OpenAPI — source of truth; generated frontend files не редактируются вручную. После API change выполняется `make api-generate`.
- Backend остаётся с одним worker. Transactional outbox, Ticket table, RefreshSession, Redis Pub/Sub, application rate limiter, Redux, microservices и unrelated refactoring не добавляются.
- Каждая задача — один vertical-slice PR и новая branch/worktree от обновлённого master после merge dependencies. Development log создаётся только при начале разрешённой implementation task.
- План и решения опроса утверждены; пользователь отдельно разрешил implementation.
- Общие quality gates и полный DoD определены в [engineering.md](../../agent-rules/engineering.md) и [AGENTS.md](../../../AGENTS.md); development loop — `make check`, pre-PR gate — `make verify`. Секреты не попадают в commits, screenshots и logs.
- Task 06 редактирует только DRAFT. PUBLISHED/CANCELLED изменения не принимаются: 409 EVENT_NOT_EDITABLE / 409 EVENT_CANCELLED соответственно.
- При `now >=` исходного `starts_at` capacity/starts_at/ends_at/timezone changes запрещены. DRAFT schedule edit обновляет `schedule_updated_at`, но не создаёт email tasks.
- Published capacity changes с confirmed_count и реальным `fill_available_slots` относятся к Day 3; published reschedule/cancellation с уведомлениями — к Day 5; signals после commit — к Day 4 SSE integration.
- Delete/cancel не входят в Day 2. Не подменять будущие registration count, promotion, notification enqueue или broadcaster успешными заглушками.

## Task

**Dependencies:** [Task 05](05-2026-10-05-event-draft-create.md) merged; утверждены PATCH field/error semantics и slug policy.

**Scope:**

- DRAFT editing use-case под Event `FOR UPDATE` с повторной проверкой состояния и owner.
- `PATCH /api/events/{event_id}`; validation объединённого состояния, а не только переданных полей.
- Title/description, capacity, starts_at/ends_at/timezone; явная кнопка «Обновить ссылку» регенерирует slug backend только в DRAFT; смена title сохраняет slug.
- При изменении schedule fields — `schedule_updated_at = clock.now()`; timestamps через Clock.
- UI `/organizer/events/:eventId/edit`, prefill, submit/errors, актуализация detail/list query cache и generated types.

**Out of scope:** PUBLISHED editing/reschedule/capacity changes, delete/cancel, waitlist promotion, notifications, SSE.

**Acceptance criteria:**

- Owner сохраняет изменения; detail/list после reload показывают новые значения; id/owner/status не меняются.
- Partial PATCH проверяет итоговое `ends_at > starts_at`, capacity и timezone; invalid request не сохраняет часть изменений.
- При `now >=` исходного `starts_at` schedule/capacity changes отклоняются согласно section 8; → 409 EVENT_ALREADY_STARTED; boundary тестируется через Fixed Clock.
- Schedule change обновляет `schedule_updated_at`; изменение только title/description его не обновляет.
- DRAFT schedule edit не создаёт email tasks.
- Чужой Event и отсутствующий Event дают согласованные ownership/not-found errors; failure не меняет запись.
- PATCH PUBLISHED → 409 EVENT_NOT_EDITABLE; PATCH CANCELLED → 409 EVENT_CANCELLED; без mutation.
- Смена title сохраняет slug; явная регенерация в DRAFT выдаёт новый globally unique slug и обновляет UI link после success.
- Title/description и DST validation соответствуют утверждённым text/timezone rules; invalid partial PATCH не сохраняет ни одно изменение.
- Backend не принимает смену owner/status через PATCH; UI не предлагает эти изменения.

**Test strategy:** TDD для partial-update validation и временных границ; PostgreSQL integration для atomic rollback и сериализации competing PATCH; RTL prefill/error/save; Playwright edit → reload. Проверяются slug stability/regeneration, text boundaries и DST offset selection. После Task 07 добавляется regression PATCH vs publish.

**Verification:** Baseline `make check`; targeted unit/integration и component tests; `make api-generate`; `make check`; `make test`; финальный `make verify` перед PR. E2E проверяет сохранение и отсутствие изменений после rejected PATCH; screenshots и staged diff проверяются перед PR.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс acceptance criteria задачи и проверенное поведение partial PATCH под PostgreSQL lock.

**Files / interfaces:** Расширить Event schemas/repository/service/router из Task 05; добавить edit page в `frontend/src/features/events/`, route и tests; regenerate API types. Task 06 владеет DRAFT PATCH contract. Published editing позднее расширяет тот же endpoint отдельным use-case, сохраняя validation/lock ordering.

## Утверждённые решения

Пользователь утвердил в чате: `1А, 2Б, 3А, 4А, 5А, 6А, 7А, 8А`. Здесь зафиксированы решения, относящиеся к Task 06.

| Вопрос | Утверждённое решение |
|---|---|
| PATCH success/validation (1А) | Success → 200; invalid input → 422 VALIDATION_ERROR; отсутствующее событие → 404 EVENT_NOT_FOUND; чужое событие → 403 EVENT_NOT_OWNER. |
| Text/timezone (2Б, 4А) | Title: 1–200 символов после trim; description обязательно, 1–10 000 символов; обычный текст. UI local time в IANA timezone, UTC storage; nonexistent DST time отклоняется, ambiguous time требует явного выбора offset. |
| Draft slug (5А) | Смена title сохраняет slug. Отдельная кнопка «Обновить ссылку» регенерирует slug backend только в DRAFT. После publish slug immutable. |
| PATCH вне DRAFT (6А) | PUBLISHED → 409 EVENT_NOT_EDITABLE; CANCELLED → 409 EVENT_CANCELLED. Новые правила не реализуют published editing в Day 2. |
| Temporal guard | При `now >=` исходного `starts_at` schedule/capacity changes → 409 EVENT_ALREADY_STARTED, согласно spec и принятому scope. |

Точные request fields для partial PATCH и явной регенерации slug, validation details и signatures конкретизируются перед реализацией в рамках утверждённого scope. Политика этих операций уже утверждена.

## Результат задачи и ручная проверка

После implementation owner сможет редактировать DRAFT через UI `/organizer/events/:eventId/edit` и `PATCH /api/events/{event_id}`. Endpoint требует auth и CSRF/Origin.

1. Создать DRAFT с будущим starts_at через Task 05.
2. Открыть edit page, изменить title/description, interval/timezone или capacity, сохранить.
3. Открыть details и mine, выполнить reload; убедиться, что значения сохранены, owner/status прежние.
4. Отправить invalid interval/capacity/timezone; убедиться, что PATCH отклонён и предыдущие данные целиком сохранены.
5. Под другим аккаунтом проверить отказ в редактировании. Временные границы проверять автоматическими Fixed Clock tests.

## Approval / execution

- [x] Утвердить решения опроса: `1А, 2Б, 3А, 4А, 5А, 6А, 7А, 8А`.
- [x] Утвердить Goal, Scope, PR boundary и план задачи: пользователь «Планы утверждаю.»
- [x] Перед реализацией конкретизировать технические шаги, schemas и signatures в рамках утверждённого scope. Изменение требований или scope требует отдельного согласования.
- [x] После разрешения создать branch/worktree от merged Task 05, подтвердить baseline и создать task development log до изменения кода.

## Execution interfaces

`EventPatchRequest` accepts optional supplied fields and `regenerate_slug`; `model_fields_set` distinguishes omitted from explicit null. `patch_owned_event(session, clock, owner_id, event_id, body) -> Event` owns lock/state/merged-value validation and persistence. Repository exposes `find_event_for_update(...)` and atomic savepoint-backed update. `PATCH /api/events/{event_id}` returns `EventResponse` (200). The edit UI route is `/organizer/events/:eventId/edit`; form updates owner-scoped detail and mine query caches only after success.

- [x] Task 05 merge dependency confirmed; create isolated worktree from updated `master`, bootstrap, baseline `make check`, create task log.
- [x] RED/GREEN HTTP and PostgreSQL tests: partial merge validation, ownership/state errors, temporal boundary, timestamp rules, slug stability/regeneration/collision and atomic rollback.
- [x] Implement lock-safe DRAFT PATCH contract and regenerate OpenAPI types.
- [x] RED/GREEN edit form prefill/save/error/reload behavior and query cache updates; Playwright edit → reload and rejected edit preserves stored state.
- [x] Independent code review completed; Important seconds-precision finding fixed and re-reviewed; checks and remaining limitation recorded in the development log.
- [x] Create [PR #7](https://github.com/nbaishev/event-registration/pull/7) from `feat/event-draft-edit` to `master`; PR remains open for review.

### Verification evidence

- Baseline `make check`: passed before implementation (backend unit 157, frontend 58).
- Final post-review-fix `make verify`: passed (backend 273, frontend 62, empty PostgreSQL migration check, production build, 11 general browser tests, event-drafts browser test, and login limiter browser test).
- New PostgreSQL PATCH integration coverage: 35 cases; edit UI covers prefill/save, explicit slug regeneration, and preserves saved seconds during text-only edit.
- Browser screenshot: `.verification/event-edit.png` (generated during the `event-drafts` Playwright run).
- Two earlier `make verify` attempts exposed intermittent failures in existing `auth-refresh.spec.ts`; the later complete run passed without auth code changes.
- Review follow-up found no Critical or Important remaining. Minor generated typing limitation: optional PATCH fields allow `null` in TypeScript but the API rejects it with 422.
