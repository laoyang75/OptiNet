#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

if pid=$(read_pid "$BACKEND_PID_FILE" 2>/dev/null) && pid_alive "$pid"; then
  kill "$pid" 2>/dev/null || true
  sleep 1
  pid_alive "$pid" && kill -9 "$pid" 2>/dev/null || true
  rm -f "$BACKEND_PID_FILE"
  echo "backend stopped (pid=$pid)"
else
  echo "backend not running"
fi
