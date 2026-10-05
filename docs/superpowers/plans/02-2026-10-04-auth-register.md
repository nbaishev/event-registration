# Task 02 — Auth Register Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Status:** Approved by user on 2026-10-04; implementation completed and verified; awaiting PR review.

**Goal:** Пользователь создаёт аккаунт через `/register` и переходит на `/login`.

**Architecture:** Register use-case нормализует email, валидирует password, хеширует Argon2id и сохраняет User. API и UI используют единый OpenAPI contract; unsafe requests защищены общим CSRF/Origin guard.

**Tech Stack:** Foundation stack, Argon2id, pytest, PostgreSQL integration, RTL/Vitest, Playwright.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 4, 24–25, 32, 34, 36–37.

## Global Constraints

- Password: Argon2id, 12–128 characters; email: trim + lowercase.
- User: UUID id, unique non-null email, non-null password_hash, created_at/updated_at timestamptz.
- Никаких Event/Registration tables, roles или RefreshSession.
- Unsafe requests проверяют CSRF и exact Origin до выполнения use-case.
- Clock, migrations, generated API и gates — [engineering rules](../../agent-rules/engineering.md).

## Task / PR boundary

**Task:** Auth Register.

**Dependencies:** Foundation PR merged в `master`.

**Branch:** Новая `feat/auth-register` и отдельный worktree от обновлённого `master` после merge Foundation.

**Scope:** User migration/model/repository, registration service/API/UI, публичный CSRF endpoint, общая unsafe-request защита, error envelope и generated types.

**Out of scope:** Автоматический login после register; login/logout/refresh, email verification, recovery, organizer UI.

**Acceptance criteria:**

- Register success → 201 `UserResponse`, без auth cookies; frontend переходит на `/login`, password не переносится в URL/state/storage.
- Password длиной 12/128 принимается, 11/129 даёт 422 `VALIDATION_ERROR`; password не trim/normalize.
- Email trim/lowercase выполняется до email validation; невалидный email → 422 `VALIDATION_ERROR`.
- Duplicate normalized email → 409 `EMAIL_ALREADY_REGISTERED`; две конкурентные попытки дают один User, один success и один 409.
- Hash имеет Argon2id format и проверяет password; hash/plaintext отсутствуют в response/logs.
- Для POST/PUT/PATCH/DELETE missing/mismatched CSRF или missing/foreign/`null` Origin → 403 `CSRF_INVALID`, без DB mutation. Проверка CSRF/Origin предшествует body validation.
- GET csrf доступен без auth и выдаёт cookie/token; форма отправляет token header и показывает ошибки по `error.code`.

**Test strategy:** TDD для service и guards; настоящая PostgreSQL для уникальности; component и E2E registration flow.

**Verification:** `make test`, `make migrate`, `make api-generate`, `make check`, `make e2e`, `make verify`. Полный gate проверяет миграцию с пустой DB; E2E подтверждает переход на `/login` и duplicate error.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md), плюс acceptance criteria и User migration.

## Review Focus

- Email case/whitespace не позволяют создать duplicate.
- Конкурентный unique violation превращается в 409 с rollback.
- Origin сравнивается целиком, без prefix/suffix matching.
- Password границы считаются по characters, без silent truncation.
- Ошибки validation не содержат submitted password.

## API contract (owned by this task)

`UserResponse = {id: UUID, email: string, created_at: UTC ISO-8601 datetime, updated_at: UTC ISO-8601 datetime}`. Password/hash не входят.

`RegisterRequest = {email: string, password: string}`.

- `GET /api/auth/csrf`: 200 `{"csrf_token":"<token>"}`; cookie `csrf_token`, host-only (Domain omitted), Path `/`, SameSite=Lax, HttpOnly=false, Secure=true в production HTTPS и false в local HTTP; session cookie. Token генерируется cryptographically securely; header `X-CSRF-Token` должен совпадать с cookie через constant-time comparison.
- `POST /api/auth/register`: 201 UserResponse; 409 EMAIL_ALREADY_REGISTERED; 422 VALIDATION_ERROR; 403 CSRF_INVALID. Register не выдаёт access/refresh cookies.
- Exact Origin берётся из `APP_ORIGIN`; trailing slash/path не допускаются в configured origin. Проверяются scheme/host/port без wildcard; Referer не заменяет missing Origin.
- Все auth responses используют `Cache-Control: no-store`.
- Ошибки: `{"error":{"code":"...","message":"...","details":{}}}`. Validation details: `{"fields":[{"field":"email|password","code":"INVALID_EMAIL|PASSWORD_LENGTH"}]}`; не включать input value. Общие malformed body ошибки: `VALIDATION_ERROR`, `details={}`.

## Files and interfaces

- Create: `backend/app/auth/models.py`, `schemas.py`, `repository.py`, `passwords.py`, `service.py`, `router.py`; `backend/app/common/errors.py`, `csrf.py`; `backend/alembic/versions/0001_create_users.py`.
- Modify: `backend/app/main.py`, Alembic metadata import, `frontend/src/app.tsx`, generated `frontend/src/api/schema.d.ts`.
- Create: `frontend/src/api/client.ts`, `frontend/src/features/auth/register-page.tsx`.
- Tests: `backend/tests/unit/test_register.py`, `test_csrf.py`; `backend/tests/integration/test_register_api.py`, `test_user_migration.py`; `frontend/src/features/auth/register-page.test.tsx`, `frontend/e2e/register.spec.ts`.
- Consumes: Foundation Clock, Settings, request-scoped Session.
- Produces: `register_user(session: Session, clock: Clock, email: str, password: str) -> User`; `hash_password(password: str) -> str`; `verify_password(password: str, password_hash: str) -> bool`; `validate_unsafe_request(request: Request, settings: Settings) -> None`; UserResponse and shared error handlers.
- Frontend `apiRequest<T>(path: string, options: RequestInit) -> Promise<T>` uses same-origin credentials, CSRF bootstrap/header for unsafe methods, typed ApiError; token storage is in memory only. JWT handling отсутствует.

## Execution steps

- [x] 1. Создать новую branch/worktree, прочитать sources и выполнить baseline `make check`; создать task log до implementation, сообщить failures.
- [x] 2. RED: normalizing email, password lengths 11/12/128/129, hash verification и безопасные validation errors; реализовать service/password validation до GREEN.
- [x] 3. Добавить User migration/repository; PostgreSQL tests утверждают поля/unique constraint и конкурентный normalized duplicate: один 201, один 409, одна row. Реализовать IntegrityError mapping с rollback; выполнить `make test`.
- [x] 4. RED: csrf bootstrap и matrix unsafe methods × invalid cookie/header/Origin; spy подтверждает отсутствие вызова use-case при failure. Реализовать guard/errors/API; подтвердить HTTP statuses, UserResponse и no-store.
- [x] 5. Выполнить `make api-generate`. RTL test: submit success → `/login`, duplicate → error, password не попадает в navigation state; реализовать форму/client. Playwright проходит реальный register через Nginx.
- [x] 6. Выполнить `make check`, `make verify`; обновить log и README, проверить staged diff на secrets, подготовить один PR в `master`.
