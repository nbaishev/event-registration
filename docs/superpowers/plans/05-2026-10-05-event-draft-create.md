# Task 05 — Event Draft Creation (Day 2)

> **For agentic workers:** План утверждён пользователем. Начинать implementation только после отдельной команды пользователя; выполнять через superpowers:executing-plans.

**Status:** Approved by user on 2026-10-05. Implemented and verified on 2026-10-05; integration pending; см. [task log](../../development-log/2026-10-05-event-draft-create.md).

**Goal:** Вошедший пользователь создаёт DRAFT, видит его в списке своих событий и открывает детали после reload.

**Architecture:** Creation service сохраняет DRAFT в PostgreSQL; ownership берётся из существующей auth dependency. OpenAPI связывает backend contract с формами и списком React.

**Tech Stack:** Существующий stack из [Product Spec](../specs/technical-design.md#3-стек).

**Spec:** [technical-design.md](../specs/technical-design.md), sections 5, 10–11, 32, 34, 36–38.

**Task / PR boundary:** Одна измеримая задача, один PR; branch `feat/event-draft-create` от актуального `master` после merge dependencies.

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
- План и решения опроса утверждены. Работа начинается только после отдельного разрешения пользователя на implementation.
- Общие quality gates и полный DoD определены в [engineering.md](../../agent-rules/engineering.md) и [AGENTS.md](../../../AGENTS.md); development loop — `make check`, pre-PR gate — `make verify`. Секреты не попадают в commits, screenshots и logs.
- Task 05 создаёт только DRAFT; редактирование и публикация реализуются в Tasks 06–07. Day 2 после всех трёх задач предоставляет create → edit draft → publish → public page.
- Registration/waitlist и связанные capacity rules относятся к Day 3; delete с реальным registration count — к последующей задаче Day 3. Не добавлять постоянный `registration_count = 0` или no-op promotion.
- Published reschedule/cancellation с уведомлениями относятся к последующим задачам Day 5; stats/SSE — к Day 4. Новые Redis/Celery/SMTP сервисы и фиктивный enqueue в этой задаче не создаются.

## Task

**Dependencies:** Foundation + Auth merged; creation/read decisions утверждены в разделе «Утверждённые решения»; перед implementation доступен работающий baseline.

**Scope:**

- Event model и новая Alembic migration: все поля section 5, FK User, unique slug, CHECK capacity/time interval.
- Creation use-case: owner из authenticated User, UUID, DRAFT, timestamps через Clock, backend-generated slug с random suffix.
- `POST /api/events`, `GET /api/events/mine`, `GET /api/events/{event_id}` с ownership validation.
- Generated API types; защищённые calls с `requiresAuth: true`.
- UI `/organizer/events`, `/organizer/events/new`, `/organizer/events/:eventId`; ссылка из аккаунта, loading/empty/error states.
- README о доступном поведении и screenshots существенных UI changes.

**Out of scope:** PATCH, publish/public page, delete/cancel, Registration, статистика, email, SSE и дополнительные инфраструктурные сервисы.

**Acceptance criteria:**

- Созданная запись имеет owner текущего пользователя и status DRAFT; `published_at`/`cancelled_at` равны NULL.
- `starts_at > clock.now()`, `capacity >= 1`, `ends_at > starts_at`, timezone проходит `zoneinfo.ZoneInfo`; invalid input → 422 VALIDATION_ERROR без создания записи.
- Title длиной 1/200 после trim и description длиной 1/10 000 принимаются; title 0/201 и description 0/10 001 отклоняются. Title из пробелов отклоняется после trim.
- Creation → 201, чтение → 200; mine — массив без пагинации, отсортированный по `created_at DESC, id DESC`.
- UI вводит local time в Event timezone; nonexistent DST time отклоняется, ambiguous time требует выбора offset. Сохранённый UTC instant соответствует выбранному времени/offset; browser timezone не меняет Event schedule.
- Title/description отображаются как текст; HTML из введённых строк не интерпретируется.
- DB CHECK отдельно отклоняет capacity 0 и invalid interval; FK/unique slug действуют в PostgreSQL.
- Slug содержит только lowercase `a-z`, `0-9`, `-` и random suffix; два события с одинаковым title получают разные slug. Искусственно вызванная коллизия обработана без перезаписи существующего события.
- `mine` показывает только события текущего пользователя; чужой detail возвращает `403 EVENT_NOT_OWNER`, отсутствующий — `404 EVENT_NOT_FOUND` (утверждённый HTTP contract).
- Без valid auth защищённое чтение/создание не выполняет business mutation; unsafe requests проходят существующую CSRF/Origin защиту.
- UI create → details → list и прямое открытие/reload работают через Nginx; сохранённые значения совпадают с API.

**Test strategy:** TDD для creation/validation/slug и ownership; PostgreSQL integration для migration/constraints/persistence и slug collision; RTL для формы и list/detail states; Playwright create → reload → mine и второй пользователь. TDD дополнительно покрывает text length boundaries, `now == starts_at`, DST gap/fold и явный offset; component tests — безопасное отображение HTML как текста.

**Verification:** Baseline `make check` до изменений; targeted tests в RED → GREEN; `make api-generate` после API changes; `make check` в development loop; `make test` для PostgreSQL integration; финальный `make verify` перед PR. Migration upgrade/check входит в полный gate. Проверить screenshots и staged diff на secrets.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс acceptance criteria задачи, reviewed migration/API contract и воспроизводимый browser scenario создания.

**Files / interfaces:** Создать `backend/app/events/{models,schemas,repository,service,router}.py`, `backend/alembic/versions/0002_create_events.py`, Event unit/integration tests, `frontend/src/features/events/` и `frontend/e2e/event-drafts.spec.ts`; подключить router в `backend/app/main.py`, metadata в Alembic и routes в `frontend/src/app.tsx`; regenerate `frontend/src/api/schema.d.ts`. Владеет Event creation/read schemas, которые импортируют следующие задачи. Точные имена frontend файлов и signatures фиксируются в отдельном task plan.

## Утверждённые решения

Пользователь утвердил в чате: `1А, 2Б, 3А, 4А, 5А, 6А, 7А, 8А`. Здесь зафиксированы решения, относящиеся к Task 05. Это approval поведения, не разрешение начать implementation.

| Вопрос | Утверждённое решение |
|---|---|
| API и список (1А) | Creation → 201; чтение/изменение → 200; invalid input → 422 VALIDATION_ERROR; отсутствующее событие → 404 EVENT_NOT_FOUND; чужое событие в organizer API → 403 EVENT_NOT_OWNER. `mine` возвращает массив без пагинации, новые события первыми: `created_at DESC, id DESC`. |
| Title/description (2Б) | Title: 1–200 символов после trim. Description обязательно: 1–10 000 символов. UI отображает обычный текст, без интерпретации HTML. |
| Creation time (3А) | При создании `starts_at > clock.now()` обязательно. `now == starts_at` и прошедшая дата отклоняются. |
| Dates/timezone (4А) | UI принимает локальную дату/время в выбранной IANA timezone; API передаёт timezone-aware ISO-8601 instants, DB хранит UTC. Несуществующее local time при DST отклоняется; для ambiguous time пользователь явно выбирает offset из двух вариантов. |

Точные response fields, validation details и signatures конкретизируются перед реализацией на основе этих решений и Product Spec, без расширения утверждённого scope.

## Результат задачи и ручная проверка

После implementation owner сможет создать и снова открыть DRAFT. API: `POST /api/events`, `GET /api/events/mine`, `GET /api/events/{event_id}` — все требуют auth.

1. После `make bootstrap` и `make up` войти через `/login` на настроенном APP_ORIGIN (по умолчанию `http://localhost:8080`).
2. Открыть `/organizer/events/new`, заполнить title/description, interval, timezone и capacity; сохранить.
3. На `/organizer/events/:eventId` проверить значения, обновить страницу; открыть `/organizer/events` и найти созданный DRAFT.
4. Под другим аккаунтом проверить, что DRAFT отсутствует в `mine` и чужие organizer details недоступны.
5. Проверить отказ при capacity 0, invalid timezone и `ends_at <= starts_at`, без создания записи.

API contract будет доступен в `/api/docs` и `/api/openapi.json`. Unsafe API requests требуют auth cookies, CSRF cookie/header и точного Origin.

## Approval / execution

- [x] Утвердить решения опроса: `1А, 2Б, 3А, 4А, 5А, 6А, 7А, 8А`.
- [x] Утвердить Goal, Scope, PR boundary и план задачи: пользователь «Планы утверждаю.»
- [x] Перед реализацией конкретизировать технические шаги, schemas и signatures в рамках утверждённого scope. Изменение требований или scope требует отдельного согласования.
- [x] Только после разрешения на implementation создать branch/worktree, подтвердить baseline и создать task development log.

## Execution steps / concrete interfaces

- [x] Read sources, create branch/worktree from `ece5102`, bootstrap, baseline `make check`, create implementation log.
- [x] RED HTTP/PostgreSQL: create 201 + fields/persistence; validation/time boundaries; mine filtering/order; owner/not-found; migration CHECK/FK/unique; slug collision recovery.
- [x] GREEN Event model/migration; `create_event(session, clock, owner_id, body) -> Event`, `list_owned_events(session, owner_id) -> list[Event]`, `get_owned_event(session, owner_id, event_id) -> Event`; router consumes existing auth/Clock/Session.
- [x] RED/GREEN `localTimeCandidates(local: string, timezone: string) -> string[]` and `resolveLocalTime(local, timezone, selected?) -> string`: DST gap/fold, browser-independent UTC result and invalid inputs.
- [x] Regenerate API; RED/GREEN create/list/detail pages with `EventCreateRequest`, `EventResponse`, `EventSummary` generated schemas; explicit protected API calls; safe text, UI states, auth loss.
- [x] Playwright create → reload → mine, invalid form, another owner; screenshots without credentials.
- [x] `make check`, PostgreSQL tests, whole-branch review, fixes, final `make verify`, log/README updates and secrets scan.

Response schema: EventResponse — все Event поля section 5; EventSummary — id, title, slug, starts_at, ends_at, timezone, capacity, status. Request schema принимает только title, description, starts_at, ends_at, timezone, capacity. POST → 201; GET → 200; validation → 422 VALIDATION_ERROR; owner/not-found → 403 EVENT_NOT_OWNER / 404 EVENT_NOT_FOUND. Temporal validation выполняется service через Clock.
