# Deploying SportIntel

The same procedure works on any machine with Docker: a Linux server, a Mac, Windows (WSL2).
Everything starts with one command from the repository root: `docker compose up -d --build`.

| Environment | Purpose | How to run |
|---|---|---|
| **production** | the working installation | `compose.yaml` + `.env` with `ENV=production` (this document) |
| **staging** | checks before a rollout, has `/api/v1/docs` | the same with `ENV=staging`, on a separate server or domain |
| **local (all in Docker)** | demo the product on your own computer | the same with `DOMAIN=localhost` |
| **development** | writing code | `make setup`, `make api`, `make worker`, `make ui`; see the root [README](../README.md) |

## What runs

```
Internet ──443/80──▶ caddy (HTTPS, Let's Encrypt) ──▶ web (API + UI)
                                                        │
                       worker (collection, events, AI, publishing) ──▶ db (PostgreSQL 16 + pgvector)
                       backup (pg_dump once a day → ./backups) ──┘
                       ollama (optional, profile llm)
```

- `migrate` runs once: it applies migrations (and seeds sources and reference data) before web and worker start.
- The database is not exposed. Only Caddy faces the outside (ports 80 and 443).
- Data lives in the Docker volumes `pgdata`, `caddy_data` (certificates) and `ollama_models`, plus the `./backups` folder.

## 1. Requirements

- **Docker:** Docker Engine with the compose v2 plugin (Linux) or Docker Desktop (macOS, Windows). On Windows keep the repository **inside WSL2** (`~/…`), not on `C:\`: it is faster and file permissions and line endings stay intact.
- **Resources:** 2 vCPU, 4 GB RAM and 20 GB disk without local AI. With Ollama (`COMPOSE_PROFILES=llm`) you need **16 GB RAM or more** and 40 GB disk (two models take ~18 GB).
- **Network:** a domain with an A record (and AAAA if you have IPv6) pointing to the server IP. Ports **80 and 443** must be open: Let's Encrypt needs port 80 to issue the certificate.

Installing Docker on a clean Ubuntu/Debian: `curl -fsSL https://get.docker.com | sh`. Then run `sudo usermod -aG docker $USER`, log out and log back in.

## 2. Installation

```bash
git clone https://github.com/notLeri/sportintel.git && cd sportintel
cp .env.deploy.example .env
# fill in .env: DOMAIN, POSTGRES_PASSWORD, BOOTSTRAP_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD, the AI block
docker compose up -d --build
```

- The first build takes 5–10 minutes because the frontend and backend are built. Later builds are faster thanks to layer caching.
- If a required variable is missing, compose stops immediately and names it (`set DOMAIN in .env`).
- Database password: `openssl rand -hex 24`. Letters and digits only, because the password is part of the connection URL.

## 3. Check

```bash
docker compose ps        # db, web, worker, caddy, backup — running (healthy); migrate — exited (0)
```

1. Open `https://<DOMAIN>` and sign in as `BOOTSTRAP_ADMIN_EMAIL` with the password `INITIAL_ADMIN_PASSWORD`.
2. **Admin → Sources → "Check"** on a couple of sources. Events appear on the home page within a few minutes.
3. **Admin → Users:** invite editors and set their passwords.
4. Telegram publishing: [docs/TELEGRAM_BOT_SETUP.md](../docs/TELEGRAM_BOT_SETUP.md). Then set `TELEGRAM_BOT_TOKEN=…` and `FLAG_TELEGRAM_PUBLISH=true` in `.env` and run `docker compose up -d`.

The admin is created from `.env` only once, while the system has no active administrator. After that you can remove `INITIAL_ADMIN_PASSWORD` from `.env`.

## 4. Everyday commands

Run all commands from the repository root.

| Task | Command |
|---|---|
| Service status | `docker compose ps` |
| Logs (recent, live) | `docker compose logs -f --tail=100 web worker` |
| **Update to a new version** | `docker compose run --rm backup once` → `git pull` → `docker compose up -d --build` |
| Apply `.env` changes | `docker compose up -d` |
| Restart everything | `docker compose restart` |
| Stop (data is kept) | `docker compose down` |
| Back up right now | `docker compose run --rm backup once` |
| Reset a password / create a user | `docker compose run --rm web admin set-password you@corp.com [--role admin]` |
| Database console | `docker compose exec db psql -U sportintel` |
| Job queue and failures | **Admin → Pipeline** (or the SQL in the root README, section "Job queue") |

Migrations apply themselves on update: `migrate` runs before web and worker start. If a migration fails, web and worker stay on the old version and do not start with the new one. Check `docker compose logs migrate`.

## 5. Backups and restore

- The `backup` service runs `pg_dump` at startup and then every `BACKUP_INTERVAL_H` hours (24 by default). Dumps go to `./backups/sportintel-<UTC time>.dump`; the last `BACKUP_KEEP` (14) are kept.
- If there is no fresh dump for longer than the interval plus 2 hours, `backup` turns **unhealthy** in `docker compose ps`.
- **Copy `./backups` off the server** (rsync, rclone, object storage). A dump on the same disk will not save you if the server is lost.

Restore (for example on a new server after installing it with step 2):

```bash
docker compose stop web worker
docker compose run --rm backup restore /backups/sportintel-20261012T030000Z.dump
docker compose up -d
```

Test a restore at least once a quarter: bring up a copy on a separate machine and sign in to it.

## 6. Artificial intelligence

Pick an option in `.env` and apply it with `docker compose up -d`.

| Option | `.env` | Notes |
|---|---|---|
| No AI | `AI_PROVIDER=none` | rules and templates; no briefs or translations |
| Anthropic | `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…` | paid, fast |
| Ollama on this server | `AI_PROVIDER=ollama`, `COMPOSE_PROFILES=llm` | models download themselves (`ollama-pull`): `LLM_MODEL` (briefs, `qwen3:14b`) and `TRANSLATION_MODEL` (translations, `gemma3:12b`), ~18 GB; ≥16 GB RAM; without a GPU a brief takes minutes |
| Ollama on another machine | `AI_PROVIDER=ollama`, `OLLAMA_URL=http://<ip>:11434` | never expose the Ollama port to the internet, only to a private network (Tailscale) |

The models the app uses are set in **Admin → Settings** (`llm_model`, `translation_model`). They must match `LLM_MODEL` and `TRANSLATION_MODEL`.

## 7. Sign-in

- **E-mail and password** always work. Passwords are set by an administrator in "Users" or with the `set-password` command. After 5 failed attempts within 15 minutes, sign-in for that e-mail and IP pair is blocked for the rest of the window.
- **Google (OIDC)** turns on when all three of `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` are set (root README, section "Sign-in"). If none is set, there is no Google button. If only some are set, web refuses to start and names the missing ones.

## 8. Resilience: what is already in place

| Failure | What happens |
|---|---|
| A process crashes or the server reboots | `restart: unless-stopped`: everything comes back by itself, in the right order (db → migrate → web/worker → caddy) |
| The database is briefly unavailable | web does not crash and answers 503 on `/readyz`, then carries on once the database is back. Docker restarts the worker. Stuck jobs are re-enqueued by the `platform.reconcile` check (every 5 min) |
| web restarts or updates | Caddy holds requests for up to 30 s until web is back, instead of returning 502 at once |
| The worker stops | SIGTERM: the worker stops taking jobs and finishes the current ones (up to 90 s) |
| Logs fill the disk | rotation: 5 × 10 MB per container |
| Data loss | daily dump, 14 copies, a "fresh dump exists" healthcheck |
| Caddy restarts | certificates live in the `caddy_data` volume, so Let's Encrypt limits are not used up |
| Silent failures (a source goes quiet, a queue grows) | Telegram alert when `ALERT_TELEGRAM_*` is set |

**What is missing: the limits of a single machine.**
- The server is a single point of failure: if it dies, the service is down until it is restored from a backup on a new server. Recovery takes minutes plus copying the dump.
- At most `BACKUP_INTERVAL_H` hours of data can be lost.

How to remove these limits: [docs/OPERATIONS.md](../docs/OPERATIONS.md), section "Scaling".

External monitoring is recommended: any free uptime service that checks `https://<DOMAIN>/readyz` once a minute.

## 9. Common problems

| Symptom | Cause and fix |
|---|---|
| `set DOMAIN in .env` (or another variable) | `.env` is not filled in, see step 2 |
| The site does not open, ACME errors in `docker compose logs caddy` | DNS does not point to the server yet, or ports 80/443 are closed. Check `dig <DOMAIN>` and the firewall |
| `bind: address already in use` on 80/443 | another web server (nginx, apache) holds the port. Stop it |
| web is `unhealthy`, database connection errors in the logs | see `docker compose logs db migrate`. If `POSTGRES_PASSWORD` was changed after the first start, the database still expects the old one: put it back |
| `migrate` exited (1) | `docker compose logs migrate`. The update stopped, data is untouched |
| Ollama crashes or is very slow | not enough RAM. Use a smaller model (`LLM_MODEL=gemma3:4b` and the same in settings) or Anthropic |
| Windows: `/bin/sh^M: bad interpreter` | the repository was cloned with CRLF outside WSL. Clone it inside WSL2 |
