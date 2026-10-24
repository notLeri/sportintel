# Развёртывание SportIntel

Один и тот же способ на любой машине с Docker: Linux-сервер, Mac, Windows (WSL2).
Всё поднимается одной командой из корня репозитория: `docker compose up -d --build`.

| Окружение | Для чего | Как запускать |
|---|---|---|
| **production** | рабочая установка | `compose.yaml` + `.env` с `ENV=production` (этот документ) |
| **staging** | проверка перед выкатом, есть `/api/v1/docs` | то же, `ENV=staging`, отдельный сервер или домен |
| **local (всё в Docker)** | показать продукт на своём компьютере | то же, `DOMAIN=localhost` |
| **разработка** | писать код | `make setup`, `make api`, `make worker`, `make ui` — корневой [README](../README.md) |

## Что поднимается

```
Интернет ──443/80──▶ caddy (HTTPS, Let's Encrypt) ──▶ web (API + интерфейс)
                                                        │
                       worker (сбор, события, ИИ, публикация) ──▶ db (PostgreSQL 16 + pgvector)
                       backup (pg_dump раз в сутки → ./backups) ──┘
                       ollama (опционально, профиль llm)
```

- `migrate` — разовый: применяет миграции (и засевает источники и справочники) перед стартом web и worker.
- База наружу не открыта. Наружу смотрит только Caddy (порты 80 и 443).
- Данные лежат в Docker volumes `pgdata`, `caddy_data` (сертификаты) и `ollama_models`, а также в папке `./backups`.

## 1. Требования

- **Docker:** Docker Engine с плагином compose v2 (Linux) или Docker Desktop (macOS, Windows). На Windows репозиторий держите **внутри WSL2** (`~/…`), а не на `C:\`: так быстрее и не портятся права и переводы строк.
- **Ресурсы:** 2 vCPU, 4 ГБ RAM и 20 ГБ диска без локального ИИ. С Ollama (`COMPOSE_PROFILES=llm`) нужно **16 ГБ RAM и больше** и 40 ГБ диска (две модели ~18 ГБ).
- **Сеть:** домен с A-записью (и AAAA, если есть IPv6) на IP сервера. Порты **80 и 443** открыты: 80 нужен, чтобы Let's Encrypt выдал сертификат.

Установка Docker на чистый Ubuntu/Debian: `curl -fsSL https://get.docker.com | sh`. Затем выйдите из сессии и зайдите снова после `sudo usermod -aG docker $USER`.

## 2. Установка

```bash
git clone <url-репозитория> sportintel && cd sportintel
cp .env.deploy.example .env
# заполнить в .env: DOMAIN, POSTGRES_PASSWORD, BOOTSTRAP_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD, блок ИИ
docker compose up -d --build
```

- Первая сборка занимает 5–10 минут: собираются фронт и бэкенд. Следующие быстрее — слои кэшируются.
- Если обязательная переменная не задана, compose сразу остановится и назовёт её (`set DOMAIN in .env`).
- Пароль базы: `openssl rand -hex 24`. Только буквы и цифры, потому что пароль входит в URL подключения.

## 3. Проверка

```bash
docker compose ps        # db, web, worker, caddy, backup — running (healthy); migrate — exited (0)
```

1. Откройте `https://<DOMAIN>` и войдите как `BOOTSTRAP_ADMIN_EMAIL` с паролем `INITIAL_ADMIN_PASSWORD`.
2. **Админка → Источники → «Проверить»** у пары источников. Через несколько минут на главной появятся события.
3. **Админка → Пользователи:** пригласите редакторов и задайте им пароли.
4. Telegram-публикация — [docs/TELEGRAM_BOT_SETUP.md](../docs/TELEGRAM_BOT_SETUP.md). Затем в `.env`: `TELEGRAM_BOT_TOKEN=…`, `FLAG_TELEGRAM_PUBLISH=true` и `docker compose up -d`.

Админ создаётся из `.env` только один раз, пока в системе нет ни одного активного администратора. После этого `INITIAL_ADMIN_PASSWORD` можно стереть из `.env`.

## 4. Ежедневные команды

Все команды выполняются из корня репозитория.

| Задача | Команда |
|---|---|
| Состояние сервисов | `docker compose ps` |
| Логи (последние, в реальном времени) | `docker compose logs -f --tail=100 web worker` |
| **Обновить до новой версии** | `docker compose run --rm backup once` → `git pull` → `docker compose up -d --build` |
| Применить изменения `.env` | `docker compose up -d` |
| Перезапустить всё | `docker compose restart` |
| Остановить (данные сохраняются) | `docker compose down` |
| Бэкап прямо сейчас | `docker compose run --rm backup once` |
| Сбросить пароль / создать пользователя | `docker compose run --rm web admin set-password you@corp.com [--role admin]` |
| Консоль базы | `docker compose exec db psql -U sportintel` |
| Очередь задач и сбои | **Админка → Конвейер** (или SQL из корневого README, раздел «Очередь задач») |

При обновлении миграции применяются сами: `migrate` выполняется до старта web и worker. Если миграция упадёт, web и worker останутся на старой версии и не запустятся с новой. Смотрите `docker compose logs migrate`.

## 5. Бэкапы и восстановление

- Сервис `backup` делает `pg_dump` при старте и затем каждые `BACKUP_INTERVAL_H` часов (по умолчанию 24). Дампы пишутся в `./backups/sportintel-<время UTC>.dump`, хранятся последние `BACKUP_KEEP` (14).
- Если свежего дампа нет дольше интервала плюс 2 часа, `backup` в `docker compose ps` становится **unhealthy**.
- **Копируйте `./backups` за пределы сервера** (rsync, rclone, объектное хранилище). Дамп на том же диске не спасёт при потере сервера.

Восстановление (например, на новом сервере после установки по шагу 2):

```bash
docker compose stop web worker
docker compose run --rm backup restore /backups/sportintel-20261012T030000Z.dump
docker compose up -d
```

Проверяйте восстановление хотя бы раз в квартал: поднимите копию на отдельной машине и войдите в неё.

## 6. Искусственный интеллект

Вариант выбирается в `.env`. Применить: `docker compose up -d`.

| Вариант | `.env` | Заметки |
|---|---|---|
| Без ИИ | `AI_PROVIDER=none` | правила и шаблоны; брифов и переводов нет |
| Anthropic | `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…` | платно, быстро |
| Ollama на этом сервере | `AI_PROVIDER=ollama`, `COMPOSE_PROFILES=llm` | модели скачиваются сами (`ollama-pull`): `LLM_MODEL` (брифы, `qwen3:14b`) и `TRANSLATION_MODEL` (переводы, `gemma3:12b`), ~18 ГБ; ≥16 ГБ RAM; без GPU бриф идёт минуты |
| Ollama на другой машине | `AI_PROVIDER=ollama`, `OLLAMA_URL=http://<ip>:11434` | порт Ollama не открывать в интернет — только частная сеть (Tailscale) |

Модели, которые использует приложение, задаются в **Админка → Настройки** (`llm_model`, `translation_model`). Они должны совпадать с `LLM_MODEL` и `TRANSLATION_MODEL`.

## 7. Вход

- **По e-mail и паролю** работает всегда. Пароли задаёт администратор в «Пользователях» или командой `set-password`. После 5 неудачных попыток за 15 минут вход для этой пары e-mail и IP блокируется на оставшееся время окна.
- **Google (OIDC)** включается, если заданы все три `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` (корневой README, раздел «Вход»). Если не задана ни одна, кнопки Google нет. Если задана часть, web не стартует и называет недостающие.

## 8. Отказоустойчивость: что уже сделано

| Сбой | Что происходит |
|---|---|
| Процесс упал или сервер перезагрузился | `restart: unless-stopped`: всё поднимается само, в правильном порядке (db → migrate → web/worker → caddy) |
| База временно недоступна | web не падает и отвечает 503 на `/readyz`, после возврата базы работает дальше. worker перезапускается Docker-ом. Зависшие задачи возвращает сверка `platform.reconcile` (каждые 5 мин) |
| Перезапуск или обновление web | Caddy держит запросы до 30 с, пока web не вернётся, вместо мгновенного 502 |
| Остановка worker | SIGTERM: worker перестаёт брать задачи и дорабатывает текущие (до 90 с) |
| Диск забивается логами | ротация: 5 × 10 МБ на контейнер |
| Потеря данных | ежедневный дамп, 14 копий, healthcheck «свежий дамп есть» |
| Перезапуск Caddy | сертификаты в volume `caddy_data`, лимиты Let's Encrypt не тратятся |
| Тихие сбои (источник молчит, очередь растёт) | оповещение в Telegram при `ALERT_TELEGRAM_*` |

**Чего нет — это ограничения одной машины:**
- Сервер — единая точка отказа: если он умер, сервис недоступен до восстановления из бэкапа на новом сервере. Время восстановления — минуты плюс копирование дампа.
- Потеря данных — не больше чем за `BACKUP_INTERVAL_H` часов.

Как убрать эти ограничения — [docs/OPERATIONS.md](../docs/OPERATIONS.md), раздел «Масштабирование».

Рекомендуется внешний мониторинг: любой бесплатный uptime-сервис, проверяющий `https://<DOMAIN>/readyz` раз в минуту.

## 9. Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `set DOMAIN in .env` (или другая переменная) | не заполнен `.env`, см. шаг 2 |
| Сайт не открывается, в `docker compose logs caddy` ошибки ACME | DNS ещё не указывает на сервер или закрыты порты 80/443. Проверьте `dig <DOMAIN>` и файрвол |
| `bind: address already in use` на 80/443 | порт занят другим веб-сервером (nginx, apache). Остановите его |
| web `unhealthy`, в логах ошибки подключения к базе | смотрите `docker compose logs db migrate`. Если `POSTGRES_PASSWORD` сменили после первого запуска, база помнит старый: верните его |
| `migrate` exited (1) | `docker compose logs migrate`. Обновление остановлено, данные не тронуты |
| Ollama падает или очень медленно | мало RAM. Возьмите модель меньше (`LLM_MODEL=gemma3:4b` и то же в настройках) или Anthropic |
| Windows: `/bin/sh^M: bad interpreter` | репозиторий склонирован с CRLF вне WSL. Клонируйте внутри WSL2 |
