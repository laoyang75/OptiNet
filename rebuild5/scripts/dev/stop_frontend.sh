#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
stop_pid_file "$FRONTEND_PID_FILE" "frontend"
