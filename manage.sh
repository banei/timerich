#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
ACTION="${1:-up}"

case "$ACTION" in
  up) docker compose up -d --build ;;
  down) docker compose down ;;
  restart) docker compose restart ;;
  logs) docker compose logs -f ;;
  ps) docker compose ps ;;
  build) docker compose build ;;
  migrate) docker compose exec backend alembic upgrade head ;;
  seed) docker compose exec backend python -m app.scripts.seed ;;
  backup) bash ./scripts/backup.sh ;;
  *) docker compose up -d --build ;;
esac

echo "Done: $ACTION"
