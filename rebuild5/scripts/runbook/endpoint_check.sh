#!/usr/bin/env bash
# Purpose: run endpoint acceptance after batch 7 completes.
# Inputs: none.
# Expected output: TCL b7 within fix5 D +/-5%, PG17 +/-20%, sliding range clean, current enriched batch clean.
# Failure handling: treat any FAIL as blocker; do not publish the run as complete.
set -euo pipefail

export PGHOST="${PGHOST:-192.168.200.217}"
export PGPORT="${PGPORT:-5488}"
export PGDATABASE="${PGDATABASE:-yangca}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-123456}"
export PGGSSENCMODE="${PGGSSENCMODE:-disable}"

psql -X -v ON_ERROR_STOP=1 <<'SQL'
WITH tcl AS (
  SELECT COUNT(*) AS b7_rows FROM rb5.trusted_cell_library WHERE batch_id = 7
),
sliding AS (
  SELECT MIN(event_time_std)::date AS min_day,
         MAX(event_time_std)::date AS max_day,
         COUNT(*) FILTER (WHERE event_time_std < DATE '2025-01-01') AS old_rows,
         COUNT(*) FILTER (WHERE event_time_std >= DATE '2025-12-08') AS future_rows
  FROM rb5.cell_sliding_window
),
latest_batch AS (
  SELECT COALESCE(MAX(batch_id), 7) AS batch_id
  FROM rb5.trusted_cell_library
  WHERE batch_id BETWEEN 1 AND 7
),
-- rb5.enriched_records is intentionally UNLOGGED. Container restart truncates
-- history batches, so endpoint validation only checks the current TCL batch.
enriched_latest AS (
  SELECT
    l.batch_id,
    DATE '2025-12-01' + (l.batch_id - 1) AS expected_day,
    COUNT(e.*) AS rows,
    MIN(e.event_time_std)::date AS min_day,
    MAX(e.event_time_std)::date AS max_day,
    COUNT(e.*) FILTER (
      WHERE e.event_time_std::date IS DISTINCT FROM DATE '2025-12-01' + (l.batch_id - 1)
    ) AS off_day_rows
  FROM latest_batch l
  LEFT JOIN rb5.enriched_records e ON e.batch_id = l.batch_id
  GROUP BY l.batch_id
),
checks AS (
  SELECT
    'tcl_b7_vs_fix5_serial_pm5' AS check_name,
    (b7_rows BETWEEN 331475 AND 366367) AS ok,
    format('b7_rows=%s fix5_serial=348921', b7_rows) AS detail
  FROM tcl
  UNION ALL
  SELECT
    'tcl_b7_vs_pg17_pm20',
    (b7_rows BETWEEN 273168 AND 409752),
    format('b7_rows=%s pg17=341460', b7_rows)
  FROM tcl
  UNION ALL
  SELECT
    'sliding_endpoint_range',
    (min_day >= DATE '2025-11-24' AND max_day = DATE '2025-12-07' AND old_rows = 0 AND future_rows = 0),
    format('min=%s max=%s old=%s future=%s', min_day, max_day, old_rows, future_rows)
  FROM sliding
  UNION ALL
  SELECT
    'enriched_latest_batch',
    (rows > 0 AND min_day = expected_day AND max_day = expected_day AND off_day_rows = 0),
    format('batch=%s rows=%s min=%s max=%s off_day=%s expected=%s note=unlogged_current_batch_only', batch_id, rows, min_day, max_day, off_day_rows, expected_day)
  FROM enriched_latest
)
SELECT check_name, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS status, detail
FROM checks;
SQL

fail_count="$(
  psql -X -At -v ON_ERROR_STOP=1 <<'SQL'
WITH tcl AS (
  SELECT COUNT(*) AS b7_rows FROM rb5.trusted_cell_library WHERE batch_id = 7
),
sliding AS (
  SELECT MIN(event_time_std)::date AS min_day,
         MAX(event_time_std)::date AS max_day,
         COUNT(*) FILTER (WHERE event_time_std < DATE '2025-01-01') AS old_rows,
         COUNT(*) FILTER (WHERE event_time_std >= DATE '2025-12-08') AS future_rows
  FROM rb5.cell_sliding_window
),
latest_batch AS (
  SELECT COALESCE(MAX(batch_id), 7) AS batch_id
  FROM rb5.trusted_cell_library
  WHERE batch_id BETWEEN 1 AND 7
),
enriched_latest AS (
  SELECT l.batch_id,
         DATE '2025-12-01' + (l.batch_id - 1) AS expected_day,
         COUNT(e.*) AS rows,
         MIN(e.event_time_std)::date AS min_day,
         MAX(e.event_time_std)::date AS max_day,
         COUNT(e.*) FILTER (
           WHERE e.event_time_std::date IS DISTINCT FROM DATE '2025-12-01' + (l.batch_id - 1)
         ) AS off_day_rows
  FROM latest_batch l
  LEFT JOIN rb5.enriched_records e ON e.batch_id = l.batch_id
  GROUP BY l.batch_id
),
checks AS (
  SELECT (b7_rows BETWEEN 331475 AND 366367) AS ok FROM tcl
  UNION ALL SELECT (b7_rows BETWEEN 273168 AND 409752) FROM tcl
  UNION ALL SELECT (min_day >= DATE '2025-11-24' AND max_day = DATE '2025-12-07' AND old_rows = 0 AND future_rows = 0) FROM sliding
  UNION ALL SELECT (rows > 0 AND min_day = expected_day AND max_day = expected_day AND off_day_rows = 0) FROM enriched_latest
)
SELECT COUNT(*) FROM checks WHERE NOT ok;
SQL
)"

if [[ "$fail_count" != "0" ]]; then
  echo "endpoint check failed: $fail_count check(s) failed" >&2
  exit 1
fi
