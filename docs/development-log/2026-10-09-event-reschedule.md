# Task 19 — Перенос опубликованного события

Started at: `2026-10-08T23:36:44+05:00`
Finished at: `2026-10-08T23:56:55+05:00`

## Initial prompt

Plan: `docs/superpowers/plans/19-2026-10-08-event-reschedule.md`

Execution prompt:

Выполни задачу [19-2026-10-08-event-reschedule.md](docs/superpowers/plans/19-2026-10-08-event-reschedule.md)

## Timeline

- 2026-10-08T23:36:44+05:00 — создан worktree `.worktrees/event-reschedule`, branch `feat/event-reschedule` от master `69c54dc`.

- 2026-10-08T23:46:53+05:00 — backend/UI targeted GREEN, PostgreSQL suite GREEN; добавлены API SMTP smoke и browser screenshots scenario.

- 2026-10-08T23:49:22+05:00 — независимый review: два Important test gaps; исправлены callback observations и pre-transition reminder eligibility, Critical/Minor нет.

- 2026-10-08T23:56:55+05:00 — final make verify exit 0, screenshots проверены, test stack освобождён.

- 2026-10-08T23:58:05+05:00 — локальная реализация committed; PR blocked автоматическим approval review screenshot upload. Remote не изменён.

## Decisions and deviations

- Execution prompt разрешает реализацию плана с исторической строкой «подготовлен для review».
- Git fetch недоступен без credentials; GitHub connector подтвердил master SHA, совпадающий с локальным. Зависимости merged.
- Pre-flight: schedule PATCH → immutable snapshot → after-commit dispatcher → Celery/SMTP; interfaces согласованы со spec и ADR-004.

## Verification

- Baseline: `backend/.venv/bin/python -m pytest backend/tests/unit/test_event_capacity.py backend/tests/unit/test_notification_rendering.py -q`, exit 0, `27 passed in 0.69s`.
- Unit RED: targeted reschedule/transition tests, exit 1, `15 failed, 3 passed in 0.65s`, отсутствовали schedule branch и snapshot interfaces. GREEN: exit 0, `18 passed in 1.05s`.
- RTL RED: отсутствующий EventScheduleForm (collection failure); GREEN: targeted schedule/pages/capacity, exit 0, `61 passed (61)`.
- Targeted PostgreSQL: isolated temporary container, approved three suites, exit 0, `57 passed in 46.61s`.
- Verification grouping RED: missing event-reschedule group/sink env, exit 1, `1 failed`; GREEN verification unit suite exit 0, `20 passed in 0.15s`.
- Environment: copied venv contained old absolute shebangs; paths corrected. Initial make check stopped at Ruff imports then mypy smoke optional Event; corrected. Subsequent sandbox unit run hung and was stopped; retry outside sandbox.


- Development gate: `UV_CACHE_DIR=/tmp/task19-uv make check`, exit 0, Ruff/format/mypy passed; `323 passed in 4.58s` backend unit, `175 passed (175)` frontend, OpenAPI drift none. React duplicate sibling key предупреждение исправлено; follow-up gate выполняется.

### Final gate

Command: `UV_CACHE_DIR=/tmp/task19-uv make verify`

Exit code: `0`

Actual result: `323 passed in 3.50s` backend unit; `175 passed (175)` frontend; `311 passed in 163.03s (0:02:43)` PostgreSQL integration; migrations/head/metadata drift, production/Docker builds, Compose/nginx passed; confirmation/reminder real SMTP smokes passed, reschedule HTTP API → after-commit Celery → real SMTP snapshot passed; Playwright `12 passed (31.4s)` + `13 passed (59.8s)`; `verify: passed (isolated project foundation-verify-6d40c0f4b944)`. Cleanup succeeded. Code/config не менялись после этого gate.

### Review fixes

After-commit тест теперь сохраняет snapshots из enqueue callback и проверяет вне exception handler. Reminder contention начинается с eligible scanner candidate и доказывает suppression после locked schedule update. Эти проверки прошли в Final gate.

### Staged secrets review

19 scoped files; no secret files/key/token patterns; credential literals are disposable fixtures. Screenshots contain only test event UI.

## Result

Implemented:
- Schedule-only опубликованный PATCH с future/interval/no-op guards, атомарным расписанием и recipient snapshot под Event lock.
- Immutable transition payload, after-commit best-effort dispatch и SMTP task без DB reread/automatic retries.
- Отдельная форма расписания, seconds/DST choice и cache updates; capacity/DRAFT regression coverage.
- PostgreSQL rollback/commit/concurrency/reminder tests, API real SMTP smoke и browser scenario.

Known limitations:
- ADR-004: notification может потеряться между commit и enqueue; порядок доставки последовательных переносов не гарантирован. Delivery history, outbox и cancellation lifecycle вне scope.

Screenshots:
- [Форма](assets/task19-event-reschedule/form.png)
- [Сохранённое расписание](assets/task19-event-reschedule/saved.png)

Final verification: см. Final gate. Независимый review: оба Important test gaps исправлены, Critical/Minor отсутствуют.


## Pull Request

Not created yet. Automatic approval review rejected `github_create_blob` screenshot upload: implementing task authorization did not specifically authorize exporting the locally generated screenshot to the GitHub destination; repository/payload were not accepted as verified/non-sensitive. No remote mutation succeeded. Explicit permission pending for code + screenshots upload and one PR to `nbaishev/event-registration`, branch `feat/event-reschedule` → `master`.

Local implementation commit: `8d183f5`. Prepared PR description: `/tmp/task19-pr-body.md`.

## Publication authorization

Corrective prompt:

Разрешаю

2026-10-09T00:07:00+05:00 — пользователь явно разрешил загрузить код и screenshots в `nbaishev/event-registration` и создать PR в `master`. Предыдущий automatic rejection относится к попытке до этого authorization. Implementation/config не менялись после успешного make verify; повтор gate не требуется.
