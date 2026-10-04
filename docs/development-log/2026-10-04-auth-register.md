# Регистрация аккаунта (Auth Register)

Начало: `2026-10-04T21:09:34+05:00`
Завершение: `2026-10-04T21:37:42+05:00`

## Исходный запрос

План: `docs/superpowers/plans/2026-10-04-auth-register.md`

Запрос (JSON сохраняет исходный пробел в конце):

```json
"Выполни задачу [2026-10-04-auth-register.md](docs/superpowers/plans/2026-10-04-auth-register.md) "
```

## Ход работы

- 2026-10-04T21:09:34+05:00 — Foundation PR #2 объединён; создана feat/auth-register от master ba25f5e в отдельном рабочем дереве. Обязательные документы прочитаны.

## Проверки

Исходные `make bootstrap` и `make check` — код 0; 6 модульных тестов backend, 3 компонентных теста frontend; `OpenAPI drift: none.` Использованы ранее настроенные Corepack 0.34 и кеши в /tmp. Chromium bootstrap не устанавливает. Исходных ошибок нет.

## Решения и отклонения

- План содержит одну задачу/границу PR и шесть последовательных шагов; журнал прогресса отслеживает эти шаги. Общие интерфейсы: нормализованный User → API UserResponse → generated types → форма; CSRF middleware должен сработать до разбора тела.

## Результат

В работе. Auth login/logout/refresh и бизнес-таблицы не входят в задачу.

## Pull Request

https://github.com/nbaishev/event-registration/pull/3

Базовая ветка: master. Ветка изменений: feat/auth-register.

## Промежуточные результаты TDD

- Валидация/Argon2id RED: 8 failed, 2 passed; после реализации GREEN: 10 passed.
- User migration RED: 1 failed, 19 passed; отсутствовала таблица users. После добавления миграции проверка схемы прошла.
- CSRF/API RED: 71 failed, 22 passed; маршруты отсутствовали, unsafe-запросы не блокировались, APP_ORIGIN принимал path.
- Исправлен тестовый ввод: httpx2 не отправляет Unicode cookie через обычный cookie API (UnicodeEncodeError до вызова приложения). В HTTP-матрице используется испорченный ASCII token; это сохраняет проверку несовпадения CSRF.
- TestClient в сетевой песочнице зависал; остановлен только процесс этого теста, последующие запуски выполняются с расширенными разрешениями.

- Компонентные тесты формы: RED 4 failed (форма отсутствовала) → GREEN 6 passed в полном frontend suite. Селекторы меток уточнены для обязательных полей MUI со звёздочкой.
- E2E RED: 2 failed, 4 passed; реальный браузер отправлял origin динамического порта, backend стенда ожидал localhost:8080. Исправление касается только verification harness: APP_ORIGIN равен фактическому E2E origin; backend пересоздаётся, Nginx перезапускается для обновления адреса backend. Строгая защита приложения сохранена.

- Перезапуск Nginx с ephemeral mapping в Docker Desktop сменил опубликованный порт: второй E2E дал ECONNREFUSED. Стенд теперь фиксирует уже выделенный порт в APP_PORT и пересоздаёт Nginx вместе с backend; это сохраняет exact Origin и актуальное разрешение адреса backend.

## Полная проверка перед ревью

Дата: `2026-10-04T21:28:51+05:00`

- `make api-generate` — код 0 — schema.d.ts создан из текущего FastAPI OpenAPI.
- `make test` — код 0 — `93 passed in 4.85s`, frontend `3 passed` до добавления формы. После добавления формы итоговый verify подтвердил `6 passed`.
- `make check` — код 0 — Ruff, mypy, ESLint, TypeScript; 77 модульных и 6 компонентных тестов; `OpenAPI drift: none.`
- `make e2e` — код 0 — `6 passed (4.4s)`; регистрация/дубликат/CSRF через Nginx; изолированные ресурсы удалены.
- `make migrate` — код 0 — `alembic upgrade head` выполнен в новой изолированной PostgreSQL; удалены только ресурсы проекта auth-register-migration-9f0935be593f. Development DB не затрагивалась.
- `make verify` — код 0 — `77 passed in 2.04s` в unit gate; полный backend `93 passed in 4.70s`; frontend `6 passed`; Playwright `6 passed (3.9s)`; `OpenAPI drift: none.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`; frontend/Docker builds, nginx -t и удаление изолированного проекта выполнены.

Скриншот формы до заполнения: `.verification/register-page.png` (локальный артефакт, не содержит введённых данных).

Результат реализации: register API/UI, User migration, Argon2id, CSRF/Origin и безопасные ошибки реализованы; после register — /login без auth cookies. Далее — независимое ревью всей ветки.

Подготовленные изменения просмотрены: только безопасные тестовые реквизиты; .env, кеши и артефакты исключены. Поиск private keys/access tokens ничего не обнаружил. Исходный пробел запроса сохранён JSON-строкой для устранения trailing whitespace.

## Независимое ревью и исправления

- Ревью d58bd8d: Critical отсутствуют; два Important — возможная утечка hash в SQL traceback и стандартный auth 500 без JSON/no-store; Minor отсутствуют.
- `uv run --frozen --project backend pytest backend/tests/unit/test_auth_errors.py -q` — RED, код 1, `3 failed`: подтверждены оба замечания и видимость SQL parameters.
- Исправления: engine скрывает SQL parameters; repository преобразует SQLAlchemy errors после rollback в безопасный 503; auth middleware возвращает безопасный JSON 500/no-store, журналирует только класс ошибки без текста/traceback. OpenAPI дополнен 500/503 ErrorResponse; success contract не изменён. Детали неожиданных ошибок намеренно не журналируются, чтобы не раскрывать реквизиты или значения строки БД.
- `uv run --frozen --project backend pytest backend/tests/unit -q` — GREEN, код 0, `80 passed in 2.31s`; fault-injection проверяет ответ, rollback и отсутствие hash/plaintext в захваченном журнале.
- Повторный `make api-generate` — код 0; обновлены generated responses 500/503.
- Итоговый `make verify` — код 0: `80 passed in 2.19s` в unit gate; backend `96 passed in 4.70s`; frontend `6 passed`; E2E `6 passed (3.7s)`; `OpenAPI drift: none.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`; сборки, nginx -t и удаление изолированных ресурсов прошли.
- 2026-10-04T21:37:42+05:00 — все Important исправлены одним проходом RED → GREEN и подтверждены полным gate. Повторное ревью не выполнялось. Скриншот пустой формы добавлен в docs/screenshots/auth-register.png для PR.

Решения по вопросам, отложенным ревью:

- Login/logout/refresh, JWT cookies и verification/recovery остаются следующими задачами по утверждённой декомпозиции; цена выхода за эту границу — совмещение разных PR и контрактов.
- Production TLS и массовые запросы относятся к отдельным задачам; application limiter не добавлен согласно scope discipline. Ограничение: текущий Compose предназначен для локальной разработки.
- Скриншот вне диапазона первого ревью просмотрен основным исполнителем: пустая форма, без введённых данных; это документальный артефакт для PR.

Итог: Auth Register реализован в отдельной feat/auth-register от master. Единственное изменение test harness — согласование exact Origin с фактическим выделенным портом. Цена ошибки этого решения — E2E перестаёт представлять реальный same-origin сценарий; положительный и отрицательный E2E проходят без обхода защиты. Известные ограничения: login пока не реализован; production TLS и защита от массовых запросов вне задачи. Minor не отложены.

2026-10-04T21:41:03+05:00 — создан PR #3 через коннектор GitHub. Удалённый коммит 1712827 и локальный 533097c имеют одинаковое дерево b40a9d8dac5093b282f6ce0b2616962388c206c4; метаданные коммитов различаются. CI запускается автоматически; актуальный статус доступен в PR. Эта запись добавляет только сведения о публикации.

## Исправление APP_ORIGIN после ревью

Начало: `2026-10-04T22:28:56+05:00`

Уточняющий запрос:

Исправь обработку `APP_ORIGIN`.

Сейчас `AnyHttpUrl` валидирует и канонизирует URL, но сохраняется исходная строка. Из-за этого, например, `https://Example.com` не совпадает с браузерным `Origin: https://example.com` и возникает `CSRF_INVALID`.

Нужно:

- сохранять канонический origin после валидации;
- учитывать default ports (`:80`, `:443`);
- не допускать path/query/fragment в `APP_ORIGIN`;
- добавить тесты на эти случаи.

Не меняй остальную CSRF-логику.

Объём правки: Settings и регрессионные тесты; middleware и CSRF comparison не меняются. Работа продолжается в feat/auth-register как исправление текущего PR #3.

- Исходный targeted suite Settings/CSRF — код 1, `5 failed, 58 passed`: локальный APP_ORIGIN настроен на localhost:8081, тесты ожидали 8080. Пользовательский .env не изменён; добавлена unit fixture, задающая тестовый origin и очищающая cache Settings.
- После изоляции origin новые тесты RED — код 1, `14 failed, 68 passed`: сохранение исходного регистра/default ports и принятие пустых query/fragment либо backslash path.
- Исправление: валидированный AnyHttpUrl используется как источник канонического origin; единственный автоматически добавленный `/` удаляется из сериализации. Явный path остаётся запрещённым; query/fragment проверяются по наличию, а не непустому значению.
- `uv run --frozen --project backend pytest backend/tests/unit -q` — GREEN, код 0, `99 passed in 2.01s`. Тесты включают lowercase host, default/non-default ports, IPv6, запрещённые URL components и прохождение существующего guard с браузерным canonical Origin.
- Производственная CSRF-логика не изменялась; новые HTTP-тесты используют существующий middleware. Полный gate выполняется.

- Первый полный gate — код 0: 115 backend, 6 frontend, 6 E2E. Дополнительный тест корневого backslash path дал RED `1 failed, 17 passed`: AnyHttpUrl превращает такой ввод в корневой `/`. Явные backslash в конфигурации также отклоняются; это завершает запрет обоих вариантов разделителя path. Итоговый gate повторяется после этой дополнительной регрессии.

Итоговый `make verify` — код 0: `100 passed in 4.19s` (unit), `116 passed in 4.88s` (полный backend), frontend `6 passed`, E2E `6 passed (3.5s)`; `OpenAPI drift: none.`; `Empty PostgreSQL upgrade, revision head and metadata drift: passed.`; сборки, nginx -t и удаление изолированных ресурсов прошли.

Завершение правки: `2026-10-04T22:37:16+05:00`. APP_ORIGIN сохраняется в браузерной канонической форме; explicit path/query/fragment отклоняются. CSRF comparison и middleware не изменены. Подготовленный diff просмотрен на секреты: только безопасные URL/синтетические token fixtures; .env исключён. Публикация — исправление существующего PR #3.
