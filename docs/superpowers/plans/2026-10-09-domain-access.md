# Запуск на VPS по HTTP — план

Статус: APPROVED — пользователь утвердил план и выбрал временный HTTP deployment с `ENVIRONMENT=development`.

**Task:** Production Compose и инструкция запуска на VPS без HTTPS.
**Goal:** Приложение доступно по одному HTTP origin; работают авторизация, SSE и email tasks.
**Branch:** `chore/domain-access`.
**Dependencies:** Существующие Dockerfiles, Nginx proxy, PostgreSQL, Redis, Celery worker/beat.

## Required context

- `compose.yaml`, `.env.example`, `.gitignore`, `backend/Dockerfile`, `frontend/Dockerfile`, `infra/nginx/default.conf`.
- `backend/app/common/config.py`: Settings и validate_startup.
- `backend/app/auth/cookies.py`, `backend/app/auth/router.py`: Secure cookies.
- `docs/agent-rules/engineering.md`: SSE, Auth, Nginx, Secrets, Canonical commands.
- `docs/development-process.md`: lifecycle и Git flow.

## Конфликт требований

Пользователь запрашивает production без HTTPS. Engineering rules требуют HTTPS production configuration. `ENVIRONMENT=production` с HTTP origin блокирует startup; auth/CSRF cookies имеют Secure и не обеспечат вход по обычному HTTP на домене VPS.

До уточнения не создавать конфигурацию, которая формально production, но не запускается или не поддерживает вход.

Согласованное решение: временный HTTP deployment существующих production Docker images с `ENVIRONMENT=development`. Изменяются только инфраструктурные файлы и документация; это явно временный режим, не production security mode. Backend не меняется.

## Scope после выбора режима

- Создать самостоятельный `compose.prod.yaml`, используемый без `compose.yaml`.
- Создать `.env.prod.example` с placeholders; добавить только его исключение в `.gitignore`. Реальный `.env.prod` остаётся вне Git.
- Создать `docs/deployment-vps.md` с инструкциями запуска, обновления и остановки.
- PostgreSQL persistent volume; Redis, backend, frontend, worker и ровно один beat.
- Restart policy и ограничение размера Docker logs для долгоживущих сервисов.
- Только Nginx публикует HTTP port 80 на VPS; PostgreSQL/Redis/backend/frontend не публикуют host ports.
- Backend запускается с одним Uvicorn worker; сохраняются login rate limit и настройки SSE существующего Nginx.
- SMTP — внешний relay, не Mailpit; credentials передаются backend/worker/beat явно из `.env.prod`.
- Обязательные origin, JWT secret и DB password без development fallback; JWT не менее 32 bytes.

## Out of scope

Certbot, HTTPS, сертификаты, автоматический DNS, фактический доступ к VPS, изменение схемы БД, новые архитектурные подсистемы, изменение backend security contract.

## Implementation steps

- [x] Уточнить HTTP-режим и утвердить этот план: выбран `ENVIRONMENT=development`.
- [x] Создать development log перед изменением конфигурации.
- [x] Создать `compose.prod.yaml`, `.env.prod.example` и исключение в `.gitignore` согласно scope.
- [x] Подготовить инструкцию VPS: Docker Engine с Compose plugin, DNS A/AAAA на VPS, firewall для SSH/HTTP, clone нужной revision, копирование example в `.env.prod`, `chmod 600`, заполнение secrets/SMTP/origin.
- [x] Документировать команды: `docker compose --env-file .env.prod -f compose.prod.yaml config --quiet`, затем `up -d --build --wait --wait-timeout 180`. Учесть существующий backend entrypoint: Alembic migrations перед Uvicorn.
- [x] Документировать проверку `/api/ready`, register/login/refresh/logout, SSE и email delivery. При нестандартном порте APP_ORIGIN включает порт.
- [x] Документировать обновление: backup PostgreSQL до миграций, checkout revision, build/up; остановка через down без `-v`. Откат образа не гарантирует обратимость DB migrations.
- [x] Проверить Compose render с безопасными тестовыми значениями и отсутствие опубликованных внутренних портов; проверить Git ignore для обоих env-файлов, SMTP propagation, Nginx config и старт HTTP/auth выбранного режима.
- [x] Review diff и исправления; финальный `make verify` согласно engineering rules. Отдельно проверить production Compose: обычный gate использует существующий test stack.
- [x] Обновить log фактически выполненными проверками и ограничениями; staged diff проверен на secrets. PR не создавался.

## Acceptance criteria

- Standalone Compose валиден и не зависит от development `.env`/Mailpit.
- Origin совпадает с адресом браузера; HTTP auth работает в согласованном режиме.
- Доступен только HTTP ingress; DB сохраняется при пересоздании контейнеров.
- Worker/beat используют те же DB/JWT/origin/SMTP settings, что backend.
- Инструкция содержит первый запуск, проверку, обновление и остановку без удаления данных.
- Certbot и HTTPS не входят в изменения.

**Test strategy:** Configuration verification; backend поведение не меняется.
**Definition of Done:** `AGENTS.md` и Acceptance criteria выше. Реальный VPS smoke фиксируется отдельно и не заявляется выполненным без доступа к серверу.
