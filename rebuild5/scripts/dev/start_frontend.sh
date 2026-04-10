#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_runtime_dir

if pid=$(read_pid "$FRONTEND_PID_FILE" 2>/dev/null) && pid_alive "$pid"; then
  echo "frontend already running (pid=$pid)"
  exit 0
fi

if [[ "$(port_open "$FRONTEND_HOST" "$FRONTEND_PORT")" == "1" ]]; then
  echo "frontend port $FRONTEND_PORT is already occupied"
  exit 1
fi

cd "$FRONTEND_DIR"
export VITE_API_BASE_URL="http://$BACKEND_HOST:$BACKEND_PORT"
spawn_detached "$FRONTEND_PID_FILE" "$FRONTEND_LOG_FILE" "$FRONTEND_DIR" \
  npx vite --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >/dev/null

if wait_for_port "$FRONTEND_HOST" "$FRONTEND_PORT" 20; then
  echo "frontend started on http://$FRONTEND_HOST:$FRONTEND_PORT"
else
  echo "frontend failed to start; check $FRONTEND_LOG_FILE"
  exit 1
fi
