SET statement_timeout = 0;
SET work_mem = '512MB';
\timing on

-- STEP 5：第一轮中心点（分箱中位数）
DROP TABLE IF EXISTS rebuild2._tmp_bs_c1;
CREATE TABLE rebuild2._tmp_bs_c1 AS
SELECT op, tech, lac, bs_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lon * 10000)::int)
        / 10000.0 AS clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lat * 10000)::int)
        / 10000.0 AS clat,
    count(*) AS n_seeds
FROM rebuild2._tmp_bs_seeds
GROUP BY op, tech, lac, bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_c1(op, tech, lac, bs_id);

-- STEP 6：异常剔除 + 第二轮中心点
DROP TABLE IF EXISTS rebuild2._tmp_bs_c2;
CREATE TABLE rebuild2._tmp_bs_c2 AS
WITH seed_dist AS (
    SELECT s.op, s.tech, s.lac, s.bs_id, s.lon, s.lat,
        SQRT(
            POWER((s.lon - c.clon) * 85300, 2) +
            POWER((s.lat - c.clat) * 111000, 2)
        ) AS dist_m
    FROM rebuild2._tmp_bs_seeds s
    JOIN rebuild2._tmp_bs_c1 c USING (op, tech, lac, bs_id)
),
bs_outlier AS (
    SELECT op, tech, lac, bs_id,
        (MAX(dist_m) > 2500) AS has_outlier
    FROM seed_dist
    GROUP BY op, tech, lac, bs_id
)
SELECT
    sd.op, sd.tech, sd.lac, sd.bs_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(sd.lon * 10000)::int)
        / 10000.0 AS clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(sd.lat * 10000)::int)
        / 10000.0 AS clat,
    count(*) AS n_final,
    bool_or(bo.has_outlier) AS had_outlier
FROM seed_dist sd
JOIN bs_outlier bo USING (op, tech, lac, bs_id)
WHERE NOT bo.has_outlier OR sd.dist_m <= 2500
GROUP BY sd.op, sd.tech, sd.lac, sd.bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_c2(op, tech, lac, bs_id);

-- STEP 7：距离指标
DROP TABLE IF EXISTS rebuild2._tmp_bs_dist;
CREATE TABLE rebuild2._tmp_bs_dist AS
WITH
outlier_flag AS (
    SELECT c1.op, c1.tech, c1.lac, c1.bs_id,
        (c1.n_seeds > c2.n_final) AS had_cut
    FROM rebuild2._tmp_bs_c1 c1
    JOIN rebuild2._tmp_bs_c2 c2 USING (op, tech, lac, bs_id)
),
pass1_dist AS (
    SELECT s.op, s.tech, s.lac, s.bs_id, s.lon, s.lat,
        SQRT(
            POWER((s.lon - c1.clon) * 85300, 2) +
            POWER((s.lat - c1.clat) * 111000, 2)
        ) AS dist1_m
    FROM rebuild2._tmp_bs_seeds s
    JOIN rebuild2._tmp_bs_c1 c1 USING (op, tech, lac, bs_id)
),
kept AS (
    SELECT pd.op, pd.tech, pd.lac, pd.bs_id, pd.lon, pd.lat
    FROM pass1_dist pd
    LEFT JOIN outlier_flag o USING (op, tech, lac, bs_id)
    WHERE COALESCE(NOT o.had_cut, true) OR pd.dist1_m <= 2500
),
final_dist AS (
    SELECT k.op, k.tech, k.lac, k.bs_id,
        SQRT(
            POWER((k.lon - c2.clon) * 85300, 2) +
            POWER((k.lat - c2.clat) * 111000, 2)
        ) AS dist_m
    FROM kept k
    JOIN rebuild2._tmp_bs_c2 c2 USING (op, tech, lac, bs_id)
)
SELECT op, tech, lac, bs_id,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dist_m)::numeric, 1) AS p50_m,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY dist_m)::numeric, 1) AS p90_m,
    ROUND(MAX(dist_m)::numeric, 1) AS max_m
FROM final_dist
GROUP BY op, tech, lac, bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_dist(op, tech, lac, bs_id);

-- STEP 8：组装 dim_bs_refined
DROP TABLE IF EXISTS rebuild2.dim_bs_refined;
CREATE TABLE rebuild2.dim_bs_refined AS
SELECT
    b.operator_code, b.operator_cn, b.tech_norm, b.lac, b.bs_id,
    b.cell_count, b.record_count, b.distinct_device_count, b.max_active_days,
    b.first_seen, b.last_seen,
    -- 精算 GPS 中心点
    c.clon                           AS gps_center_lon,
    c.clat                           AS gps_center_lat,
    c.n_final                        AS seed_count,
    COALESCE(c.had_outlier, false)   AS had_outlier_removal,
    -- GPS 统计
    COALESCE(cnt.n, 0)               AS total_gps_points,
    COALESCE(cnt.n_dev, 0)           AS distinct_gps_devices,
    COALESCE(cnt.n_cell, 0)          AS cells_with_gps,
    -- 距离指标
    d.p50_m                          AS gps_p50_dist_m,
    d.p90_m                          AS gps_p90_dist_m,
    d.max_m                          AS gps_max_dist_m,
    -- GPS 质量分级
    CASE
        WHEN COALESCE(cnt.n_cell, 0) >= 2 THEN 'Usable'
        WHEN COALESCE(cnt.n_cell, 0) = 1  THEN 'Risk'
        ELSE 'Unusable'
    END                              AS gps_quality,
    -- Phase 2 旧中心点（对比用）
    b.gps_center_lon                 AS old_center_lon,
    b.gps_center_lat                 AS old_center_lat,
    b.valid_gps_count                AS old_valid_gps_count,
    now()                            AS created_at
FROM rebuild2.dim_bs_stats b
LEFT JOIN rebuild2._tmp_bs_cnt  cnt ON b.operator_code = cnt.op  AND b.tech_norm = cnt.tech AND b.lac = cnt.lac AND b.bs_id = cnt.bs_id
LEFT JOIN rebuild2._tmp_bs_c2   c   ON b.operator_code = c.op    AND b.tech_norm = c.tech   AND b.lac = c.lac   AND b.bs_id = c.bs_id
LEFT JOIN rebuild2._tmp_bs_dist d   ON b.operator_code = d.op    AND b.tech_norm = d.tech   AND b.lac = d.lac   AND b.bs_id = d.bs_id
ORDER BY b.record_count DESC;

CREATE INDEX ON rebuild2.dim_bs_refined(operator_code, tech_norm, lac, bs_id);
CREATE INDEX ON rebuild2.dim_bs_refined(gps_quality);
