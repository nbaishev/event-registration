# Auth refresh E2E — registration navigation race

Started at: `2026-10-06T21:50:20+06:00`
Finished at: `IN PROGRESS`

## Initial prompt

Plan: `docs/superpowers/plans/04-2026-10-04-auth-refresh.md`; текущая bugfix scope утверждена запросом ниже.

Исправь падающий E2E-тест:
`e2e/auth-refresh.spec.ts`\
`old refresh cannot overwrite cookies after login as another account`
Сейчас после регистрации второго аккаунта тест ожидает `/login`, но остаётся на `/register` и падает по timeout.
Найди первопричину, почему регистрация не завершается в этом сценарии: проверь response `/api/auth/register`, CSRF, cookies и влияние параллельного refresh.
Исправь именно причину, не ослабляй assertions и не увеличивай timeout без необходимости.
Сначала воспроизведи только этот тест, затем после исправления запусти весь E2E-набор:
`corepack pnpm e2e --grep-invert 'login limiter|event-drafts'`
Кратко сообщи, в чём была причина и что изменено.

## Timeline

- 2026-10-06T21:50:20+06:00 — исходный targeted baseline воспроизвёл failure на второй попытке; журнал создан перед diagnostic test changes. Branch fix/auth-refresh-e2e, worktree .worktrees/auth-refresh-e2e, base 1e37b2c. Подготовка началась раньше; Exact timestamp not recorded.

## Verification

Command: `corepack pnpm e2e e2e/auth-refresh.spec.ts --grep 'old refresh cannot overwrite cookies after login as another account'` (isolated Compose; Nginx rate budget reset между попытками).
Exit code: `1` (вторая попытка).
Result: attempt1 `1 passed (5.3s)`; attempt2 `1 failed`, URL остаётся /register, snapshot Email пуст и INVALID_EMAIL. Другие tests не запускались.

## Decisions and deviations

Scope: только первопричина targeted Auth E2E, сохраняются security/race assertions и исходные timeouts. Временная диагностика не пишет passwords/token/cookie values и будет удалена после исследования.

## Result

Первопричина: SPA URL изменялся до отображения Register. Playwright находил общий Email label на старой Login форме; focus попадал в input, который затем удалялся при смене страницы. Fill завершался без input event на Register, запрос отправлял email="" и получал422 INVALID_EMAIL. CSRF, Origin и cookies были корректны; refresh ещё не был запущен.

Изменены только 7 строк setup существующего E2E: unique destination heading wait, Email value assertion, register201/response email assertion. Security/concurrency assertions и timeouts не ослаблены; retries/sleep не добавлены. Временные listeners удалены, application код не менялся.

Known limitations: новых нет. Полученные diagnostic artifacts содержат только безопасные признаки без credential values.


## Pull Request

Not created yet.

## Diagnosis evidence

Первый diagnostic run (input/submit): targeted attempt2 failed. Отдельный focus-tracing run: targeted attempt4 failed. Второй register отправил email=""; response422 VALIDATION_ERROR / INVALID_EMAIL. CSRF match=true, Origin match=true; access cookie присутствовала, refresh cookie Path=/api/auth/refresh и HttpOnly, CSRF Path=/. Ни одного refresh request до failure. DOM не получил второй email input event, несмотря на завершившийся fill; submit уже в Register с пустым Email. Исследуется момент focus/navigation, не backend/auth mutation.

- 2026-10-06T21:54:41+06:00 — root cause подтверждена focus tracing: перед second-email fill pathname=/register, heading=Войти, focusin emailEmpty=true; input event отсутствовал, после mount Register submit emailEmpty=true. Response422/INVALID_EMAIL, CSRF/Origin корректны, refresh requests отсутствовали.
- Исправление: unique Register heading assertion до fill; проверка сохранённого Email и register201/response email. Временная instrumentation удалена. Исходные auth race assertions и timeouts сохраняются; business/Auth код не меняется.

- 2026-10-06T21:57:40+06:00 — corrected target10/10 passed, затем exact requested E2E command passed (11 tests). make check exit0: unit157, frontend65, OpenAPI drift none. Reviewer: no Critical/Important; замечание об attempt numbering исправлено (два отдельных diagnostic runs).

Command: `corepack pnpm e2e e2e/auth-refresh.spec.ts --grep 'old refresh cannot overwrite cookies after login as another account'`
Exit code: `0` для всех десяти последовательных запусков.
Result: `10/10` targeted tests passed; assertions/token serialization scenario сохранены. Test rate budget reset только в уникальном isolated Nginx между запусками; retries в committed test не добавлены.

Command: `corepack pnpm e2e --grep-invert 'login limiter|event-drafts'`
Exit code: `0`
Result: `11 passed (10.1s)`.

Command: `make check`
Exit code: `0`
Result: backend `157 passed in 5.90s`, frontend `65 passed (65)`, lint/typecheck/mypy passed, OpenAPI drift none.

## Final verification — 2026-10-06T22:00:35+06:00

Command: `UV_CACHE_DIR=/tmp/uv-cache-auth-refresh-e2e make verify`
Exit code: `0`
Result: backend `273 passed in 38.58s`, frontend `65 passed (65)`; migrations/schema drift, frontend/Docker builds, nginx passed. Auth/smoke, event draft и login limiter browser groups passed; полный набор13 tests. Изолированные ресурсы удалены.

- 2026-10-06T22:00:35+06:00 — final gate passed; подготовка PR. Review no Critical/Important; единственное замечание к номеру diagnostic attempt исправлено. Diff secrets scan перед commit/PR; .env не добавляется.
