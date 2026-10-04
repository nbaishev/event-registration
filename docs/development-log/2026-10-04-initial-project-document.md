# Initial Project Documents

**Date:** 2026-10-04  
**Stage:** Pre-development / project initialization  
**Status:** Approved

**Started at:** exact timestamp was not recorded  
**Finished at:** exact timestamp was not recorded

> Этот log создаётся по итогам pre-development design discussion. Точное время отдельных предыдущих сообщений не реконструировалось. С момента создания repository все implementation logs обязаны содержать фактические ISO 8601 timestamps.

---

## Purpose

Этот документ фиксирует решения, принятые **до начала реализации** Event Registration Service.

Код приложения на этом этапе ещё не создавался.

Цель:

- уточнить требования;
- выбрать архитектуру;
- определить scope;
- установить правила AI-assisted development;
- определить документацию;
- подготовить доказуемую историю принятия решений.

Полный transcript предварительного обсуждения в repository не включается.

Вместо него сохраняются Product Spec, ADR, implementation plans и development logs.

---

## Submission requirements received

До начала implementation были зафиксированы требования к форме сдачи.

Результат должен включать:

1. ссылку на GitHub repository;
2. сведения об использованных AI tools и models и краткое обоснование выбора;
3. prompts, agent-session export либо decision/development logs;
4. доказательство постепенного хода работы во времени;
5. описание проекта и deployment instructions;
6. фактическое состояние проекта;
7. описание следующей итерации;
8. сведения об использованных external solutions, templates и generators.

Принято решение **не использовать полный session export как основной артефакт**.

Вместо него проект будет содержать структурированные development logs и ADR.

---

## AI tools used at this stage

Pre-development architecture/design:

```text
Tool: ChatGPT
Model: GPT-5.6 Sol
```

Использовался для:

- анализа требований;
- сравнения архитектурных вариантов;
- review спецификации;
- определения scope;
- подготовки initial documentation.

Implementation предполагается выполнять через Codex непосредственно в repository.

Фактическая Codex model должна быть записана позднее в `docs/submission.md`; заранее она не предполагается.

---

## Design principle

Основной принцип MVP:

```text
сохранять сложность, необходимую для корректности задания,
и удалять production-hardening,
который не требуется для MVP
```

---

## Approved architecture

```text
React
  ↓
Nginx
  ↓
FastAPI
  ↓
PostgreSQL

FastAPI / Celery
  ↓
Redis
  ↓
SMTP
```

Выбран modular monolith.

Backend и frontend находятся в одном monorepo, но являются отдельными приложениями.

Microservices отклонены как неоправданная сложность для текущего scope.

---

## Key approved decisions

Сохранены как обязательные:

- PostgreSQL как source of truth;
- `SELECT ... FOR UPDATE` для capacity/concurrency;
- FIFO waitlist;
- единый `fill_available_slots`;
- atomic conditional check-in;
- deterministic `Clock`;
- real PostgreSQL concurrency tests;
- HttpOnly JWT cookies;
- CSRF + Origin validation;
- SSE для live dashboard;
- risk-based TDD;
- `make check` для обычной работы;
- `make verify` перед Pull Request.

---

## MVP exclusions

Сознательно исключены:

- transactional outbox;
- отдельная Ticket table;
- ticket history;
- EmailDelivery subsystem;
- RefreshSession storage;
- refresh reuse detection;
- Redis Pub/Sub;
- multi-worker SSE;
- application-level rate limiter;
- Redux;
- microservices;
- QR/PDF;
- admin panel.

Эти пункты не являются забытыми requirements.

---

## Development approach

Выбран vertical-slice подход.

```text
business behavior
→ database
→ backend
→ API contract
→ frontend
→ verification
→ Pull Request
```

Детальная декомпозиция создаётся непосредственно в Codex на основании фактического состояния repository.

---

## Evidence of gradual work

После создания repository каждая implementation task должна иметь:

```text
Started at
Timeline
Verification timestamps
Finished at
```

Git commits также создаются постепенно по мере завершения осмысленных изменений.

Агенту запрещено:

- собирать всю историю одним финальным commit без причины;
- искусственно менять commit timestamps;
- придумывать timestamps в development logs.

---

## Documentation structure

```text
/
├── AGENTS.md
└── docs/
    ├── agent-rules/
    │   ├── engineering.md
    │   └── development-log.md
    ├── adr/
    ├── development-log/
    ├── development-process.md
    ├── submission.md
    └── superpowers/
        ├── specs/
        └── plans/
```

Responsibilities:

```text
Product Spec
→ что строим

AGENTS.md
→ обязательные правила агента

engineering.md
→ технические правила

development-log.md
→ правила журналирования и evidence

development-process.md
→ lifecycle и milestones

ADR
→ почему принято архитектурное решение

development-log/*
→ как реально шла работа

submission.md
→ карта финальной сдачи
```

---

## Initial documents approved

До implementation утверждены:

```text
AGENTS.md

docs/agent-rules/engineering.md
docs/agent-rules/development-log.md

docs/development-process.md
docs/submission.md

docs/superpowers/specs/technical-design.md

docs/development-log/2026-10-04-initial-project-document.md
```

---

## Result

Pre-development design stage завершён.

Подготовлены:

- Product Spec;
- agent rules;
- engineering rules;
- development-log policy;
- development process;
- initial decision history;
- submission structure.

Следующий этап:

```text
create GitHub repository
→ commit initial documents
→ record real timestamp
→ open repository in Codex
→ decompose Day 1 milestone
→ review decomposition
→ approve first task
→ create implementation plan
→ implementation
```