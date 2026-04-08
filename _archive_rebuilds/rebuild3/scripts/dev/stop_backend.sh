#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
if stop_from_pid_file "$BACKEND_PID_FILE"; then
  echo "backend stopped"
else
  echo "backend pid file not found; nothing to stop"
fi
