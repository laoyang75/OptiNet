SET statement_timeout = 0;
SET work_mem = '1024MB';

-- STEP 6.5：对 l0_gps 也执行 ANALYZE
ANALYZE rebuild2.l0_gps;
ANALYZE rebuild2.l0_lac;

-- STEP 7：更新统计缓存 l0_gps
DELETE FROM rebuild2_meta.l0_stats_cache WHERE table_name IN ('l0_gps', 'l0_lac');

-- l0_gps summary
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_gps', 'summary', 'all', jsonb_build_object(
    'total', count(*),
    'records', count(DISTINCT "原始记录ID"),
    'has_cellid', count(*) FILTER (WHERE "有CellID"),
    'gps_valid', count(*) FILTER (WHERE "GPS有效"),
    'has_coord', count(*) FILTER (WHERE "经度" IS NOT NULL),
    'has_rsrp', count(*) FILTER (WHERE "RSRP" IS NOT NULL),
    'has_dbm', count(*) FILTER (WHERE "Dbm" IS NOT NULL)
) FROM rebuild2.l0_gps;

-- l0_gps by_origin_tech
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_gps', 'by_origin_tech', "Cell来源" || '|' || "标准制式",
  jsonb_build_object('cell_origin', "Cell来源", 'tech_norm', "标准制式", 'cnt', count(*))
FROM rebuild2.l0_gps GROUP BY "Cell来源", "标准制式";

-- l0_gps by_operator
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_gps', 'by_operator', COALESCE("运营商中文", 'NULL'),
  jsonb_build_object('operator_cn', "运营商中文", 'cnt', count(*))
FROM rebuild2.l0_gps WHERE "运营商编码" IS NOT NULL GROUP BY "运营商中文";

-- l0_gps field_quality
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_gps', 'field_quality', 'all', jsonb_build_object(
    'total', count(*),
    'rsrp_null', round(count(*) FILTER (WHERE "RSRP" IS NULL)::numeric / count(*), 4),
    'rsrq_null', round(count(*) FILTER (WHERE "RSRQ" IS NULL)::numeric / count(*), 4),
    'sinr_null', round(count(*) FILTER (WHERE "SINR" IS NULL)::numeric / count(*), 4),
    'rssi_null', round(count(*) FILTER (WHERE "RSSI" IS NULL)::numeric / count(*), 4),
    'dbm_null', round(count(*) FILTER (WHERE "Dbm" IS NULL)::numeric / count(*), 4),
    'asu_null', round(count(*) FILTER (WHERE "ASU等级" IS NULL)::numeric / count(*), 4),
    'level_null', round(count(*) FILTER (WHERE "信号等级" IS NULL)::numeric / count(*), 4),
    'operator_null', round(count(*) FILTER (WHERE "运营商编码" IS NULL)::numeric / count(*), 4),
    'lac_null', round(count(*) FILTER (WHERE "LAC" IS NULL)::numeric / count(*), 4),
    'cellid_null', round(count(*) FILTER (WHERE "CellID" IS NULL)::numeric / count(*), 4),
    'gps_null', round(count(*) FILTER (WHERE "经度" IS NULL)::numeric / count(*), 4),
    'ts_null', round(count(*) FILTER (WHERE "上报时间" IS NULL)::numeric / count(*), 4),
    'cell_ts_null', round(count(*) FILTER (WHERE "基站时间" IS NULL)::numeric / count(*), 4)
) FROM rebuild2.l0_gps;


-- l0_lac summary
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_lac', 'summary', 'all', jsonb_build_object(
    'total', count(*),
    'records', count(DISTINCT "原始记录ID"),
    'has_cellid', count(*) FILTER (WHERE "有CellID"),
    'gps_valid', count(*) FILTER (WHERE "GPS有效"),
    'has_coord', count(*) FILTER (WHERE "经度" IS NOT NULL),
    'has_rsrp', count(*) FILTER (WHERE "RSRP" IS NOT NULL),
    'has_dbm', count(*) FILTER (WHERE "Dbm" IS NOT NULL)
) FROM rebuild2.l0_lac;

-- l0_lac by_origin_tech
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_lac', 'by_origin_tech', "Cell来源" || '|' || "标准制式",
  jsonb_build_object('cell_origin', "Cell来源", 'tech_norm', "标准制式", 'cnt', count(*))
FROM rebuild2.l0_lac GROUP BY "Cell来源", "标准制式";

-- l0_lac by_operator
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_lac', 'by_operator', COALESCE("运营商中文", 'NULL'),
  jsonb_build_object('operator_cn', "运营商中文", 'cnt', count(*))
FROM rebuild2.l0_lac WHERE "运营商编码" IS NOT NULL GROUP BY "运营商中文";

-- l0_lac field_quality
INSERT INTO rebuild2_meta.l0_stats_cache (table_name, stat_type, stat_key, stat_value)
SELECT 'l0_lac', 'field_quality', 'all', jsonb_build_object(
    'total', count(*),
    'rsrp_null', round(count(*) FILTER (WHERE "RSRP" IS NULL)::numeric / count(*), 4),
    'rsrq_null', round(count(*) FILTER (WHERE "RSRQ" IS NULL)::numeric / count(*), 4),
    'sinr_null', round(count(*) FILTER (WHERE "SINR" IS NULL)::numeric / count(*), 4),
    'rssi_null', round(count(*) FILTER (WHERE "RSSI" IS NULL)::numeric / count(*), 4),
    'dbm_null', round(count(*) FILTER (WHERE "Dbm" IS NULL)::numeric / count(*), 4),
    'asu_null', round(count(*) FILTER (WHERE "ASU等级" IS NULL)::numeric / count(*), 4),
    'level_null', round(count(*) FILTER (WHERE "信号等级" IS NULL)::numeric / count(*), 4),
    'operator_null', round(count(*) FILTER (WHERE "运营商编码" IS NULL)::numeric / count(*), 4),
    'lac_null', round(count(*) FILTER (WHERE "LAC" IS NULL)::numeric / count(*), 4),
    'cellid_null', round(count(*) FILTER (WHERE "CellID" IS NULL)::numeric / count(*), 4),
    'gps_null', round(count(*) FILTER (WHERE "经度" IS NULL)::numeric / count(*), 4),
    'ts_null', round(count(*) FILTER (WHERE "上报时间" IS NULL)::numeric / count(*), 4),
    'cell_ts_null', round(count(*) FILTER (WHERE "基站时间" IS NULL)::numeric / count(*), 4)
) FROM rebuild2.l0_lac;
