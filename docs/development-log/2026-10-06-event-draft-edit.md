# Task 06 — Event Draft Editing

Started at: `2026-10-06T00:20:22+05:00`
Finished at: `IN PROGRESS`

## Initial prompt

Plan: `docs/superpowers/plans/06-2026-10-05-event-draft-edit.md`

Execution prompt:

Выполни задачу [06-2026-10-05-event-draft-edit.md](docs/superpowers/plans/06-2026-10-05-event-draft-edit.md)

## Timeline

- 2026-10-06T00:20:22+05:00 — Task 05 PR #6 confirmed merged; new `feat/event-draft-edit` worktree created from master `f826f24149d22af5fa6057f17b0f0b9899027ca6`; dependencies bootstrapped; baseline `make check` passed. Log created before implementation.
- 2026-10-06T00:25+05:00 — Added PostgreSQL integration tests first. Initial RED: 34 expected failures because PATCH route was not implemented (HTTP 405); a later sandbox-only connection failure was isolated to network access from the constrained test process. Running tests with the approved network context reached PostgreSQL consistently.
- 2026-10-06T00:30+05:00 — Implemented strict PATCH schema, row lock, merged-state validation, status/temporal guards, transactional savepoint slug retries, endpoint, and event response handling. Backend integration tests GREEN: 34 passed, including competing updates and collision rollback.
- 2026-10-06T00:36+05:00 — Added draft edit form and route, exact instant timezone prefill (including ambiguous DST), save/error state, detail/list cache updates, explicit slug regeneration action, and generated OpenAPI types. RTL GREEN: 12 event page tests and 5 timezone tests passed.
- 2026-10-06T00:41+05:00 — Extended browser flow for rejected PATCH → reload unchanged, successful edit → reload, and owner list. Targeted Playwright `event-drafts`: 1 passed; screenshot saved at `.verification/event-edit.png`.
- 2026-10-06T00:43+05:00 — First `make verify` passed unit/integration/component/migration/build checks but hit two existing intermittent `auth-refresh.spec.ts` failures. A second run had one auth-switch registration/history failure before the event E2E group. No auth code was changed.
- 2026-10-06T00:52+05:00 — Third full `make verify` passed: unit 157, integration 272, frontend 61, migrations, build, 11 general browser tests, event-drafts 1, login limiter 1. Docker project was isolated and automatically removed.
- 2026-10-06T00:54+05:00 — Independent code review found a schedule-second precision issue in unchanged `datetime-local` values. Fixed by preserving the original UTC instant unless its local time, timezone, or DST fold choice changes; added a text-only edit regression test. Made `regenerate_slug` optional in generated TypeScript and explicit-null-invalid at runtime.
- 2026-10-06T01:00+05:00 — Final post-review-fix `make verify` passed: unit 157, integration 273, frontend 62, migrations, build, general E2E 11, event-drafts 1, login limiter 1.
- 2026-10-06T01:01+05:00 — Reviewer follow-up confirmed the precision issue is fixed and found no Critical or Important remaining. Minor OpenAPI mismatch remains: generated optional nullable types allow `null` although the request validator rejects it.

## Decisions and deviations

- PATCH request is a strict partial schema: optional `title`, `description`, `starts_at`, `ends_at`, `timezone`, `capacity`, plus optional strict boolean `regenerate_slug` (omitted means false). An empty body, `regenerate_slug: false` as the sole action, and explicit null values are rejected with 422. A supplied field equal to its persisted value returns without changing timestamps. No owner/status input is accepted.
- Validate the merged persisted + supplied field state before mutation. A request that supplies a field equal to its persisted value is not a change; schedule timestamp updates only when starts/ends/timezone value actually changes.
- `regenerate_slug: true` is the explicit slug action. It uses the effective title. Title-only changes preserve slug. Slug collisions retry within the savepoint/transaction; exhaustion rolls back all fields.
- Lock sequence: load Event by id with `FOR UPDATE`, return missing/owner/state errors, then validate/update and commit under that lock. For `now >= original starts_at`, actual schedule or capacity changes return 409 `EVENT_ALREADY_STARTED`. PUBLISHED returns 409 `EVENT_NOT_EDITABLE`; CANCELLED returns 409 `EVENT_CANCELLED`.
- A successful value change sets `updated_at = clock.now()`; only actual schedule changes set `schedule_updated_at`. DRAFT update does not enqueue notifications.

## Baseline

Command: `make bootstrap`, then `make check` with cached UV/Corepack/PNPM paths.

Exit code: `0`.

Result: Ruff check/format and mypy passed; backend unit `157 passed in 7.34s`; frontend lint and typecheck passed; Vitest `58 passed (58)`; `OpenAPI drift: none.` No baseline failures.

## Result

Implementation and review completed; ready for PR. Scope is DRAFT partial update, explicit DRAFT slug regeneration, and owner edit UI. No published-event editing, delete/cancel, waitlist, notification, or SSE behavior.

## Verification

- `make api-generate` — passed; generated `frontend/src/api/schema.d.ts` from FastAPI OpenAPI.
- Final post-review-fix `make verify` — passed: backend 273, frontend 62, migrations, production build, general E2E 11, event-drafts E2E 1, login limiter E2E 1.
- Targeted PostgreSQL integration before final run — 34 passed; final full integration total was 273.
- Targeted Playwright `event-drafts` — 1 passed.
- Screenshots: `.verification/event-edit.png` and `.verification/event-detail.png`.
- Earlier E2E failures in two existing auth refresh/switch tests were transient; the final full verification passed. Auth implementation was not changed.
- Review: seconds-loss finding fixed and independently confirmed. Remaining minor OpenAPI nullability mismatch is documented; optional `null` is rejected by API validation.

## Known limitations

- Edit is intentionally limited to DRAFT. Published/cancelled editing, cancellation, notifications, and SSE remain out of scope.
- The frontend production bundle emits the existing Vite warning that the minified chunk exceeds 500 kB; the build succeeds.

## Pull Request

Not created yet.
