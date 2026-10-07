# CI auth-refresh E2E setup race

Started at: `2026-10-07T21:15:40+06:00`
Finished at: `IN PROGRESS`

## Initial prompt

Исправь CI failure в auth-refresh E2E.

Проверь гипотезу race: registerAndLogin может вернуть управление после
рендера cached user, пока первоначальный /api/auth/me ещё выполняется.
После замены cookies этот старый запрос может породить первый refresh,
а reload — второй.

Production auth code без подтверждённой необходимости не меняй.
Стабилизируй setup failing test, сохрани требование refreshes === 1.

Сначала запусти только failing E2E с repeat-each=10.
Если проходит — один финальный make verify.
Следуй AGENTS.md, scope не расширяй.

## Timeline

- 2026-10-07T21:15:40+06:00 — CI run 37634817619/job 112838130014 изучен; failing assertion Expected 1, Received 2. Baseline только failing E2E repeat-each=10 выполняется.

- 2026-10-07T21:17:39+06:00 — baseline failing E2E repeat-each=10: exit 0, 10 passed (38.4s); race локально не воспроизведён. Setup дополнен barrier successful initial /me до замены cookies.

- 2026-10-07T21:19:34+06:00 — setup GREEN: targeted 10 passed (23.7s), exit 0; начат единственный финальный make verify.

- 2026-10-07T21:23:40+06:00 — единственный финальный make verify exit 0; исправленный E2E прошёл также в полном suite.

## Decisions and deviations

- Продолжение исправления CI в существующей ветке/worktree `feat/my-registrations`, PR #13.
- Scope: только setup `expired refresh clears auth cookies and returns to login without a recovery loop`; production auth и общий registerAndLogin не меняются (другой тест намеренно удерживает initial /me).
- Временный runner `/tmp/auth-refresh-repeat.py` запускает только этот test с `--repeat-each=10 --workers=1` на уникальном Compose stack. Быстрые 10 логинов получают отдельный test login budget через временный nginx override. Repository limiter не меняется; финальный make verify использует исходный production config.

## Verification

### CI RED

Run: `37634817619`, job `112838130014`, 2026-10-07T14:17:51Z.
Failing test: `expired refresh clears auth cookies and returns to login without a recovery loop`.
Result: `Expected: 1`, `Received: 2`, suite `1 failed, 11 passed`.

### Baseline targeted

Command: `corepack pnpm exec playwright test e2e/auth-refresh.spec.ts --grep 'expired refresh clears auth cookies and returns to login without a recovery loop' --repeat-each=10 --workers=1` (temporary isolated runner).
Exit code: `0`.
Result: `10 passed (38.4s)`.
Race не воспроизведён локально, но helper возвращается после cached email, и существующий controlled initial-session-in-flight test подтверждает возможность незавершённого /me. LoginPage пишет user в query cache до навигации; useSession запускает stale GET при mount. Barrier устранит эту предпосылку без production change.
Первый неверный временный grep дал `No tests found`, не используется как evidence.


### Targeted после изменения setup

Command: `corepack pnpm exec playwright test e2e/auth-refresh.spec.ts --grep 'expired refresh clears auth cookies and returns to login without a recovery loop' --repeat-each=10 --workers=1` (temporary isolated runner).
Exit code: `0`.
Result: `10 passed (23.7s)`.
`refreshes === 1` сохранён и проверен в каждом повторении. Test stack освобождён.

### Единственный финальный quality gate

Timestamp: `2026-10-07T21:23:40+06:00`.
Command: `make verify`.
Exit code: `0`.
Result: `404 passed in 93.01s (0:01:33)`; Vitest `120 passed (120)`; Playwright `12 passed (11.0s)`, `2 passed (7.6s)`, `1 passed (6.7s)`, `1 passed (6.5s)`, `1 passed (1.6s)`.
Миграции: `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`
Build/Compose/Nginx/smoke прошли.
Result: `verify: passed (isolated project foundation-verify-c0ba44ba0570).`

## Result

Setup failing test ждёт successful initial /me и завершения body до замены cookies. `refreshes === 1` сохранён. Production auth и общий helper не изменены. Проверки — выше; remote CI после публикации ожидается.

Known limitations: CI race не воспроизведён локально в исходных 10 повторах; проверка setup prerequisite опирается на код и существующий controlled initial-session-in-flight test.

Secrets review: изменены только E2E setup и log; tokens/cookies/JWT_SECRET не записываются; git diff --check exit 0.

## Pull Request

https://github.com/nbaishev/event-registration/pull/13
