# Auth Refresh

Started at: `2026-10-05T19:47:24+06:00`
Finished at: `IN PROGRESS`

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

## Decisions and deviations

- Исходный refresh token/cookie/expiration не продлевается; cookies в JavaScript не читаются.
- Client generation предотвращает публикацию ответов старой сессии после logout. Logout ждёт settlement текущего refresh, затем отправляет server logout.
- SSE/EventSource, rotation/revocation/sliding lifetime остаются вне scope.
- Timestamps журнала получены из среды в user-facing timezone Asia/Bishkek.

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

## Result

Реализованы access-only refresh, cleanup invalid refresh, bounded single-flight recovery, session loss и logout ordering; Day 1 browser flow проверен.
Независимый review перед PR ещё выполняется.
Ограничения: stateless JWT без rotation/revocation/sliding lifetime; SSE reconnect остаётся Day 4. Day 1 завершается после merge.

## Pull Request

Not created yet.
