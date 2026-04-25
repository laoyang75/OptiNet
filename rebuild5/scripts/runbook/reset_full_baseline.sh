#!/usr/bin/env bash
# Purpose: reset rebuild5 Step 1-5 state before a full 7-batch baseline run.
# Inputs: none. Optional env: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD.
# Expected output: reset SQL succeeds and key result tables are empty/missing.
# Failure handling: stop immediately, inspect the psql error, then rerun reset before any runner.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export PGHOST="${PGHOST:-192.168.200.217}"
export PGPORT="${PGPORT:-5488}"
export PGDATABASE="${PGDATABASE:-yangca}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-123456}"
export PGGSSENCMODE="${PGGSSENCMODE:-disable}"

psql -X -v ON_ERROR_STOP=1 \
  -f "$ROOT_DIR/rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql"

psql -X -v ON_ERROR_STOP=1 <<'SQL'
SELECT
  to_regclass('rb5.enriched_records') AS enriched_records_regclass,
  (SELECT COUNT(*) FROM rb5.trusted_cell_library) AS trusted_cell_library_rows,
  (SELECT COUNT(*) FROM rb5.cell_sliding_window) AS cell_sliding_window_rows,
  to_regclass('rb5._step2_cell_input') AS step2_fallback_regclass,
  to_regclass('rb5.step2_batch_input') AS step2_scope_regclass;
SQL
