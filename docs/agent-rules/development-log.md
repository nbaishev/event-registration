# Development Log Rules

Для каждой implementation task создаётся:

```text
docs/development-log/YYYY-MM-DD-<task-name>.md
```

Файл создаётся **до начала реализации** и обновляется по ходу работы.

Development log — краткий проверяемый журнал работы, а не полный transcript чата.

Журнал вести на русском языке. Команды, фактический вывод инструментов, идентификаторы
и дословные исходные запросы сохранять без перевода.

---

## 1. Time tracking

Каждый task log должен содержать реальные временные метки.

В начале задачи зафиксировать:

```markdown
Started at: 2026-10-05T09:14:23+06:00
```

В конце:

```markdown
Finished at: 2026-10-05T11:47:10+06:00
```

Использовать ISO 8601 с timezone offset.

Получать время из среды, например:

```bash
date --iso-8601=seconds
```

Не придумывать и не реконструировать точное время задним числом.

Если точное время неизвестно, явно написать:

```text
Exact timestamp not recorded.
```

---

## 2. Timeline

Во время реализации фиксировать несколько существенных milestones.

Пример:

```markdown
## Timeline

- 2026-10-05T09:14:23+06:00 — task started, baseline verification started.
- 2026-10-05T09:22:11+06:00 — baseline checks completed.
- 2026-10-05T09:31:44+06:00 — RED test confirmed.
- 2026-10-05T10:18:05+06:00 — implementation reached GREEN.
- 2026-10-05T10:42:37+06:00 — review found migration issue.
- 2026-10-05T11:21:52+06:00 — make check passed.
- 2026-10-05T11:43:09+06:00 — make verify passed.
- 2026-10-05T11:47:10+06:00 — task completed.
```

Не логировать каждую команду или изменение файла.

Timeline должен показывать постепенный ход работы:

```text
start
→ implementation
→ verification/review
→ corrections
→ completion
```

История Git commits является дополнительным подтверждением хода работы, но не заменяет timestamps в development log.

---

## 3. Initial prompt

Записывается **дословно prompt, с которым запущена implementation task**.

Не пересказывать его своими словами.

Если задача была запущена после длинной цепочки обсуждений, достаточно:

```markdown
## Initial prompt

Plan:
`docs/superpowers/plans/2026-10-05-auth.md`

Execution prompt:

Реализуй утверждённый Auth plan.
Следуй AGENTS.md.
Не выходи за scope.
```

То есть:

```text
approved plan
+
точный final execution prompt
```

Агент не должен реконструировать prompts, которых он не видел.

---

## 4. Secrets and sensitive output

Development log никогда не должен содержать:

- passwords;
- API tokens;
- JWT secrets;
- SMTP credentials;
- private keys;
- cookies;
- Authorization headers;
- содержимое `.env`;
- production DB credentials;
- другие secrets.

Если secret присутствовал в prompt или output:

```text
[REDACTED]
```

Не копировать полный вывод:

```bash
env
printenv
cat .env
```

Вместо этого записывать безопасный итог.

---

## 5. Corrective prompts

Corrective prompt сохраняется только если он изменил хотя бы одно из следующего:

1. requirement;
2. technical approach;
3. acceptance criterion;
4. scope;
5. способ или ожидаемый результат verification.

Пример:

```text
Не используй SQLite для concurrency test.
Тест должен выполняться на PostgreSQL.
```

Такой prompt сохраняется.

Не сохранять:

```text
да
продолжай
ок
проверь ещё раз
```

если они сами по себе ничего не изменили.

---

## 6. Decisions and deviations

Фиксировать:

- отклонения от approved plan;
- обнаруженные противоречия;
- проблемы, повлиявшие на решение;
- решения, отсутствовавшие в spec/plan;
- architecture decisions.

Если решение архитектурное, создать ADR и сослаться на него из log.

---

## 7. Verification evidence

Для каждой финальной проверки указывать минимум:

```text
Command
Exit code
Actual final result
```

Нельзя ограничиваться:

```text
make check — passed
```

Правильно:

```markdown
### Backend tests

Command:
`uv run pytest`

Exit code:
`0`

Result:
`87 passed in 6.42s`
```

Другой пример:

```markdown
### Quality gate

Command:
`make check`

Exit code:
`0`

Result:
`backend: passed; frontend: passed; OpenAPI drift: none`
```

Использовать **реальный вывод команды**.

Не придумывать количество tests, duration или exit code.

---

## 8. RED evidence

Для критичных TDD-задач:

```markdown
### RED

Timestamp:
`2026-10-05T09:31:44+06:00`

Command:
`uv run pytest tests/test_registration.py::test_last_seat_concurrency -v`

Exit code:
`1`

Result:
`1 failed`

Expected reason:
seat-allocation locking ещё не реализован.
```

Полный traceback сохранять не требуется.

---

## 9. Result

Перед PR:

```markdown
## Result

Implemented:
- ...

Known limitations:
- ...

Final verification:
- make check — exit 0 — <actual result>
- make verify — exit 0 — <actual result>
```

Если команда не запускалась, написать это прямо.

---

## 10. Pull Request

После создания:

```markdown
## Pull Request

PR #12
```

или URL.

Если PR ещё не существует:

```text
Not created yet.
```

Не придумывать номер.

---

## 11. Recommended template

```markdown
# <Task Name>

Started at: `<ISO timestamp>`
Finished at: `<ISO timestamp or IN PROGRESS>`

## Initial prompt

Plan:
`docs/superpowers/plans/...`

Execution prompt:

<exact prompt, secrets redacted>

## Timeline

- <timestamp> — task started.
- <timestamp> — ...
- <timestamp> — task completed.

## Corrective prompts

<only prompts changing requirement, approach, scope or verification>

## Decisions and deviations

<important decisions>

## Issues discovered

<important issues>

## Verification

### <check>

Timestamp:
`...`

Command:
`...`

Exit code:
`...`

Result:
`...`

## Result

Implemented:
- ...

Known limitations:
- ...

## Pull Request

...
```