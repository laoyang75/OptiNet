#!/usr/bin/env bash
set -euo pipefail

# Step30 16 分片并发执行（需要 psql）
# 用法：
#   export DATABASE_URL='postgresql://...'
#   bash lac_enbid_project/Layer_3/sql/run_step30_sharded_16.sh
# 或直接传参：
#   bash lac_enbid_project/Layer_3/sql/run_step30_sharded_16.sh 'postgresql://...'

DATABASE_URL="${DATABASE_URL:-${1:-}}"
if [[ -z "${DATABASE_URL}" ]]; then
  echo "Usage: DATABASE_URL='postgresql://...' bash $0"
  echo "   or: bash $0 'postgresql://...'"
  exit 2
fi

SHARD_COUNT=16
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SQL_DIR="${SCRIPT_DIR}"

for shard_id in $(seq 0 $((SHARD_COUNT - 1))); do
  shard_suffix="$(printf '%02d' "${shard_id}")"
  shard_table="\"Y_codex_Layer3_Step30_Master_BS_Library__shard_${shard_suffix}\""
  (
    exec psql "$DATABASE_URL" \
      -v shard_count="${SHARD_COUNT}" \
      -v shard_id="${shard_id}" \
      -v step30_master_table="${shard_table}" \
      -f "${SQL_DIR}/30_step30_master_bs_library_shard_psql.sql"
  ) &
done

wait

psql "$DATABASE_URL" \
  -v shard_count="${SHARD_COUNT}" \
  -f "${SQL_DIR}/31_step30_merge_shards_psql.sql"
