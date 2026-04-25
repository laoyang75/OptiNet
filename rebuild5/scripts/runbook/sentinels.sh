#!/usr/bin/env bash
# Purpose: run the four per-batch data sentinels after each batch completes.
# Inputs: sentinels.sh <batch_id>.
# Expected output: four PASS/FAIL rows; any FAIL exits non-zero.
# Failure handling: stop the runner immediately and write a blocker note before further batches.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <batch_id>" >&2
  exit 2
fi

BATCH_ID="$1"
export PGHOST="${PGHOST:-192.168.200.217}"
export PGPORT="${PGPORT:-5488}"
export PGDATABASE="${PGDATABASE:-yangca}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-123456}"
export PGGSSENCMODE="${PGGSSENCMODE:-disable}"

psql -X -v ON_ERROR_STOP=1 -v bid="$BATCH_ID" <<'SQL'
CREATE TEMP TABLE sentinel_checks AS
WITH params AS (
  SELECT :'bid'::int AS bid, DATE '2025-12-01' + (:'bid'::int - 1) AS expected_day
),
enriched AS (
  SELECT
    p.bid,
    p.expected_day,
    COUNT(e.*) AS rows,
    MIN(e.event_time_std)::date AS min_day,
    MAX(e.event_time_std)::date AS max_day,
    COUNT(e.*) FILTER (
      WHERE e.event_time_std::date IS DISTINCT FROM p.expected_day
    ) AS off_day_rows
  FROM params p
  LEFT JOIN rb5.enriched_records e ON e.batch_id = p.bid
  GROUP BY p.bid, p.expected_day
),
sliding AS (
  SELECT
    p.bid,
    MIN(s.event_time_std)::date AS min_day,
    MAX(s.event_time_std)::date AS max_day,
    MAX(s.event_time_std) - MIN(s.event_time_std) AS span,
    COUNT(*) FILTER (WHERE s.event_time_std < DATE '2025-01-01') AS old_rows,
    COUNT(*) FILTER (WHERE s.event_time_std >= DATE '2025-12-08') AS future_rows
  FROM params p
  LEFT JOIN rb5.cell_sliding_window s ON s.batch_id = p.bid
  GROUP BY p.bid
),
scope_rel AS (
  SELECT to_regclass('rb5._step2_cell_input') AS fallback_rel,
         to_regclass('rb5.step2_batch_input') AS scope_rel
),
scope_max AS (
  SELECT CASE
    WHEN (SELECT scope_rel FROM scope_rel) IS NULL THEN NULL::date
    ELSE (SELECT MAX(event_time_std)::date FROM rb5.step2_batch_input)
  END AS max_day
),
tcl AS (
  SELECT p.bid, COUNT(t.*) AS rows
  FROM params p
  LEFT JOIN rb5.trusted_cell_library t ON t.batch_id = p.bid
  GROUP BY p.bid
),
prev_tcl AS (
  SELECT p.bid, COUNT(t.*) AS rows
  FROM params p
  LEFT JOIN rb5.trusted_cell_library t ON t.batch_id = p.bid - 1
  GROUP BY p.bid
)
SELECT
  'enriched_single_day' AS check_name,
  (rows = 0 OR (min_day = expected_day AND max_day = expected_day AND off_day_rows = 0)) AS ok,
  format('rows=%s min=%s max=%s off_day=%s expected=%s', rows, min_day, max_day, off_day_rows, expected_day) AS detail
FROM enriched
UNION ALL
SELECT
  'sliding_span_no_old_future',
  (span <= INTERVAL '14 days' AND old_rows = 0 AND future_rows = 0),
  format('min=%s max=%s span=%s old=%s future=%s', min_day, max_day, span, old_rows, future_rows)
FROM sliding
UNION ALL
SELECT
  'step2_scope_clean_or_today',
  (
    (SELECT fallback_rel FROM scope_rel) IS NULL
    AND ((SELECT scope_rel FROM scope_rel) IS NULL OR (SELECT max_day FROM scope_max) = (SELECT expected_day FROM params))
  ),
  format('fallback=%s scope=%s scope_max=%s', (SELECT fallback_rel FROM scope_rel), (SELECT scope_rel FROM scope_rel), (SELECT max_day FROM scope_max))
UNION ALL
SELECT
  'tcl_monotonic',
  (tcl.rows > 0 AND (tcl.bid = 1 OR tcl.rows > prev_tcl.rows)),
  format('batch=%s rows=%s prev_rows=%s', tcl.bid, tcl.rows, prev_tcl.rows)
FROM tcl JOIN prev_tcl USING (bid);

SELECT check_name, CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END AS status, detail
FROM sentinel_checks
ORDER BY check_name;

SELECT COUNT(*) AS fail_count FROM sentinel_checks WHERE NOT ok;
SELECT CASE WHEN COUNT(*) = 0 THEN 'true' ELSE 'false' END AS sentinel_ok
FROM sentinel_checks
WHERE NOT ok;
\gset
\if :sentinel_ok
\else
  \echo sentinel failed for batch :bid: :fail_count check(s) failed
  \quit 1
\endif
SQL
