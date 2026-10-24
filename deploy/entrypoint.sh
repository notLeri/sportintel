#!/bin/sh
# Process role: web | worker | migrate | admin <command> (sportintel-admin --help).
set -eu
case "${1:-web}" in
  web) exec sportintel-web ;;
  worker) exec sportintel-worker ;;
  migrate) exec sportintel-migrate ;;  # alembic upgrade head as the DATABASE_URL_MIGRATOR role
  admin) shift; exec sportintel-admin "$@" ;;
  *) echo "unknown role: $1 (expected web|worker|migrate|admin)" >&2; exit 64 ;;
esac
