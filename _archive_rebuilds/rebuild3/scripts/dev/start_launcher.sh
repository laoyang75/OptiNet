#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_runtime_dir

if pid=$(read_pid "$LAUNCHER_PID_FILE" 2>/dev/null) && pid_alive "$pid"; then
  echo "launcher already running (pid=$pid)"
  exit 0
fi

if [[ "$(port_open "$LAUNCHER_HOST" "$LAUNCHER_PORT")" == "1" ]]; then
  echo "launcher port $LAUNCHER_PORT is already occupied; please inspect before starting"
  exit 1
fi

PY_BIN=$(resolve_python)
cd "$PROJECT_ROOT"
LAUNCHER_ARGS=(--host "$LAUNCHER_HOST" --port "$LAUNCHER_PORT")
if [[ "${REBUILD3_LAUNCHER_OPEN_BROWSER:-1}" == "1" ]]; then
  LAUNCHER_ARGS+=(--open-browser)
fi
nohup env \
  REBUILD3_LAUNCHER_HOST="$LAUNCHER_HOST" \
  REBUILD3_LAUNCHER_PORT="$LAUNCHER_PORT" \
  REBUILD3_BACKEND_HOST="$BACKEND_HOST" \
  REBUILD3_BACKEND_PORT="$BACKEND_PORT" \
  REBUILD3_FRONTEND_HOST="$FRONTEND_HOST" \
  REBUILD3_FRONTEND_PORT="$FRONTEND_PORT" \
  "$PY_BIN" launcher/launcher.py "${LAUNCHER_ARGS[@]}" >>"$LAUNCHER_LOG_FILE" 2>&1 &
echo $! >"$LAUNCHER_PID_FILE"

if wait_for_port "$LAUNCHER_HOST" "$LAUNCHER_PORT" 20; then
  echo "launcher started on http://$LAUNCHER_HOST:$LAUNCHER_PORT"
else
  echo "launcher failed to start; check $LAUNCHER_LOG_FILE"
  exit 1
fi
