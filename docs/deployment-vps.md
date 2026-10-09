# Запуск на VPS по HTTP

Конфигурация `compose.prod.yaml` предназначена для временного запуска на VPS без HTTPS. Она собирает production frontend и backend images, но явно задаёт backend `ENVIRONMENT=development`: существующий production mode требует HTTPS и Secure cookies. По HTTP cookies передаются без Secure. Certbot и настройка HTTPS в эту инструкцию не входят.

## Подготовка VPS и домена

1. На Linux VPS установите Git, Docker Engine, Buildx и Compose plugin по [официальной инструкции Docker](https://docs.docker.com/engine/install/ubuntu/) для вашей ОС. Проверьте `docker version` и `docker compose version`. Команды ниже выполняются пользователем с доступом к Docker; при необходимости используйте `sudo docker`.
2. Настройте A-запись домена на IPv4 VPS. AAAA добавляйте только при работающем IPv6 на этом VPS. Дождитесь обновления DNS.
3. В firewall провайдера разрешите входящий SSH с вашего адреса и TCP 80 для посетителей. Не открывайте PostgreSQL 5432, Redis 6379, backend 8000. Docker может обходить правила UFW для опубликованных портов; учитывайте [правила Docker firewall](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations).
4. Освободите порт 80: этот stack содержит собственный Nginx. Для нестандартного порта измените `APP_PORT`, firewall и порт в `APP_ORIGIN`.

## Checkout и окружение

Клонируйте репозиторий и переключитесь на опубликованную ветку `chore/domain-access` либо утверждённую release revision. Перед первым запуском файлы из этой ветки должны быть доступны на VPS.

```bash
git clone <repository-url> event-registration
cd event-registration
git checkout chore/domain-access
umask 077
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

Заполните `.env.prod` редактором на VPS:

| Переменная | Значение |
| --- | --- |
| `APP_ORIGIN` | Точный адрес браузера, например `http://events.example.com`, без завершающего `/`, path или query. Для порта 8080: `http://events.example.com:8080`. |
| `APP_PORT` | Порт VPS, по умолчанию 80. |
| `APP_IMAGE_TAG` | Git revision текущего checkout (`git rev-parse --short HEAD`). |
| `POSTGRES_USER`, `POSTGRES_DB` | Имена роли и БД; после первого запуска сохраняйте их. |
| `POSTGRES_PASSWORD` | Отдельный случайный пароль БД. |
| `JWT_SECRET` | Отдельный случайный секрет минимум 32 bytes. |
| `SMTP_HOST`, `SMTP_FROM` | Внешний SMTP relay и разрешённый sender address. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Credentials внешнего SMTP relay; обязательны в этом Compose. |
| `SMTP_SECURITY`, `SMTP_PORT` | Обычно `starttls` / 587; для implicit TLS — `tls` / порт relay (обычно 465). |

Для генерации каждого из двух независимых секретов можно использовать `openssl rand -hex 32`. Не сохраняйте результат в Git или development log. Значения с `$` и `#` заключайте в одинарные кавычки; правила описаны в [документации Compose env files](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/#env-file-syntax).

`.env.prod` игнорируется Git; `.env.prod.example` содержит только пример и пустые обязательные секреты. Compose завершится ошибкой, пока обязательные значения не заполнены. Не устанавливайте `ENVIRONMENT=production` для этого HTTP deployment: backend остановится на HTTPS validation. В Compose выбранный режим задан явно, переменная `ENVIRONMENT` из shell его не переопределяет.

Используйте отдельный shell без экспортированных application variables: они имеют приоритет над `--env-file`. Этот stack не использует локальный development `.env`. Все команды запускайте из checkout; не объединяйте `compose.prod.yaml` с `compose.yaml` и не используйте здесь `make up` / `make down`.

## Первый запуск

Для краткости определите shell function; повторите определение в каждой новой SSH-сессии:

```bash
prod() {
  docker compose --env-file .env.prod -f compose.prod.yaml "$@"
}
prod config --quiet
prod up -d --build --wait --wait-timeout 180
prod ps
prod exec -T nginx nginx -t
```

`config --quiet` проверяет конфигурацию без вывода secrets. Backend entrypoint выполняет `alembic upgrade head` перед запуском Uvicorn. PostgreSQL хранит данные в named volume проекта `event-registration-prod`; backend запускается ровно с одним Uvicorn worker. Worker и beat начинают работу после readiness backend и Redis. Не масштабируйте backend и beat и не запускайте второй проект для того же deployment.

Наружу опубликован только Nginx. Он проксирует frontend и `/api/` с одного origin; существующие login rate limit, proxy headers и SSE buffering/timeout settings сохраняются. Для контейнеров включены автоматический restart и ротация Docker logs. Mailpit в stack отсутствует.

## Проверка после запуска

Подставьте ваш домен:

```bash
curl --fail http://events.example.com/api/ready
curl --fail --output /dev/null http://events.example.com/
prod logs --tail=100 backend worker beat nginx
```

Ожидается `/api/ready` → `{"status":"ready"}` и HTTP 200 для frontend. Не публикуйте logs, если SMTP relay или приложение записали туда чувствительные данные.

В браузере откройте именно `APP_ORIGIN` и проверьте:

1. Регистрацию, вход, сохранение сессии после reload и logout. Вход по IP при настроенном origin домена будет отклонён проверкой Origin.
2. Создание и публикацию события, регистрацию участника, получение confirmation email через реальный SMTP relay.
3. Dashboard организатора: новое действие участника обновляет stats через SSE без reload страницы.

Readiness подтверждает доступ к БД, но не успешность SMTP delivery. Проверяйте доставку в почтовом ящике и ошибки worker. HTTP auth, SSE и доставка на вашем VPS требуют этой ручной проверки; локальный `make verify` не проверяет ваш DNS и внешний SMTP relay.

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
prod config --quiet
prod up -d --build --wait --wait-timeout 180
prod ps
```

Повторите readiness и браузерные проверки. Изменение `POSTGRES_PASSWORD` в env не меняет пароль уже инициализированной БД; для ротации нужна отдельная процедура изменения роли PostgreSQL.

Возврат старого checkout/image не откатывает Alembic migrations. При несовместимой схеме нужен план восстановления из backup; не выполняйте автоматический downgrade или удаление volume.

## Остановка и ограничения

```bash
prod down
```

Named volume БД сохраняется. Для следующего запуска используйте тот же checkout directory, env и project name. Не применяйте `down -v` или volume prune к этому deployment. Redis broker не хранится в persistent volume: при пересоздании Redis очередь теряется; confirmation/reminder scanners повторно ставят актуальные задачи в очередь.

Это временная публикация по HTTP с согласованным development security mode. Настройка HTTPS и переход на `ENVIRONMENT=production` — отдельная задача.
