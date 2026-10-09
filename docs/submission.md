# Project Submission

## 1. Ссылка на repository

https://github.com/nbaishev/event-registration

Основная ветка: `master`.

## 2. Инструменты и модели

**Подготовка требований и архитектуры:** ChatGPT, **GPT-5.6 Sol**. Использовался для анализа требований, выбора архитектуры и подготовки Product Spec. Я выбрал ChatGPT для обсуждения проекта в формате командного review: уточнять требования, сравнивать варианты и проверять решения до начала кодирования. Также общение в чате на тратит лимиты Codex.

**Разработка:** Codex, **GPT-6.1 Sol**. Использовался для подготовки планов, реализации, запуска tests и исправлений после review. Codex: читает существующий код, вносит изменения и запускает через субагентов независимые проверки. GPT-6.1 Sol пишет качественный код и при этом затраты на токены оптимальные. Также OpenAI предоставляет бесплатные сбросы лимитов.

## 3. Промпты и ход работы

Ниже задачи расположены по времени начала. Названия кратко описывают содержание запросов; исходные тексты находятся по ссылкам.

| Дата | Запрос / этап | Журнал |
|---|---|---|
| 04.10.2026 | Требования, архитектура и правила разработки | [Project documents](development-log/2026-10-04-initial-project-document.md) |
| 04.10.2026 | Основа проекта и quality gates | [Foundation](development-log/2026-10-04-project-foundation.md) |
| 04.10.2026 | Регистрация аккаунта | [Auth register](development-log/2026-10-04-auth-register.md) |
| 04.10.2026 | Вход и выход | [Login / logout](development-log/2026-10-04-auth-login-logout.md) |
| 05.10.2026 | Обновление авторизации | [Auth refresh](development-log/2026-10-05-auth-refresh.md) |
| 05.10.2026 | Планирование управления мероприятиями | [Events planning](development-log/2026-10-05-day2-events-planning.md) |
| 05.10.2026 | Создание черновика мероприятия | [Draft creation](development-log/2026-10-05-event-draft-create.md) |
| 06.10.2026 | Редактирование черновика | [Draft editing](development-log/2026-10-06-event-draft-edit.md) |
| 06.10.2026 | Исправления редактирования | [Draft corrections](development-log/2026-10-06-event-draft-edit-bugfixes.md) |
| 06.10.2026 | Публикация и публичная страница | [Event publishing](development-log/2026-10-06-event-publish.md) |
| 06.10.2026 | Исправление auth-refresh E2E | [E2E correction](development-log/2026-10-06-auth-refresh-e2e.md) |
| 06.10.2026 | Регистрация, билет и очередь ожидания | [Registration](development-log/2026-10-06-event-registration.md), [публикация PR](development-log/2026-10-06-event-registration-pr.md) |
| 06–07.10.2026 | Отмена регистрации и продвижение очереди | [Cancellation / promotion](development-log/2026-10-06-registration-cancel.md) |
| 07.10.2026 | Изменение вместимости | [Event capacity](development-log/2026-10-07-event-capacity.md) |
| 07.10.2026 | Синхронизация auth-refresh E2E | [E2E synchronization](development-log/2026-10-07-auth-refresh-e2e-sync.md) |
| 07.10.2026 | Список собственных регистраций | [My registrations](development-log/2026-10-07-my-registrations.md) |
| 07.10.2026 | Исправление auth-refresh E2E в CI | [CI correction](development-log/2026-10-07-auth-refresh-e2e-ci.md) |
| 07.10.2026 | Удаление пустого черновика | [Draft deletion](development-log/2026-10-07-event-draft-delete.md) |
| 07.10.2026 | Изоляция login limiter в E2E | [Login rate isolation](development-log/2026-10-07-e2e-login-rate-isolation.md) |
| 07.10.2026 | Устранение повторных запусков test suites | [Verification deduplication](development-log/2026-10-07-verification-suite-deduplication.md) |
| 08.10.2026 | Check-in по билету | [Check-in](development-log/2026-10-08-check-in.md) |
| 08.10.2026 | Статистика организатора | [Organizer statistics](development-log/2026-10-08-organizer-stats.md) |
| 08.10.2026 | SSE для обновления статистики | [Statistics SSE](development-log/2026-10-08-stats-sse.md) |
| 08.10.2026 | Live dashboard и восстановление соединения | [Dashboard reconnect](development-log/2026-10-08-live-dashboard-reconnect.md) |
| 08.10.2026 | Письмо с подтверждением и билетом | [Confirmation email](development-log/2026-10-08-confirmation-email.md) |
| 08.10.2026 | Email-напоминания | [Reminder email](development-log/2026-10-08-reminder-email.md) |
| 09.10.2026 | Отдельный E2E job в CI | [E2E CI job](development-log/2026-10-08-ci-e2e-job.md) |
| 09.10.2026 | Перенос опубликованного мероприятия | [Rescheduling](development-log/2026-10-09-event-reschedule.md) |
| 09.10.2026 | Отмена мероприятия | [Event cancellation](development-log/2026-10-09-event-cancellation.md) |
| 09.10.2026 | Доступ по домену на VPS | [Domain access](development-log/2026-10-09-domain-access.md) |
| 09.10.2026 | Production HTTPS и Certbot | [HTTPS deployment](development-log/2026-10-09-production-https-certbot.md) |
| 09.10.2026 | Исправление dashboard E2E в CI | [Dashboard CI correction](development-log/2026-10-09-live-dashboard-refresh-ci.md) |


## 4. Описание проекта и развёртывание

Сервис регистрации на мероприятия на **FastAPI, PostgreSQL и React**. Фоновые задачи выполняются через **Celery и Redis**.

Реализованы аккаунты, создание и публикация мероприятий, регистрация участников, очередь ожидания с автоматическим продвижением, билеты, check-in, live-статистика и email-уведомления.

**Рабочая версия:** https://aian.space

Для проверки начните с https://aian.space/register.

### Локальный запуск

Требуются Python 3.12, uv, Node.js 22.13+, Corepack, Docker Compose и make. Точные версии и конфигурация описаны в [README](../README.md).

```bash
git clone https://github.com/nbaishev/event-registration.git
cd event-registration
make bootstrap
make up
```

- Frontend: http://localhost:8080/register
- API documentation: http://localhost:8080/api/docs
- Миграции выполняются автоматически.
- Остановка: `make down`; данные PostgreSQL сохраняются.

## 5. Следующий этап и почему

1. **Улучшить UI.**. Сейчас интерфейс минималистичный и не понятный пользователю.
2. **Добавить надёжную доставку уведомлений.** Это уменьшит риск потери писем при сбоях брокера или SMTP.
3. **Добавить восстановление пароля, email verification и отзыв сессий.** Это необходимо для самостоятельного обслуживания аккаунтов и управления доступом.
4. **Добавить QR-билеты и расширить E2E coverage.** QR упростит check-in, а дополнительные сценарии снизят риск регрессий.
5. **Добавить CD.**. Чтобы автоматизировать deploy в production.