# Event Registration Service

Клиент-серверный сервис регистрации на мероприятия. Реализованы Foundation и
Auth Register/Login/Logout/Refresh: PostgreSQL, Alembic, FastAPI и React UI аккаунта.
Добавлены создание, список и owner-details черновиков мероприятий.
Публикация, редактирование, регистрации на мероприятия, waitlist, билеты и уведомления пока не реализованы.

## Требования

- Python 3.12 и uv 0.12.5;
- Node.js 22.13+ (ветка 22), Corepack 0.34.0; pnpm 10.18.3 закреплён в package.json;
- Docker Engine и Docker Compose с поддержкой `up --wait`;
- make.

При старом Corepack обновите его: `npm install --global corepack@0.34.0`.

## Локальный запуск

```bash
make bootstrap
make up
```

Bootstrap устанавливает зависимости по lock files, создаёт `.env` из
`.env.example`, если `.env` ещё нет. Повторный запуск сохраняет существующую
конфигурацию и добавляет отсутствующий local `JWT_SECRET` (32 случайных bytes,
без вывода). Существующий secret сохраняется. В `.env.example` secret пустой;
production требует явно заданный secret и HTTPS `APP_ORIGIN`.

Откройте http://localhost:8080/register. Укажите email и пароль длиной 12–128 символов.
После создания аккаунта форма переходит на `/login`. После входа `/` показывает
email и кнопку выхода; reload восстанавливает аккаунт через `/api/auth/me`.
Frontend и API работают через Nginx в одном origin.

```bash
curl --fail http://localhost:8080/api/health
curl --fail http://localhost:8080/api/ready
```

Ответы: `{"status":"ok"}` и `{"status":"ready"}`. При недоступной DB readiness
возвращает 503 `SERVICE_UNAVAILABLE`, без DB credentials. API documentation:
http://localhost:8080/api/docs. Backend запускается ровно с одним worker.

Альтернативный запуск после bootstrap: `docker compose up --build`.
Backend выполняет `alembic upgrade head` перед запуском сервера; миграция `0001`
создаёт таблицу `users`, `0002` — `events`. Дополнительная команда `make migrate` для первого запуска не нужна.

Остановка: `make down`. Данные PostgreSQL сохраняются в Compose volume.
DB port не публикуется в development stack. Если порт 8080 занят, измените
APP_PORT и APP_ORIGIN в `.env` согласованно. Container backend получает DB_HOST и POSTGRES_USER/PASSWORD/DB раздельно;
SQLAlchemy собирает URL безопасно, включая reserved characters в password.
Host tooling получает test URL отдельно.
Для production HTTP-конфигурация не предназначена; HTTPS/VPS deployment — Day 6.

## Регистрация аккаунта

`GET /api/auth/csrf` выдаёт token и session cookie `csrf_token` (Path `/`, SameSite=Lax,
без Domain и HttpOnly; Secure в production). Клиент хранит token в памяти и отправляет
`X-CSRF-Token` с unsafe-запросами. Backend проверяет CSRF и exact Origin до разбора тела.
`APP_ORIGIN` должен содержать scheme/host/port без trailing slash, path, query и credentials.

`POST /api/auth/register` возвращает 201 с id, нормализованным email и UTC timestamps;
пароль хранится только как Argon2id hash. Auth cookies при регистрации не выдаются.
Ошибки: 409 `EMAIL_ALREADY_REGISTERED`, 422 `VALIDATION_ERROR`, 403 `CSRF_INVALID`.
При недоступности БД возвращается безопасный 503 `SERVICE_UNAVAILABLE`; неожиданные
ошибки auth возвращают 500 `INTERNAL_ERROR` в том же JSON envelope без внутренних данных.
Все auth responses содержат `Cache-Control: no-store`.

## Вход и выход

`POST /api/auth/login` принимает email/password с той же валидацией, что register,
и возвращает 200 UserResponse. Неверные credentials → 401 `AUTH_INVALID_CREDENTIALS`.
`GET /api/auth/me` возвращает текущий User или 401 `AUTH_REQUIRED`.
`POST /api/auth/logout` возвращает 204 без body, требует CSRF/Origin и удаляет cookies;
повторный logout также 204. Logout сохраняет CSRF cookie и очищает frontend query cache.

Access/refresh — stateless HS256 JWT в host-only HttpOnly SameSite=Lax cookies:
`access_token` (Path `/api/`, 900 seconds), `refresh_token`
(Path `/api/auth/refresh`, 2592000 seconds). Secure включён в production.
JWT не возвращаются в JSON и не хранятся в browser storage.
Защищённые API calls явно задают `requiresAuth: true`; публичные запросы
не ограничиваются auth phase. При 401 `AUTH_REQUIRED` защищённого запроса клиент один раз вызывает
`POST /api/auth/refresh`: 200 UserResponse и новый access cookie. Исходный refresh
не переустанавливается и истекает через 30 дней после входа. Параллельные запросы
разделяют результат одной refresh attempt, в том числе failed; новый ручной запрос
после failure может повторить recovery. Каждый запрос повторяется максимум один раз.
Вход в другой аккаунт ждёт текущий refresh и блокирует новую recovery до login response.
Невалидный refresh → 401 `AUTH_REFRESH_INVALID`, удаление обеих auth cookies,
очистка query cache и переход на `/login`. Network/403/5xx показывают ошибку.
Logout блокирует recovery, ждёт уже начатый refresh, затем удаляет browser cookies;
выданный JWT не отзывается на сервере.

Nginx ограничивает только точный login route: `10r/m`, `burst=5 nodelay` по реальному
client IP. Rejection → 429 `AUTH_RATE_LIMITED` в общем JSON envelope с no-store;
произвольный X-Forwarded-For не меняет limiter key.

## Черновики мероприятий

После входа откройте «Мои мероприятия» в аккаунте или `/organizer/events`.
Создайте черновик на `/organizer/events/new`: название 1–200 символов после trim,
обязательное описание 1–10 000 символов, будущая дата начала, дата окончания после
начала, IANA timezone и целое положительное количество мест.

Даты вводятся в выбранном часовом поясе; сохраняются в UTC и отображаются в timezone
события. Несуществующее время при переходе DST отклоняется; для неоднозначного
времени форма требует явного выбора UTC offset. Название/описание отображаются
обычным текстом, HTML не интерпретируется.

После сохранения откроется `/organizer/events/:eventId`. Reload сохраняет данные;
`/organizer/events` показывает только собственные мероприятия, новые первыми.
Событие создаётся с status DRAFT; редактирование и публикация — следующие задачи.
Публичная страница по slug пока недоступна.

| Method | Endpoint | Результат |
|---|---|---|
| POST | `/api/events` | 201 EventResponse, новый DRAFT |
| GET | `/api/events/mine` | 200 массив EventSummary, `created_at DESC, id DESC` |
| GET | `/api/events/{event_id}` | 200 EventResponse, только owner |

Все endpoints требуют access-cookie auth; POST также CSRF и exact Origin.
Client задаёт `requiresAuth: true`, поэтому существующий refresh flow работает и
для этих запросов. Неавторизованный запрос → 401 AUTH_REQUIRED; чужой Event →
403 EVENT_NOT_OWNER; отсутствующий → 404 EVENT_NOT_FOUND; invalid input →
422 VALIDATION_ERROR. API contracts доступны в `/api/docs` и `/api/openapi.json`.
Slug генерирует backend с random suffix, уникальность обеспечена PostgreSQL.

[Форма создания](docs/screenshots/event-create.png) · [Сохранённый черновик](docs/screenshots/event-detail.png).

Browser test проверяет create → details reload → mine reload и отказ второму
аккаунту. Полный gate: `make verify`.

## Проверки

Для `make e2e` и `make verify` отдельно установите Chromium после bootstrap:

```bash
cd frontend && corepack pnpm exec playwright install --with-deps chromium
```

На Linux установка системных зависимостей браузера может требовать sudo.
Для запуска backend/frontend и `make check` браузер не нужен. CI устанавливает
его отдельным шагом только в job `e2e`.

```bash
make check          # быстрый development gate, без Docker/PostgreSQL
make test           # pytest unit/integration на отдельной PostgreSQL + Vitest
make e2e            # build + отдельный Compose stack + Playwright через Nginx
make verify         # полный pre-PR gate, включая миграции и production builds
make api-generate   # regenerate TypeScript из FastAPI OpenAPI
```

Точный состав gates: [engineering rules](docs/agent-rules/engineering.md#состав-quality-gates).
CI для PR в master запускает два независимых job: `verify` (`make verify-ci`,
все non-browser gates) и `e2e` (`make e2e`, Playwright). Локальный `make verify`
по-прежнему выполняет полный gate. Test/verify/e2e создают уникальные
Compose projects с отдельной database, dynamic localhost ports и удаляют только
свои контейнеры/volumes, в том числе при failure. Development volume не очищается.
Миграционная проверка отказывается работать с непустой test DB.

Generated `frontend/src/api/schema.d.ts` не редактируется вручную. `make check`
экспортирует OpenAPI без запущенного backend и сравнивает временную генерацию с
tracked output; drift завершает gate с ошибкой без перезаписи файла.

## Документы

- [Product spec](docs/superpowers/specs/technical-design.md)
- [Foundation plan](docs/superpowers/plans/01-2026-10-04-project-foundation.md)
- [Event Draft Creation plan](docs/superpowers/plans/05-2026-10-05-event-draft-create.md)
- [Development lifecycle](docs/development-process.md)
- [Agent instructions](AGENTS.md)
