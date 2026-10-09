# Production на VPS: HTTPS и контейнерный Certbot

TLS завершается в Docker Nginx; backend, worker и beat используют `ENVIRONMENT=production`. Certbot работает одноразовым контейнером в webroot-режиме. Сертификаты/ACME account хранятся в named volume `event-registration-prod_letsencrypt`, challenge — в `event-registration-prod_acme_webroot`; Nginx подключает оба read-only. Certbot на хост устанавливать не нужно. Автоматический renewal запускает systemd timer на VPS, затем выполняет Nginx check/reload.

## Подготовка VPS и домена

1. На Linux VPS установите Git, Docker Engine, Buildx и Compose plugin по [официальной инструкции Docker](https://docs.docker.com/engine/install/ubuntu/) для вашей ОС. Проверьте `docker version` и `docker compose version`. Команды ниже выполняются пользователем с доступом к Docker; при необходимости используйте `sudo docker`.
2. Настройте A-запись домена на IPv4 VPS. AAAA добавляйте только при работающем IPv6 на этом VPS. Дождитесь обновления DNS.
3. В firewall провайдера разрешите входящий SSH с вашего адреса и TCP 80 и 443 для посетителей. Порт 80 нужен и после выпуска для ACME renewal. Не открывайте PostgreSQL 5432, Redis 6379, backend 8000. Docker может обходить правила UFW для опубликованных портов; учитывайте [правила Docker firewall](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations).
4. Освободите порты 80 и 443: этот stack содержит собственный Nginx. Используется один canonical hostname и стандартные порты 80/443. Нужны Linux/systemd, `flock` (util-linux) и Make для команд ниже; Compose fallback описан далее.

## Checkout и окружение

Клонируйте репозиторий и переключитесь на опубликованную ветку `chore/production-https` либо утверждённую release revision. Перед первым запуском файлы из этой ветки должны быть доступны на VPS.

```bash
git clone <repository-url> event-registration
cd event-registration
git checkout <approved-release-revision>
umask 077
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

Заполните `.env.prod` редактором на VPS:

| Переменная | Значение |
| --- | --- |
| `APP_DOMAIN` | DNS hostname, например `events.example.com`, без scheme, path и порта. |
| `APP_ORIGIN` | Ровно `https://<APP_DOMAIN>`, без завершающего `/`, path или query. |
| `CERTBOT_EMAIL` | Email администратора для ACME account. |
| `APP_IMAGE_TAG` | Git revision текущего checkout (`git rev-parse --short HEAD`). |
| `POSTGRES_USER`, `POSTGRES_DB` | Имена роли и БД; после первого запуска сохраняйте их. |
| `POSTGRES_PASSWORD` | Отдельный случайный пароль БД. |
| `JWT_SECRET` | Отдельный случайный секрет минимум 32 bytes. |
| `SMTP_HOST`, `SMTP_FROM` | Внешний SMTP relay и разрешённый sender address. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Credentials внешнего SMTP relay; обязательны в этом Compose. |
| `SMTP_SECURITY`, `SMTP_PORT` | Обычно `starttls` / 587; для implicit TLS — `tls` / порт relay (обычно 465). |

Для генерации каждого из двух независимых секретов можно использовать `openssl rand -hex 32`. Не сохраняйте результат в Git или development log. Значения с `$` и `#` заключайте в одинарные кавычки; правила описаны в [документации Compose env files](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/#env-file-syntax).

`.env.prod` игнорируется Git; `.env.prod.example` содержит только пример и пустые обязательные секреты. Compose завершится ошибкой, пока обязательные значения не заполнены. Production mode задан в Compose явно; origin должен быть HTTPS, иначе backend не запустится. Проверьте соответствие APP_DOMAIN и APP_ORIGIN перед запуском.

Используйте отдельный shell без экспортированных application variables: они имеют приоритет над `--env-file`. Этот stack не использует локальный development `.env`. Все команды запускайте из checkout; не объединяйте `compose.prod.yaml` с `compose.yaml` и не используйте здесь `make up` / `make down`.

## Первый выпуск и запуск

Для нового VPS и перехода существующего HTTP deployment используйте тот же checkout и project name `event-registration-prod`, сохраняя DB/JWT/SMTP settings. Bootstrap заменяет ingress на короткое maintenance window: приложение отвечает 503 до `prod-up`. Не запускайте второй проект для той же БД, не используйте `--remove-orphans` или `down -v`.

```bash
make prod-config
make prod-bootstrap
```

Проверьте challenge до обращения к ACME: создайте временный token в общем webroot (без secrets) и запросите его с внешней машины.

```bash
docker compose --env-file .env.prod -f compose.certbot-bootstrap.yaml run --rm --no-deps --entrypoint /bin/sh certbot -ec 'mkdir -p /var/www/certbot/.well-known/acme-challenge; printf bootstrap-ok > /var/www/certbot/.well-known/acme-challenge/probe'
curl --fail http://events.example.com/.well-known/acme-challenge/probe
```

Ожидается `bootstrap-ok`. Удалите probe аналогичной контейнерной командой `rm -f /var/www/certbot/.well-known/acme-challenge/probe`. Неверные A/AAAA, firewall или CDN routing исправьте до выпуска.

```bash
make prod-cert-check   # staging dry-run, сертификат не сохраняется
make prod-cert-issue   # реальный выпуск; принимает ACME Terms of Service
make prod-up
make prod-nginx-check
make prod-ps
```

Оба certificate targets читают домен/email через ограниченный environment контейнера из `.env.prod`. Сертификат выпускается с `--cert-name APP_DOMAIN`, поэтому Nginx использует `/etc/letsencrypt/live/<APP_DOMAIN>/fullchain.pem` и `privkey.pem`. При ошибке выпуска оставайтесь в bootstrap, проверяйте Certbot logs и исправляйте challenge; не запускайте TLS ingress без сертификата. Не делайте повторные реальные выпуски вместо staging-проверки.

Backend entrypoint выполняет Alembic migrations перед Uvicorn. PostgreSQL остаётся в прежнем persistent volume; один backend worker и один beat. Worker/beat стартуют после readiness backend/Redis. Наружу открыт только Nginx; Mailpit отсутствует.

## Команды управления и Compose fallback

| Команда | Назначение |
| --- | --- |
| `make prod-config` | Проверка конфигурации без вывода secrets. |
| `make prod-up` | Первый запуск либо обновление с build и readiness wait. |
| `make prod-down` | Остановка без удаления volumes. |
| `make prod-ps` | Статус сервисов. |
| `make prod-logs` | Последние 100 строк и follow; завершение Ctrl-C. Logs могут содержать чувствительные сведения. |
| `make prod-nginx-check` / `make prod-nginx-reload` | Проверка / проверка и graceful reload. |
| `make prod-bootstrap` | HTTP ACME ingress с maintenance response. |
| `make prod-cert-check` / `make prod-cert-issue` | Staging-проверка / первый production выпуск. |
| `make prod-cert-renew-check` / `make prod-cert-renew` | Renewal dry-run / renewal и Nginx check/reload. |

Без Make определите функции в каждой SSH-сессии:

```bash
prod() { docker compose --env-file .env.prod -f compose.prod.yaml "$@"; }
bootstrap() { docker compose --env-file .env.prod -f compose.certbot-bootstrap.yaml "$@"; }
prod config --quiet
# Запуск: prod up -d --build --wait --wait-timeout 180
# Bootstrap: bootstrap config --quiet; bootstrap up -d --wait --wait-timeout 180
# Статус/логи: prod ps; prod logs --tail=100 --follow
# Check/reload: prod exec -T nginx nginx -t && prod exec -T nginx nginx -s reload
# Остановка: prod down
```

Для прямого первого выпуска задайте только публичные значения `APP_DOMAIN` и `CERTBOT_EMAIL` в shell вручную, не выполняйте `source .env.prod`:

```bash
APP_DOMAIN=events.example.com
CERTBOT_EMAIL=admin@example.com
bootstrap run --rm --no-deps certbot certonly --webroot -w /var/www/certbot --cert-name "$APP_DOMAIN" -d "$APP_DOMAIN" --email "$CERTBOT_EMAIL" --agree-tos --non-interactive --dry-run
# После успешной проверки повторите предыдущую команду без --dry-run.
```

Renewal без Make: `./infra/certbot/renew.sh --dry-run` или `./infra/certbot/renew.sh`. Wrapper блокирует параллельный запуск через flock и возвращает ошибки; reload происходит только после успешного renewal и `nginx -t`. Даже если сертификат пока не требует обновления, выполняется безопасный graceful reload.

## Автопродление через systemd

Используйте root-owned checkout `/opt/event-registration` либо измените **оба** пути WorkingDirectory/ExecStart в service на реальный абсолютный путь. Checkout, wrapper, `.env.prod` и unit не должны быть доступны на запись непривилегированным пользователям: service выполняется root с доступом к Docker. На VPS без root-owned deployment выберите отдельного deployment user с Docker access и измените User; учитывайте, что Docker access даёт привилегии хоста.

Проверьте отсутствие другого scheduler для этого сертификата. Установите units после успешного HTTPS запуска:

```bash
sudo install -m 644 infra/certbot/event-registration-certbot.service /etc/systemd/system/
sudo install -m 644 infra/certbot/event-registration-certbot.timer /etc/systemd/system/
# При отличающемся checkout path отредактируйте установленный service.
sudo systemd-analyze verify /etc/systemd/system/event-registration-certbot.service /etc/systemd/system/event-registration-certbot.timer
make prod-cert-renew-check
sudo systemctl daemon-reload
sudo systemctl enable --now event-registration-certbot.timer
sudo systemctl list-timers event-registration-certbot.timer
sudo journalctl -u event-registration-certbot.service --since today
```

Timer проверяет renewal дважды в сутки, добавляет до часа jitter и запускает пропущенную проверку после reboot. Cron или постоянный renewal loop не добавляйте. Unit вызывает wrapper напрямую и не требует Make. Dry-run использует staging CA, затем перечитывает действующий production сертификат; сам staging сертификат не устанавливается. Проверяйте статус timer, ошибки service и Certbot logs (volume `event-registration-prod_certbot_logs`). Успех Certbot сам по себе не доказывает reload — wrapper должен завершиться с exit 0.

Проверка сертификата снаружи:

```bash
curl --fail https://events.example.com/api/ready
openssl s_client -connect events.example.com:443 -servername events.example.com </dev/null 2>/dev/null | openssl x509 -noout -dates -issuer
```

Проверка доверия выполняется curl **без** `-k`. Внутренний container healthcheck обращается к canonical hostname через localhost override с SNI и проверяет backend readiness; он не проверяет доверие CA.

## Проверка после запуска

Подставьте ваш домен:

```bash
curl --fail https://events.example.com/api/ready
curl --fail --output /dev/null https://events.example.com/
make prod-logs
```

Ожидается `/api/ready` → `{"status":"ready"}` и HTTP 200 для frontend. Не публикуйте logs, если SMTP relay или приложение записали туда чувствительные данные.

В браузере откройте именно `APP_ORIGIN` и проверьте:

1. Регистрацию, вход, refresh, сохранение сессии после reload и logout. После перехода с HTTP повторно войдите; auth cookies должны быть HttpOnly/Secure, CSRF cookie — Secure. Вход по IP при настроенном origin домена будет отклонён проверкой Origin.
2. Создание и публикацию события, регистрацию участника, получение confirmation email через реальный SMTP relay.
3. Dashboard организатора: новое действие участника обновляет stats через SSE без reload страницы.

Readiness подтверждает доступ к БД, но не успешность SMTP delivery. Проверяйте доставку в почтовом ящике и ошибки worker. HTTPS auth, SSE и доставка на вашем VPS требуют этой ручной проверки; локальный `make verify` не проверяет ваш DNS и внешний SMTP relay.

## Backup и обновление

Сначала подготовьте backup PostgreSQL до запуска новых migrations. Для согласованной точки восстановления остановите приложение и фоновые задачи, оставив PostgreSQL запущенным:

```bash
prod stop nginx beat worker backend
mkdir -p "$HOME/event-registration-backups"
chmod 700 "$HOME/event-registration-backups"
prod exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$HOME/event-registration-backups/pre-update-$(date +%Y%m%d-%H%M%S).dump"
```

Проверьте exit code `pg_dump` и сохраните backup вне VPS. Если backup завершился ошибкой, прекратите обновление; для возврата прежнего stack выполните `prod up -d --wait --wait-timeout 180` до смены revision.

Затем получите утверждённую revision, например:

```bash
git fetch origin
git checkout <approved-revision>
```

Убедитесь, что новая revision содержит `compose.prod.yaml`. Обновите `APP_IMAGE_TAG` в `.env.prod`, сохранив DB credentials и origin. Затем:

```bash
make prod-up
make prod-ps
```

Повторите readiness и браузерные проверки. Изменение `POSTGRES_PASSWORD` в env не меняет пароль уже инициализированной БД; для ротации нужна отдельная процедура изменения роли PostgreSQL.

Возврат старого checkout/image не откатывает Alembic migrations. При несовместимой схеме нужен план восстановления из backup; не выполняйте автоматический downgrade или удаление volume.

## Остановка и ограничения

```bash
prod down
```

Named volume БД сохраняется. Для следующего запуска используйте тот же checkout directory, env и project name. Не применяйте `down -v` или volume prune к этому deployment. Redis broker не хранится в persistent volume: при пересоздании Redis очередь теряется; confirmation/reminder scanners повторно ставят актуальные задачи в очередь.

Сертификаты, ACME account и private keys сохраняются в named volume при `down`. Создайте защищённый backup volume `event-registration-prod_letsencrypt` вне Git/публичного хранилища, отдельно от PostgreSQL backup. Для согласованного backup остановите timer, дождитесь завершения service и отсутствия ручного renewal; архивируйте volume через временный контейнер с read-only mount. Восстанавливайте в volume того же project name, сохраняя права и symlinks `live` → `archive`, затем проверьте `nginx -t`/reload и включите timer.

При ошибке renewal/config check работающий Nginx не перезагружается; исправьте причину и повторите wrapper. При неудачном обновлении ingress верните прежнюю рабочую HTTPS-конфигурацию/образы, учитывая совместимость DB migrations. Не возвращайтесь автоматически к HTTP/development mode. Локальный `make verify` не подтверждает реальный DNS, ACME issuance/renewal, внешний SMTP или состояние timer на VPS.
