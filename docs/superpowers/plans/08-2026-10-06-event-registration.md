# Task 08 — Event Registration Implementation Plan (Day 3)

> **For agentic workers:** Использовать superpowers:executing-plans. Checklist ниже относится к будущей implementation; начинать только по отдельной команде пользователя.

**Status:** Декомпозиция, scope и предложенные контракты утверждены пользователем в чате 2026-10-06: «Утверждаю». Этот документ оформляет утверждённую задачу; implementation не начата.

**Task:** Регистрация участника и конкурентное распределение мест.

**Goal:** Вошедший участник регистрируется с публичной страницы и после reload видит сохранённый CONFIRMED или WAITLIST.

**Architecture:** Registration use-case блокирует Event, проверяет актуальные state/time/owner и распределяет место по SQL confirmed count. Registration хранит билет и notification timestamps; mutation и response snapshot формируются в одной транзакции. Public content и participant controls используют отдельные queries.

**Tech Stack:** Существующий FastAPI / sync SQLAlchemy 2.x / psycopg / PostgreSQL / Alembic; React / TypeScript / MUI / TanStack Query; pytest / RTL / Playwright.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 6–8, 11–12, 16–17, 25, 32, 34–38; [ADR-002](../../adr/002-postgresql-concurrency.md).

## Global Constraints

- Общие implementation rules и quality gates: [engineering.md](../../agent-rules/engineering.md); lifecycle и PR flow: [development-process.md](../../development-process.md); журнал: [development-log rules](../../agent-rules/development-log.md).
- Состояния и DB CHECK должны точно соответствовать sections 6–7 spec; FIFO — `waitlisted_at ASC, id ASC`; `CONFIRMED <= capacity`.
- Event `FOR UPDATE` предшествует existing Registration `FOR UPDATE`; count и время проверяются после получения Event lock.
- Ticket уже обязателен для CONFIRMED по spec; check-in остаётся Day 4, доставка email — Day 5, без успешных заглушек этих интеграций.
- Technical steps конкретизируют утверждённый scope; новые требования или архитектура не добавляются.

## Task / PR boundary

**Dependencies:** Merged Foundation/Auth и Tasks 05–07. При анализе `master` был `208b9dd`; branch создаётся от актуального master при разрешённом начале implementation.

**Branch:** `feat/event-registration`, один vertical-slice PR, новый отдельный worktree.

**Scope:** Registration model/migration/constraints/indexes; register/reactivate и own read; ticket generation/formatting; RegistrationResponse; participant action/status на public page; generated types и tests.

**Out of scope:** DELETE registration, FIFO promotion, capacity PATCH, `/me/registrations`, organizer participants list, Event deletion/cancellation, check-in, ticket-input normalization, email, stats/SSE.

**Acceptance criteria:**

- POST разрешён только для PUBLISHED при `now < starts_at`, current user не owner. Guard failures не изменяют DB.
- Свободное место → CONFIRMED, `confirmed_at == ticket_issued_at == now`, ticket присутствует, waitlist/cancel/check-in/email/reminder fields NULL. Нет места → WAITLIST с `waitlisted_at == now`, без ticket и прочего inactive state.
- Два конкурентных POST разных users при capacity 1 → оба 201, ровно один CONFIRMED, один WAITLIST и две rows. PostgreSQL подтверждает отсутствие oversubscription.
- Повторная активная регистрация → 409 ALREADY_REGISTERED; параллельный duplicate одного user → один 201, один 409, одна row.
- CANCELLED row переиспользуется с прежними id/created_at; перед reactivation очищаются все поля section 16. Новое CONFIRMED получает новый ticket; новое WAITLIST получает новое waitlisted_at и позицию в конце очереди.
- Ticket: 12 символов из `23456789ABCDEFGHJKMNPQRSTUVWXYZ`, raw в DB, `XXXX-XXXX-XXXX` в response/UI, unique глобально. Принудительная collision не перезаписывает другой ticket и не освобождает Event lock.
- DB отдельно отклоняет каждую нарушенную state invariant, неизвестный status, duplicate event/user и duplicate non-null ticket; несколько NULL ticket допустимы. FK и partial FIFO index присутствуют.
- Own GET возвращает только registration текущего user; position 1-based среди активных WAITLIST данного Event, остальные statuses → NULL.
- Public page сохраняет anonymous доступ после logout/failed refresh; защищённый registration call требует явного auth opt-in. Reload показывает сохранённый статус; чужие ticket/user data не раскрываются.

**Test strategy:** TDD; Fixed Clock boundaries; настоящая PostgreSQL для constraints, collision и конкуренции; RTL с controllable promises; Playwright с независимыми participant browser contexts. CANCELLED reactivation до Task 09 проверяется валидной DB fixture.

**Verification:** До кода повторить baseline `make check` и `make test`. Затем targeted tests ниже, `make api-generate`, `make check`; PostgreSQL suite через `make test`, browser suite через `make e2e` при необходимости отдельного прогона; финальный `make verify` перед PR. Ожидание: exit 0, OpenAPI drift none, migration upgrade/check и новый registration E2E выполняются в полном gate. Скриншот participant states и staged secrets review по общим правилам.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс все acceptance criteria, reviewed migration и доказанный concurrent last seat на PostgreSQL.

## API contract и утверждённые решения

| Endpoint / condition | Response |
|---|---|
| POST `/api/events/{event_id}/registrations`, без business body, creation/reactivation | 201 RegistrationResponse |
| GET `/api/events/{event_id}/my-registration`, own row, включая CANCELLED | 200 RegistrationResponse |
| Missing Event; POST/GET DRAFT | 404 EVENT_NOT_FOUND |
| Own GET без row | 404 REGISTRATION_NOT_FOUND |
| POST owner | 403 OWNER_CANNOT_REGISTER |
| POST CANCELLED Event | 409 EVENT_CANCELLED |
| POST PUBLISHED, `now >= ends_at` | 409 EVENT_FINISHED |
| POST PUBLISHED, `starts_at <= now < ends_at` | 409 EVENT_ALREADY_STARTED |
| POST existing CONFIRMED/WAITLIST | 409 ALREADY_REGISTERED |

Auth/CSRF/Origin/validation используют существующий error envelope и no-store. Business checks POST: Event existence/visibility → owner → Event state/time → existing registration. Own GET доступен для PUBLISHED/CANCELLED/finished Event и не применяет mutation time guards.

RegistrationResponse точно соответствует section 35: `id`, `event_id`, `user_id`, `status`, `confirmed_at`, `waitlisted_at`, `cancelled_at`, `waitlist_position`, `ticket_code`, `checked_in_at`. Nullable поля присутствуют как NULL; notification timestamps не экспортируются. Position и row читаются из согласованного SQL snapshot, без N+1 per-position queries.

## Files / interfaces

- Create: `backend/app/registrations/__init__.py`, `models.py`, `schemas.py`, `repository.py`, `service.py`, `tickets.py`, `router.py`; `backend/alembic/versions/0003_create_registrations.py` (revision `0003`, down_revision `0002`).
- Modify: `backend/app/main.py` (router), `backend/alembic/env.py` (metadata import).
- Create: `frontend/src/features/registrations/api.ts`, `event-registration-panel.tsx`, `event-registration-panel.test.tsx`; integrate panel in `frontend/src/features/events/public-event-page.tsx`; regenerate `frontend/src/api/schema.d.ts`.
- Tests: `backend/tests/unit/test_registration_tickets.py`, `backend/tests/unit/test_event_registration.py`, `backend/tests/integration/test_event_registration.py`, `backend/tests/integration/test_registration_migration.py`, `frontend/e2e/event-registration.spec.ts`.
- Modify `scripts/verification.py` только если новому browser flow нужен отдельный test Nginx rate budget; не менять production limiter и не исключать новый E2E из gate.

**Consumes:** `Clock.now() -> datetime`; `events.repository.find_event_for_update(session, event_id) -> Event | None`; existing CurrentUser/DatabaseSession и `apiRequest`.

**Produces:**

- `register_for_event(session: Session, clock: Clock, user_id: UUID, event_id: UUID) -> RegistrationResponse` — owns commit/rollback; response snapshot готовится под lock.
- `get_my_registration(session: Session, user_id: UUID, event_id: UUID) -> RegistrationResponse` — read-only.
- `repository.find_registration_for_update(session: Session, event_id: UUID, user_id: UUID) -> Registration | None` и `count_confirmed(session: Session, event_id: UUID) -> int`; repository helpers не commit.
- `confirm_registration(session: Session, registration: Registration, now: datetime) -> None` — reusable transition/persistence helper, own commit отсутствует; используется promotion в Task 09. Очищает предыдущий state и выдаёт ticket с bounded unique-collision retry.
- `tickets.generate_ticket_code() -> str`, `tickets.format_ticket_code(raw: str) -> str`; cryptographic randomness, максимум 5 candidate attempts, exhaustion → 503 SERVICE_UNAVAILABLE с rollback всей mutation. Retry только unique ticket constraint, не любого IntegrityError; state transition/flush помещается внутри savepoint без premature autoflush.
- Frontend `registrationKeys.detail(userId, eventId)` = `['registrations', userId, 'detail', eventId]`; `registerForEvent(eventId): Promise<RegistrationResponse>`; `getMyRegistration(eventId, signal?): Promise<RegistrationResponse | null>` преобразует только 404 REGISTRATION_NOT_FOUND в null. Calls используют `requiresAuth: true`.

Panel не превращает public page в protected route: session и own-state loading/errors не скрывают public content. Anonymous CTA ведёт на существующий login; автоматический POST после login не добавляется. После success отменить exact in-flight own query, затем записать response; не автоматически повторять mutation при network uncertainty.

## Review Focus / проверяемые случаи

| Test | Assertions |
|---|---|
| `test_last_seat_concurrency` | statuses sorted = CONFIRMED/WAITLIST; SQL counts 1/1; total 2 |
| `test_duplicate_concurrency` | HTTP statuses 201/409; ALREADY_REGISTERED; total 1 |
| `test_ticket_collision_and_exhaustion` | retry выдаёт другой ticket; exhaustion 503; исходные rows/state сохранены |
| `test_reactivation_resets_state` | old id/created_at сохранены; поля section 16 очищены; confirmed ticket новый; waitlisted position последняя |
| `delayed own GET cannot replace registration success` | response CONFIRMED остаётся в UI после settlement stale GET; public content доступен |

Дополнительные tests: `now == starts_at`, `now == ends_at`, owner/DRAFT/CANCELLED/missing, CSRF/Origin/auth без mutation; migration matrix всех non-null/null invariants; own-read isolation и FIFO tie-break по UUID.

## Execution steps

- [ ] 1. По отдельной implementation команде создать branch/worktree, прочитать sources, выполнить baseline и создать task log до кода. Незавершённый analysis baseline не считается успешным: cache failure exit 2; retry завершён interrupt exit 130 после Ruff/mypy.
- [ ] 2. Добавить unit ticket tests: length 12, alphabet, formatting `7K4P9Q2M8RTA` → `7K4P-9Q2M-8RTA`; service guard/state tests с Fixed Clock и fake repository.
- [ ] 3. Запустить `uv run --frozen --project backend pytest backend/tests/unit/test_registration_tickets.py backend/tests/unit/test_event_registration.py -q`; подтвердить RED из-за отсутствующего поведения, зафиксировать причину.
- [ ] 4. Реализовать models/schemas/ticket helpers и register/read use-cases по interfaces; добавить migration и metadata/router integration.
- [ ] 5. Повторить unit команду до GREEN; commit backend rules с тестами.
- [ ] 6. Добавить PostgreSQL tests таблицы Review Focus, constraints и API matrix; запустить `make test`, подтвердить RED для ещё не реализованной persistence/HTTP гарантии.
- [ ] 7. Довести transactional repository/router до GREEN `make test`; проверить separate sessions, lock contention и SQL конечное состояние. Barrier до mutation; не размещать barrier после Event lock, где второй запрос закономерно заблокирован.
- [ ] 8. Выполнить `make api-generate`; написать panel RTL tests: null own state → POST → status; WAITLIST position; duplicate/refetch; loading/error; anonymous public page после failed refresh; delayed query race. Подтвердить RED через `cd frontend && corepack pnpm exec vitest run src/features/registrations/event-registration-panel.test.tsx`.
- [ ] 9. Реализовать API wrapper/panel и public integration; повторить RTL команду до GREEN; commit UI и generated contract.
- [ ] 10. Добавить Playwright `event-registration` scenario: owner creates/publishes capacity 1; A registers CONFIRMED, B WAITLIST; reload обоих. E2E setup ждёт heading целевой auth формы перед fill; login budgets изолированы в test harness.
- [ ] 11. Выполнить `make check`, `make verify`; review, screenshots, журнал с actual results и staged secrets check; один PR. Day 3 полностью этим PR не закрывается.
