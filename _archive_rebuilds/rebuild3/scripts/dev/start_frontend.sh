#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_runtime_dir

if pid=$(read_pid "$FRONTEND_PID_FILE" 2>/dev/null) && pid_alive "$pid"; then
  echo "frontend already running (pid=$pid)"
  exit 0
fi

if [[ "$(port_open "$FRONTEND_HOST" "$FRONTEND_PORT")" == "1" ]]; then
  echo "frontend port $FRONTEND_PORT is already occupied; please inspect before starting"
  exit 1
fi

cd "$FRONTEND_DIR"
nohup env REBUILD3_BACKEND_HOST="$BACKEND_HOST" REBUILD3_BACKEND_PORT="$BACKEND_PORT" \
  npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >>"$FRONTEND_LOG_FILE" 2>&1 &
echo $! >"$FRONTEND_PID_FILE"

if wait_for_port "$FRONTEND_HOST" "$FRONTEND_PORT" 30; then
  echo "frontend started on http://$FRONTEND_HOST:$FRONTEND_PORT"
else
  echo "frontend failed to start; check $FRONTEND_LOG_FILE"
  exit 1
fi
