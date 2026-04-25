#!/usr/bin/env bash
# Purpose: run all seven rebuild5 batches serially as the stable fallback path.
# Inputs: none. Optional env: SKIP_RESET=1, LOG_PATH=/tmp/file.log, START_DAY, END_DAY, START_BATCH_ID.
# Expected output: background PID and log path; log emits one batch_validation per completed batch.
# Failure handling: stop, run sentinels.sh for the last completed batch, then inspect traceback.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export PGOPTIONS="${PGOPTIONS:--c auto_explain.log_analyze=off}"
export REBUILD5_PG_DSN="${REBUILD5_PG_DSN:-postgres://postgres:123456@192.168.200.217:5488/yangca}"
export PGPASSWORD="${PGPASSWORD:-123456}"
export PGGSSENCMODE="${PGGSSENCMODE:-disable}"

START_DAY="${START_DAY:-2025-12-01}"
END_DAY="${END_DAY:-2025-12-07}"
START_BATCH_ID="${START_BATCH_ID:-1}"
timestamp="$(date +%Y%m%d_%H%M%S)"
LOG_PATH="${LOG_PATH:-/tmp/fix6_03_serial_b${START_BATCH_ID}_7_${timestamp}.log}"
PID_PATH="${PID_PATH:-/tmp/fix6_03_serial.pid}"

args=(
  "$ROOT_DIR/rebuild5/scripts/run_citus_serial_batches.py"
  --start-day "$START_DAY"
  --end-day "$END_DAY"
  --start-batch-id "$START_BATCH_ID"
)
if [[ "${SKIP_RESET:-0}" == "1" ]]; then
  args+=(--skip-reset)
fi

nohup python3 "${args[@]}" > "$LOG_PATH" 2>&1 &
echo "$!" > "$PID_PATH"
echo "pid=$(cat "$PID_PATH")"
echo "log=$LOG_PATH"
