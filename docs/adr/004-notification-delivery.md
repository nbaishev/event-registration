# ADR-004: Упрощённая надёжность email без Transactional Outbox

**File:** `docs/adr/004-notification-delivery.md`  
**Status:** Accepted  
**Date:** 2026-10-04

## Context

Система должна отправлять:

- confirmation/ticket email;
- promotion email;
- reminder;
- reschedule email;
- event cancellation email.

Первоначально рассматривалась production-grade схема:

```text
DB transaction
→ transactional outbox
→ dispatcher
→ delivery state/retry
→ SMTP
```

Она обеспечивает более сильную надёжность, но существенно увеличивает объём MVP.

## Considered options

### 1. Отправлять email прямо из HTTP request

### 2. Celery task после commit

### 3. Transactional Outbox + EmailDelivery state machine

### 4. Гибридный Lite-подход

Celery + DB scanner для наиболее критичных писем.

## Decision

Использовать гибридный **MVP notification model**.

### Confirmation / promotion

В `Registration` хранится:

```text
confirmation_email_sent_at
```

Celery Beat scanner периодически ищет:

```text
Registration.status = CONFIRMED
confirmation_email_sent_at IS NULL
Event.status = PUBLISHED
now < starts_at
```

и создаёт delivery task.

### Reminder

Используется:

```text
reminder_sent_at
```

и аналогичный Beat scanner.

### Delivery task

Перед SMTP task повторно проверяет текущее состояние:

```text
Event FOR SHARE
→ Registration FOR UPDATE
→ state recheck
→ read current data
→ SMTP
→ set *_sent_at
→ commit
```

Для MVP row lock удерживается на время SMTP.

### Reschedule / cancellation

Эти письма ставятся в Celery после успешного DB commit без outbox.

## Why

Confirmation/ticket и reminder непосредственно связаны с обязательными требованиями задания.

Для них scanner + `*_sent_at` даёт дешёвый recovery mechanism.

Transactional outbox потребовал бы:

- новую таблицу;
- dispatcher;
- delivery state machine;
- additional retry logic;
- cleanup/monitoring.

Это непропорционально шестидневному MVP.

## Known risk

Для reschedule/cancellation:

```text
DB commit
→ process or Redis failure before enqueue
→ notification may be lost
```

Этот риск сознательно принят.

Также существует редкий ambiguity:

```text
SMTP accepted email
→ process crashed before *_sent_at commit
→ scanner may send duplicate
```

Physical SMTP exactly-once не гарантируется.

## Reminder decision

После одного успешно отправленного reminder перенос события **не создаёт второй reminder**.

Event, опубликованный менее чем за 24 часа до начала, отдельный reminder не создаёт.

Participant, подтверждённый менее чем за 24 часа, также не получает отдельного reminder.
