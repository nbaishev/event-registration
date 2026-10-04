# Auth Login / Logout

Started at: `2026-10-04T22:53:32+05:00`
Finished at: `IN PROGRESS`

## Initial prompt

Plan: `docs/superpowers/plans/2026-10-04-auth-login-logout.md`

Execution prompt (JSON сохраняет завершающий пробел):
```json
"Выполни задачу [2026-10-04-auth-login-logout.md](docs/superpowers/plans/2026-10-04-auth-login-logout.md) "
```

## Timeline

- 2026-10-04T22:53:32+05:00 — обязательные документы прочитаны; новая ветка `feat/auth-login-logout` от master `8664ffebbb9b68957f9b2b6e04337ff34af0ec96`, отдельный worktree; baseline завершён.

## Decisions and deviations

- Общий контракт Register используется без изменений; refresh endpoint не входит в задачу.
- Plan содержит один PR с шестью execution steps; progress ledger отслеживает эти шаги.

## Issues discovered

Baseline failures отсутствуют.

## Verification

### Baseline
Command: `make bootstrap`, затем `make check` (PNPM/Corepack и UV cache настроены для среды).
Exit code: `0` для обеих команд.
Result: `100 passed in 2.93s`; frontend `Tests 6 passed (6)`; Ruff/mypy/ESLint/TypeScript успешны; `OpenAPI drift: none.` Браузер при bootstrap не устанавливался.

## Result

Реализованы login/me/logout, typed HS256 JWT с Clock, exact cookie paths/flags/deletion,
local bootstrap secret и production startup validation, session UI/query cache cleanup,
Nginx limiter, generated API и screenshots.

Известные ограничения: refresh endpoint/recovery и HTTPS deployment вне scope;
logout удаляет browser cookies, stateless JWT не отзывается сервером.
Финальный whole-branch review ожидается.

## Pull Request

Not created yet.

## TDD и промежуточные проверки

- 2026-10-04T22:54:31+05:00 — RED `pytest test_tokens.py test_config.py`: exit 1, `5 failed, 18 passed, 33 errors` (token module отсутствовал; отдельный assertion подтвердил отсутствие). Негативные JWT fixtures далее подписаны независимо через HMAC: PyJWT.encode сам запрещает нестроковый issuer.
- 2026-10-04T22:57:37+05:00 — RED `make test`: exit 2, backend `21 failed, 154 passed in 10.08s`; новые login HTTP requests возвращали 404 вместо ожидаемых statuses. Один fixture JWT ещё требовал исправления выше.
- RED bootstrap: exit 1, `3 failed in 0.07s` — секрет не генерировался, production constraint отсутствовал.
- Первый GREEN run выявил два случая: Starlette delete_cookie использует текущий Expires при expires=0; установлена явная прошедшая дата 1970. Production bootstrap fixture учитывает ENVIRONMENT из окружения test runner, теперь явно задаёт production.
- Existing CSRF production fixture переведён на HTTPS согласно новому утверждённому startup requirement. Original bootstrap test сохранения конфигурации расширен: старые значения сохраняются, отсутствующий JWT_SECRET добавляется согласно plan.

- 2026-10-04T23:13:01+05:00 — backend GREEN `make test`: exit 0, `176 passed in 10.54s`, frontend `6 passed`; после него добавлены отдельные unit service tests и UI field/network tests.
- Frontend RED: `pnpm test`, exit 1, `8 failed | 4 passed (12)`. Первый GREEN attempt показал race cache-clear; исправлен порядок navigation/cache clear. Async assertion anonymous navigation ожидает DOM commit, а не только URL.
- Limiter RED: `make e2e`, exit 2; основной suite `7 passed (5.2s)`, отдельный probe получил `20` 401 вместо ожидаемых `6`.
- 2026-10-04T23:13:01+05:00 — `make e2e` exit 0: `7 passed (6.1s)` + `1 passed (3.1s)`; `nginx -t`: `syntax is ok`, `test is successful`. Isolated project удалён вместе с volumes.
- В verification runner limiter выделен в отдельный непересекающийся Playwright запуск после restart Nginx этого уникального test project. Это сбрасывает zone; development stack не затрагивается.
- Mypy: без config exit 1, missing jwt_secret argument; `mypy --config-file backend/pyproject.toml backend/app scripts` exit 0, `Success: no issues found in 27 source files`. Makefile теперь явно использует уже существующий config/plugin; динамическая загрузка обязательного JWT_SECRET из окружения сохраняет runtime validation.

- 2026-10-04T23:13:16+05:00 — первый финальный `make verify` exit 2: unit `143 passed in 2.87s`, frontend `1 failed | 13 passed (14)`. Cache clear test воспроизвёл race несмотря на flushSync: trace показал повторный observer/refetch во время асинхронной BrowserRouter navigation. Решение: отключать session query на весь logout; после success не включать до unmount, при error вернуть retry. FlushSync удалён.
- 2026-10-04T23:16:11+05:00 — диагностика выполнена через lifecycle events без user/token данных; временный trace удалён. Повторный полный gate запущен.

## Финальный quality gate перед review

Timestamp: `2026-10-04T23:18:50+05:00`
Command: `make verify PNPM='/tmp/event-registration-tools/node_modules/.bin/corepack pnpm'`
Environment: COREPACK_HOME, UV_CACHE_DIR, PLAYWRIGHT_BROWSERS_PATH указывают на task tooling/cache в `/tmp`.
Exit code: `0`.
Result:
- `make check`: Ruff check/format, mypy (`27 source files`), unit `143 passed in 2.96s`, frontend `14 passed (14)`, `OpenAPI drift: none.`
- Полный backend: `179 passed in 12.31s`; frontend повторно `14 passed (14)`.
- `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`
- Frontend production build и оба Docker images собраны.
- Compose config и `nginx -t` успешны.
- Playwright основной suite и отдельный limiter probe прошли (7+1 tests).
- `verify: passed (isolated project foundation-verify-00e05c06ba4f).`; cleanup завершён.

2026-10-04T23:18:50+05:00 — реализация прошла полный gate, подготовка commit и независимого review.
