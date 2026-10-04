# Event Registration Service

Клиент-серверный сервис регистрации на мероприятия. Текущий этап — Foundation:
React shell, FastAPI health/readiness, PostgreSQL, Alembic и воспроизводимые проверки.
Auth, мероприятия, waitlist, билеты и уведомления пока не реализованы.

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
конфигурацию. Пример содержит только безопасные локальные defaults, не production secrets.

Откройте http://localhost:8080. `/login` и `/register` сейчас показывают Foundation
shell. Frontend и API работают через Nginx в одном origin.

```bash
curl --fail http://localhost:8080/api/health
curl --fail http://localhost:8080/api/ready
```

Ответы: `{"status":"ok"}` и `{"status":"ready"}`. При недоступной DB readiness
возвращает 503 `SERVICE_UNAVAILABLE`, без DB credentials. API documentation:
http://localhost:8080/api/docs. Backend запускается ровно с одним worker.

Альтернативный запуск после bootstrap: `docker compose up --build`.
Backend выполняет `alembic upgrade head` перед запуском сервера. Foundation ещё
не содержит business tables/revisions; конфигурация Alembic уже работоспособна.
Persistent tables добавляются миграциями соответствующих features.

Остановка: `make down`. Данные PostgreSQL сохраняются в Compose volume.
DB port не публикуется в development stack. Если порт 8080 занят, измените
APP_PORT и APP_ORIGIN в `.env` согласованно. Container backend получает DB_HOST и POSTGRES_USER/PASSWORD/DB раздельно;
SQLAlchemy собирает URL безопасно, включая reserved characters в password.
Host tooling получает test URL отдельно.
Для production HTTP-конфигурация не предназначена; HTTPS/VPS deployment — Day 6.

## Проверки

Для `make e2e` и `make verify` отдельно установите Chromium после bootstrap:

```bash
cd frontend && corepack pnpm exec playwright install --with-deps chromium
```

На Linux установка системных зависимостей браузера может требовать sudo.
Для запуска backend/frontend и `make check` браузер не нужен. CI устанавливает
его отдельным шагом.

```bash
make check          # быстрый development gate, без Docker/PostgreSQL
make test           # pytest unit/integration на отдельной PostgreSQL + Vitest
make e2e            # build + отдельный Compose stack + Playwright через Nginx
make verify         # полный pre-PR gate, включая миграции и production builds
make api-generate   # regenerate TypeScript из FastAPI OpenAPI
```

Точный состав gates: [engineering rules](docs/agent-rules/engineering.md#состав-quality-gates).
CI выполняет тот же `make verify` для PR в master. Test/verify/e2e создают уникальные
Compose projects с отдельной database, dynamic localhost ports и удаляют только
свои контейнеры/volumes, в том числе при failure. Development volume не очищается.
Миграционная проверка отказывается работать с непустой test DB.

Generated `frontend/src/api/schema.d.ts` не редактируется вручную. `make check`
экспортирует OpenAPI без запущенного backend и сравнивает временную генерацию с
tracked output; drift завершает gate с ошибкой без перезаписи файла.

## Документы

- [Product spec](docs/superpowers/specs/technical-design.md)
- [Foundation plan](docs/superpowers/plans/2026-10-04-project-foundation.md)
- [Development lifecycle](docs/development-process.md)
- [Agent instructions](AGENTS.md)
