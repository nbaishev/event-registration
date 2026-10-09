# Production HTTPS через контейнерный Certbot

Started at: `2026-10-09T15:03:41+06:00`
Finished at: `2026-10-09T15:18:32+06:00`

## Initial prompt

Plan: `docs/superpowers/plans/2026-10-09-production-https-certbot.md`

Execution prompt:

Утверждаю

## Timeline

- 2026-10-09T15:03:41+06:00 — создан worktree `chore/production-https`, начало реализации.

- 2026-10-09T15:10:27+06:00 — baseline и targeted commands checks прошли; подготовлен runbook, review выполняется.

- 2026-10-09T15:11:26+06:00 — независимое review без Critical/Important/Minor; Docker ingress checks прошли; запущен финальный make verify.

- 2026-10-09T15:18:32+06:00 — финальный make verify завершён с exit 0; staged diff проверен на secrets.

## Decisions and deviations

- Fetch недоступен: GitHub credentials отсутствуют. Локальные master и origin/master совпадают (`df861f3`); worktree создан от этой revision.
- Task 3 уточняет передачу APP_DOMAIN/CERTBOT_EMAIL в Certbot: только эти две переменные; никаких DB/JWT/SMTP secrets.

## Verification

### Baseline

Command: `make check`
Exit code: `0`
Result: Ruff/mypy/backend unit/frontend lint/typecheck/tests прошли; `OpenAPI drift: none.`

### RED → GREEN: production commands

Command: `python3 -m unittest discover -s infra/certbot/tests -q`
RED result: `Ran 7 tests ... FAILED (failures=9)` — отсутствовали targets и wrapper.
GREEN exit code: `0`
GREEN result: `Ran 8 tests ... OK`; добавлена проверка конкурентного renewal.

### Shell и systemd

Command: `sh -n infra/certbot/renew.sh`
Exit code: `0`
Result: shell syntax valid.
Command: `SYSTEMD_UNIT_PATH=/tmp/https-systemd-units:/usr/lib/systemd/system systemd-analyze verify ...`
Exit code: `0`
Result: units валидны с реальным локальным checkout path и stub docker.service. Первоначальная проверка raw templates не прошла: на этой машине отсутствуют docker.service и deployment path `/opt/event-registration`; состояние реального VPS не проверено.


### Isolated ingress

Command: `python3 -u /tmp/check-https-nginx.py`
Exit code: `0`
Result: `Compose contracts: PASS`; `Empty-certificate bootstrap + ACME 200/404 + maintenance 503: PASS`; `TLS + canonical redirect + ACME + readiness probe + rate limit + proxy/SSE config + reload: PASS`.
Проверка использовала отдельный project, localhost dynamic ports, self-signed cert и mock upstreams; project удалён. Это не публичный CA/browser smoke.

### Certbot image и полный isolated smoke

Command: `python3 /tmp/check-https-ingress.py`
Exit code: `0`
Result: Compose/bootstrap/TLS checks PASS; Docker image `certbot/certbot:v5.8.0` загружен, container `--version` подтвердил `certbot 5.8.0`. Повторная ingress проверка обоснована незавершённой загрузкой Certbot в первом запуске; production resources не использовались.

### Make targets

Command: `make -n prod-config prod-up prod-down prod-ps prod-logs prod-nginx-check prod-nginx-reload prod-bootstrap prod-cert-check prod-cert-issue prod-cert-renew prod-cert-renew-check`
Exit code: `0`
Result: все targets доступны и раскрываются; поведение ошибок проверено targeted tests выше.

### Review

Независимый read-only reviewer: Critical/Important/Minor — нет. Реальный DNS/ACME, публичное доверие и installed systemd runtime отложены до VPS rollout, поскольку отсутствует deployment environment.

### Final quality gate

Command: `make verify`
Exit code: `0`
Result: backend unit и 322 integration tests прошли; frontend 187 tests прошли; OpenAPI drift none; empty DB migrations/head/metadata check passed; production frontend/Docker builds и readiness/same-origin smoke прошли; Playwright 12 + 14 tests passed. Изолированный verification stack и его volumes удалены.

### Staged diff

Command: `git diff --cached --check` и scoped secret scan staged diff
Exit code: `0`
Result: whitespace errors отсутствуют; real env/private keys/token signatures не добавлены; конфигурация и docs содержат placeholders.

## Result

Implemented:
- Production HTTPS ingress и bootstrap, общий persistent Certbot storage.
- Certbot Docker image v5.8.0, systemd renewal orchestration и graceful Nginx reload.
- Makefile production commands, targeted failure/concurrency tests и VPS runbook.

Known limitations:
- Реальный DNS/ACME issuance и renewal, доверенный публичный сертификат, systemd runtime и browser/SMTP smoke на VPS не выполнялись; инструкции готовы для отдельного rollout.
- Remote fetch недоступен из-за отсутствия credentials; base совпадал с локальным origin/master.

Final verification: evidence выше. Ветка и worktree сохранены для review/integration.

GitHub connector опубликовал проверенное дерево `6086293885d96f7f6b3bfdd6fb1eba26c77bdba6` с remote commit `a93d8ee`; local implementation commit `869ea76` имеет то же дерево. HTTPS/SSH CLI credentials недоступны. PR создан в master; повторный gate не запускался, код/configuration не менялись.

## Pull Request

https://github.com/nbaishev/event-registration/pull/25
