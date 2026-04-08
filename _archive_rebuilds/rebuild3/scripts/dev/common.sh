#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
RUNTIME_DIR="$PROJECT_ROOT/runtime"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
LAUNCHER_DIR="$PROJECT_ROOT/launcher"
BACKEND_HOST="${REBUILD3_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${REBUILD3_BACKEND_PORT:-47121}"
FRONTEND_HOST="${REBUILD3_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${REBUILD3_FRONTEND_PORT:-47122}"
LAUNCHER_HOST="${REBUILD3_LAUNCHER_HOST:-127.0.0.1}"
LAUNCHER_PORT="${REBUILD3_LAUNCHER_PORT:-47120}"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
BACKEND_LOG_FILE="$RUNTIME_DIR/backend.log"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
FRONTEND_LOG_FILE="$RUNTIME_DIR/frontend.log"
LAUNCHER_PID_FILE="$RUNTIME_DIR/launcher.pid"
LAUNCHER_LOG_FILE="$RUNTIME_DIR/launcher.log"

ensure_runtime_dir() {
  mkdir -p "$RUNTIME_DIR"
}

resolve_python() {
  if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    echo "$PROJECT_ROOT/.venv/bin/python"
  else
    echo "python3"
  fi
}

read_pid() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  cat "$pid_file"
}

pid_alive() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

port_open() {
  local host="$1"
  local port="$2"
  python3 - "$host" "$port" <<'PY'
import socket
import sys
host = sys.argv[1]
port = int(sys.argv[2])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.5)
try:
    ok = sock.connect_ex((host, port)) == 0
finally:
    sock.close()
print('1' if ok else '0')
PY
}

wait_for_port() {
  local host="$1"
  local port="$2"
  local attempts="${3:-20}"
  for ((i=0; i<attempts; i++)); do
    if [[ "$(port_open "$host" "$port")" == "1" ]]; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

stop_from_pid_file() {
  local pid_file="$1"
  if ! pid=$(read_pid "$pid_file" 2>/dev/null); then
    return 1
  fi
  if pid_alive "$pid"; then
    kill "$pid"
    for _ in {1..20}; do
      if ! pid_alive "$pid"; then
        rm -f "$pid_file"
        return 0
      fi
      sleep 0.3
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
  return 0
}

service_status_line() {
  local name="$1"
  local host="$2"
  local port="$3"
  local pid_file="$4"
  local pid="--"
  local status="stopped"
  if pid=$(read_pid "$pid_file" 2>/dev/null) && pid_alive "$pid"; then
    status="running"
  elif [[ "$(port_open "$host" "$port")" == "1" ]]; then
    status="port-open"
    pid="unknown"
  else
    pid="--"
  fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$status" "$host:$port" "$pid"
}
