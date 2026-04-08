#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
if stop_from_pid_file "$FRONTEND_PID_FILE"; then
  echo "frontend stopped"
else
  echo "frontend pid file not found; nothing to stop"
fi
