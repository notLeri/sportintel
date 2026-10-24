#!/bin/sh
# Роль процесса: web | worker | migrate | admin <команда> (sportintel-admin --help).
set -eu
case "${1:-web}" in
  web) exec sportintel-web ;;
  worker) exec sportintel-worker ;;
  migrate) exec sportintel-migrate ;;  # alembic upgrade head ролью DATABASE_URL_MIGRATOR
  admin) shift; exec sportintel-admin "$@" ;;
  *) echo "unknown role: $1 (expected web|worker|migrate|admin)" >&2; exit 64 ;;
esac
