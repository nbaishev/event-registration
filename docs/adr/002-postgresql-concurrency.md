# ADR-002: PostgreSQL как источник истины и механизм конкурентности

**File:** `docs/adr/002-postgresql-concurrency.md`  
**Status:** Accepted  
**Date:** 2026-10-04

## Context

Критическое требование системы:

```text
capacity = 1

два пользователя одновременно регистрируются

→ ровно один CONFIRMED
→ второй WAITLIST
```

Также необходимо безопасно выполнять:

- cancellation;
- waitlist promotion;
- увеличение capacity;
- check-in;
- одновременный check-in/cancellation.

Application-level проверки вида:

```text
if confirmed_count < capacity:
    confirm()
```

не обеспечивают корректность при конкурентных запросах.

## Considered options

### 1. Проверки только в application code

Сначала читать количество участников, затем создавать Registration.

### 2. Redis distributed locks

Создавать lock на Event в Redis.

### 3. PostgreSQL row-level locking

Использовать transactions и `SELECT ... FOR UPDATE` / `FOR SHARE`.

## Decision

PostgreSQL является **единственным источником истины** для:

- Event state;
- capacity;
- Registration;
- waitlist;
- ticket/check-in state;
- notification sent flags.

Seat allocation использует:

```sql
SELECT ...
FROM events
WHERE id = :event_id
FOR UPDATE;
```

Единый lock ordering:

```text
Event
→ Registration
```

Никогда наоборот.

Ключевые правила:

```text
register/reactivate
→ Event FOR UPDATE
→ Registration FOR UPDATE when applicable

cancel registration
→ Event FOR UPDATE
→ Registration FOR UPDATE

PATCH Event
→ Event FOR UPDATE

cancel Event
→ Event FOR UPDATE

check-in
→ Event FOR SHARE
→ conditional Registration UPDATE
```

Redis не используется для business locking.

## Why

PostgreSQL уже хранит данные, участвующие в инвариантах.

Использование его же transaction/locking mechanisms:

- не создаёт второй источник координации;
- обеспечивает атомарность изменения данных;
- предотвращает oversubscription;
- упрощает failure model;
- позволяет проверять поведение обычными integration tests.

Redis lock потребовал бы синхронизации между:

```text
Redis lock state
+
PostgreSQL transaction state
```

что для MVP не даёт практической пользы.

## Consequences

Плюсы:

- `CONFIRMED <= capacity` можно гарантировать транзакционно;
- FIFO promotion работает на актуальном состоянии;
- нет distributed locking subsystem;
- меньше race conditions.

Минусы:

- конкурентные операции на одном Event сериализуются;
- требуется внимательно соблюдать единый lock order;
- SQLite не подходит для доказательства этих гарантий.

## Testing consequence

Concurrency tests должны выполняться на **реальном PostgreSQL**.

Критический обязательный тест:

```text
capacity = 1
+
2 parallel registrations
→ exactly 1 CONFIRMED
→ exactly 1 WAITLIST
```

## Rejected

Application-only locking отклонён из-за race conditions.

Redis distributed lock отклонён как лишний механизм координации при наличии PostgreSQL transaction locking.