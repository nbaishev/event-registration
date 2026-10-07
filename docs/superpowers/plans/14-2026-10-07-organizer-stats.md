# Task 14 — Organizer Statistics Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax. Implementation только по отдельной команде пользователя.

**Status:** Декомпозиция и решения утверждены пользователем 2026-10-07; файл подготовлен для review перед implementation.

**Goal:** Owner видит согласованный SQL snapshot capacity/confirmed/waitlist/checked_in/available_slots.

**Architecture:** Один SQL statement выбирает Event и aggregate registrations, обеспечивая согласованный snapshot. Dashboard размещается на существующей event details, получает initial snapshot и поддерживает ручной refetch.

**Tech Stack:** Существующие Python/FastAPI, sync SQLAlchemy/PostgreSQL, React/TypeScript/MUI/TanStack Query, pytest/Vitest/Playwright; новые infrastructure services не нужны.

**Spec:** [technical-design.md](../specs/technical-design.md), §§31–32, 35–36; lifecycle access уточнён пользователем 2026-10-07.

## Global Constraints

- Lifecycle и PR: [development-process.md](../../development-process.md); engineering rules — только sections из Required context ниже; journal: [development-log.md](../../agent-rules/development-log.md).
- Перед кодом: отдельная branch/worktree от updated master и development log. Сейчас создаются только plans, implementation не начинается.
- Не добавлять Ticket table, outbox, RefreshSession, Redis Pub/Sub, Redux, microservices или unrelated refactoring. Persistent schema change не предполагается.
- Targeted tests для RED/GREEN; `make check` для development gate. Review → fixes → один финальный `make verify`; после успешного gate без изменений повтор не нужен. `make test` не является промежуточным обязательным gate.
- Before PR: actual verification evidence/limitations в log, staged diff secrets review; screenshots для существенных UI changes.

## Definition of Done

[AGENTS.md](../../../AGENTS.md), общий gate из engineering.md и все Acceptance criteria этого plan. Один PR; реализация только по отдельной execution-команде после review этого файла.

## Task / PR boundary

**Dependencies:** Task 13 merged; registration/capacity/auth flows.
**Branch:** `feat/organizer-stats`.
**Scope:** GET stats, SQL aggregation, owner dashboard, cache isolation, generated API.
**Out of scope:** SSE/polling, mutable counters, participants list, графики/history.

## Required context

Spec sections выше; engineering.md: Architecture, PostgreSQL, Auth, Generated API, Canonical commands. Existing event details/API/query keys, Event/Registration models, auth SessionBoundary.

## Contract / Acceptance criteria

- GET `/api/events/{event_id}/stats` → StatsResponse spec §35; missing → 404 EVENT_NOT_FOUND, wrong owner → 403 EVENT_NOT_OWNER, own DRAFT → 409 EVENT_NOT_PUBLISHED. Auth required; no-store.
- PUBLISHED включая now >= ends_at и CANCELLED доступны; FINISHED вычисляемый lifecycle, не новый DB enum.
- SQL считает CONFIRMED, WAITLIST и CONFIRMED с checked_in_at NOT NULL; CANCELLED registration не входит. available_slots = capacity−confirmed. Никаких stored mutable counters, N+1 или отдельных несогласованных reads capacity/counts.
- Empty published Event: counts 0, available_slots==capacity. Check-in увеличивает checked_in, confirmed сохраняется.
- Register, cancel/promotion, capacity и check-in видны после refetch/reload.
- Details после публикации показывает пять подписанных значений и кнопку «Обновить статистику»; DRAFT dashboard не запрашивает. Loading/error/retry; CANCELLED/finished dashboard доступен.
- Query key включает ownerId/eventId; abort/delayed response/account switch не показывают старый owner snapshot. Не перезаписывать существующие event detail cache stats-ответом.

## Files / interfaces

Create `backend/app/events/stats.py`, `backend/tests/integration/test_event_stats.py`; extend events/schemas.py/router.py.
Create frontend `features/events/event-stats.tsx`, `event-stats.test.tsx`; extend events/api.ts и event-detail-page.tsx; generated schema; `frontend/e2e/organizer-stats.spec.ts`.
Produces `StatsResponse`, `get_owned_stats(session: Session, owner_id: UUID, event_id: UUID) -> StatsResponse`, frontend `getEventStats(eventId, signal?): Promise<StatsResponse>`, `eventKeys.stats(ownerId,eventId)` и `<EventStats ownerId eventId />`. Task 16 использует именно этот key и component.

## Review Focus / Test strategy

PostgreSQL integration: `test_empty_stats`, `test_counts_after_registration_cancel_promotion_capacity_checkin`, `test_stats_access_lifecycle`, `test_checked_in_is_subset_of_confirmed`; auth/no-store. SQL selection проверять actual snapshots, без тестов структуры query ради самой структуры.
RTL loading/error/retry, publish→dashboard, account switch/delayed fetch. Playwright refresh counts после registration и check-in через UI Tasks 13–14; без ожидания временных boundaries.

## Execution steps / Verification

- [ ] Branch/worktree/log; integration tests → RED: disposable `TEST_DATABASE_URL`, `uv run --frozen --project backend pytest backend/tests/integration/test_event_stats.py -q`.
- [ ] Реализовать single-statement read/use-case/schema/router до GREEN.
- [ ] `make api-generate`; RTL → RED: `cd frontend && corepack pnpm exec vitest run src/features/events/event-stats.test.tsx`.
- [ ] Реализовать dashboard/query key до GREEN; добавить Playwright и isolated verification group по существующему pattern.
- [ ] `make check`; review/fixes; финальный `make verify`, screenshot dashboard, log actual evidence и secrets review; один PR.
