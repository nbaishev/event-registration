# Verification Suite Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax. Implementation только по отдельной команде пользователя.

**Status:** Декомпозиция и решения утверждены пользователем 2026-10-07; файл подготовлен для review перед implementation.

**Goal:** Каждый backend unit/frontend suite выполняется ровно один раз внутри make verify, без потери обязательных gates.

**Architecture:** make verify сохраняет prerequisite make check. scripts/verification.py в режиме verify запускает только PostgreSQL integration; режим test сохраняет полный backend/frontend suite.

**Tech Stack:** Существующие Python/FastAPI, sync SQLAlchemy/PostgreSQL, React/TypeScript/MUI/TanStack Query, pytest/Vitest/Playwright; новые infrastructure services не нужны.

**Spec:** [engineering.md](../../agent-rules/engineering.md), Canonical commands / Состав quality gates.

## Global Constraints

- Lifecycle и PR: [development-process.md](../../development-process.md); engineering rules — только sections из Required context ниже; journal: [development-log.md](../../agent-rules/development-log.md).
- Перед кодом: отдельная branch/worktree от updated master и development log. Сейчас создаются только plans, implementation не начинается.
- Не добавлять Ticket table, outbox, RefreshSession, Redis Pub/Sub, Redux, microservices или unrelated refactoring. Persistent schema change не предполагается.
- Targeted tests для RED/GREEN; `make check` для development gate. Review → fixes → один финальный `make verify`; после успешного gate без изменений повтор не нужен. `make test` не является промежуточным обязательным gate.
- Before PR: actual verification evidence/limitations в log, staged diff secrets review; screenshots для существенных UI changes.

## Definition of Done

[AGENTS.md](../../../AGENTS.md), общий gate из engineering.md и все Acceptance criteria этого plan. Один PR; реализация только по отдельной execution-команде после review этого файла.

## Task / PR boundary

**Task:** Устранение повторных suites перед Day 4.
**Dependencies:** Текущий master с завершённым Day 3.
**Branch:** `chore/verification-suite-deduplication`.
**Scope:** mode dispatch suites в scripts/verification.py и его regression tests.
**Out of scope:** Изменение состава gates, login limiter isolation, feature/API/DB changes, переписывание verification orchestration.

## Required context

- engineering.md: Canonical commands, Вывод команд, Состав quality gates, Secrets.
- `Makefile`, `scripts/verification.py`; существующие subprocess tests в `backend/tests/unit/test_bootstrap.py` как pattern только при необходимости.

## Acceptance criteria

- `make verify`: make check выполняет unit/Vitest; Python verify затем выполняет `pytest backend/tests/integration -q` и не вызывает frontend test.
- `make test`: по-прежнему `pytest backend/tests -q` плюс frontend test.
- `make e2e`: не запускает pytest/Vitest; существующие browser groups/rate isolation сохраняются.
- Migration/build/Docker/Nginx/readiness/Playwright gates, isolated DB/project names и cleanup finally сохраняются.
- Failure любого subprocess сохраняет ненулевой результат, cleanup выполняется и при failure.

## Files / interfaces

Modify `scripts/verification.py`; create `backend/tests/unit/test_verification.py`. Makefile не требует изменения.
Consumes `verify(mode: str) -> None`, `run(command, cwd=..., env=...)`; produces прежний CLI `python3 scripts/verification.py test|e2e|verify` с исправленным dispatch. Direct Python verify является второй фазой gate, а не заменой `make verify`.

## Review Focus / Test strategy

TDD с mocked subprocess boundary: `test_verify_runs_integration_without_unit_or_vitest`, `test_test_runs_full_suites`, `test_e2e_skips_python_suites`, `test_failure_propagates_and_cleans_up`. Проверять реальные command lists, порядок migrations/build и cleanup; Docker в unit не запускать, secrets/env values не печатать.

## Execution steps / Verification

- [ ] Создать branch/worktree и task log; записать scope и текущий dispatch.
- [ ] Написать перечисленные tests; `uv run --frozen --project backend pytest backend/tests/unit/test_verification.py -q` → ожидаемый RED на repeated suites.
- [ ] Разделить test/verify dispatch; повторить targeted command до GREEN.
- [ ] Проверить diff: последующие gates и E2E isolation не изменены; `make check` → exit 0; review и fixes.
- [ ] `make verify` → exit 0; evidence подтверждает unit/frontend по одному разу и полный integration/migration/build/browser gates. Обновить log, secrets review, один PR и merge перед Task 13.
