# Engineering Rules — MVP Lite

## Architecture

Backend:

```text
router
→ service/use-case
→ database/repository
```

Business rules не помещать непосредственно в:

- FastAPI routers;
- Celery tasks;
- React components;
- Nginx configuration.

---

## Clock

В application/business logic запрещено:

```python
datetime.now()
datetime.utcnow()
```

Использовать внедряемый:

```python
clock.now()
```

Production Clock возвращает UTC.

Tests используют Fixed/Fake Clock.

Не использовать `sleep()` для проверки временных границ.

---

## PostgreSQL

PostgreSQL является источником истины для:

- Event state;
- capacity;
- registrations;
- waitlist;
- ticket code;
- check-in;
- confirmation email state;
- reminder state.

Redis используется только для Celery.

---

## Lock ordering

Всегда:

```text
Event
→ Registration
```

Никогда наоборот.

```text
register/reactivate
→ Event FOR UPDATE
→ existing Registration FOR UPDATE

cancel registration
→ Event FOR UPDATE
→ Registration FOR UPDATE

PATCH Event
→ Event FOR UPDATE
→ promoted WAITLIST rows FOR UPDATE

publish Event
→ Event FOR UPDATE

cancel Event
→ Event FOR UPDATE

check-in
→ Event FOR SHARE
→ conditional Registration UPDATE

confirmation/reminder task
→ Event FOR SHARE
→ Registration FOR UPDATE
```

Не менять locking strategy без изменения Product Spec/ADR.

---

## Concurrency

Seat allocation использует PostgreSQL `FOR UPDATE`.

Check-in использует atomic conditional UPDATE.

Concurrency tests используют настоящий PostgreSQL.

Не использовать SQLite для доказательства locking behavior.

---

## Registration invariants

Не допускаются состояния:

```text
CONFIRMED + cancelled_at
WAITLIST + ticket_code
CANCELLED + ticket_code
CANCELLED + reminder_sent_at
CANCELLED + confirmation_email_sent_at
```

Application validation и DB CHECK должны соответствовать друг другу.

---

## Email tasks

Confirmation/reminder scanner фильтрует:

```text
Event.status == PUBLISHED
```

и временные условия Product Spec.

Scanner только enqueue task.

Task:

```text
Event FOR SHARE
→ Registration FOR UPDATE
→ повторная проверка состояния
→ чтение актуальных данных
→ SMTP
→ *_sent_at
→ commit
```

В MVP Registration lock удерживается во время SMTP.

Retry confirmation/reminder выполняется последующим scanner run.

---

## Check-in

Check-in обязан проверять:

- Event ownership;
- Event status;
- time window;
- Registration `CONFIRMED`;
- `event_id`;
- `checked_in_at IS NULL`.

Операция выполняется в одной transaction.

Финальное изменение — atomic conditional UPDATE.

---

## SSE

Backend запускается только с одним worker:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

In-memory broadcaster не совместим с несколькими workers.

`stats_changed` публикуется после commit для:

- registration;
- cancellation;
- promotion;
- capacity change;
- check-in.

Sync threadpool code использует:

```text
loop.call_soon_threadsafe(...)
```

или эквивалентный thread-safe mechanism.

SSE stream не держит PostgreSQL session.

---

## Auth

Использовать:

- Argon2id;
- HttpOnly JWT cookies;
- double-submit CSRF;
- exact Origin validation.

JWT нельзя хранить в:

- localStorage;
- sessionStorage.

Server-side RefreshSession в MVP не добавляется.

---

## Nginx

Обязательны:

- `limit_req` для `/api/auth/login`;
- `proxy_buffering off` для SSE;
- увеличенный `proxy_read_timeout` для SSE;
- proxy headers;
- HTTPS production configuration.

---

## Migrations

Любое persistent schema change требует Alembic migration.

Это относится также к:

- CHECK;
- UNIQUE;
- indexes;
- partial indexes.

Проверка должна подтверждать:

```text
empty PostgreSQL
→ alembic upgrade head
```

Не использовать `create_all()` как deployment strategy.

---

## Generated API

FastAPI OpenAPI — source of truth.

Generated frontend files вручную не редактируются.

После API change:

```bash
make api-generate
```

Если generated output неверный:

```text
fix source schema
→ regenerate
```

---

## Secrets

Не коммитить:

- `.env`;
- passwords;
- JWT secrets;
- SMTP credentials;
- production DB credentials;
- API tokens;
- private keys.

Коммитится только `.env.example` с placeholders или безопасными development defaults.

---

## TDD

Для задач, помеченных TDD:

```text
RED → GREEN → REFACTOR
```

Нельзя менять утверждённый тест только потому, что implementation его не проходит.

Изменение теста допустимо только если:

- изменилось утверждённое требование;
- acceptance criterion оказался ошибочным;
- сам тест неверно выражал требование.

Причина фиксируется в development log.

---

## Canonical commands

```bash
make bootstrap
make up
make down
make migrate
make api-generate
make test
make check
make e2e
make verify
```

Во время разработки:

```bash
make check
```

Перед Pull Request:

```bash
make verify
```

`make verify` не требуется после каждого небольшого изменения.

### Состав quality gates

`make test` выполняет полный backend pytest suite (unit и integration на отдельной PostgreSQL) и frontend Vitest/React Testing Library suite. Playwright запускается отдельно через `make e2e`.

`make check` — быстрый development gate:

- backend: Ruff check, Ruff format check, mypy, unit tests;
- frontend: ESLint, TypeScript typecheck, Vitest/React Testing Library;
- OpenAPI drift: экспорт schema из текущего FastAPI app без запущенного HTTP server, генерация TypeScript во временный каталог и сравнение с committed output.

Unit tests в этом gate не требуют PostgreSQL или Compose. Проверка OpenAPI не меняет committed files. PostgreSQL integration, Docker build и Playwright не входят в быстрый gate.

`make verify` — полный gate перед каждым PR:

1. `make check`;
2. `make test`;
3. миграционная проверка: пустая изолированная PostgreSQL → `alembic upgrade head`, соответствие revision head и отсутствие расхождения metadata/schema через `alembic check`;
4. frontend production build и сборка backend/frontend Docker images;
5. `docker compose config` и `nginx -t`;
6. запуск изолированного Compose test stack, readiness/same-origin smoke и `make e2e` через Nginx.

Каждый шаг обязателен; любой failure завершает gate ненулевым exit code. Нельзя заменять ещё не настроенную проверку успешной заглушкой или silently skip. Integration/E2E используют отдельные database/project names; проверка миграций никогда не очищает development/production DB. Test stack освобождается и при failure. Повторно выполнять тот же suite внутри одного gate не требуется: результаты `make check` могут переиспользоваться для `make test`, если полный набор tests действительно выполнен.

CI запускает тот же `make verify`. Day 1 Foundation task создаёт реализацию этих команд; до неё команды отсутствуют. Состав gates хранится только здесь, планы ссылаются на этот раздел.

---

## Scope restrictions

Без approved architecture change не добавлять:

- transactional outbox;
- EmailDelivery subsystem;
- отдельную Ticket table;
- RefreshSession;
- Redis Pub/Sub;
- application rate limiter;
- Redux;
- microservices.
