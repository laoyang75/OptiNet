#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
ensure_runtime_dir
printf 'service\tstatus\tendpoint\tpid\n'
service_status_line launcher "$LAUNCHER_HOST" "$LAUNCHER_PORT" "$LAUNCHER_PID_FILE"
service_status_line backend "$BACKEND_HOST" "$BACKEND_PORT" "$BACKEND_PID_FILE"
service_status_line frontend "$FRONTEND_HOST" "$FRONTEND_PORT" "$FRONTEND_PID_FILE"
printf 'database\tmanual\t%s:%s\t--\n' "${REBUILD3_PG_HOST:-192.168.200.217}" "${REBUILD3_PG_PORT:-5433}"
printf 'launcher-log\t--\t%s\t--\n' "$LAUNCHER_LOG_FILE"
printf 'backend-log\t--\t%s\t--\n' "$BACKEND_LOG_FILE"
printf 'frontend-log\t--\t%s\t--\n' "$FRONTEND_LOG_FILE"
