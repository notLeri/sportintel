# SportIntel

Сбор и кластеризация спортивных и iGaming-новостей и праздников разных стран в события, AI-брифы на ru/en и публикация в Telegram-каналы — с одобрением редактора или автоматически.

**Развернуть на сервере или любой машине с Docker:** `cp .env.deploy.example .env` → заполнить → `docker compose up -d --build` — [deploy/README.md](deploy/README.md). Эксплуатация и масштабирование — [docs/OPERATIONS.md](docs/OPERATIONS.md).

**Железо (минимум):**

| Вариант | CPU | RAM | Диск |
|---|---|---|---|
| Без ИИ или с Anthropic API | 2 vCPU | 4 ГБ | 20 ГБ |
| С локальной Ollama (`qwen3:14b` + `gemma3:12b` для переводов) | 4+ vCPU (лучше GPU или Apple Silicon) | 16 ГБ+ | 40 ГБ (модели ~18 ГБ) |

ОС любая с Docker; наружу нужны порты 80 и 443. Ollama можно вынести на другую машину — тогда сервер остаётся в первой строке.

Документация: [архитектура](docs/ARCHITECTURE.md), [эксплуатация](docs/OPERATIONS.md), решения — [`docs/adr/`](docs/adr/).

## Как это работает

Режим по умолчанию — без ИИ и без платных сервисов (ADR-004): правила, шаблоны, лексическая кластеризация.

```
источники (RSS/HTML/Telegram-каналы) → статьи → обогащение правилами → события → [AI-бриф] → черновик → редактор → Telegram-канал
```

1. **Сбор.** Worker по расписанию опрашивает источники (`sources.schedule_due` → `ingestion.fetch_source`), извлекает текст статьи и отбрасывает дубли.
2. **Обогащение** (`intelligence.enrich_article`). Правила из `app_settings` определяют вид спорта, турнир, команды/игроков (по справочнику и алиасам), маркеры слухов и кликбейта, важность.
3. **Кластеризация** (`events.cluster_article`). Статья присоединяется к похожему событию (заголовок, сущности, турнир — пороги в ADR-003) или открывает новое. Кандидаты — только из того же региона (`sources.region`). Событие пересчитывает доверие к источникам (число независимых изданий и их уровень; источники «не доверяем» не учитываются), важность, заголовок и сводку — из основной статьи.
4. **AI-бриф** (`editorial.build_brief`, по кнопке в карточке события). LLM пишет бриф на языке интерфейса: что произошло, статус (официально / подтверждено / одно СМИ / слух), суть, кого касается, влияние, что делать. Ссылки на источники подставляет код по номерам, выбранным моделью; «подтверждено» требует ≥2 разных изданий. Статус проверки (и предупреждение «не подтверждено») видит только редактор — в Telegram-пост он не попадает. Автогенерация — `app_settings.briefs.auto_languages` (по умолчанию выключена).
5. **Черновики** (`editorial.autodraft_due` или вручную, в т.ч. «Пост из AI-брифа»). У каждой версии свой язык поста; редактор правит, утверждает. Лента `/feed` — готовые черновики.
6. **Публикация** (`editorial.publish_due`, раз в минуту). Каналы с расписанием (cron, UTC) и фильтрами (вид спорта, регион, важность, доверие). Режим «одобрение» — постит утверждённые черновики, «авто» — брифы (кроме слухов); можно дайджестом. Включается `FLAG_TELEGRAM_PUBLISH=true` + `TELEGRAM_BOT_TOKEN` — [настройка бота](docs/TELEGRAM_BOT_SETUP.md).

Все действия пишутся в историю (audit). LLM: `AI_PROVIDER=ollama` (локально, бесплатно; модель — `app_settings.llm_model`, по умолчанию `qwen3:14b`) или `anthropic` (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`). С `AI_PROVIDER=none` всё, кроме брифов, работает на правилах.

## Как пользоваться

Нужны: [uv](https://docs.astral.sh/uv/), Node.js 22 + pnpm 12, Docker (версии — `.tool-versions`), для брифов — [Ollama](https://ollama.com).

```bash
make setup && make db-start && make db-migrate   # один раз (db-migrate — и после обновления кода)
make api      # API :8000
make worker   # фоновые задачи (:8001 — только /healthz); без него нет новостей, брифов и публикаций
make ui       # UI на http://localhost:5173 (/api проксируется на :8000)
```

Каждую команду — в своём терминале. Для брифов с `AI_PROVIDER=ollama` должен работать `ollama serve` с моделью (`make llm-start`, `make llm-pull`). Остановить: Ctrl+C в терминале команды, `make stop` (api, worker, ui) или `make stop-all` (ещё Ollama и база). `address already in use` — порт занят старым процессом: `make stop`.

Вход локально — форма dev-login на `/login`: любой e-mail и роль (`admin` для первой настройки). Роли: researcher → editor → admin. Язык интерфейса — en (по умолчанию) или ru, переключается в меню пользователя; в нём же показываются заголовки событий и брифы. Непонятные элементы снабжены подсказками (наведение или «?»).

1. **Админка → Источники**: добавить RSS/сайт или публичный Telegram-канал (тип `html`, профиль `telegram`, лента `https://t.me/s/<канал>` — без API и ключей), указать регион и уровень доверия (официальный … «не доверяем»), нажать «Проверить», включить.
2. **Админка → Справочники**: команды, игроки, турниры и их алиасы (по ним правила узнают сущности; нераспознанные имена — в разделе «Несвязанные»).
3. **Админка → Настройки**: правила важности, пороги кластеризации, автодрафт — меняются без деплоя.
4. **Главная (события)**: фильтры (в т.ч. регион, доверие), поиск, карточка события: источники, AI-бриф, черновик поста; правка, слияние/перенос статей, ручное событие или статья по URL.
5. **Лента (`/feed`)**: готовые черновики → «Взять в работу» → правка → «Утвердить» → публикация каналом или вручную («Копировать» → «Опубликовано»).
6. **Автопостинг** (отдельная вкладка): переключатель автопостинга канала (новый канал создаётся выключенным), календарь на неделю — когда уйдёт следующий пост и что в очереди, справа — канал глазами подписчика (публичный `@username` читается с t.me, приватный — по журналу отправок) с запланированными постами внизу. Там же настройка канала (chat_id, язык постов — по умолчанию en, режим, расписание, фильтры), «Тест», «Запустить сейчас», журнал.
7. **Админка → Конвейер**: очереди, упавшие задачи (повтор), здоровье источников. **Аналитика** — полезные истории по людям и дням.

Алерты о тихих сбоях (источник молчит, очередь растёт) уходят в Telegram-чат, если заданы `ALERT_TELEGRAM_BOT_TOKEN` и `ALERT_TELEGRAM_CHAT_ID`, иначе — в лог.

## Структура

| Каталог | Что внутри |
|---|---|
| `backend/` | Python 3.12, FastAPI, модульный монолит (`src/sportintel/`) |
| `frontend/` | React 19 + Vite SPA |
| `deploy/` | Dockerfile, compose, манифесты платформы |
| `fixtures/` | RSS/HTML-фикстуры источников (contract, integration, e2e) |
| `evals/` | Размеченные датасеты для evals |
| `docs/` | Архитектура, эксплуатация, ADR |
| `.github/` | CI/CD |

## Команды

Все команды с описаниями — `make` (то же, что `make help`). Что сейчас запущено — `make status`. Старые имена (`make web`, `make fe`, `make up`, `make migrate`…) работают как синонимы.

Интеграционные тесты поднимают PostgreSQL (`pgvector/pgvector:pg16`) через testcontainers — нужен запущенный Docker. Если задан `TEST_DATABASE_URL`, используется он (так работает CI). С **Colima** на macOS:

```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
```

Pre-commit: ruff, end-of-file-fixer, trailing-whitespace, check-yaml, gitleaks, lint-staged для `frontend/`. Проверка всего дерева: `cd backend && uv run pre-commit run --all-files`.

## Frontend: запуск

```bash
cd frontend
pnpm install      # pnpm 12 (packageManager в package.json), Node 22+
pnpm dev          # http://localhost:5173; /api и /auth проксируются на http://localhost:8000
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

Слои FSD (`app → pages → features → entities → shared`) проверяет ESLint (`eslint-plugin-boundaries`): импорт только вниз, слайс — только через его `index.ts`. UI-примитивы shadcn/ui лежат в `src/shared/ui` (`components.json` настроен на этот путь). В `import.meta.env` допустимы только публичные `VITE_SENTRY_DSN` и `VITE_VERSION`.

## Docker

Один образ на все роли (`deploy/Dockerfile`, multi-stage, non-root uid 10001): `web` (API + собранный SPA), `worker`, `migrate`, `admin`.

Боевая установка — корневой `compose.yaml` (HTTPS, бэкапы, автоперезапуск): [deploy/README.md](deploy/README.md). Ниже — то, что нужно для разработки.

```bash
make db-start       # только PostgreSQL для разработки
make docker-all     # migrate → web (http://localhost:8000, с SPA) + worker в контейнерах
make docker-image   # образ sportintel:<git sha>
docker build -f deploy/Dockerfile --target fe-maps -o maps .   # source maps для Sentry
```

Все источники в статусе degraded с ошибкой `ssrf_blocked`? Скорее всего, включён VPN с fake-ip DNS (Clash, sing-box, Surge). Добавьте в `.env` строку `SAFE_FETCH_ALLOW_FAKE_IP=true` и перезапустите `make docker-all`. Второй вариант — переключить DNS в VPN-клиенте на redir-host / real-ip.

### Локальная LM (опционально, ADR-004)

```bash
make llm-pull      # скачать qwen3:14b в Ollama на Mac (LLM_MODEL=gemma3:12b — другую)
make llm-models    # что скачано и что загружено в память
make llm-docker    # альтернатива: Ollama в Docker + qwen3:14b и bge-m3
make eval-briefs   # сравнить модели на evals/datasets/briefs_v1.jsonl (MODELS="ollama:qwen3:14b ollama:gemma3:12b")
```

На Mac Ollama нативно (Metal) быстрее, чем в Docker: `brew install ollama`, `ollama serve`. Нужно ~16 ГБ RAM; бриф — ~50 с на M4. Отчёты сравнения — `evals/reports/`. LM не обязана жить рядом с приложением: `OLLAMA_URL` может указывать на отдельную локальную VM/сервер или ноутбук с Ollama, доступный worker по сети (например, через Tailscale). Порт Ollama не публикуется в интернет — доступ только из сети worker. Включение по шагам — `app_settings.ai_routing` (CONV §3).

## CI

`.github/workflows/ci.yml`: jobs `backend` (ruff, mypy, import-linter, миграции с нуля и одна голова, pytest с покрытием на service-PostgreSQL), `frontend` (lint, typecheck, test, build, check:api), `contract` (`openapi.json` ↔ backend ↔ TS-типы), `security` (gitleaks, pip-audit, pnpm audit), `image` (buildx `linux/amd64`, smoke migrate → web → `/healthz`, `/readyz`, SPA). Path filters пропускают нетронутые части; пропущенный job отдаёт Success.

**Защита `main`** (включить в настройках GitHub после публикации репозитория): обязательные проверки `backend`, `frontend`, `contract`, `security`, `image`; линейная история; squash merge. Локально `main` собирается merge-коммитами с тегами `done/*` (раздел ниже) — при переходе на GitHub это заменяется PR со squash.

## Вход

**По e-mail и паролю** — всегда (ADR-005). Первый admin — `BOOTSTRAP_ADMIN_EMAIL` + `INITIAL_ADMIN_PASSWORD` при старте web. Остальным пароли задаёт admin в «Пользователях». Аварийный сброс: `docker compose run --rm web admin set-password <email>`.

**Через Google (OIDC)** — если заданы все три `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`; иначе кнопки Google нет. В `local`, `ci`, `e2e` используется `FakeOidcProvider` (без сети). Допуск: существующий активный пользователь, домен email из `OIDC_ALLOWED_DOMAINS` (роль researcher) или `BOOTSTRAP_ADMIN_EMAIL` (admin, пока нет ни одного admin).

**Настройка OAuth client в Google Cloud Console:**
1. APIs & Services → OAuth consent screen: тип **Internal** (только пользователи Workspace) или External + тестовые пользователи.
2. Credentials → Create credentials → OAuth client ID → **Web application**.
3. Authorized redirect URIs — строго `APP_BASE_URL + /auth/callback` для каждого окружения, например `https://staging.example.com/auth/callback` и `https://app.example.com/auth/callback`.
4. Client ID и secret — в Secret Manager / env (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`), `OIDC_ISSUER=https://accounts.google.com`.

## Очередь задач

Фоновые задачи — Procrastinate в схеме `procrastinate` той же БД; задачи объявлены в `modules/*/jobs.py`. `make worker` запускает в одном процессе три worker: основной (служебные, `ai`, `cluster`), `fetch` (`WORKER_FETCH_CONCURRENCY` — чтобы паузы вежливости к сайтам не держали остальное) и `ai_interactive` (`WORKER_INTERACTIVE_CONCURRENCY`).

```sql
-- что в очереди и что сломалось
SELECT queue_name, task_name, status, count(*)
FROM procrastinate.procrastinate_jobs GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- последние упавшие задачи
SELECT id, task_name, args, attempts, scheduled_at
FROM procrastinate.procrastinate_jobs WHERE status = 'failed' ORDER BY id DESC LIMIT 20;
```

Задачи ставятся после коммита (`uow.enqueue_after_commit`); если процесс упал между коммитом и постановкой, задачу вернёт периодическая сверка `platform.reconcile` (каждые 5 мин, заодно перезапускает задачи «зависших» worker).


## Конфигурация

Переменные окружения читаются только в `backend/src/sportintel/platform/config.py` (локально — из `.env`, шаблон `.env.example`; файл подхватывает `uv run --env-file`, сам `Settings` `.env` не читает). Ошибка конфигурации → лог `config.invalid` со списком полей и `exit 1`. Runtime-настройки бизнеса — таблица `platform.app_settings`. Секреты в репозиторий не коммитятся.

Источник истины — `platform/config.py`; при изменении править и эту таблицу.

| Переменная | Тип | Обязательна | По умолчанию | Описание |
|---|---|---|---|---|
| `ENV` | `local\|ci\|e2e\|staging\|production` | да | — | Окружение |
| `VERSION` | str | нет | `dev` | git sha, вшивается при сборке образа |
| `DATABASE_URL` | str (`postgresql+psycopg://…`) | да | — | Роль `app` |
| `DATABASE_URL_MIGRATOR` | str | нет | = `DATABASE_URL` | Роль `migrator`, используется только `alembic` |
| `DB_POOL_SIZE` | int | нет | 10 | Пул SQLAlchemy на процесс |
| `APP_BASE_URL` | URL | да | — | Публичный URL (для OIDC redirect) |
| `OIDC_ISSUER` | URL | да вне `local/ci/e2e` | — | |
| `OIDC_CLIENT_ID` | str | да вне `local/ci/e2e` | — | |
| `OIDC_CLIENT_SECRET` | secret | да вне `local/ci/e2e` | — | |
| `OIDC_ALLOWED_DOMAINS` | csv | нет | пусто | Домены e-mail, допускаемые без allowlist |
| `BOOTSTRAP_ADMIN_EMAIL` | email | нет | — | Получает роль admin при первом входе |
| `DEV_LOGIN_ENABLED` | bool | нет | false | Разрешено **только** при `ENV ∈ {local, e2e}`, иначе старт падает |
| `AI_PROVIDER` | `none\|ollama\|fake\|anthropic` | нет | `none` | ADR-004: где выполняются шаги `llm`; `none` — правила и шаблоны |
| `OLLAMA_URL` | URL | если `ollama` | `http://localhost:11434` | Машина с Ollama (та же VM, отдельная VM, ноутбук через туннель) |
| `OLLAMA_TIMEOUT_S` | int | нет | 180 | Таймаут вызова LM |
| `OLLAMA_CONCURRENCY` | int | нет | 1 | Параллельные вызовы LM на worker |
| `ANTHROPIC_API_KEY` | secret | если `AI_PROVIDER=anthropic` | — | |
| `ANTHROPIC_MODEL` | str | нет | `claude-haiku-5-5` | Модель для брифов при `AI_PROVIDER=anthropic` |
| `EMBEDDINGS_PROVIDER` | `none\|ollama\|fake\|voyage` | нет | `none` | `none` — кластеризация лексическая |
| `VOYAGE_API_KEY` | secret | если `voyage` | — | |
| `AI_RECORD` | bool | нет | false | Только `local`: запись фикстур fake-AI |
| `SENTRY_DSN` | secret | нет | — | Пусто → Sentry выключен |
| `ALERT_TELEGRAM_BOT_TOKEN` | secret | нет | — | Пусто → алерты только в лог |
| `ALERT_TELEGRAM_CHAT_ID` | str | нет | — | |
| `TELEGRAM_BOT_TOKEN` | secret | для публикации | — | Бот публикации в каналы; нужен ещё `FLAG_TELEGRAM_PUBLISH=true` |
| `FETCH_USER_AGENT` | str | нет | `SportIntelBot/1.0 (+<APP_BASE_URL>/bot)` | |
| `WORKER_CONCURRENCY` | int | нет | 4 | Параллелизм worker |
| `WORKER_INTERACTIVE_CONCURRENCY` | int | нет | 2 | Отдельный лимит для очереди `ai_interactive` |
| `WORKER_FETCH_CONCURRENCY` | int | нет | 4 | Отдельный лимит для очереди `fetch` |
| `LOG_LEVEL` | str | нет | `INFO` | |
| `LOG_FORMAT` | `json\|console` | нет | `console` в local, иначе `json` | |
| `SAFE_FETCH_ALLOW_HOSTS` | csv | нет | пусто | **Только `ENV=e2e`**: хосты, для которых SSRF-проверка приватных IP отключена (INFRA-T5.1). В других окружениях непустое значение → ошибка конфигурации |
| `SAFE_FETCH_ALLOW_FAKE_IP` | bool | нет | `false` | **Только `ENV=local`**: пропускать адреса fake-ip DNS у VPN-клиентов (`198.18.0.0/15`, `240.0.0.0/4`), иначе все источники падают с `ssrf_blocked`. Остальные SSRF-проверки, порты и редиректы проверяются как обычно. В других окружениях `true` → ошибка конфигурации |
| `STATIC_DIR` | path | нет | `/app/static` | Каталог собранного SPA (INFRA-T0.10) |
| `PORT` | int | нет | 8000 | Порт HTTP (web; worker отвечает на нём `/healthz` для Cloud Run, `make worker` ставит 8001) |
| `CSP_MODE` | `report-only\|enforce` | нет | `report-only` | Режим CSP (BE-T5.5) |
| `FLAG_<NAME>` | bool | нет | false | Feature flags (CONV §9) |

## Лицензия

[MIT](LICENSE)
