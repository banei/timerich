#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
source_env() { grep "^$1=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'"; }
MYSQL_ROOT_PASSWORD=$(source_env MYSQL_ROOT_PASSWORD)
MYSQL_DATABASE=$(source_env MYSQL_DATABASE || echo dca_dashboard)
BACKUP_DIR=$(source_env BACKUP_DIR || echo "$PROJECT_DIR/backups")
mkdir -p "$BACKUP_DIR" "$PROJECT_DIR/logs"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/timerich_${DATE}.sql.gz"
cd "$PROJECT_DIR"
docker compose exec -T mysql mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE" | gzip -9 > "$BACKUP_FILE"
echo "Backup OK: $BACKUP_FILE"
