#!/usr/bin/env bash
set -euo pipefail

# Layer_4：按 BS shard 并行跑 Step40+Step41，然后汇总指标/对比
#
# 用法：
#   export DATABASE_URL='postgresql://...'
#   bash lac_enbid_project/Layer_4/sql/run_layer4_sharded_32.sh
#
# 可选参数：
#   SHARD_COUNT=32     # 默认 32（按机器/库负载调整）
#   MAX_JOBS=8         # 并发数上限（避免把 DB 打满）
#   IS_SMOKE=0|1       # 是否冒烟（默认 0）
#   SMOKE_DATE=YYYY-MM-DD
#   SMOKE_OPERATOR_ID_RAW=46000
#
# 产物：
# - Step40: public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill__shard_XX" + metrics
# - Step41: public."Y_codex_Layer4_Final_Cell_Library__shard_XX" + metrics
# - Step42: public."Y_codex_Layer4_Step42_Compare_Summary"
# - Step43: public."Y_codex_Layer4_Step40_Gps_Metrics_All" / public."Y_codex_Layer4_Step41_Signal_Metrics_All"

DATABASE_URL="${DATABASE_URL:-${1:-}}"
if [[ -z "${DATABASE_URL}" ]]; then
  echo "Usage: DATABASE_URL='postgresql://...' bash $0"
  echo "   or: bash $0 'postgresql://...'"
  exit 2
fi

SHARD_COUNT="${SHARD_COUNT:-32}"
MAX_JOBS="${MAX_JOBS:-8}"
IS_SMOKE="${IS_SMOKE:-0}"
SMOKE_DATE="${SMOKE_DATE:-2025-12-01}"
SMOKE_OPERATOR_ID_RAW="${SMOKE_OPERATOR_ID_RAW:-46000}"

if ! [[ "${SHARD_COUNT}" =~ ^[0-9]+$ ]] || [[ "${SHARD_COUNT}" -le 0 ]]; then
  echo "ERROR: SHARD_COUNT must be a positive integer" >&2
  exit 2
fi
if ! [[ "${MAX_JOBS}" =~ ^[0-9]+$ ]] || [[ "${MAX_JOBS}" -le 0 ]]; then
  echo "ERROR: MAX_JOBS must be a positive integer" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

SMOKE_BOOL='false'
if [[ "${IS_SMOKE}" == "1" || "${IS_SMOKE}" == "true" ]]; then
  SMOKE_BOOL='true'
fi

run_one_shard() {
  local shard_id="$1"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
    -c "SET codex.shard_count='${SHARD_COUNT}'; SET codex.shard_id='${shard_id}'; SET codex.is_smoke='${SMOKE_BOOL}'; SET codex.smoke_date='${SMOKE_DATE}'; SET codex.smoke_operator_id_raw='${SMOKE_OPERATOR_ID_RAW}';" \
    -f "${SCRIPT_DIR}/40_step40_cell_gps_filter_fill.sql" \
    -f "${SCRIPT_DIR}/41_step41_cell_signal_fill.sql"
}

echo "[Layer_4] RUN shards=${SHARD_COUNT} max_jobs=${MAX_JOBS} smoke=${SMOKE_BOOL}"

declare -A pid_to_shard=()
pids=()
failed=0

for shard_id in $(seq 0 $((SHARD_COUNT - 1))); do
  while [[ "${#pids[@]}" -ge "${MAX_JOBS}" ]]; do
    finished_pid=""
    if wait -n -p finished_pid; then
      :
    else
      echo "[Layer_4] ERROR: shard ${pid_to_shard[${finished_pid}]:-unknown} failed (pid=${finished_pid})" >&2
      failed=1
    fi
    unset "pid_to_shard[${finished_pid}]"
    new_pids=()
    for p in "${pids[@]}"; do
      if [[ "${p}" != "${finished_pid}" ]]; then
        new_pids+=("${p}")
      fi
    done
    pids=("${new_pids[@]}")
  done

  (
    run_one_shard "${shard_id}"
  ) &
  pid="$!"
  pids+=("${pid}")
  pid_to_shard["${pid}"]="${shard_id}"
done

for pid in "${pids[@]}"; do
  if ! wait "${pid}"; then
    echo "[Layer_4] ERROR: shard ${pid_to_shard[${pid}]:-unknown} failed (pid=${pid})" >&2
    failed=1
  fi
done

if [[ "${failed}" -ne 0 ]]; then
  echo "[Layer_4] ERROR: one or more shards failed; refusing to run Step42/Step43." >&2
  exit 1
fi

echo "[Layer_4] Step42 compare (auto UNION shards when shard_count>1)"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -c "SET codex.shard_count='${SHARD_COUNT}'; SET codex.is_smoke='${SMOKE_BOOL}'; SET codex.smoke_date='${SMOKE_DATE}'; SET codex.smoke_operator_id_raw='${SMOKE_OPERATOR_ID_RAW}';" \
  -f "${SCRIPT_DIR}/42_step42_compare.sql"

echo "[Layer_4] Step43 merge metrics"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -c "SET codex.shard_count='${SHARD_COUNT}';" \
  -f "${SCRIPT_DIR}/43_step43_merge_metrics.sql"

echo "[Layer_4] DONE"
