# AGENTS.md

## Required reading

Перед implementation task прочитай:

1. текущий approved implementation plan;
2. только spec/ADR sections, на которые прямо ссылается plan;
3. только релевантные sections `docs/agent-rules/engineering.md`.

Не сканируй целиком `docs/superpowers/specs/`, `docs/adr/`,
предыдущие development logs или весь repository без конкретной необходимости.

Если plan уже содержит достаточный contract задачи, используй его как основной
execution context и обращайся к Product Spec только для разрешения неоднозначности.

В рамках задачи не перечитывай уже прочитанные документы, пока они не изменились
или не возникла конкретная неоднозначность. При необходимости читай только нужный раздел.

Для консультаций и review без изменения файлов не запускай implementation workflow:
baseline tests, создание worktree и development log не требуются.

Правила вывода команд и повторных проверок находятся в
`docs/agent-rules/engineering.md`, формат журнала — в
`docs/agent-rules/development-log.md`.

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

## Context disciplin
- не читать весь spec/repository без необходимости;
- не перечитывать неизменившиеся файлы;
- большие существующие файлы менять patch/edit, а не переписывать целиком;
- reviewer сам читает git diff, не передавать ему весь source tree;
- successful logs → только summary;
- speculative edge cases вне acceptance criteria → follow-up, а не автоматическая реализация;
- make verify не запускать во время обычного development loop.

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
