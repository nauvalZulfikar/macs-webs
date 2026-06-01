#!/bin/bash
# Production start: bind to Tailscale IP, no auto-reload, log to file.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

# load env
set -a
. "$ROOT/.env"
set +a

BIND_HOST="${PROD_BIND_HOST:-100.81.47.91}"
PORT="${BIND_PORT:-8000}"

exec "$ROOT/.venv/bin/uvicorn" main:app \
  --host "$BIND_HOST" \
  --port "$PORT" \
  --log-level info \
  --access-log
