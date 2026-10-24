# Operations and scaling

For whoever looks after a running installation. Installation, everyday commands, backups and common problems are in [deploy/README.md](../deploy/README.md). This document covers what to watch, how to react, and when and how to grow. The decision behind the current setup: [ADR-005](adr/005-single-host-compose-password-login.md).

## 1. Current setup and its limits

One machine, `compose.yaml`: caddy → web → db, worker, backup, optionally ollama.

| Parameter | Current value | Source |
|---|---|---|
| RPO (how much data can be lost) | ≤ `BACKUP_INTERVAL_H` (24 h) | `backup` service |
| RTO (how long a lost server takes to fix) | ~30–60 min: new server + install + restore the dump | deploy/README.md §5 |
| Downtime during an update | seconds: Caddy holds requests for up to 30 s while web restarts | `lb_try_duration` |
| Processes | web ×1, worker ×1 (inside: main, `fetch`, `ai_interactive`) | `make worker` |
| Users | sized for ~20 concurrent | ARCHITECTURE §0 |

Differences from the target architecture (ARCHITECTURE §29): no managed PostgreSQL with PITR (a daily dump instead), no second web replica, no managed observability (Docker logs, the `capacity.sql` report and Telegram alerts instead).

## 2. What to watch

### Daily (1 minute)

```bash
docker compose ps            # everything healthy; backup unhealthy = no fresh dump
```

- **Admin → Pipeline:** queues, failed jobs, source health.
- The alert Telegram chat (`ALERT_TELEGRAM_*`): quiet sources and growing queues.

### Weekly: the load report

```bash
docker compose exec db psql -U sportintel -f /capacity.sql
```

The report is read-only. It has 9 sections:

1. Database size, top tables.
2. Articles and events per day.
3. "Published → ingested" latency (p50/p95).
4. Queue: waiting and failed jobs, age of the oldest.
5. Source polls and errors over 24 h.
6. AI: calls, errors, p50/p95 duration.
7. Users and sessions.
8. Telegram publications.
9. Database connections.

**Save the output once a week** (`… > reports/capacity-$(date +%F).txt`). The trend over 4–8 weeks is what scaling decisions are based on (§4).

Machine resources:

```bash
docker stats --no-stream     # CPU and memory per container
df -h                        # disk: database, ./backups, images
docker system df             # how much images and volumes take
```

### Logs

`docker compose logs -f --tail=200 web worker` prints JSON lines (structlog, fields in ARCHITECTURE §26). Useful filters:
- `| grep '"severity": "ERROR"'`: errors;
- `| grep identity.password_login_denied`: failed sign-ins;
- `| grep platform.stalled_jobs_retried`: a worker died in the middle of a job.

Docker logs rotate at 5 × 10 MB per container. For longer retention, connect Sentry (`SENTRY_DSN`) or a log collector.

## 3. Responding

| Signal | First action |
|---|---|
| `/readyz` is not 200 / the site does not open | `docker compose ps` → find what is not healthy → `docker compose logs <service>` |
| `migrate` exited (1) after an update | `docker compose logs migrate`. Rollback: `git checkout <previous tag>` → `docker compose up -d --build` (migrations are compatible with N−1, ARCHITECTURE §29.2) |
| backup unhealthy | `docker compose logs backup`. Usually the disk is full (`df -h`) |
| "oldest_waiting" grows in the `fetch` queue | sources are slow or there are more of them → `WORKER_FETCH_CONCURRENCY` (§4) |
| The `ai`/`translate` queue grows | AI cannot keep up: the local model is slow → §4, the "AI" row |
| Failed jobs pile up | **Admin → Pipeline** → cause → "Retry". Failed jobs are deleted automatically after 30 days (`platform.purge_old_jobs`) |
| Disk > 80 % | largest tables are in section 1 of the report. Move old `./backups` off the server, `docker image prune` |
| Suspected password brute force | `identity.password_login_denied` in the logs. The 5 per 15 min limit per e-mail + IP pair is already active; for an attack from many IPs use Fail2ban or a host firewall |
| The only admin forgot the password | `docker compose run --rm web admin set-password admin@… --role admin` |

## 4. When to scale: signals

Decide on trends from the `capacity.sql` report and `docker stats`, not "just in case". The thresholds below are starting points; tune them to your own data.

| Signal | Threshold | Bottleneck | Step (§5) |
|---|---|---|---|
| Machine CPU, daily average | > 70 % | everything | 1, vertical |
| RAM | > 80 % or OOM in `dmesg` | usually Ollama | 1 or 3 |
| p95 "published → ingested" latency (sec. 3) | > 15 min consistently | `fetch` worker | 2 |
| oldest_waiting in `fetch` / `ai` / `cluster` (sec. 4) | > 15 min | worker | 2 |
| AI p95 duration (sec. 6) | brief > 60 s and editors are waiting | LLM | 3 |
| Database size (sec. 1) | > 50 % of disk or growth > 1 GB/month | disk | 1, then 4 |
| Database connections (sec. 9) | > 70 % of `max_connections` | database | 4 |
| Concurrent users (sec. 7) | > 20 active per day or complaints about a slow UI | web | 5 |
| Downtime requirement | the business cannot accept an RTO of ~1 h or losing a day of data | single machine | 4 + 6 |

## 5. How to scale: the ladder

Steps are ordered by cost. No step changes the code (except where noted), because one image serves every role (ARCHITECTURE §29.1).

1. **Vertical.** More vCPU, RAM and disk on the same machine. Takes minutes; data in volumes is kept.
2. **Worker parallelism.** Set `WORKER_FETCH_CONCURRENCY`, `WORKER_CONCURRENCY`, `WORKER_INTERACTIVE_CONCURRENCY` in `.env`, then `docker compose up -d`. Watch database connections (sec. 9): each thread holds a connection.
3. **Move AI off the machine.**
   - Ollama on a separate computer or GPU server in a private network (`OLLAMA_URL`, deploy/README §6), or `AI_PROVIDER=anthropic`.
   - Raise `OLLAMA_CONCURRENCY` only if the LLM host has enough memory/GPU.
   - The most common first step when local AI is on.
4. **Separate database.** Managed PostgreSQL 16 with pgvector and `unaccent` (check with your provider) gives PITR (RPO in minutes) and snapshots.
   - Remove the `db` service and point `DATABASE_URL`/`DATABASE_URL_MIGRATOR` at the managed database. This needs a compose override (`compose.override.yaml`) or a two-line edit.
   - Migration: `backup once` → `pg_restore` into the new database.
   - The backup service is no longer needed afterwards.
5. **Several web replicas.** `docker compose up -d --scale web=2`. In `deploy/Caddyfile` replace the static upstream with a dynamic one so Caddy sees every replica:

   ```
   reverse_proxy {
   	dynamic a web 8000
   	lb_policy round_robin
   	lb_try_duration 30s
   }
   ```
   - **Needs a code change:** move the failed sign-in counter from process memory to the database (`identity/api/router.py`, `_Attempts`, marked `ponytail:`).
   - Sessions are already in the database and the first admin is created under an advisory lock, so everything else is ready.
6. **A second machine / a managed platform.** ARCHITECTURE §29 as the target setup:
   - a container platform (rolling deploy, web ×2+);
   - a managed database;
   - a secret manager;
   - observability (OTel → Grafana Cloud, ARCHITECTURE §27).

   Same image and env. Moving means putting `.env` into the platform's secrets and restoring the dump.

A dedicated worker per queue (for example `fetch` on a separate machine closer to the sources) is possible from steps 4–6 on: run `worker` with the same env on the second machine. Procrastinate distributes jobs through the same database.

## 6. Routine maintenance

| When | What |
|---|---|
| Weekly | `capacity.sql` report → save it; a look at "Pipeline" |
| Weekly | copy `./backups` off the server (unless automated) |
| Monthly | OS and Docker updates on the host; `git pull` + `up -d --build` (with a backup first) |
| Quarterly | **restore test** from a dump on a separate machine (deploy/README §5) |
| Quarterly | rotate admin passwords; review users in "Admin → Users" |
| When the team changes | deactivate people who left (the "Active" checkbox closes their sessions immediately) |

## 7. What is stored and for how long

| Data | Retention | Mechanism |
|---|---|---|
| Article text | limited (source ToS) | `ingestion.purge_content` |
| Source poll log | limited | `ingestion.purge_fetch_runs` |
| Sessions | 12 h idle / 7 days maximum | `identity.purge_sessions` |
| Queue jobs | succeeded 7 days, failed 30 days | `platform.purge_old_jobs` |
| Audit, events, publications | forever | — |
| Dumps | last `BACKUP_KEEP` (14) | `backup` service |
| Container logs | 50 MB per container | Docker rotation |

Exact retention periods and schedules are in the periodic jobs in `backend/src/sportintel/modules/*/jobs.py`.
