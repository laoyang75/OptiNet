SET statement_timeout = 0;
SET work_mem = '512MB';
\timing on

-- STEP 2：提取 GPS+RSRP 有效记录
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps;
CREATE TABLE rebuild2._tmp_bs_gps AS
SELECT
    l."运营商编码"  AS op,
    l."标准制式"    AS tech,
    l."LAC"::text   AS lac,
    l."基站ID"      AS bs_id,
    l."CellID"      AS cell_id,
    l."设备标识"    AS dev,
    l."经度"        AS lon,
    l."纬度"        AS lat,
    l."RSRP"        AS rsrp
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
   AND l."标准制式"   = t.tech_norm
   AND l."LAC"        = t.lac::bigint
WHERE l."GPS有效" = true
  AND l."经度" BETWEEN 73 AND 135
  AND l."纬度" BETWEEN 3 AND 54
  AND l."RSRP" IS NOT NULL
  AND l."RSRP" < 0
  AND l."RSRP" NOT IN (-1, -110);

CREATE INDEX ON rebuild2._tmp_bs_gps(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_gps;
