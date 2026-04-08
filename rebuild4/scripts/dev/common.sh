#!/usr/bin/env bash
# rebuild4 dev scripts common utilities

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="$PROJECT_ROOT/runtime"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

LAUNCHER_HOST="${REBUILD4_LAUNCHER_HOST:-127.0.0.1}"
LAUNCHER_PORT="${REBUILD4_LAUNCHER_PORT:-47130}"
BACKEND_HOST="${REBUILD4_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${REBUILD4_BACKEND_PORT:-47131}"
FRONTEND_HOST="${REBUILD4_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${REBUILD4_FRONTEND_PORT:-47132}"
DB_HOST="${REBUILD4_PG_HOST:-192.168.200.217}"
DB_PORT="${REBUILD4_PG_PORT:-5433}"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
BACKEND_LOG_FILE="$RUNTIME_DIR/backend.log"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
FRONTEND_LOG_FILE="$RUNTIME_DIR/frontend.log"

ensure_runtime_dir() { mkdir -p "$RUNTIME_DIR"; }

resolve_python() {
  for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then echo "$candidate"; return; fi
  done
  echo "python3"
}

read_pid() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local p; p=$(cat "$f" 2>/dev/null) || return 1
  [[ "$p" =~ ^[0-9]+$ ]] || { rm -f "$f"; return 1; }
  echo "$p"
}

pid_alive() {
  kill -0 "$1" 2>/dev/null
}

port_open() {
  local host="$1" port="$2"
  if (echo >/dev/tcp/"$host"/"$port") 2>/dev/null; then echo 1; else echo 0; fi
}

wait_for_port() {
  local host="$1" port="$2" timeout="${3:-15}" elapsed=0
  while (( elapsed < timeout )); do
    if [[ "$(port_open "$host" "$port")" == "1" ]]; then return 0; fi
    sleep 1; ((elapsed++))
  done
  return 1
}
