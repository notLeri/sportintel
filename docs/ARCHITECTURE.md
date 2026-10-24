# Архитектура: Brazilian Sports Intelligence & Telegram Content Tool

> **ADR-004 (2026-10-07, `docs/adr/004-rules-first-local-llm.md`):** базовый режим — без платного ИИ: правила обогащения, лексическая кластеризация, экстрактивный summary, шаблонный черновик и лента «фейкового Telegram». LLM-части архитектуры (§ про AI gateway, промпты, grounding, бюджет) применяются только в опциональном режиме `llm` с **локальной** моделью через Ollama; адаптеры Claude/Voyage отложены. При конфликте с текстом ниже действует ADR-004 и код.

> Дата: 2026-10-03 · Исходный архитектурный замысел; детали реализации могли уйти вперёд — источник истины код.
> Документ описывает **только архитектуру**. Задачи реализации сюда намеренно не входят.

**Где найти требуемые артефакты:**

| Артефакт | Раздел |
|---|---|
| High-Level Architecture | §1 |
| Domains, Domain Model | §2, §3 |
| Modules, Module Diagram | §4 |
| Backend Architecture, Package Structure | §5 |
| Event Flow, Data Flow | §6 |
| Background Jobs | §7 |
| AI Integration | §8 |
| Database Schema / Design | §9 |
| API Strategy / Design | §10 |
| Authentication, Authorization, Security Model | §11, §12, §13 |
| Frontend Architecture, State Management | §14, §15 |
| Notifications, Third-party Integrations | §16, §17 |
| Caching, Error Handling, Offline | §18, §19, §20 |
| i18n, Accessibility | §21, §22 |
| Configuration, Feature Flags, Environments | §23, §24, §25 |
| Logging, Monitoring, Analytics | §26, §27, §28 |
| Deployment Architecture / Strategy, CI/CD | §29, §30 |
| Testing Strategy / Architecture | §31 |
| Folder Structure (полная) | §32 (детали — §5.2, §14.2) |
| Эволюция, риски, открытые вопросы | §33 |

Каждое значимое решение оформлено как **Почему / Альтернативы / Компромиссы** (в тексте или в таблице решений раздела).

---

## 0. Контекст, допущения и архитектурные драйверы

### 0.1. Допущения о масштабе

В SRS нет чисел, поэтому ниже рабочие допущения. Если реальность окажется на порядок больше, их нужно пересмотреть (раздел 33).

| Параметр | Допущение | Влияние на архитектуру |
|---|---|---|
| Источники | 20–100 (RSS, sitemap, HTML, официальные сайты клубов и федераций) | Простой планировщик, ограничение частоты запросов на каждый домен |
| Статьи | 2–10 тыс./день, около 1–3 млн/год | Одного PostgreSQL хватает, партиционирование не нужно |
| Пользователи | 3–20 внутренних сотрудников, desktop | Нет требований к горизонтальному масштабированию API |
| Задержка появления | p95 ≤ 10 мин от публикации источником до появления Event в UI | Опрос раз в 2–5 мин и асинхронный конвейер |
| Отклик Dashboard | p95 API ≤ 300 мс для списка с фильтрами | Индексы, keyset-пагинация, никаких LLM-вызовов в request path |
| Расходы на AI | Ограниченный дневной бюджет | Маршрутизация моделей, кэш, дешёвая модель для массовых задач |

### 0.2. Архитектурные драйверы (по приоритету)

1. **Доверие к фактам** (AC-11, AC-12, §5.5, §10). AI нигде не служит источником истины. Каждое утверждение прослеживается до публикации.
2. **Скорость работы редактора** (метрика «Useful Stories per Hour»). Один Event вместо десяти статей, быстрые фильтры, Telegram-превью в один клик.
3. **Расширяемость** справочников (sports, competitions, sources) без изменения кода.
4. **Простота эксплуатации.** Это внутренний инструмент небольшой команды, поэтому каждый лишний компонент инфраструктуры обходится дорого.
5. **Безопасность и соответствие требованиям:** авторизация, аудит, учёт ToS и copyright, минимальное хранение чужих текстов.

### 0.3. Принципы, применяемые ко всем решениям

- **Детерминированный код для правил, от которых зависит безопасность; AI для извлечения данных.** Reliability, статусы, предупреждения о конфликтах и пометки «не подтверждено» вычисляет код. AI только поставляет для них входные признаки.
- **Минимум движущихся частей.** PostgreSQL выполняет роль хранилища, очереди, поискового движка и векторного индекса. Каждый новый компонент (Redis, Elasticsearch, брокер) добавляется только при измеренной необходимости.
- **Порт там, где есть вторая реализация.** Абстракция появляется только для внешних систем: в тестах их заменяет fake. Над собственной БД интерфейсов-пустышек нет.
- **Ручная правка человека имеет приоритет над AI.** Автоматика никогда молча не перезаписывает отредактированное человеком.

---

## 1. Высокоуровневая архитектура

### 1.1. Диаграмма

```mermaid
flowchart LR
  User((Researcher / Editor / Admin))

  subgraph App["Модульный монолит — один Docker-образ"]
    SPA["SPA (React)<br/>статика"]
    API["web: API-процесс<br/>FastAPI"]
    WRK["worker: процесс задач<br/>+ планировщик"]
  end

  PG[("PostgreSQL 16<br/>данные + очередь задач<br/>pgvector · pg_trgm · FTS")]

  subgraph Ext["Внешние системы"]
    SRC["Новостные источники<br/>RSS / sitemap / HTML"]
    LLM["Anthropic Claude API"]
    EMB["Embeddings API"]
    IDP["OIDC IdP<br/>(Google Workspace / Entra)"]
    OBS["Sentry + лог-агрегатор"]
  end

  User -->|HTTPS| SPA
  SPA -->|"REST /api/v1 (cookie-сессия)"| API
  API --> PG
  WRK --> PG
  WRK -->|"HTTP GET (SSRF-safe)"| SRC
  WRK --> LLM
  WRK --> EMB
  API -->|OIDC| IDP
  API -.-> OBS
  WRK -.-> OBS
```

Ключевое свойство: **API никогда не обращается к LLM или внешним сайтам синхронно.** Всё медленное, ненадёжное или потенциально опасное (сеть, AI, парсинг чужого HTML) выполняет worker. Поэтому Dashboard остаётся быстрым, а SSRF-поверхность сосредоточена в одном процессе.

### 1.2. Технологический стек

| Слой | Выбор | Почему (кратко) |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic | Лучшая экосистема для парсинга новостей и NLP (feedparser, trafilatura), типизированные схемы, OpenAPI из коробки |
| Очередь и планировщик | Procrastinate (очередь задач поверх PostgreSQL) | Задачи ставятся в очередь в той же транзакции, что и данные, то есть transactional outbox получается бесплатно. Нет Redis |
| БД | PostgreSQL 16 с pgvector, pg_trgm, unaccent | Одна система для OLTP, FTS (`portuguese`), нечёткого поиска имён и векторного поиска |
| Frontend | React 19, TypeScript, Vite, TanStack Query, TanStack Router, shadcn/ui (Radix), Tiptap, i18next | SPA для desktop, доступные примитивы, типизированный роутинг с состоянием в URL |
| API-контракт | OpenAPI 3.1 (генерируется FastAPI) → `openapi-typescript` | Один источник истины для типов фронта и бэка |
| AI | Claude (Haiku 4.5 для массовых задач, Sonnet 5.5 для summary и draft), embeddings через API | Структурированный вывод, качество работы с pt-BR, prompt caching |
| Аутентификация | OIDC (Authorization Code + PKCE), серверные сессии в PostgreSQL | Не храним пароли, используем SSO компании |
| Наблюдаемость | structlog (JSON) → stdout → агрегатор; Sentry; метрики OpenTelemetry → Prometheus-совместимый backend | Стандартный набор, всё можно заменить |
| Деплой | Один образ, два типа процессов (web, worker), managed PostgreSQL, PaaS или VM | Минимум операционной нагрузки |
| CI/CD | GitHub Actions | Обычный выбор для git-репозитория |

### 1.3. Ключевые архитектурные решения (ADR-индекс)

**ADR-01. Модульный монолит, а не микросервисы**
- **Почему:** одна небольшая команда, единая предметная модель (Article → Event → Draft) с сильной транзакционной связностью, малая нагрузка. Границы модулей дают те же выгоды по изоляции, но без распределённых транзакций, сетевых сбоев и N деплоев.
- **Альтернативы:** (а) микросервисы ingestion / intelligence / editorial; (б) «большой ком» без границ; (в) serverless-функции на каждый шаг конвейера.
- **Компромиссы:** нельзя масштабировать модули независимо. Компенсируется тем, что web и worker уже разделены как процессы одного образа и масштабируются отдельно. Дисциплину границ придётся поддерживать инструментально (import-linter). Критерии выделения сервиса описаны в §33.

**ADR-02. PostgreSQL как единственная stateful-зависимость**
- **Почему:** FTS с конфигурацией `portuguese`, pg_trgm для имён игроков, pgvector для кластеризации и очередь задач в одной базе. Один бэкап, одна точка отказа вместо четырёх, транзакционная согласованность «данные + задача».
- **Альтернативы:** Elasticsearch/OpenSearch для поиска; Redis + Celery/RQ для очереди; Qdrant/Pinecone для векторов; Kafka для событий.
- **Компромиссы:** FTS в PostgreSQL слабее Elastic в ранжировании и подсветке, pgvector медленнее специализированных БД на десятках миллионов векторов. Для 1–3 млн статей в год этого достаточно. Путь миграции описан в §33.

**ADR-03. Python для backend и TypeScript для frontend (два языка)**
- **Почему:** извлечение контента (trafilatura), RSS (feedparser), обработка текста и SDK провайдеров AI в Python лучше всего. Frontend на TS здесь вне конкуренции.
- **Альтернативы:** весь стек на TypeScript (NestJS или Next.js + tRPC); Django.
- **Компромиссы:** нет общих типов «из коробки». Решается генерацией TS-типов из OpenAPI. Django дал бы готовую админку и auth, но хуже сочетается с Clean Architecture и async-конвейером. Админ-экранов мало (sources, taxonomy, settings), их проще сделать в SPA.

**ADR-04. Асинхронный конвейер на задачах, а не потоковая обработка**
- **Почему:** каждый шаг (fetch → extract → enrich → cluster → refresh) представляет собой идемпотентную задачу с ретраями. Объёмы невелики, и потоковая платформа избыточна.
- **Альтернативы:** Kafka/Redpanda; синхронная обработка в одном cron-скрипте.
- **Компромиссы:** нет повторного проигрывания событий, как в логе Kafka. Повторная обработка выполняется перепостановкой задач по выборке из БД, чего хватает для нашего объёма.

**ADR-05. Публикация в Telegram — по каналам и только под флагом** (пересмотрен 2026-10-09; было: «нет автопубликации в MVP»)
- **Почему:** руководству нужна регулярная доставка брифов; ручное копирование не масштабируется на несколько каналов и языков.
- **Как:** сущность «Канал» (`editorial.channels`): chat_id, язык, фильтры (регион, вид спорта, источники, минимальный уровень источника, важность, доверие), режим и cron. Режимы:
  - `approval` — публикуются только события «Готово» с постом на языке канала; человек утвердил текст, после отправки событие → PUBLISHED.
  - `auto` — события выше порогов с AI-брифом на языке канала; слухи не публикуются, статус события не меняется.
- **Защита:** без `FLAG_TELEGRAM_PUBLISH=true` и `TELEGRAM_BOT_TOKEN` ничего не отправляется; `publications` UNIQUE(channel, event) исключает повторы; ошибки Telegram пишутся в журнал канала.
- **Компромиссы:** формат `digest` — заголовки со ссылками, без полного текста.


**ADR-06. Сначала правила и шаблоны, локальная LM — опционально** (подробно: `docs/adr/004-rules-first-local-llm.md`)
- **Почему:** нулевой бюджет; гипотеза, что шаблонов с ручной доработкой достаточно.
- **Компромиссы:** кластеризация и relevance грубее; AC-11 только с LM. Порты `LlmClient`/`EmbeddingClient` сохраняются, LM включается по шагам без изменения кода модулей.
---

## 2. Предметные области (Domains / Bounded Contexts)

### 2.1. Классификация доменов

| Домен | Тип | Ответственность | Ключевые понятия |
|---|---|---|---|
| **Events (Story Intelligence)** | **Core** | Кластеризация статей в события, агрегированная оценка, конфликты, редакционный workflow события | Event, EventStatus, Conflict, Clustering |
| **Intelligence (Enrichment)** | **Core** | Понимание отдельной статьи: sport, competition, сущности, утверждения (claims), признаки слухов и clickbait, relevance, embedding | Enrichment, Claim, RelevanceAssessment |
| **Editorial** | **Core** | Telegram-черновики, версии, grounding и цитаты, превью и копирование | TelegramDraft, DraftVersion, Citation |
| **Ingestion** | Supporting | Получение и нормализация публикаций, дедупликация по URL и контенту | Article, FetchRun |
| **Sources** | Supporting | Каталог источников, расписание опроса, tier и владелец, ToS-политика, здоровье | Source, SourceHealth, OwnerGroup |
| **Taxonomy** | Supporting | Справочники: Sport, Competition, Team, Player, алиасы | Sport, Entity, Alias |
| **Identity & Access** | Generic | Пользователи, роли, сессии, OIDC | User, Role, Session |
| **Audit** | Generic | Неизменяемая история критических действий | AuditEntry |
| **Analytics** | Generic (read-only) | Метрики «Useful Stories per Hour», качество AI | Read models |

**Почему Intelligence и Events разделены:** Intelligence работает на уровне **одной статьи** и не знает о событиях. Events работает на уровне **множества статей** и получает от Intelligence готовые признаки. Так можно менять модели и промпты обогащения, не затрагивая логику кластеризации и workflow, и наоборот.
**Альтернатива:** единый модуль «AI processing». **Компромисс:** при раздельных модулях есть дополнительный контракт (DTO обогащения), зато высокая связность внутри каждого из них.

### 2.2. Context Map

```mermaid
flowchart TB
  Sources -->|"Customer/Supplier:<br/>конфигурация источника"| Ingestion
  Ingestion -->|"Published Language:<br/>ArticleIngested"| Intelligence
  Taxonomy -->|"Shared Kernel (read):<br/>entity linking"| Intelligence
  Intelligence -->|"Published Language:<br/>ArticleEnriched DTO"| Events
  Sources -->|"tier, owner_group"| Events
  Events -->|"Customer/Supplier:<br/>EventSnapshot + evidence pack"| Editorial
  Identity -->|"Conformist:<br/>CurrentUser, Role"| Events
  Identity --> Editorial
  Events -->|"audit facts"| Audit
  Editorial -->|"audit facts"| Audit
  Audit -->|"read model"| Analytics
  Events -->|"read model"| Analytics
```

### 2.3. Единый язык (Ubiquitous Language)

| Термин | Определение |
|---|---|
| **Article** | Одна публикация одного источника по одному каноническому URL. Неизменяема по сути, но может обновляться (правки источника) |
| **Event** | Реальный факт или история, о которой сообщают 1..N Article. Единица работы редактора |
| **Claim** | Атомарное утверждение из статьи: *субъект, атрибут, значение, модальность (подтверждено / ожидается / слух)* |
| **Conflict** | Противоречивые значения одного (субъект, атрибут) в разных Article одного Event |
| **Relevance** | Важность для iGaming-аудитории: HIGH / MEDIUM / LOW / IRRELEVANT с объяснением |
| **Reliability** | Достоверность: HIGH / MEDIUM / LOW / UNKNOWN. Вычисляется из факторов, **независимо** от Relevance |
| **Independent sources** | Источники с разным `owner_group` (например, Globo и GE относятся к одной группе и не считаются двумя независимыми подтверждениями) |
| **Evidence pack** | Пронумерованный набор фрагментов статей, на которые разрешено ссылаться AI при генерации |
| **Manual override** | Поле Event, заблокированное от автоматической перезаписи после правки человеком |

---

## 3. Модель предметной области (Domain Model)

### 3.1. Агрегаты

```mermaid
classDiagram
  direction LR

  class Source {
    +SourceId id
    +name
    +base_url
    +SourceKind kind [rss, sitemap, html, official]
    +SourceTier tier [A, B, C, OFFICIAL]
    +owner_group
    +language
    +poll_interval
    +ContentPolicy policy
    +bool active
    +HealthStatus health
  }

  class Article {
    +ArticleId id
    +SourceId source_id
    +CanonicalUrl url
    +title
    +lead_snippet
    +published_at
    +discovered_at
    +image_url
    +content_hash
    +ProcessingState state
  }

  class Enrichment {
    <<value object>>
    +SportId sport
    +EntityId competition
    +EntityRef[] entities
    +Claim[] claims
    +RumorMarker[] rumor_markers
    +bool clickbait
    +stale_hint
    +RelevanceAssessment relevance
    +Vector embedding
    +PromptVersion version
  }

  class Event {
    +EventId id
    +title
    +Summary summary
    +occurred_at
    +first_seen_at
    +last_article_at
    +SportId sport
    +EntityId competition
    +EntityRef[] teams
    +EntityRef[] players
    +RelevanceAssessment relevance
    +ReliabilityAssessment reliability
    +EventStatus status
    +RejectionReason rejection
    +Set~Field~ manual_overrides
    +int version
    +attach(article)
    +detach(article)
    +transition(to, actor, reason)
    +override(field, value, actor)
  }

  class Conflict {
    +subject
    +attribute
    +Position[] positions
    +ConflictState state [open, resolved, dismissed]
  }

  class TelegramDraft {
    +DraftId id
    +EventId event_id
    +DraftState state [generating, ready, failed]
    +DraftVersion current
    +DraftVersion[] history
  }

  class DraftVersion {
    <<entity>>
    +n
    +body_tg_html
    +image_url
    +caption
    +Origin origin [ai, human]
    +Citation[] citations
    +GroundingReport grounding
    +author
  }

  Source "1" --> "*" Article : publishes
  Article "1" *-- "0..1" Enrichment
  Event "1" o-- "1..*" Article : clusters
  Event "1" *-- "*" Conflict
  Event "1" --> "*" Event : related
  Event "1" --> "0..*" TelegramDraft
  TelegramDraft "1" *-- "1..*" DraftVersion
```

### 3.2. Value Objects

| VO | Состав | Инварианты |
|---|---|---|
| `RelevanceAssessment` | level, rationale (≤ 280 символов), origin (ai/rule/human), prompt_version | rationale обязателен для любого level кроме IRRELEVANT |
| `ReliabilityAssessment` | level, factors[] (код фактора, вклад, пояснение), origin | level **выводится** из factors функцией политики; при origin=human обязательна причина |
| `Summary` | text, origin (ai/human), citations[], generated_from_article_ids[] | AI-summary без цитат невалидна |
| `Claim` | subject_entity, attribute (availability, transfer, score, lineup, suspension, coach, other), value, modality (confirmed/expected/rumor/denied), quote_span, article_id | quote_span обязан быть подстрокой исходного текста |
| `CanonicalUrl` | нормализованный URL (без utm, fragment, с lowercase host) | уникален в системе |
| `RejectionReason` | DUPLICATE, IRRELEVANT, LOW_QUALITY, INCORRECT, OLD_NEWS, NOT_TELEGRAM_WORTHY, OTHER (+ comment) | при OTHER comment обязателен |

### 3.3. Инварианты агрегата Event

1. Event содержит ≥ 1 Article (кроме Event, созданного вручную: тогда допускается 0 Article, но reliability = UNKNOWN до прикрепления источника).
2. `reliability.level` не может быть HIGH, если у события есть открытый Conflict по ключевому атрибуту. В таком случае уровень ограничивается MEDIUM, а спорный claim исключается из «фактов».
3. Поля из `manual_overrides` (title, summary, sport, competition, relevance, reliability) не перезаписываются автоматическим `refresh`. Вместо перезаписи выставляется флаг `has_updates_since_edit`.
4. Переходы статусов только по state machine (§3.4). Каждый переход фиксируется в Audit.
5. `version` увеличивается при каждом изменении (оптимистичная блокировка).

### 3.4. State machine статуса Event

```mermaid
stateDiagram-v2
  [*] --> NEW
  NEW --> REVIEWING
  REVIEWING --> SELECTED
  SELECTED --> DRAFT : создан Telegram draft
  DRAFT --> READY : только Editor/Admin
  READY --> DRAFT : вернуть на доработку
  READY --> PUBLISHED : отмечено вручную
  NEW --> REJECTED
  REVIEWING --> REJECTED
  SELECTED --> REJECTED
  DRAFT --> REJECTED
  REJECTED --> NEW : восстановить (Editor/Admin)
  PUBLISHED --> [*]
```

- SRS явно указывает только `NEW → REJECTED`. Расширение (отклонение с REVIEWING, SELECTED и DRAFT, восстановление) — **интерпретация**: кнопка Reject в Telegram Preview (§9 SRS) подразумевает отклонение на стадии черновика. Набор переходов задан одной таблицей в доменной политике и меняется в одном месте.
- **Почему статус принадлежит Event, а не Draft:** редактор работает с событиями. У Draft есть только технический статус генерации. Два параллельных workflow запутали бы UI и аналитику.
- **Альтернатива:** отдельный workflow у Draft. **Компромисс:** несколько вариантов черновиков одного события не получают собственных статусов (в MVP это не нужно: «текущая версия» плюс история).

### 3.5. Доменные политики (domain services)

| Политика | Модуль | Детерминирована? | Описание |
|---|---|---|---|
| `ReliabilityPolicy` | events | **Да** | Факторы: tier источников, число независимых `owner_group`, наличие OFFICIAL-источника, rumor markers, clickbait, открытые конфликты, одиночный источник. Таблица правил (§8.6) |
| `RelevancePolicy` | events | Частично | Берётся максимум AI-оценок статей и корректируется детерминированными модификаторами (вес competition, приоритетные команды, staleness) |
| `ClusteringPolicy` | events | Да (с AI в серой зоне) | Скоринг кандидатов и пороги (§8.5) |
| `WorkflowPolicy` | events | Да | Допустимые переходы и роли |
| `GroundingValidator` | editorial | **Да** | Проверка, что каждое предложение черновика имеет цитату, а числа, имена и цитаты встречаются в evidence pack |
| `UrlCanonicalizer` | ingestion | Да | Нормализация URL |

---

## 4. Модули и диаграмма модулей

### 4.1. Диаграмма зависимостей модулей

```mermaid
flowchart TB
  subgraph Entry["Composition roots"]
    WEB["main.py (web)"]
    WORKER["worker.py"]
  end

  subgraph Modules["modules/*"]
    identity
    sources
    ingestion
    taxonomy
    intelligence
    events
    editorial
    audit
    analytics
  end

  subgraph Platform["platform/* (shared kernel, технический)"]
    config
    db
    jobs
    ai["ai (LLM gateway, prompts)"]
    fetch["safe_fetch (HTTP)"]
    flags
    logging
    errors
  end

  WEB --> Modules
  WORKER --> Modules

  ingestion --> sources
  intelligence --> taxonomy
  events --> intelligence
  events --> sources
  events --> taxonomy
  editorial --> events
  analytics -.->|"только SQL read models"| events
  analytics -.-> audit

  Modules --> Platform
```

### 4.2. Правила зависимостей (проверяются в CI через import-linter)

1. **Направление внутри модуля:** `api → application → domain`; `infrastructure → application/domain`. Domain ничего не импортирует, кроме stdlib и `platform.errors`.
2. **Между модулями** разрешён импорт только из `modules/<x>/public.py`, то есть фасада с DTO и функциями. Импорт `modules/x/domain/...` из модуля `y` запрещён.
3. **Граф модулей ацикличен.** Обратная связь (например, events должен сообщить editorial об изменении) передаётся задачей в очереди, а не импортом.
4. **`platform` не знает о модулях.**
5. **У каждой таблицы БД ровно один модуль-владелец.** Чужие таблицы не читаются. Исключение составляет `analytics`, которому разрешены read-only SQL-представления (views), и это явное и задокументированное исключение.

**Почему так:** правила 2 и 3 дают слабую связанность без распределённой системы, а правило 5 сохраняет возможность выделить модуль в сервис позже.
**Альтернатива:** «модули» как папки без проверки. На практике границы размываются за несколько месяцев.
**Компромисс:** фасадные DTO требуют маппинга. Это небольшая цена.

### 4.3. Каталог модулей

| Модуль | Владеет таблицами | Публичный фасад (примеры) | Задачи (jobs) |
|---|---|---|---|
| identity | users, sessions | `get_current_user`, `require_role` | `purge_expired_sessions` |
| sources | sources, source_fetch_runs | `list_due_sources`, `get_source_meta` | `schedule_due_sources` (periodic) |
| ingestion | articles, article_content | `get_article`, `get_evidence(article_ids)`, `ingest_manual_url` | `fetch_source`, `extract_article`, `purge_article_content` |
| taxonomy | sports, entities, entity_aliases | `link_entities(mentions)`, `list_sports` | — |
| intelligence | article_enrichments, ai_runs* | `get_enrichment(article_id)`, `find_similar(embedding, window)` | `enrich_article` |
| events | events, event_articles, event_entities, event_conflicts, event_relations | `get_event_snapshot`, `transition`, `list_events` | `cluster_article`, `refresh_event`, `detect_conflicts` |
| editorial | telegram_drafts, telegram_draft_versions | `generate_draft`, `get_draft` | `generate_draft`, `regenerate_summary`** |
| audit | audit_log | `record(actor, action, target, diff)` | — |
| analytics | — (views) | `useful_stories_per_hour(range)` | `refresh_materialized_views` |

\* `ai_runs` принадлежит `platform.ai` (технический журнал), а не модулю.
\** Генерация summary события физически вызывается из events (`refresh_event`), но промпт и grounding переиспользуются из editorial через фасад. Альтернативой было бы дублирование grounding-логики, что хуже.

> Связь Article → Event хранится в таблице `event_articles` (PK = `article_id`, то есть одна статья принадлежит одному событию). Владелец таблицы — **events**, а не колонка `articles.event_id`. Так ingestion не знает о событиях, и правило 5 соблюдается без исключений.

---

## 5. Архитектура бэкенда

### 5.1. Слои внутри модуля (Clean Architecture)

```mermaid
flowchart LR
  API["api/<br/>FastAPI routers,<br/>Pydantic request/response"] --> APP
  JOBS["jobs.py<br/>обработчики задач"] --> APP
  APP["application/<br/>use cases (команды/запросы),<br/>порты (Protocol), DTO"] --> DOM["domain/<br/>агрегаты, VO, политики,<br/>доменные ошибки"]
  INFRA["infrastructure/<br/>репозитории SQLAlchemy,<br/>адаптеры внешних систем"] --> APP
  INFRA --> DOM
```

- **Domain** состоит из чистых dataclass-ов без SQLAlchemy и Pydantic. Тестируется за миллисекунды.
- **Application** содержит use case: открыть Unit of Work, загрузить агрегат, вызвать метод домена, сохранить, поставить задачу, записать аудит. Транзакция включает и данные, и задачи.
- **Infrastructure** держит репозитории (классический Data Mapper, SQLAlchemy Core/ORM-маппинг отдельно от доменных классов) и адаптеры.
- **API** — тонкий слой: валидация, авторизация через зависимость, вызов use case, маппинг ошибок.

**Решение по портам:** порты (Protocol) заводятся только для внешних систем: `LlmClient`, `EmbeddingClient`, `HttpFetcher`, `OidcProvider`, `Clock`, позже `TelegramPublisher`. У каждого есть реальный адаптер и fake для тестов. **Репозитории являются конкретными классами без интерфейса** и тестируются на реальном PostgreSQL.
- **Почему:** интерфейс с единственной реализацией — это церемония. Подмена БД в тестах ради скорости не стоит потери уверенности (FTS, pgvector и блокировки не мокаются).
- **Альтернатива:** «каноническая» Clean Architecture с `IEventRepository` и in-memory реализацией.
- **Компромисс:** тесты application-слоя требуют PostgreSQL (testcontainers, около 2 с на старт). Это допустимо.

**Решение по CQRS-lite:** команды проходят через агрегаты, а запросы списков для Dashboard (фильтры, поиск, пагинация) — через выделенные read-запросы (SQL), которые возвращают DTO напрямую, минуя доменные объекты.
- **Почему:** Dashboard — самый нагруженный путь, и загружать агрегаты ради списка расточительно.
- **Альтернатива:** всё через репозитории агрегатов; полноценный CQRS с отдельной read-БД.
- **Компромисс:** две модели чтения одной таблицы. Это допустимо, потому что они в одном модуле.

### 5.2. Структура пакетов бэкенда

```text
backend/
├── pyproject.toml                 # зависимости, ruff, mypy, import-linter contracts
├── alembic.ini
├── migrations/                    # Alembic: одна линейная история на весь монолит
│   └── versions/
├── src/sportintel/
│   ├── main.py                    # composition root (web): create_app(), подключение routers
│   ├── worker.py                  # composition root (worker): регистрация задач и периодики
│   ├── platform/                  # технический shared kernel, не знает о модулях
│   │   ├── config.py              # Settings (pydantic-settings), загрузка env
│   │   ├── db.py                  # engine, session, UnitOfWork, advisory locks
│   │   ├── jobs.py                # обёртка procrastinate: enqueue в текущей транзакции
│   │   ├── errors.py              # базовые DomainError/NotFound/Conflict/Forbidden
│   │   ├── http_api.py            # problem+json, middleware (request_id, CSRF), pagination
│   │   ├── logging.py             # structlog, контекстные поля
│   │   ├── telemetry.py           # Sentry, OTel-метрики
│   │   ├── flags.py               # feature flags (env default + DB override)
│   │   ├── clock.py               # Clock port
│   │   ├── safe_fetch/            # HttpFetcher port + SSRF-safe adapter, robots.txt, rate limit per host
│   │   └── ai/
│   │       ├── gateway.py         # LlmClient/EmbeddingClient ports, routing, budget guard, cache
│   │       ├── anthropic.py       # адаптер Claude
│   │       ├── embeddings.py      # адаптер embeddings API
│   │       ├── fake.py            # детерминированный fake для тестов и local
│   │       └── prompts/           # версионируемые промпты: <task>/v<N>.md + schema.py
│   └── modules/
│       ├── identity/
│       ├── sources/
│       ├── ingestion/
│       ├── taxonomy/
│       ├── intelligence/
│       ├── events/
│       ├── editorial/
│       ├── audit/
│       └── analytics/
└── tests/
    ├── unit/                      # domain + политики, без I/O
    ├── integration/               # use cases + репозитории на реальном Postgres
    ├── contract/                  # парсеры источников на сохранённых фикстурах RSS/HTML
    ├── api/                       # HTTP-тесты роутеров (auth, RBAC, problem+json)
    ├── architecture/              # import-linter + проверка владения таблицами
    └── evals/                     # AI golden sets (отдельный запуск)
```

Структура одного модуля (на примере `events`):

```text
modules/events/
├── public.py              # фасад: функции и DTO для других модулей (единственная точка входа)
├── domain/
│   ├── event.py           # агрегат Event, методы attach/detach/transition/override
│   ├── conflict.py
│   ├── values.py          # RelevanceAssessment, ReliabilityAssessment, EventStatus, RejectionReason
│   ├── policies/
│   │   ├── reliability.py
│   │   ├── relevance.py
│   │   ├── clustering.py
│   │   └── workflow.py
│   └── errors.py          # InvalidTransition, OverrideLocked, ...
├── application/
│   ├── commands/          # cluster_article, refresh_event, transition_event, edit_event, merge, split, create_manual
│   ├── queries/           # list_events (фильтры/поиск), get_event_details, related_events
│   └── dto.py
├── infrastructure/
│   ├── repository.py      # EventRepository (Data Mapper)
│   ├── tables.py          # SQLAlchemy Table-определения (владелец таблиц)
│   └── read_queries.py    # SQL для списка/поиска
├── api/
│   ├── router.py          # /api/v1/events...
│   └── schemas.py         # Pydantic request/response
└── jobs.py                # cluster_article, refresh_event, detect_conflicts
```

### 5.3. Взаимодействие модулей

| Тип взаимодействия | Механизм | Когда |
|---|---|---|
| Синхронный запрос | Вызов функции из `public.py` | Нужны данные другого модуля сейчас (events читает enrichment) |
| Асинхронная реакция | Задача Procrastinate, поставленная **в той же транзакции** | Реакция на изменение (статья обогащена → кластеризовать) |
| Широковещательное «доменное событие» | Не используется в MVP | Добавляется, когда у одного события появится ≥ 2 независимых подписчика |

- **Почему не in-process event bus:** у каждого «события» в MVP ровно один потребитель, поэтому прямая постановка задачи проще и трассируема. При этом задача и данные коммитятся атомарно, и потерянных событий не бывает.
- **Альтернатива:** таблица outbox и диспетчер подписок; брокер сообщений.
- **Компромисс:** продюсер знает имя задачи потребителя. Это допустимая связь через фасад, например `events.public.enqueue_cluster(article_id)`.

### 5.4. Транзакции и конкурентность

- **Unit of Work на use case.** Одна транзакция PostgreSQL на команду.
- **Оптимистичная блокировка** (`version`) для правок человеком: заголовок `If-Match`, при несовпадении ответ 409 и UI показывает diff.
- **Пессимистичная блокировка для кластеризации:** `pg_advisory_xact_lock(hash(sport_id, day_bucket))` на время выбора «прикрепить или создать». Без неё две одновременно обработанные статьи об одном факте создадут два Event. Ограничение: блокировка по виду спорта и дню сериализует кластеризацию внутри «корзины». При текущих объёмах это десятки миллисекунд; если станет узким местом, нужно перейти на блокировку по top-кандидату.
- **Debounce пересчёта события:** у `refresh_event` есть `queueing_lock = event_id`, поэтому в очереди не больше одной задачи на событие. Десять статей подряд дают один пересчёт.
- **Идемпотентность:** `articles.canonical_url` UNIQUE, а задачи проверяют `processing_state` и пропускают уже выполненный шаг.

---

## 6. Поток событий и потоки данных (Event Flow / Data Flow)

### 6.1. Конвейер ingestion → event

```mermaid
sequenceDiagram
  autonumber
  participant SCH as Scheduler (worker)
  participant ING as ingestion
  participant SRC as Источник
  participant INT as intelligence
  participant AI as Claude / Embeddings
  participant EV as events
  participant DB as PostgreSQL

  SCH->>DB: каждые 60 с: sources due? (sources.schedule_due_sources)
  SCH->>ING: enqueue fetch_source(source_id)
  ING->>SRC: conditional GET RSS/sitemap (ETag / If-Modified-Since)
  SRC-->>ING: список элементов
  ING->>DB: INSERT articles ON CONFLICT(canonical_url) DO NOTHING<br/>+ enqueue extract_article (в одной транзакции)
  ING->>SRC: GET страницы статьи (robots.txt, rate limit per host)
  ING->>DB: title, lead, published_at, image, content_hash<br/>текст → article_content (TTL)<br/>+ enqueue enrich_article
  INT->>AI: 1 структурированный вызов (Haiku): sport, competition,<br/>entities, claims, rumor markers, clickbait, stale_hint, relevance+why
  INT->>AI: embedding(title + lead + entities)
  INT->>DB: article_enrichments + entity linking (taxonomy)<br/>+ enqueue cluster_article
  EV->>DB: advisory lock(sport, day) → кандидаты: ANN top-k за 72 ч
  alt score ≥ T_high
    EV->>DB: attach к существующему Event
  else T_low < score < T_high
    EV->>AI: adjudicate (Haiku): «тот же факт?»
    EV->>DB: attach или new Event
  else score ≤ T_low
    EV->>DB: new Event
  end
  EV->>DB: enqueue refresh_event(event_id) [queueing_lock]
  EV->>DB: refresh: reliability (детерм.), relevance, entities,<br/>conflicts, related events, summary (если не override)
  Note over EV,DB: UI получает изменения через polling /events?updated_since=
```

### 6.2. Редакторский поток

```mermaid
sequenceDiagram
  autonumber
  actor R as Researcher
  actor E as Editor
  participant UI as SPA
  participant API as API
  participant DB as PostgreSQL
  participant W as worker (editorial)
  participant AI as Claude Sonnet

  R->>UI: фильтр Football + HIGH + 24h
  UI->>API: GET /events?sport=football&relevance=HIGH&from=...
  API-->>UI: список (keyset page)
  R->>UI: открыть событие (master-detail)
  UI->>API: GET /events/{id} (+ articles, conflicts)
  R->>UI: Select
  UI->>API: POST /events/{id}/transitions {to: SELECTED}
  R->>UI: Generate draft
  UI->>API: POST /events/{id}/drafts (Idempotency-Key)
  API->>DB: draft(state=generating) + enqueue generate_draft
  API-->>UI: 202 + draft_id
  W->>DB: evidence pack (фрагменты статей, claims, conflicts, reliability)
  W->>AI: генерация с обязательными цитатами [n]
  W->>W: GroundingValidator + детерминированные дисклеймеры
  W->>DB: draft version 1 (origin=ai, citations, grounding report)<br/>event: SELECTED → DRAFT
  UI->>API: polling GET /drafts/{id} до state=ready
  R->>UI: правка (Tiptap) → Save
  UI->>API: PATCH /drafts/{id} (If-Match) → version 2 (origin=human)
  E->>UI: проверка фактов по цитатам → Mark Ready
  UI->>API: POST /events/{id}/transitions {to: READY} (только Editor)
  E->>UI: Copy → вставка в Telegram вручную
  E->>UI: Mark Published
```

### 6.3. Ручные потоки

- **Добавить URL вручную:** `POST /articles {url}` возвращает 202 и запускает тот же конвейер с флагом `manual=true` (источник определяется по домену, при отсутствии — `Source(kind=manual)`). SSRF-защита описана в §13.
- **Создать Event вручную:** `POST /events` создаёт событие с `origin=human`, reliability=UNKNOWN, пока не прикреплены статьи.
- **Исправление кластеризации:** `POST /events/{id}/articles/{article_id}/move {target_event_id | new}` и `POST /events/{id}/merge {other_id}`. Ручное перемещение выставляет `event_articles.cluster_locked = true`, и автокластеризация эту статью больше не трогает. В SRS это явно не требуется, но без этой функции ошибки AI (§13 SRS) неисправимы. Корректировки служат сигналом для evals.

### 6.4. Развитие истории в течение дня и прочие edge cases

| Edge case (SRS §13) | Архитектурный ответ |
|---|---|
| Несколько источников об одном событии | Кластеризация §8.5, независимость по `owner_group` |
| Развитие новости в течение дня | Новые статьи прикрепляются к Event, `refresh_event` пересчитывает summary. Если summary правил человек, вместо перезаписи выставляется `has_updates_since_edit` и UI показывает баннер «N новых источников после вашей правки». Существенно новый факт (новые claims по другому атрибуту) создаёт новый Event со связью `related(kind=follow_up)` |
| Противоречивые источники | Claims → `event_conflicts`, баннер ⚠ Conflicting reports, reliability ≤ MEDIUM, спорный claim исключается из фактов в промпте и маркируется в draft |
| Слухи | Rumor markers из enrichment (`segundo apuração`, `pode`, `especula-se`, `negocia`, …) → фактор reliability. Draft получает **детерминированную** плашку «⚠ Não confirmado» |
| Старые события, опубликованные заново | `stale_hint` (дата факта в тексте ≪ даты публикации) и совпадение с закрытым Event старше окна → статья помечается как related к старому событию, relevance понижается на уровень, в UI бейдж «Possibly old news» |
| Clickbait | Флаг `clickbait`: заголовок статьи не используется как заголовок Event, фактор reliability понижается |
| Недоступный источник | `source_fetch_runs` и экспоненциальный backoff; health DEGRADED/DOWN виден в admin. Ссылка на статью остаётся, рядом показывается «источник недоступен при последней проверке» |
| Нет подтверждения | Одиночный источник уровня B/C даёт reliability LOW/UNKNOWN; draft генерируется с плашкой |
| Ошибки AI | Ошибка схемы → одна попытка «repair», затем `enrichment_failed`. Статья видна с Sport=Unclassified и **не теряется**. Ручная корректировка в UI |
| Низкая iGaming relevance | IRRELEVANT по умолчанию скрыт фильтром, но доступен |
| Мало информации | Событие из 1 статьи с коротким lead: summary помечается «Informação limitada», draft-генерация показывает предупреждение |

---

## 7. Фоновые задачи (Background Jobs)

### 7.1. Механизм

**Решение:** Procrastinate (PostgreSQL `LISTEN/NOTIFY` и `SELECT … FOR UPDATE SKIP LOCKED`), периодические задачи встроены в worker.
- **Почему:** нет Redis; постановка в очередь атомарна с бизнес-данными; есть ретраи, queueing locks (debounce) и периодические задачи; состояние очереди видно SQL-запросом.
- **Альтернативы:** Celery + Redis/RabbitMQ (тяжелее, ещё одна зависимость, нет атомарности с БД); arq/RQ (нужен Redis); Temporal (мощно, но избыточно для линейного конвейера); cron + скрипты (нет ретраев и параллелизма).
- **Компромиссы:** пропускная способность ограничена PostgreSQL. Это тысячи задач в секунду, на порядки больше нашей нагрузки. Если очередь станет проблемой, её можно вынести в отдельную БД, не меняя кода задач.

### 7.2. Каталог задач

| Задача | Триггер | Очередь | Ретраи | Идемпотентность / lock |
|---|---|---|---|---|
| `schedule_due_sources` | periodic, 60 с | `scheduler` | — | один экземпляр (periodic lock) |
| `fetch_source(source_id)` | планировщик | `fetch` | 3, backoff 1→5→15 мин | `queueing_lock=source_id` |
| `extract_article(article_id)` | после fetch | `fetch` | 3, backoff | проверка `state` |
| `enrich_article(article_id)` | после extract | `ai` | 3 (+1 repair на ошибку схемы) | кэш `ai_runs` по input_hash |
| `cluster_article(article_id)` | после enrich | `cluster` | 5, короткий backoff | advisory lock (sport, day) |
| `refresh_event(event_id)` | после attach/detach/edit | `cluster` | 5 | `queueing_lock=event_id` (debounce) |
| `generate_draft(draft_id)` | действие пользователя | `ai_interactive` | 2 | проверка `draft.state` |
| `regenerate_summary(event_id)` | действие пользователя | `ai_interactive` | 2 | `queueing_lock=event_id` |
| `purge_article_content` | periodic, 1 ч | `maintenance` | — | DELETE по TTL |
| `purge_expired_sessions` | periodic, 1 ч | `maintenance` | — | — |
| `refresh_analytics_views` | periodic, 15 мин | `maintenance` | — | `REFRESH MATERIALIZED VIEW CONCURRENTLY` |
| `check_source_health` | periodic, 15 мин | `maintenance` | — | агрегирует fetch_runs |

### 7.3. Правила

- **Отдельная очередь `ai_interactive`** с выделенными воркерами: генерация черновика по клику пользователя не ждёт, пока ночная волна обогащения пройдёт очередь `ai`.
- **Ограничение параллелизма к хосту** реализовано в `safe_fetch`: не больше 1–2 одновременных запросов и интервал между запросами настраивается у Source. Это вопрос вежливости и ToS.
- **Глобальный AI rate limit и дневной бюджет** (`platform.ai.gateway`): при превышении задачи `ai` откладываются (retry с задержкой), а `ai_interactive` продолжают работать до жёсткого лимита.
- **Ошибки после последнего ретрая:** задача уходит в `failed`, сущность получает `processing_state=failed` с кодом ошибки. Admin-экран «Pipeline» показывает их и позволяет «Retry».
- **Ключи идемпотентности:** каждая задача безопасна при повторном выполнении. Ретрай не создаёт дубликатов благодаря уникальным ключам и проверке state.

---

## 8. Интеграция с ИИ (AI Integration)

### 8.1. Роль AI: принцип «AI извлекает, код решает»

| AI делает | Код делает (детерминированно) |
|---|---|
| Извлекает sport, competition, entities, claims, rumor markers, clickbait, stale hint | Связывает сущности со справочником, нормализует |
| Предлагает relevance + why | Применяет модификаторы, хранит origin |
| Решает «тот же факт?» в серой зоне кластеризации | Выбирает кандидатов, вычисляет скоринг и пороги |
| Сравнивает claims на противоречие | Группирует claims, ограничивает reliability |
| Пишет summary и draft с цитатами | Валидирует grounding, вставляет дисклеймеры, маркирует AI-контент |
| — | **Вычисляет reliability целиком** |

**Почему:** требования AC-12 и §10 SRS («AI не должен…») нельзя гарантировать промптом, их можно гарантировать только проверкой результата.
**Альтернатива:** доверять промпту («не выдумывай факты»).
**Компромисс:** больше кода-валидатора и иногда ложные срабатывания (предложение помечено как «непроверенное», хотя оно верно). Ложное срабатывание дёшево, пропущенная выдумка дорога.

### 8.2. LLM Gateway (`platform/ai`)

Единая точка всех вызовов AI. Модули не импортируют SDK провайдера.

```text
LlmClient.run(task: TaskName, prompt_version, inputs, output_schema) -> (validated_output, run_id)
EmbeddingClient.embed(texts) -> vectors
```

Обязанности шлюза:
1. **Маршрутизация моделей по задаче** (конфиг в `app_settings`, меняется без деплоя):
   - _ADR-004: в MVP вместо этой маршрутизации — режимы шагов `rules|llm` с локальной моделью (`qwen2.5:7b-instruct`), см. CONV §3 `ai_routing`. Ниже — целевая маршрутизация для отложенного платного провайдера._
   - `enrich_article`, `cluster_adjudicate`, `conflict_check` → **claude-haiku-4-5** (объём, цена, задержка);
   - `event_summary`, `telegram_draft`, `headline` → **claude-sonnet-5-5** (качество текста на pt-BR);
   - эскалация на более сильную модель при повторной ошибке схемы.
2. **Структурированный вывод:** JSON Schema из Pydantic-моделей (tool use / structured outputs), валидация, одна попытка repair.
3. **Журнал `ai_runs`:** task, model, prompt_version, input_hash, tokens, cost, latency, status, output. Это одновременно аудит, кэш, источник для evals и биллинг.
4. **Кэш** по `(task, prompt_version, model, input_hash)`. Переобработка той же статьи бесплатна.
5. **Prompt caching** провайдера для длинных стабильных частей (системные инструкции, рубрика relevance, справочник алиасов).
6. **Бюджет и circuit breaker:** дневной лимит расходов на окружение, отключение при всплеске ошибок провайдера (деградация описана в §19).
7. **Fake-адаптер** для local, CI и e2e: детерминированные ответы по фикстурам.

**Почему собственный тонкий шлюз, а не LangChain-подобный фреймворк:** нужно около пяти функций, а фреймворк приносит абстракции, нестабильный API и усложняет отладку промптов.
**Альтернатива:** внешний LLM-прокси (LiteLLM, Portkey). Это имеет смысл при нескольких провайдерах, и в MVP такая необходимость не обоснована.
**Компромисс:** при добавлении второго провайдера понадобится ещё один адаптер, и порт к этому готов.

### 8.3. Промпты как код

- Промпты лежат в `platform/ai/prompts/<task>/v<N>.md` вместе со схемой вывода. Изменение промпта означает новую версию, PR и обязательный прогон evals (§31).
- `prompt_version` сохраняется в каждом результате (enrichment, summary, draft), поэтому видно, какая версия что породила.
- Рубрика iGaming relevance — **данные, а не промпт**: она хранится в `app_settings`, редактируется Admin и подставляется в промпт. Admin меняет «что важно для бизнеса», не трогая инженерные инструкции.
- **Альтернатива:** промпты в БД с UI-редактором. **Компромисс:** при подходе «промпты в git» менять их могут только разработчики, зато есть ревью и evals. Для фактической корректности это важнее.

### 8.4. Обогащение статьи (один вызов на статью)

Вход: title, lead, текст (усечённый до N токенов), источник, дата публикации, список кандидатов-алиасов из taxonomy (prompt-cached).
Выход (схема): `language, sport, competition_mention, entities[{mention, kind, canonical_guess}], claims[], rumor_markers[], clickbait, event_date_hint, relevance{level, rationale}`.

**Почему один вызов вместо десяти отдельных классификаторов:** в 5–10 раз дешевле и быстрее, а признаки согласованы между собой.
**Альтернатива:** классические модели (fastText для спорта, NER spaCy pt). Они дешевле на объёме, но требуют обучения и разметки, хуже работают со сленгом и не дают rationale.
**Компромисс:** зависимость от LLM для каждой статьи. Предусмотрен путь деградации: правило «sport по разделу RSS/URL» как fallback.

Entity linking выполняется детерминированно: алиас из `entity_aliases` (exact, unaccent) → trigram similarity ≥ порога → иначе `unlinked mention`, видимый в admin для пополнения справочника.

### 8.5. Кластеризация и дедупликация

Три уровня дедупликации:
1. **URL:** `canonical_url` UNIQUE.
2. **Контент (синдикация):** одинаковый `content_hash` (SimHash по нормализованному тексту) у разных URL. Статья помечается как копия, прикрепляется к тому же Event и **не** считается независимым подтверждением.
3. **Семантика (событие):** скоринг кандидатов.

Скоринг кандидата (Event в окне 72 ч, тот же sport или Unclassified):

```text
score = 0.6 · cos(embedding_article, centroid_event)
      + 0.3 · jaccard(linked_entities_article, entities_event)
      + 0.1 · same_competition
      − штраф, если claims по одному (субъект, атрибут) несовместимы по времени
```

- `score ≥ T_high` (около 0.82) → attach; `score ≤ T_low` (около 0.6) → new Event; между порогами → LLM-adjudication (короткий промпт: «описывают ли эти тексты один и тот же факт? yes/no/related»). `related` создаёт новый Event со связью `event_relations(kind=related)`.
- Пороги и веса хранятся в `app_settings` и калибруются по evals. Это калибровочная ручка, а не константа.
- Кандидаты выбираются через pgvector HNSW (`top-k=20`) с фильтром по времени и спорту.

**Почему гибрид (векторы + сущности + LLM в серой зоне):** только векторы склеивают «Flamengo победил» и «Flamengo проиграл» (похожие тексты), а только LLM по всем парам дорог (O(n) вызовов на статью).
**Альтернативы:** HDBSCAN или пакетная кластеризация раз в N минут (лучше глобальная структура, но хуже задержка и нестабильны ID событий, а редактор теряет «своё» событие); только LLM.
**Компромисс:** онлайн-кластеризация зависит от порядка поступления статей. Исправляется ручными merge/move, а также фоновым `suggest_merges` (post-MVP).

### 8.6. Reliability (детерминированная политика)

| Правило (сверху вниз, первое совпавшее) | Уровень |
|---|---|
| Есть источник OFFICIAL (клуб, федерация, лига) с claim `confirmed` и нет открытых конфликтов | HIGH |
| ≥ 2 независимых (`owner_group`) источника tier A, нет rumor markers, нет конфликтов | HIGH |
| Открытый конфликт по ключевому атрибуту | ≤ MEDIUM (cap) |
| 1 источник tier A **или** ≥ 2 независимых tier B, без rumor markers | MEDIUM |
| Есть rumor markers, или clickbait, или только tier C | LOW |
| Источник без tier (manual/unknown) или нет статей | UNKNOWN |

Факторы сохраняются в `ReliabilityAssessment.factors` и показываются в UI («почему MEDIUM»). Editor может переопределить уровень с обязательной причиной (аудит).
**Альтернатива:** уровень от LLM. Он необъясним, нестабилен и противоречит §10 SRS («reliability assistance», а не «reliability decision»).
**Компромисс:** правила грубые, а tier источника назначает человек. Post-MVP «Source reliability history» позволит пересчитывать tier по статистике.

### 8.7. Grounding черновиков и summary (AC-12)

1. **Evidence pack:** код собирает пронумерованные фрагменты: lead и релевантные абзацы статей события (из `article_content`, пока не истёк TTL), claims с модальностью, список конфликтов, уровень reliability.
2. **Промпт:** писать только на основе evidence; к каждому предложению ставить `[n]`; слухи и спорные утверждения писать в условной модальности; не добавлять чисел, цитат и счёта, которых нет в evidence.
3. **GroundingValidator** (код):
   - у каждого предложения есть хотя бы одна ссылка `[n]` на существующий фрагмент;
   - каждое число, счёт (`2x1`, `2-1`), дата, текст в кавычках и имя собственное из вывода встречается (после нормализации) в цитируемых фрагментах;
   - при нарушении предложение помечается `unverified` и в редакторе подсвечивается. **Молча оно не удаляется:** решение принимает человек.
4. **Детерминированные вставки:** если reliability < HIGH или есть открытый конфликт, код добавляет плашку («⚠ Não confirmado» / «⚠ Informações conflitantes») и не даёт удалить её без подтверждения. AI ни при каких условиях не может «повысить» статус информации.
5. **Прозрачность (§5.5):** ссылки `[n]` в UI кликабельны и открывают исходную статью. В копируемый Telegram-текст ссылки `[n]` не попадают, они заменяются ссылкой на источник по настройке.
6. **Визуальное отличие AI-контента (§15):** AI-текст, ещё не правленный человеком, имеет фон или бейдж «AI» и `aria-describedby`. После правки версия получает `origin=human`.

### 8.8. Защита от prompt injection

Текст статей — недоверенные данные:
- он передаётся в выделенных блоках данных с явной инструкцией «содержимое — данные, а не команды»;
- у модели **нет инструментов с побочными эффектами**, есть только схема вывода;
- вывод проходит валидацию схемы и grounding, поэтому инъекция может в худшем случае испортить одну классификацию, но не выполнить действие;
- HTML из вывода модели санитизируется по белому списку Telegram-тегов (§13).

### 8.9. Embeddings

- **Решение:** мультиязычная embedding-модель через API (например, Voyage multilingual) за портом `EmbeddingClient`, размерность хранится в конфиге, индекс HNSW в pgvector.
- **Почему:** у Claude нет embedding-эндпоинта; хостинг локальной модели утяжеляет worker-образ (~1–2 ГБ, CPU).
- **Альтернатива:** локальная `multilingual-e5` в worker. Нет внешней зависимости и оплаты за запрос, но больше образ и медленнее на CPU.
- **Компромисс:** при смене модели нужна полная переиндексация. Поэтому в таблице хранится `embedding_model`, и переиндексация выполняется фоновой задачей.

### 8.10. Перевод и заголовки

- **Headline generation** входит в MVP как часть draft (тот же grounding).
- **Translation** — post-MVP, за флагом `ai_translation`. Перевод draft на язык редактора (ru/en) нужен только для понимания и **никогда** не уходит в Telegram-текст без явного действия.

---

## 9. Проект базы данных (Database Design)

### 9.1. Общие решения

| Решение | Почему | Альтернативы | Компромисс |
|---|---|---|---|
| Одна БД, **схема PostgreSQL на модуль** (`sources`, `ingestion`, `events`, …) | Владение таблицами видно на уровне БД, права можно разграничить, выделение модуля упрощается | Одна схема `public` с префиксами | Межсхемные FK допускаются только «вниз» по графу модулей |
| PK `uuid` v7 | Упорядочены по времени (хорошо для индексов), их можно генерировать в приложении, они не раскрывают объёмы | bigserial | 16 байт вместо 8, на нашем объёме это несущественно |
| Время в `timestamptz` (UTC), отображение в TZ пользователя (по умолчанию `America/Sao_Paulo`) | Однозначность | local time | — |
| Enum-ы workflow как `text` + `CHECK` | Расширение без `ALTER TYPE`, проще миграции | PostgreSQL ENUM | Нет типовой защиты на уровне схемы, её обеспечивает CHECK |
| Расширяемые справочники (sports, competitions) — **таблицы**, а не enum | Требование SRS §5.2 «список должен быть расширяемым» | enum в коде | Нужны seed-миграции |
| Полуструктурированные результаты AI в `jsonb` + ключевые поля в колонках | Фильтры идут по колонкам, детали (claims, factors) в jsonb, схема AI может эволюционировать | Полная нормализация claims | Claims не индексируются по отдельности (в MVP это не нужно) |
| **Полный текст статей не хранится постоянно** | SRS §16 (copyright и ToS) | Хранить всё | Поиск по «content» работает по lead, summary и сущностям, а не по полному тексту. Текст живёт в `article_content` с TTL (по умолчанию 7 дней, политика на уровне источника) для evidence pack |

### 9.2. ER-диаграмма

```mermaid
erDiagram
  USERS ||--o{ SESSIONS : has
  SOURCES ||--o{ SOURCE_FETCH_RUNS : logs
  SOURCES ||--o{ ARTICLES : publishes
  ARTICLES ||--o| ARTICLE_CONTENT : "transient text"
  ARTICLES ||--o| ARTICLE_ENRICHMENTS : enriched_by
  ARTICLES ||--o{ ARTICLE_ENTITIES : mentions
  ENTITIES ||--o{ ARTICLE_ENTITIES : ""
  ENTITIES ||--o{ ENTITY_ALIASES : known_as
  SPORTS ||--o{ ENTITIES : scopes
  EVENTS ||--|{ EVENT_ARTICLES : clusters
  ARTICLES ||--o| EVENT_ARTICLES : "belongs to"
  EVENTS ||--o{ EVENT_ENTITIES : involves
  ENTITIES ||--o{ EVENT_ENTITIES : ""
  EVENTS ||--o{ EVENT_CONFLICTS : has
  EVENTS ||--o{ EVENT_RELATIONS : relates
  EVENTS ||--o{ TELEGRAM_DRAFTS : has
  TELEGRAM_DRAFTS ||--|{ TELEGRAM_DRAFT_VERSIONS : versions
  USERS ||--o{ AUDIT_LOG : acts
  SPORTS ||--o{ EVENTS : classifies
```

### 9.3. Схема (логическое описание таблиц)

> Ниже приведена схема данных, а не миграции. Типы и ограничения отражают архитектурные инварианты.

```sql
-- identity ---------------------------------------------------------------
users (
  id uuid PK, email citext UNIQUE NOT NULL, display_name text,
  role text NOT NULL CHECK (role IN ('researcher','editor','admin')),
  locale text DEFAULT 'pt-BR', timezone text DEFAULT 'America/Sao_Paulo',
  active bool DEFAULT true, oidc_subject text UNIQUE, created_at, last_login_at
)
sessions (
  id_hash bytea PK,                 -- храним SHA-256 токена, не сам токен
  user_id uuid FK, created_at, last_seen_at, expires_at, ip inet, user_agent text
)

-- sources ----------------------------------------------------------------
sources (
  id uuid PK, name text, base_url text, domain text UNIQUE,
  kind text CHECK (kind IN ('rss','sitemap','html','official','manual')),
  feed_urls text[], parser_profile text,          -- ключ профиля парсинга (селекторы в коде/конфиге)
  tier text CHECK (tier IN ('OFFICIAL','A','B','C')) NULL,
  owner_group text,                               -- 'globo', 'uol', ... для независимости
  language text DEFAULT 'pt-BR',
  poll_interval interval DEFAULT '5 min', min_request_gap interval DEFAULT '2 s',
  content_policy text CHECK (content_policy IN ('snippet_only','transient_text')) DEFAULT 'transient_text',
  content_ttl interval DEFAULT '7 days',
  tos_notes text, active bool DEFAULT true,
  health text DEFAULT 'unknown', next_poll_at timestamptz,
  etag text, last_modified text, version int
)
source_fetch_runs (
  id uuid PK, source_id FK, started_at, finished_at, status text,
  http_status int, items_seen int, items_new int, error_code text, error_detail text
)  -- retention 30 дней

-- ingestion --------------------------------------------------------------
articles (
  id uuid PK, source_id FK, canonical_url text UNIQUE NOT NULL, original_url text,
  title text NOT NULL, lead text,                 -- lead/snippet ≤ ~500 символов
  published_at timestamptz, discovered_at timestamptz NOT NULL,
  image_url text, author text, language text,
  content_hash bigint,                            -- SimHash
  duplicate_of uuid NULL FK articles,             -- синдикация
  manual bool DEFAULT false, added_by uuid NULL,
  state text CHECK (state IN ('discovered','extracted','enriched','clustered','failed')),
  failure_code text,
  search_tsv tsvector GENERATED (title + lead, config 'pt_unaccent')
)
article_content (
  article_id uuid PK FK, text text, extracted_at, expires_at  -- удаляется purge-задачей
)

-- taxonomy ---------------------------------------------------------------
sports (id text PK /* 'football' */, name_i18n jsonb, sort int, active bool)
entities (
  id uuid PK, kind text CHECK (kind IN ('competition','team','player','coach','person','venue')),
  sport_id text FK NULL, canonical_name text, country text,
  external_ids jsonb, priority smallint DEFAULT 0,   -- вес для relevance (Série A, Libertadores…)
  active bool
)
entity_aliases (entity_id FK, alias text, alias_norm text /* unaccent+lower */, PRIMARY KEY (entity_id, alias_norm))
  -- GIN trgm индекс по alias_norm

-- intelligence -----------------------------------------------------------
article_enrichments (
  article_id uuid PK FK,
  sport_id text FK NULL, competition_id uuid FK NULL,
  relevance text, relevance_rationale text,
  clickbait bool, rumor_markers text[], event_date_hint date,
  claims jsonb, raw_entities jsonb,
  embedding vector(1024), embedding_model text,
  prompt_version text, ai_run_id uuid, enriched_at
)
article_entities (article_id FK, entity_id FK, role text, PRIMARY KEY (article_id, entity_id))

-- events -----------------------------------------------------------------
events (
  id uuid PK, title text, title_origin text,
  summary text, summary_origin text, summary_citations jsonb,
  occurred_at timestamptz, first_seen_at, last_article_at, updated_at,
  sport_id text FK, competition_id uuid FK NULL,
  relevance text, relevance_rationale text, relevance_origin text,
  reliability text, reliability_factors jsonb, reliability_origin text,
  status text CHECK (status IN ('NEW','REVIEWING','SELECTED','DRAFT','READY','PUBLISHED','REJECTED')),
  rejection_reason text NULL, rejection_comment text NULL,
  manual_overrides text[] DEFAULT '{}', has_updates_since_edit bool DEFAULT false,
  has_open_conflicts bool DEFAULT false, stale_suspected bool DEFAULT false,
  source_count int, independent_source_count int,  -- денормализация для списка
  centroid vector(1024),
  origin text CHECK (origin IN ('auto','manual')), created_by uuid NULL,
  assignee_id uuid NULL,
  search_doc text,                                 -- title+summary+entity names+source names
  search_tsv tsvector GENERATED (search_doc, 'pt_unaccent'),
  version int NOT NULL DEFAULT 1
)
event_articles (
  article_id uuid PK FK, event_id uuid FK NOT NULL,
  attached_at, attach_score real, attach_method text /* auto|adjudicated|manual */,
  cluster_locked bool DEFAULT false
)
event_entities (event_id FK, entity_id FK, role text, mentions int, PRIMARY KEY (event_id, entity_id))
event_conflicts (
  id uuid PK, event_id FK, subject_entity_id uuid NULL, attribute text,
  positions jsonb,          -- [{article_id, statement, modality}]
  state text CHECK (state IN ('open','resolved','dismissed')), resolved_by uuid NULL, resolution_note text
)
event_relations (event_id FK, related_event_id FK, kind text /* related|follow_up|possible_duplicate|old_news */, score real,
  PRIMARY KEY (event_id, related_event_id))

-- editorial --------------------------------------------------------------
telegram_drafts (
  id uuid PK, event_id FK, state text CHECK (state IN ('generating','ready','failed')),
  current_version int, created_by uuid, created_at, updated_at, version int
)
telegram_draft_versions (
  draft_id FK, n int, body_tg_html text, image_url text NULL, caption text NULL,
  origin text CHECK (origin IN ('ai','human')), citations jsonb, grounding_report jsonb,
  prompt_version text NULL, ai_run_id uuid NULL, author_id uuid NULL, created_at,
  PRIMARY KEY (draft_id, n)
)

-- platform ---------------------------------------------------------------
ai_runs (
  id uuid PK, task text, model text, prompt_version text, input_hash bytea,
  status text, input_tokens int, output_tokens int, cost_usd numeric(10,6), latency_ms int,
  output jsonb, error text, created_at
)  -- UNIQUE (task, prompt_version, model, input_hash) WHERE status='ok' → кэш; retention 90 дней
app_settings (key text PK, value jsonb, updated_by uuid, updated_at)  -- рубрика relevance, пороги, модели
feature_flags (key text PK, enabled bool, roles text[] NULL, description text, updated_by, updated_at)

-- audit ------------------------------------------------------------------
audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PK, at timestamptz, actor_id uuid NULL /* NULL = system */,
  action text, target_type text, target_id uuid, before jsonb, after jsonb, reason text, request_id text
)  -- приложение имеет только INSERT/SELECT (REVOKE UPDATE, DELETE)

-- procrastinate_* : таблицы очереди (управляются библиотекой, своя схема)
```

### 9.4. Индексы (ключевые)

| Индекс | Обслуживает |
|---|---|
| `events (status, relevance, last_article_at DESC, id)` | Основной список Dashboard + keyset-пагинация |
| `events (sport_id, last_article_at DESC)`, `events (competition_id, last_article_at DESC)` | Фильтры (AC-04) |
| `events USING GIN (search_tsv)` | Поиск (AC-05) |
| `event_entities (entity_id, event_id)` | Поиск и фильтр по игроку/команде |
| `entity_aliases USING GIN (alias_norm gin_trgm_ops)` | Нечёткий поиск имён (`Gabigol` ≈ `Gabriel Barbosa` через алиасы) |
| `articles USING GIN (search_tsv)`, `articles (source_id, published_at DESC)` | Поиск по статьям, фильтр по источнику |
| `article_enrichments USING hnsw (embedding vector_cosine_ops)` | Кандидаты кластеризации |
| `events USING hnsw (centroid vector_cosine_ops)` | Похожие и связанные события |
| `audit_log (target_type, target_id, at)` | История объекта |

**Поиск:** собственная конфигурация FTS `pt_unaccent` (portuguese stemmer + unaccent). Запрос пользователя разбирается так: (1) tsquery по `events.search_tsv`; (2) параллельно trigram-поиск по алиасам сущностей → события с этими сущностями; результаты объединяются и ранжируются (`ts_rank` + совпадение сущности + свежесть). Фильтр «Source» реализован через `EXISTS` по `event_articles ⋈ articles`.
- **Почему не Elasticsearch:** на 1–3 млн документов PostgreSQL FTS укладывается в бюджет латентности, а Elasticsearch — это ещё один stateful-кластер и синхронизация данных.
- **Компромисс:** нет продвинутых подсветок, синонимов и «did you mean». Синонимы частично заменяются алиасами сущностей.

### 9.5. Жизненный цикл данных

| Данные | Хранение |
|---|---|
| `article_content.text` | TTL на уровне источника (по умолчанию 7 дней; `snippet_only` вообще не сохраняет текст) |
| articles, events, drafts | Бессрочно (метаданные + собственный контент) |
| `source_fetch_runs` | 30 дней |
| `ai_runs.output` | 90 дней (затем агрегаты) |
| `audit_log` | ≥ 2 лет, append-only |
| sessions | До истечения + 7 дней |

**Миграции:** Alembic, только по схеме expand → migrate → contract (совместимость N и N-1 версий кода для rolling deploy). Детали — в §29.

---

## 10. Стратегия и проектирование API (API Strategy / API Design)

### 10.1. Стратегия

| Решение | Почему | Альтернативы | Компромисс |
|---|---|---|---|
| **REST + JSON**, ресурсно-ориентированный, `/api/v1` | Один клиент (SPA), простые CRUD + действия, кэширование HTTP, OpenAPI-инструменты | GraphQL (гибкость выборок не нужна одному клиенту, усложняет авторизацию и кэш); tRPC (требует TS-бэкенд); gRPC (не для браузера) | Над агрегатами иногда нужно 2 запроса (event + drafts). Решается включениями `?include=` |
| **OpenAPI-first через код** (FastAPI генерирует, CI фиксирует `openapi.json`) | Контракт всегда соответствует реализации, TS-типы генерируются | Ручной spec-first | Изменения контракта видны как diff `openapi.json` в PR |
| Действия workflow как **sub-resource команд** (`POST /events/{id}/transitions`) | Переход статуса — команда с правилами, а не PATCH поля | `PATCH {status}` | Чуть больше эндпоинтов, зато явная семантика и аудит |
| Асинхронные операции → **202 + ресурс со state** + polling | Генерация draft занимает 5–30 с | Long-polling, WebSocket | Задержка polling 1–2 с. Для UX этого достаточно |
| Обновления списка → polling `?updated_since=` каждые 30 с | Простота, работает за любым прокси | SSE через `LISTEN/NOTIFY` | До 30 с задержки. SSE можно добавить за флагом, контракт данных тот же |
| Версионирование: путь `/v1` + только аддитивные изменения | Один клиент, деплоится вместе с API | Header versioning | `/v2` понадобится только при публичных потребителях |

### 10.2. Соглашения

- **Ошибки:** RFC 9457 `application/problem+json`: `{type, title, status, detail, code, errors[], request_id}`. `code` стабилен (`event.invalid_transition`, `draft.version_conflict`) и переводится на фронте.
- **Пагинация:** keyset (cursor) — `?limit=50&cursor=<opaque>`, ответ `{items, next_cursor}`. Offset не используется: список постоянно пополняется, и offset даёт дубли и пропуски.
- **Фильтры:** query-параметры, повторяемые значения через запятую (`relevance=HIGH,MEDIUM`), все комбинируются через AND (AC-04).
- **Конкурентность:** `ETag: "<version>"` в ответе, `If-Match` обязателен для PATCH и переходов (иначе 428).
- **Идемпотентность:** заголовок `Idempotency-Key` для `POST /articles` и `POST /events/{id}/drafts`; ключи хранятся 24 ч.
- **Время:** ISO 8601 UTC.
- **Enum-ы:** стабильные ключи (`HIGH`, `NOT_TELEGRAM_WORTHY`), отображаемые названия — на фронте (i18n).
- **AI-маркировка в данных:** каждое текстовое поле, которое может быть AI-сгенерировано, сопровождается `*_origin: "ai" | "human"`.

### 10.3. Ресурсы

| Метод и путь | Назначение | Роль (мин.) |
|---|---|---|
| `GET /auth/login` → redirect IdP; `GET /auth/callback`; `POST /auth/logout` | OIDC | — |
| `GET /me` | Пользователь, роль, локаль, feature flags | любая |
| `GET /events?sport=&competition=&relevance=&reliability=&source=&status=&from=&to=&q=&entity=&updated_since=&cursor=&limit=&sort=` | Список, фильтры и поиск (AC-04, AC-05) | researcher |
| `GET /events/{id}?include=articles,conflicts,related,draft` | Детали (AC-03, AC-06) | researcher |
| `POST /events` | Создать Event вручную | researcher |
| `PATCH /events/{id}` (If-Match) | Правка title, summary, sport, competition, entities → manual override | researcher |
| `PUT /events/{id}/relevance`, `PUT /events/{id}/reliability` | Ручной override с причиной | editor |
| `POST /events/{id}/transitions {to, reason?, comment?}` | Workflow (AC-10) | researcher; `READY`/`PUBLISHED`/восстановление — editor |
| `POST /events/{id}/merge {other_event_id}` | Слияние | researcher |
| `POST /events/{id}/articles/{article_id}/move {target_event_id\|null}` | Перенос и split | researcher |
| `POST /events/{id}/summary:regenerate` | Перегенерировать summary (202) | researcher |
| `PATCH /events/{id}/conflicts/{cid} {state, note}` | Разрешить или отклонить конфликт | editor |
| `POST /events/{id}/drafts` (Idempotency-Key) | Сгенерировать draft (202) | researcher |
| `GET /drafts/{id}`, `GET /drafts/{id}/versions/{n}` | Draft и история | researcher |
| `PATCH /drafts/{id}` (If-Match) `{body_tg_html, image_url, caption}` | Сохранить новую версию (AC-08) | researcher |
| `POST /drafts/{id}:regenerate` | Новая AI-версия | researcher |
| `GET /articles?q=&source=&from=&to=` / `GET /articles/{id}` | Поиск и детали статей | researcher |
| `POST /articles {url}` (Idempotency-Key) | Добавить URL вручную (202) | researcher |
| `GET /taxonomy/sports`, `GET /taxonomy/entities?q=&kind=` | Справочники и autocomplete | researcher |
| `POST/PATCH /taxonomy/...` | Управление справочниками | admin |
| `GET/POST/PATCH /sources`, `GET /sources/{id}/runs`, `POST /sources/{id}:test` | Источники и здоровье (`:test` — пробный fetch без сохранения) | admin |
| `GET/PUT /settings/{key}` | Рубрика relevance, пороги, модели | admin |
| `GET/PUT /feature-flags/{key}` | Флаги | admin |
| `GET/POST/PATCH /users` | Пользователи и роли | admin |
| `GET /pipeline/failures`, `POST /pipeline/failures/{id}:retry` | Ошибки конвейера | admin |
| `GET /audit?target_type=&target_id=` | История действий | editor |
| `GET /analytics/useful-stories?from=&to=&group_by=user\|day` | Продуктовая метрика | editor |
| `GET /healthz`, `GET /readyz` (вне `/api/v1`, без auth) | Liveness и readiness | — |

### 10.4. Пример ответа (форма, не реализация)

```json
{
  "id": "0192…",
  "title": "Flamengo: atacante sofre lesão muscular",
  "title_origin": "ai",
  "summary": { "text": "…[1][3]", "origin": "ai", "citations": [{"n":1,"article_id":"…"}] },
  "sport": {"id":"football","name":"Football"},
  "competition": {"id":"…","name":"Brasileirão Série A"},
  "teams": [{"id":"…","name":"Flamengo"}],
  "players": [{"id":"…","name":"Pedro"}],
  "relevance": {"level":"HIGH","rationale":"Lesão de titular antes do clássico…","origin":"ai"},
  "reliability": {"level":"MEDIUM","origin":"rule",
    "factors":[{"code":"single_tier_a","label_key":"reliability.single_tier_a"}]},
  "status": "REVIEWING",
  "source_count": 7, "independent_source_count": 3,
  "has_open_conflicts": true, "has_updates_since_edit": false,
  "occurred_at": "2026-10-03T14:10:00Z", "last_article_at": "2026-10-03T15:02:00Z",
  "version": 12
}
```

---

## 11. Аутентификация (Authentication)

**Решение:** OIDC Authorization Code Flow + PKCE через корпоративный IdP (Google Workspace или Microsoft Entra ID). После callback создаётся **серверная сессия** в PostgreSQL, браузер получает непрозрачный идентификатор в cookie `__Host-sid; HttpOnly; Secure; SameSite=Lax; Path=/`.

- **Почему:**
  - внутренний инструмент: нет паролей, сброса и MFA на нашей стороне, всё это делает IdP;
  - offboarding сотрудника в IdP закрывает доступ автоматически;
  - серверная сессия отзывается мгновенно (удаление строки), токены не попадают в JS (защита от XSS-кражи), нет проблем refresh token в SPA;
  - SPA и API на одном origin, поэтому cookie работает без CORS.
- **Альтернативы:**
  - JWT в localStorage: уязвим к XSS, сложно отзывать;
  - email + пароль (argon2) + TOTP: своя реализация сброса и MFA, больше поверхность атаки;
  - magic links: зависят от почты, неудобны при ежедневной работе;
  - Auth0/Clerk: внешний вендор для ~20 пользователей избыточен.
- **Компромиссы:** нужен корпоративный IdP (**открытый вопрос**, §33). Fallback, если его нет: magic link с allowlist доменов за тем же интерфейсом `OidcProvider`. Каждый запрос делает lookup сессии в PostgreSQL (индекс по PK, < 1 мс; кэширование в процессе на 30 с допустимо).

> **Обновление 2026-10-12 ([ADR-005](adr/005-single-host-compose-password-login.md)).** Корпоративного IdP может не быть, поэтому fallback реализован как **e-mail + пароль**, а не magic link (почта — ещё один сервис):
> - хэш — `hashlib.scrypt`; лимит — 5 неудач на пару e-mail + IP за 15 мин;
> - сессия, CSRF и cookie — те же;
> - OIDC включается, если заданы `OIDC_*`;
> - первый admin — из `BOOTSTRAP_ADMIN_EMAIL` + `INITIAL_ADMIN_PASSWORD`;
> - пароли задаёт и сбрасывает admin (сброс закрывает сессии пользователя);
> - аварийный сброс — `sportintel-admin set-password`.
>
> MFA и самостоятельного сброса нет.

**Детали:**
- **Доступ:** пользователь должен быть заранее заведён Admin-ом (allowlist по email) **или** входить в разрешённый домен с ролью по умолчанию `researcher` (настройка). Самостоятельной регистрации нет.
- **Время жизни сессии:** скользящий idle timeout 12 ч, абсолютный 7 дней. Re-auth через IdP прозрачен.
- **CSRF:** `SameSite=Lax` + обязательный заголовок `X-CSRF-Token` (double-submit из `GET /me`) на всех небезопасных методах.
- **Logout:** удаление сессии + `end_session_endpoint` IdP.
- **Сервисные учётные записи** (CI smoke-тесты): отдельный пользователь с ролью и токеном только в staging.

---

## 12. Авторизация (Authorization)

**Решение:** RBAC с тремя ролями из SRS, проверка в двух местах:
1. **API-слой** — декларативная зависимость `require(permission)` на роутере (грубая проверка).
2. **Domain-слой** — `WorkflowPolicy` проверяет, может ли роль выполнить конкретный переход (тонкая проверка, которую нельзя обойти новым эндпоинтом).

| Право | Researcher | Editor | Admin |
|---|:-:|:-:|:-:|
| Просмотр, поиск, фильтры, открыть источник | ✓ | ✓ | ✓ |
| Правка Event (title, summary, sport, entities), создание вручную, добавление URL | ✓ | ✓ | ✓ |
| Переходы NEW → REVIEWING → SELECTED → DRAFT, Reject | ✓ | ✓ | ✓ |
| Генерация, правка и копирование draft | ✓ | ✓ | ✓ |
| Merge / move статей | ✓ | ✓ | ✓ |
| **DRAFT → READY, READY → PUBLISHED, восстановление из REJECTED** | — | ✓ | ✓ |
| Override relevance и reliability, разрешение конфликтов | — | ✓ | ✓ |
| Аудит и аналитика | — | ✓ | ✓ |
| Источники, справочники, настройки, флаги, пользователи, pipeline retry | — | — | ✓ |

- **Почему RBAC:** роли SRS однозначно соответствуют наборам прав, а владения ресурсами (multi-tenant) нет (§17 SRS).
- **Альтернативы:** ABAC/ReBAC (OPA, Cedar, OpenFGA) — избыточно; права «на пользователя» — неуправляемо.
- **Компромиссы:** нет правила «редактировать может только автор черновика». Оно и не нужно в небольшой команде, а аудит показывает, кто что менял. Права описаны как константы `Permission` → набор ролей, и добавление роли — это изменение одной таблицы.
- **Принцип «четырёх глаз» (опциональный флаг `require_second_reviewer`):** READY не может выставить автор последней версии draft. Флаг по умолчанию выключен, потому что для 3 человек это может блокировать работу.

---

## 13. Модель безопасности (Security Model)

### 13.1. Границы доверия

```mermaid
flowchart LR
  subgraph Untrusted["Недоверенная зона"]
    WEB["Чужие сайты:<br/>HTML, RSS, изображения"]
    BROWSER["Браузер пользователя"]
    LLMOUT["Вывод LLM"]
  end
  subgraph Trusted["Доверенная зона (наш VPC)"]
    API
    WORKER
    DB[(PostgreSQL)]
  end
  BROWSER -->|"сессия + CSRF + RBAC"| API
  WEB -->|"SSRF-safe fetch, размер/таймаут,<br/>санитизация, данные ≠ инструкции"| WORKER
  LLMOUT -->|"валидация схемы + grounding<br/>+ санитизация HTML"| WORKER
  API --> DB
  WORKER --> DB
```

### 13.2. Угрозы и меры (STRIDE-lite)

| Угроза | Вектор | Меры |
|---|---|---|
| **SSRF** | «Добавить URL вручную», редиректы источников, URL изображений | Только `http(s)`, DNS-резолв и **запрет приватных, loopback, link-local и metadata-адресов** (проверка после резолва и на каждом редиректе, защита от DNS rebinding через pinning IP), ≤ 5 редиректов, таймаут 10 с, лимит 5 МБ, разрешённые content-type. Fetch выполняется только в worker, у которого нет доступа к внутренним сервисам, кроме БД (egress-политика) |
| **Stored XSS** | Заголовки и HTML источников, вывод LLM, draft | Из источников извлекается только текст. Draft хранится как Telegram-HTML и санитизируется **на сервере** белым списком (`b, strong, i, em, u, s, a[href=https], code, pre, blockquote, tg-spoiler`) и повторно при рендере (DOMPurify). Строгий CSP: `default-src 'self'; img-src 'self' https:; script-src 'self'; frame-ancestors 'none'` |
| **Prompt injection** | Текст статьи | §8.8: нет инструментов, валидация схемы, grounding, человек в контуре |
| **CSRF** | Мутации | SameSite=Lax + `X-CSRF-Token` |
| **Кража сессии** | XSS, перехват | HttpOnly, Secure, `__Host-`, HSTS, CSP; токен в БД хранится как хэш |
| **Повышение привилегий** | Прямые вызовы API | RBAC на роутере и в домене; API-тесты матрицы прав |
| **Утечка секретов** | Frontend, логи, репозиторий | Ключи AI, IdP и Sentry только на сервере (SRS §16); secret manager платформы; gitleaks в CI; редактирование секретов в логах |
| **Отказ (DoS) и расходы** | Массовые запросы генерации | Rate limit на пользователя для AI-эндпоинтов, дневной бюджет AI, ограничение размера тела запроса |
| **Подмена данных** | Отрицание действий | Append-only `audit_log` (у роли приложения нет UPDATE и DELETE) |
| **Юридические риски (ToS, copyright)** | Хранение и копирование контента | robots.txt, `tos_notes` и `content_policy` у источника, TTL текста, в draft только перефраз и короткие цитаты с атрибуцией, ссылка на оригинал |
| **Supply chain** | Зависимости | Lock-файлы, Dependabot/Renovate, `pip-audit`/`npm audit`, сканирование образа (Trivy), pinned base image |

### 13.3. Защита данных

- TLS везде (до БД тоже). Шифрование at rest — средствами managed PostgreSQL и бэкапов.
- PII минимальны: email, имя и IP в сессиях. Все пользователи внутренние, данные наружу не уходят.
- В LLM отправляются только тексты статей и рубрика. **Данные пользователей в промпты не попадают.**
- Принцип наименьших привилегий в БД: роль `app` (DML на своих схемах, только INSERT/SELECT на `audit_log`), роль `migrator` (DDL), read-only роль для аналитики и отладки.

### 13.4. Аудит критических действий (SRS §16)

Записываются: смена статуса (с причиной), правка title, summary и relevance/reliability (before/after), сохранение и копирование draft (событие `draft.copied` — сигнал «почти опубликовано»), merge и move, изменения источников, настроек, флагов и ролей, вход и выход. Аудит пишется **в той же транзакции**, что и изменение.

---

## 14. Архитектура фронтенда (Frontend Architecture)

### 14.1. Решения

| Решение | Почему | Альтернативы | Компромисс |
|---|---|---|---|
| **SPA (React + Vite)**, раздаётся тем же web-процессом (или CDN) на том же origin | Внутренний инструмент за логином: SEO и SSR не нужны; одно приложение «master-detail» с интенсивным взаимодействием | Next.js (SSR избыточен, ещё один runtime); HTMX + шаблоны (сложно для превью, редактора и горячих клавиш); Vue/Svelte (одинаково годны, выбор по распространённости) | Первая загрузка тяжелее SSR. Для desktop-инструмента это неважно |
| **TanStack Router** с типизированными search params | Фильтры и выбранное событие живут в URL: ссылку можно отправить коллеге, работает «назад» | React Router | — |
| **TanStack Query** для серверного состояния | Кэш, polling, дедупликация, оптимистичные мутации | Redux Toolkit Query, SWR | — |
| **shadcn/ui (Radix) + Tailwind** | Доступные примитивы (focus, ARIA, клавиатура) и полный контроль над кодом компонентов | MUI, Ant Design (тяжелее, сложнее кастомизировать «под Telegram») | Компоненты копируются в репозиторий и поддерживаются нами |
| **Tiptap** с урезанной схемой для редактора draft | WYSIWYG ровно в пределах возможностей Telegram (bold, italic, underline, strike, link, code, blockquote, spoiler); на выходе Telegram-HTML без конвертации | Markdown-textarea (нужна конвертация и экранирование MarkdownV2, редактор видит разметку); contenteditable вручную | Зависимость от ProseMirror (~100 КБ). Оправдана: редактор — центр работы |
| **Feature-Sliced Design (облегчённый)** | Явные слои и правила импорта, как у бэкенда | Папки по типу (`components/`, `hooks/`), которые не масштабируются | Немного больше папок |

### 14.2. Структура фронтенда

```text
frontend/
├── index.html
├── vite.config.ts
├── src/
│   ├── app/                         # инициализация: providers, router, QueryClient, i18n, ErrorBoundary, auth guard
│   │   ├── routes/                  # файловые маршруты TanStack Router
│   │   └── providers.tsx
│   ├── pages/                       # композиция фич на экран (без бизнес-логики)
│   │   ├── dashboard/               # Filters | EventList | EventDetails (master-detail, §6 SRS)
│   │   ├── event/                   # полноэкранный вид события (тот же EventDetails)
│   │   ├── admin-sources/
│   │   ├── admin-taxonomy/
│   │   ├── admin-settings/          # рубрика relevance, пороги, флаги, пользователи
│   │   ├── admin-pipeline/          # ошибки конвейера, retry
│   │   ├── analytics/
│   │   └── login/
│   ├── features/                    # пользовательские сценарии (UI + хуки + мутации)
│   │   ├── event-filters/           # фильтры ↔ URL search params
│   │   ├── event-search/
│   │   ├── event-list/              # виртуализированный список, горячие клавиши j/k
│   │   ├── event-details/
│   │   ├── event-sources/           # источники и связанные статьи (AC-06)
│   │   ├── event-conflicts/         # ⚠ Conflicting reports (AC-11)
│   │   ├── event-workflow/          # кнопки статусов, диалог Reject с причинами
│   │   ├── event-edit/              # правка полей, merge/move
│   │   ├── telegram-draft/          # editor (Tiptap) | preview | copy | grounding highlights
│   │   └── manual-ingest/           # добавить URL, создать Event
│   ├── entities/                    # доменные сущности фронта: типы, query-ключи, мелкий UI
│   │   ├── event/                   # RelevanceBadge, ReliabilityBadge, StatusChip, eventQueries
│   │   ├── article/
│   │   ├── source/
│   │   ├── draft/
│   │   └── user/                    # useMe(), can(permission)
│   └── shared/
│       ├── api/                     # generated/ (из openapi.json) + http-клиент (CSRF, problem+json → AppError)
│       ├── ui/                      # shadcn-компоненты, AiContentMark, Kbd, EmptyState
│       ├── lib/
│       │   ├── telegram/            # sanitize, render preview, toClipboard (html + plain)
│       │   ├── datetime.ts          # Intl, относительное время, TZ
│       │   └── draft-autosave.ts    # localStorage-буфер несохранённого черновика
│       ├── i18n/                    # каталоги pt-BR, en, ru
│       └── config/                  # build-time конфиг (без секретов)
└── tests/
    ├── e2e/                         # Playwright + axe
    └── setup/                       # MSW-хэндлеры для component-тестов
```

Правило импорта: `app → pages → features → entities → shared`, только вниз. Проверяется `eslint-plugin-boundaries`.

### 14.3. Ключевые UI-решения под метрику «Useful Stories per Hour»

- **Master-detail без перезагрузки:** выбор события меняет только `?event=<id>`, детали подгружаются с prefetch при наведении или фокусе.
- **Горячие клавиши триажа:** `j/k` — следующее и предыдущее событие, `s` — Select, `r` — Reject (диалог причины), `g` — Generate draft, `c` — Copy, `/` — поиск. Справка открывается по `?`.
- **Виртуализация списка** (TanStack Virtual): тысячи событий без лагов.
- **Telegram Preview** рендерится тем же санитизированным Telegram-HTML, что и редактор, в «пузыре» канала (шрифт, ширина около 420 px, превью ссылки, картинка с подписью). Это **один источник истины для превью и копирования**, поэтому они не расходятся.
- **Copy:** `navigator.clipboard.write` с `text/html` и `text/plain` одновременно. Проверка вставки форматирования в Telegram Desktop и Web входит в приёмочные тесты; если какой-то клиент не воспринимает HTML, остаётся plain-text версия с сохранёнными эмодзи и ссылками.
- **Визуальное отличие AI-контента:** компонент `AiContentMark` (иконка + фон + подпись «AI · não revisado»), который снимается после правки человеком.

---

## 15. Управление состоянием (State Management)

| Вид состояния | Где живёт | Пример |
|---|---|---|
| **Серверное** | TanStack Query cache | события, детали, черновики, справочники |
| **Навигационное и шаринговое** | URL (search params) | фильтры, поисковый запрос, выбранное событие, вкладка |
| **Локальное UI** | `useState` / `useReducer` в компоненте | открыт ли диалог, текущий ввод |
| **Черновик в процессе редактирования** | Tiptap state + `localStorage`-буфер до подтверждения сервером | несохранённый текст draft |
| **Предпочтения пользователя** | `localStorage` (+ `users.locale/timezone` на сервере) | ширина панелей, плотность списка |
| **Сессия и права** | `useMe()` (Query) | роль, флаги, локаль |

- **Почему без глобального store (Redux, Zustand):** почти всё состояние серверное или навигационное, а для этого есть специализированные инструменты. Глобальный store дублировал бы кэш и URL.
- **Альтернатива:** Redux Toolkit как единый store. **Компромисс:** если появится сложное кросс-панельное клиентское состояние (например, многошаговый мастер), Zustand добавляется локально для этой фичи.
- **Политики кэша:** список событий `staleTime 15s` + `refetchInterval 30s` (только при видимой вкладке); детали события `staleTime 10s`; справочники `staleTime 10m`; draft в состоянии `generating` опрашивается раз в 1.5 с, затем polling прекращается.
- **Оптимистичные обновления** только для обратимых действий (смена статуса): при ошибке выполняется откат и показывается toast. Сохранение draft не оптимистично: ждём подтверждения сервером, потому что потеря текста недопустима.
- **Конфликт правок (409):** UI показывает «Событие изменено пользователем X», diff полей и кнопки «Перезагрузить» или «Перезаписать». Вторая доступна, только если пользователь видел diff.

---

## 16. Уведомления (Notifications)

**MVP: только in-app.**
- Бейдж «N новых HIGH» над списком (по `updated_since`) и подсветка новых строк.
- Опционально `Notification API` браузера для HIGH relevance при фоновой вкладке (пользователь включает сам).
- Admin-баннеры: источник DOWN, рост очереди, исчерпание AI-бюджета, ошибки конвейера.
- Toast-ы о результате действий (draft готов, конфликт правок).

**Post-MVP (за флагом `notify_telegram_bot`):** Telegram-бот, присылающий в личку редакторам HIGH + reliability ≥ MEDIUM события. Реализуется задачей `notify_high_relevance`, поставленной из `refresh_event` при **переходе** relevance в HIGH (не на каждом пересчёте), с дедупликацией по event_id.

- **Почему не email и не push в MVP:** пользователи работают в инструменте в течение смены; email для новостей с жизнью в минуты бесполезен.
- **Альтернативы:** Slack/Telegram-бот сразу; web push через service worker.
- **Компромисс:** вне вкладки пользователь ничего не узнаёт. Это приемлемо для MVP, и путь расширения описан выше. Канал уведомлений оформлен портом `Notifier` только тогда, когда появится первая реализация.

---

## 17. Интеграции со сторонними сервисами (Third-party Integrations)

| Интеграция | Порт / адаптер | Режим отказа | Примечание |
|---|---|---|---|
| **Новостные источники** | `HttpFetcher` (`platform/safe_fetch`) + профили парсинга (`ingestion/infrastructure/parsers/<profile>.py`): RSS (feedparser), sitemap-news, HTML (trafilatura + селекторы профиля) | Backoff, health источника, статья с частичными данными (только title + URL) лучше, чем ничего | **Предпочтение RSS и sitemap**, а не HTML-скрапингу (стабильность, ToS). Для каждого профиля есть contract-тест на сохранённых фикстурах. Новый источник со стандартным RSS добавляется без кода (только запись в `sources`), нестандартный — новым профилем |
| **Anthropic Claude** | `LlmClient` | Retry с jitter, circuit breaker, деградация (§19) | Ключ только на сервере; бюджет; журнал `ai_runs` |
| **Embeddings API** | `EmbeddingClient` | Retry, при недоступности кластеризация по сущностям и FTS-похожести (хуже, но работает) | Модель зафиксирована в конфиге |
| **OIDC IdP** | `OidcProvider` (authlib) | Нет входа новых сессий, существующие работают | Discovery по `.well-known` |
| **Sentry** | SDK | Fire-and-forget | PII-scrubbing включён (`send_default_pii=False`) |
| **Telegram Bot API** (post-MVP) | `TelegramPublisher`, `Notifier` | Очередь + retry | Публикация только из статуса READY с явным подтверждением. Draft уже хранится в Telegram-HTML (`parse_mode=HTML`), поэтому конвертация не нужна |
| **Спортивные данные** (future: календарь матчей, составы) | `FixturesProvider` | — | Обогатит relevance («матч через 2 дня») и проверку фактов. Вне MVP |

**Общие правила интеграций:** у каждого внешнего вызова есть таймаут, ограниченные ретраи с backoff и jitter, корреляционный `request_id` в логах и fake-реализация для тестов и local. Ни одна интеграция не вызывается из request path API, кроме IdP при логине.

---

## 18. Кэширование (Caching)

| Уровень | Что кэшируется | Механизм | Инвалидация |
|---|---|---|---|
| HTTP к источникам | Ленты RSS и sitemap | `ETag` / `If-Modified-Since` (хранятся в `sources`) | По ответу источника |
| Результаты AI | Обогащение, adjudication, conflict check | `ai_runs` с ключом `(task, prompt_version, model, input_hash)` | Новая версия промпта или модели означает новый ключ |
| Провайдер AI | Длинные стабильные префиксы промптов (инструкции, рубрика, алиасы) | Prompt caching Anthropic | Автоматически по TTL провайдера |
| Агрегаты списка | `source_count`, `independent_source_count`, `has_open_conflicts`, `search_doc` | Денормализация в `events` при `refresh_event` | В той же транзакции, что и изменение |
| Аналитика | Метрики за периоды | Materialized views | `REFRESH … CONCURRENTLY` каждые 15 мин |
| Справочники и настройки в процессе | sports, флаги, `app_settings` | In-process TTL-кэш 30–60 с | По TTL (Admin видит эффект через ≤ 1 мин) |
| Статика фронтенда | JS, CSS | Хэшированные имена + `Cache-Control: immutable`; `index.html` — `no-cache` | При деплое |
| Клиент | Ответы API | TanStack Query (§15) | `invalidateQueries` после мутаций |

- **Почему без Redis:** единственный процесс-потребитель кэша — web на 1–2 инстансах. In-process кэш с коротким TTL и денормализация в PostgreSQL покрывают потребности.
- **Альтернатива:** Redis для кэша, rate limit и сессий.
- **Компромисс:** rate limit «на пользователя» при нескольких инстансах web считается по инстансам (неточно). Если это станет важно или web масштабируется больше чем до 2 инстансов, добавляется Redis, и это изолированное изменение в `platform`.
- **HTTP-кэш API не используется** (данные приватные и часто меняются), только `ETag` для конкурентности.

---

## 19. Обработка ошибок (Error Handling)

### 19.1. Таксономия ошибок бэкенда

| Класс | Пример | HTTP | Поведение |
|---|---|---|---|
| `ValidationError` | Неверный фильтр | 400/422 | problem+json с `errors[]` по полям |
| `NotAuthenticated` / `Forbidden` | Нет сессии или роли | 401 / 403 | Фронт: редирект на login или сообщение |
| `NotFound` | Нет события | 404 | — |
| `DomainRuleViolation` | `event.invalid_transition`, `event.override_locked` | 409/422 | Стабильный `code`, локализуемое сообщение |
| `ConcurrencyConflict` | Устаревший `If-Match` | 409 / 412 | UI показывает diff |
| `PreconditionRequired` | Нет `If-Match` | 428 | — |
| `RateLimited` / `BudgetExceeded` | Слишком много генераций, исчерпан AI-бюджет | 429 | `Retry-After` |
| `DependencyUnavailable` | AI или embeddings лежат (для синхронных проверок) | 503 | Редко, так как AI вызывается только в worker |
| Неожиданная | Баг | 500 | Sentry + `request_id` в ответе, без stack trace |

Доменные ошибки — типизированные исключения в `domain/errors.py`. Маппинг в HTTP выполняется **в одном месте** (`platform/http_api.py`). Use case не знают об HTTP.

### 19.2. Ошибки в конвейере (worker)

- **Транзиентные** (сеть, 5xx, 429, таймаут, ошибка схемы AI): ретрай с экспоненциальным backoff и jitter (§7.2).
- **Постоянные** (404 статьи, неподдерживаемый контент, нарушение политики): сразу `state=failed` с `failure_code`, без ретраев.
- **После исчерпания ретраев:** `failed`, видно в Admin → Pipeline, ручной retry.
- **Частичный успех лучше полного отказа:** статья без текста сохраняется (title + URL); без обогащения — Sport=Unclassified; без embedding кластеризуется по сущностям.

### 19.3. Деградация при отказе AI

| Отказ | Что продолжает работать | Что пользователь видит |
|---|---|---|
| LLM недоступен или бюджет исчерпан | Ingestion, список статей, поиск, фильтры, ручные Event, ручной draft | Баннер «AI temporariamente indisponível», новые статьи в Unclassified, кнопка Generate неактивна с пояснением |
| Embeddings недоступны | Кластеризация по сущностям + FTS-похожести заголовков | Чуть больше дублей событий |
| Источник недоступен | Остальные источники | Health в admin, пометка у ссылок |
| БД недоступна | — | `/readyz` = 503, страница ошибки, конвейер на паузе (задачи переживают рестарт) |

### 19.4. Фронтенд

- **Error boundary на панель** (фильтры, список, детали, draft): падение одной панели не ломает экран.
- `problem+json` → `AppError{code, status, requestId}` → локализованное сообщение по `code` с fallback на `title`. `request_id` можно скопировать для багрепорта.
- Мутации: toast с действием «Повторить». Сохранение draft при ошибке **не теряет текст** (буфер в localStorage, §20).
- Сетевые ошибки запросов: автоматический retry TanStack Query (3 раза, только для GET).

---

## 20. Стратегия офлайн-работы (Offline Strategy)

**Решение: online-only приложение с защитой от потери ввода.** Полноценный офлайн (PWA, Service Worker, локальная БД, синхронизация) **не проектируется**.

- **Почему:** ценность продукта в свежих новостях и AI-обработке, которые требуют сети. Пользователи работают на desktop в офисе. SRS офлайн не требует.
- **Что делается:**
  - Индикатор соединения (`navigator.onLine` + неудачные запросы) с баннером «Sem conexão — alterações não salvas».
  - **Автосохранение черновика** в `localStorage` при каждой правке (debounce 1 с) с ключом `draft:{id}:{base_version}`. Буфер очищается после подтверждения сервером. При возврате на страницу, если буфер новее сервера, предлагается восстановить.
  - Последние загруженные данные остаются на экране (кэш TanStack Query), мутации блокируются с понятным сообщением.
- **Альтернативы:** PWA с offline-first и очередью мутаций; IndexedDB-реплика.
- **Компромисс:** без сети работать нельзя. Конфликты офлайн-правок не возникают, потому что нет офлайн-мутаций.

---

## 21. Интернационализация (Internationalization)

Два независимых измерения:

**1. Язык интерфейса (UI locale):**
- i18next + ICU MessageFormat (множественные числа: «1 fonte / 7 fontes»), каталоги `pt-BR` (обязателен по SRS §15), `en`, `ru` (команда пишет SRS на русском, поэтому вероятно нужен). Каталоги по неймспейсам фич.
- Локаль хранится в `users.locale`, переключается в профиле.
- Даты и числа — `Intl.DateTimeFormat`/`Intl.RelativeTimeFormat` в TZ пользователя (по умолчанию `America/Sao_Paulo`).
- Названия enum-ов и справочников: enum-ы переводятся на фронте по ключу, справочники хранят `name_i18n jsonb`.
- CI-проверка: отсутствующие ключи в обязательной локали `pt-BR` ломают сборку.

**2. Язык контента:**
- Статьи на pt-BR. FTS-конфигурация `portuguese` + unaccent (`São Paulo` = `sao paulo`).
- Telegram draft генерируется на **языке канала** (`app_settings.telegram_language`, по умолчанию pt-BR), независимо от языка UI.
- Rationale и summary генерируются на языке `analysis_language` (по умолчанию pt-BR, настраивается Admin-ом).
- Перевод для понимания (post-MVP) показывается отдельным блоком с пометкой «tradução automática» и не смешивается с оригиналом.

- **Почему i18next:** зрелый, есть ICU, lazy-загрузка неймспейсов.
- **Альтернативы:** FormatJS/react-intl (равноценен), Lingui (компиляция каталогов).
- **Компромисс:** перевод AI-текстов (rationale) на язык UI в MVP не делается, rationale показывается на языке анализа.

---

## 22. Доступность (Accessibility)

**Цель:** WCAG 2.2 AA для всех экранов.

- **Примитивы Radix:** корректные роли, фокус и клавиатура для диалогов, меню, select и tabs.
- **Полностью клавиатурная работа** (горячие клавиши из §14.3 + видимый фокус). Горячие клавиши не перехватываются в полях ввода, и их можно отключить в настройках (WCAG 2.1.4).
- **Информация не передаётся только цветом:** relevance и reliability = иконка + текст + цвет (`🔥 HIGH`, `⚡ MEDIUM`). Конфликт = иконка ⚠ + текст.
- **Master-detail:** при выборе события фокус переходит на заголовок деталей, `aria-live="polite"` объявляет «Evento carregado». Новые события в списке объявляются сводно («3 novos eventos»), а не по одному.
- **AI-контент** помечен визуально и через `aria-describedby` («Texto gerado por IA, não revisado»).
- Telegram preview имеет `role="article"` и `aria-label`. Эмодзи в тексте не заменяются, скринридер читает их нативно.
- Контраст токенов темы ≥ 4.5:1, поддержка `prefers-reduced-motion`, масштабирование до 200 % без потери функций (desktop-first, но с гибкой разметкой).
- **Проверка:** axe-core в Playwright на каждом ключевом экране (CI), eslint-plugin-jsx-a11y, ручная проверка клавиатурой и скринридером перед релизом.

---

## 23. Конфигурация (Configuration)

Три уровня конфигурации с разными владельцами и циклами изменения:

| Уровень | Где | Кто меняет | Примеры | Перечитывание |
|---|---|---|---|---|
| **Инфраструктурная** | Переменные окружения → `pydantic-settings` (типизация, валидация при старте, fail-fast) | DevOps / деплой | `DATABASE_URL`, `ANTHROPIC_API_KEY`, `OIDC_*`, `SENTRY_DSN`, `ENV`, параллелизм воркеров | Рестарт |
| **Бизнес-настройки (runtime)** | `app_settings` (jsonb + JSON Schema-валидация) | Admin в UI, с аудитом | Рубрика iGaming relevance, пороги кластеризации, маршрутизация моделей, дневной AI-бюджет, TTL контента по умолчанию, язык канала | ≤ 60 с (TTL-кэш) |
| **Данные-справочники** | Таблицы `sources`, `sports`, `entities` | Admin | Источники, виды спорта, турниры, команды, алиасы | Сразу |
| **Код-конфигурация** | Репозиторий | Разработчики через PR | Промпты, профили парсинга, state machine, политика reliability | Деплой |

- Секреты **никогда** не лежат в репозитории и `app_settings`: только secret manager платформы → env.
- Frontend получает только публичную конфигурацию (через `GET /me` и build-time переменные без секретов).
- **Почему разделение:** разная частота изменений и разный уровень риска. Рубрику бизнес меняет еженедельно, промпт требует evals, URL БД меняется раз в год.
- **Альтернатива:** всё в env или всё в БД. **Компромисс:** нужно помнить, где какой параметр. Решается таблицей выше в README.

---

## 24. Флаги функций (Feature Flags)

**Решение:** собственная минимальная реализация: таблица `feature_flags (key, enabled, roles[])` + значение по умолчанию из env + in-process кэш 30 с. Флаги отдаются фронту в `GET /me`.

- **Почему:** нужны простые булевы флаги с таргетингом по роли для ~20 пользователей. Проценты раскатки и эксперименты не нужны.
- **Альтернативы:** Unleash, Flagsmith (self-hosted, ещё один сервис); LaunchDarkly (платно, внешние данные); флаги только в env (нужен деплой).
- **Компромисс:** нет процентного rollout и A/B. Если они понадобятся, вызов `flags.is_enabled(key, user)` заменяется адаптером к Unleash без изменения точек вызова.

**Кандидаты на флаги:**

| Флаг | Назначение |
|---|---|
| `ai_translation` | Post-MVP перевод |
| `sse_updates` | SSE вместо polling |
| `notify_telegram_bot` | Уведомления в Telegram |
| `telegram_publish` | Публикация через Bot API после approval |
| `require_second_reviewer` | Принцип четырёх глаз |
| `cluster_adjudication_llm` | Kill switch для LLM в серой зоне кластеризации |
| `prompt.<task>.canary` | Новая версия промпта для роли admin перед общим включением |

**Гигиена:** у каждого флага есть `description` и владелец. Флаги, включённые везде дольше 30 дней, удаляются из кода (проверка в CI по списку).

---

## 25. Управление окружениями (Environment Management)

| Окружение | Назначение | БД | AI | Источники | Доступ |
|---|---|---|---|---|---|
| **local** | Разработка | Docker Compose PostgreSQL + seed (справочники, ~200 статей-фикстур) | **Fake** по умолчанию, реальный по флагу с личным ключом | Записанные фикстуры (VCR-подобно) или 2–3 реальных RSS | Dev-логин без IdP (только `ENV=local`, жёсткая проверка) |
| **ci** | Автотесты | Эфемерный PostgreSQL (service container) | Fake | Фикстуры | — |
| **staging** | Приёмка, проверка миграций, evals на живых данных | Отдельная managed БД | Реальный, **отдельный ключ и низкий бюджет** | Подмножество реальных источников | IdP, ограниченная группа |
| **production** | Работа | Managed PostgreSQL с PITR (целевое); сейчас — PostgreSQL в `compose.yaml` + ежедневный дамп (ADR-005) | Реальный, рабочий бюджет | Все активные | IdP или пароль (ADR-005) |

- **Паритет:** один и тот же Docker-образ во всех окружениях, различаются только env и секреты (12-factor).
- **Данные:** production-данные в staging не копируются (ToS-контент и данные пользователей). Staging наполняется собственным ingestion.
- **Preview-окружения на PR** не нужны: команда маленькая, staging достаточно. Это можно пересмотреть при росте команды.
- **Почему так:** минимальное число окружений, которое даёт безопасную проверку миграций и промптов перед продом.
- **Компромисс:** staging-ingestion создаёт нагрузку на источники. Поэтому выбирается подмножество источников с увеличенным интервалом опроса.

---

## 26. Логирование (Logging)

- **Формат:** структурированный JSON (structlog) в stdout. Сбор выполняет платформа (Loki, CloudWatch, Better Stack), приложение о хранилище логов не знает.
- **Обязательные поля:** `ts, level, env, service (web|worker), version (git sha), request_id | job_id, user_id (uuid, не email), module, event`.
- **Корреляция:** `request_id` из заголовка или сгенерированный передаётся в поставленные задачи (`job.meta.request_id`). Цепочка «клик Generate → задача → AI run» восстанавливается одним запросом по id. В логах конвейера также есть `source_id, article_id, event_id, ai_run_id`.
- **Уровни:** `INFO` — бизнес-факты (статья обнаружена, событие создано, переход статуса); `WARNING` — деградации и ретраи; `ERROR` — исчерпанные ретраи и 5xx; `DEBUG` выключен в prod.
- **Чего никогда нет в логах:** токены сессий, ключи API, cookie, полный текст статей, тела промптов и ответов LLM (для них есть `ai_runs` с ограниченным доступом и retention), email.
- **Retention:** 30 дней в prod (больше не нужно: долгосрочная история — это `audit_log` и `ai_runs`).
- **Почему JSON в stdout:** стандарт для контейнеров, переносимость между платформами.
- **Альтернатива:** OTel logs (ещё рано; OTel вводится для метрик, логи можно связать позже).
- **Компромисс:** при грепе глазами JSON читать неудобно, поэтому локально используется consolerenderer structlog.

---

## 27. Мониторинг (Monitoring)

### 27.1. Сигналы

| Категория | Метрика / сигнал | Источник |
|---|---|---|
| **Доступность** | `/healthz` (жив процесс), `/readyz` (БД доступна, миграции применены) | Uptime-проверка внешним сервисом |
| **API (RED)** | rate, errors, duration p50/p95/p99 по маршрутам | OTel → Prometheus-совместимый backend (Grafana Cloud / managed) |
| **Очередь** | Глубина по очередям, возраст старейшей задачи, failed/min | SQL по таблицам Procrastinate (экспортер-задача) |
| **Свежесть данных (ключевая)** | **Ingest lag** = `discovered_at − published_at` (p95); **time-to-event** = `clustered_at − published_at` | Метрики из worker |
| **Источники** | Успешность fetch по источнику, «нет новых статей N часов при обычной активности» (тихий отказ парсера) | `source_fetch_runs` |
| **AI** | Вызовы, ошибки, ошибки схемы, латентность, **стоимость/день** по task и model, cache hit rate | `ai_runs` |
| **Качество AI (дрейф)** | Доля Unclassified, доля adjudication в серой зоне, ручные merge/move на 100 событий, доля `unverified` предложений в draft | SQL-агрегаты |
| **Ошибки** | Исключения с контекстом, релизы, регрессии | Sentry (web, worker, frontend) |
| **Инфраструктура** | CPU, RAM, соединения БД, место на диске, replication lag | Платформа / managed DB |

### 27.2. Алерты (минимальный набор, всё остальное — дашборды)

| Алерт | Условие | Почему важно |
|---|---|---|
| Сервис недоступен | `/readyz` failing > 2 мин | Нет работы |
| Конвейер стоит | Возраст старейшей задачи в `fetch`/`ai` > 15 мин | Нарушается NFR «минимальная задержка» |
| Ingest lag | p95 > 15 мин за 30 мин | То же |
| Источник молчит | Tier A/OFFICIAL без новых статей > 6 ч в активные часы, или 5 подряд ошибок | Сломался парсер (тихий отказ) |
| AI-бюджет | > 80 % дневного лимита | Деградация к концу дня |
| AI error rate | > 20 % за 10 мин | Circuit breaker, проверить провайдера |
| Всплеск 5xx | > 2 % за 5 мин | Баг или релиз |

Канал алертов — тот же Telegram или Slack команды. On-call неформальный (внутренний инструмент, рабочие часы).

- **Почему:** самые опасные отказы здесь **тихие** (парсер перестал находить статьи, AI начал всё складывать в Unclassified), поэтому мониторятся бизнес-сигналы свежести и качества, а не только CPU.
- **Альтернативы:** только Sentry + uptime (не ловит тихие отказы); полный стек Prometheus + Grafana + Alertmanager self-hosted (слишком много ops).
- **Компромисс:** managed observability-сервис стоит денег, но дешевле поддержки собственного стека.

---

## 28. Аналитика (Analytics)

**Решение:** аналитика строится **из собственных данных в PostgreSQL** (`audit_log`, `events`, `ai_runs`) через materialized views и один экран «Analytics» для Editor/Admin. Сторонние продуктовые трекеры не используются.

### 28.1. Основная метрика: Useful Stories per Hour

- **Useful story** — событие, которое пользователь перевёл в `SELECTED` или дальше, **и** которое не было затем отклонено с причиной `DUPLICATE`/`INCORRECT`.
- **Час работы** — активное время редактора: сумма интервалов между действиями в `audit_log` (+ heartbeat «просмотр события») с разрывом сессии при паузе > 15 мин.
- `USpH = useful_stories / active_hours` по пользователю, дню и источнику. Отдельно считается **воронка**: NEW → REVIEWING → SELECTED → DRAFT → READY → PUBLISHED с конверсиями и временем на этапе.

### 28.2. Вспомогательные метрики

| Метрика | Что показывает |
|---|---|
| Time-to-select | Время от `first_seen_at` до SELECTED (насколько быстро находят) |
| Распределение причин Reject | Где шум: `IRRELEVANT` → калибровать рубрику, `DUPLICATE` → калибровать кластеризацию |
| Precision HIGH relevance | Доля HIGH, которые стали useful |
| Draft edit distance | Насколько человек переписывает AI-черновик (нормализованный Левенштейн v1 → final). Метрика качества промпта |
| Источники-лидеры | Какой источник первым сообщил о событиях, ставших useful (задел для «наиболее оперативные источники», §19 SRS) |
| AI cost per useful story | Экономика |

- **Heartbeat просмотра** — единственное поведенческое событие с фронта: `POST /analytics/heartbeat {event_id}` не чаще раза в минуту, хранится в легковесной таблице с retention 90 дней.
- **Почему без Mixpanel/Amplitude/PostHog:** все значимые действия уже есть в аудите на сервере, пользователей мало, данные внутренние и чувствительные.
- **Альтернатива:** PostHog self-hosted. Он даёт session replay и воронки «из коробки», но это отдельный сервис, а нужда не доказана.
- **Компромисс:** нет кликовой аналитики UI (какие кнопки не используются). Если она понадобится, PostHog добавляется за флагом.

---

## 29. Архитектура и стратегия развёртывания (Deployment Architecture / Strategy)

### 29.1. Топология

```mermaid
flowchart TB
  subgraph Internet
    U((Пользователи))
    SRCS[Источники]
    AIP[Anthropic / Embeddings]
  end

  subgraph Cloud["Облако (регион South America — São Paulo)"]
    LB["HTTPS Load Balancer / edge<br/>TLS, HSTS, WAF-правила (опц.)"]
    subgraph Compute["Контейнеры (один образ sportintel:<sha>)"]
      W1["web ×2<br/>uvicorn: API + статика SPA"]
      WK1["worker ×1–2<br/>очереди fetch/ai/cluster/maintenance"]
      WK2["worker-interactive ×1<br/>очередь ai_interactive"]
      MIG["release job:<br/>alembic upgrade"]
    end
    PG[("Managed PostgreSQL 16<br/>pgvector · PITR · ежедневные снапшоты<br/>private network")]
    SM["Secret Manager"]
  end

  OBS["Sentry · Logs · Metrics · Uptime"]

  U --> LB --> W1
  W1 --> PG
  WK1 --> PG
  WK2 --> PG
  MIG --> PG
  WK1 -->|egress| SRCS
  WK1 -->|egress| AIP
  WK2 -->|egress| AIP
  SM -.-> Compute
  Compute -.-> OBS
```

**Решения:**

| Решение | Почему | Альтернативы | Компромисс |
|---|---|---|---|
| **Один образ, несколько типов процессов** (web / worker / worker-interactive / release) | Одна сборка и одна версия кода во всех процессах, нет рассинхронизации | Отдельные образы на модуль | Образ включает зависимости всех процессов (worker тянет trafilatura и в web). Это допустимо |
| **Managed контейнерная платформа** (Cloud Run / ECS Fargate / Fly.io / Render) | Нет администрирования серверов, rolling deploy, секреты, логи | Kubernetes (избыточен для 3 процессов и небольшой команды); VM + Docker Compose (дёшево, но ручные TLS, обновления и деплой) | Зависимость от платформы смягчается тем, что всё упаковано в стандартный Docker без платформенных API. **Бюджетный вариант:** одна VM + Docker Compose + Caddy — та же архитектура, без изменений в коде |
| **Managed PostgreSQL** с pgvector | Бэкапы, PITR, обновления, мониторинг | Self-hosted PostgreSQL | Стоимость; нужно проверить поддержку pgvector и unaccent у провайдера |
| **Регион São Paulo** | Близко к источникам (быстрее fetch) и к целевой аудитории; географическая резидентность данных бразильского рынка | Регион ЕС (если команда там) | Задержка UI для удалённой команды на ~150–200 мс. Для desktop-инструмента это допустимо |
| **SPA раздаётся web-процессом** | Один origin: простые cookie и CSP, нет CORS | CDN/S3 для статики | Нет edge-кэша. Для 20 пользователей это несущественно, CDN можно поставить перед тем же origin |
| **Worker без входящего трафика**, egress разрешён наружу и в БД | Изоляция SSRF-поверхности | — | — |

### 29.2. Стратегия выката

- **Rolling deploy** web (минимум 2 инстанса → без простоя) по readiness-пробе.
- Worker: **graceful shutdown**. При SIGTERM задачи доделываются (таймаут 60 с), незавершённые возвращаются в очередь (задачи идемпотентны).
- **Миграции:** отдельный release-шаг **до** выката кода, только обратно совместимые (expand). Удаление колонок (contract) выполняется в следующем релизе. Тяжёлые изменения данных идут фоновыми задачами, а не в миграции. Индексы — `CREATE INDEX CONCURRENTLY`.
- **Откат:** повторный деплой предыдущего образа (миграции совместимы с N-1). Откат миграций в проде **не делается**, вместо этого выпускается roll-forward.
- **Промпты и модели:** новая версия промпта включается сначала через `prompt.<task>.canary` для admin, затем для всех. Откат промпта — переключение настройки без деплоя.
- **Бэкапы и восстановление:** PITR 7–14 дней + ежедневный снапшот. **RPO ≤ 5 мин, RTO ≤ 2 ч** (внутренний инструмент). Восстановление проверяется раз в квартал на staging.
- **Почему не blue/green или canary-трафик:** при ~20 пользователях rolling + быстрый откат образа дают тот же эффект проще.

### 29.3. Текущая реализация: одна машина (ADR-005)

Пока нет бюджета на managed-платформу, production и staging работают по бюджетному варианту из таблицы §29.1. Корневой `compose.yaml`:
- caddy (HTTPS) → web; worker; db (PostgreSQL 16 + pgvector, без открытого порта);
- разовый migrate;
- backup (`pg_dump` по расписанию);
- опционально ollama.

Установка и обновление: `docker compose up -d --build` — [deploy/README.md](../deploy/README.md).

Отличия от §29.1–29.2:

| Целевое | Сейчас | Чем закрыто |
|---|---|---|
| Rolling deploy, web ×2 | web ×1, перезапуск — секунды | Caddy `lb_try_duration 30s` держит запросы |
| PITR, RPO ≤ 5 мин, RTO ≤ 2 ч | дамп раз в `BACKUP_INTERVAL_H` (24 ч), RTO ~30–60 мин | healthcheck свежести дампа; проверка восстановления раз в квартал |
| Secret Manager | `.env` на сервере | файл вне git, права только у владельца |
| Managed observability | логи Docker (ротация), `deploy/capacity.sql`, Telegram-алерты, опц. Sentry | [OPERATIONS.md](OPERATIONS.md) §2 |
| Release job миграций | сервис `migrate` до web/worker (`service_completed_successfully`) | то же поведение |

Сигналы и лестница перехода к §29.1 (вертикально → worker → ИИ отдельно → managed БД → реплики web → платформа) описаны в [OPERATIONS.md](OPERATIONS.md) §4–5.

---

## 30. CI/CD

### 30.1. Конвейер

```mermaid
flowchart LR
  PR["Pull Request"] --> L["Lint & types<br/>ruff · mypy · eslint · tsc"]
  PR --> AR["Architecture<br/>import-linter · eslint-boundaries ·<br/>владение таблицами"]
  PR --> UT["Unit tests<br/>backend + frontend (Vitest)"]
  PR --> IT["Integration + API tests<br/>Postgres service container"]
  PR --> CT["Contract<br/>OpenAPI diff · TS client up to date ·<br/>parser fixtures"]
  PR --> SEC["Security<br/>gitleaks · pip-audit · npm audit"]
  PR --> EV{"Изменены prompts/<br/>или clustering?"}
  EV -->|да| EVAL["AI evals (реальный API,<br/>бюджет-лимит) → отчёт в PR"]
  L & AR & UT & IT & CT & SEC --> M["Merge в main"]
  M --> B["Build image<br/>+ SBOM + Trivy scan"]
  B --> E2E["E2E Playwright + axe<br/>против образа (fake AI)"]
  E2E --> STG["Deploy → staging<br/>migrate · smoke tests"]
  STG --> GATE{"Manual approval"}
  GATE --> PROD["Deploy → production<br/>migrate · rolling · smoke"]
  PROD --> SENTRY["Sentry release + source maps"]
```

### 30.2. Правила

- **Trunk-based:** короткоживущие ветки, squash merge в `main`, `main` всегда деплоебелен.
- **Обязательные проверки** для merge: всё, кроме evals. Evals обязательны, только если изменены `prompts/**`, `modules/events/domain/policies/clustering.py` или маршрутизация моделей. Регресс метрик больше допуска блокирует merge (§31.4).
- **Артефакт:** образ, тегированный git sha. Один образ проходит staging и prod (build once, deploy many).
- **Production:** ручное подтверждение (GitHub Environments) + автоматический smoke (`/readyz`, логин сервисного пользователя на staging, `GET /events`).
- **Ночные задачи CI:** полный прогон evals на свежей выборке staging, dependency update PR (Renovate), проверка восстановления бэкапа (раз в квартал).
- **Почему GitHub Actions:** интеграция с репозиторием, Environments с approval, бесплатных минут для объёма хватит.
- **Альтернативы:** GitLab CI, CircleCI — равноценны. Выбор определяется хостингом репозитория.
- **Компромисс:** ручной gate на prod замедляет выкат. Его можно снять, когда smoke-тесты и мониторинг станут надёжными.

---

## 31. Стратегия и архитектура тестирования (Testing Strategy / Architecture)

### 31.1. Пирамида

```mermaid
flowchart TB
  E2E["E2E (Playwright + axe)<br/>~10–15 сценариев = AC-01…AC-12"]
  EVAL["AI evals<br/>golden datasets, метрики качества"]
  API["API tests<br/>HTTP, RBAC-матрица, problem+json"]
  INT["Integration<br/>use cases + репозитории на реальном Postgres<br/>(FTS, pgvector, блокировки, очередь)"]
  CON["Contract<br/>парсеры источников на фикстурах · OpenAPI"]
  UNIT["Unit<br/>domain: state machine, reliability, clustering score,<br/>grounding validator, URL canonicalizer · frontend: telegram sanitize/render"]
  UNIT --> CON --> INT --> API --> EVAL --> E2E
```

### 31.2. Слои тестов

| Слой | Что покрывает | Инструменты | Скорость / когда |
|---|---|---|---|
| **Unit (domain)** | State machine (все разрешённые и запрещённые переходы × роли), `ReliabilityPolicy` (таблица правил как табличный тест), скоринг кластеризации, `GroundingValidator` (числа, цитаты, имена, отсутствие ссылок), canonicalizer, санитайзер Telegram-HTML. **Самое важное для AC-11/AC-12 тестируется здесь детерминированно** | pytest, hypothesis (свойства canonicalizer и sanitizer) | Секунды, на каждый коммит |
| **Contract (парсеры)** | Для каждого профиля источника сохранённые RSS и HTML → ожидаемые title, lead, published_at, image. Еженедельная задача обновляет фикстуры с реальных сайтов и показывает diff (раннее обнаружение изменений вёрстки) | pytest + фикстуры | Секунды |
| **Contract (API)** | `openapi.json` в репозитории совпадает со сгенерированным; TS-клиент актуален; breaking changes (oasdiff) запрещены без явной метки | oasdiff | CI |
| **Integration** | Use case целиком на реальном PostgreSQL: ingestion → enrichment (fake AI) → clustering → refresh; конкурентная кластеризация (две статьи одного факта параллельно дают **один** Event); поиск pt-BR (акценты, стемминг); keyset-пагинация; транзакционная постановка задач; append-only аудит | pytest + testcontainers, fake `LlmClient`/`EmbeddingClient`/`HttpFetcher` | Минуты, на PR |
| **API** | Аутентификация и сессии, CSRF, матрица RBAC (каждый эндпоинт × роль, генерируется из таблицы прав), формат ошибок, `If-Match`/409, идемпотентность | httpx AsyncClient | На PR |
| **Frontend component** | Фильтры ↔ URL, список, Telegram preview (рендер bold/italic/links/emoji/hashtags), copy (html + plain), конфликтный баннер, AI-маркировка, автосохранение | Vitest + Testing Library + MSW | Секунды |
| **E2E** | Сценарии по AC: новая статья из фикстурного источника появляется (AC-01); 3 статьи → 1 Event (AC-02); фильтр + поиск (AC-04, AC-05); открыть источники (AC-06); preview, edit, copy (AC-07…09); workflow + reject с причиной (AC-10); конфликт виден (AC-11); unverified-предложение подсвечено (AC-12). На каждом экране axe без нарушений | Playwright, стек в Docker с fake AI и fake-источником (статический HTTP-сервер с фикстурами) | ~5–10 мин, после merge |
| **AI evals** | См. §31.4 | pytest-based harness, реальный API | При изменении промптов, ночью |
| **Smoke** | После деплоя | curl/Playwright | Минута |

### 31.3. Тестовые двойники (только для внешних систем)

- `FakeLlmClient` — ответы по фикстурам, сопоставление по `(task, input_hash)`. В режиме «record» пишет реальные ответы в фикстуры.
- `FakeEmbeddingClient` — детерминированные векторы (хэш-проекция), чтобы похожие тексты были «похожи».
- `FakeHttpFetcher` / статический сервер-источник — фикстуры RSS и HTML.
- `FrozenClock`.
- **БД не мокается** (§5.1).

### 31.4. AI evals (качество как тест)

| Набор | Размер (старт) | Метрика | Порог блокировки |
|---|---|---|---|
| Sport classification | 300 размеченных статей pt-BR | accuracy, macro-F1 | падение > 2 п.п. |
| Entity extraction + linking | 200 статей | precision/recall сущностей | падение > 3 п.п. |
| Relevance | 300 статей, разметка редакторами по рубрике | weighted F1, **recall HIGH** | recall HIGH < 0.85 |
| Clustering | 50 «дней» новостей (~1500 статей) с эталонными событиями | B-cubed F1, доля ложных склеек | ложные склейки растут > 1 п.п. |
| Conflict detection | 60 пар конфликт / не конфликт | precision/recall | recall < 0.8 |
| **Grounding drafts** | 100 событий | Доля предложений без цитаты, доля фактов вне evidence (автоматически валидатором + LLM-судья + выборочно человек), **0 недопустимых «слух → факт»** | любой регресс по «слух → факт» |

- Датасеты пополняются **из реальной работы:** ручные merge, move и override, отклонения `INCORRECT` и сильно переписанные черновики попадают в очередь на разметку.
- **Почему evals обязательны:** изменение промпта ломает поведение так же, как изменение кода, только без падения тестов.
- **Компромисс:** evals стоят денег и времени, поэтому запускаются только при релевантных изменениях и по ночам.

### 31.5. Покрытие и нефункциональные тесты

- Цель покрытия: domain и application ≥ 90 %, общее ≥ 80 %. Метрика ориентировочная, не самоцель.
- **Производительность:** k6-сценарий на staging (список с фильтрами, поиск) на объёме данных за год (синтетически 3 млн статей) → p95 < 300 мс. Запускается перед релизами со схемными изменениями.
- **Безопасность:** API-тесты SSRF (приватные IP, редиректы, DNS rebinding), XSS-полезные нагрузки через санитайзер, RBAC-матрица; ежегодный внешний пентест опционален.

---

## 32. Структура папок (полная)

```text
parser_brasil_news/
├── README.md                       # запуск, конфигурация (таблица §23), ссылки на docs
├── docs/
│   ├── OPERATIONS.md
│   ├── ARCHITECTURE.md             # этот документ
│   └── adr/                        # ADR по мере принятия новых решений (формат §1.3)
├── backend/                        # см. §5.2
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── src/sportintel/
│   │   ├── main.py
│   │   ├── worker.py
│   │   ├── platform/
│   │   └── modules/{identity,sources,ingestion,taxonomy,intelligence,events,editorial,audit,analytics}/
│   │       ├── public.py
│   │       ├── domain/
│   │       ├── application/
│   │       ├── infrastructure/
│   │       ├── api/
│   │       └── jobs.py
│   └── tests/{unit,contract,integration,api,architecture,evals}/
├── frontend/                       # см. §14.2
│   ├── package.json
│   ├── src/{app,pages,features,entities,shared}/
│   └── tests/{e2e,setup}/
├── evals/
│   └── datasets/                   # размеченные наборы (версионируются; большие — в объектном хранилище с манифестом)
├── fixtures/
│   └── sources/<profile>/          # RSS/HTML фикстуры (общие для contract, integration и e2e)
├── deploy/
│   ├── Dockerfile                  # multi-stage: build frontend → build backend → runtime (non-root)
│   ├── compose.local.yml           # postgres+pgvector, app, worker, fake-source server
│   ├── Caddyfile, backup.sh, capacity.sql, README.md   # боевая установка (ADR-005)
│   └── platform/                   # манифесты выбранной платформы (Cloud Run / Fly / ECS) — позже
├── compose.yaml                    # боевая установка на одной машине (ADR-005), .env.deploy.example
├── openapi.json                    # зафиксированный контракт API (проверяется в CI)
└── .github/
    └── workflows/{ci.yml,deploy.yml,evals.yml,nightly.yml}
```

**Почему монорепозиторий:** фронт, бэк и контракт меняются вместе, один PR соответствует одной фиче, а OpenAPI-синхронизация проверяется атомарно.
**Альтернатива:** отдельные репозитории. **Компромисс:** CI должен запускать только затронутые части (path filters).

---

## 33. Эволюция архитектуры, риски и открытые вопросы

### 33.1. Путь развития (post-MVP и Future из SRS)

| Возможность | Куда ложится в архитектуре | Что добавляется |
|---|---|---|
| Breaking news detection | events: скорость прироста независимых источников за окно | Политика + флаг + уведомление (§16) |
| Trending topics / most discussed | analytics: агрегаты по `event_entities` за окна | Materialized views |
| Source reliability history | sources + events: доля подтверждённых и опровергнутых claims по источнику | Пересчёт `tier` как рекомендации для Admin |
| Event timeline | events: claims с временем, отсортированные по статьям | Read model, без новой инфраструктуры |
| Automatic story angles, image suggestions | editorial: новые AI-задачи через тот же gateway и grounding | Промпты + evals |
| Telegram publishing после approval | editorial: порт `TelegramPublisher`, статус READY → PUBLISHED автоматически | Флаг `telegram_publish`, аудит, повторная проверка роли |
| Advanced taxonomy | taxonomy: иерархия competitions, внешние ID (fixtures-провайдер) | Таблицы + интеграция `FixturesProvider` |
| Sports Intelligence Platform | Новые bounded contexts (Trends, Opportunities) поверх тех же Events | Новые модули, тот же монолит |

### 33.2. Когда менять ключевые решения (триггеры)

| Решение | Пересмотреть, если |
|---|---|
| Монолит → выделить сервис | Ingestion/AI-нагрузка требует масштабирования, несовместимого с web (например, GPU для локальных моделей), или появилась вторая команда со своим циклом релизов. Первый кандидат — **ingestion + intelligence** как отдельный worker-сервис (у него уже есть чёткий выходной контракт `ArticleEnriched`) |
| PostgreSQL FTS → OpenSearch | Статей > 20–30 млн или нужны синонимы, подсветка и фасеты с p95 < 300 мс, которые недостижимы в PostgreSQL |
| pgvector → специализированная векторная БД | Векторов > 10–20 млн и деградация recall/латентности HNSW |
| Procrastinate → брокер | > 500 задач/с устойчиво или нужен fan-out на многих потребителей |
| Polling → SSE | Пользователей > 50 или требование секундной задержки |
| In-process кэш → Redis | web > 2 инстансов или нужен точный распределённый rate limit |
| Собственные флаги → Unleash | Нужны процентные раскатки и эксперименты |

### 33.3. Главные риски

| Риск | Вероятность / влияние | Митигирующее архитектурное решение |
|---|---|---|
| Ошибки кластеризации (склейка разных фактов или дробление) | Высокая / высокое | Гибридный скоринг, LLM в серой зоне, ручные merge/move, evals, метрика ручных исправлений |
| AI выдаёт слух за факт | Средняя / критическое | Детерминированная reliability, grounding validator, дисклеймеры кодом, human-in-the-loop (READY только у Editor) |
| Тихая поломка парсеров источников | Высокая / среднее | Contract-фикстуры, алерт «источник молчит», предпочтение RSS |
| ToS и copyright | Средняя / высокое | `content_policy`, TTL текста, robots.txt, только ссылки и перефраз; **юридическая проверка списка источников до запуска** |
| Рост расходов на AI | Средняя / среднее | Один вызов на статью, дешёвая модель для массы, кэш, prompt caching, бюджет и circuit breaker |
| Блокировка нашего IP источниками | Средняя / среднее | Вежливый fetch (rate per host, честный User-Agent, conditional GET); при необходимости — согласованный доступ или фиды |

### 33.4. Открытые вопросы (влияют на архитектуру, но не блокируют её)

1. **Есть ли корпоративный IdP** (Google Workspace / Entra)? Если нет, используется fallback magic link (§11).
2. **Список источников и их ToS:** какие разрешают скрапинг HTML, а какие только RSS? Это определяет `content_policy` по умолчанию.
3. **Язык Telegram-канала** (pt-BR?) и язык интерфейса команды (ru/en/pt-BR)?
4. **Нужна ли изоляция ролей «четыре глаза»** (Researcher не может выставить READY своему же черновику, даже став Editor-ом)?
5. **Целевая задержка «минимальная»** — подтверждение SLO p95 ≤ 10 мин или жёстче (тогда нужны чаще опрос и SSE)?
6. **Облачный провайдер и бюджет** — определяют выбор между managed-платформой и VM-вариантом (§29), архитектура от этого не меняется.
7. **Хранение изображений:** только `image_url` источника (текущее решение, без копирования из-за copyright) или нужны собственные копии для Telegram-поста?
