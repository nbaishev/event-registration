# Auth Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Status:** Approved by user on 2026-10-04; implementation verified on 2026-10-05, final review / PR in progress.

**Goal:** Expired access восстанавливается через valid refresh; terminal refresh failure возвращает пользователя на login без циклов и восстановления после logout.

**Architecture:** Stateless refresh use-case проверяет refresh JWT и существование User, выдаёт новый access cookie. Frontend координирует одну refresh attempt и повторяет запрос максимум один раз.

**Tech Stack:** Auth Login/Logout stack; same-origin typed API client и TanStack Query.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 24–25, 29, 32, 34, 37; [ADR-003](../../adr/003-authentication-security-model.md).

## Global Constraints

- Refresh JWT: 30 days, HttpOnly, server-side не хранится.
- Invalid/expired refresh: 401 AUTH_REFRESH_INVALID.
- Refresh защищён CSRF + exact Origin; JWT не хранится browser JavaScript.
- Clock без sleep для boundaries; gates согласно [engineering.md](../../agent-rules/engineering.md).
- SSE reconnect остаётся Day 4; API recovery interface должен быть пригоден для будущего stream consumer.

## Task / PR boundary

**Task:** Auth Refresh.

**Dependencies:** Login/Logout PR merged в master.

**Branch:** Новая `feat/auth-refresh` и отдельный worktree от обновлённого master.

**Scope:** Refresh endpoint, access renewal, API client recovery/single-flight, bounded retry, session loss и refresh/logout race handling; итоговый Day 1 E2E.

**Out of scope:** RefreshSession, rotation/reuse detection/revocation; sliding refresh lifetime; SSE/EventSource implementation.

**Acceptance criteria:**

- POST refresh success → 200 UserResponse, новый access cookie на 900 seconds; исходный refresh token/expiration не продлевается и cookie не переустанавливается.
- Missing/tampered/expired/wrong-type refresh, missing User → 401 AUTH_REFRESH_INVALID.
- Refresh valid до exp, при now==exp invalid; timestamp checks используют Clock.
- CSRF/Origin failure → 403 CSRF_INVALID без renewal.
- API client выполняет refresh только на 401 AUTH_REQUIRED защищённого запроса, исключая login/register/refresh/logout.
- Параллельные failures используют один refresh Promise; каждый исходный запрос повторяется максимум один раз.
- Refresh 401 очищает local auth state и переводит на `/login`; network/403/5xx не маскируются как success и не создают повторный refresh loop.
- Logout блокирует новую recovery, ждёт уже начатую refresh attempt, затем отправляет logout; ответ старой attempt не возвращает authenticated UI. Cookies, установленные in-flight refresh, очищаются последующим logout response.
- Итоговый Day 1 flow register → `/login` → login → `/me` → refresh → logout проходит через Compose/Nginx.

**Test strategy:** TDD JWT/service boundaries; HTTP+PostgreSQL integration; component tests с controllable promises для concurrency/logout; Playwright success/terminal failure через proxy.

**Verification:** `make test`, `make api-generate`, `make check`, `make e2e`, `make verify`; Compose smoke Day 1. Browser expired-access scenario использует server-side Fixed Clock в isolated test app (dependency override при запуске test process, не public test endpoint) или заранее expired signed access cookie из fixture; production TTL не меняется.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md), плюс acceptance criteria и полный Day 1 browser scenario.

## Review Focus

- Access JWT нельзя использовать вместо refresh.
- Refresh не продлевает 30-day lifetime.
- Одновременные 401 не создают refresh storm.
- Повторный 401 после recovery не вызывает loop.
- In-flight refresh не отменяет результат logout.

## API contract (owned by this task)

- `POST /api/auth/refresh`: без body; 200 UserResponse; 401 AUTH_REFRESH_INVALID; 403 CSRF_INVALID; no-store.
- UserResponse и CSRF — [Register contract](2026-10-04-auth-register.md#api-contract-owned-by-this-task).
- Cookie/claims/algorithm — [Login/Logout contract](2026-10-04-auth-login-logout.md#auth-contract-owned-by-this-task).
- Success устанавливает только `access_token` с исходными attributes. Refresh cookie остаётся с первоначальным сроком. 401 удаляет обе auth cookies с их исходными paths; stateless JWT централизованно не отзывается.
- Невалидная access cookie не препятствует valid refresh; refresh use-case не зависит от access auth dependency.

## Files and interfaces

- Modify: `backend/app/auth/service.py`, `router.py`, `tokens.py`, generated `frontend/src/api/schema.d.ts`, `frontend/src/api/client.ts`, `frontend/src/features/auth/session.ts`.
- Create: `backend/tests/unit/test_refresh.py`, `backend/tests/integration/test_refresh_api.py`, `frontend/src/api/client.test.ts`, `frontend/e2e/auth-refresh.spec.ts`.
- Consumes: UserResponse, verify_token(expected_type='refresh'), Clock/Settings/Session, Login/Logout cookie helpers.
- Produces: `refresh_access(session: Session, refresh_token: str, clock: Clock, settings: Settings) -> tuple[User, str]` (User и internal access JWT).
- Frontend `refreshSession(): Promise<UserResponse>` координирует single-flight, CSRF request и auth generation. `logoutSession(): Promise<void>` блокирует recovery, invalidates prior generation, ждёт settlement текущего refresh и выполняет logout без automatic recovery. Уже начатые запросы старой generation не публикуют session state.
- API client retry сохраняет method/body/header contract; unsafe запрос повторяется только после AUTH_REQUIRED, который backend выдаёт до business mutation. Не повторять запрос при network uncertainty или произвольном 401.

## Execution steps

- [x] 1. Новая branch/worktree от актуального master; baseline `make check`; task log перед implementation, существующие failures сообщить.
- [x] 2. RED: valid/missing/tampered/expired/wrong-type token, missing User и boundary exp; реализовать refresh use-case до GREEN.
- [x] 3. HTTP integration: success 200 UserResponse + access Set-Cookie без refresh renewal; 401 cleanup; csrf/origin 403; expired access не блокирует refresh. Реализовать endpoint и regenerate API.
- [x] 4. RED client tests с controllable promises: несколько AUTH_REQUIRED → одна refresh attempt; retry один раз; refresh 401 → login; 403/5xx/network не создают loop; in-flight refresh → logout → cookies cleared и UI anonymous. Реализовать recovery и session generation.
- [x] 5. Playwright проходит реальный expired-access recovery и terminal expired-refresh flow через Nginx, без sleep для temporal boundaries; проверить итоговый Day 1 сценарий.
- [ ] 6. `make check`, `make verify`, README/log/secret review; один PR в master. Day 1 считается выполненным после merge и успешного полного gate.
