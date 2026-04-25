#!/usr/bin/env bash
# Purpose: run endpoint acceptance after batch 7 completes.
# Inputs: none.
# Expected output: TCL b7 within fix5 D +/-5%, PG17 +/-20%, sliding range clean, enriched coverage clean.
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
enriched AS (
  SELECT
    batch_id,
    MIN(event_time_std)::date AS min_day,
    MAX(event_time_std)::date AS max_day,
    COUNT(*) AS rows,
    COUNT(*) FILTER (
      WHERE event_time_std::date IS DISTINCT FROM DATE '2025-12-01' + (batch_id - 1)
    ) AS off_day_rows
  FROM rb5.enriched_records
  WHERE batch_id BETWEEN 1 AND 7
  GROUP BY batch_id
),
enriched_summary AS (
  SELECT COUNT(*) AS batch_rows,
         COUNT(*) FILTER (WHERE rows > 0 AND min_day = DATE '2025-12-01' + (batch_id - 1)
                                AND max_day = DATE '2025-12-01' + (batch_id - 1)
                                AND off_day_rows = 0) AS strict_nonempty_batches,
         COUNT(*) FILTER (WHERE rows = 0) AS empty_batches,
         COALESCE(SUM(off_day_rows), 0) AS off_day_rows
  FROM enriched
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
    'enriched_7_batch_coverage',
    (batch_rows IN (6, 7) AND strict_nonempty_batches = 6 AND off_day_rows = 0),
    format('batches=%s strict_nonempty=%s empty=%s off_day=%s note=batch1_path_a_empty_allowed', batch_rows, strict_nonempty_batches, empty_batches, off_day_rows)
  FROM enriched_summary
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
enriched AS (
  SELECT batch_id,
         COUNT(*) FILTER (WHERE event_time_std::date IS DISTINCT FROM DATE '2025-12-01' + (batch_id - 1)) AS off_day_rows
  FROM rb5.enriched_records
  WHERE batch_id BETWEEN 1 AND 7
  GROUP BY batch_id
),
enriched_summary AS (
  SELECT COUNT(*) AS batch_rows, COALESCE(SUM(off_day_rows), 0) AS off_day_rows FROM enriched
),
checks AS (
  SELECT (b7_rows BETWEEN 331475 AND 366367) AS ok FROM tcl
  UNION ALL SELECT (b7_rows BETWEEN 273168 AND 409752) FROM tcl
  UNION ALL SELECT (min_day >= DATE '2025-11-24' AND max_day = DATE '2025-12-07' AND old_rows = 0 AND future_rows = 0) FROM sliding
  UNION ALL SELECT (batch_rows IN (6, 7) AND off_day_rows = 0) FROM enriched_summary
)
SELECT COUNT(*) FROM checks WHERE NOT ok;
SQL
)"

if [[ "$fail_count" != "0" ]]; then
  echo "endpoint check failed: $fail_count check(s) failed" >&2
  exit 1
fi
