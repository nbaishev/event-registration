# Task 08: регистрация участника, билет и список ожидания

Участник регистрируется с публичной страницы и после reload видит сохранённый CONFIRMED с билетом либо WAITLIST с позицией. При capacity=1 два конкурентных участника получают ровно одно подтверждение и одно место в очереди.

Plan: [08-2026-10-06-event-registration.md](../superpowers/plans/08-2026-10-06-event-registration.md).

- Migration 0003: registrations, FK, уникальные event/user и ticket, CHECK всех state invariants, partial FIFO index.
- POST `/api/events/{event_id}/registrations` и GET `/api/events/{event_id}/my-registration`; ErrorResponse/no-store, generated OpenAPI types.
- Event → Registration locking, SQL confirmed count, CANCELLED row reuse, bounded unique-ticket savepoint retry без освобождения Event lock; response snapshot до commit.
- Public participant panel с независимыми queries, explicit auth opt-in, защитой от запоздалого own GET и удалением private data после failed refresh.

Verification: `make verify` exit 0; 332 backend tests, 83 frontend tests, 15 Playwright E2E; migration upgrade/head/metadata drift passed; OpenAPI drift none; production frontend и Docker builds passed. Baseline `make check`/`make test` exit 0. Независимое review — actionable findings отсутствуют; staged secrets review completed.

Screenshots:

- [CONFIRMED](https://github.com/nbaishev/event-registration/blob/feat/event-registration/docs/screenshots/registration-confirmed.png)
- [WAITLIST](https://github.com/nbaishev/event-registration/blob/feat/event-registration/docs/screenshots/registration-waitlist.png)

Scope limitations: отмена, promotion, capacity PATCH, check-in, email и SSE относятся к следующим задачам; Day 3 целиком данным PR не закрывается.
