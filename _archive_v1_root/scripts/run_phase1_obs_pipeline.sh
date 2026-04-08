#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PHASE1_ENV_QUIET=1 source "$ROOT_DIR/scripts/phase1_env.sh"
SQL_DIR="${PHASE1_OBS_SQL_DIR:-$ROOT_DIR/sql/phase1_obs}"
LOG_DIR="${PHASE1_OBS_LOG_DIR:-$ROOT_DIR/docs/phase1/dev/run_logs}"
DB_DSN="${PHASE1_DB_DSN:-}"
SKIP_DDL="${PHASE1_OBS_SKIP_DDL:-0}"
RUN_GATES="${PHASE1_OBS_RUN_GATES:-1}"

if [[ -z "$DB_DSN" ]]; then
  echo "ERROR: PHASE1_DB_DSN 未设置，无法执行 obs 流水线。"
  echo "示例：export PHASE1_DB_DSN='postgresql://user:pass@host:5432/ip_loc2'"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: 未找到 psql，请先安装 PostgreSQL 客户端。"
  exit 1
fi

mkdir -p "$LOG_DIR"
TS="$(date -u +"%Y%m%d_%H%M%S")"

DDL_SQL="$SQL_DIR/01_obs_ddl.sql"
BUILD_SQL="$SQL_DIR/02_obs_build.sql"
GATE_SQL="$SQL_DIR/03_obs_gate_checks.sql"

DDL_LOG="$LOG_DIR/phase1_obs_ddl_${TS}.log"
BUILD_LOG="$LOG_DIR/phase1_obs_build_${TS}.log"
GATE_LOG="$LOG_DIR/phase1_obs_gates_${TS}.log"
SUMMARY_MD="$LOG_DIR/phase1_obs_pipeline_${TS}.md"

run_sql_file() {
  local sql_file="$1"
  local log_file="$2"
  if [[ ! -f "$sql_file" ]]; then
    echo "ERROR: SQL 文件不存在: $sql_file"
    exit 1
  fi
  echo "Running: $sql_file"
  psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -f "$sql_file" >"$log_file" 2>&1
}

if [[ "$SKIP_DDL" != "1" ]]; then
  run_sql_file "$DDL_SQL" "$DDL_LOG"
else
  echo "Skip DDL (PHASE1_OBS_SKIP_DDL=1)"
fi

run_sql_file "$BUILD_SQL" "$BUILD_LOG"

if [[ "$RUN_GATES" == "1" ]]; then
  run_sql_file "$GATE_SQL" "$GATE_LOG"
else
  echo "Skip Gate Checks (PHASE1_OBS_RUN_GATES=0)"
fi

LATEST_RUN_ID="$(
  psql "$DB_DSN" -X -At -v ON_ERROR_STOP=1 \
    -c "SELECT run_id FROM public.\"Y_codex_obs_run_registry\" ORDER BY run_started_at DESC LIMIT 1;"
)"

RUN_STATUS="$(
  psql "$DB_DSN" -X -At -v ON_ERROR_STOP=1 \
    -c "SELECT COALESCE(run_status, 'unknown') FROM public.\"Y_codex_obs_run_registry\" WHERE run_id = '$LATEST_RUN_ID' LIMIT 1;"
)"

FAIL_GATE_CNT="$(
  psql "$DB_DSN" -X -At -v ON_ERROR_STOP=1 \
    -c "SELECT COUNT(*) FROM public.\"Y_codex_obs_gate_result\" WHERE run_id = '$LATEST_RUN_ID' AND pass_flag IS FALSE;"
)"

{
  echo "# Phase1 Obs 流水线运行报告"
  echo ""
  echo "- 运行时间(UTC)：$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "- run_id：\`$LATEST_RUN_ID\`"
  echo "- run_status：\`$RUN_STATUS\`"
  echo "- 未通过门禁数：\`$FAIL_GATE_CNT\`"
  echo "- DDL日志：\`$DDL_LOG\`"
  echo "- Build日志：\`$BUILD_LOG\`"
  echo "- Gate日志：\`$GATE_LOG\`"
  echo ""
  echo "## 门禁结果"
  echo ""
  psql "$DB_DSN" -X -v ON_ERROR_STOP=1 -P border=2 -c "
    SELECT gate_code, gate_name, actual_value, expected_value, diff_value, pass_flag
    FROM public.\"Y_codex_obs_gate_result\"
    WHERE run_id = '$LATEST_RUN_ID'
    ORDER BY gate_code;
  "
} >"$SUMMARY_MD"

echo "Pipeline finished. Summary: $SUMMARY_MD"
if [[ "$FAIL_GATE_CNT" != "0" ]]; then
  echo "WARNING: 存在未通过门禁，请查看报告。"
  exit 2
fi
