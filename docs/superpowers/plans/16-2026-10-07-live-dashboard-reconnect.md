# Task 16 — Live Dashboard and Reconnect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax. Implementation только по отдельной команде пользователя.

**Status:** Декомпозиция и решения утверждены пользователем 2026-10-07; файл подготовлен для review перед implementation.

**Goal:** Dashboard обновляет counters без reload и восстанавливает snapshot после разрыва/expired access cookie.

**Architecture:** EventStats использует управляемый EventSource hook и существующий refreshSession. Stream только invalidates owner/event stats query; reconnect закрывает старый stream, обновляет auth и refetches snapshot после нового открытия.

**Tech Stack:** Существующие Python/FastAPI, sync SQLAlchemy/PostgreSQL, React/TypeScript/MUI/TanStack Query, pytest/Vitest/Playwright; новые infrastructure services не нужны.

**Spec:** [technical-design.md](../specs/technical-design.md), §§27–30, 38; [ADR-005](../../adr/005-sse-single-worker.md); автоматический backoff утверждён 2026-10-07.

## Global Constraints

- Lifecycle и PR: [development-process.md](../../development-process.md); engineering rules — только sections из Required context ниже; journal: [development-log.md](../../agent-rules/development-log.md).
- Перед кодом: отдельная branch/worktree от updated master и development log. Сейчас создаются только plans, implementation не начинается.
- Не добавлять Ticket table, outbox, RefreshSession, Redis Pub/Sub, Redux, microservices или unrelated refactoring. Persistent schema change не предполагается.
- Targeted tests для RED/GREEN; `make check` для development gate. Review → fixes → один финальный `make verify`; после успешного gate без изменений повтор не нужен. `make test` не является промежуточным обязательным gate.
- Before PR: actual verification evidence/limitations в log, staged diff secrets review; screenshots для существенных UI changes.

## Definition of Done

[AGENTS.md](../../../AGENTS.md), общий gate из engineering.md и все Acceptance criteria этого plan. Один PR; реализация только по отдельной execution-команде после review этого файла.

## Task / PR boundary

**Dependencies:** Tasks 14–15 merged; существующие refreshSession/SessionBoundary.
**Branch:** `feat/live-dashboard`.
**Scope:** EventSource lifecycle, live invalidation, refresh/reconnect/backoff, UI connection status, browser integration.
**Out of scope:** Новая auth implementation, participant live updates, polling fallback, WebSocket, replay, изменения SSE/backend контрактов.

## Required context

Spec/ADR выше; engineering.md: Auth, SSE, Canonical commands; Task 14 Files/interfaces, Task 15 Contract; `frontend/src/api/client.ts`, features/auth/session.ts и existing EventStats.

## Contract / Acceptance criteria

- Same-origin EventSource `/api/events/{eventId}/stats/stream`, cookies browser; subscribe только при active auth и mounted owner/event dashboard.
- При onopen initial/reconnected stream invalidates exact `eventKeys.stats(ownerId,eventId)` для snapshot; stats_changed делает тот же refetch. Counter updates берутся только из StatsResponse.
- onerror закрывает старый EventSource и запускает один recovery loop, подавляя нативный auto-reconnect. Первую попытку refresh+new EventSource делать через 1s; subsequent failures через 2,4,8,16,30s, далее 30s. Successful onopen сбрасывает backoff; transient network/5xx не удаляет current snapshot.
- Перед каждым reconnect использовать existing refreshSession (single-flight с обычным HTTP client); новый EventSource только после success. Refresh 401 → existing session loss/login, retries останавливаются.
- Чтобы hanging connection не оставался без retry, открытие нового stream имеет timeout 10s, затем close и следующий backoff. onerror/timeouts одной попытки не создают двойной retry.
- После успешного refresh, перед созданием stream, выполнить authenticated getEventStats: 403/404/EVENT_NOT_PUBLISHED останавливают recovery и показывают existing access/error UI. Snapshot request/stream callbacks защищены от stale owner/event generation.
- UI статусы «Подключаемся…», «Обновляется в реальном времени», «Восстанавливаем соединение…»; при terminal access failure — dashboard error. Existing ручной refetch сохраняется; polling нет.
- Unmount/navigation/logout/account switch: close stream, clear timers, abort owned validation fetch; late refresh/open/error callbacks не создают stream и не меняют новый cache/UI.
- Owner dashboard получает изменения register/cancel/promotion/capacity/check-in из другого browser context без reload. Пропущенные во время разрыва изменения восстанавливаются snapshot после onopen.

## Files / interfaces

Create `frontend/src/features/events/use-live-stats.ts`, `use-live-stats.test.tsx`; modify event-stats.tsx/tests; create `frontend/e2e/live-dashboard.spec.ts`, extend existing verification grouping. Existing api/client.ts только потребляется, auth algorithm не переписывается.
Produces `useLiveStats(ownerId: string, eventId: string): 'connecting' | 'live' | 'reconnecting' | 'error'`, lifecycle owned by EventStats; consumes refreshSession, getEventStats, eventKeys.stats и existing auth subscriptions. Active callback generation — локальный hook lifecycle guard, не новая global auth generation.

## Review Focus / Test strategy

RTL fake EventSource/deferred promises/fake timers: `test_signal_refetches_exact_stats`, `test_reconnect_refresh_open_refetch_order`, `test_backoff_and_open_timeout`, `test_refresh_401_stops`, `test_forbidden_stats_stops`, `test_cleanup_blocks_late_callbacks`, `test_concurrent_http_and_sse_share_refresh`. Проверять network/refetch effects, а не только status label.
Playwright browser contexts owner/participants: counts без reload после всех mutation sources; принудительный stream abort с управляемым route interception; удалить access cookie перед reconnect → refresh/new stream/refetch; удалить refresh cookie → login; изменения во время disconnect видны после recovery. Не ждать реального JWT TTL. Existing E2E fixtures обеспечивают rate isolation; включить scenario ровно один раз в make verify.

## Execution steps / Verification

- [ ] Branch/worktree/log; перечисленные RTL tests → RED: `cd frontend && corepack pnpm exec vitest run src/features/events/use-live-stats.test.tsx src/features/events/event-stats.test.tsx`.
- [ ] Hook/status integration до GREEN; использовать existing refresh/session lifecycle без отдельного refresh fetch.
- [ ] Добавить browser live/recovery сценарии и verification rate-budget group; targeted Playwright на отдельном test stack для диагностики только при необходимости.
- [ ] `make check`, review/fixes; финальный `make verify` с live/reconnect browser scenarios. Screenshot live/reconnect, actual evidence в log, staged secrets review; один PR.
