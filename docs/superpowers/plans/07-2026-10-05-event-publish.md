# Task 07 — Event Publishing + Public Page (Day 2)

> **For agentic workers:** План утверждён пользователем. Начинать implementation только после отдельной команды пользователя; выполнять через superpowers:executing-plans.

**Status:** Approved by user on 2026-10-05. Implemented on 2026-10-06; final make verify passed; [PR #8](https://github.com/nbaishev/event-registration/pull/8) open.

**Goal:** Owner публикует валидный черновик; anonymous visitor открывает событие по slug.

**Architecture:** Publication use-case блокирует Event и повторно проверяет состояние и время. Публичные API/schema и React page обслуживают anonymous visitor независимо от auth phase.

**Tech Stack:** Существующий stack из [Product Spec](../specs/technical-design.md#3-стек).

**Spec:** [technical-design.md](../specs/technical-design.md), sections 5, 8–11, 32, 34, 36–38.

**Task / PR boundary:** Одна измеримая задача, один PR; branch `feat/event-publish` от актуального `master` после merge dependencies.

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
- Task 07 завершает Day 2 create → edit draft → publish → public page. PUBLISHED editing, delete/cancel, Event registration, tickets и dashboard не входят в результат Day 2.
- Publication разрешена только при `starts_at > now`, `ends_at > starts_at`, `capacity >= 1` и valid IANA timezone; первая публикация задаёт `schedule_updated_at == published_at`.
- Public page не раскрывает DRAFT, private organizer/auth data и не запускает automatic auth recovery. FINISHED доступен с отметкой «Завершено»; после внедрения cancellation CANCELLED доступен с отметкой «Отменено».
- Capacity/Registration и удаление с реальным registration count — последующие задачи Day 3; SSE/stats — Day 4; reschedule/cancellation notifications — Day 5. Успешные no-op integrations не добавляются.
- UI не предлагает ещё недоступную регистрацию участника, отмену, удаление или редактирование опубликованного события.

## Task

**Dependencies:** [Task 05](05-2026-10-05-event-draft-create.md) и [Task 06](06-2026-10-05-event-draft-edit.md) merged; утверждены publication/public-response semantics.

**Scope:**

- `POST /api/events/{event_id}/publish` под Event `FOR UPDATE`, повторные owner/state/time checks.
- `DRAFT → PUBLISHED`, `published_at` и `schedule_updated_at` получают одно значение Clock при первой публикации.
- `GET /api/public/events/{slug}` и публичная response schema без private User/auth data.
- Organizer publish action и public link; UI `/events/:slug`, event timezone display, loading/not-found/error states.
- Публичный API call без `requiresAuth: true`; authenticated organizer calls с явным opt-in.
- Effective FINISHED отображается по времени без изменения persisted status; generated types и итоговый Day 2 E2E.

**Out of scope:** Event registration/CTA с обещанием работающей регистрации, participants list, cancel/delete, published edits, email, stats/SSE.

**Acceptance criteria:**

- Owner публикует DRAFT только если `starts_at > now`, `ends_at > starts_at`, `capacity >= 1` и valid IANA timezone.
- При `now == starts_at` publication отклоняется без mutation; invalid publication использует `409 EVENT_NOT_PUBLISHABLE`.
- Первая публикация устанавливает PUBLISHED и `schedule_updated_at == published_at`; оба timestamps получены через Clock.
- Publication не меняет slug; после publish попытка сменить slug не сохраняется.
- Чужой пользователь не публикует Event. Concurrent publish/PATCH не обходят проверки состояния; результат соответствует одному последовательному порядку операций.
- Anonymous public GET → 200 для PUBLISHED; DRAFT/unknown slug → 404 EVENT_NOT_FOUND.
- Повторный publish уже PUBLISHED и publish CANCELLED → 409 EVENT_NOT_PUBLISHABLE; status, published_at и schedule_updated_at не меняются.
- Публичная страница открывается после failed refresh и logout без запуска automatic auth recovery.
- При `now == ends_at` событие effective FINISHED; в DB status остаётся PUBLISHED. Public page показывает «Завершено»; будущая cancellation task сохраняет страницу CANCELLED с отметкой «Отменено».
- Сквозной browser scenario create → edit → publish → anonymous public page проходит через Compose/Nginx; direct navigation/reload сохраняют доступность страницы.

**Test strategy:** TDD lifecycle и Fixed Clock boundaries; HTTP/PostgreSQL ownership/visibility/concurrent publish vs PATCH; RTL publish/public states; Playwright с отдельным anonymous browser context и regression failed refresh → public page. Проверяются повторный publish без timestamp mutation, public DRAFT/unknown 404 и ended-event display; CANCELLED response можно проверить через DB fixture без добавления cancellation endpoint.

**Verification:** Baseline `make check`; targeted lifecycle/integration/component tests; `make api-generate`; `make check`; `make test`; финальный `make verify` перед PR. Полный gate включает Day 2 browser scenario и существующие Auth regressions. Screenshots и staged diff проверяются перед PR.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс acceptance criteria задачи и полный Day 2 browser scenario. Готовность Day 2 оценивается после merge всех трёх PR и успешного полного gate на интеграционной ветке.

**Files / interfaces:** Расширить Event backend и tests; добавить public page и publish action в `frontend/src/features/events/`, route `/events/:slug`, `frontend/e2e/event-publish.spec.ts`; regenerate API types. Task 07 владеет publication и public response contract. Он не вводит Registration fields или статистические counters в Event.

## Утверждённые решения

Пользователь утвердил в чате: `1А, 2Б, 3А, 4А, 5А, 6А, 7А, 8А`. Здесь зафиксированы решения, относящиеся к Task 07. Это approval поведения, не разрешение начать implementation.

| Вопрос | Утверждённое решение |
|---|---|
| Publication (7А) | Первый publish → 200. Непубликуемый DRAFT, CANCELLED и повторный publish уже PUBLISHED → 409 EVENT_NOT_PUBLISHABLE. Отказ не меняет status/timestamps. |
| Public visibility (8А) | DRAFT/unknown slug → 404 EVENT_NOT_FOUND. PUBLISHED доступен и после окончания с отметкой «Завершено». После реализации cancellation CANCELLED сохраняет публичную страницу с отметкой «Отменено». |
| Immutable slug / published PATCH (5А, 6А) | Publication сохраняет slug; PUBLISHED PATCH → 409 EVENT_NOT_EDITABLE, без изменения slug или других полей. |
| Public text/time display (2Б, 4А) | Title/description показываются как обычный текст. Schedule отображается в Event IANA timezone; persisted timestamps UTC. |

CANCELLED visibility — утверждённый контракт для последующей cancellation task, не добавление операции отмены в Day 2. Effective FINISHED не меняет persisted PUBLISHED status. Точная public response schema фиксируется в детальном implementation plan.

## Результат Day 2 и ручная проверка

После implementation Tasks 05–07 organizer сможет создать DRAFT, отредактировать его, опубликовать и поделиться публичной ссылкой. Посетитель сможет прочитать событие без аккаунта. Регистрация на событие, отмена/удаление и редактирование PUBLISHED будут следующими этапами.

| Method | Endpoint | Доступ / результат |
|---|---|---|
| POST | `/api/events` | Auth + CSRF/Origin; создать DRAFT |
| GET | `/api/events/mine` | Auth; список своих событий |
| GET | `/api/events/{event_id}` | Auth + owner; organizer details |
| PATCH | `/api/events/{event_id}` | Auth + owner + CSRF/Origin; изменить DRAFT |
| POST | `/api/events/{event_id}/publish` | Auth + owner + CSRF/Origin; опубликовать |
| GET | `/api/public/events/{slug}` | Public; прочитать опубликованное событие |

1. После `make bootstrap` и `make up` войти через `/login` на настроенном APP_ORIGIN (по умолчанию `http://localhost:8080`).
2. Создать событие через `/organizer/events/new` с будущим starts_at; изменить через `/organizer/events/:eventId/edit`, проверить сохранение после reload.
3. На `/organizer/events/:eventId` выполнить publish и получить ссылку `/events/:slug`.
4. Открыть ссылку в отдельном anonymous browser context; проверить title/description, schedule/timezone и capacity. Выполнить direct reload.
5. Открыть public URL неопубликованного DRAFT: его данные не должны раскрываться. После logout public URL опубликованного события остаётся доступен.
6. Под другим аккаунтом проверить отказ в organizer edit/publish.

Публичный API можно проверить без cookies: `curl --fail "$APP_ORIGIN/api/public/events/$SLUG"`, где APP_ORIGIN — настроенный origin, SLUG — slug опубликованного события. API documentation: `/api/docs`; OpenAPI: `/api/openapi.json`. Публичный каталог всех событий (`GET /api/public/events`) не входит в spec/Day 2.

Автоматическая проверка: `make check`, `make test`, `make e2e`; финальный `make verify` включает integration, migration/build/proxy checks и сквозной browser scenario. Это команды для будущей реализации; их успешное выполнение сейчас не заявляется.

## Approval / execution

- [x] Утвердить решения опроса: `1А, 2Б, 3А, 4А, 5А, 6А, 7А, 8А`.
- [x] Утвердить Goal, Scope, PR boundary и план задачи: пользователь «Планы утверждаю.»
- [x] Перед реализацией конкретизировать технические шаги, schemas и signatures в рамках утверждённого scope. Изменение требований или scope требует отдельного согласования.
- [x] Только после разрешения на implementation создать branch/worktree, подтвердить baseline и создать task development log.

## Технические шаги реализации

1. Backend TDD: publish_owned_event(session, clock, owner_id, event_id), lock → owner/state/ZoneInfo/interval/capacity/time checks → save. Тimestamps одной Clock.now().
2. PublicEventResponse содержит id/title/description/slug/starts_at/ends_at/timezone/capacity/status (PUBLISHED/FINISHED/CANCELLED). get_public_event(session, clock, slug) выбирает только PUBLISHED/CANCELLED и вычисляет effective status. Public router без auth dependencies; no-store.
3. Generated API types; publish mutation обновляет detail и invalidates mine; public query keyed by slug вне OrganizerLayout.
4. PostgreSQL lifecycle/visibility/races, RTL publish/public/auth regressions, Playwright create→edit→publish→anonymous/reload/failed refresh.
5. make check/test/verify, screenshots, review, журнал и PR.

## Execution result

Publication/public vertical slice реализован; миграция не требуется. Итоговое review выявило delayed detail GET / publish cache race, исправленную через exact query cancellation с RED→GREEN regression. Финальный make verify: backend286, frontend76, E2E14; migration/build/proxy gates passed. Фактические команды, timestamps и ограничения: [development log](../../development-log/2026-10-06-event-publish.md).
