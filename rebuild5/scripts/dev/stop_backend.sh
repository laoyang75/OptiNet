#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
stop_pid_file "$BACKEND_PID_FILE" "backend"
