# Task 10 — Published Event Capacity Implementation Plan (Day 3)

> **For agentic workers:** Использовать superpowers:executing-plans. Implementation начинается только по отдельной команде пользователя.

**Status:** Capacity-only PUBLISHED PATCH и scope утверждены пользователем в чате 2026-10-06; implementation завершена; независимый review и `make verify` успешны (2026-10-07).

**Task:** Изменение capacity опубликованного Event с promotion.

**Goal:** Owner увеличивает capacity, и свободные места атомарно получают FIFO участники waitlist.

**Architecture:** Существующий PATCH dispatches DRAFT editing или capacity-only PUBLISHED update после Event lock. Published use-case проверяет SQL confirmed count и вызывает общий promotion helper; Event и Registration changes сохраняются одним commit.

**Tech Stack:** Существующий Event/Registration stack и quality tools.

**Spec:** [technical-design.md](../specs/technical-design.md), sections 8, 11, 13–14, 38; [Task 09](09-2026-10-06-registration-cancel.md).

## Global Constraints

- Правила/gates: [engineering.md](../../agent-rules/engineering.md); lifecycle: [development-process.md](../../development-process.md); journal: [development-log rules](../../agent-rules/development-log.md).
- `new_capacity >= confirmed_count`, `now < starts_at`, FIFO и Event → Registration; mutable counters не добавляются.
- Утверждённое расширение Day 2 contract разрешает только PUBLISHED capacity. Остальные ограничения [Task 06](06-2026-10-05-event-draft-edit.md) / [Task 07](07-2026-10-05-event-publish.md) сохраняются; исторические планы не переписываются.

## Task / PR boundary

**Dependencies:** Task 09 merged, включая reusable no-commit `fill_available_slots`.

**Branch:** `feat/event-capacity`, новый worktree от updated master, один vertical-slice PR.

**Scope:** PUBLISHED capacity-only PATCH; confirmed SQL count; decrease guard; increase promotion; atomic transaction; organizer capacity control; cache update и tests.

**Out of scope:** PUBLISHED text/schedule editing, slug changes, Event cancellation, notification delivery, participants list, stats/SSE.

**Acceptance criteria:**

- Owner PUBLISHED PATCH `{capacity: N}` → 200 EventResponse; чужой → 403 EVENT_NOT_OWNER; missing → 404 EVENT_NOT_FOUND; CANCELLED → 409 EVENT_CANCELLED.
- Strict integer capacity 1..2147483647, без null/bool/string coercion; invalid → 422 VALIDATION_ERROR. PUBLISHED request с любым другим supplied field → 409 EVENT_NOT_EDITABLE целиком, даже если это значение не меняется.
- Decrease до confirmed count разрешён; ниже → 409 CAPACITY_BELOW_CONFIRMED, Event/Registration не изменены.
- Actual capacity change при `now >= starts_at` → 409 EVENT_ALREADY_STARTED. Equal-value capacity-only PATCH — 200 без changes/timestamps/promotion, аналогично прежнему no-op PATCH.
- Increase вызывает единый `fill_available_slots`, подтверждает первые N с корректными ticket/state. Shortage waitlist оставляет доступные места.
- Capacity, updated_at и все promotions сохраняются одной транзакцией; failure после partial promotion откатывает весь PATCH.
- Capacity-only change не меняет slug, schedule_updated_at, published_at, owner или status. DRAFT editing и partial form semantics остаются прежними.
- Concurrent capacity/register/cancel, в том числе decrease vs register, сохраняют confirmed <= capacity и соответствуют одному последовательному порядку.
- Organizer details после success/reload показывает capacity; participant после refetch/reload видит promotion. Delayed old detail GET не перезаписывает успешный PATCH.

**Test strategy:** TDD guards и no-op; PostgreSQL multi-slot FIFO, rollback и competing requests; RTL form/errors/cache; Playwright owner increase → participant reload.

**Verification:** Baseline `make check`/`make test`; targeted tests; `make api-generate` после изменения API schemas/responses; `make check`; `make test`; финальный `make verify`, включая DRAFT regression и capacity browser flow. Отдельно browser diagnostics через `make e2e` только при необходимости.

**Definition of Done:** [AGENTS.md](../../../AGENTS.md) плюс capacity invariant, atomic rollback и отсутствие регрессии DRAFT PATCH.

## Files / interfaces

- Modify: `backend/app/events/service.py`, `router.py` (OpenAPI errors при необходимости); `repository.py` только для persistence primitive, требуемого atomic update. Request/response schemas сохраняют существующие имена.
- Create tests: `backend/tests/unit/test_event_capacity.py`, `backend/tests/integration/test_event_capacity.py`; adjust только конкретные PUBLISHED capacity assertions в existing draft/publish tests, остальные запреты сохраняются.
- Create: `frontend/src/features/events/event-capacity-form.tsx`, `event-capacity-form.test.tsx`; integrate в `event-detail-page.tsx`; extend `frontend/e2e/event-registration.spec.ts`; regenerate schema при drift.

**Consumes:** `patch_owned_event(session, clock, owner_id, event_id, body) -> Event`, EventPatchRequest/EventResponse, Event FOR UPDATE; Task 09 `fill_available_slots(session, event, now) -> list[UUID]`; Task 08 `count_confirmed`.

**Produces:** `patch_published_capacity(session: Session, event: Event, now: datetime, capacity: int) -> Event` в events/service.py — Event уже locked/owner-validated, helper не commit; внешний `patch_owned_event` владеет final commit/rollback для PUBLISHED branch. Frontend использует прежний `patchEvent(id, {capacity})`.

Текущий `repository.save_event` делает commit; вызывать его до promotion нельзя. PUBLISHED branch использует flush-only persistence и единственный outer commit, не меняя transaction ownership unrelated DRAFT/publish operations. Перед изменениями собрать reject checks по supplied fields (`model_fields_set`), state/time/count. Frontend capacity form отправляет только capacity, синхронизирует pristine baseline, сохраняет dirty input при refetch; одинаковое значение не отправляет.

## Review Focus / test assertions

| Test | Assertions |
|---|---|
| `test_increase_promotes_multiple_fifo` | capacity +2; first 2 WAITLIST CONFIRMED; later WAITLIST; schedule timestamps прежние |
| `test_capacity_rollback_after_promotion_failure` | Event capacity и все registration snapshots прежние |
| `test_decrease_vs_register` | каждый возможный lock order сохраняет invariant; reject PATCH → CAPACITY_BELOW_CONFIRMED |
| `test_mixed_published_patch_and_noop` | mixed body 409 без mutation; equal capacity 200 без timestamps/promotion |
| `capacity success survives delayed detail GET` | UI новое capacity после старого GET; dirty form input не теряется |

Boundary tests: now==starts_at, capacity==confirmed, capacity==confirmed-1, 0/bool/null/overflow; other-owner/CANCELLED; race cancel/PATCH; DRAFT schedule/text/slug regressions.

## Execution steps

- [x] 1. По execution команде после merge 09 создать branch/worktree, baseline и log до implementation.
- [x] 2. Написать unit guards/no-op/mixed-body tests; `uv run --frozen --project backend pytest backend/tests/unit/test_event_capacity.py -q` → ожидаемый RED, записать причину.
- [x] 3. Реализовать dispatch и capacity helper; повторить unit command до GREEN.
- [x] 4. Добавить PostgreSQL tests Review Focus и race/boundary matrix; `make test` → RED для отсутствующего transactional behavior.
- [x] 5. Реализовать atomic persistence до GREEN `make test`; targeted historical PUBLISHED test обновить только для утверждённого capacity exception; commit backend/tests.
- [x] 6. Синхронизировать OpenAPI через `make api-generate` при contract change. Написать RTL prefill/save/error/dirty-refetch/delayed-GET tests; `cd frontend && corepack pnpm exec vitest run src/features/events/event-capacity-form.test.tsx` → RED.
- [x] 7. Реализовать form/details integration, exact detail query cancellation перед cache write, invalidation mine/public queries; повторить RTL до GREEN; commit UI.
- [x] 8. Добавить Playwright capacity increase с WAITLIST participant → reload CONFIRMED и rejected decrease → unchanged reload.
- [x] 9. Review, `make check`, финальный `make verify`, screenshots, journal actual results и secrets check; один PR.
