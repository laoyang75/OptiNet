SET statement_timeout = 0;
SET work_mem = '512MB';
\timing on

-- STEP 4：设备去重 + 信号加权选种
DROP TABLE IF EXISTS rebuild2._tmp_bs_seeds;
CREATE TABLE rebuild2._tmp_bs_seeds AS
WITH
-- >100 点 BS：每设备取 RSRP 最强的一条
deduped AS (
    SELECT DISTINCT ON (g.op, g.tech, g.lac, g.bs_id, g.dev)
        g.op, g.tech, g.lac, g.bs_id, g.lon, g.lat, g.rsrp
    FROM rebuild2._tmp_bs_gps g
    JOIN rebuild2._tmp_bs_cnt c USING (op, tech, lac, bs_id)
    WHERE c.n > 100
    ORDER BY g.op, g.tech, g.lac, g.bs_id, g.dev, g.rsrp DESC
),
-- 合并去重后 + 原始（≤100点）
all_pts AS (
    SELECT op, tech, lac, bs_id, lon, lat, rsrp FROM deduped
    UNION ALL
    SELECT g.op, g.tech, g.lac, g.bs_id, g.lon, g.lat, g.rsrp
    FROM rebuild2._tmp_bs_gps g
    JOIN rebuild2._tmp_bs_cnt c USING (op, tech, lac, bs_id)
    WHERE c.n <= 100
),
-- 按 RSRP 降序排名
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY op, tech, lac, bs_id ORDER BY rsrp DESC) AS rn,
        COUNT(*)     OVER (PARTITION BY op, tech, lac, bs_id) AS grp
    FROM all_pts
)
-- 选种：≥50→top50, ≥20→top20, ≥5→top80%, <5→全部
SELECT op, tech, lac, bs_id, lon, lat, rsrp
FROM ranked
WHERE CASE
    WHEN grp >= 50 THEN rn <= 50
    WHEN grp >= 20 THEN rn <= 20
    WHEN grp >= 5  THEN rn <= GREATEST(CEIL(grp * 0.8)::int, 1)
    ELSE true
END;

CREATE INDEX ON rebuild2._tmp_bs_seeds(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_seeds;
