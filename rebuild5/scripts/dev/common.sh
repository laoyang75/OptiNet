#!/usr/bin/env bash
# rebuild5 dev scripts common utilities

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"
RUNTIME_DIR="$PROJECT_ROOT/runtime"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend/design"

LAUNCHER_HOST="${REBUILD5_LAUNCHER_HOST:-127.0.0.1}"
LAUNCHER_PORT="${REBUILD5_LAUNCHER_PORT:-47230}"
BACKEND_HOST="${REBUILD5_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${REBUILD5_BACKEND_PORT:-47231}"
FRONTEND_HOST="${REBUILD5_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${REBUILD5_FRONTEND_PORT:-47232}"
PG_DSN="${REBUILD5_PG_DSN:-postgresql://postgres:123456@192.168.200.217:5488/yangca}"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
BACKEND_LOG_FILE="$RUNTIME_DIR/backend.log"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
FRONTEND_LOG_FILE="$RUNTIME_DIR/frontend.log"

ensure_runtime_dir() { mkdir -p "$RUNTIME_DIR"; }

resolve_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return
    fi
  done
  echo "python3"
}

read_pid() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local pid
  pid=$(cat "$file" 2>/dev/null) || return 1
  [[ "$pid" =~ ^[0-9]+$ ]] || {
    rm -f "$file"
    return 1
  }
  echo "$pid"
}

pid_alive() {
  kill -0 "$1" 2>/dev/null
}

port_open() {
  local host="$1" port="$2"
  if (echo >/dev/tcp/"$host"/"$port") >/dev/null 2>&1; then
    echo 1
  else
    echo 0
  fi
}

wait_for_port() {
  local host="$1" port="$2" timeout="${3:-20}" elapsed=0
  while (( elapsed < timeout )); do
    if [[ "$(port_open "$host" "$port")" == "1" ]]; then
      return 0
    fi
    sleep 1
    ((elapsed++))
  done
  return 1
}

spawn_detached() {
  local pid_file="$1"
  local log_file="$2"
  local workdir="$3"
  shift 3
  local py_bin
  py_bin=$(resolve_python)

  "$py_bin" - "$pid_file" "$log_file" "$workdir" "$@" <<'PY'
import pathlib
import subprocess
import sys

pid_file, log_file, workdir, *cmd = sys.argv[1:]
with open(log_file, 'ab', buffering=0) as log:
    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
pathlib.Path(pid_file).write_text(str(proc.pid))
print(proc.pid)
PY
}

stop_pid_file() {
  local pid_file="$1"
  local name="$2"
  local pid
  if ! pid=$(read_pid "$pid_file"); then
    echo "$name is not running"
    return 0
  fi

  kill "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    if ! pid_alive "$pid"; then
      rm -f "$pid_file"
      echo "$name stopped"
      return 0
    fi
    sleep 0.5
  done

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "$name force stopped"
}
