#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
if stop_from_pid_file "$LAUNCHER_PID_FILE"; then
  echo "launcher stopped"
else
  echo "launcher pid file not found; nothing to stop"
fi
