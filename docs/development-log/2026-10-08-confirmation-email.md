# Task 17 — Confirmation / Ticket Email

Started at: `2026-10-08T18:11:23+06:00`
Finished at: `2026-10-08T18:34:32+06:00`

## Initial prompt

Plan: `docs/superpowers/plans/17-2026-10-08-confirmation-email.md`

Execution prompt:

Выполни задачу [17-2026-10-08-confirmation-email.md](docs/superpowers/plans/17-2026-10-08-confirmation-email.md)

## Timeline

- 2026-10-08T18:11:23+06:00 — создан worktree `feat/confirmation-email` от 0390630, начат baseline.
- 2026-10-08T18:20:26+06:00 — unit и PostgreSQL GREEN; development gate и review.
- 2026-10-08T18:24:38+06:00 — финальный gate выполняет unit/frontend checks после review fixes.
- 2026-10-08T18:29:13+06:00 — broker → worker → SMTP smoke успешен; Playwright выполняется.
- 2026-10-08T18:31:10+06:00 — `make verify` exit 0, isolated stack/volumes удалены.
- 2026-10-08T18:34:32+06:00 — создан PR #20 через GitHub connector.

## Decisions and deviations

- Execution prompt принят как approval указанного плана: прежний Status описывает состояние до этой команды. Стоимость ошибочного толкования — дополнительный review реализации.
- Shell `git fetch origin master` недоступен без HTTPS credentials. GitHub connector подтвердил remote master SHA `039063042ae5a9bbe942b80721ec738bc6830dae`, совпадающий с baseline. Публикация через connector.
- Persistent schema и HTTP API не меняются.
- Ruling: exactly-once не добавлять — ADR-004; стоимость — возможный duplicate после SMTP accepted/commit failure.
- Ruling: reminder/reschedule/cancellation не реализуются — отдельные планы; стоимость — эти уведомления остаются для следующих задач.
- Ruling: scanner batching/indexes/throughput не расширять — approved MVP scope; стоимость — отдельный анализ при росте нагрузки.
- SMTP fake исправлен под реальный `send_message` success contract (пустой dict). Default FROM использует example.com: EmailStr отклоняет special-use example.test.
- Existing verification tests обновлены под Redis/Mailpit port calls, обязательный smoke и failure cleanup.

## Review

Fresh reviewer `confirmation_review` (gpt-6-astra), staged diff от 0390630. Critical: none.

Important: после назначения ephemeral APP_ORIGIN worker/Beat сохраняли старый origin. Исправлено явным recreation worker/Beat до smoke; regression RED → GREEN.

Minor (deferred):

- Различать SMTP/SMTP_SSL fake и отдельно проверять validating SSL context; риск — пробел покрытия при будущем изменении transport.
- Malicious-title headers в real sink: smoke использует benign title, injection-looking title покрыт rendering unit test; риск — пробел дополнительного end-to-end покрытия.

## Verification

### Baseline

Command: `uv run --frozen --project backend pytest backend/tests/unit -q`
Exit code: `0`
Result: `259 passed in 4.75s`.

### RED / GREEN

- Unit eligibility/rendering/SMTP: RED exit 1 (`13 failed, 8 passed`), GREEN exit 0 (`21 passed in 0.29s`).
- PostgreSQL scanner/delivery: RED exit 1 (`15 failed, 7 passed in 8.81s`).
- Command: `uv run --frozen --project backend pytest backend/tests/integration/test_confirmation_email.py backend/tests/integration/test_waitlist_promotion.py backend/tests/integration/test_registration_cancel.py -q`; exit 0, `38 passed in 19.37s`.
- Дополнительные concurrency/time-boundary tests: confirmation integration suite exit 0, `24 passed in 4.13s`.
- Celery adapters: RED exit 1 (`3 failed, 9 passed`); GREEN с SMTP/rendering exit 0 (`24 passed in 1.04s`).
- Review regression `test_final_origin_reaches_worker_and_beat_before_smoke`: RED exit 1 (`1 failed in 0.07s`); verification unit suite GREEN exit 0 (`17 passed in 0.06s`).

### Final gate

Timestamp: `2026-10-08T18:31:10+06:00`
Command: `make verify`
Exit code: `0`
Result:

- Ruff check/format, mypy (`55 source files`), backend unit `285 passed in 5.23s`.
- Frontend Vitest `170 passed (170)`; ESLint/TypeScript; `OpenAPI drift: none`.
- PostgreSQL integration `265 passed in 142.88s (0:02:22)`.
- Empty PostgreSQL upgrade/revision head/metadata drift passed.
- Frontend production build, backend/frontend Docker images, Compose config и `nginx -t` passed.
- `Notification smoke: real broker, worker, SMTP, ticket and committed timestamp passed.`
- Playwright: две группы по 12 tests passed.
- `verify: passed (isolated project foundation-verify-f4666de7258a)`; cleanup containers/network/volume успешен.

Staged diff проверен на whitespace и secrets: реальные credentials отсутствуют; только безопасные development defaults и synthetic test values. Полный gate output находится в `/tmp/task17-verify.log` (не коммитится).

## Result

Implemented: scanner/delivery с locks и recovery; Celery/Beat/Redis; plain-text билет с timezone/offset/link; SMTP security/timeout; isolated real-delivery smoke в make verify.

Known limitations: duplicate risk ADR-004; deferred review minors выше; остальные notification kinds вне scope.

Final verification: evidence выше. После gate код/configuration не менялись; только этот журнал и Git/PR metadata.

## Pull Request

https://github.com/nbaishev/event-registration/pull/20

Merge не выполнялся. Worktree сохранён.

Shell GitHub auth отсутствует, поэтому remote commit создан через connector: remote implementation `d1bb082d4d1a263702ed6f2febb328f39a76048c`, local implementation `b886e02`; tree SHA совпадает (`21e38bee15fc66d90911b1d6a154af5963fc2488`). Commit metadata различается; при дальнейшем shell push нужен authenticated fetch и согласование branch history. Завершающий docs-only commit фиксирует этот журнал в обоих checkout/PR.
