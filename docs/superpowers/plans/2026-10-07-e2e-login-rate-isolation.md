# CI E2E login limiter isolation

Status: execution authorized by user request 2026-10-07; bugfix contract below.

Scope: isolated Compose verification runner and Playwright test fixtures/imports; regression proving limiter state is reset between tests. Production Nginx config, rate/burst and login limiter assertions remain unchanged.

Required context: technical-design.md §26 and §30; engineering.md Nginx, TDD, secrets and canonical commands; existing development-process/development-log rules.

Steps:
1. New worktree from updated master; baseline make check, log before implementation.
2. Reproduce exact CI auth group/order and inspect shared Nginx bucket; save actual evidence including any passing local attempts.
3. RED regression: limiter test exhausts its bucket; next independent test must get backend 401 rather than stale 429.
4. Minimal test-only isolation: auto Playwright fixture restarts only this run's labelled isolated Nginx container before each test. Require ENVIRONMENT=test, explicit container ID and matching unique verification project/service labels. Poll readiness only, never retry login or wait for bucket decay. Runner passes container ID; no HTTP reset endpoint or production config change.
5. Every E2E uses the shared fixture. Preserve CI auth order and limiter's six 401/fourteen 429 assertions. Remove redundant group restarts once per-test reset owns isolation.
6. Run requested grep-invert group and limiter suite on isolated stack, then make check/review and full make verify.
7. Update journal, staged secrets review; retain branch/worktree. Apply the fix to existing PR #14, preserving its draft-deletion scenario, and verify CI.

Acceptance: auth group no leaked429; each test has fresh bucket; limiter still returns exactly14 rate-limited responses for20 rapid requests; unsafe/non-test resets rejected before restart; no prod limiter weakening, no login retries/sleeps.
