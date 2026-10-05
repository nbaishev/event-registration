# Task 03 — Auth Login / Logout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Status:** Approved by user on 2026-10-04; implementation and whole-branch review complete; make verify passed; published as PR #4.

**Goal:** Пользователь входит, видит текущий аккаунт после reload и выходит с очисткой auth cookies.

**Architecture:** Login service проверяет Argon2id password и выдаёт типизированные stateless JWT. Auth dependency проверяет access и User в PostgreSQL. Frontend получает текущего пользователя через `/me`, tokens доступны только backend/browser cookie mechanism.

**Tech Stack:** Foundation/Auth Register stack, JWT HS256, TanStack Query, Nginx limit_req.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 24–26, 32, 34, 36–37; [ADR-003](../../adr/003-authentication-security-model.md).

## Global Constraints

- Access: 15 min; refresh: 30 days; оба в HttpOnly cookies.
- JWT не хранятся в localStorage/sessionStorage и не возвращаются в JSON.
- Stateless refresh; никаких RefreshSession/revocation/reuse detection.
- Login/logout защищены CSRF + exact Origin согласно Register plan.
- Один worker; application-level rate limiter запрещён.
- Общие technical rules/gates: [engineering.md](../../agent-rules/engineering.md).

## Task / PR boundary

**Task:** Auth Login / Logout.

**Dependencies:** Auth Register PR merged в `master`.

**Branch:** Новая `feat/auth-login-logout` и отдельный worktree от обновлённого `master`.

**Scope:** Login/me/logout, JWT issuance/validation, auth cookies, минимальный authenticated UI на `/`, frontend session bootstrap, Nginx login limiter, OpenAPI/types.

**Out of scope:** Refresh endpoint/recovery; server-side revocation; event pages; SSE; HTTPS deployment (production cookie settings входят).

**Acceptance criteria:**

- Login success → 200 UserResponse и две auth cookies; frontend переходит на `/` и показывает email/logout.
- `/me` success → 200 UserResponse; reload сохраняет authenticated UI.
- Unknown email/wrong password → одинаковые 401 AUTH_INVALID_CREDENTIALS; password/hash/token не раскрываются.
- Missing/tampered/expired/wrong-type access или отсутствующий User → 401 AUTH_REQUIRED.
- Access принимается до `exp`, при `now == exp` отклоняется; тесты используют Clock.
- Logout → 204 без body, очищает access/refresh cookies с исходными Path/Domain; повторный logout с валидным CSRF/Origin тоже 204.
- После logout `/me` → 401, frontend query cache очищен и пользователь на `/login`.
- Cookie flags соответствуют таблице ниже; CSRF/Origin failure → 403 без login/logout mutation.
- Nginx limit `10r/m`, burst=5 nodelay; rejected requests → 429; limiter действует только для login.

**Test strategy:** TDD для credentials/JWT/Clock; HTTP+PostgreSQL integration; component tests auth bootstrap/login/logout; Playwright через Nginx; proxy limiter integration.

**Verification:** `make test`, `make api-generate`, `make check`, `make e2e`, `make verify`; `docker compose exec nginx nginx -t`. E2E проверяет register → login → reload → logout и cookie flags; limiter probe использует изолированный test stack/IP.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md), плюс acceptance criteria и proxy security checks.

## Review Focus

- Refresh token не может авторизовать `/me`.
- JWT с неверным algorithm/issuer/audience отклоняется.
- Logout удаляет cookie именно с исходным Path.
- Request через похожий чужой Origin не допускается.
- Reload не создаёт flash authenticated content при anonymous session.

## Auth contract (owned by this task)

UserResponse/error envelope/CSRF contract импортируются из [Register plan](02-2026-10-04-auth-register.md#api-contract-owned-by-this-task).

- `POST /api/auth/login`: `{email:string,password:string}`; 200 UserResponse; 401 AUTH_INVALID_CREDENTIALS; 422 VALIDATION_ERROR; 403 CSRF_INVALID. Email trim/lowercase; request password 12–128 characters, без trim; malformed email/password → 422 с Register validation schema.
- `GET /api/auth/me`: 200 UserResponse; 401 AUTH_REQUIRED. CSRF не требуется.
- `POST /api/auth/logout`: без body; 204 empty; 403 CSRF_INVALID; access/refresh validity не требуется. CSRF cookie сохраняется для последующего login.
- Все responses: `Cache-Control: no-store`.

| Cookie | Path | HttpOnly | SameSite | Max-Age |
|---|---|---|---|---|
| `access_token` | `/api/` | true | Lax | 900 seconds |
| `refresh_token` | `/api/auth/refresh` | true | Lax | 2592000 seconds |

Обе host-only: Domain omitted. Secure=true при production HTTPS, false при local HTTP. Production configuration с HTTP APP_ORIGIN отклоняется на startup. Logout устанавливает Max-Age=0 и past Expires для каждой cookie, сохраняя её Path/Domain/security attributes. Raw logout response проверяется отдельно: refresh cookie не отправляется браузером на logout path, но удаляется Set-Cookie с её исходным Path.

JWT algorithm — **HS256**, allowlist только HS256; `JWT_SECRET` содержит минимум 32 random bytes, генерируется для local `.env` при bootstrap без вывода/commit. Production требует явно заданный secret. Не использовать hardcoded secret из `.env.example`.

Обязательные claims: `sub` (User UUID string), `iat` и `exp` (integer UTC NumericDate), `iss="event-registration"`, `aud="event-registration-api"`, `token_type="access"|"refresh"`. Access `exp=iat+900`, refresh `exp=iat+2592000`. Запрещены missing claims, невалидный UUID, неверные types, future iat, `exp <= iat`, неожиданный token_type, algorithm, issuer или audience; leeway=0. Clock участвует в issuance и temporal validation; cryptographic verification не отключается ради Fake Clock. Tokens не содержат password/hash/email.

Nginx: `limit_req_zone $binary_remote_addr zone=auth_login:10m rate=10r/m`; exact location `/api/auth/login`: `limit_req zone=auth_login burst=5 nodelay`, `limit_req_status 429`. Proxy отвечает общим envelope с code `AUTH_RATE_LIMITED` для limiter rejection и no-store. Нет доверия произвольному client X-Forwarded-For при определении IP.

## Files and interfaces

- Create: `backend/app/auth/tokens.py`, `dependencies.py`; `backend/tests/unit/test_tokens.py`, `test_login.py`; `backend/tests/integration/test_auth_session.py`.
- Modify: auth service/router/schemas; common config; `.env.example`; `infra/nginx/default.conf`; frontend app/client and generated schema.
- Create: `frontend/src/features/auth/login-page.tsx`, `session.ts`, `account-page.tsx`, соответствующие `.test.tsx`; `frontend/e2e/auth-session.spec.ts`, `frontend/e2e/login-rate-limit.spec.ts`.
- Consumes: Register User/repository/passwords/CSRF/errors/UserResponse, Foundation Clock/Settings/Session.
- Produces: `issue_tokens(user_id: UUID, clock: Clock, settings: Settings) -> TokenPair`; `verify_token(token: str, expected_type: Literal['access','refresh'], clock: Clock, settings: Settings) -> UUID`; `get_current_user(...) -> User` as FastAPI dependency.
- `TokenPair` содержит internal access/refresh strings; ни одна public response schema его не экспортирует.
- Frontend session query key `['auth','me']`; auth failures различаются по error.code; до refresh task AUTH_REQUIRED переводит на `/login` без recovery.

## Execution steps

- [x] 1. Создать новую branch/worktree от актуального master; baseline `make check`; создать task log перед product changes, сообщить failures.
- [x] 2. RED: token types/claims/signature/algorithm/issuer/audience и Clock boundaries (`exp-1 second`, `exp`); реализовать issuance/validation до GREEN.
- [x] 3. RED: HTTP login/me/logout contracts, normalized credentials, unknown User, cookie flags и точные deletion paths, повторный logout. Реализовать services/dependency/router; выполнить PostgreSQL integration tests.
- [x] 4. Настроить Nginx limiter; isolated burst из 20 login requests даёт хотя бы один 429 AUTH_RATE_LIMITED, csrf endpoint не лимитируется этой zone; не использовать sleep для token boundary tests. Проверить `nginx -t`.
- [x] 5. Regenerate API. RTL проверяет anonymous/loading/authenticated состояния, success navigation и logout cache reset. Реализовать UI; Playwright проверяет reload, cookies и полный flow через proxy.
- [x] 6. Выполнить `make check`, `make verify`; обновить log/README и secrets check; подготовить один PR в master.
