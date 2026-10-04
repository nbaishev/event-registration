# ADR-003: JWT в HttpOnly cookies, CSRF и Origin validation

**File:** `docs/adr/003-authentication-security-model.md`  
**Status:** Accepted  
**Date:** 2026-10-04

## Context

MVP требует полноценные пользовательские аккаунты по email/password.

Frontend и backend работают через один origin:

```text
/     → React
/api/ → FastAPI
```

Необходимо выбрать authentication scheme, который:

- достаточно безопасен для MVP;
- не требует сложной session infrastructure;
- подходит React frontend;
- позволяет иметь access/refresh flow.

## Considered options

### 1. JWT в localStorage

Frontend самостоятельно добавляет Bearer token.

### 2. Server-side sessions

Opaque session ID + session storage в PostgreSQL/Redis.

### 3. JWT в HttpOnly cookies

Access и refresh JWT автоматически передаются browser.

## Decision

Использовать:

- password hashing через Argon2id;
- access JWT — 15 минут;
- refresh JWT — 30 дней;
- оба token передаются через HttpOnly cookies;
- double-submit CSRF;
- exact `Origin` validation для unsafe requests.

JWT не хранится в:

```text
localStorage
sessionStorage
```

Server-side `RefreshSession` table в MVP отсутствует.

Invalid/expired refresh возвращает:

```text
401 AUTH_REFRESH_INVALID
```

## Why

HttpOnly cookies уменьшают доступ JavaScript-кода к authentication tokens.

Cookie authentication требует отдельной CSRF защиты, поэтому используются два механизма:

```text
double-submit CSRF
+
Origin validation
```

Stateless refresh JWT уменьшает количество infrastructure/state, необходимое для MVP.

## Consequences

Плюсы:

- tokens недоступны обычному frontend JavaScript;
- same-origin deployment упрощает cookie configuration;
- нет отдельного session store;
- frontend authentication flow остаётся относительно простым.

Минусы:

- refresh token невозможно централизованно отозвать до expiration;
- отсутствует refresh-token reuse detection;
- compromise refresh token имеет более серьёзные последствия, чем при server-side rotation.

## Additional mitigation

Login brute-force protection выполняется на уровне Nginx через:

```text
limit_req
```

Application Redis rate limiter не вводится.
