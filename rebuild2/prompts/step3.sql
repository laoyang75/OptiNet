SET statement_timeout = 0;
SET work_mem = '512MB';
\timing on

-- STEP 3：BS 级 GPS 点数统计
DROP TABLE IF EXISTS rebuild2._tmp_bs_cnt;
CREATE TABLE rebuild2._tmp_bs_cnt AS
SELECT op, tech, lac, bs_id,
    count(*)              AS n,
    count(DISTINCT dev)   AS n_dev,
    count(DISTINCT cell_id) AS n_cell
FROM rebuild2._tmp_bs_gps
GROUP BY op, tech, lac, bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_cnt(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_cnt;
