#!/usr/bin/env bash
set -euo pipefail

# Step30 v4：PREPARE（单次）+ METRICS（分片并行）+ MERGE
#
# 设计目标：
# - 避免旧版“每个 shard 会话重复扫 Step02/Step05”的 16x 放大
# - 先落桶（semi-join bucket_universe），再对每桶仅取最近 N=1000 点跑重链路
#
# 用法：
#   export DATABASE_URL='postgresql://...'
#   bash lac_enbid_project/Layer_3/sql/run_step30_v4_sharded_32.sh
#
# 可选参数：
#   SHARD_COUNT=32                 # 默认 32（40 核机器建议 24~36）
#   STEP30_MASTER_TABLE=...        # 默认 Y_codex_Layer3_Step30_Master_BS_Library
#   STEP30_STATS_TABLE=...         # 默认 Y_codex_Layer3_Step30_Gps_Level_Stats
#   SKIP_PREPARE=1                 # 跳过 PREPARE（已物化过底座时用于重跑 METRICS/MERGE）
#   SKIP_METRICS=1                 # 跳过 METRICS（仅重跑 MERGE）

DATABASE_URL="${DATABASE_URL:-${1:-}}"
if [[ -z "${DATABASE_URL}" ]]; then
  echo "Usage: DATABASE_URL='postgresql://...' bash $0"
  echo "   or: bash $0 'postgresql://...'"
  exit 2
fi

SHARD_COUNT="${SHARD_COUNT:-32}"
if ! [[ "${SHARD_COUNT}" =~ ^[0-9]+$ ]] || [[ "${SHARD_COUNT}" -le 0 ]]; then
  echo "ERROR: SHARD_COUNT must be a positive integer"
  exit 2
fi

STEP30_MASTER_TABLE_NAME="${STEP30_MASTER_TABLE:-Y_codex_Layer3_Step30_Master_BS_Library}"
STEP30_STATS_TABLE_NAME="${STEP30_STATS_TABLE:-Y_codex_Layer3_Step30_Gps_Level_Stats}"
STEP30_MASTER_TABLE="\"${STEP30_MASTER_TABLE_NAME}\""
STEP30_STATS_TABLE="\"${STEP30_STATS_TABLE_NAME}\""

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${SKIP_PREPARE:-0}" == "1" ]]; then
  echo "[Step30 v4] PREPARE skipped (SKIP_PREPARE=1)"
else
  if [[ -n "${SKIP_PREPARE:-}" ]]; then
    echo "[Step30 v4] PREPARE (SKIPPED)"
  else
    echo "[Step30 v4] PREPARE"
    psql "$DATABASE_URL" \
      -f "${SCRIPT_DIR}/30_step30_master_bs_library_v4_prepare.sql"
  fi
fi

if [[ "${SKIP_METRICS:-0}" == "1" ]]; then
  echo "[Step30 v4] METRICS skipped (SKIP_METRICS=1)"
else
  echo "[Step30 v4] METRICS shards=${SHARD_COUNT}"
  pids=()
  shard_ids=()
  for shard_id in $(seq 0 $((SHARD_COUNT - 1))); do
    shard_suffix="$(printf '%02d' "${shard_id}")"
    shard_table="\"Y_codex_Layer3_Step30__v4_metrics__shard_${shard_suffix}\""
    (
      exec psql "$DATABASE_URL" \
        -v shard_count="${SHARD_COUNT}" \
        -v shard_id="${shard_id}" \
        -v step30_metrics_table="${shard_table}" \
        -f "${SCRIPT_DIR}/30_step30_master_bs_library_v4_metrics_shard_psql.sql"
    ) &
    pids+=("$!")
    shard_ids+=("${shard_id}")
  done

  failed=0
  for i in "${!pids[@]}"; do
    pid="${pids[$i]}"
    sid="${shard_ids[$i]}"
    if ! wait "${pid}"; then
      echo "[Step30 v4] ERROR: shard ${sid} failed (pid=${pid})" >&2
      failed=1
    fi
  done
  if [[ "${failed}" -ne 0 ]]; then
    echo "[Step30 v4] ERROR: one or more shards failed; refusing to merge." >&2
    exit 1
  fi
fi

echo "[Step30 v4] MERGE"
psql "$DATABASE_URL" \
  -v shard_count="${SHARD_COUNT}" \
  -v step30_master_table="${STEP30_MASTER_TABLE}" \
  -v step30_stats_table="${STEP30_STATS_TABLE}" \
  -f "${SCRIPT_DIR}/30_step30_master_bs_library_v4_merge_psql.sql"

echo "[Step30 v4] DONE master_table=${STEP30_MASTER_TABLE_NAME} stats_table=${STEP30_STATS_TABLE_NAME}"
