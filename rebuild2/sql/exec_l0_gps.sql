SET statement_timeout = 0;
SET work_mem = '1024MB';

-- STEP 2: 重建 l0_gps — cell_infos 部分
DROP TABLE IF EXISTS rebuild2.l0_gps_ci;
CREATE TABLE rebuild2.l0_gps_ci AS
WITH base AS (
  SELECT
    "记录数唯一标识" AS record_id,
    "数据来源dna或daa" AS data_source_detail,
    did, ts, ip, pkg_name, wifi_name, wifi_mac, sdk_ver,
    "gps上报时间" AS gps_ts_raw,
    "主卡运营商id" AS plmn_main,
    "品牌" AS brand, "机型" AS model,
    gps_info_type,
    "原始上报gps" AS gps_raw,
    cpu_info, "压力" AS pressure, oaid,
    NULLIF(btrim("cell_infos"), '')::jsonb AS ci_json
  FROM legacy."网优项目_gps定位北京明细数据_20251201_20251207"
  WHERE "cell_infos" IS NOT NULL AND length("cell_infos") > 5
),
expanded AS (
  SELECT b.*, e.key AS ci_key, e.value AS cell FROM base b, jsonb_each(b.ci_json) e
  -- 只保留主服务基站（is_connected=1），去掉邻区（is_connected=2）
  WHERE (e.value->>'isConnected')::int = 1
)
SELECT
  record_id, 'sdk' AS data_source, data_source_detail,
  'cell_infos' AS cell_origin,
  lower(cell->>'type') AS tech_raw,
  CASE lower(cell->>'type')
    WHEN 'lte' THEN '4G' WHEN 'nr' THEN '5G' WHEN 'gsm' THEN '2G' WHEN 'wcdma' THEN '3G'
    ELSE lower(cell->>'type')
  END AS tech_norm,
  COALESCE(cell->'cell_identity'->>'mno',
    (cell->'cell_identity'->>'mccString')||(cell->'cell_identity'->>'mncString')
  ) AS operator_id_raw,
  COALESCE(cell->'cell_identity'->>'Tac', cell->'cell_identity'->>'tac',
    cell->'cell_identity'->>'lac', cell->'cell_identity'->>'Lac')::bigint AS lac_dec,
  COALESCE(cell->'cell_identity'->>'Ci', cell->'cell_identity'->>'Nci',
    cell->'cell_identity'->>'nci', cell->'cell_identity'->>'cid')::bigint AS cell_id_dec,
  (cell->'cell_identity'->>'Pci')::int AS pci,
  COALESCE(cell->'cell_identity'->>'Earfcn', cell->'cell_identity'->>'earfcn',
    cell->'cell_identity'->>'ChannelNumber', cell->'cell_identity'->>'arfcn',
    cell->'cell_identity'->>'uarfcn')::int AS freq_channel,
  (cell->'cell_identity'->>'Bwth')::int AS bandwidth,
  COALESCE((cell->'signal_strength'->>'rsrp')::int, (cell->'signal_strength'->>'SsRsrp')::int) AS sig_rsrp,
  COALESCE((cell->'signal_strength'->>'rsrq')::int, (cell->'signal_strength'->>'SsRsrq')::int) AS sig_rsrq,
  COALESCE((cell->'signal_strength'->>'rssnr')::int, (cell->'signal_strength'->>'SsSinr')::int) AS sig_sinr,
  (cell->'signal_strength'->>'rssi')::int AS sig_rssi,
  (cell->'signal_strength'->>'Dbm')::int AS sig_dbm,
  (cell->'signal_strength'->>'AsuLevel')::int AS sig_asu_level,
  (cell->'signal_strength'->>'Level')::int AS sig_level,
  NULL::int AS sig_ss,
  (cell->'signal_strength'->>'TimingAdvance')::int AS timing_advance,
  (cell->'signal_strength'->>'CsiRsrp')::int AS sig_csi_rsrp,
  (cell->'signal_strength'->>'CsiRsrq')::int AS sig_csi_rsrq,
  (cell->'signal_strength'->>'CsiSinr')::int AS sig_csi_sinr,
  (cell->'signal_strength'->>'cqi')::int AS sig_cqi,
  ts AS ts_raw,
  CASE WHEN ts ~ '^\d{4}-' THEN ts::timestamptz ELSE NULL END AS ts_std,
  cell->>'timeStamp' AS cell_ts_raw,
  gps_ts_raw, gps_info_type,
  CASE WHEN gps_info_type IN ('gps','1') THEN true ELSE false END AS gps_valid,
  CASE WHEN gps_raw IS NOT NULL AND gps_raw LIKE '%,%' THEN split_part(gps_raw,',',1)::float8 END AS lon_raw,
  CASE WHEN gps_raw IS NOT NULL AND gps_raw LIKE '%,%' THEN split_part(gps_raw,',',2)::float8 END AS lat_raw,
  'raw_gps' AS gps_filled_from,
  NULL::bigint AS fill_time_delta_ms,
  'own'::text AS cell_block_source,
  did, ip, plmn_main, brand, model, sdk_ver, oaid,
  pkg_name,
  CASE WHEN wifi_name IN ('<unknown ssid>', 'unknown', '') THEN NULL ELSE wifi_name END AS wifi_name,
  CASE WHEN wifi_mac IN ('02:00:00:00:00:00', '00:00:00:00:00:00', '') THEN NULL ELSE wifi_mac END AS wifi_mac,
  cpu_info, pressure
FROM expanded
WHERE COALESCE(cell->'cell_identity'->>'Ci', cell->'cell_identity'->>'Nci',
  cell->'cell_identity'->>'nci', cell->'cell_identity'->>'cid') IS NOT NULL;

-- STEP 3：重建 l0_gps — ss1 部分（信号按制式匹配）
DROP TABLE IF EXISTS rebuild2.l0_gps_ss1;
CREATE TABLE rebuild2.l0_gps_ss1 AS
WITH base AS (
  SELECT
    "记录数唯一标识" AS record_id,
    "数据来源dna或daa" AS data_source_detail,
    did, ts, ip, pkg_name, wifi_name, wifi_mac, sdk_ver,
    "gps上报时间" AS gps_ts_raw,
    "主卡运营商id" AS plmn_main,
    "品牌" AS brand, "机型" AS model,
    gps_info_type, "原始上报gps" AS gps_raw,
    cpu_info, "压力" AS pressure, oaid,
    NULLIF(btrim(ss1), '') AS ss1_text
  FROM legacy."网优项目_gps定位北京明细数据_20251201_20251207"
  WHERE ss1 IS NOT NULL AND length(ss1) > 5
),
numbered_groups AS (
  SELECT b.*, grp, grp_idx
  FROM base b,
  LATERAL unnest(string_to_array(trim(trailing ';' FROM ss1_text), ';'))
    WITH ORDINALITY AS t(grp, grp_idx)
),
elements AS (
  SELECT ng.*,
    split_part(grp, '&', 1) AS sig_block,
    split_part(grp, '&', 2) AS ts_block,
    split_part(grp, '&', 3) AS gps_block,
    split_part(grp, '&', 4) AS cell_block
  FROM numbered_groups ng
),
with_carry AS (
  SELECT e.*,
    CASE WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[ln]' THEN cell_block ELSE NULL END AS cb_own,
    CASE WHEN cell_block = '1' THEN 'inherited' WHEN cell_block NOT IN ('', '0', '1') AND cell_block ~ '^[ln]' THEN 'own' ELSE 'none' END AS cb_source
  FROM elements e
),
inherited AS (
  SELECT w.*,
    COALESCE(cb_own, max(cb_own) OVER (PARTITION BY record_id ORDER BY grp_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)) AS cell_block_resolved
  FROM with_carry w
),
-- 拆基站
cells AS (
  SELECT h.*, unnest(string_to_array(rtrim(cell_block_resolved, '+'), '+')) AS cell_entry
  FROM inherited h
  WHERE cell_block_resolved IS NOT NULL AND cell_block_resolved != ''
),
parsed_cells AS (
  SELECT c.*,
    left(cell_entry, 1) AS cell_tech,
    split_part(cell_entry, ',', 2) AS cid_str,
    split_part(cell_entry, ',', 3) AS lac_str,
    split_part(cell_entry, ',', 4) AS plmn_str
  FROM cells c
  WHERE length(cell_entry) > 2 AND cell_entry ~ '^[lnge],'
    AND split_part(cell_entry, ',', 2) != '-1'
    AND split_part(cell_entry, ',', 2) != ''
),
-- 拆信号（同组同制式匹配）
parsed_sigs AS (
  SELECT record_id, grp_idx,
    left(sig_entry, 1) AS sig_tech,
    split_part(sig_entry, ',', 2) AS ss_val,
    split_part(sig_entry, ',', 3) AS rsrp_val,
    split_part(sig_entry, ',', 4) AS rsrq_val,
    split_part(sig_entry, ',', 5) AS sinr_val
  FROM (
    SELECT h.record_id, h.grp_idx, unnest(string_to_array(rtrim(h.sig_block, '+'), '+')) AS sig_entry
    FROM inherited h
    WHERE h.sig_block IS NOT NULL AND h.sig_block != ''
  ) sub
  WHERE length(sig_entry) > 2 AND sig_entry ~ '^[lng]'
),
-- 按制式匹配
matched AS (
  SELECT
    c.record_id, c.grp_idx, c.cb_source, c.ts_block, c.gps_block,
    c.cell_tech AS tech_raw, c.cid_str, c.lac_str, c.plmn_str,
    s.ss_val, s.rsrp_val, s.rsrq_val, s.sinr_val,
    c.data_source_detail, c.did, c.ts, c.ip, c.pkg_name, c.wifi_name, c.wifi_mac,
    c.sdk_ver, c.gps_ts_raw, c.plmn_main, c.brand, c.model, c.gps_info_type,
    c.gps_raw, c.cpu_info, c.pressure, c.oaid
  FROM parsed_cells c
  LEFT JOIN parsed_sigs s ON s.record_id = c.record_id AND s.grp_idx = c.grp_idx AND s.sig_tech = c.cell_tech
)
SELECT
  record_id, 'sdk' AS data_source, data_source_detail,
  'ss1' AS cell_origin,
  tech_raw,
  CASE tech_raw WHEN 'l' THEN '4G' WHEN 'n' THEN '5G' WHEN 'g' THEN '2G' ELSE tech_raw END AS tech_norm,
  NULLIF(plmn_str, '') AS operator_id_raw,
  CASE WHEN lac_str ~ '^\d+$' THEN lac_str::bigint END AS lac_dec,
  CASE WHEN cid_str ~ '^\d+$' THEN cid_str::bigint END AS cell_id_dec,
  NULL::int AS pci, NULL::int AS freq_channel, NULL::int AS bandwidth,
  -- 信号：-1 视为无效
  CASE WHEN rsrp_val ~ '^-?\d+$' AND rsrp_val != '-1' THEN rsrp_val::int END AS sig_rsrp,
  CASE WHEN rsrq_val ~ '^-?\d+$' AND rsrq_val != '-1' THEN rsrq_val::int END AS sig_rsrq,
  CASE WHEN sinr_val ~ '^-?\d+$' AND sinr_val != '-1' THEN sinr_val::int END AS sig_sinr,
  NULL::int AS sig_rssi, NULL::int AS sig_dbm, NULL::int AS sig_asu_level,
  NULL::int AS sig_level,
  CASE WHEN ss_val ~ '^-?\d+$' AND ss_val != '-1' THEN ss_val::int END AS sig_ss,
  NULL::int AS timing_advance,
  NULL::int AS sig_csi_rsrp, NULL::int AS sig_csi_rsrq, NULL::int AS sig_csi_sinr, NULL::int AS sig_cqi,
  ts AS ts_raw,
  CASE WHEN ts ~ '^\d{4}-' THEN ts::timestamptz ELSE NULL END AS ts_std,
  ts_block AS cell_ts_raw,
  gps_ts_raw, gps_info_type,
  CASE WHEN gps_block != '0' AND gps_block ~ '^\d+\.\d+,\d+\.\d+' THEN true ELSE false END AS gps_valid,
  CASE WHEN gps_block ~ '^\d+\.\d+,' THEN split_part(gps_block, ',', 1)::float8 END AS lon_raw,
  CASE WHEN gps_block ~ '^\d+\.\d+,\d+\.\d+' THEN split_part(gps_block, ',', 2)::float8 END AS lat_raw,
  CASE WHEN gps_block != '0' AND gps_block ~ '^\d+\.\d+,' THEN 'ss1_own' ELSE 'none' END AS gps_filled_from,
  NULL::bigint AS fill_time_delta_ms,
  cb_source AS cell_block_source,
  did, ip, plmn_main, brand, model, sdk_ver, oaid,
  pkg_name,
  CASE WHEN wifi_name IN ('<unknown ssid>', 'unknown', '') THEN NULL ELSE wifi_name END AS wifi_name,
  CASE WHEN wifi_mac IN ('02:00:00:00:00:00', '00:00:00:00:00:00', '') THEN NULL ELSE wifi_mac END AS wifi_mac,
  cpu_info, pressure
FROM matched;

-- STEP 4：合并 + ODS 清洗 → 最终 l0_gps
DROP TABLE IF EXISTS rebuild2.l0_gps_new;
CREATE TABLE rebuild2.l0_gps_new AS
WITH merged AS (
  SELECT * FROM rebuild2.l0_gps_ci
  UNION ALL
  SELECT * FROM rebuild2.l0_gps_ss1
)
SELECT
  row_number() OVER () AS "L0行ID",
  record_id AS "原始记录ID",
  data_source AS "数据来源",
  data_source_detail AS "来源明细",
  cell_origin AS "Cell来源",
  cell_block_source AS "基站信息来源",
  tech_raw AS "原始制式",
  tech_norm AS "标准制式",
  -- 运营商清洗
  CASE
    WHEN operator_id_raw IN ('00000','0','000000','(null)(null)','') THEN NULL
    WHEN operator_id_raw NOT IN ('46000','46001','46002','46003','46005','46006','46007','46009','46011','46015','46020') THEN NULL
    ELSE operator_id_raw
  END AS "运营商编码",
  CASE operator_id_raw
    WHEN '46000' THEN '移动' WHEN '46002' THEN '移动' WHEN '46007' THEN '移动'
    WHEN '46001' THEN '联通' WHEN '46006' THEN '联通' WHEN '46009' THEN '联通'
    WHEN '46003' THEN '电信' WHEN '46005' THEN '电信' WHEN '46011' THEN '电信'
    WHEN '46015' THEN '广电' WHEN '46020' THEN '铁路' ELSE NULL
  END AS "运营商中文",
  -- LAC 清洗
  CASE WHEN lac_dec = 0 OR lac_dec IN (65534,65535) AND tech_norm = '4G' OR lac_dec = 268435455 THEN NULL ELSE lac_dec END AS "LAC",
  -- CellID 清洗
  CASE WHEN cell_id_dec = 0 OR (cell_id_dec = 268435455 AND tech_norm = '5G') THEN NULL ELSE cell_id_dec END AS "CellID",
  -- 基站ID/扇区ID
  CASE
    WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0 AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
      AND tech_norm = '5G' THEN cell_id_dec / 4096
    WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0 AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
      THEN cell_id_dec / 256
  END AS "基站ID",
  CASE
    WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0 AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
      AND tech_norm = '5G' THEN cell_id_dec % 4096
    WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0 AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
      THEN cell_id_dec % 256
  END AS "扇区ID",
  pci AS "PCI", freq_channel AS "频点号", bandwidth AS "带宽",
  -- 信号清洗
  CASE WHEN sig_rsrp > 0 OR sig_rsrp = 0 OR sig_rsrp < -156 THEN NULL ELSE sig_rsrp END AS "RSRP",
  CASE WHEN sig_rsrq > 10 OR sig_rsrq < -34 THEN NULL ELSE sig_rsrq END AS "RSRQ",
  CASE WHEN sig_sinr > 40 OR sig_sinr < -23 THEN NULL ELSE sig_sinr END AS "SINR",
  sig_rssi AS "RSSI",
  CASE WHEN sig_dbm > 0 OR sig_dbm = 0 THEN NULL ELSE sig_dbm END AS "Dbm",
  CASE WHEN sig_asu_level < 0 OR sig_asu_level > 99 THEN NULL ELSE sig_asu_level END AS "ASU等级",
  sig_level AS "信号等级",
  CASE WHEN sig_ss = 2147483647 OR sig_ss > 0 THEN NULL ELSE sig_ss END AS "SS原始值",
  CASE WHEN timing_advance > 63 OR timing_advance < 0 THEN NULL ELSE timing_advance END AS "时间提前量",
  sig_csi_rsrp AS "CSI_RSRP", sig_csi_rsrq AS "CSI_RSRQ", sig_csi_sinr AS "CSI_SINR", sig_cqi AS "CQI",
  -- 时间
  ts_raw AS "上报时间原始",
  CASE WHEN ts_raw ~ '^\d{4}-' THEN ts_raw::timestamptz ELSE NULL END AS "上报时间",
  CASE WHEN cell_origin = 'ss1' AND cell_ts_raw ~ '^\d{10}$' THEN to_timestamp(cell_ts_raw::bigint) ELSE NULL END AS "基站时间",
  cell_ts_raw AS "基站时间原始",
  gps_ts_raw AS "GPS上报时间",
  CASE WHEN gps_ts_raw ~ '^\d{13}$' THEN to_timestamp(gps_ts_raw::bigint / 1000.0) ELSE NULL END AS "GPS时间",
  gps_info_type AS "GPS类型", gps_valid AS "GPS有效",
  lon_raw AS "经度", lat_raw AS "纬度",
  gps_filled_from AS "GPS补齐来源",
  (cell_id_dec IS NOT NULL AND cell_id_dec != 0 AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')) AS "有CellID",
  fill_time_delta_ms AS "补齐时间差",
  did AS "设备标识", ip AS "IP地址", plmn_main AS "主卡运营商",
  brand AS "品牌", model AS "机型", sdk_ver AS "SDK版本",
  oaid AS "OAID", pkg_name AS "应用包名",
  wifi_name AS "WiFi名称", wifi_mac AS "WiFi_MAC",
  cpu_info AS "CPU信息", pressure AS "气压"
FROM merged
-- 排除 CellID 无效行
WHERE cell_id_dec IS NOT NULL AND cell_id_dec != 0
  AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G');

-- STEP 5：替换旧表 + 建索引
DROP TABLE IF EXISTS rebuild2.l0_gps;
ALTER TABLE rebuild2.l0_gps_new RENAME TO l0_gps;

CREATE INDEX idx_l0_gps_cellid ON rebuild2.l0_gps ("CellID") WHERE "CellID" IS NOT NULL;
CREATE INDEX idx_l0_gps_lac ON rebuild2.l0_gps ("LAC") WHERE "LAC" IS NOT NULL;
CREATE INDEX idx_l0_gps_bsid ON rebuild2.l0_gps ("基站ID") WHERE "基站ID" IS NOT NULL;
CREATE INDEX idx_l0_gps_operator_tech ON rebuild2.l0_gps ("运营商编码", "标准制式") WHERE "运营商编码" IS NOT NULL;
CREATE INDEX idx_l0_gps_record ON rebuild2.l0_gps ("原始记录ID");
CREATE INDEX idx_l0_gps_ts ON rebuild2.l0_gps ("上报时间") WHERE "上报时间" IS NOT NULL;

-- 更新统计信息
ANALYZE rebuild2.l0_gps;

-- 清理中间表
DROP TABLE IF EXISTS rebuild2.l0_gps_ci;
DROP TABLE IF EXISTS rebuild2.l0_gps_ss1;
