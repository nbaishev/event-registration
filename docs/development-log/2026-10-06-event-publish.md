# Task 07 — Event Publishing + Public Page

Started at: `2026-10-06T21:07:08+06:00`
Finished at: `2026-10-06T21:29:47+06:00`

## Initial prompt

Plan: `docs/superpowers/plans/07-2026-10-05-event-publish.md`

Выполни задачу [07-2026-10-05-event-publish.md](docs/superpowers/plans/07-2026-10-05-event-publish.md)

## Timeline

- 2026-10-06T21:07:08+06:00 — baseline завершён, журнал создан перед реализацией. Branch `feat/event-publish`, worktree `.worktrees/event-publish`, base `1e37b2c`; Task 06 merged (PR #7). Точное время начала подготовительных чтений не записано.
- 2026-10-06T21:12:06+06:00 — backend/frontend GREEN: make test exit 0, `282 passed in 42.94s`, frontend `72 passed (72)`. Добавлены дополнительные boundary/row-lock/transport проверки и Day 2 browser scenario.
- 2026-10-06T21:16:14+06:00 — расширенные tests GREEN: backend `286 passed in 45.49s`, frontend `75 passed (75)`. Empty PostgreSQL upgrade/revision/metadata drift passed; production build passed. Полный make verify ещё выполняет Compose/E2E. Начато итоговое branch review.
- 2026-10-06T21:18:02+06:00 — make verify exit 2: существующий Auth browser test `old refresh cannot overwrite cookies after login as another account` остановился на регистрации второго аккаунта (auth-refresh.spec.ts:117). Snapshot: Email пуст, локальная validation error; остальные 10 Auth/smoke tests прошли. Auth код и этот тест не изменялись. Day 2 group не запускалась; изолированный stack очищен. Повторный запуск проверяет воспроизводимость; причина timing пока гипотеза.
- 2026-10-06T21:19:56+06:00 — итоговое review нашло Important: delayed detail GET перезаписывает PUBLISHED stale DRAFT. Regression RED: `corepack pnpm exec vitest run src/features/events/event-pages.test.tsx`, exit 1, `1 failed | 26 passed (27)`, expected PUBLISHED / received DRAFT. Fix: await cancelQueries exact saved owner/id перед setQueryData публикации. Других findings нет.
- 2026-10-06T21:21:09+06:00 — cache-race GREEN: full frontend `76 passed (76)`, exit 0. make check после исправления: unit `157 passed`, frontend `76 passed`, OpenAPI drift none. Повторный изолированный browser gate прошёл: Auth/smoke 11, event lifecycle 2, limiter 1. Регистрационный сбой не повторился; root cause не доказана. Screenshots event-public.png/event-published-owner.png просмотрены: safe plain text, timezone и public link соответствуют plan. Финальный make verify будет выполнен на snapshot с review fix.

- 2026-10-06T21:29:47+06:00 — PR #8 создан; задача завершена, feature branch/worktree сохранены для review. Staged/branch diff проверен: secrets и .env отсутствуют, только synthetic fixtures.

## Decisions and deviations

- PublicEventResponse: id, title, description, slug, starts_at, ends_at, timezone, capacity, status. Без owner_id и внутренних timestamps. Status PUBLISHED/FINISHED/CANCELLED; FINISHED вычисляется Clock при now >= ends_at.
- Publish устанавливает published_at, schedule_updated_at и updated_at одним значением Clock; slug сохраняется. PostgreSQL row lock общий с PATCH.
- Миграция не требуется: все persisted поля существуют.
- Public page/API не вызывают session recovery. Registration/cancellation/published editing/notifications отложены согласно approved scope; до последующих задач эти операции недоступны.
- Итоговое review: один Important cache race исправлен по TDD; Critical/Minor нет. Второе review не запускалось согласно executing-plans; fix подтверждён regression и полным frontend suite.
- Browser lifecycle scenarios используют отдельный rate budget после Auth suite посредством перезапуска только уникального test Nginx. Production limiter не менялся.

## Issues discovered

- Первый make verify — exit 2 на frontend typecheck: новый test вызвал logout вместо logoutSession. Исправлено имя тестового вызова; application Auth код не менялся.
- Следующий make verify — exit 2, existing Auth test `old refresh cannot overwrite cookies after login as another account` (auth-refresh.spec.ts:117) не перешёл с register на login. Snapshot: пустое Email и локальная validation error. Остальные 10 Auth/smoke tests passed. На повторном изолированном запуске все 11 passed. Timing — гипотеза, root cause не доказана; нестабильность может повториться. Auth refactoring вне scope.
- Vite сообщает warning о chunk >500 kB; production build успешен. Code splitting не входит в эту задачу.
- HTTPS Git credentials локально отсутствуют. PR будет опубликован через GitHub connector; подтверждается совпадение Git tree локального snapshot и удалённого commit.

## Verification

### Baseline — 2026-10-06T21:07:08+06:00

Command: `UV_CACHE_DIR=/tmp/uv-cache-event-publish make check`
Exit code: `0`
Result: backend `157 passed in 6.56s`, frontend `65 passed (65)`; OpenAPI drift: none.

### RED — 2026-10-06T21:09:22+06:00

Command: `make test`
Exit code: `2` (pytest `1`)
Result: `9 failed, 273 passed in 51.45s`; новые endpoints отсутствуют (404).

Command: `cd frontend && corepack pnpm test -- src/features/events/event-pages.test.tsx`
Exit code: `1`
Result: `7 failed | 65 passed (72)`; publish action и public route отсутствуют.


### GREEN — 2026-10-06T21:12:06+06:00

Command: `make test`
Exit code: `0`
Result: backend `282 passed in 42.94s`, frontend `72 passed (72)`.

### API generation

Command: `make api-generate`
Exit code: `0`
Result: generated schema.d.ts; subsequent OpenAPI drift checks: none.

### Review correction RED — 2026-10-06T21:19:56+06:00

Command: `cd frontend && corepack pnpm exec vitest run src/features/events/event-pages.test.tsx`
Exit code: `1`
Result: `1 failed | 26 passed (27)`; delayed background GET replaced PUBLISHED with DRAFT.

### Review correction GREEN — 2026-10-06T21:21:09+06:00

Command: `cd frontend && corepack pnpm test`
Exit code: `0`
Result: `76 passed (76)`; regression сохраняет PUBLISHED и public link после delayed GET.

Command: `make check`
Exit code: `0`
Result: Ruff/mypy/ESLint/typecheck passed; backend `157 passed`, frontend `76 passed (76)`; OpenAPI drift: none.

### Browser screenshots

`.verification/event-public.png` и `.verification/event-published-owner.png` просмотрены. Только synthetic test event; no credentials. Screenshots остаются локальными artifacts.

### Final quality gate — 2026-10-06T21:27:40+06:00

Command: `UV_CACHE_DIR=/tmp/uv-cache-event-publish make verify`
Exit code: `0`
Result: backend `286 passed in 73.74s (0:01:13)`, frontend `76 passed (76)`; migrations/builds/nginx passed; Auth/smoke `11 passed (11.3s)`, event lifecycle `2 passed (8.6s)`, limiter `1 passed (2.1s)`; `verify: passed (isolated project foundation-verify-642fac1941c2)`.
Review-corrected implementation snapshot: `c06690b`. Isolated resources удалены. Screenshots повторно созданы этим gate.

## Result

- 2026-10-06T21:27:40+06:00 — финальный gate успешно завершён; implementation и review correction проверены. Подготовка PR.

Implemented:
- Owner publication POST с row lock и строгой валидацией; стабильный slug и timestamps.
- Anonymous public GET/schema и page /events/:slug; safe text, event timezone, effective FINISHED/CANCELLED, loading/error/retry.
- Publish action, public link, API types, race/boundary/auth regression tests и сквозной Day 2 browser scenario.

Known limitations:
- Registration, cancellation operations, published editing и notifications — последующие approved tasks.
- Один существующий Auth E2E registration сбой не повторился на двух последующих успешных запусках; первопричина не установлена.
- Vite bundle-size warning, без build failure.

## Pull Request

https://github.com/nbaishev/event-registration/pull/8

Open, не merged. Remote implementation commit `092d13b3908b47eb7d6e608fdc2904fd03ebf613`; его tree `86a34be727abef7e0f4a4292cac170e823c2ca4e` совпал с local `7546f01` tree. Различие commit SHA связано с публикацией через GitHub connector; source tree идентичен.
