#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
LOG_DIR="$ROOT_DIR/.logs"
mkdir -p "$LOG_DIR"

DSN="${REBUILD3_PG_DSN:-postgresql://postgres:123456@192.168.200.217:5433/ip_loc2}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/timepoint_snapshot_scenarios_${TS}.log"
PID_FILE="$LOG_DIR/timepoint_snapshot_scenarios_${TS}.pid"

nohup "$PYTHON_BIN" "$ROOT_DIR/backend/scripts/run_timepoint_snapshot_scenarios.py" \
  --dsn "$DSN" \
  --mode scenarios \
  >"$LOG_FILE" 2>&1 &

echo $! >"$PID_FILE"
echo "started pid=$(cat "$PID_FILE")"
echo "log_file=$LOG_FILE"
echo "pid_file=$PID_FILE"

