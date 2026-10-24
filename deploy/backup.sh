#!/bin/sh
# Бэкап PostgreSQL: loop — дамп сразу и затем каждые BACKUP_INTERVAL_H часов;
# once — один дамп сейчас; restore <файл> — восстановить базу из дампа (web и worker остановить).
# Хранится BACKUP_KEEP последних дампов в /backups (на хосте — ./backups).
set -eu
KEEP="${BACKUP_KEEP:-14}"
INTERVAL_H="${BACKUP_INTERVAL_H:-24}"

dump() {
	f="/backups/sportintel-$(date -u +%Y%m%dT%H%M%SZ).dump"
	pg_dump -Fc -f "$f.part"
	mv "$f.part" "$f"  # недописанный дамп не выглядит готовым
	ls -1t /backups/sportintel-*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm --
	echo "backup: $f ($(du -h "$f" | cut -f1))"
}

case "${1:-loop}" in
once) dump ;;
loop)
	until pg_isready -q; do sleep 2; done
	while :; do
		dump || echo "backup: FAILED" >&2  # healthcheck покажет, что свежего дампа нет
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
