#!/bin/sh
# PostgreSQL backup: loop dumps now and then every BACKUP_INTERVAL_H hours;
# once dumps now; restore <file> restores the database from a dump (stop web and worker first).
# The last BACKUP_KEEP dumps are kept in /backups (./backups on the host).
set -eu
KEEP="${BACKUP_KEEP:-14}"
INTERVAL_H="${BACKUP_INTERVAL_H:-24}"

dump() {
	f="/backups/sportintel-$(date -u +%Y%m%dT%H%M%SZ).dump"
	pg_dump -Fc -f "$f.part"
	mv "$f.part" "$f"  # an unfinished dump never looks complete
	ls -1t /backups/sportintel-*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm --
	echo "backup: $f ($(du -h "$f" | cut -f1))"
}

case "${1:-loop}" in
once) dump ;;
loop)
	until pg_isready -q; do sleep 2; done
	while :; do
		dump || echo "backup: FAILED" >&2  # the healthcheck will report the missing fresh dump
		sleep "$((INTERVAL_H * 3600))"
	done
	;;
restore)
	file="${2:?usage: backup.sh restore /backups/<file>.dump}"
	pg_restore --clean --if-exists --no-owner --exit-on-error -d "$PGDATABASE" "$file"
	echo "restored: $file"
	;;
*)
	echo "usage: backup.sh loop|once|restore <file>" >&2
	exit 64
	;;
esac
