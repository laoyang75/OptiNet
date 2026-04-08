#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PHASE1_ENV_QUIET=1 source "$ROOT_DIR/scripts/phase1_env.sh"
LOG_DIR="${PHASE1_OBS_LOG_DIR:-$ROOT_DIR/docs/phase1/dev/run_logs}"
DB_DSN="${PHASE1_DB_DSN:-}"
INPUT_RUN_ID="${1:-${PHASE1_RUN_ID:-}}"

if [[ -z "$DB_DSN" ]]; then
  echo "ERROR: PHASE1_DB_DSN 未设置，无法执行一致性检查。"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: 未找到 psql，请先安装 PostgreSQL 客户端。"
  exit 1
fi

mkdir -p "$LOG_DIR"
TS="$(date -u +"%Y%m%d_%H%M%S")"

if [[ -n "$INPUT_RUN_ID" ]]; then
  RUN_ID="$INPUT_RUN_ID"
else
  RUN_ID="$(
    psql "$DB_DSN" -X -At -v ON_ERROR_STOP=1 \
      -c "SELECT run_id FROM public.\"Y_codex_obs_run_registry\" ORDER BY run_started_at DESC LIMIT 1;"
  )"
fi

if [[ -z "$RUN_ID" ]]; then
  echo "ERROR: 未找到可用 run_id。"
  exit 1
fi

RUN_EXISTS="$(
  psql "$DB_DSN" -X -At -v ON_ERROR_STOP=1 \
    -c "SELECT COUNT(*) FROM public.\"Y_codex_obs_run_registry\" WHERE run_id = '$RUN_ID';"
)"
if [[ "$RUN_EXISTS" == "0" ]]; then
  echo "ERROR: run_id 不存在: $RUN_ID"
  exit 1
fi

FAIL_GATE_CNT="$(
  psql "$DB_DSN" -X -At -v ON_ERROR_STOP=1 \
    -c "SELECT COUNT(*) FROM public.\"Y_codex_obs_gate_result\" WHERE run_id = '$RUN_ID' AND pass_flag IS FALSE;"
)"
NONZERO_RECON_CNT="$(
  psql "$DB_DSN" -X -At -v ON_ERROR_STOP=1 \
    -c "SELECT COUNT(*) FROM public.\"Y_codex_obs_reconciliation\" WHERE run_id = '$RUN_ID' AND diff_value <> 0;"
)"

REPORT_MD="$LOG_DIR/phase1_obs_consistency_${RUN_ID}_${TS}.md"

{
  echo "# Phase1 Obs 一致性检查报告"
  echo ""
  echo "- 检查时间(UTC)：$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "- run_id：\`$RUN_ID\`"
  echo "- 未通过门禁数：\`$FAIL_GATE_CNT\`"
  echo "- 非零对账差值数量：\`$NONZERO_RECON_CNT\`"
  echo ""
  echo "## 1) 运行摘要"
  psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -P border=2 -c "
    SELECT run_id, run_status, run_started_at, run_finished_at, source_db, pipeline_version
    FROM public.\"Y_codex_obs_run_registry\"
    WHERE run_id = '$RUN_ID';
  "
  echo ""
  echo "## 2) 门禁结果"
  psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -P border=2 -c "
    SELECT gate_code, gate_name, actual_value, expected_value, diff_value, pass_flag
    FROM public.\"Y_codex_obs_gate_result\"
    WHERE run_id = '$RUN_ID'
    ORDER BY gate_code;
  "
  echo ""
  echo "## 3) 分层快照"
  psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -P border=2 -c "
    SELECT layer_id, input_rows, output_rows, pass_flag
    FROM public.\"Y_codex_obs_layer_snapshot\"
    WHERE run_id = '$RUN_ID'
    ORDER BY layer_id;
  "
  echo ""
  echo "## 4) 对账明细（按差值绝对值降序）"
  psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -P border=2 -c "
    SELECT check_code, lhs_value, rhs_value, diff_value, pass_flag
    FROM public.\"Y_codex_obs_reconciliation\"
    WHERE run_id = '$RUN_ID'
    ORDER BY ABS(diff_value) DESC, check_code;
  "
  echo ""
  echo "## 5) 异常暴露矩阵"
  psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -P border=2 -c "
    SELECT object_level, field_code, exposed_flag, true_obj_cnt, total_obj_cnt, note
    FROM public.\"Y_codex_obs_exposure_matrix\"
    WHERE run_id = '$RUN_ID'
    ORDER BY object_level, field_code;
  "
} >"$REPORT_MD"

echo "Consistency report generated: $REPORT_MD"
if [[ "$FAIL_GATE_CNT" != "0" || "$NONZERO_RECON_CNT" != "0" ]]; then
  echo "WARNING: 检测到门禁失败或对账差值异常，请优先处理。"
  exit 2
fi
