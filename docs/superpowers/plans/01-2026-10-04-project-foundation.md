# Task 01 — Project Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Status:** Approved by user on 2026-10-04; implementation verified locally; see development log.

**Goal:** Из чистого checkout запустить frontend/backend через Compose и получить воспроизводимые проверки.

**Architecture:** Modular monolith, отдельные backend/frontend в monorepo. Nginx обслуживает один origin; PostgreSQL хранит данные; business time внедряется через Clock.

**Tech Stack:** Python, uv, FastAPI, Pydantic, sync SQLAlchemy 2.x, psycopg, Alembic, PostgreSQL; React, TypeScript, Vite, MUI, React Router, TanStack Query, pnpm; Nginx, Docker Compose. Quality stack — согласно spec.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 2–3, 32, 37.

## Global Constraints

- Один Uvicorn worker; router → service/use-case → repository/database.
- Clock возвращает timezone-aware UTC; business logic не вызывает datetime.now/utcnow.
- OpenAPI — source of truth; generated files вручную не редактируются.
- Secrets не коммитятся; persistent schema changes выполняются через Alembic.
- Состав quality gates: [engineering.md](../../agent-rules/engineering.md#состав-quality-gates).

## Task / PR boundary

**Task:** Project Foundation.

**Dependencies:** Утверждение этого плана; интеграционная ветка `master`.

**Branch:** Новая `chore/project-foundation` и отдельный worktree от актуального `master`. Текущая `feat/foundation-auth` не используется для implementation этой задачи.

**Scope:** Каркас приложений, DB sessions/Alembic, settings/Clock, Compose/Nginx, health/readiness, SPA shell, lock files, canonical Make targets, CI, generated types, README.

**Out of scope:** User/Auth, Event/Registration, SSE, Celery/Beat/Redis/Mailpit, email delivery, VPS/HTTPS deployment. Эти инфраструктурные сервисы добавляются вместе с потребляющими их features.

**Acceptance criteria:**

- `make bootstrap` устанавливает locked dependencies и создаёт локальную конфигурацию без перезаписи существующей `.env`; secrets в выводе отсутствуют.
- `docker compose up --build` после bootstrap делает `/` и `/api/health` доступными через `http://localhost:8080`.
- `/api/health` → 200 `{"status":"ok"}`; `/api/ready` → 200 `{"status":"ready"}` при доступной DB, иначе 503 с error code `SERVICE_UNAVAILABLE`.
- `/login` и `/register` при прямом открытии возвращают SPA shell; формы появятся в следующих PR.
- Backend запускается с `--workers 1`; readiness не раскрывает connection strings.
- Пустая отдельная PostgreSQL проходит Alembic upgrade/check; create_all не используется.
- Все canonical targets работают; тесты реально выполняются, CI использует полный gate.
- Повторная генерация API не меняет output; README описывает запуск и текущее ограничение «Auth ещё не реализован».

**Test strategy:** Integration, browser smoke, Verification; unit test UTC Clock. Проверять поведение, а не наличие файлов.

**Verification:** `make bootstrap`, `make up`, `make migrate`, `make api-generate`, `make test`, `make check`, `make e2e`, `make verify`, `make down`; отдельный smoke `docker compose up --build`. Все gates имеют exit 0; smoke подтверждает HTTP responses выше.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md), плюс acceptance criteria этого PR и работающий CI.

## Review Focus

- Повторный bootstrap сохраняет локальную конфигурацию.
- Недоступная DB даёт безопасный readiness failure.
- Прямой SPA route работает после reload.
- Verification не удаляет development DB.
- OpenAPI check обнаруживает drift, не переписывая tracked output.

## Files and interfaces

- Create: `backend/pyproject.toml`, `backend/uv.lock`, `backend/app/main.py`, `backend/app/common/config.py`, `backend/app/common/clock.py`, `backend/app/db/session.py`, `backend/app/db/base.py`, `backend/alembic.ini`, `backend/alembic/env.py`.
- Create: `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/src/main.tsx`, `frontend/src/app.tsx`, `frontend/src/api/schema.d.ts` (generated), frontend tool configs and `frontend/index.html`.
- Create: `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yaml`, `infra/nginx/default.conf`, `Makefile`, `scripts/export_openapi.py`, `scripts/check_api_drift.py`, `scripts/verify_migrations.py`, `.github/workflows/verify.yml`, `.env.example`.
- Modify: `.gitignore`, `README.md`.
- Tests: `backend/tests/unit/test_clock.py`, `backend/tests/integration/test_readiness.py`, `frontend/src/app.test.tsx`, `frontend/e2e/foundation.spec.ts`.
- Produces: `Clock.now() -> datetime`, `SystemClock`, `FixedClock`; `Settings` с `APP_ORIGIN=http://localhost:8080`, DB URL и environment; request-scoped SQLAlchemy `Session` с rollback/close на failure; FastAPI `app`; generated `paths`/`components` types через openapi-typescript.
- `make api-generate` экспортирует OpenAPI из app, затем генерирует `frontend/src/api/schema.d.ts`; gate сравнивает временный output с tracked file.

## Execution steps

- [x] 1. Проверить branch/worktree, создать новую branch/worktree по lifecycle; зафиксировать отсутствие baseline tests в task log до product changes. Не создавать log до разрешённого начала implementation.
- [x] 2. Создать locked toolchain и минимальные app entrypoints, необходимые для запуска smoke. Настроить Clock и DB/Alembic без business tables; проверить unit Clock: aware UTC и фиксированное время.
- [x] 3. Добавить integration readiness tests: доступная DB → 200, недоступная → 503 без DSN в response. Реализовать endpoints и lifecycle session; выполнить `make test`.
- [x] 4. Добавить Compose/Nginx и browser smoke: `/`, `/login`, `/register` доступны через один origin; `/api/health` возвращает JSON. Проверить `docker compose config`, `nginx -t`, `make up`, `make e2e`.
- [x] 5. Реализовать canonical targets и CI по engineering rules. Изолировать migration/test stack; проверить empty DB upgrade/check, обнаружение API drift, сохранение `.env` при повторном bootstrap. Generated drift probe выполнять во временной копии, без изменения working output.
- [x] 6. Обновить README, выполнить `make check`, затем `make verify`; записать фактические результаты в log, проверить staged diff на secrets и подготовить один PR в `master`.
