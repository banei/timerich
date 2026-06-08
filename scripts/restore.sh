#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
source_env() { grep "^$1=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'"; }
MYSQL_ROOT_PASSWORD=$(source_env MYSQL_ROOT_PASSWORD)
MYSQL_DATABASE=$(source_env MYSQL_DATABASE || echo dca_dashboard)
BACKUP_DIR=$(source_env BACKUP_DIR || echo "$PROJECT_DIR/backups")
TARGET="${1:-latest}"
if [[ "$TARGET" == "latest" ]]; then
  FILE=$(ls -t "$BACKUP_DIR"/timerich_*.sql.gz 2>/dev/null | head -1)
else
  FILE="$BACKUP_DIR/$TARGET"
fi
[[ -f "$FILE" ]] || { echo "备份不存在: $FILE"; exit 1; }
cd "$PROJECT_DIR"
gzip -dc "$FILE" | docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"
echo "Restore OK from $FILE"
