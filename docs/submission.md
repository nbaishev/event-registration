# Project Submission

Этот документ содержит сведения, необходимые для передачи и оценки проекта.

Заполняется постепенно в ходе разработки и окончательно проверяется перед сдачей.

---

## 1. Repository

GitHub:

```text
<repository URL>
```

Main branch:

```text
master
```

Final commit:

```text
<commit SHA>
```

---

## 2. Tools and models

### Pre-development / architecture

Tool:

```text
ChatGPT
```

Model:

```text
GPT-5.6 Sol
```

Использование:

- анализ требований;
- architecture review;
- определение scope;
- формирование Product Spec;
- разработка agent rules и development process.

Почему выбран:

ChatGPT использовался для итеративного анализа требований и критического review архитектуры до начала кодирования.

### Implementation

Tool:

```text
Codex
```

Model:

```text
<record the actual model used>
```

Использование:

- работа непосредственно с repository;
- implementation plans;
- изменение кода;
- запуск tests;
- review и corrections.

Почему выбран:



Перед сдачей указать **реальную модель**, использованную во время implementation. Не заполнять её предположением заранее.

Если в ходе разработки использовались другие инструменты или модели, добавить их сюда.

---

## 3. AI prompts and decision history

Полный экспорт AI session не сдаётся.

Вместо него используются:

```text
docs/development-log/
docs/adr/
docs/superpowers/specs/
docs/superpowers/plans/
```

Development logs содержат:

- точный execution prompt;
- значимые corrective prompts;
- timeline;
- decisions/deviations;
- verification evidence;
- результаты.

Architecture decisions вынесены в:

```text
docs/adr/
```

---

## 4. Work timeline

Постепенный ход работы подтверждается двумя независимыми источниками:

### Git history

```bash
git log --date=iso --pretty=fuller
```

Коммиты создаются по ходу реализации, а не одним commit в конце.

### Development logs

Каждая implementation task содержит:

```text
Started at
Timeline
Verification timestamps
Finished at
```

с timezone-aware ISO timestamps.

Основной индекс:

```text
docs/development-log/
```

Не изменять искусственно timestamps для создания видимости постепенной работы.

---

## 5. Project description and deployment

Каноническая инструкция находится в:

```text
README.md
```

README должен содержать:

- назначение проекта;
- реализованные возможности;
- prerequisites;
- configuration;
- `make bootstrap`;
- `make up`;
- migrations;
- как открыть frontend;
- как проверить API;
- как запустить tests;
- known limitations;
- текущее состояние проекта.

Не дублировать полную deployment-инструкцию здесь.

Final status:

```text
<COMPLETE / PARTIAL / DEMO READY>
```

Known blocking issues:

```text
<none or list>
```

---

## 6. Verification at submission

Перед сдачей записать реальные результаты:

```text
make check
Exit code: <...>
Result: <actual final line>

make verify
Exit code: <...>
Result: <actual final line>
```

Production/demo smoke test:

```text
<actual result>
```

---

## 7. What would be done next

Функции, сознательно оставленные за пределами, но рекомендуемые для следующей итерации:

- transactional outbox для надёжной доставки всех notification types;
- server-side refresh sessions и refresh-token rotation;
- multi-worker SSE через Redis Pub/Sub или другой shared transport;
- полноценная observability;
- password recovery;
- email verification;
- QR tickets;
- PDF tickets;
- более полный E2E suite;
- deployment automation.

Перед сдачей список должен быть пересмотрен по фактическому состоянию проекта.

Не указывать уже реализованные возможности как future work.

---

## 8. External solutions, templates and generators

Для каждого внешнего источника, который существенно повлиял на проект, указать:

```text
Name:
Source:
Version/commit, if applicable:
Used for:
Modified:
License:
```

Примеры того, что необходимо раскрыть:

- starter templates;
- boilerplates;
- copied code;
- substantial snippets;
- generators;
- OpenAPI generators;
- UI templates;
- external reference implementations.

Стандартные package dependencies не требуется перечислять здесь целиком — они фиксируются lock files.

### Planned generator

OpenAPI TypeScript contract generation:

```text
Tool: openapi-typescript
Purpose: generate frontend types from FastAPI OpenAPI
```

Перед сдачей зафиксировать реально использованную version через lock file.

### Project origin

Если проект написан с нуля:

```text
No external application or reference implementation was used as the project base.
```

Если это изменится во время разработки, этот раздел необходимо обновить.

---
