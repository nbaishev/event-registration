# ADR-001: Modular Monolith, Monorepo и основной стек

**File:** `docs/adr/001-architecture-and-stack.md`  
**Status:** Accepted  
**Date:** 2026-10-04

## Context

Необходимо за шесть дней реализовать клиент-серверный MVP сервиса регистрации на мероприятия.

Система включает:

- аккаунты пользователей;
- создание мероприятий;
- регистрацию и waitlist;
- конкурентное распределение мест;
- билеты и check-in;
- email notifications;
- live dashboard организатора.

Главные ограничения:

- короткий срок разработки;
- один небольшой продукт;
- тесно связанные транзакционные сценарии;
- необходимость понятного deployment;
- разработка преимущественно с помощью AI-агента под human review.

## Considered options

### 1. Microservices

Отдельные сервисы для:

- authentication;
- events;
- registrations;
- notifications.

### 2. Несколько отдельных приложений

Frontend, backend и infrastructure находятся в разных папках.

### 3. Modular monolith в monorepo

Один backend с внутренними domain modules и отдельное React-приложение в одном repository.

## Decision

Использовать **modular monolith в monorepo**.

Основной стек:

### Backend

- Python;
- FastAPI;
- SQLAlchemy 2.x;
- psycopg;
- Alembic;
- PostgreSQL;
- uv.

### Frontend

- React;
- TypeScript;
- Vite;
- MUI;
- React Router;
- TanStack Query;
- pnpm.

### Infrastructure

- Docker Compose;
- Nginx;
- Redis;
- Celery;
- Celery Beat;
- SMTP;
- Mailpit для local development.

Backend модули организуются по feature/domain:

```text
auth/
events/
registrations/
notifications/
```

Основное направление зависимостей:

```text
router
→ service/use-case
→ repository/database
```

## Why

Modular monolith обеспечивает достаточно хорошие границы между domain areas, но не требует:

- service discovery;
- distributed transactions;
- нескольких deployments;
- межсервисной authentication;
- отдельного observability stack.

Monorepo упрощает:

- синхронное изменение OpenAPI и frontend;
- Docker Compose;
- CI;
- работу AI-агента с полным контекстом проекта;
- review одного vertical slice.

FastAPI выбран как небольшой Python web framework с автоматическим OpenAPI.

React + TypeScript позволяют отделить browser UI от backend и использовать generated API types.

PostgreSQL нужен не только для хранения данных, но и для transaction/locking guarantees.

## Consequences

Плюсы:

- быстрый старт;
- простая deployment topology;
- одна транзакционная граница backend;
- удобные vertical slices;
- меньше инфраструктурных компонентов;
- весь проект доступен агенту в одном repository.

Минусы:

- backend масштабируется как единое приложение;
- необходимо дисциплинированно соблюдать module boundaries;
- при значительном росте системы отдельные модули позднее могут потребовать выделения.

## Rejected

Microservices отклонены как неоправданная сложность для шестидневного MVP.

Separate repositories отклонены, поскольку усложняют синхронизацию API, CI и AI-assisted development.