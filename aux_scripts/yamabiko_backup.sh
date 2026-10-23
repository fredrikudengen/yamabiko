#!/usr/bin/env bash
#
# Yamabiko backup: dumps the Postgres database and (optionally) archives the
# data directory (activity files, Strava import, user images).
#
# Segments, efforts, notes and photos exist only in Postgres, and imported
# files only in the data directory, so back up both before importing more
# history or upgrading.
#
# Usage:
#   BACKUP_DIR=/mnt/backup/yamabiko ./yamabiko_backup.sh
#
# Environment (all optional except BACKUP_DIR):
#   BACKUP_DIR      Where to write backups. Required. Put it on another disk,
#                   or on a folder that syncs to Nextcloud.
#   PG_CONTAINER    Name of the Postgres container (default: endurain-postgres).
#   DATA_DIR        Host path of the app's data directory, for example
#                   ~/code_projects/yamabiko-data/backend/data. If unset, only
#                   the database is backed up.
#   KEEP_DAYS       Delete backups older than this many days (default: 30).
#                   Set to 0 to keep everything.
#
# User and database name are read from the container's own POSTGRES_USER and
# POSTGRES_DB, so they never have to be repeated here and no password is used.
#
# Nightly at 03:15 (crontab -e):
#   15 3 * * * BACKUP_DIR=/mnt/backup/yamabiko /path/to/yamabiko_backup.sh >> /path/to/yamabiko_backup.log 2>&1
#
# Restore a dump into a fresh, empty database (never over a running one):
#   docker exec -i endurain-postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists' < yamabiko-db-YYYYmmdd-HHMMSS.dump

set -euo pipefail
umask 077

: "${BACKUP_DIR:?Set BACKUP_DIR to the folder the backups should be written to}"
PG_CONTAINER="${PG_CONTAINER:-endurain-postgres}"
KEEP_DAYS="${KEEP_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

DB_FILE="$BACKUP_DIR/yamabiko-db-$STAMP.dump"
DB_PARTIAL="$DB_FILE.partial"

cleanup() { rm -f "$DB_PARTIAL" "${DATA_PARTIAL:-}"; }
trap cleanup EXIT

if ! docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true; then
  echo "ERROR: container '$PG_CONTAINER' is not running (set PG_CONTAINER if it has another name)" >&2
  exit 1
fi

echo "[$(date -Is)] Dumping database from $PG_CONTAINER..."
# Custom format: compressed, and pg_restore can restore parts of it.
docker exec "$PG_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' > "$DB_PARTIAL"

# A dump that cannot be listed is not a backup. Fail instead of keeping it.
if ! docker exec -i "$PG_CONTAINER" pg_restore --list < "$DB_PARTIAL" > /dev/null; then
  echo "ERROR: the dump could not be read back by pg_restore; discarding it" >&2
  exit 1
fi
mv "$DB_PARTIAL" "$DB_FILE"
echo "[$(date -Is)] Database dump written: $DB_FILE ($(du -h "$DB_FILE" | cut -f1))"

if [ -n "${DATA_DIR:-}" ]; then
  if [ ! -d "$DATA_DIR" ]; then
    echo "ERROR: DATA_DIR '$DATA_DIR' is not a directory" >&2
    exit 1
  fi
  DATA_FILE="$BACKUP_DIR/yamabiko-data-$STAMP.tar.gz"
  DATA_PARTIAL="$DATA_FILE.partial"
  echo "[$(date -Is)] Archiving $DATA_DIR..."
  tar -czf "$DATA_PARTIAL" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
  tar -tzf "$DATA_PARTIAL" > /dev/null
  mv "$DATA_PARTIAL" "$DATA_FILE"
  echo "[$(date -Is)] Data archive written: $DATA_FILE ($(du -h "$DATA_FILE" | cut -f1))"
fi

# Rotation runs last, so a failed backup never deletes the old ones.
if [ "$KEEP_DAYS" -gt 0 ]; then
  find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'yamabiko-db-*.dump' -o -name 'yamabiko-data-*.tar.gz' \) \
    -mtime "+$KEEP_DAYS" -print -delete | sed 's/^/Removed old backup: /'
fi

echo "[$(date -Is)] Done."
