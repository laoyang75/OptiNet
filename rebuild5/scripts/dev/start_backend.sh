#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_runtime_dir

if pid=$(read_pid "$BACKEND_PID_FILE" 2>/dev/null) && pid_alive "$pid"; then
  echo "backend already running (pid=$pid)"
  exit 0
fi

if [[ "$(port_open "$BACKEND_HOST" "$BACKEND_PORT")" == "1" ]]; then
  echo "backend port $BACKEND_PORT is already occupied"
  exit 1
fi

PY_BIN=$(resolve_python)
cd "$WORKSPACE_ROOT"
export PYTHONPATH="$WORKSPACE_ROOT"
export REBUILD5_PG_DSN="$PG_DSN"
export REBUILD5_BACKEND_HOST="$BACKEND_HOST"
export REBUILD5_BACKEND_PORT="$BACKEND_PORT"
export REBUILD5_FRONTEND_HOST="$FRONTEND_HOST"
export REBUILD5_FRONTEND_PORT="$FRONTEND_PORT"
spawn_detached "$BACKEND_PID_FILE" "$BACKEND_LOG_FILE" "$WORKSPACE_ROOT" \
  "$PY_BIN" -m uvicorn rebuild5.backend.app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >/dev/null

if wait_for_port "$BACKEND_HOST" "$BACKEND_PORT" 20; then
  echo "backend started on http://$BACKEND_HOST:$BACKEND_PORT"
else
  echo "backend failed to start; check $BACKEND_LOG_FILE"
  exit 1
fi
