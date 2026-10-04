# Project Foundation

Started at: `2026-10-04T17:28:10+06:00`
Finished at: `2026-10-04T17:58:15+06:00`

## Initial prompt

Plan:
`docs/superpowers/plans/2026-10-04-project-foundation.md`

Execution prompt (JSON string preserves original trailing space):

```json
"Приступай к выполнению плана [2026-10-04-project-foundation.md](docs/superpowers/plans/2026-10-04-project-foundation.md) "
```

## Timeline

- 2026-10-04T17:28:10+06:00 — implementation started; master 45bda12 contains merged PR #1; new branch/worktree chore/project-foundation.

- 2026-10-04T17:38:54+06:00 — Clock 3 RED failures → 3 passed; bootstrap 1 RED failure → passed; readiness 3 RED (404) → 3 passed on PostgreSQL; UI 3 RED failures → 3 passed.

- 2026-10-04T17:50:05+06:00 — whole-branch review completed; reserved-character DB credentials regression fixed; final make verify exit 0.

- 2026-10-04T17:58:15+06:00 — PR #2 created; GitHub Verify run 37200252328 completed successfully; PR/CI evidence recorded.

## Decisions and deviations

- Worktree directory initially ignored via local Git exclude; tracked .gitignore will include it in this task. No unrelated commit on master.

- Versions pinned in lock files; current Starlette uses httpx2 for TestClient. Compatible jest-dom 6.9.1 pinned, esbuild explicitly allowed through pnpm-workspace.yaml.
- Reviewer Important finding: raw credentials interpolation in Compose URL. Fixed using separate components and SQLAlchemy URL.create; regression test observed RED (`1 failed`) then GREEN (`6 passed` unit suite), final full suite `9 passed`.
- Review rulings: Auth/throttling/SSE/business schemas/email/HTTPS remain outside Foundation; no extra features added. Repeated suites are permitted and kept simple. Remote CI implementation run passed; evidence below. Dependency security audit/image-digest pinning are outside this task; pinned image version tags and dependency lock files are used.

## Issues discovered

- Baseline `make check`: exit 2, `No rule to make target 'check'`. No application code, Makefile or tests exist yet.
- Docker socket requires sandbox escalation; system Corepack 0.30.0 had outdated signing keys. Corepack 0.34.0 installed under /tmp; signature validation retained.
- Initial TestClient deprecation resolved by switching dev transport to httpx2.
- Default localhost:8080 smoke failed: Docker Desktop forwarding returned 500. Read-only Windows Get-NetTCPConnection confirmed a listener on 0.0.0.0:8080 (PID 5240, process httpd); unrelated process was not stopped. APP_PORT=18080/APP_ORIGIN=http://localhost:18080 smoke passed. Defaults remain 8080.

## RED evidence

- Clock: `uv run --frozen --project backend pytest backend/tests/unit/test_clock.py -q`, exit 1, `3 failed`; interface stubs raised NotImplementedError.
- Bootstrap preservation: `uv run --frozen --project backend pytest backend/tests/unit/test_bootstrap.py -q`, exit 1, `1 failed`; ensure_env not implemented.
- Readiness: `uv run --frozen --project backend pytest backend/tests/integration -q`, exit 1, `3 failed`; all routes returned 404. Separate PostgreSQL project `foundation-red-45bda12` used.
- UI: `pnpm test`, exit 1, `3 failed`; empty App had no heading/status.
- Exact timestamps of individual RED commands were not recorded; milestone above uses actual current time and does not reconstruct command timestamps.

## Verification

### Baseline
Command: `make check`
Exit code: `2`
Result: `make: *** No rule to make target 'check'. Stop.`

### Executed commands and evidence

Environment overrides only for this sandbox: PNPM points to Corepack 0.34.0 under /tmp; UV/COREPACK/PLAYWRIGHT caches also under /tmp. No secret environment values are recorded.

- `make bootstrap` — exit 0 — locked dependencies/Chromium installed, existing .env preserved. Repeated ensure_env probe confirmed identical existing bytes.
- `make api-generate` — exit 0 — openapi-typescript 7.13.0 generated schema.d.ts; later re-generation was identical.
- `make check` — exit 0 — `6 passed`, `3 passed`, `OpenAPI drift: none.` (final full-gate run).
- `make test` — exit 0 — `7 passed` backend + `3 passed` frontend before added configuration regression; independent test Compose project cleaned up. Final make verify ran expanded 9-test backend suite.
- `make e2e` — exit 0 — `4 passed`; independent build/Compose/Nginx browser tests.
- `make verify` — exit 0 — `9 passed in 1.11s`, `3 passed`, `4 passed (2.5s)`, `No new upgrade operations detected.`, `Empty PostgreSQL upgrade, revision head and metadata drift: passed.` Project `foundation-verify-1f7de4a54b31` and its volumes removed.
- `make up` with APP_PORT=18080/APP_ORIGIN=http://localhost:18080 — exit 0 — backend/PostgreSQL/proxy healthy. Default8080 attempt exit2 due occupied Windows port.
- `docker compose up --build -d --wait --wait-timeout 120` with port18080 override — exit 0 — all four services healthy.
- HTTP smoke — exit 0 — /, /login, /register, /api/docs HTML available, health200/status=ok and ready200/status=ready.
- Drift probe — exit 0 — deliberately stale temporary output detected; stale file and tracked generated file unchanged; correct output passed comparison.
- `make migrate` — exit 0 — alembic upgrade head completed in backend container.
- `make down` — exit 0 — local stack stopped; development volume retained. RED-only stack removed with its own project-scoped volumes.
- Development DB sentinel id41 survived isolated make test/E2E and final make verify; verification did not remove development data. Sentinel table then removed from our own development DB.
- `git diff --cached --check` and staged secrets scan — exit 0; .env/cache files excluded; only development defaults and synthetic test credentials present.

### GitHub CI

Workflow: Verify, run 37200252328, job 111430295756, implementation commit 3590f812a12dffaa4e310b6a226cc04ef9775639.

Command: `make verify`
Exit code: `0` (step/job conclusion: success).
Actual output: `9 passed in 0.66s`; frontend `3 passed`; `4 passed (1.7s)`; `No new upgrade operations detected.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`; `OpenAPI drift: none.`

Run: https://github.com/nbaishev/event-registration/actions/runs/37200252328

## Result

Implemented:
- FastAPI health/readiness, injectable UTC Clock, request-scoped SQLAlchemy Session and Alembic configuration.
- React/MUI SPA shell, same-origin Nginx/Compose, one backend worker.
- Frozen dependency toolchains, API generation/drift detection, canonical Make gates and CI workflow.
- README and meaningful unit/integration/component/E2E coverage; reserved-character DB credentials regression fixed.

Known limitations:
- Auth and business features are intentionally outside this task.
- Default port 8080 is occupied on the Windows host; local smoke used 18080. Free 8080 or configure APP_PORT/APP_ORIGIN before local launch.
- Remote CI implementation run passed; later documentation-only commits run the same workflow again. Current checks are linked from PR #2.
- ESLint 9 and the jsdom whatwg-encoding transitive package emit package-install deprecation notices; runtime/checks/builds pass. No dependency security audit was performed.

Final verification:
- make check — exit 0 — Ruff, mypy, ESLint, TypeScript, 6 unit tests, 3 component tests; OpenAPI drift none.
- make verify — exit 0 — 9 backend tests, 3 component tests, 4 Playwright tests; empty PostgreSQL upgrade/head/metadata checks; production and Docker builds, nginx config and cleanup passed.


## Pull Request

https://github.com/nbaishev/event-registration/pull/2

Base: master. Head: chore/project-foundation.

Publication via GitHub connector because HTTPS Git credentials are unavailable. Local implementation commit 9de9a2d and remote implementation commit 3590f81 have identical tree 7fcf777efcb74b7846d2b4c897e97cdaa8a1f261; metadata/SHA differ. This follow-up records PR and CI evidence only.
