# CI: live dashboard refresh

Started at: `2026-10-09T15:37:07+06:00`
Finished at: `2026-10-09T15:39:43+06:00`

## Initial prompt

Исправь в отдельной ветке падение CI на тесте frontend/e2e/live-dashboard.spec.ts:80. Ошибка возникает на строке const rejected = page.waitForResponse(
  response => response.url().endsWith('/api/auth/refresh')
);. Лишние проверки не запускай.

## Context / Scope

Task 16: `docs/superpowers/plans/16-2026-10-07-live-dashboard-reconnect.md`, browser recovery contract. Только синхронизация существующего E2E-сценария; production behavior не меняется.

## Timeline

- 2026-10-09T15:37:07+06:00 — создан отдельный worktree, начата диагностика гонки SPA-навигации.
- 2026-10-09T15:39:43+06:00 — targeted сценарий после изменения прошёл; diff проверен.

## Decisions and deviations

- По запросу пользователя проверки ограничены падающим E2E-сценарием; baseline/full gates не запускаются.
- Гипотеза: click возвращается до размонтирования dashboard; немедленный pushState может оставить прежний stream, который не вызывает новый refresh.

## Verification

Command: `python3 /tmp/run-live-dashboard-targeted.py` (временный wrapper существующего runner; только `corepack pnpm e2e e2e/live-dashboard.spec.ts --grep 'interrupted stream'`, остальные группы исключены).

До изменения: exit code `0`, `1 passed (6.3s)`; локально intermittent failure не воспроизведён.
После изменения: exit code `0`, `1 passed (6.2s)`, scenario duration `4.6s`.

Review: просмотрен diff; добавлено только ожидание завершения SPA-перехода. `git diff --check`: exit code `0`. Production code и contract не менялись. Stack удалён runner после проверки.

## Result

Внесено ожидание заголовка списка мероприятий до повторного mount dashboard и удаления refresh cookie.

Known limitations: полный `make verify` не запускался; PR не создавался.
