# Исправление синхронизации auth-refresh E2E в PR #12

Started at: `2026-10-07T17:54:25+05:00`
Finished at: `2026-10-07T18:05:05+05:00`

## Initial prompt

Execution prompt:

Исправь

Контекст: CI PR #12 падает в `logout waits for an in-flight refresh and clears its new access cookie` по общему timeout 30000 ms.

## Scope / plan

Пользователь разрешил исправить обнаруженный CI failure в существующем PR. Продолжается worktree `feat/event-capacity`, base correction `d833dbf`; production auth и capacity contract не меняются.

1. Проверить baseline и воспроизвести незавершённый initial `/me` в E2E.
2. Исправить synchronization: bounded condition ожидания фактического refresh с повторным visibility event после завершения initial query; общий timeout/retries/assertions безопасности не ослаблять.
3. Проверить обычный и delayed-initial-session сценарии, соседний account-switch тест, полный `make verify`; review, secrets scan, обновить PR #12 и проверить CI.

## Timeline

- 2026-10-07T17:54:25+05:00 — начато исправление; рабочая копия чистая; исходный CI run `37621231851`: 10 passed, 1 failed (logout/refresh timeout); local previous verify exit 0.

- 2026-10-07T17:59:34+05:00 — deterministic RED подтверждён: original synchronization + held initial server 200 `/me` → timeout 30000 ms; bounded refresh synchronization реализована; GREEN выполняется.

- 2026-10-07T18:01:16+05:00 — targeted GREEN: 5 passed (7.7s), включая delayed `/me`; independent review без findings; полный `make verify` запущен.

- 2026-10-07T18:05:05+05:00 — локальная реализация/verification завершены: полный `make verify` exit 0 после cleanup. Исправление публикуется в PR #12; результат последующего GitHub CI записывается в description PR со ссылкой на run.

## Decisions and deviations

- Не утверждаем точную причину CI без trace. Код содержит воспроизводимую гонку: cached login user виден до завершения `/me`; visibility event дедуплицируется с текущим query; raw `refreshing` Promise не имеет собственного timeout.
- Синхронизация соседнего account-switch сценария использует тот же механизм и входит в исправление общей причины.

## Verification

- Baseline: targeted `corepack pnpm e2e --grep auth-refresh` через временную копию `scripts/verification.py` с одним Playwright group, isolated stack; exit 0, `4 passed (6.5s)`, cleanup завершён (`/tmp/task10-auth-baseline.log`).
- RED: тот же targeted runner, добавлен delayed initial `/me` сценарий; exit 1, `1 failed`, `4 passed (38.6s)`; failure строго в `...with initial session in flight`, `Test timeout of 30000ms exceeded` (`/tmp/task10-auth-red.log`).
- `cd frontend && corepack pnpm lint && corepack pnpm typecheck`: exit 0.
- GREEN: targeted auth-refresh runner — exit 0, `5 passed (7.7s)`; delayed initial `/me` logout case `1.4s`; cleanup завершён (`/tmp/task10-auth-green.log`).
- Independent review: без actionable findings; auth assertions сохранены, actual server refresh 200 и cleanup подтверждены.
- Final `make verify`: exit 0 после cleanup (`/tmp/task10-auth-verify-exit`), `/tmp/task10-auth-verify.log`: Ruff/format/mypy, unit `207 passed in 2.99s`, frontend lint/typecheck + `112 passed`, PostgreSQL/backend `400 passed in 95.54s`, empty PostgreSQL upgrade/head/check, production/Docker builds, Compose config/readiness/Nginx; Playwright 12 + 2 + 1 + 1 passed. Unique stack и volumes удалены.
- На момент этого локального commit исправление ещё не опубликовано; GitHub CI будет проверен на опубликованном correction commit. Актуальный результат и run URL — в PR #12 description. Локальный success не является утверждением о success CI.

## Result

Исправлена воспроизводимая гонка E2E setup: cached user render не используется как доказательство завершения initial `/me`. Тест ждёт реального refresh request с ограниченным polling, удерживает его до logout/login assertions и освобождает при ошибке. Добавлен regression variant с задержанным реальным `/me` response. Общий timeout, retries и security assertions не ослаблены. Production auth/registration/Event код не меняется.

Known limitations: trace исходного CI run отсутствует; доказана сама гонка и устранён её воспроизводимый сценарий. GitHub CI подтверждается отдельно после публикации.

## Pull Request

https://github.com/nbaishev/event-registration/pull/12
