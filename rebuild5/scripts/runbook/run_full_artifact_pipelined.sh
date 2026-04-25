#!/usr/bin/env bash
# Purpose: run all seven rebuild5 batches with immutable Step 2 input artifacts.
# Inputs: none. Optional env: SKIP_RESET=1, LOG_PATH=/tmp/file.log.
# Expected output: background PID and log path; log ends with artifact_pipelined_complete.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export PGOPTIONS="${PGOPTIONS:--c auto_explain.log_analyze=off}"
export REBUILD5_PG_DSN="${REBUILD5_PG_DSN:-postgres://postgres:123456@192.168.200.217:5488/yangca}"
export PGPASSWORD="${PGPASSWORD:-123456}"
export PGGSSENCMODE="${PGGSSENCMODE:-disable}"

timestamp="$(date +%Y%m%d_%H%M%S)"
LOG_PATH="${LOG_PATH:-/tmp/loop_optim_03_artifact_pipelined_${timestamp}.log}"
PID_PATH="${PID_PATH:-/tmp/loop_optim_03.pid}"

args=(
  "$ROOT_DIR/rebuild5/scripts/run_citus_artifact_pipelined.py"
  --start-day 2025-12-01
  --end-day 2025-12-07
  --start-batch-id 1
)
if [[ "${SKIP_RESET:-0}" == "1" ]]; then
  args+=(--skip-reset)
fi

nohup python3 "${args[@]}" > "$LOG_PATH" 2>&1 &
echo "$!" > "$PID_PATH"
echo "pid=$(cat "$PID_PATH")"
echo "log=$LOG_PATH"
