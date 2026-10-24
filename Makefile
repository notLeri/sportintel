# SportIntel development commands. `make` with no arguments prints this list.
# "## text" after a target is its description in `make help`; "##@ Section" is a group heading.

.DEFAULT_GOAL := help
BE := cd backend &&
ENV_RUN := uv run --env-file ../.env
COMPOSE_LOCAL := docker compose -f deploy/compose.local.yml
LLM_MODEL ?= qwen3:14b
TRANSLATION_MODEL ?= gemma3:12b
OLLAMA_LOG := $(or $(TMPDIR),/tmp/)ollama.log

# $(call stop_port,port,name): gently (SIGTERM) stop the process listening on a port.
# ponytail: after make docker-all the Docker proxy holds the port; stop it with docker compose there.
define stop_port
	@pids=$$(lsof -ti tcp:$(1) -sTCP:LISTEN); \
	if [ -n "$$pids" ]; then kill $$pids && echo "$(2): stopped (:$(1))"; else echo "$(2): not running"; fi
endef

.PHONY: help
help: ## Show the list of commands
	@awk 'BEGIN {FS = ":.*## "} \
		/^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
		/^[a-z0-9-]+:.*## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Usual start: make db-start → make db-migrate → in three terminals: make api, make worker, make ui"
	@echo "Stop: Ctrl+C in the command's terminal, or make stop (api, worker, ui), or make stop-all (+ Ollama and the database)"

##@ First run
.PHONY: setup
setup: ## Install backend and frontend dependencies, git hooks, create .env from .env.example
	$(BE) uv sync
	@if [ -f frontend/package.json ]; then pnpm -C frontend install; fi
	$(BE) uv run pre-commit install --install-hooks
	@[ -f .env ] || cp .env.example .env

##@ Database (PostgreSQL in Docker)
.PHONY: db-start db-stop db-migrate
db-start: ## Start the database (container sportintel-db-1)
	$(COMPOSE_LOCAL) up -d db

db-stop: ## Stop the database (data is kept)
	$(COMPOSE_LOCAL) stop db

db-migrate: ## Apply schema migrations: after db-start and after pulling new code
	$(BE) $(ENV_RUN) sportintel-migrate

##@ Application: each command in its own terminal
.PHONY: api worker ui status stop api-stop worker-stop ui-stop stop-all
api: ## API (FastAPI) on http://localhost:8000
	$(BE) $(ENV_RUN) sportintel-web

worker: ## Background jobs: news collection, events, AI briefs, publishing (/healthz on :8001)
	$(BE) PORT=8001 $(ENV_RUN) sportintel-worker  # api holds PORT

ui: ## UI on http://localhost:5173 (/api requests go to :8000)
	pnpm -C frontend dev

status: ## What is running: database, api/worker/ui ports, Ollama and its models
	@printf "DB:      "; docker ps --filter name=sportintel-db --format '{{.Status}}' | grep . || echo "not running (make db-start)"
	@for p in 8000:api 8001:worker 5173:ui; do \
		printf "%-8s " "$${p#*:}:"; lsof -ti tcp:$${p%%:*} -sTCP:LISTEN >/dev/null && echo "running on :$${p%%:*}" || echo "not running"; done
	@printf "Ollama:  "; curl -sf localhost:11434/api/version >/dev/null && echo "running" || echo "not running (make llm-start)"
	@-ollama ps 2>/dev/null | tail -n +2 | sed 's/^/  in memory: /'

stop: api-stop worker-stop ui-stop ## Stop api, worker and ui (database and Ollama keep running)

api-stop: ## Stop api (:8000)
	$(call stop_port,8000,api)

worker-stop: ## Stop worker (:8001)
	$(call stop_port,8001,worker)

ui-stop: ## Stop ui (:5173)
	$(call stop_port,5173,ui)

stop-all: stop llm-stop db-stop ## Stop everything: api, worker, ui, Ollama and the database

##@ Local LLM (Ollama on a Mac)
.PHONY: llm-start llm-stop llm-pull llm-models llm-docker
llm-start: ## Start Ollama in the background (log: $TMPDIR/ollama.log); the model loads on the first request
	@if curl -sf localhost:11434/api/version >/dev/null; then echo "Ollama: already running"; \
	else nohup ollama serve >"$(OLLAMA_LOG)" 2>&1 & sleep 2; curl -sf localhost:11434/api/version >/dev/null \
		&& echo "Ollama: started, log $(OLLAMA_LOG)" || echo "Ollama: failed to start, see $(OLLAMA_LOG)"; fi

llm-stop: ## Stop Ollama (frees model memory)
	@if brew services list 2>/dev/null | grep -q '^ollama .*started'; then brew services stop ollama; \
	elif docker ps -q --filter name=ollama | grep -q .; then $(COMPOSE_LOCAL) --profile llm stop ollama; \
	else pids=$$(pgrep -f 'ollama serve'); \
		if [ -n "$$pids" ]; then kill $$pids && echo "Ollama: stopped"; else echo "Ollama: not running"; fi; fi

llm-pull: ## Pull both models: briefs and posts (LLM_MODEL, qwen3:14b) and translations (TRANSLATION_MODEL, gemma3:12b), ~18 GB
	ollama pull $(LLM_MODEL) && ollama pull $(TRANSLATION_MODEL)

llm-models: ## Downloaded models and models currently loaded in memory
	@echo "Downloaded:"; ollama list
	@echo; echo "In memory:"; ollama ps

llm-docker: ## Alternative: Ollama in Docker (slower on a Mac, no Metal) + qwen3:14b and bge-m3
	$(COMPOSE_LOCAL) --profile llm up -d ollama
	$(COMPOSE_LOCAL) exec ollama sh -c "ollama pull qwen3:14b && ollama pull bge-m3"

##@ Checks
.PHONY: test test-backend test-frontend test-e2e lint
test: test-backend test-frontend ## All unit and integration tests

test-backend: ## Backend tests (pytest, without evals; needs Docker)
	$(BE) uv run pytest -m "not evals"

test-frontend: ## Frontend tests (vitest)
	pnpm -C frontend test

test-e2e: ## Playwright end-to-end tests against deploy/compose.e2e.yml
	docker compose -f deploy/compose.e2e.yml up -d --build
	pnpm -C frontend e2e

lint: ## Linters and types: ruff, mypy, import-linter, eslint, tsc
	$(BE) uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
	pnpm -C frontend lint
	pnpm -C frontend typecheck

##@ AI and rules quality
.PHONY: eval-rules eval-briefs
eval-rules: ## Evaluate rules and clustering on evals/datasets/
	$(BE) $(ENV_RUN) pytest -m evals tests/evals

MODELS ?= ollama:qwen3:14b ollama:gemma3:12b
eval-briefs: ## Compare LLMs on briefs (MODELS="ollama:qwen3:14b ollama:gemma3:12b")
	$(BE) $(ENV_RUN) python -m tests.evals.briefs ../evals/datasets/briefs_v1.jsonl --models $(MODELS) --lang ru

##@ Misc
.PHONY: api-client docker-all docker-image
api-client: ## After an API change: export openapi.json and regenerate the frontend TS types
	$(BE) uv run python scripts/export_openapi.py
	pnpm -C frontend gen:api

docker-all: ## Everything in containers: migrate → api (with the built UI) + worker on :8000
	$(COMPOSE_LOCAL) --profile full up --build

docker-image: ## Build the image sportintel:<git sha>
	docker build -f deploy/Dockerfile --build-arg VERSION=$$(git rev-parse --short HEAD) -t sportintel:$$(git rev-parse --short HEAD) .

# Old names kept as aliases; hidden from help.
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
