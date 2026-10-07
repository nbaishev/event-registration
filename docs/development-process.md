# Development Process

## 1. Назначение

Этот документ описывает только:

- lifecycle задачи;
- формат задачи;
- Git/PR flow;
- шестидневный roadmap.

Все технические правила выполнения, TDD, проверки, CI, Definition of Done, миграции, секреты и команды находятся в:

```text
AGENTS.md
```

Не дублировать их здесь.

---

# 2. Подход

Разработка идёт вертикальными срезами:

```text
business behavior
→ database
→ backend
→ OpenAPI
→ frontend
→ verification
→ PR
```

Не используем подход:

```text
весь backend
→ весь frontend
```

Внутри одной feature backend contract обычно стабилизируется до подключения соответствующего frontend.

---

# 3. Единица разработки

Единица работы — измеримая задача, которую можно независимо проверить на review.

Хороший пример:

```text
Пользователь может зарегистрироваться и войти.
```

Плохой пример:

```text
Создать таблицу User.
```

Технические шаги являются частью задачи, но не заменяют её пользовательский или системный результат.

---

# 4. Шаблон задачи

Постановка implementation task должна указывать точный путь к approved implementation
plan. Используй этот файл вместо поиска актуального плана по всей директории.

Каждый implementation plan должен содержать:

```text
Task:
[короткое название]

Goal:
[один измеримый результат]

Dependencies:
[что должно быть уже реализовано]

Required context:
[точные пути файлов и sections spec/ADR/engineering rules, необходимые для задачи]

Scope:
[что входит]

Out of scope:
[что намеренно не входит]

Acceptance criteria:
- ...
- ...
- ...

Test strategy:
[TDD / Integration / Component / E2E / Verification]

Verification:
[конкретные команды и проверки согласно AGENTS.md]

Definition of Done:
Ссылка на общий DoD в /AGENTS.md
+
специфические условия этой задачи
```

Не копировать общий DoD из `AGENTS.md` внутрь каждой задачи.

---

# 5. Lifecycle задачи

```text
1. выбрать измеримую задачу
2. составить implementation plan
3. получить approval
4. создать feature branch/worktree
5. выполнить задачу агентом
6. проверить результат
7. code review
8. исправить замечания
9. выполнить финальную проверку по AGENTS.md
10. создать Pull Request
11. review PR
12. merge в master
```

Если во время реализации обнаружен конфликт между:

```text
Product Spec
Implementation Plan
AGENTS.md
```

реализация останавливается до уточнения.

---

# 6. Git flow

`master` — интеграционная ветка.

Каждая измеримая задача начинается в новой отдельной ветке и worktree от обновлённого `master`. Не продолжать следующую задачу в ветке предыдущей задачи.

Примеры:

```text
chore/project-foundation
feat/auth
feat/events
feat/event-registration
feat/checkin-live
feat/notifications
```

После merge зависимая следующая задача начинается от обновлённого `master`.

Независимые задачи могут выполняться параллельно только если их interfaces уже определены и они не меняют общий контракт одновременно.

---

# 7. Pull Request

PR соответствует одной измеримой задаче или одному логически цельному vertical slice.

PR содержит:

- цель;
- ссылку на implementation plan;
- реализованные acceptance criteria;
- изменения API/DB;
- реально выполненные проверки;
- известные ограничения;
- screenshots для существенных UI changes.

Подробные quality gates определяются `/AGENTS.md`.

---

# 8. Day 1 — Foundation + Auth

Цель дня:

```text
docker compose up
→ frontend/backend доступны
→ пользователь может register/login/logout
```


---

# 9. Day 2 — Events

Цель:

```text
organizer
→ create event
→ edit
→ publish
→ public page
```

---

# 10. Day 3 — Registration + Waitlist

Цель:

```text
participant
→ register
→ CONFIRMED / WAITLIST
→ cancel
→ automatic FIFO promotion
```

Критический результат:

```text
capacity = 1
2 concurrent registrations
→ 1 CONFIRMED
→ 1 WAITLIST
```

---

# 11. Day 4 — Check-in + Live Dashboard

Цель:

```text
CONFIRMED получает ticket code
→ organizer делает одноразовый check-in
→ dashboard обновляется live
```

Крупные области:

- ticket code;
- atomic check-in;
- organizer dashboard;
- SSE;
- frontend reconnect.

---

# 12. Day 5 — Email + Reminder

Цель:

- confirmation/ticket email;
- promotion email;
- reminder;
- reschedule email;
- cancellation email.

---

# 13. Day 6 — E2E + Deployment

Цель:

```text
рабочий MVP
→ Linux/VPS
→ Docker Compose
→ Nginx
→ HTTPS
```

Проверяются основные сквозные пользовательские сценарии и исправляются интеграционные дефекты.

---


# 14. Где находятся правила

```text
Что строим
→ docs/superpowers/specs/

Как реализовать конкретную задачу
→ docs/superpowers/plans/

Как агент должен работать и проверять результат
→ /AGENTS.md

Почему принято архитектурное решение
→ docs/adr/

Что сознательно изменилось по ходу реализации
→ docs/development-log/
```
