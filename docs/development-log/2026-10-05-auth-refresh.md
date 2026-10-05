# Auth Refresh

Started at: `2026-10-05T19:47:24+06:00`
Finished at: `2026-10-05T20:33:03+06:00`

## Initial prompt

Plan: `docs/superpowers/plans/2026-10-04-auth-refresh.md`

Execution prompt (JSON сохраняет завершающий пробел):
```json
"Выполни задачу [2026-10-04-auth-refresh.md](docs/superpowers/plans/2026-10-04-auth-refresh.md) "
```

## Timeline

- 2026-10-05T19:47:24+06:00 — обязательные документы прочитаны; Login/Logout PR #4 merged; новая branch `feat/auth-refresh` и worktree от master `a80d5163e0a1e4af18dcf13274136c19bbf40180`; baseline завершён.

- 2026-10-05T19:47:26+06:00 — unit RED: 7 failed, отсутствовал refresh use-case.
- 2026-10-05T19:50:02+06:00 — HTTP RED: 8 failed, 196 passed; отсутствовал endpoint.
- 2026-10-05T19:58:59+06:00 — client RED: 9 failed, 19 passed, 2 unhandled rejections от отсутствующей recovery.
- 2026-10-05T20:06:04+06:00 — backend GREEN: 204 passed; client GREEN: 28 passed. Добавлены проверки позднего concurrent 401, повторного выхода и очистки cache при terminal failure.

- 2026-10-05T20:10:13+06:00 — E2E воспроизвёл преждевременный redirect при logout; component RED с задержанным logout response: 1 failed, 9 passed. Выход показывает pending до server response.

- 2026-10-05T20:12:04+06:00 — первый полный `make verify`: exit 0, 205 backend / 32 frontend / 11 E2E, migration/build/API drift успешны.
- 2026-10-05T20:12:50+06:00 — дополнительный RED известной anonymous-сессии при SPA navigation: 1 failed, 10 passed; disabled query оставлял вечный loading.
- 2026-10-05T20:13:20+06:00 — anonymous state проверяется до loading; существующий logout test ждёт React heading, а не только изменение URL.

- 2026-10-05T20:15:17+06:00 — итоговый `make verify`: exit 0; 205 backend / 33 frontend / 11 E2E.

- 2026-10-05T20:27:29+06:00 — независимый fresh-context review: 3 Important, 0 Critical/Minor; fix pass RED: 6 failed / 33 passed → GREEN 39 passed. Дополнительно browser regression account switch.

- 2026-10-05T20:29:34+06:00 — итоговый gate после review: exit 0, 205 backend / 39 frontend / 12 E2E; все Important исправлены.

- 2026-10-05T20:33:03+06:00 — PR #5 создан в master; реализация и review-fix опубликованы, merge не выполнялся; worktree сохранён.

## Decisions and deviations

- Исходный refresh token/cookie/expiration не продлевается; cookies в JavaScript не читаются.
- Client generation предотвращает публикацию ответов старой сессии после logout. Logout ждёт settlement текущего refresh, затем отправляет server logout.
- SSE/EventSource, rotation/revocation/sliding lifetime остаются вне scope.
- Timestamps журнала получены из среды в user-facing timezone Asia/Bishkek.

- Review ruling: single-flight учитывает settlement ошибки, а не только successful renewal. Старые запросы получают тот же результат attempt; новые ручные запросы после failure могут начать recovery.
- Review ruling: login сериализуется после refresh/logout и блокирует recovery; logout также ждёт уже отправленный login. Это сохраняет cookie ownership при смене аккаунта.
- Stale-generation response теперь отменяет прежний Query с revert; не превращается в подтверждённый anonymous `null`, поэтому logout failure сохраняет account и retry.

### Решения по Declined to judge

- Cross-tab coordination не добавляется: plan задаёт Promise внутри клиента. Пользователь получает защиту порядка в одной вкладке; cost при неверном ожидании — межвкладочная гонка остаётся.
- Rotation/reuse detection/revocation не добавляются: явно stateless MVP; cost — украденный JWT действует до exp.
- SSE/EventSource reconnect остаётся Day 4: интерфейс refresh готов; cost — live reconnect ещё отсутствует.
- Timeout ожидания refresh при logout не вводится: plan требует settlement; cost — зависший transport задерживает logout, pending UI остаётся.
- Malformed/non-JSON errors и streaming bodies не перерабатываются: текущие auth interfaces JSON; cost — transport error остаётся generic, stream body retry не поддерживается.

## Issues discovered

Baseline failures отсутствуют.

Обнаружена гонка: rejected old-generation refresh завершал `/me` значением null и вызывал переход до server logout. Исправление сохраняет pending UI до завершения удаления cookies.
Тестовые pnpm команды требуют cwd `frontend`; запуск Corepack из root выбирает отсутствующую глобальную версию. Это ошибка команды, не приложения.

## Verification

### Baseline
Command: `make bootstrap`, затем `make check` с configured PNPM/Corepack/UV cache.
Exit code: `0` для обеих команд.
Result: backend unit `150 passed`; frontend `14 passed (14)`; Ruff/mypy/ESLint/TypeScript успешны; `OpenAPI drift: none.` Bootstrap не устанавливал браузер.

### TDD backend
Command: `uv run --frozen --project backend pytest backend/tests/unit/test_refresh.py backend/tests/unit/test_tokens.py -q`.
Exit code: `0`. Result: `40 passed in 0.72s` (RED только refresh: exit `1`, `7 failed in 0.71s`).

### HTTP / PostgreSQL
Command: `make test`.
RED: exit `2`, `8 failed, 196 passed in 14.93s` (route 404).
GREEN: exit `0`, `204 passed in 14.65s`, frontend `14 passed`.
`make api-generate`: exit `0`, contract regenerated.

### Client TDD
Command: `cd frontend && corepack pnpm test`.
RED: exit `1`, `9 failed | 19 passed`, `2 errors` (rejections без recovery).
GREEN: exit `0`, `28 passed (28)`.

### Итоговый полный gate
Command: `make verify` с configured PNPM/Corepack/UV cache и PLAYWRIGHT_BROWSERS_PATH.
Exit code: `0`.
Result: `157 passed in 2.66s` (quick unit); frontend `33 passed (33)`; полный backend `205 passed in 15.19s`; `OpenAPI drift: none.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`; production/frontend и Docker builds успешны; E2E `10 passed (11.6s)` + limiter `1 passed (1.5s)`; `verify: passed (isolated project foundation-verify-a4dc2de2a2a4).` Изолированные containers/volumes удалены.
Standalone `make e2e` первоначально exit `2`, `1 failed, 9 passed`: premature redirect; финальные browser scenarios повторно прошли в `make verify` после исправления.

### Дополнительные RED
Command: `cd frontend && corepack pnpm exec vitest run src/features/auth/account-page.test.tsx`.
Logout response ordering: exit `1`, `1 failed | 9 passed` → GREEN в полном gate.
Known anonymous SPA navigation: exit `1`, `1 failed | 10 passed` → GREEN в полном gate.

### Review fix pass
Command: `cd frontend && corepack pnpm test`.
RED (2026-10-05T20:23:05+06:00): exit `1`, `6 failed | 33 passed (39)`.
GREEN (2026-10-05T20:24:20+06:00): exit `0`, `39 passed (39)`.

### Финальная проверка после review
Command: `make verify` с configured PNPM/Corepack/UV cache и Chromium path.
Exit code: `0`.
Result: quick unit `157 passed in 2.93s`; frontend `39 passed (39)`; backend `205 passed in 18.76s`; `OpenAPI drift: none.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`; production и Docker builds успешны; browser `11 passed (11.0s)` + limiter `1 passed (2.1s)`; `verify: passed (isolated project foundation-verify-58692d7979c0).` Containers/volumes этой проверки удалены.
Secret scan перед первым commit: 17 staged files, local key/.env/private keys отсутствуют. Review-fix commit scan: 7 staged files, exit `0`, local key/.env/private keys отсутствуют. Документальный final commit проверяется отдельно.

## Result

Реализованы access-only refresh, cleanup invalid refresh, bounded single-flight recovery, session loss и logout ordering; Day 1 browser flow проверен.
Независимый read-only review выполнен; 3 Important исправлены одним TDD pass, Critical/Minor отсутствуют. Повторный review не запускался по executing-plans workflow.
Ограничения: stateless JWT без rotation/revocation/sliding lifetime; SSE reconnect остаётся Day 4. Day 1 завершается после merge.

## Pull Request

[PR #5](https://github.com/nbaishev/event-registration/pull/5) → `master`.

GitHub implementation commit: `b178db43176f2d2f2157f6d03bd158bdeef52d6d`; review fix: `b2f1d1f1231a201de437900683d8136206dc6a81`. Их Git trees совпадают с локальными commits `4ce253f` / `3602cca`; опубликованный verified implementation tree: `3e9dd31c0884a83e841f26e33594225beaec6338`. CI запущен; локальный full gate успешен. Финальный commit меняет только status/log, повторное выполнение тестов для этих документов не требовалось.

## PR correction: public requests

Resumed at: `2026-10-05T21:44:10+06:00`
Finished at: `2026-10-05T21:48:51+06:00`

### Corrective prompt

Исправь замечание `Allow anonymous requests to public API routes`. Не расширяй allowlist публичными URL. Убери предположение, что все `/api/*` требуют авторизации. Требование аутентификации должно задаваться явно для защищённых запросов/маршрутов. Публичные endpoints, включая `/api/health` и `/api/public/events/{slug}`, должны продолжать отправляться при `auth phase === anonymous`. Добавь regression tests для сценария failed refresh → anonymous → public event request succeeds, при этом защищённый request не должен выполняться без авторизации.

### Baseline / scope

PR #5 остаётся текущей задачей: branch `feat/auth-refresh`, worktree чистый, HEAD `0c38d6e`. Отдельная feature task не начинается.
Command: `cd frontend && corepack pnpm test`. Exit code: `0`. Result: `39 passed (39)`; existing failures отсутствуют.
Решение: `requiresAuth: true` задаётся явно вызывающим защищённым запросом. По умолчанию запрос публичный; auth phase / generation не ограничивают его transport. URL allowlist публичных endpoints не добавляется.
Существующие protected tests получают явный признак согласно уточнённому контракту; `/api/auth/me` caller обновляется. Backend/CSRF/JWT не меняются.

### RED
Timestamp: `2026-10-05T21:44:17+06:00`.
Command: `cd frontend && corepack pnpm test`. Exit code: `1`. Result: `5 failed | 39 passed (44)`.
Expected reason: URL-based auth guard блокировал public requests после terminal refresh, запускал recovery для public 401 и отклонял public response при logout generation change.

### GREEN / полный gate
Timestamp: `2026-10-05T21:47:34+06:00`.
Command: `make verify` с configured PNPM/Corepack/UV cache и Chromium path.
Exit code: `0`.
Result: quick unit `157 passed in 3.01s`; frontend `44 passed (44)`; backend `205 passed in 16.96s`; `OpenAPI drift: none.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`; frontend / Docker builds, Compose config и nginx config успешны; browser `11 passed (11.6s)` + limiter `1 passed (2.2s)`; `verify: passed (isolated project foundation-verify-96764b39422a).` Изолированные containers/volumes удалены.

### Результат correction

URL-based предположение о protected `/api/*` удалено полностью. Public calls по умолчанию используют transport без session guard / refresh / generation checks. Protected calls явно задают `requiresAuth: true`; metadata не передаётся в fetch. `/api/auth/me` caller и существующие protected tests обновлены.
Добавлены regressions failed refresh → anonymous → public event/health/new route succeeds, protected call blocked до fetch; public 401 не запускает recovery; public response завершается при logout. Public events backend не добавлялся: тестируется API client contract в рамках Auth Refresh.
Исправление подготовлено для обновления существующего [PR #5](https://github.com/nbaishev/event-registration/pull/5). Staged diff проверяется на secrets перед commit; master не меняется.

## Ссылки после нумерации планов

- Текущий файл плана: [04-2026-10-04-auth-refresh.md](../superpowers/plans/04-2026-10-04-auth-refresh.md); исходное имя `2026-10-04-auth-refresh.md` в prompt сохранено дословно.
