# ADR-005. A single machine with Docker Compose and password sign-in

- **Status:** accepted
- **Date:** 2026-10-12

**Context.** The product must deploy turnkey on a clean machine with Docker: a Linux server, a Mac or Windows (WSL2). The budget is close to zero (ADR-004). ARCHITECTURE §29 assumed a managed platform and managed PostgreSQL, with VM + Compose + Caddy mentioned only as a budget option. Also, outside `local/ci/e2e` the app did not start without Google OIDC. For a new installation that is a manual step in Google Cloud Console, and it requires a corporate IdP that may not exist.

**Decision.**
1. **Deployment:** the root `compose.yaml`, one machine. Services:
   - `db`: PostgreSQL 16 + pgvector, no exposed port;
   - `migrate`: runs once;
   - `web`, `worker`: one image;
   - `caddy`: HTTPS via Let's Encrypt;
   - `backup`: scheduled `pg_dump`;
   - `ollama`: optional, profile `llm`.

   Configuration is a single `.env` based on `.env.deploy.example`. Installing and updating is one command: `docker compose up -d --build`. No installer scripts: compose behaves the same on every OS, and `${VAR:?…}` checks required variables by itself.
2. **Sign-in:**
   - e-mail + password always works. The hash is `hashlib.scrypt` from the standard library. Limit: 5 failures per e-mail + IP pair in 15 minutes.
   - OIDC turns on only when all three `OIDC_*` are set. If none is set, there is no Google button. A partial set is a configuration error.
   - The first admin is created when web starts, from `BOOTSTRAP_ADMIN_EMAIL` + `INITIAL_ADMIN_PASSWORD`, while there is no active admin.
   - Password reset: in the UI or with `sportintel-admin set-password`.
3. **Minimal resilience** without a second machine:
   - `restart: unless-stopped`;
   - healthchecks (`/readyz`, the worker's `/healthz`, `pg_isready`, dump freshness);
   - startup order by dependencies;
   - graceful worker stop (90 s);
   - Caddy waits up to 30 s for web during a restart;
   - Docker log rotation;
   - a daily dump with 14 copies kept;
   - cleanup of old queue jobs (`platform.purge_old_jobs`).

**Why.**
- One machine and Compose is the cheapest and most portable option, understandable without DevOps.
- The image already serves every role (§29.1), so the code does not change.
- Passwords remove the IdP dependency for small teams (up to ~20 people). Server-side sessions, CSRF and the `__Host-sid` cookie stay the same (§11).

**Alternatives.**
- A managed platform (Cloud Run etc.): paid and ties you to a cloud. It remains the scaling path (docs/OPERATIONS.md §5).
- Kubernetes: overkill.
- A Bash/PowerShell installer: two implementations of the same logic, while `.env` + compose is enough.
- argon2/bcrypt: a new dependency, while scrypt is in the standard library.
- Magic links: need e-mail (SMTP), i.e. one more service.

**Trade-offs.**
- The server is a single point of failure. RPO equals the backup interval (24 h by default); RTO is the time to install a new machine plus restore the dump.
- Self-managed passwords: no MFA, reset only through an administrator. Revisit when a corporate IdP appears (turn on OIDC) or there are more than ~20 users.
- The failed sign-in counter lives in the memory of a single web process. With several web replicas it must move to the database.
- Revisit the whole decision based on the signals in docs/OPERATIONS.md §4.
