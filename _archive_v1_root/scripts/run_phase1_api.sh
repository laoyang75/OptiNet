#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PHASE1_ENV_QUIET=1 source "$ROOT_DIR/scripts/phase1_env.sh"
PORT="${PHASE1_API_PORT:-8508}"
HOST="${PHASE1_API_HOST:-127.0.0.1}"

exec uvicorn apps.phase1_api.server:app --app-dir "$ROOT_DIR" --host "$HOST" --port "$PORT"
