# CI E2E — изоляция login limiter

Started at: `2026-10-07T22:40:50+06:00`
Finished at: `2026-10-07T22:18:03+05:00`

## Initial prompt

Исправь нестабильный CI E2E.

Падает:

`e2e/auth-session.spec.ts`\
`register login reload logout through the same origin proxy`

Ошибка:\
`Expected 200, Received 429` при `POST /login`.

Похоже, предыдущие E2E auth-тесты исчерпывают login rate limit, и состояние limiter сохраняется между тестами.

Задача:

1. Воспроизведи падение именно в том порядке, в котором тесты запускаются в CI.
2. Найди, почему rate limiter протекает между независимыми E2E-тестами.
3. Обеспечь изоляцию тестов: каждый тест/набор не должен получать `429` из-за запросов предыдущих тестов.
4. Не отключай rate limiting в production и не ослабляй сам тест `login limiter`.
5. Не исправляй проблему простым увеличением лимита или retry/sleep.
6. Если нужен специальный test-mode/reset для limiter — реализуй минимально и безопасно только для тестового окружения.
7. Проверь, что тесты rate limiting по-прежнему действительно проверяют `429`.

После исправления запусти:

`corepack pnpm e2e --grep-invert 'login limiter|event-drafts|event-publish|event-registration|my-registrations'`

а затем полный `make verify`.

В конце кратко опиши:

- почему возникал `429`;
- почему ошибка проявлялась только в CI;
- что изменено для изоляции тестов;
- какие проверки прошли.

## Timeline

- 2026-10-07T22:40:50+06:00 — worktree `fix/e2e-login-rate-isolation` от local/remote master `dac35cf`; baseline и точный CI test order проверяются.

- 2026-10-07T22:48:55+06:00 — deterministic limiter RED→GREEN; реализован safe per-test restart.
- 2026-10-07T22:51:06+06:00 — requested auth group/make check/safety smoke GREEN; original CI rerun ещё выполняется.

## Decisions

Контракт пользователя фиксируется в `docs/superpowers/plans/2026-10-07-e2e-login-rate-isolation.md`. Production Nginx limiter сохраняется. Reset — полный restart только nginx уникального test Compose project, без нового endpoint.

## Verification

В работе.


### Baseline

Command: `UV_CACHE_DIR=/tmp/task12-uv-cache make check`
Exit code: `0`
Result: `207 passed in 5.24s`; Vitest `120 passed (120)`; `OpenAPI drift: none.`

Command: `UV_CACHE_DIR=/tmp/task12-uv-cache make e2e`
Exit code: `0`
Result: auth group в точном CI порядке — `12 passed (20.0s)`. Локальный первый auth-refresh test `4.2s`, следующие `1.2s/1.4s/1.6s/2.1s`; bucket успевает восстановить слот. Остальные existing E2E также прошли.

### CI evidence

GitHub run `37650305760`, job `112891601932`, PR #14 head `86739254b09e60eef55769cfcee669fc77eb8564`.
Порядок совпадает с локальным --list: auth-refresh five tests → auth-session.
Actual CI durations: `1.1s`, `839ms`, `904ms`, `1.3s`, `1.4s`; auth-session `602ms`, `Expected: 200 / Received: 429`, `1 failed, 11 passed (11.3s)`.
Причина: zone `auth_login`, key `$binary_remote_addr`, `10r/m`, `burst=5 nodelay`; шесть запросов внутри auth-refresh + седьмой auth-session. Shared state Nginx не относится к browser context. CI быстрее и не даёт bucket восстановить один слот; старый runner перезапускал Nginx между крупными группами, но не внутри auth group.

### RED — limiter state leak

Command: `corepack pnpm e2e --grep 'login limiter'` (isolated stack, CI=true, workers=1)
Exit code: `1`
Result: `1 failed, 1 passed (2.0s)`. Исходный rate test сохранил `6 × 401 / 14 × 429`; следующий независимый test получил `Expected: 401 / Received: 429`.
Дополнительные два локальных повтора точного CI auth order прошли (`12 passed (13.9s)` и `12 passed (12.4s)`). Совпадающий исходный auth-session failure подтверждён actual CI job выше; локально более медленный UI даёт bucket время восстановиться. Deterministic RED доказывает общий Nginx state независимо от скорости UI.

### Implementation

Shared auto Playwright fixture: ENVIRONMENT=test + явный 64-hex container ID + unique verification project/service/test Compose labels + workers=1. Перед каждым test полный restart только этого nginx; poll только `/api/ready`, login не повторяется и не ожидает bucket decay. Все E2E используют fixture; runner передаёт container ID и сохраняет первую CI auth группу, redundant group restarts удалены. Production Nginx rate/burst/config не менялись.

### GREEN targeted

Command: `corepack pnpm e2e --grep 'login limiter'`
Exit code: `0`
Result: `2 passed (6.6s)`; исходный strict probe сохраняет `6 × 401 / 14 × 429`, новый independent test получает `401`.

Command: `corepack pnpm e2e --grep-invert 'login limiter|event-drafts|event-publish|event-registration|my-registrations'`
Exit code: `0`
Result: `12 passed (39.2s)` на изолированном stack с новым fixture, точный CI auth order сохранён.

Command: `UV_CACHE_DIR=/tmp/task12-uv-cache make check`
Exit code: `0`
Result: backend unit/Ruff/mypy; ESLint/typecheck; Vitest `120 passed (120)`; `OpenAPI drift: none.`
ESLint initially detected required Playwright empty dependency destructuring (`no-empty-pattern`); narrow documented lint suppression added. Production code unchanged.

Original CI failed job rerun requested through GitHub to reproduce the old code on CI itself (not a test retry workaround).

### Safety smoke

Command: targeted Playwright API-health invocation with ENVIRONMENT=production; then ENVIRONMENT=test with backend container ID.
Driver exit code: `0` (оба negative invocations expected exit `1`).
Result: `production-mode: rejected before restart, container StartedAt unchanged`; `non-nginx-target: rejected before restart, container StartedAt unchanged`.

## Result

Исправление проверено полным make verify в CI и включено в PR #14. Production limiter сохранён; test isolation работает только на выделенном test Nginx. Ограничение: workers=1, как в текущем CI.

### Original CI reproduction

Run: `37650305760`, повторный job `112908124281`, original PR #14 code без исправления.
Exit/conclusion: `failure`.
Result: auth-refresh durations `1.1s`, `869ms`, `911ms`, `1.3s`, `1.3s`; затем original auth-session `674ms`, `Expected: 200 / Received: 429`; `1 failed, 11 passed (10.9s)`.
Исходное падение воспроизведено в реальной CI среде и точном исходном порядке, без изменения production limiter или добавления retries в тесты.

### Independent review

Reviewer: `gpt-6-astra`, diff `dac35cf..fcc9c4e`.
Result: Critical/Important/Minor — нет. Parallel workers намеренно не поддерживаются (guard workers=1); финальные make verify/CI results ожидаются отдельно.

### Final verify — infrastructure failure

Command: `UV_CACHE_DIR=/tmp/task12-uv-cache make verify`
Exit code: `2`
Result: unit/frontend/integration suites, migrations and frontend production build passed; Docker backend build failed resolving unchanged `ghcr.io/astral-sh/uv:0.12.5` metadata.
Actual reason: Docker Desktop `connectex` timeout to `ghcr.io:443`, direct connection without HTTPS proxy. No E2E failure in this invocation: browser step had not started. Registry connectivity checked separately before retrying full gate; no production/rate-limit changes for this infrastructure failure.

### Final CI verification

Command: `make verify`
Run: https://github.com/nbaishev/event-registration/actions/runs/37657279549
Verified code commit: `ee703db9af950f95f194eccf560122305c0c81ba`.
Exit/conclusion: `0 / success`.
Result: 421 backend, 128 frontend, migrations/drift, production/Docker builds, Nginx/same-origin checks; requested exact grep-invert group `12 passed (17.5s)` followed by remaining group `7 passed (19.1s)` (19 total). Original auth-session passed in the original CI order. Both limiter tests passed, preserving strict 6×401/14×429 assertions. Task 12 deletion scenario preserved.
Local full verify remains blocked by Docker Desktop registry timeout; successful full CI gate ran the combined Task 12 + limiter fix tree.
Final documentation-only update does not change the verified implementation. Staged diff checked for secrets; no credentials added.
