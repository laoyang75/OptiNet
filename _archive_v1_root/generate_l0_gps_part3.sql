SET statement_timeout = 0;
SET work_mem = '256MB';

DROP TABLE IF EXISTS rebuild2.l0_gps;
CREATE TABLE rebuild2.l0_gps AS
WITH merged AS (
  SELECT * FROM rebuild2.l0_gps_ci
  UNION ALL
  SELECT * FROM rebuild2.l0_gps_ss1
),
-- 删除规则：主服务无 CellID
filtered AS (
  SELECT * FROM merged
  WHERE NOT (cell_origin = 'cell_infos' AND is_connected = 1
    AND (cell_id_dec IS NULL OR cell_id_dec = 0 OR cell_id_dec = 268435455))
),
-- 清洗 + 派生
cleaned AS (
  SELECT
    row_number() OVER () AS "L0行ID",
    record_id AS "原始记录ID",
    data_source AS "数据来源",
    data_source_detail AS "来源明细",
    cell_origin AS "Cell来源",
    cell_block_source AS "基站信息来源",
    is_connected AS "是否连接",

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
    CASE
      WHEN lac_dec = 0 THEN NULL
      WHEN lac_dec IN (65534, 65535) AND tech_norm = '4G' THEN NULL
      WHEN lac_dec = 268435455 THEN NULL
      ELSE lac_dec
    END AS "LAC",

    -- CellID 清洗
    CASE
      WHEN cell_id_dec = 0 THEN NULL
      WHEN cell_id_dec = 268435455 AND tech_norm = '5G' THEN NULL
      ELSE cell_id_dec
    END AS "CellID",

    -- 基站ID / 扇区ID（基于清洗后的 CellID）
    CASE
      WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0
        AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
        AND tech_norm = '5G' THEN cell_id_dec / 4096
      WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0
        AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
        THEN cell_id_dec / 256
    END AS "基站ID",
    CASE
      WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0
        AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
        AND tech_norm = '5G' THEN cell_id_dec % 4096
      WHEN cell_id_dec IS NOT NULL AND cell_id_dec != 0
        AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')
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
    sig_csi_rsrp AS "CSI_RSRP", sig_csi_rsrq AS "CSI_RSRQ",
    sig_csi_sinr AS "CSI_SINR", sig_cqi AS "CQI",

    -- 时间统一
    ts_raw AS "上报时间原始",
    CASE WHEN ts_raw ~ '^\d{4}-' THEN ts_raw::timestamptz ELSE NULL END AS "上报时间",
    CASE
      WHEN cell_origin = 'ss1' AND cell_ts_raw ~ '^\d{10}$' THEN to_timestamp(cell_ts_raw::bigint)
      ELSE NULL
    END AS "基站时间",
    cell_ts_raw AS "基站时间原始",
    gps_ts_raw AS "GPS上报时间",
    CASE WHEN gps_ts_raw ~ '^\d{13}$' THEN to_timestamp(gps_ts_raw::bigint / 1000.0) ELSE NULL END AS "GPS时间",

    gps_info_type AS "GPS类型",
    gps_valid AS "GPS有效",
    lon_raw AS "经度", lat_raw AS "纬度",
    gps_filled_from AS "GPS补齐来源",

    (cell_id_dec IS NOT NULL AND cell_id_dec != 0
      AND NOT (cell_id_dec = 268435455 AND tech_norm = '5G')) AS "有CellID",
    fill_time_delta_ms AS "补齐时间差",

    did AS "设备标识", ip AS "IP地址", plmn_main AS "主卡运营商",
    brand AS "品牌", model AS "机型", sdk_ver AS "SDK版本",
    oaid AS "OAID", pkg_name AS "应用包名",
    wifi_name AS "WiFi名称", wifi_mac AS "WiFi_MAC",
    cpu_info AS "CPU信息", pressure AS "气压"
  FROM filtered
)
SELECT * FROM cleaned;

-- 清理中间表
DROP TABLE IF EXISTS rebuild2.l0_gps_ci;
DROP TABLE IF EXISTS rebuild2.l0_gps_ss1;
