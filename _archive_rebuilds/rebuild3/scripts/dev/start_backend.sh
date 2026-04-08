#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_runtime_dir

if pid=$(read_pid "$BACKEND_PID_FILE" 2>/dev/null) && pid_alive "$pid"; then
  echo "backend already running (pid=$pid)"
  exit 0
fi

if [[ "$(port_open "$BACKEND_HOST" "$BACKEND_PORT")" == "1" ]]; then
  echo "backend port $BACKEND_PORT is already occupied; please inspect before starting"
  exit 1
fi

PY_BIN=$(resolve_python)
cd "$BACKEND_DIR"
nohup env REBUILD3_FRONTEND_HOST="$FRONTEND_HOST" REBUILD3_FRONTEND_PORT="$FRONTEND_PORT" \
  "$PY_BIN" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >>"$BACKEND_LOG_FILE" 2>&1 &
echo $! >"$BACKEND_PID_FILE"

if wait_for_port "$BACKEND_HOST" "$BACKEND_PORT" 20; then
  echo "backend started on http://$BACKEND_HOST:$BACKEND_PORT"
else
  echo "backend failed to start; check $BACKEND_LOG_FILE"
  exit 1
fi
