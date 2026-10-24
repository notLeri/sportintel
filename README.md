# SportIntel

An editorial desk for sports, iGaming and public-holiday news. SportIntel collects news from RSS feeds, websites and public Telegram channels, clusters articles into events, writes AI briefs in English or Russian and publishes posts to Telegram channels, either after an editor approves them or automatically.

- **Collect:** RSS, HTML sites and public Telegram channels (`t.me/s/<channel>`, no API keys), plus public-holiday calendars by country (OpenHolidays, GOV.UK, BrasilAPI, Wikipedia).
- **Cluster:** articles about the same story are merged into one event. Each event shows how many independent outlets confirm it, how much the sources are trusted and how important it is. The rules are editable without a redeploy.
- **Brief:** an AI brief answers "what happened, status, gist, who is affected, what to do". Source links are inserted by code, not by the model. Runs on a local Ollama model (free) or the Anthropic API. Without AI everything except briefs works on rules and templates.
- **Publish:** post drafts, an approval feed, channels with schedules and filters, autoposting, a send calendar and a subscriber's view of each channel.
- **Interface** in English or Russian, light and dark themes, hotkeys, a hint on every control. Roles: researcher → editor → admin. Sign-in with e-mail and password; Google (OIDC) is optional.

**Deploy on a server or any machine with Docker:** `cp .env.deploy.example .env` → fill it in → `docker compose up -d --build`. See [deploy/README.md](deploy/README.md). Operations and scaling: [docs/OPERATIONS.md](docs/OPERATIONS.md).

**Minimum hardware:**

| Setup | CPU | RAM | Disk |
|---|---|---|---|
| No AI, or the Anthropic API | 2 vCPU | 4 GB | 20 GB |
| Local Ollama (`qwen3:14b` + `gemma3:12b` for translations) | 4+ vCPU (a GPU or Apple Silicon is better) | 16 GB+ | 40 GB (models take ~18 GB) |

Any OS with Docker; ports 80 and 443 must be reachable. Ollama can run on another machine, in which case the server only needs the first row.

Documentation: [architecture](docs/ARCHITECTURE.md), [operations](docs/OPERATIONS.md), decisions in [`docs/adr/`](docs/adr/).

## How it works

The default mode uses no AI and no paid services (ADR-004): rules, templates and lexical clustering.

```
sources (RSS/HTML/Telegram channels) → articles → rule enrichment → events → [AI brief] → draft → editor → Telegram channel
```

1. **Collection.** The worker polls sources on a schedule (`sources.schedule_due` → `ingestion.fetch_source`), extracts the article text and drops duplicates.
2. **Enrichment** (`intelligence.enrich_article`). Rules from `app_settings` detect the sport, competition, teams and players (from the reference data and aliases), rumour and clickbait markers, and importance.
3. **Clustering** (`events.cluster_article`). An article joins a similar event (title, entities, competition; thresholds in ADR-003) or opens a new one. Candidates come only from the same region (`sources.region`). The event recomputes source reliability (the number of independent outlets and their tier; "untrusted" sources do not count), importance, title and summary from its main article.
4. **AI brief** (`editorial.build_brief`, via a button on the event card). The LLM writes a brief in the interface language: what happened, status (official / confirmed / single outlet / rumour), gist, who is affected, impact, what to do. Code inserts the source links by the numbers the model picked; "confirmed" requires at least 2 different outlets. Only the editor sees the verification status (and the "not confirmed" warning); it never reaches the Telegram post. Automatic generation: `app_settings.briefs.auto_languages` (off by default).
5. **Drafts** (`editorial.autodraft_due` or by hand, including "Post from AI brief"). Each version has its own post language; the editor edits and approves. The `/feed` page lists ready drafts.
6. **Publishing** (`editorial.publish_due`, every minute). Channels have a schedule (cron, UTC) and filters (sport, region, importance, reliability). "Approval" mode posts approved drafts; "auto" mode posts briefs (except rumours), optionally as a digest. Enable with `FLAG_TELEGRAM_PUBLISH=true` + `TELEGRAM_BOT_TOKEN`; see [bot setup](docs/TELEGRAM_BOT_SETUP.md).

Every action is written to the history (audit log). LLM: `AI_PROVIDER=ollama` (local and free; model in `app_settings.llm_model`, `qwen3:14b` by default) or `anthropic` (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`). With `AI_PROVIDER=none` everything except briefs works on rules.

## Getting started

You need [uv](https://docs.astral.sh/uv/), Node.js 22 + pnpm 12, Docker (versions in `.tool-versions`), and [Ollama](https://ollama.com) for briefs.

```bash
make setup && make db-start && make db-migrate   # once (db-migrate again after pulling new code)
make api      # API on :8000
make worker   # background jobs (:8001 serves only /healthz); without it there are no news, briefs or posts
make ui       # UI on http://localhost:5173 (/api is proxied to :8000)
```

Run each command in its own terminal. For briefs with `AI_PROVIDER=ollama`, `ollama serve` must be running with a model (`make llm-start`, `make llm-pull`). To stop: Ctrl+C in the command's terminal, `make stop` (api, worker, ui) or `make stop-all` (also Ollama and the database). `address already in use` means an old process holds the port: run `make stop`.

Local sign-in is the dev-login form on `/login`: any e-mail and role (`admin` for the initial setup). Roles: researcher → editor → admin. The interface language is English (default) or Russian, switchable in the user menu; event titles and briefs follow it. Unclear controls have hints (hover or "?").

1. **Admin → Sources**: add an RSS feed/site or a public Telegram channel (type `html`, profile `telegram`, feed `https://t.me/s/<channel>`, no API or keys), set the region and trust tier (official … "untrusted"), click "Check", enable it.
2. **Admin → Reference data**: teams, players, competitions and their aliases (the rules recognise entities by them; unrecognised names land in "Unlinked").
3. **Admin → Settings**: importance rules, clustering thresholds, autodraft. Changes apply without a redeploy.
4. **Home (events)**: filters (including region and reliability), search, the event card: sources, AI brief, post draft; editing, merging/moving articles, a manual event or an article by URL.
5. **Feed (`/feed`)**: ready drafts → "Take" → edit → "Approve" → published by a channel or by hand ("Copy" → "Published").
6. **Autoposting** (its own tab): a per-channel autoposting switch (new channels start switched off), a weekly calendar of when the next post goes out and what is queued, and on the right the channel as a subscriber sees it (a public `@username` is read from t.me, a private one from the send log) with scheduled posts at the bottom. Channel settings live here too (chat_id, post language (English by default), mode, schedule, filters), plus "Test", "Run now" and the log.
7. **Admin → Pipeline**: queues, failed jobs (retry), source health. **Analytics**: useful stories by person and day.

Alerts about silent failures (a source goes quiet, a queue grows) go to a Telegram chat if `ALERT_TELEGRAM_BOT_TOKEN` and `ALERT_TELEGRAM_CHAT_ID` are set, otherwise to the log.

## Layout

| Directory | Contents |
|---|---|
| `backend/` | Python 3.12, FastAPI, modular monolith (`src/sportintel/`) |
| `frontend/` | React 19 + Vite SPA |
| `deploy/` | Dockerfile, compose files, Caddy, backup script |
| `fixtures/` | RSS/HTML source fixtures (contract, integration, e2e tests) |
| `evals/` | Labelled datasets and reports for evals |
| `docs/` | Architecture, operations, ADRs |
| `.github/` | CI |

## Commands

`make` (same as `make help`) lists every command with a description. `make status` shows what is running. Old names (`make web`, `make fe`, `make up`, `make migrate`…) still work as aliases.

Integration tests start PostgreSQL (`pgvector/pgvector:pg16`) through testcontainers, so Docker must be running. If `TEST_DATABASE_URL` is set, it is used instead (that is how CI works). With **Colima** on macOS:

```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
```

Pre-commit runs ruff, end-of-file-fixer, trailing-whitespace, check-yaml, gitleaks and lint-staged for `frontend/`. To check the whole tree: `cd backend && uv run pre-commit run --all-files`.

## Frontend

```bash
cd frontend
pnpm install      # pnpm 12 (packageManager in package.json), Node 22+
pnpm dev          # http://localhost:5173; /api and /auth are proxied to http://localhost:8000
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

ESLint (`eslint-plugin-boundaries`) enforces the FSD layers (`app → pages → features → entities → shared`): imports only go down, and a slice is imported only through its `index.ts`. shadcn/ui primitives live in `src/shared/ui` (`components.json` points there). Only the public `VITE_SENTRY_DSN` and `VITE_VERSION` are allowed in `import.meta.env`.

## Docker

One image for every role (`deploy/Dockerfile`, multi-stage, non-root uid 10001): `web` (API + built SPA), `worker`, `migrate`, `admin`.

Production setup is the root `compose.yaml` (HTTPS, backups, auto-restart): [deploy/README.md](deploy/README.md). Below is what you need for development.

```bash
make db-start       # PostgreSQL only, for development
make docker-all     # migrate → web (http://localhost:8000, with the SPA) + worker in containers
make docker-image   # image sportintel:<git sha>
docker build -f deploy/Dockerfile --target fe-maps -o maps .   # source maps for Sentry
```

Every source is degraded with `ssrf_blocked`? Most likely a VPN with fake-ip DNS is on (Clash, sing-box, Surge). Add `SAFE_FETCH_ALLOW_FAKE_IP=true` to `.env` and restart `make docker-all`. Alternatively switch the VPN client's DNS to redir-host / real-ip.

### Local LLM (optional, ADR-004)

```bash
make llm-pull      # pull qwen3:14b into Ollama on a Mac (LLM_MODEL=gemma3:12b for another one)
make llm-models    # what is downloaded and what is loaded in memory
make llm-docker    # alternative: Ollama in Docker + qwen3:14b and bge-m3
make eval-briefs   # compare models on evals/datasets/briefs_v1.jsonl (MODELS="ollama:qwen3:14b ollama:gemma3:12b")
```

On a Mac, native Ollama (Metal) is faster than Docker: `brew install ollama`, `ollama serve`. It needs ~16 GB of RAM; a brief takes ~50 s on an M4. Comparison reports are in `evals/reports/`. The LLM does not have to live next to the app: `OLLAMA_URL` can point to a separate local VM/server or a laptop with Ollama reachable by the worker over the network (for example via Tailscale). Do not expose the Ollama port to the internet; only the worker's network should reach it. Step-by-step rollout: `app_settings.ai_routing`.

## CI

`.github/workflows/ci.yml` jobs: `backend` (ruff, mypy, import-linter, migrations from scratch with a single head, pytest with coverage on a service PostgreSQL), `frontend` (lint, typecheck, test, build, check:api), `contract` (`openapi.json` ↔ backend ↔ TS types), `security` (gitleaks, pip-audit, pnpm audit), `image` (buildx `linux/amd64`, smoke test migrate → web → `/healthz`, `/readyz`, SPA). Path filters skip untouched parts; a skipped job reports success.

**Protecting `main`** (GitHub settings): required checks `backend`, `frontend`, `contract`, `security`, `image`; linear history; squash merge.

## Sign-in

**E-mail and password** always work (ADR-005). The first admin is created from `BOOTSTRAP_ADMIN_EMAIL` + `INITIAL_ADMIN_PASSWORD` when web starts. An admin sets passwords for everyone else in "Users". Emergency reset: `docker compose run --rm web admin set-password <email>`.

**Google (OIDC)** is available when all three of `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` are set; otherwise there is no Google button. `local`, `ci` and `e2e` use `FakeOidcProvider` (no network). Access is granted to an existing active user, to an e-mail domain from `OIDC_ALLOWED_DOMAINS` (role researcher) or to `BOOTSTRAP_ADMIN_EMAIL` (admin, while there is no admin yet).

**Setting up the OAuth client in Google Cloud Console:**
1. APIs & Services → OAuth consent screen: type **Internal** (Workspace users only) or External + test users.
2. Credentials → Create credentials → OAuth client ID → **Web application**.
3. Authorized redirect URIs: exactly `APP_BASE_URL + /auth/callback` for each environment, e.g. `https://staging.example.com/auth/callback` and `https://app.example.com/auth/callback`.
4. Put the client ID and secret into your secret store / env (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`), with `OIDC_ISSUER=https://accounts.google.com`.

## Job queue

Background jobs run on Procrastinate in the `procrastinate` schema of the same database; jobs are declared in `modules/*/jobs.py`. `make worker` starts three workers in one process: the main one (housekeeping, `ai`, `cluster`), `fetch` (`WORKER_FETCH_CONCURRENCY`, so politeness delays towards sites do not block the rest) and `ai_interactive` (`WORKER_INTERACTIVE_CONCURRENCY`).

```sql
-- what is queued and what broke
SELECT queue_name, task_name, status, count(*)
FROM procrastinate.procrastinate_jobs GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- latest failed jobs
SELECT id, task_name, args, attempts, scheduled_at
FROM procrastinate.procrastinate_jobs WHERE status = 'failed' ORDER BY id DESC LIMIT 20;
```

Jobs are enqueued after commit (`uow.enqueue_after_commit`). If a process dies between the commit and the enqueue, the periodic `platform.reconcile` check (every 5 minutes) re-enqueues the job and also restarts jobs of stuck workers.

## Configuration

Environment variables are read only in `backend/src/sportintel/platform/config.py` (locally from `.env`, template `.env.example`; `uv run --env-file` loads the file, `Settings` itself does not read `.env`). A configuration error logs `config.invalid` with the list of fields and exits with code 1. Business settings that change at runtime live in the `platform.app_settings` table. Secrets are never committed.

`platform/config.py` is the source of truth; update this table when you change it.

| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `ENV` | `local\|ci\|e2e\|staging\|production` | yes | — | Environment |
| `VERSION` | str | no | `dev` | git sha, baked in at image build |
| `DATABASE_URL` | str (`postgresql+psycopg://…`) | yes | — | `app` role |
| `DATABASE_URL_MIGRATOR` | str | no | = `DATABASE_URL` | `migrator` role, used only by `alembic` |
| `DB_POOL_SIZE` | int | no | 10 | SQLAlchemy pool per process |
| `APP_BASE_URL` | URL | yes | — | Public URL (for the OIDC redirect) |
| `OIDC_ISSUER` | URL | yes outside `local/ci/e2e` | — | |
| `OIDC_CLIENT_ID` | str | yes outside `local/ci/e2e` | — | |
| `OIDC_CLIENT_SECRET` | secret | yes outside `local/ci/e2e` | — | |
| `OIDC_ALLOWED_DOMAINS` | csv | no | empty | E-mail domains admitted without an allowlist |
| `BOOTSTRAP_ADMIN_EMAIL` | email | no | — | Gets the admin role on first sign-in |
| `DEV_LOGIN_ENABLED` | bool | no | false | Allowed **only** with `ENV ∈ {local, e2e}`, otherwise startup fails |
| `AI_PROVIDER` | `none\|ollama\|fake\|anthropic` | no | `none` | ADR-004: where `llm` steps run; `none` means rules and templates |
| `OLLAMA_URL` | URL | if `ollama` | `http://localhost:11434` | Machine with Ollama (same VM, a separate VM, a laptop over a tunnel) |
| `OLLAMA_TIMEOUT_S` | int | no | 180 | LLM call timeout |
| `OLLAMA_CONCURRENCY` | int | no | 1 | Parallel LLM calls per worker |
| `ANTHROPIC_API_KEY` | secret | if `AI_PROVIDER=anthropic` | — | |
| `ANTHROPIC_MODEL` | str | no | `claude-haiku-5-5` | Model for briefs with `AI_PROVIDER=anthropic` |
| `EMBEDDINGS_PROVIDER` | `none\|ollama\|fake\|voyage` | no | `none` | `none` means lexical clustering |
| `VOYAGE_API_KEY` | secret | if `voyage` | — | |
| `AI_RECORD` | bool | no | false | `local` only: record fake-AI fixtures |
| `SENTRY_DSN` | secret | no | — | Empty → Sentry off |
| `ALERT_TELEGRAM_BOT_TOKEN` | secret | no | — | Empty → alerts go only to the log |
| `ALERT_TELEGRAM_CHAT_ID` | str | no | — | |
| `TELEGRAM_BOT_TOKEN` | secret | for publishing | — | Bot that posts to channels; also needs `FLAG_TELEGRAM_PUBLISH=true` |
| `FETCH_USER_AGENT` | str | no | `SportIntelBot/1.0 (+<APP_BASE_URL>/bot)` | |
| `WORKER_CONCURRENCY` | int | no | 4 | Worker parallelism |
| `WORKER_INTERACTIVE_CONCURRENCY` | int | no | 2 | Separate limit for the `ai_interactive` queue |
| `WORKER_FETCH_CONCURRENCY` | int | no | 4 | Separate limit for the `fetch` queue |
| `LOG_LEVEL` | str | no | `INFO` | |
| `LOG_FORMAT` | `json\|console` | no | `console` in local, `json` otherwise | |
| `SAFE_FETCH_ALLOW_HOSTS` | csv | no | empty | **`ENV=e2e` only**: hosts for which the SSRF private-IP check is off. A non-empty value in any other environment is a configuration error |
| `SAFE_FETCH_ALLOW_FAKE_IP` | bool | no | `false` | **`ENV=local` only**: allow fake-ip DNS addresses of VPN clients (`198.18.0.0/15`, `240.0.0.0/4`), otherwise every source fails with `ssrf_blocked`. All other SSRF checks, ports and redirects still apply. `true` in any other environment is a configuration error |
| `STATIC_DIR` | path | no | `/app/static` | Directory of the built SPA |
| `PORT` | int | no | 8000 | HTTP port (web; the worker serves `/healthz` on it, `make worker` sets 8001) |
| `CSP_MODE` | `report-only\|enforce` | no | `report-only` | CSP mode |
| `FLAG_<NAME>` | bool | no | false | Feature flags |

## License

[MIT](LICENSE)
