# Исправления редактирования DRAFT Event

Started at: `2026-10-06T20:42:35+06:00`
Finished at: `2026-10-06T20:59:19+06:00`

## Initial prompt

План: `docs/superpowers/plans/06-2026-10-05-event-draft-edit.md`

Execution prompt:

Исправь 3 бага редактирования draft event:

1. `PATCH` сейчас отправляет все поля формы, включая неизменённые. Формируй payload только из полей, которые отличаются от загруженной версии события.
2. Не допускай lost update при редактировании одного draft в двух вкладках: изменение одного поля из второй вкладки не должно перезаписывать stale значения других полей. Сохрани partial-update semantics endpoint.
3. При открытии EditForm `useQuery` может сначала вернуть cached stale event, а затем свежий результат refetch. Сейчас локальный `useState` остаётся инициализирован старой версией. Синхронизируй форму со свежими incoming data, пока пользователь ещё не начал редактирование, но не перезаписывай dirty fields.

Добавь/обнови тесты для всех трёх сценариев и не расширяй scope.

## Timeline

- 2026-10-06T20:37+06:00 — подтверждены чистая `master` и существующий отдельный worktree `feat/event-draft-edit`; ветка с открытым PR #7 содержит реализацию, которой касаются дефекты.
- 2026-10-06T20:42:35+06:00 — baseline `make check` прошёл после повторного запуска с разрешённым test-контекстом: backend unit 157, frontend 62, lint/typecheck и OpenAPI drift без ошибок.
- 2026-10-06T20:42+06:00 — уточнены acceptance criteria плана для минимального PATCH, двух вкладок и обновления query data; development log создан до реализации.
- 2026-10-06T20:45+06:00 — RED: четыре focused component regressions упали ожидаемо: PATCH включал неизменённые значения, а форма оставалась на Cached title после свежего query результата; сценарий dirty title также не синхронизировал остальные поля.
- 2026-10-06T20:47+06:00 — GREEN: PATCH payload формируется по отличиям от текущего event; query refresh синхронизирует только поля, совпадавшие с предыдущим baseline. Четыре focused regressions прошли.
- 2026-10-06T20:48+06:00 — обновлены assertions для явной slug-регенерации и точности расписания; все event page tests: 16 passed.
- 2026-10-06T20:49+06:00 — `make check`: exit 0; backend unit 157, frontend 65, lint/typecheck и OpenAPI drift прошли.
- 2026-10-06T20:53:28+06:00 — полный `make verify`: exit 0; backend integration 273, frontend 65, миграции, локальная и Docker production build, Compose/Nginx smoke, 11 general E2E, event-drafts E2E 1 и login limiter E2E 1 прошли.
- 2026-10-06T20:53:28+06:00 — read-only code review не обнаружил Critical/Important замечаний; diff check прошёл.
- 2026-10-06T20:58:55+06:00 — staged secret scan прошёл; фиксы опубликованы в существующий PR #7 отдельными commits, PR description обновлено. Проверено, что PR открыт, не слит, head содержит семь commits.

## Decisions and deviations

- Работа остаётся в worktree и ветке `feat/event-draft-edit`, поскольку открытый PR #7 ещё не слит и `master` не содержит Task 06. Новый независимый PR/ветка не создаются.
- PATCH остаётся частичным; backend update под существующей PostgreSQL `FOR UPDATE` транзакцией сохраняется. Клиент будет исключать неизменённые поля из body.
- Dirty status относится к значениям полей формы, а не к факту любого ввода: если пользователь вернул значение к текущему baseline, поле синхронизируется как чистое.

## Baseline

Command: `UV_CACHE_DIR=/tmp/uv-cache-event-edit make check` (с разрешённым test-контекстом после sandbox-зависания на старте TestClient).

Exit code: `0`.

Result: Ruff check/format и mypy прошли; backend unit `157 passed in 3.81s`; frontend lint/typecheck прошли; Vitest `62 passed (62)`; `OpenAPI drift: none.` В sandbox тот же unit runner не завершался в timeout, вне ограниченного контекста завершился успешно.

## Verification

### RED

Command: `corepack pnpm exec vitest run src/features/events/event-pages.test.tsx -t 'prefills and saves an event draft|does not overwrite a different field|synchronizes untouched form fields|preserves dirty form fields'`

Exit code: `1`.

Result: `4 failed | 12 skipped`; проверки обнаружили полный PATCH body и stale values после refetch.

### Focused component tests

Command: `corepack pnpm exec vitest run src/features/events/event-pages.test.tsx`

Exit code: `0`.

Result: `16 passed`.

### Quality gate

Command: `UV_CACHE_DIR=/tmp/uv-cache-event-edit make check`

Exit code: `0`.

Result: Ruff check/format и mypy прошли; backend unit `157 passed in 3.15s`; frontend lint/typecheck прошли; Vitest `65 passed (65)`; `OpenAPI drift: none.`

### Full verification

Command: `UV_CACHE_DIR=/tmp/uv-cache-event-edit make verify`

Exit code: `0`.

Result: backend unit `157 passed in 3.01s`; backend integration `273 passed in 45.29s`; frontend `65 passed`; пустая PostgreSQL migration upgrade/revision head/metadata drift прошла; local/Docker frontend build и backend image build прошли; Compose readiness и `nginx -t` прошли; Playwright: 11 general + 1 event-drafts + 1 login-limiter passed. Vite выдал известное предупреждение о чанке `526.52 kB` (>500 kB), сборка успешна.

### Review and diff

Independent read-only code review: Critical/Important `0`; partial PATCH locking contract remains unchanged; no out-of-scope backend/API/schema changes.

`git diff --check`: exit `0`.

## Result

Implemented:
- Edit form отправляет только значения, которые отличаются от последнего синхронизированного Event; неизменённые поля и `regenerate_slug: false` опущены.
- Обычное редактирование из второй вкладки не отправляет stale значения других полей; существующий partial PATCH и PostgreSQL `FOR UPDATE` сохранены.
- Query refresh заменяет чистые значения формы и оставляет dirty values пользователя без изменений; успешный ответ становится новым clean baseline.
- Добавлены regressions для body, сценария другой вкладки, stale cache → свежий event и защиты dirty fields.

Known limitations:
- Известное предупреждение Vite о production chunk больше 500 kB осталось без изменений и не влияет на успешную сборку.

## Pull Request

Обновлён существующий [PR #7](https://github.com/nbaishev/event-registration/pull/7); открыт для review, не слит.
