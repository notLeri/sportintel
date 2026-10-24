# SportIntel — команды разработки. `make` без аргументов показывает этот список.
# Строка «## текст» после цели — её описание в `make help`; «##@ Раздел» — заголовок группы.

.DEFAULT_GOAL := help
BE := cd backend &&
ENV_RUN := uv run --env-file ../.env
COMPOSE_LOCAL := docker compose -f deploy/compose.local.yml
LLM_MODEL ?= qwen3:14b
TRANSLATION_MODEL ?= gemma3:12b
OLLAMA_LOG := $(or $(TMPDIR),/tmp/)ollama.log

# $(call stop_port,порт,имя): мягко (SIGTERM) завершить процесс, слушающий порт.
# ponytail: после make docker-all порт держит прокси Docker — там останавливать через docker compose.
define stop_port
	@pids=$$(lsof -ti tcp:$(1) -sTCP:LISTEN); \
	if [ -n "$$pids" ]; then kill $$pids && echo "$(2): остановлен (:$(1))"; else echo "$(2): не запущен"; fi
endef

.PHONY: help
help: ## Показать список команд
	@awk 'BEGIN {FS = ":.*## "} \
		/^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
		/^[a-z0-9-]+:.*## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Обычный запуск: make db-start → make db-migrate → в трёх терминалах: make api, make worker, make ui"
	@echo "Завершение: Ctrl+C в терминале команды, или make stop (api, worker, ui), или make stop-all (+ Ollama и база)"

##@ Первый запуск
.PHONY: setup
setup: ## Установить зависимости backend и frontend, git-хуки, создать .env из .env.example
	$(BE) uv sync
	@if [ -f frontend/package.json ]; then pnpm -C frontend install; fi
	$(BE) uv run pre-commit install --install-hooks
	@[ -f .env ] || cp .env.example .env

##@ База данных (PostgreSQL в Docker)
.PHONY: db-start db-stop db-migrate
db-start: ## Запустить базу (контейнер sportintel-db-1)
	$(COMPOSE_LOCAL) up -d db

db-stop: ## Остановить базу (данные сохраняются)
	$(COMPOSE_LOCAL) stop db

db-migrate: ## Применить миграции схемы — после db-start и после обновления кода
	$(BE) $(ENV_RUN) sportintel-migrate

##@ Приложение — каждую команду в своём терминале
.PHONY: api worker ui status stop api-stop worker-stop ui-stop stop-all
api: ## API (FastAPI) на http://localhost:8000
	$(BE) $(ENV_RUN) sportintel-web

worker: ## Фоновые задачи: сбор новостей, события, AI-брифы, публикация (/healthz на :8001)
	$(BE) PORT=8001 $(ENV_RUN) sportintel-worker  # PORT занят api

ui: ## Интерфейс на http://localhost:5173 (запросы /api уходят на :8000)
	pnpm -C frontend dev

status: ## Что сейчас запущено: база, порты api/worker/ui, Ollama и её модели
	@printf "База:    "; docker ps --filter name=sportintel-db --format '{{.Status}}' | grep . || echo "не запущена (make db-start)"
	@for p in 8000:api 8001:worker 5173:ui; do \
		printf "%-8s " "$${p#*:}:"; lsof -ti tcp:$${p%%:*} -sTCP:LISTEN >/dev/null && echo "работает на :$${p%%:*}" || echo "не запущен"; done
	@printf "Ollama:  "; curl -sf localhost:11434/api/version >/dev/null && echo "работает" || echo "не запущена (make llm-start)"
	@-ollama ps 2>/dev/null | tail -n +2 | sed 's/^/  в памяти: /'

stop: api-stop worker-stop ui-stop ## Остановить api, worker и ui (база и Ollama остаются)

api-stop: ## Остановить api (:8000)
	$(call stop_port,8000,api)

worker-stop: ## Остановить worker (:8001)
	$(call stop_port,8001,worker)

ui-stop: ## Остановить ui (:5173)
	$(call stop_port,5173,ui)

stop-all: stop llm-stop db-stop ## Остановить всё: api, worker, ui, Ollama и базу

##@ Локальная LLM (Ollama на Mac)
.PHONY: llm-start llm-stop llm-pull llm-models llm-docker
llm-start: ## Запустить Ollama в фоне (лог — $TMPDIR/ollama.log); модель грузится при первом запросе
	@if curl -sf localhost:11434/api/version >/dev/null; then echo "Ollama: уже работает"; \
	else nohup ollama serve >"$(OLLAMA_LOG)" 2>&1 & sleep 2; curl -sf localhost:11434/api/version >/dev/null \
		&& echo "Ollama: запущена, лог $(OLLAMA_LOG)" || echo "Ollama: не стартовала, см. $(OLLAMA_LOG)"; fi

llm-stop: ## Остановить Ollama (освобождает память моделей)
	@if brew services list 2>/dev/null | grep -q '^ollama .*started'; then brew services stop ollama; \
	elif docker ps -q --filter name=ollama | grep -q .; then $(COMPOSE_LOCAL) --profile llm stop ollama; \
	else pids=$$(pgrep -f 'ollama serve'); \
		if [ -n "$$pids" ]; then kill $$pids && echo "Ollama: остановлена"; else echo "Ollama: не запущена"; fi; fi

llm-pull: ## Скачать обе модели: брифы и посты (LLM_MODEL, qwen3:14b) и переводы (TRANSLATION_MODEL, gemma3:12b), ~18 ГБ
	ollama pull $(LLM_MODEL) && ollama pull $(TRANSLATION_MODEL)

llm-models: ## Скачанные модели и модели, загруженные сейчас в память
	@echo "Скачаны:"; ollama list
	@echo; echo "В памяти:"; ollama ps

llm-docker: ## Альтернатива: Ollama в Docker (медленнее на Mac — без Metal) + qwen3:14b и bge-m3
	$(COMPOSE_LOCAL) --profile llm up -d ollama
	$(COMPOSE_LOCAL) exec ollama sh -c "ollama pull qwen3:14b && ollama pull bge-m3"

##@ Проверки
.PHONY: test test-backend test-frontend test-e2e lint
test: test-backend test-frontend ## Все unit- и интеграционные тесты

test-backend: ## Тесты backend (pytest, без evals; нужен Docker)
	$(BE) uv run pytest -m "not evals"

test-frontend: ## Тесты frontend (vitest)
	pnpm -C frontend test

test-e2e: ## Сквозные тесты Playwright на стенде deploy/compose.e2e.yml
	docker compose -f deploy/compose.e2e.yml up -d --build
	pnpm -C frontend e2e

lint: ## Линтеры и типы: ruff, mypy, import-linter, eslint, tsc
	$(BE) uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
	pnpm -C frontend lint
	pnpm -C frontend typecheck

##@ Качество AI и правил
.PHONY: eval-rules eval-briefs
eval-rules: ## Оценка правил и кластеризации на evals/datasets/
	$(BE) $(ENV_RUN) pytest -m evals tests/evals

MODELS ?= ollama:qwen3:14b ollama:gemma3:12b
eval-briefs: ## Сравнить LLM на брифах (MODELS="ollama:qwen3:14b ollama:gemma3:12b")
	$(BE) $(ENV_RUN) python -m tests.evals.briefs ../evals/datasets/briefs_v1.jsonl --models $(MODELS) --lang ru

##@ Разное
.PHONY: api-client docker-all docker-image
api-client: ## После изменения API: выгрузить openapi.json и перегенерировать TS-типы frontend
	$(BE) uv run python scripts/export_openapi.py
	pnpm -C frontend gen:api

docker-all: ## Всё в контейнерах: migrate → api (со сборкой UI) + worker на :8000
	$(COMPOSE_LOCAL) --profile full up --build

docker-image: ## Собрать образ sportintel:<git sha>
	docker build -f deploy/Dockerfile --build-arg VERSION=$$(git rev-parse --short HEAD) -t sportintel:$$(git rev-parse --short HEAD) .

# Старые имена — на них ссылаются спецификации; в help не показываются.
.PHONY: up up-full image migrate web fe test-be test-fe openapi evals e2e
up: db-start
up-full: docker-all
image: docker-image
migrate: db-migrate
web: api
fe: ui
test-be: test-backend
test-fe: test-frontend
openapi: api-client
evals: eval-rules
e2e: test-e2e
