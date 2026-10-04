# ADR-005: SSE с одним backend worker для live dashboard

**File:** `docs/adr/005-sse-single-worker.md`  
**Status:** Accepted  
**Date:** 2026-10-04

## Context

Dashboard организатора должен live показывать:

- confirmed;
- waitlist;
- checked-in.

Live updates происходят после:

- registration;
- cancellation;
- promotion;
- capacity change;
- check-in.

Необходим простой realtime mechanism.

## Considered options

### 1. Polling

Frontend периодически вызывает `/stats`.

### 2. WebSocket

Постоянное двустороннее соединение.

### 3. SSE + shared Redis Pub/Sub

Позволяет несколько backend workers.

### 4. SSE + in-memory broadcaster

Один FastAPI process.

## Decision

Использовать:

```text
Server-Sent Events
+
in-memory broadcaster
+
exactly one FastAPI worker
```

Production MVP запускается:

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1
```

SSE несёт только сигнал:

```text
stats_changed
```

После него frontend выполняет:

```text
GET /api/events/{event_id}/stats
```

и получает актуальное состояние из PostgreSQL.

## Why

Dashboard требует только server → browser notifications.

WebSocket даёт лишнюю двустороннюю сложность.

Polling проще, но создаёт постоянные запросы независимо от изменений.

Redis Pub/Sub устраняет single-worker limitation, однако добавляет инфраструктурную сложность, не необходимую MVP.

SSE + in-memory broadcaster минимален и удовлетворяет требованиям при одном backend worker.

## Threading constraint

Backend использует sync SQLAlchemy/FastAPI handlers, которые могут выполняться в threadpool.

Они не должны напрямую модифицировать `asyncio.Queue`.

Broadcaster использует:

```text
loop.call_soon_threadsafe(...)
```

или эквивалентный thread-safe mechanism.

## Authentication consequence

SSE connection авторизуется при создании.

Текущий stream может пережить expiration access token.

При разрыве frontend выполняет:

```text
close EventSource
→ POST /auth/refresh
→ open new EventSource
→ refetch stats
```

При refresh `401` пользователь отправляется на login.

## Nginx consequence

Для SSE обязательно:

```text
proxy_buffering off
```

увеличенный:

```text
proxy_read_timeout
```

и периодический heartbeat.

## Consequences

Плюсы:

- небольшая реализация;
- браузерный стандарт;
- нет WebSocket protocol;
- нет Redis Pub/Sub;
- PostgreSQL остаётся source of truth.

Минусы:

- backend нельзя запустить с несколькими workers;
- процессный restart разрывает streams;
- horizontal scaling невозможен без смены broadcaster.
