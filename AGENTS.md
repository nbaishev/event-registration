# AGENTS.md

## Required reading

Перед любой implementation task прочитай:

1. `docs/superpowers/specs/` — утверждённые требования продукта;
2. `docs/superpowers/plans/<current-task>.md` — утверждённый plan задачи;
3. `docs/agent-rules/engineering.md` — технические правила реализации;
4. `docs/agent-rules/development-log.md` — правила журнала разработки.

Процесс постановки задач, worktree и PR описан в:

```text
docs/development-process.md
```

---

## Before coding

Перед изменением кода:

1. проверь текущую branch/worktree;
2. запусти baseline tests, относящиеся к задаче;
3. сообщи о существующих failures;
4. создай development log задачи;
5. не выходи за утверждённый scope.

---

## Source of truth

При конфликте действует порядок:

```text
Product Spec
↓
approved Implementation Plan
↓
AGENTS.md / docs/agent-rules/
↓
существующая реализация
```

Не угадывай решение при конфликте.

Зафиксируй конфликт в development log и останови соответствующую часть реализации до уточнения.

---

## Development loop

Для обычной работы используй:

```bash
make check
```

Для TDD-задач соблюдай:

```text
RED → GREEN → REFACTOR
```

Полный:

```bash
make verify
```

запускается **перед готовностью задачи к Pull Request**, а не после каждого изменения.

---

## Completion

Нельзя заявлять:

```text
готово
fixed
PR ready
all tests pass
```

до успешного `make verify`.

Перед PR:

- обнови development log;
- зафиксируй фактически выполненные проверки;
- укажи известные ограничения;
- проверь staged diff на secrets.

---

## Scope discipline

Без отдельного approved architecture change не добавлять:

- transactional outbox;
- отдельную Ticket table;
- RefreshSession;
- Redis Pub/Sub;
- application-level rate limiter;
- Redux;
- microservices;
- unrelated refactoring.

---

## Documentation ownership

```text
Product requirements
→ docs/superpowers/specs/

Implementation plans
→ docs/superpowers/plans/

Engineering rules
→ docs/agent-rules/engineering.md

Development-log rules
→ docs/agent-rules/development-log.md

Architecture decisions
→ docs/adr/

Task history and important prompts
→ docs/development-log/

Development lifecycle
→ docs/development-process.md
```

Не дублируй одно и то же правило в нескольких документах.