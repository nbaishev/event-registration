# Task 05 — Event Draft Creation

Started at: `2026-10-05T23:06:36+06:00`
Finished at: `2026-10-05T23:35:48+06:00`

## Initial prompt

Plan: [05-2026-10-05-event-draft-create.md](../superpowers/plans/05-2026-10-05-event-draft-create.md).

Execution prompt (JSON сохраняет завершающий пробел):

```json
"Приступай к выполнению задачи [05-2026-10-05-event-draft-create.md](docs/superpowers/plans/05-2026-10-05-event-draft-create.md) "
```

## Timeline

- 2026-10-05T23:06:36+06:00 — документы прочитаны; branch `feat/event-draft-create`, отдельный worktree от master `ece5102`; bootstrap и baseline прошли, log создан до product changes. Точное время начала setup не записано.

- 2026-10-05T23:20:32+06:00 — backend HTTP RED 28 failed/205 passed → GREEN 233 passed; frontend time RED 3 failed/1 passed, UI RED 8 failed → GREEN 12 passed. API types regenerated; общий gate и E2E готовятся.

- 2026-10-05T23:30:15+06:00 — whole-branch review: owner cache isolation и UTC overflow подтверждены regression RED; исправлены. Повторный final make verify запущен.

- 2026-10-05T23:35:48+06:00 — final `make verify` exit 0; implementation и review corrections завершены, screenshots просмотрены; подготовка feature commit.

## Decisions and deviations

- Contract: CreateEventRequest принимает title/description, starts_at/ends_at, timezone, capacity; extra fields запрещены. EventResponse включает все Event поля из spec; EventSummary включает id/title/slug/starts_at/ends_at/timezone/capacity/status. Validation errors используют существующий безопасный envelope без submitted input.
- UI local-time conversion — отдельный pure helper на Intl.DateTimeFormat, покрытый DST gap/fold tests; дополнительных dependencies нет. Business temporal decisions остаются в backend service через Clock.
- Slug collision повторяется под PostgreSQL savepoint до 5 attempts; исчерпание возвращает безопасный 503, не переписывая существующую запись.
- Existing User migration test проверяет текущий head, а не только revision 0001. Его список таблиц/head необходимо расширить для утверждённой Event migration; assertions User columns/constraints сохраняются.

## Issues discovered

Baseline failures отсутствуют.

Review выявило общий Event query cache для нескольких аккаунтов: owner ID добавлен в ключи списка/деталей и seeded cache после create. Tests проходят через login другого аккаунта в одном QueryClient с задержанным request и ошибкой. UTC normalization overflow преобразован в validation error. Замечание о NUL text и capacity вне PostgreSQL int32 повышено с Minor до Important: invalid input должен возвращать 422, а не database 503. Они отклоняются до persistence; это физические ограничения выбранного хранения, дополнительной архитектуры нет.

Первый make verify — exit 2: backend/check/migrations прошли, E2E 11 passed/1 failed; Playwright exact label не находил required MUI datetime label. Использован label regexp; второй browser context явно получает baseURL. Setup использует существующие tooling/cache в /tmp; .env не выводится и не коммитится.

## Verification

### Baseline

Command: `make bootstrap`, затем `make check` с PNPM/Corepack/UV cache в /tmp.
Exit code: `0` для обеих команд.
Result: backend unit `157 passed in 4.87s`; frontend `44 passed (44)`; Ruff, mypy, ESLint, TypeScript успешны; `OpenAPI drift: none.` Браузер bootstrap не устанавливал.

## Result

Реализованы Event model/migration 0002, authenticated create/mine/owner detail API, generated contracts, organizer create/list/detail UI с timezone/DST conversion, validation и plain-text rendering. Review findings исправлены с regression RED→GREEN. README, plan и screenshots обновлены.

Known limitations: PATCH, publish/public page, delete/cancel, Registration/SSE/email не входят в задачу. Vite предупреждает о production bundle больше 500 kB (518.18 kB); build успешен, splitting не входит в Task 05. Capacity ограничена физическим PostgreSQL int32; NUL text и UTC overflow — 422.

Integration: локальные commits `0f5de85`, `acd8904`; worktree `.worktrees/event-draft-create`; base master `ece5102`. Опубликованная GitHub ветка `feat/event-draft-create` содержит итоговое состояние файлов, созданное connector commit `37d9cb71326b74b651674581d484e7b9d150ee08` поверх удалённого `master` `2d83323818daccd6e128725c023816161c7633e5` (локальные commit objects через shell не отправились из-за отсутствия git credentials). PR #6 открыт; details ниже.

## Pull Request

PR #6: https://github.com/nbaishev/event-registration/pull/6 — open, base `master`, head `feat/event-draft-create`; mergeable при последней проверке.

## TDD evidence

Command: `make test` (isolated PostgreSQL).
RED exit code: `2` (pytest exit `1`). Result: `28 failed, 205 passed in 24.96s`; Event routes возвращали 404.
Backend GREEN: `233 passed in 27.79s`; общий make test в этот момент exit `2`, потому что frontend находился на отдельном RED этапе. Это не финальный успешный gate.

Command: `pnpm exec vitest run src/features/events/event-time.test.ts`.
RED exit code: `1`. Result: `3 failed | 1 passed (4)`; minimal exports ещё выбрасывали Not implemented. Предыдущий collection failure от отсутствующего module не считается assertion RED.

Command: `pnpm exec vitest run src/features/events/event-pages.test.tsx`.
RED exit code: `1`. Result: `8 failed (8)`; organizer routes отсутствовали.

Command: `pnpm exec vitest run src/features/events`.
GREEN exit code: `0`. Result: `12 passed (12)`.

### Review corrections RED → GREEN

Command: `pnpm exec vitest run src/features/events/event-pages.test.tsx`.
RED exit code: `1`; result: `2 failed | 8 passed (10)` — list и detail раскрывали cached Event другого owner при pending запросе.
Command: `make test`.
RED exit code: `2` (pytest `1`); result: `5 failed, 233 passed in 29.86s` — UTC overflow, PostgreSQL int32 overflow и NUL text.
Command: `pnpm exec vitest run src/features/events`.
GREEN exit code: `0`; result: `14 passed (14)`.

### Interim make check

Command: `make check` с согласованным PNPM и UV cache.
Exit code: `0`.
Result: backend unit `157 passed`; frontend `56 passed (56)`; Ruff, mypy, ESLint и TypeScript успешны; `OpenAPI drift: none.` До review fixes; финальный gate фиксируется отдельно.

### E2E isolation correction

Второй `make verify` — exit `2`: backend `238 passed in 27.22s`, frontend `58 passed (58)`, migrations/build прошли; browser `11 passed (19.9s)`, один Event test failed на втором owner login с UI `Слишком много попыток`. Create/reload/mine уже прошли.
Причина — общий Nginx rate zone после auth suite. Verification harness разделяет auth/Event/limiter группы и сбрасывает rate zone перезапуском только уникального test-project Nginx. Production config и ограничения не меняются; sleeps/retries и обход auth не используются. Это необходимая адаптация verification к добавленному сценарию двух owner.

### Final quality gate

Command: `UV_CACHE_DIR=/tmp/event-registration-uv-cache COREPACK_HOME=/tmp/event-registration-corepack PLAYWRIGHT_BROWSERS_PATH=/tmp/event-registration-playwright make verify PNPM='/tmp/event-registration-tools/node_modules/.bin/corepack pnpm'`.
Exit code: `0`.
Result: `238 passed in 28.72s` backend unit/integration на PostgreSQL; frontend `58 passed (58)`; `OpenAPI drift: none.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.` Production frontend/Docker builds и Nginx syntax прошли. Browser: auth/foundation/register 11 passed; Event draft 1 passed; login limiter 1 passed. `verify: passed (isolated project foundation-verify-b7bf610e65e7).` Тестовый Compose project/volumes удалены штатно.
В составе `make verify` успешно выполнен `make check`: Ruff, formatting, mypy, backend unit, ESLint, TypeScript, Vitest, OpenAPI drift.

Screenshots: `docs/screenshots/event-create.png`, `docs/screenshots/event-detail.png` — реальные Playwright captures, визуально просмотрены, credentials отсутствуют.

### Integration and Pull Request

Первый `git push -u origin feat/event-draft-create` до разрешения пользователя был отклонён sandbox auto-review: ownership/trust destination не подтверждены, отсутствовало явное разрешение на публикацию. Пользователь разрешил публикацию. Повторный shell push завершился ошибкой credentials: `could not read Username for 'https://github.com': No such device or address`.

Проверена GitHub repository permission: `admin/maintain/push: true`; удалённый master: `2d83323818daccd6e128725c023816161c7633e5`. По явному разрешению пользователя подключённым GitHub integration создана ветка `feat/event-draft-create` с commit `37d9cb71326b74b651674581d484e7b9d150ee08`, содержащим итоговый snapshot файлов относительно remote master. PR #6 открыт в `master`: https://github.com/nbaishev/event-registration/pull/6. Проверка PR metadata: `open`, `mergeable: true`, `merged: false`.
