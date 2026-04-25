#!/usr/bin/env bash
# Purpose: run one day through the serial Citus runner for quick code validation.
# Inputs: run_single_batch.sh <YYYY-MM-DD> <batch_id>. Optional env: SKIP_RESET=1.
# Expected output: runner emits batch_validation for the requested batch.
# Failure handling: stop, run sentinels.sh <batch_id>, and inspect the runner traceback.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <YYYY-MM-DD> <batch_id>" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DAY="$1"
BATCH_ID="$2"
export PGOPTIONS="${PGOPTIONS:--c auto_explain.log_analyze=off}"
export REBUILD5_PG_DSN="${REBUILD5_PG_DSN:-postgres://postgres:123456@192.168.200.217:5488/yangca}"
export PGPASSWORD="${PGPASSWORD:-123456}"
export PGGSSENCMODE="${PGGSSENCMODE:-disable}"

args=(
  "$ROOT_DIR/rebuild5/scripts/run_citus_serial_batches.py"
  --start-day "$DAY"
  --end-day "$DAY"
  --start-batch-id "$BATCH_ID"
)
if [[ "${SKIP_RESET:-0}" == "1" ]]; then
  args+=(--skip-reset)
fi

python3 "${args[@]}"
