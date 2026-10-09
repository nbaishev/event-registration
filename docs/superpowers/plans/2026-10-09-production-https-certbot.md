# Production HTTPS через Certbot — Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task-by-task after approval. Steps use checkbox syntax for tracking.

**Статус:** APPROVED — пользователь утвердил контейнерный вариант и Makefile targets. Локальная реализация и финальный `make verify` выполнены; VPS rollout отдельно.
**Task:** HTTPS ingress и автоматическое продление сертификата на production VPS.
**Goal:** Приложение доступно по одному HTTPS origin с доверенным сертификатом, production cookies и работающим автопродлением без остановки приложения.
**Architecture:** TLS завершается в существующем Docker Nginx. Certbot запускается отдельным одноразовым контейнером в webroot-режиме; общие named volumes хранят сертификаты и ACME webroot, Nginx подключает их read-only. Хостовый systemd timer запускает Compose renewal и проверку/reload Nginx; установка Certbot на VPS не требуется. Первый выпуск использует отдельный HTTP bootstrap ingress, не требующий сертификатов и доступа к приложению.
**Tech Stack:** Docker Compose, Nginx 1.28, официальный образ certbot/certbot, Let's Encrypt, Linux/systemd.
**Spec:** `docs/superpowers/specs/technical-design.md`, sections 24–26 (cookies, CSRF/Origin, login limit), 30 (Nginx).
**Dependencies:** Существующий standalone `compose.prod.yaml` и HTTP deployment из `2026-10-09-domain-access.md`; эта задача заменяет временный режим.

## Required context

- `compose.prod.yaml`, `.env.prod.example`, `infra/nginx/default.conf`, `docs/deployment-vps.md`, `Makefile`.
- `backend/app/common/config.py`: Settings.validate_startup; `backend/app/auth/cookies.py`: production Secure cookies; CSRF cookie в `backend/app/auth/router.py`.
- Только перечисленные выше sections Product Spec.
- `docs/agent-rules/engineering.md`: Auth, Nginx, Secrets, Canonical commands / вывод команд / quality gates.
- `docs/development-process.md`: lifecycle и Git flow; `docs/agent-rules/development-log.md`: формат журнала.

## Global constraints и scope

- Один canonical DNS hostname, без wildcard; `APP_ORIGIN=https://<APP_DOMAIN>`, без path, query и нестандартного порта.
- VPS с systemd, прямым доступом к TCP 80/443 и DNS A/AAAA, указывающими на него. Версию ОС, реальный домен, email для ACME и абсолютный checkout path уточнить перед операциями на VPS; placeholders допустимы при реализации файлов.
- `ENVIRONMENT=production` одинаков для backend, worker и beat. Существующие JWT/DB/SMTP secrets сохраняются.
- Наружу публикует порты только Nginx; один backend worker и один beat сохраняются.
- Login limit 10 requests/minute/IP, burst=5 и JSON 429; SSE buffering off и read timeout 60s; существующие proxy headers сохраняются.
- TLS 1.2/1.3. HTTPS redirect 308 использует canonical domain, а не произвольный Host. ACME challenge обслуживается по HTTP без redirect.
- Development/test ingress `infra/nginx/default.conf` остаётся самостоятельным; production получает отдельные templates.
- Вне scope: DNS automation/DNS-01, wildcard, CDN, HSTS preload, изменения backend security contract, архитектуры, БД и SMTP; фактический deployment без отдельного запроса пользователя.

## Review focus

1. Пустой `/etc/letsencrypt`: bootstrap стартует, основной TLS ingress ожидаемо требует сертификат.
2. ACME token доступен по HTTP и после включения redirect; отсутствие token даёт 404.
3. Подстановка hostname не уничтожает Nginx `$scheme`, `$http_host`, `$request_uri` и остальные runtime variables.
4. После renewal Nginx перечитывает сертификат; ошибка проверки/reload видима в журнале.
5. HTTPS login/refresh/CSRF и SSE сохраняют контракт; healthcheck действительно проверяет backend readiness.

## Task 1: Production ingress и bootstrap

**Files:**
- Modify: `compose.prod.yaml`, `.env.prod.example`.
- Create: `infra/nginx/production/default.conf.template`.
- Create: `infra/nginx/bootstrap/default.conf.template`, `compose.certbot-bootstrap.yaml`.

**Interfaces:** `APP_DOMAIN` — DNS hostname без scheme/path/port; сертификат имеет `--cert-name "$APP_DOMAIN"`. Volumes `letsencrypt` → `/etc/letsencrypt` и `acme_webroot` → `/var/www/certbot`: Certbot получает read-write, Nginx read-only. Certbot logs/work используют volumes `certbot_logs` → `/var/log/letsencrypt`, `certbot_work` → `/var/lib/letsencrypt`. Оба Compose файла объявляют одинаковые volumes и используют одинаковый project name. Templates → `/etc/nginx/templates`; `NGINX_ENVSUBST_FILTER=^APP_DOMAIN$`.

- [x] После approval создать отдельную ветку/worktree по lifecycle и development log до изменений конфигурации.
- [x] Создать отдельный standalone bootstrap Compose с прежним project name `event-registration-prod`, сервисами `nginx` и одноразовым `certbot`, портом 80, bootstrap template и общими volumes. Certbot находится в profile `acme` и запускается явно через `run --rm --no-deps certbot`, поэтому bootstrap `up` запускает только Nginx. Он заменяет существующий ingress на короткое maintenance window; не использовать `--remove-orphans`, чтобы не удалять остальные сервисы. Bootstrap отдаёт только ACME challenge, `/healthz` → 200 и 503 для остальных путей; не зависит от backend/frontend и не ссылается на TLS-файлы.
- [x] Production template: HTTP `/.well-known/acme-challenge/` с `root /var/www/certbot`, `try_files $uri =404`; остальные HTTP пути → 308 на `https://${APP_DOMAIN}$request_uri`. HTTPS server читает `live/${APP_DOMAIN}/fullchain.pem` и `privkey.pem`; перенести application locations из существующего ingress, включая rate limit, SSE и proxy headers. Не проксировать приложению HTTP запросы в production.
- [x] В production Compose заменить текущий mount конфигурации на production templates, добавить два read-only volume mounts и порты `80:80`, `443:443`; убрать APP_PORT. Настроить envsubst только для APP_DOMAIN. Backend environment anchor переключить на production; APP_ORIGIN error text обновить на HTTPS.
- [x] Заменить redirect-sensitive Nginx healthcheck на HTTPS `/api/ready` с canonical Host и SNI. Контейнерный probe может отключать проверку доверия локально; доверие сертификата отдельно проверяется внешним curl без `-k`. Проверить наличие выбранного HTTP client в образе Nginx.
- [x] Добавить в оба Compose файла одинаковый сервис Certbot в profile `acme`: официальный `certbot/certbot` с явным version tag (зафиксировать актуальную совместимую версию при реализации, без `latest`), общие volumes, без host ports, Docker socket и restart loop. Не подключать `.env.prod` целиком к Certbot: домен/email передаются аргументами CLI.
- [x] В `.env.prod.example` указать CERTBOT_EMAIL (placeholder), APP_DOMAIN и HTTPS APP_ORIGIN, убрать HTTP-комментарии и APP_PORT. Документировать равенство hostname/origin; не добавлять секреты или реальные значения.
- [x] Проверить `docker compose --env-file <safe-fixture> -f compose.prod.yaml config --quiet` и отдельный bootstrap render; production mode всех трёх сервисов, опубликованные порты только ingress, неизменное имя проекта/DB volume.
- [x] В изолированном Compose project проверить bootstrap с пустым certificate directory, ACME 200/404 и application 503. Для TLS-конфига использовать временный self-signed certificate вне Git, mock upstreams и отдельные localhost ports: `nginx -t`, HTTPS proxy, redirect со сохранением path/query и ACME без redirect. Проверить сохранение Nginx runtime variables после envsubst. Не запускать эти проверки на production volume.

## Task 2: Контейнерный выпуск, renewal и операционная инструкция

**Files:**
- Modify: `docs/deployment-vps.md`.
- Create: `infra/certbot/renew.sh`, `infra/certbot/event-registration-certbot.service`, `infra/certbot/event-registration-certbot.timer`.

**Interfaces:** Хостовый wrapper запускает `docker compose --env-file .env.prod -f compose.prod.yaml run --rm --no-deps certbot renew --non-interactive`, затем проверяет и перезагружает Nginx через `exec -T`. Certbot CLI доступен исключительно в контейнере. Unit содержит настроенный абсолютный checkout path; timer запускает wrapper дважды в сутки с RandomizedDelaySec и Persistent=true.

- [x] Переписать HTTP runbook в HTTPS runbook: prerequisites, новая установка и переход существующего deployment, renewal, troubleshooting, обновление и recovery. Указать maintenance window при bootstrap и необходимость повторного входа после переключения origin. Не менять DB project/volume и не выполнять `down -v`.
- [x] Документировать Docker/Compose и systemd prerequisites: Certbot на хост устанавливать не нужно. Перед включением нового timer проверить, что иной scheduler не обслуживает этот же сертификат. Timer запускает контейнер Certbot; отдельный постоянный renewal-контейнер не нужен.
- [ ] Перед bootstrap проверить DNS, включая работоспособность AAAA, firewall провайдера/хоста, доступность 80/443 и отсутствие другого listener. Подготовить production env с HTTPS origin; выполнить bootstrap Compose `up -d --wait`. Положить тестовый token в `acme_webroot` через временный контейнер и проверить его с внешней машины.
- [x] Определить в runbook функции `bootstrap()` и `prod()` с точными Compose файлами и `.env.prod`. Загрузить APP_DOMAIN/CERTBOT_EMAIL как отдельные явно заданные shell variables; не выполнять `source .env.prod`, не выводить secrets. Выполнить `bootstrap run --rm --no-deps certbot certonly --dry-run --webroot -w /var/www/certbot --cert-name "$APP_DOMAIN" -d "$APP_DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --non-interactive`. Затем production-выпуск той же командой без `--dry-run`. При ошибке не включать TLS ingress; проверить exit code и Certbot logs в volume, устранить DNS/challenge проблему и повторить проверку.
- [ ] После успешного выпуска проверить наличие файлов сертификата через временный контейнер с volume, выполнить production `config --quiet`, затем `up -d --build --wait --wait-timeout 180`. Не совмещать production Compose с development Compose или bootstrap файлом. Проверить `nginx -t`, readiness и доверенный HTTPS снаружи; порт 80 оставить открытым для renewal.
- [x] Реализовать host wrapper: строгий shell error handling, точный абсолютный checkout path/CLI, host `flock` для исключения конкурентных запусков, последовательность container `renew` → `nginx -t` → `nginx -s reload`. При ошибке любого шага завершаться ненулевым exit code; при ошибке renewal не выполнять reload. Успешный `renew` может означать, что сертификат ещё не требует обновления: в этом случае тоже выполнять безопасный graceful reload. Этот осознанный выбор обходится без marker volumes и Docker socket внутри контейнеров.
- [x] Wrapper принимает только необязательный аргумент `--dry-run`, который добавляет `--dry-run` к container renew и затем выполняет обычные Nginx check/reload. Другие аргументы отклонять. Проверить shell syntax и mock Docker CLI: порядок вызовов при успехе, отсутствие reload после renewal/config failure, ненулевой exit при reload failure, dry-run propagation и блокировку параллельного запуска.
- [x] Подготовить systemd oneshot service, вызывающий wrapper по абсолютному пути из deployment checkout, и timer дважды в сутки с jitter и пропущенным запуском после reboot. Запускать через пользователя с доступом к Docker; unit и executable должны быть защищены от изменения непривилегированными пользователями. Проверить unit через `systemd-analyze verify`; описать установку, daemon-reload, enable/start timer, list-timers и journalctl. Не создавать одновременно cron.
- [ ] На VPS выполнить wrapper `--dry-run`: staging renewal должен пройти, затем production Nginx — успешно проверить конфигурацию и выполнить reload действующего сертификата. Зафиксировать результат и активный timer. Описать проверку Certbot/systemd logs и фактического срока сертификата снаружи; завершение Certbot само по себе не доказывает reload.
- [x] Recovery: при ошибке wrapper оставить работающий Nginx, исправить причину и повторить запуск; при неработающем новом ingress вернуть предыдущую рабочую HTTPS-конфигурацию/образы с совместимой схемой. Возврат к HTTP/development security mode не делать автоматически. Сохранить защищённый backup `letsencrypt` volume с private keys и ACME account вне Git, отдельно от DB backup. Описать восстановление в volume с тем же именем/project name. `down` сохраняет named volumes; `down -v` запрещён для deployment.

## Task 3: Production команды в Makefile

**Files:**
- Modify: `Makefile`, `docs/deployment-vps.md`.

**Interfaces:** Все production targets используют только `docker compose --env-file .env.prod -f compose.prod.yaml`; bootstrap targets — только `compose.certbot-bootstrap.yaml` с тем же env-файлом. Команды выполняются из корня checkout. Существующие development/test targets сохраняют своё назначение.

- [x] Добавить `.PHONY` targets и общие Makefile variables для production/bootstrap Compose commands, чтобы не повторять аргументы в каждом recipe. Не включать `.env.prod` как Makefile и не выполнять shell `source`; secrets читает Compose. Не выводить rendered Compose с secrets.
- [x] Добавить `prod-config`: production `config --quiet`; `prod-up`: сначала config validation, затем `up -d --build --wait --wait-timeout 180`; `prod-down`: `down` без `-v`; `prod-ps`: `ps`; `prod-logs`: `logs --tail=100 --follow`. `prod-up` также применяется для обновления после подготовки backup и checkout утверждённой revision. При первом неуспешном шаге target завершается ошибкой.
- [x] Добавить `prod-nginx-check`: `exec -T nginx nginx -t`; `prod-nginx-reload`: сначала check, затем `exec -T nginx nginx -s reload`. Reload не вызывается, если check завершился ошибкой.
- [x] Добавить `prod-bootstrap`: bootstrap `config --quiet`, затем `up -d --wait --wait-timeout 180`. Он запускает только bootstrap Nginx; приложение в этот момент недоступно согласно Task 1. Production `prod-up` заменяет bootstrap ingress после выпуска сертификата.
- [x] Добавить `prod-cert-check` и `prod-cert-issue`: bootstrap `run --rm --no-deps certbot certonly --webroot -w /var/www/certbot --non-interactive`; первый добавляет `--dry-run`, второй выполняет реальный выпуск с `--agree-tos`. APP_DOMAIN и CERTBOT_EMAIL читать из Compose environment отдельного сервиса Certbot (передать туда только эти два значения из `.env.prod`); container shell использует quoted variables для `--cert-name`, `-d`, `--email`. При shell entrypoint явно вызвать `certbot`, корректно экранировать `$` на уровнях Make/Compose. До сетевого запроса отклонять пустые hostname/email. Не требовать ручного дублирования env values в аргументах make. Staging-check также передаёт `--agree-tos`.
- [x] Добавить `prod-cert-renew` и `prod-cert-renew-check`: вызов `infra/certbot/renew.sh` без аргументов и с `--dry-run` соответственно. Systemd service остаётся прямым вызовом того же wrapper и не требует установленного Make на VPS для автоматического renewal.
- [x] Обновить runbook: основные пользовательские команды — Makefile targets; сохранить точные underlying Compose команды как fallback для VPS без Make. Объяснить порядок первого запуска: `prod-bootstrap` → `prod-cert-check` → `prod-cert-issue` → `prod-up` → `prod-nginx-check`; timer устанавливается отдельно по Task 2. Описать logs как потенциально чувствительный вывод и остановку без удаления volumes.
- [x] Проверить `make -n` для каждого нового target с безопасным env fixture и targeted mock CLI проверки: точный Compose/env-file, production/bootstrap разделение, validation перед up, остановка без `-v`, check перед reload, propagation failures и правильная передача certificate arguments. Реальный выпуск сертификата в локальных проверках не выполнять.

**Уточнение Task 2:** Makefile certificate targets используют контейнерный shell и ограниченный environment из этого task; runbook не требует отдельного задания APP_DOMAIN/CERTBOT_EMAIL в shell. Оба Compose сервиса Certbot получают только эти два application env значения, без DB/JWT/SMTP secrets. Прямые CLI команды Task 2 остаются fallback с явно заданными значениями.

## Acceptance criteria и verification

- [ ] Доверенный HTTPS frontend и `/api/ready` доступны; HTTP application request возвращает 308 на canonical HTTPS, challenge — 200/404 без redirect.
- [ ] Backend/worker/beat используют production и одинаковый HTTPS origin; login/register/refresh/logout работают, auth cookies HttpOnly/Secure, CSRF cookie Secure; неверный Origin отклоняется.
- [ ] Login rate limit и SSE updates/heartbeat/reconnect работают по HTTPS; frontend reload и email links используют HTTPS origin.
- [ ] First issuance работает без заранее существующего сертификата. Контейнерный renewal dry-run и последующий reload проходят; systemd timer активен; reload не останавливает контейнеры. DB volume и данные сохраняются.
- [x] Makefile содержит документированные production targets для validation/start/update/stop/status/logs, Nginx check/reload, bootstrap и certificate check/issue/renew; они используют `.env.prod` и соответствующий standalone Compose, сохраняют volumes и возвращают ошибки вызывающему процессу.
- [x] Review diff и fixes, затем один финальный `make verify` по engineering rules. Обычный gate дополнить targeted production/bootstrap checks из Task 1: test stack сам по себе не проверяет публичный ACME и реальный TLS.
- [x] Обновить development log фактическими результатами и ограничениями; проверить staged diff на secrets перед PR.

**Test strategy:** Configuration/integration verification для ingress; targeted renewal-wrapper checks; existing backend security tests; ручной VPS smoke для реального DNS, ACME, сертификата и scheduler. Публичные операции не выполняются при локальной реализации файлов.
**Definition of Done:** `AGENTS.md` плюс acceptance criteria. Отдельно фиксировать локальную реализацию и VPS rollout: без доступа к VPS не заявлять успешный выпуск/renewal/deployment. Для составления этого draft baseline tests/worktree/development log не требуются.

## Источники

- [Certbot: webroot, renewal, deploy hooks](https://eff-certbot.readthedocs.io/en/stable/using.html).
- [Let's Encrypt: HTTP-01 challenge](https://letsencrypt.org/docs/challenge-types/).
- [Let's Encrypt: keep port 80 open](https://letsencrypt.org/docs/allow-port-80/).
