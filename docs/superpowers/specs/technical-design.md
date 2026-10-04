# Event Registration Service

## 1. Цель

За 6 дней реализовать рабочий клиент-серверный сервис регистрации на мероприятия.

Обязательные возможности:

- аккаунт по email/password;
- создание и публикация события;
- лимит мест;
- регистрация и отказ;
- FIFO waitlist;
- автоматическое повышение из waitlist;
- корректная конкуренция за последнее место;
- билет с кодом;
- одноразовый check-in;
- live-статистика;
- одно reminder за сутки;
- email при переносе события.

---

# 2. Архитектура

```text
Browser
  │
  ├── REST
  └── SSE
  │
Nginx
  │
  ├── /      → React
  └── /api   → FastAPI
                 │
                 ├── PostgreSQL
                 └── Redis → Celery → SMTP
```

Используется modular monolith:

```text
backend/app/
├── auth/
├── events/
├── registrations/
├── notifications/
├── db/
├── common/
└── main.py
```

Направление зависимостей:

```text
router
→ service/use-case
→ database/repository
```

Business rules не находятся непосредственно в router, Celery task или React component.

Production запускает **ровно один FastAPI/Uvicorn worker**:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Это обязательное ограничение MVP.

---

# 3. Стек

Backend:

- Python;
- FastAPI;
- Pydantic;
- SQLAlchemy 2.x sync;
- psycopg;
- Alembic;
- PostgreSQL;
- uv.

Frontend:

- React;
- TypeScript;
- Vite;
- MUI;
- React Router;
- TanStack Query;
- pnpm.

Infrastructure:

- Redis;
- Celery;
- Celery Beat;
- Nginx;
- Docker Compose;
- SMTP;
- Mailpit.

Quality:

- pytest;
- Ruff;
- mypy;
- ESLint;
- TypeScript;
- Vitest;
- React Testing Library;
- Playwright.

---

# 4. User

```text
User
----
id: UUID PK
email: varchar UNIQUE NOT NULL
password_hash: varchar NOT NULL
created_at: timestamptz NOT NULL
updated_at: timestamptz NOT NULL
```

Email нормализуется:

```text
trim + lowercase
```

Один User может одновременно быть organizer и participant.

Owner не может регистрироваться на своё Event.

---

# 5. Event

```text
Event
-----
id: UUID PK
owner_id: UUID FK User NOT NULL

title: varchar NOT NULL
description: text NOT NULL
slug: varchar UNIQUE NOT NULL

starts_at: timestamptz NOT NULL
ends_at: timestamptz NOT NULL
timezone: varchar NOT NULL

capacity: integer NOT NULL
status: EventStatus NOT NULL

schedule_updated_at: timestamptz NOT NULL

published_at: timestamptz NULL
cancelled_at: timestamptz NULL

created_at: timestamptz NOT NULL
updated_at: timestamptz NOT NULL
```

`EventStatus`:

```text
DRAFT
PUBLISHED
CANCELLED
```

DB constraints:

```text
CHECK capacity >= 1
CHECK ends_at > starts_at
```

`timezone` валидируется как IANA timezone через `zoneinfo.ZoneInfo`.

Effective FINISHED:

```text
status == PUBLISHED
AND now >= ends_at
→ FINISHED
```

Поэтому все операции «до окончания» используют:

```text
now < ends_at
```

---

# 6. Registration

```text
Registration
------------
id: UUID PK
event_id: UUID FK Event NOT NULL
user_id: UUID FK User NOT NULL

status: RegistrationStatus NOT NULL

confirmed_at: timestamptz NULL
waitlisted_at: timestamptz NULL
cancelled_at: timestamptz NULL

ticket_code: varchar UNIQUE NULL
ticket_issued_at: timestamptz NULL
checked_in_at: timestamptz NULL

confirmation_email_sent_at: timestamptz NULL
reminder_sent_at: timestamptz NULL

created_at: timestamptz NOT NULL
updated_at: timestamptz NOT NULL

UNIQUE(event_id, user_id)
```

Statuses:

```text
CONFIRMED
WAITLIST
CANCELLED
```

---

# 7. Registration invariants

## CONFIRMED

```text
confirmed_at IS NOT NULL
waitlisted_at IS NULL
cancelled_at IS NULL

ticket_code IS NOT NULL
ticket_issued_at IS NOT NULL
```

## WAITLIST

```text
confirmed_at IS NULL
waitlisted_at IS NOT NULL
cancelled_at IS NULL

ticket_code IS NULL
ticket_issued_at IS NULL
checked_in_at IS NULL
confirmation_email_sent_at IS NULL
reminder_sent_at IS NULL
```

## CANCELLED

```text
confirmed_at IS NULL
waitlisted_at IS NULL
cancelled_at IS NOT NULL

ticket_code IS NULL
ticket_issued_at IS NULL
checked_in_at IS NULL
confirmation_email_sent_at IS NULL
reminder_sent_at IS NULL
```

Эти состояния закрепляются PostgreSQL `CHECK` constraint.

Обязательные индексы:

```text
UNIQUE(event_id, user_id)
UNIQUE(ticket_code)
```

и:

```sql
CREATE INDEX ...
ON registrations(event_id, waitlisted_at, id)
WHERE status = 'WAITLIST';
```

FIFO:

```text
ORDER BY waitlisted_at ASC, id ASC
```

---

# 8. Event lifecycle

```text
DRAFT → PUBLISHED → effective FINISHED
             │
             └──→ CANCELLED
```

Publish разрешён только если:

```text
starts_at > now
ends_at > starts_at
capacity >= 1
valid IANA timezone
```

После `starts_at` запрещены:

- новая registration;
- cancellation registration;
- waitlist promotion;
- изменение capacity;
- изменение starts_at;
- изменение ends_at;
- изменение timezone.

Check-in разрешён только:

```text
starts_at - 2h <= now < ends_at
```

---

# 9. Изменение расписания

При изменении:

- `starts_at`;
- `ends_at`;
- `timezone`

устанавливается:

```text
schedule_updated_at = now
```

Для PUBLISHED Event новый:

```text
starts_at > now
```

обязателен.

Редактирование дат DRAFT не создаёт никаких email-задач.

При первой публикации:

```text
schedule_updated_at = published_at
```

---

# 10. Slug и удаление

Slug:

- глобально уникален;
- генерируется backend;
- lowercase;
- `a-z`, `0-9`, `-`;
- имеет random suffix;
- изменяем только в DRAFT;
- после publish immutable.

Event физически удаляется только если:

```text
status == DRAFT
AND registration_count == 0
```

иначе:

```text
409 EVENT_NOT_DELETABLE
```

---

# 11. Стратегия блокировок

Во всех use-case используется единый порядок:

```text
Event → Registration
```

Никогда наоборот.

| Операция | Event | Registration |
|---|---|---|
| Новая registration / reactivation | `FOR UPDATE` | существующая строка `FOR UPDATE`, если есть |
| Cancellation registration | `FOR UPDATE` | target `FOR UPDATE` |
| PATCH Event | `FOR UPDATE` | promoted WAITLIST rows `FOR UPDATE`, если capacity увеличен |
| Publish Event | `FOR UPDATE` | не требуется |
| Cancel Event | `FOR UPDATE` | не требуется: Event lock сериализует с check-in |
| Check-in | `FOR SHARE` | atomic `UPDATE` получает row lock |
| Confirmation/reminder email task | `FOR SHARE` | target `FOR UPDATE` |

`PATCH capacity`, publish и cancel никогда не изменяют Event без соответствующего Event lock.

Check-in и Event cancellation сериализуются потому, что:

```text
check-in → Event FOR SHARE
cancel event → Event FOR UPDATE
```

---

# 12. Регистрация и конкуренция

Registration разрешена:

```text
event.status == PUBLISHED
AND now < starts_at
AND current_user != owner
```

Под:

```sql
SELECT *
FROM events
WHERE id = :event_id
FOR UPDATE;
```

заново считается число CONFIRMED.

Есть место:

```text
→ CONFIRMED
→ новый ticket_code
→ confirmation_email_sent_at = NULL
→ reminder_sent_at = NULL
```

Нет места:

```text
→ WAITLIST
```

Повторная активная регистрация:

```text
409 ALREADY_REGISTERED
```

Инвариант:

```text
CONFIRMED <= capacity
```

Критический test:

```text
capacity = 1
2 concurrent requests
→ 1 CONFIRMED
→ 1 WAITLIST
```

---

# 13. fill_available_slots

Единый use-case:

```text
fill_available_slots(event)
```

Работает только:

```text
event.status == PUBLISHED
AND now < starts_at
```

Для DRAFT, CANCELLED или уже начавшегося Event:

```text
no-op
```

Под Event lock:

```text
free_slots = capacity - confirmed_count

первые N WAITLIST
→ Registration FOR UPDATE
→ CONFIRMED
→ confirmed_at = now
→ waitlisted_at = NULL
→ новый ticket_code
→ ticket_issued_at = now
→ confirmation_email_sent_at = NULL
→ reminder_sent_at = NULL
```

Вызывается:

- после cancellation CONFIRMED;
- после увеличения capacity.

---

# 14. Capacity

Увеличение capacity вызывает `fill_available_slots`.

Уменьшение разрешено только:

```text
new_capacity >= confirmed_count
```

иначе:

```text
409 CAPACITY_BELOW_CONFIRMED
```

После `starts_at` изменение capacity:

```text
409 EVENT_ALREADY_STARTED
```

---

# 15. Cancellation registration

В одной transaction:

```text
Event FOR UPDATE
→ Registration FOR UPDATE
```

Если Event:

```text
CANCELLED
→ 409 EVENT_CANCELLED

now >= ends_at
→ 409 EVENT_FINISHED

starts_at <= now < ends_at
→ 409 EVENT_ALREADY_STARTED
```

Если Registration отсутствует или уже `CANCELLED`:

```text
404 REGISTRATION_NOT_FOUND
```

Повторный DELETE поэтому возвращает 404.

## CONFIRMED

Под lock:

```text
checked_in_at IS NULL
```

иначе:

```text
409 TICKET_ALREADY_CHECKED_IN
```

После отмены:

```text
status = CANCELLED

confirmed_at = NULL
waitlisted_at = NULL
cancelled_at = now

ticket_code = NULL
ticket_issued_at = NULL
checked_in_at = NULL

confirmation_email_sent_at = NULL
reminder_sent_at = NULL

fill_available_slots()
```

## WAITLIST

```text
status = CANCELLED
waitlisted_at = NULL
cancelled_at = now

confirmation_email_sent_at = NULL
reminder_sent_at = NULL
```

---

# 16. Повторная регистрация

CANCELLED Registration переиспользуется.

Перед reactivation очищаются:

```text
confirmed_at
waitlisted_at
cancelled_at
ticket_code
ticket_issued_at
checked_in_at
confirmation_email_sent_at
reminder_sent_at
```

После этого создаётся новое валидное состояние.

CONFIRMED:

```text
confirmed_at = now
ticket_code = новый код
ticket_issued_at = now
```

WAITLIST:

```text
waitlisted_at = now
```

---

# 17. Ticket code

Алфавит:

```text
23456789ABCDEFGHJKMNPQRSTUVWXYZ
```

Не используются:

```text
0 1 I L O
```

Храним:

```text
7K4P9Q2M8RTA
```

Показываем:

```text
7K4P-9Q2M-8RTA
```

Нормализация:

```text
trim
uppercase
remove spaces
remove "-"
```

Другие символы → `422`.

Код глобально уникален.

---

# 18. Check-in

Только owner Event.

В одной transaction:

1. `Event FOR SHARE`;
2. проверить owner/status/time;
3. выполнить atomic Registration UPDATE.

Event errors:

```text
CANCELLED
→ 409 EVENT_CANCELLED

now >= ends_at
→ 409 EVENT_FINISHED

now < starts_at - 2h
→ 409 CHECKIN_NOT_OPEN
```

Успешное окно:

```text
starts_at - 2h <= now < ends_at
```

Atomic update:

```sql
UPDATE registrations
SET checked_in_at = :now
WHERE event_id = :event_id
  AND ticket_code = :normalized_code
  AND status = 'CONFIRMED'
  AND checked_in_at IS NULL
RETURNING ...;
```

Первый check-in:

```text
200
```

Повторный:

```text
409 TICKET_ALREADY_CHECKED_IN
```

Неизвестный код или код другого Event:

```text
404 TICKET_NOT_FOUND
```

Cancellation/check-in race:

```text
check-in раньше
→ Registration row locked/updated
→ cancellation ждёт
→ затем видит checked_in_at
→ 409

cancellation раньше
→ Registration становится CANCELLED
→ check-in UPDATE затрагивает 0 rows
```

Оба действия успешно завершиться не могут.

---

# 19. Confirmation email scanner

Beat каждые 5 минут ищет:

```text
Registration.status = CONFIRMED
confirmation_email_sent_at IS NULL

Event.status = PUBLISHED
now < Event.starts_at
```

Scanner только ставит Celery task.

## Confirmation email task

Task начинает новую transaction:

```text
Event FOR SHARE
→ Registration FOR UPDATE
```

Затем повторно проверяет:

```text
Event.status == PUBLISHED
now < starts_at

Registration.status == CONFIRMED
confirmation_email_sent_at IS NULL
ticket_code IS NOT NULL
```

Email, Event data и `ticket_code` читаются **после получения этих lock**.

### MVP locking decision

Transaction и Registration row lock **удерживаются на время SMTP-вызова**.

Это сознательный компромисс MVP:

- cancellation/check-in могут подождать несколько секунд;
- зато email не отправляется по уже изменённому состоянию между recheck и SMTP.

После успешного SMTP:

```text
confirmation_email_sent_at = now
COMMIT
```

При ошибке SMTP transaction откатывается или завершается без установки `*_sent_at`.

Следующий scanner повторит попытку.

---

# 20. Reminder scanner

Beat каждые 5 минут ищет:

```text
Registration.status = CONFIRMED
reminder_sent_at IS NULL

Event.status = PUBLISHED

confirmed_at <= starts_at - 24h
schedule_updated_at <= starts_at - 24h

starts_at <= now + 24h
now < starts_at
```

Event, впервые опубликованный менее чем за 24 часа до начала, reminder никому не создаёт.

Scanner только ставит Celery task.

## Reminder email task

В новой transaction:

```text
Event FOR SHARE
→ Registration FOR UPDATE
```

Повторно проверяются все условия scanner:

```text
Event.status == PUBLISHED
now < starts_at

Registration.status == CONFIRMED
reminder_sent_at IS NULL

confirmed_at <= starts_at - 24h
schedule_updated_at <= starts_at - 24h
```

Актуальные Event/Registration данные читаются под lock.

Transaction/Registration lock удерживаются во время SMTP.

После success:

```text
reminder_sent_at = now
COMMIT
```

---

# 21. Retry email

Для reminder нет Celery automatic retry.

Retry происходит только:

```text
следующий Beat scan
```

пока:

```text
Event.status == PUBLISHED
AND now < starts_at
```

То же scanner-based recovery используется для confirmation email.

Сознательно принимается редкий риск:

```text
SMTP принял письмо
→ процесс упал до *_sent_at
→ следующий scan может отправить duplicate
```

Это допустимый риск MVP Lite.

---

# 22. Reminder после re-registration и reschedule

Cancellation и reactivation очищают:

```text
reminder_sent_at = NULL
```

Поэтому новая регистрационная попытка получает собственный reminder при выполнении правил.

При изменении расписания:

```text
schedule_updated_at = now
```

Если новое событие начинается менее чем через 24 часа:

```text
schedule_updated_at > starts_at - 24h
```

нового reminder нет.

Если reminder **уже был отправлен до переноса**, `reminder_sent_at` не очищается — даже если новая дата дальше чем через 24 часа.

То есть после одного отправленного reminder последующий reschedule **не создаёт второй reminder**.

Письмо `EVENT_RESCHEDULED` считается актуальным уведомлением.

Это осознанное правило MVP Lite.

---

# 23. Reschedule / cancellation email

При изменении расписания PUBLISHED Event уведомляются:

- CONFIRMED;
- WAITLIST.

При Event cancellation:

- CONFIRMED;
- WAITLIST.

Эти задачи ставятся в Celery после commit.

Осознанный Lite-risk:

```text
DB commit
→ процесс/Redis падает до enqueue
→ reschedule/cancellation email может потеряться
```

Confirmation и promotion email защищены scanner-механизмом.

---

# 24. Auth

Password:

```text
Argon2id
12–128 characters
```

JWT:

```text
access: 15 min
refresh: 30 days
```

Оба — HttpOnly cookies.

Refresh server-side не хранится.

Невалидный/expired refresh:

```text
401 AUTH_REFRESH_INVALID
```

Logout очищает cookies.

---

# 25. CSRF и Origin

Double-submit CSRF.

```text
GET /api/auth/csrf
```

доступен без auth.

Unsafe requests:

```text
POST
PUT
PATCH
DELETE
```

проходят:

1. CSRF cookie/header comparison;
2. exact Origin validation against configured application origin.

Login/register/refresh/logout тоже защищены.

Ошибка:

```text
403 CSRF_INVALID
```

---

# 26. Login brute-force

Application Redis limiter отсутствует.

Nginx использует `limit_req` для:

```text
/api/auth/login
```

MVP baseline:

```text
10 requests/minute/IP
```

с небольшим burst.

---

# 27. SSE

MVP использует:

```text
1 FastAPI worker
+
in-memory broadcaster
```

`stats_changed` публикуется **после commit** при:

- новой registration;
- registration cancellation;
- waitlist promotion;
- capacity update;
- check-in.

SSE передаёт только сигнал.

Frontend после сигнала refetches:

```text
GET /api/events/{event_id}/stats
```

---

# 28. SSE thread-safety

Sync endpoints/SQLAlchemy работают в threadpool.

Sync code не пишет напрямую в `asyncio.Queue`.

Broadcaster использует:

```text
loop.call_soon_threadsafe(...)
```

или эквивалентный thread-safe mechanism.

---

# 29. SSE auth и refresh

```text
GET /api/events/{event_id}/stats/stream
```

проверяет:

- access cookie;
- Event ownership.

CSRF не требуется.

После auth DB session закрывается. Stream не держит PostgreSQL connection.

Текущий stream может жить дольше access-token TTL.

Если соединение оборвалось и reconnect не удался из-за expired access cookie, frontend обязан:

```text
1. закрыть старый EventSource
2. POST /api/auth/refresh
3. при успехе создать новый EventSource
4. refetch GET /stats
5. если refresh → 401, перейти к login
```

Для нативного `EventSource`, который не даёт удобного доступа к HTTP status в `onerror`, frontend при failed reconnect выполняет refresh attempt перед новым подключением.

---

# 30. Nginx

Обязательно:

```text
proxy_buffering off
```

для SSE.

Также на SSE route задаётся увеличенный:

```text
proxy_read_timeout
```

и heartbeat примерно раз в 15 секунд.

Login route использует `limit_req`.

---

# 31. Statistics

SQL вычисляет:

```text
capacity
confirmed
waitlist
checked_in
available_slots
```

Mutable counters в Event отсутствуют.

---

# 32. Error contract

```json
{
  "error": {
    "code": "ALREADY_REGISTERED",
    "message": "User is already registered.",
    "details": {}
  }
}
```

Frontend принимает решения по `error.code`.

Основные codes:

```text
AUTH_INVALID_CREDENTIALS
AUTH_REFRESH_INVALID
AUTH_REQUIRED
EMAIL_ALREADY_REGISTERED
CSRF_INVALID

EVENT_NOT_FOUND
EVENT_NOT_OWNER
EVENT_NOT_PUBLISHABLE
EVENT_CANCELLED
EVENT_ALREADY_STARTED
EVENT_FINISHED
EVENT_NOT_DELETABLE
CAPACITY_BELOW_CONFIRMED
OWNER_CANNOT_REGISTER

ALREADY_REGISTERED
REGISTRATION_NOT_FOUND

TICKET_NOT_FOUND
TICKET_ALREADY_CHECKED_IN
CHECKIN_NOT_OPEN
```

---

# 33. Endpoint/error mapping

## DELETE `/api/events/{event_id}/registration`

```text
no Registration / already CANCELLED
→ 404 REGISTRATION_NOT_FOUND

Event CANCELLED
→ 409 EVENT_CANCELLED

starts_at <= now < ends_at
→ 409 EVENT_ALREADY_STARTED

now >= ends_at
→ 409 EVENT_FINISHED

checked_in_at != NULL
→ 409 TICKET_ALREADY_CHECKED_IN

success
→ 200 RegistrationResponse(status=CANCELLED)
```

## POST `/api/events/{event_id}/check-ins`

```text
Event not owned
→ 403 EVENT_NOT_OWNER

Event CANCELLED
→ 409 EVENT_CANCELLED

now >= ends_at
→ 409 EVENT_FINISHED

now < starts_at - 2h
→ 409 CHECKIN_NOT_OPEN

code missing / another Event
→ 404 TICKET_NOT_FOUND

already checked in
→ 409 TICKET_ALREADY_CHECKED_IN

success
→ 200 CheckInResponse
```

---

# 34. API

Auth:

```text
GET  /api/auth/csrf
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
GET  /api/auth/me
```

Events:

```text
POST   /api/events
GET    /api/events/mine
GET    /api/events/{event_id}
PATCH  /api/events/{event_id}
POST   /api/events/{event_id}/publish
POST   /api/events/{event_id}/cancel
DELETE /api/events/{event_id}
```

Public:

```text
GET /api/public/events/{slug}
```

Registration:

```text
POST   /api/events/{event_id}/registrations
DELETE /api/events/{event_id}/registration
GET    /api/events/{event_id}/my-registration
GET    /api/me/registrations
```

Organizer:

```text
GET  /api/events/{event_id}/registrations
POST /api/events/{event_id}/check-ins
GET  /api/events/{event_id}/stats
GET  /api/events/{event_id}/stats/stream
```

Participants list:

```text
?page=1&page_size=50
```

Rules:

```text
page >= 1
1 <= page_size <= 100
```

---

# 35. Response schemas

## RegistrationResponse

```json
{
  "id": "uuid",
  "event_id": "uuid",
  "user_id": "uuid",
  "status": "CONFIRMED",
  "confirmed_at": "2026-10-10T12:00:00Z",
  "waitlisted_at": null,
  "cancelled_at": null,
  "waitlist_position": null,
  "ticket_code": "7K4P-9Q2M-8RTA",
  "checked_in_at": null
}
```

## CheckInResponse

```json
{
  "status": "checked_in",
  "registration_id": "uuid",
  "event_id": "uuid",
  "ticket_code": "7K4P-9Q2M-8RTA",
  "checked_in_at": "2026-10-10T12:32:10Z",
  "participant": {
    "user_id": "uuid",
    "email": "participant@example.com"
  }
}
```

## StatsResponse

```json
{
  "event_id": "uuid",
  "capacity": 100,
  "confirmed": 87,
  "waitlist": 12,
  "checked_in": 54,
  "available_slots": 13
}
```

---

# 36. Frontend routes

```text
/login
/register

/events/:slug

/me/registrations

/organizer/events
/organizer/events/new
/organizer/events/:eventId
/organizer/events/:eventId/edit
/organizer/events/:eventId/check-in
```

---

# 37. Clock

Вся business logic получает время через единый:

```text
Clock
```

Например:

```python
clock.now()
```

Прямые:

```python
datetime.now()
datetime.utcnow()
```

в application/domain logic запрещены.

Boundary tests не используют `sleep()`.

---

# 38. Критические тесты

Обязательно:

1. duplicate registration;
2. concurrent last seat;
3. FIFO promotion;
4. capacity increase promotion;
5. capacity decrease below confirmed;
6. capacity change after starts_at;
7. WAITLIST cancellation;
8. cancellation vs check-in race;
9. re-registration resets email/reminder/ticket state;
10. new ticket after re-registration;
11. check-in only owner;
12. code from another Event → 404;
13. duplicate parallel check-in;
14. `now == ends_at` → EVENT_FINISHED;
15. confirmation scanner excludes CANCELLED/DRAFT Event;
16. confirmation task rechecks state under locks;
17. reminder scanner excludes CANCELLED/DRAFT Event;
18. reminder task rechecks state under locks;
19. scanners recover unsent mail;
20. late confirmation <24h no reminder;
21. publish <24h before start → no reminders;
22. reschedule <24h → no immediate reminder;
23. reminder already sent + later reschedule → no second reminder;
24. reschedule requires future starts_at;
25. DRAFT schedule edit sends no mail;
26. delete only DRAFT without registrations;
27. IANA timezone validation;
28. DB CHECK rejects invalid Registration state;
29. SSE signal after register/cancel/promotion/capacity/check-in;
30. SSE reconnect refresh flow at frontend level.

---

# 39. Осознанные ограничения

Не входят:

- transactional outbox;
- separate Ticket table;
- ticket history;
- server-side refresh sessions;
- refresh reuse detection;
- Redis Pub/Sub;
- multi-process SSE;
- application rate limiter;
- guaranteed reschedule/cancellation delivery;
- SMTP physical exactly-once;
- QR/PDF;
- admin panel;
- microservices.