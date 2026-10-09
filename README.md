# Event Registration Service

Клиент-серверный сервис регистрации на мероприятия на FastAPI, PostgreSQL и React.
Реализованы аккаунты, управление мероприятиями, публичные страницы, регистрации
с очередью ожидания, билеты, check-in, live-статистика и email-уведомления.
Фоновые задачи выполняются Celery через Redis; локальная почта поступает в Mailpit.
Для production предусмотрен отдельный HTTPS stack с Nginx и Certbot.

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
создаёт таблицу `users`, `0002` — `events`, `0003` — `registrations`.
Дополнительная команда `make migrate` для первого запуска не нужна.

Остановка: `make down`. Данные PostgreSQL сохраняются в Compose volume.
DB port не публикуется в development stack. Если порт 8080 занят, измените
APP_PORT и APP_ORIGIN в `.env` согласованно. Container backend получает DB_HOST и POSTGRES_USER/PASSWORD/DB раздельно;
SQLAlchemy собирает URL безопасно, включая reserved characters в password.
Host tooling получает test URL отдельно.
Development stack также запускает Redis, Celery worker, beat и Mailpit.
Порты Redis и Mailpit не публикуются на хост; SMTP по умолчанию — `mailpit:1025`.
Для production используйте отдельный HTTPS stack (см. ниже).

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

## Управление мероприятиями

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
Событие создаётся со статусом `DRAFT`. На странице деталей доступны редактирование
(`/organizer/events/:eventId/edit`), публикация и удаление черновика.
При редактировании черновика можно заново сгенерировать slug.

После публикации ссылка `/events/:slug` доступна без входа. Черновики публично
не видны. Завершённые события отображаются как `FINISHED`, отменённые — как
`CANCELLED`. До начала опубликованного события организатор может отдельно менять
расписание или вместимость и отменить мероприятие. Вместимость нельзя уменьшить
ниже числа подтверждённых регистраций; увеличение автоматически освобождает
места для очереди ожидания. Отмена мероприятия блокирует новые регистрации
и check-in; существующие записи регистраций сохраняются.

| Method | Endpoint | Результат |
|---|---|---|
| POST | `/api/events` | 201 EventResponse, новый DRAFT |
| GET | `/api/events/mine` | 200 массив EventSummary, `created_at DESC, id DESC` |
| GET | `/api/events/{event_id}` | 200 EventResponse, только owner |
| PATCH | `/api/events/{event_id}` | Редактирование черновика; расписание или вместимость опубликованного события |
| POST | `/api/events/{event_id}/publish` | Публикация черновика |
| POST | `/api/events/{event_id}/cancel` | Отмена опубликованного события до начала |
| DELETE | `/api/events/{event_id}` | 204, удаление черновика без регистраций |
| GET | `/api/public/events/{slug}` | Публичные детали, без авторизации |

Приватные endpoints требуют access-cookie auth; изменяющие запросы также CSRF и exact Origin.
Client задаёт `requiresAuth: true`, поэтому существующий refresh flow работает и
для этих запросов. Неавторизованный запрос → 401 AUTH_REQUIRED; чужой Event →
403 EVENT_NOT_OWNER; отсутствующий → 404 EVENT_NOT_FOUND; invalid input →
422 VALIDATION_ERROR. API contracts доступны в `/api/docs` и `/api/openapi.json`.
Slug генерирует backend с random suffix, уникальность обеспечена PostgreSQL.

[Форма создания](docs/screenshots/event-create.png) · [Сохранённый черновик](docs/screenshots/event-detail.png).

## Регистрации, очередь ожидания и билеты

На публичной странице `/events/:slug` пользователь после входа может
зарегистрироваться до начала мероприятия. Организатор не может зарегистрироваться
на собственное событие. При наличии места регистрация получает статус `CONFIRMED`
и код билета; при заполнении — `WAITLIST` с позицией в очереди.

Участник может отменить регистрацию до начала и затем зарегистрироваться снова.
При освобождении места следующий участник очереди автоматически получает
подтверждение и билет. Раздел `/me/registrations` показывает собственные
регистрации, статусы мероприятий и билеты. Код билета содержит 12 символов и
отображается в формате `XXXX-XXXX-XXXX`.

| Method | Endpoint | Назначение |
|---|---|---|
| POST | `/api/events/{event_id}/registrations` | Регистрация или повторная регистрация после отмены |
| GET | `/api/events/{event_id}/my-registration` | Собственная регистрация на событие |
| DELETE | `/api/events/{event_id}/registration` | Отмена собственной регистрации |
| GET | `/api/me/registrations` | Все собственные регистрации |

Эти запросы требуют авторизации; изменяющие запросы — CSRF и exact Origin.

## Check-in и live-статистика

Организатор отмечает участников по коду билета на
`/organizer/events/:eventId/check-in`. Check-in открыт за два часа до начала
опубликованного мероприятия и до его окончания. При вводе допустимы пробелы,
дефисы и нижний регистр. Билет должен принадлежать подтверждённой регистрации
именно этого события; повторная отметка возвращает `TICKET_ALREADY_CHECKED_IN`.
API: `POST /api/events/{event_id}/check-ins` с полем `ticket_code`.

Страница деталей организатора показывает вместимость, подтверждённые регистрации,
очередь ожидания, отмеченных участников и свободные места.
`GET /api/events/{event_id}/stats` возвращает снимок статистики;
`GET /api/events/{event_id}/stats/stream` отправляет SSE-события `stats_changed`,
после которых клиент запрашивает свежий снимок. Доступ есть только у владельца,
для черновиков статистика недоступна. Клиент восстанавливает соединение при обрыве.
In-memory broadcaster требует запуска backend ровно с одним worker.

## Email-уведомления

Celery beat каждые пять минут запускает сканирование подтверждений и напоминаний.
Подтверждённый участник получает письмо с билетом, в том числе после перехода
из очереди ожидания. Напоминание отправляется в течение последних 24 часов
до начала, если регистрация была подтверждена и расписание обновлено не позднее
чем за 24 часа до начала. Неотправленные подтверждения и напоминания повторно
подбираются следующим сканированием, пока выполняются условия отправки.

Перенос и отмена мероприятия ставят отдельные письма в очередь после commit
для подтверждённых участников и очереди ожидания. Эти письма отправляются
без автоматического retry; гарантированная доставка не реализована.

Локально используется Mailpit; для production задаются `SMTP_HOST`, `SMTP_PORT`,
`SMTP_FROM`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD` и
`SMTP_TIMEOUT_SECONDS`. Поддерживаются `none`, `starttls` и `tls`.

## Production: HTTPS на VPS

Используйте `compose.prod.yaml` отдельно от development Compose и настройте
`.env.prod` по [.env.prod.example](.env.prod.example): домен, точный HTTPS origin,
отдельные секреты БД/JWT и внешний SMTP relay. Production stack публикует только
порты Nginx 80/443 и не содержит Mailpit.

Первый запуск включает HTTP bootstrap для ACME, выпуск сертификата и
`make prod-up`. Команды `make prod-ps`, `make prod-logs` и `make prod-down`
управляют stack; для продления сертификата предусмотрены
`make prod-cert-renew` и systemd timer. Настройка DNS, firewall, выпуска и
автоматического продления описана в [инструкции развёртывания на VPS](docs/deployment-vps.md).

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
- [Implementation plans](docs/superpowers/plans/)
- [Развёртывание на VPS](docs/deployment-vps.md)
- [Development lifecycle](docs/development-process.md)
- [Agent instructions](AGENTS.md)
