SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 2: Cell GPS 校验（dim_cell_refined）
-- 提取 Cell GPS 中心点，与 BS 中心比较，标记异常
-- ============================================================

-- 2.1 提取可信 LAC 范围内的 GPS 有效记录（Cell 粒度）
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps;
CREATE TABLE rebuild2._tmp_cell_gps AS
SELECT
    l."运营商编码"  AS op,
    l."标准制式"    AS tech,
    l."LAC"::text   AS lac,
    l."CellID"      AS cell_id,
    l."基站ID"      AS bs_id,
    l."设备标识"    AS dev,
    l."经度"        AS lon,
    l."纬度"        AS lat
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
   AND l."标准制式"   = t.tech_norm
   AND l."LAC"        = t.lac::bigint
WHERE l."GPS有效" = true
  AND l."经度" BETWEEN 73 AND 135
  AND l."纬度" BETWEEN 3 AND 54;

CREATE INDEX ON rebuild2._tmp_cell_gps(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_gps;

-- 2.2 计算 Cell GPS 中心点（分箱中位数，无信号加权）
DROP TABLE IF EXISTS rebuild2._tmp_cell_center;
CREATE TABLE rebuild2._tmp_cell_center AS
SELECT
    op, tech, lac, cell_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lon * 10000)::int)
        / 10000.0 AS clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lat * 10000)::int)
        / 10000.0 AS clat,
    count(*)              AS gps_count,
    count(DISTINCT dev)   AS gps_device_count
FROM rebuild2._tmp_cell_gps
GROUP BY op, tech, lac, cell_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_center(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_center;

-- 2.3 计算 Cell 中心到 BS 中心的距离，并标记异常
DROP TABLE IF EXISTS rebuild2._tmp_cell_dist;
CREATE TABLE rebuild2._tmp_cell_dist AS
SELECT
    cc.op, cc.tech, cc.lac, cc.cell_id,
    cc.clon, cc.clat, cc.gps_count, cc.gps_device_count,
    br.gps_center_lon  AS bs_lon,
    br.gps_center_lat  AS bs_lat,
    br.gps_quality     AS bs_gps_quality,
    CASE
        WHEN br.gps_center_lon IS NOT NULL THEN
            ROUND(SQRT(
                POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                POWER((cc.clat - br.gps_center_lat) * 111000, 2)
            )::numeric, 1)
        ELSE NULL
    END AS dist_to_bs_m,
    CASE
        WHEN br.gps_center_lon IS NULL THEN false
        WHEN cc.tech LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 1000 THEN true
        WHEN cc.tech NOT LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 2000 THEN true
        ELSE false
    END AS gps_anomaly,
    CASE
        WHEN br.gps_center_lon IS NULL THEN NULL
        WHEN cc.tech LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 1000
            THEN 'cell_to_bs_dist>1000m(5G)'
        WHEN cc.tech NOT LIKE '%5G%' AND
            SQRT(POWER((cc.clon - br.gps_center_lon) * 85300, 2) +
                 POWER((cc.clat - br.gps_center_lat) * 111000, 2)) > 2000
            THEN 'cell_to_bs_dist>2000m(non5G)'
        ELSE NULL
    END AS gps_anomaly_reason
FROM rebuild2._tmp_cell_center cc
LEFT JOIN rebuild2.dim_bs_refined br
    ON cc.op   = br.operator_code
   AND cc.tech = br.tech_norm
   AND cc.lac  = br.lac
   AND (SELECT bs_id FROM rebuild2.dim_cell_stats
        WHERE operator_code = cc.op AND tech_norm = cc.tech
          AND lac = cc.lac AND cell_id = cc.cell_id LIMIT 1)
       = br.bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_dist(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_dist;

-- 2.4 组装 dim_cell_refined（join dim_cell_stats 获取完整字段）
DROP TABLE IF EXISTS rebuild2.dim_cell_refined;
CREATE TABLE rebuild2.dim_cell_refined AS
SELECT
    cs.operator_code,
    cs.operator_cn,
    cs.tech_norm,
    cs.lac,
    cs.cell_id,
    cs.bs_id,
    cs.sector_id,
    cs.record_count,
    cs.distinct_device_count,
    cs.active_days,
    COALESCE(cd.clon, cs.gps_center_lon)     AS gps_center_lon,
    COALESCE(cd.clat, cs.gps_center_lat)     AS gps_center_lat,
    COALESCE(cd.gps_count, cs.valid_gps_count) AS gps_count,
    COALESCE(cd.gps_device_count, 0)         AS gps_device_count,
    cd.dist_to_bs_m,
    COALESCE(cd.gps_anomaly, false)          AS gps_anomaly,
    cd.gps_anomaly_reason,
    COALESCE(cd.bs_gps_quality,
        (SELECT gps_quality FROM rebuild2.dim_bs_refined br
         WHERE br.operator_code = cs.operator_code
           AND br.tech_norm     = cs.tech_norm
           AND br.lac           = cs.lac
           AND br.bs_id         = cs.bs_id LIMIT 1)
    )                                        AS bs_gps_quality,
    now()                                    AS created_at
FROM rebuild2.dim_cell_stats cs
LEFT JOIN rebuild2._tmp_cell_dist cd
    ON cs.operator_code = cd.op
   AND cs.tech_norm     = cd.tech
   AND cs.lac           = cd.lac
   AND cs.cell_id       = cd.cell_id
ORDER BY cs.record_count DESC;

CREATE INDEX ON rebuild2.dim_cell_refined(operator_code, tech_norm, lac, cell_id);
CREATE INDEX ON rebuild2.dim_cell_refined(operator_code, tech_norm, lac, bs_id);
CREATE INDEX ON rebuild2.dim_cell_refined(gps_anomaly);
CREATE INDEX ON rebuild2.dim_cell_refined(bs_gps_quality);

-- 清理临时表
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps;
DROP TABLE IF EXISTS rebuild2._tmp_cell_center;
DROP TABLE IF EXISTS rebuild2._tmp_cell_dist;

SELECT 'Step 2 完成: dim_cell_refined 已创建' AS status;
