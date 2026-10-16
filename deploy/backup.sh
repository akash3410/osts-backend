#!/usr/bin/env bash
# pg_dump daily backup for the OSTS Postgres instance.
# Run via cron: 0 3 * * * /app/deploy/backup.sh
set -euo pipefail

: "${POSTGRES_DB:=osts}"
: "${POSTGRES_USER:=osts}"
: "${POSTGRES_PASSWORD:=changeme}"
: "${BACKUP_DIR:=/backups}"

TS="$(date -u +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/osts-$TS.dump.gz"

mkdir -p "$BACKUP_DIR"

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump -Fc -U "$POSTGRES_USER" -h "${POSTGRES_HOST:-db}" -d "$POSTGRES_DB" | gzip -9c > "$OUT"

# keep 14 daily dumps locally
find "$BACKUP_DIR" -name 'osts-*.dump.gz' -mtime +14 -delete

echo "Backup written: $OUT ($(du -h "$OUT" | cut -f1))"