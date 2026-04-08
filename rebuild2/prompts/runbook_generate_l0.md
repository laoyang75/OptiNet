# Runbook：生成 L0 数据

> 身份：**执行 Agent**
> 任务：从两张原始表分别生成 `rebuild2.l0_gps` 和 `rebuild2.l0_lac`
> 前置：Phase 1 字段治理已完成，清洗规则已确认

---

## 1. 环境信息

### 数据库
- **主机**：192.168.200.217
- **端口**：5433
- **库名**：ip_loc2
- **用户**：postgres
- **密码**：123456
- **DSN**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`

### SSH 服务器
- **地址**：192.168.200.217
- **用户**：root
- **密码**：111111

### PG17 是 Docker 部署
```bash
# 1. 先 SSH 到服务器
ssh root@192.168.200.217
# 密码：111111

# 2. 在服务器上连接 PG17
PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2

# 或从本地直连（不经过 SSH，但大数据量会慢）
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2
```

---

## 2. 执行流程

**三步走：MCP 小规模测试 → SSH 服务器全量执行 → MCP 检查结果**

### Step 0：用 MCP (PG17) 测试 SQL 片段

在执行全量之前，先用 MCP 工具（`mcp__PG17__execute_sql`）测试每段 SQL 的逻辑正确性。用 `LIMIT 100` 或 `TABLESAMPLE BERNOULLI(0.01)` 跑小规模验证。

### Step 1：SSH 到服务器执行全量 SQL

MCP 测试通过后，通过 SSH 连接到服务器用 `psql` 执行全量 SQL。原因：数据量大（GPS 表 2217 万行，解析后约 1.3 亿行），MCP 连接会超时。

```bash
# SSH 到服务器后用 psql 执行
PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2 -f /tmp/generate_l0.sql
```

或直接粘贴 SQL 块执行。

### Step 2：用 MCP 检查执行结果

全量执行完后，用 MCP 查行数、抽样验证、统计清洗影响。

---

## 3. 必须先读取

1. `rebuild2/prompts/phase1_field_governance.md` — 了解所有规则和逻辑
2. 数据库 `rebuild2_meta.ods_clean_rule` — 24 条清洗规则
3. 数据库 `rebuild2.l0_sample_10k` — 样本表结构（就是目标表的结构）

---

## 4. SQL 执行顺序

以下 SQL 要**按顺序**执行。先跑 GPS 表，再跑 LAC 表。每张表分 4 步。

### 4.1 准备

```sql
-- 取消超时限制（全量计算可能需要几十分钟）
SET statement_timeout = 0;
SET work_mem = '256MB';
```

### 4.2 生成 L0_gps — Step A：解析 cell_infos

```sql
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
)
SELECT
  record_id, 'sdk' AS data_source, data_source_detail,
  'cell_infos' AS cell_origin,
  (cell->>'isConnected')::int AS is_connected,
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
  CASE WHEN ts ~ '^\d{10,13}$' THEN to_timestamp(ts::bigint / 1000.0) ELSE NULL END AS ts_std,
  cell->>'timeStamp' AS cell_ts_raw,
  gps_ts_raw, gps_info_type,
  CASE WHEN gps_info_type IN ('gps','1') THEN true ELSE false END AS gps_valid,
  CASE WHEN gps_raw IS NOT NULL AND gps_raw LIKE '%,%' THEN split_part(gps_raw,',',1)::float8 END AS lon_raw,
  CASE WHEN gps_raw IS NOT NULL AND gps_raw LIKE '%,%' THEN split_part(gps_raw,',',2)::float8 END AS lat_raw,
  'raw_gps' AS gps_filled_from,
  NULL::bigint AS fill_time_delta_ms,
  'own'::text AS cell_block_source,
  did, ip, plmn_main, brand, model, sdk_ver, oaid,
  pkg_name, wifi_name, wifi_mac, cpu_info, pressure
FROM expanded;
```

**MCP 测试方法**：先在 MCP 中加 `LIMIT 1000` 到 base CTE 的 SELECT 末尾，跑通后再去服务器执行全量。

### 4.3 生成 L0_gps — Step B：解析 ss1

```sql
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
    CASE WHEN cell_block NOT IN ('', '0', '1') THEN cell_block ELSE NULL END AS cb_own,
    CASE
      WHEN cell_block NOT IN ('', '0', '1') THEN 'own'
      WHEN cell_block = '1' THEN 'inherited'
      ELSE 'none'
    END AS cb_source
  FROM elements e
),
inherited AS (
  SELECT w.*,
    COALESCE(
      cb_own,
      max(cb_own) OVER (PARTITION BY record_id ORDER BY grp_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    ) AS cell_block_resolved
  FROM with_carry w
),
cells AS (
  SELECT h.*, unnest(string_to_array(rtrim(cell_block_resolved, '+'), '+')) AS cell_entry
  FROM inherited h
  WHERE cell_block_resolved IS NOT NULL AND cell_block_resolved != ''
),
parsed AS (
  SELECT c.*,
    CASE left(cell_entry,1) WHEN 'l' THEN 'lte' WHEN 'n' THEN 'nr' WHEN 'g' THEN 'gsm' WHEN 'c' THEN 'cdma' ELSE NULL END AS tech_raw,
    split_part(cell_entry,',',2) AS cid_str,
    split_part(cell_entry,',',3) AS lac_str,
    split_part(cell_entry,',',4) AS plmn_str,
    split_part(split_part(sig_block,'+',1),',',2) AS ss_val,
    split_part(split_part(sig_block,'+',1),',',3) AS rsrp_val,
    split_part(split_part(sig_block,'+',1),',',4) AS rsrq_val,
    split_part(split_part(sig_block,'+',1),',',5) AS sinr_val
  FROM cells c
  WHERE length(cell_entry) > 2 AND cell_entry ~ '^[lngce],'
)
SELECT
  record_id, 'sdk' AS data_source, data_source_detail,
  'ss1' AS cell_origin,
  NULL::int AS is_connected,
  tech_raw,
  CASE tech_raw WHEN 'lte' THEN '4G' WHEN 'nr' THEN '5G' WHEN 'gsm' THEN '2G' WHEN 'cdma' THEN '2G' ELSE tech_raw END AS tech_norm,
  NULLIF(plmn_str,'') AS operator_id_raw,
  CASE WHEN lac_str ~ '^\d+$' THEN lac_str::bigint END AS lac_dec,
  CASE WHEN cid_str ~ '^\d+$' AND cid_str != '-1' THEN cid_str::bigint END AS cell_id_dec,
  NULL::int AS pci, NULL::int AS freq_channel, NULL::int AS bandwidth,
  CASE WHEN rsrp_val ~ '^-?\d+$' THEN rsrp_val::int END AS sig_rsrp,
  CASE WHEN rsrq_val ~ '^-?\d+$' THEN rsrq_val::int END AS sig_rsrq,
  CASE WHEN sinr_val ~ '^-?\d+$' THEN sinr_val::int END AS sig_sinr,
  NULL::int AS sig_rssi, NULL::int AS sig_dbm, NULL::int AS sig_asu_level,
  NULL::int AS sig_level,
  CASE WHEN ss_val ~ '^-?\d+$' THEN ss_val::int END AS sig_ss,
  NULL::int AS timing_advance,
  NULL::int AS sig_csi_rsrp, NULL::int AS sig_csi_rsrq, NULL::int AS sig_csi_sinr, NULL::int AS sig_cqi,
  ts AS ts_raw,
  CASE WHEN ts ~ '^\d{10,13}$' THEN to_timestamp(ts::bigint / 1000.0) ELSE NULL END AS ts_std,
  ts_block AS cell_ts_raw,
  gps_ts_raw, gps_info_type,
  CASE WHEN gps_block != '0' AND gps_block ~ '^\d+\.\d+,\d+\.\d+' THEN true ELSE false END AS gps_valid,
  CASE WHEN gps_block ~ '^\d+\.\d+,' THEN split_part(gps_block,',',1)::float8 END AS lon_raw,
  CASE WHEN gps_block ~ '^\d+\.\d+,\d+\.\d+' THEN split_part(gps_block,',',2)::float8 END AS lat_raw,
  CASE WHEN gps_block != '0' AND gps_block ~ '^\d+\.\d+,' THEN 'ss1_own' ELSE 'none' END AS gps_filled_from,
  NULL::bigint AS fill_time_delta_ms,
  cb_source AS cell_block_source,
  did, ip, plmn_main, brand, model, sdk_ver, oaid,
  pkg_name, wifi_name, wifi_mac, cpu_info, pressure
FROM parsed
WHERE cid_str != '-1' AND cid_str != '' AND cid_str IS NOT NULL;
```

### 4.4 生成 L0_gps — Step C：合并 + 清洗 + 派生

```sql
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
```

### 4.5 生成 L0_lac

**完全相同的 SQL，只需替换源表名**：

```
将所有
  legacy."网优项目_gps定位北京明细数据_20251201_20251207"
替换为
  legacy."网优项目_lac定位北京明细数据_20251201_20251207"

将所有
  rebuild2.l0_gps_ci / l0_gps_ss1 / l0_gps
替换为
  rebuild2.l0_lac_ci / l0_lac_ss1 / l0_lac
```

### 4.6 记录统计

执行完两张表后，用 MCP 运行：

```sql
-- 基础统计
SELECT 'l0_gps' AS tbl, count(*) AS total,
  count(*) FILTER (WHERE "有CellID") AS has_cellid,
  count(*) FILTER (WHERE "GPS有效") AS gps_valid,
  count(*) FILTER (WHERE "RSRP" IS NOT NULL) AS has_rsrp,
  count(DISTINCT "原始记录ID") AS distinct_records
FROM rebuild2.l0_gps
UNION ALL
SELECT 'l0_lac', count(*),
  count(*) FILTER (WHERE "有CellID"),
  count(*) FILTER (WHERE "GPS有效"),
  count(*) FILTER (WHERE "RSRP" IS NOT NULL),
  count(DISTINCT "原始记录ID")
FROM rebuild2.l0_lac;
```

---

## 5. 验收标准

| 指标 | l0_gps 预期 | l0_lac 预期 |
|------|------------|------------|
| 总行数 | 约 1~1.5 亿 | 约 0.8~1.2 亿 |
| 原始记录数 | ~2200 万 | ~1800 万 |
| 有 CellID | ~73% | ~73% |
| GPS 有效 | ~85%（gps 表 GPS 质量差） | ~60%（lac 表本身 GPS 少） |
| RSRP 非空 | ~88%（清洗后） | ~88% |

---

## 6. 失败处理

- **超时**：确认 `SET statement_timeout = 0`
- **磁盘空间**：每张 L0 表预计 30~60GB，确认有足够空间
- **内存**：`SET work_mem = '256MB'` 或更高
- **分段执行**：如果 cell_infos 全量 CTAS 太慢，可以分批（按 record_id 哈希分片）
- **中间表未清理**：如果执行中断，手动 `DROP TABLE IF EXISTS rebuild2.l0_gps_ci, rebuild2.l0_gps_ss1;`
