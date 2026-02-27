# Layer_0：北京明细源表解析规则 v1（GPS / LAC）

> 目标：按你给定的口径，把北京两张明细源表的 `cell_infos` / `ss1` 解析为“基站明细表（时间+cell_id+lac+运营商）”结构，并明确必须产出的统计指标。

## 1. 输入源表

- GPS 定位北京明细（第一步骤）：  
  `public."网优项目_gps定位北京明细数据_20251201_20251207"`
- LAC 定位北京明细（方案里的“全库”）：  
  `public."网优项目_lac定位北京明细数据_20251201_20251207"`

两表字段结构一致（27 列），主要差异仅在最后一列的命名。

## 2. 字段语义与解析口径

### 2.1 `cell_infos`

- 含义：手机在**本次连接中实时扫描到的基站信息**（包含当前连接与周边小区），信息较全。
- 解析：
  - 每个 `cell_infos` JSON 节点拆成 1 行基站明细；
  - 从 `cell_identity` 中取：
    - `cell_id`：`Nci/nci/Ci/ci`
    - `lac_raw`：`Tac/tac/Lac/lac`
    - `plmn_id_raw`：优先 `mno/Mno`，否则 `mccString+mncString`
  - `tech`：`nr→5G`，`lte→4G`，其他制式映射保留（L1 只用 4G/5G）
  - 时间字段：取节点中的 `timeStamp`（不强制解释单位）

### 2.2 `ss1`

- 含义：应用置于后台后自动采集的信息，字段比 `cell_infos` 少。
- 每组解析说明（你提供的格式）：
  - 组间以 `;` 分割；
  - 组内以 `&` 分割成 5 个元素：
    1) 信号强度块（按 `+` 分多条，`l*` 为 LTE、`n*` 为 NR；4 子元素：`ss/rsrp/rsrq/rssnr`）  
    2) 当前获取时间  
    3) 经度、纬度、时间  
    4) 基站信息块（按 `+` 分多条，`l*`/`n*` 区分 LTE/NR；4 子元素：制式标识、cell_id、lac、plmn）  
    5) AP 信息（bssid、ssid；ssid 为 hex 编码）
- 解析：
  - 对每组的第 4 元素，按 `+` 拆成多条基站记录；
  - 每条基站记录提取：`cell_id_raw/lac_raw/plmn_id_raw/tech`；
  - 时间字段：取第 2 元素（unix 秒级）。

### 2.3 `ss1` 与 `cell_infos` 继承/保留规则

为了让 `cell_id` 尽量携带运营商与 LAC 标签：

1. 用 `ss1.cell_id` 与同一原始记录的 `cell_infos.cell_id` 做匹配；
2. 若匹配成功：
   - **不单独保留 `ss1` 行**；
   - 以 `cell_infos` 行为准进入 L0。
3. 若匹配失败：
   - **保留 `ss1` 行**；
   - 标记 `match_status='SS1_UNMATCHED'`；
   - 后续再做补齐/清洗。

## 3. L0 输出关系（统一结构）

本轮 L0 输出两张**解析视图**（后续可按需 CTAS 成表）：

- GPS 源解析输出：`public.l0_gps_bj_detail_20251201_20251207_v1`
- LAC 源解析输出：`public.l0_lac_bj_detail_20251201_20251207_v1`

两视图字段一致，核心字段与 `public."网优cell项目_清洗补齐库_v1"` 对齐：

- `"记录id"`：原表 `"记录数唯一标识"`
- `cell_ts`：基站时间原始值（`cell_infos.timeStamp` 或 `ss1` 第 2 元素）
- `cell_ts_std`：按规则派生的标准时间（便于后续按时间序列研究；保留原始 `cell_ts` 不改动）
- `"运营商id"` / `"原始lac"` / `cell_id` / `tech`
- `lac_dec/lac_hex/cell_id_dec/cell_id_hex`
- `bs_id/sector_id`（4G `/256,%256`；5G `/4096,%4096`）
- `parsed_from`：`cell_infos` 或 `ss1`
- `match_status`：`CELL_INFOS` / `SS1_UNMATCHED`
- 信号参数（优先从 `cell_infos.signal_strength`，其次从 `ss1` 第 1 元素信号块解析；缺失则为空）：
  - `sig_rsrp/sig_rsrq/sig_sinr`（rsrp/rsrq/sinr；ss1 的第 5 个值 `rssnr` 统一映射为 `sig_sinr`）
  - `sig_rssi/sig_dbm/sig_asu_level/sig_level`（如存在）
  - `sig_ss`（ss1 的 `ss` 或 cell_infos 的 `string.ss`，仅做原始留存）
- 研究保留字段：`数据来源`, `did`, `ts`, `ip`, `sdk_ver`, `品牌`, `机型`, `gps_raw`, `lon_raw`, `lat_raw`, `gps_final`, `lon`, `lat`, `gps_info_type`, `oaid`

## 4. 解析 SQL（可直接执行）

> 两段 SQL 逻辑一致，只是源表与 `loc_method` 字段名不同。  
> 建议先 `CREATE OR REPLACE VIEW`，确认无误后再视情况落表。

### 4.1 GPS 源表 → `l0_gps_bj_detail_20251201_20251207_v1`

```sql
CREATE OR REPLACE VIEW public.l0_gps_bj_detail_20251201_20251207_v1 AS
WITH base AS (
  SELECT
    t."记录数唯一标识"       AS record_id,
    t."数据来源dna或daa"     AS data_source,
    t.did,
    t.ts,
    t.ip,
    t.sdk_ver,
    t."品牌"                AS brand,
    t."机型"                AS model,
    t.oaid,
    t.gps_info_type,
    t."原始上报gps"          AS gps_raw,
    t."当前数据最终经度"     AS lon,
    t."当前数据最终纬度"     AS lat,
    t."主卡运营商id"         AS plmn_main,
    NULLIF(btrim(t."cell_infos"), '')::jsonb AS cell_infos_json,
    NULLIF(btrim(t.ss1), '') AS ss1,
    t."gps定位北京来源ss1或daa" AS loc_method
  FROM public."网优项目_gps定位北京明细数据_20251201_20251207" t
),
cell_infos_cells AS (
  SELECT
    b.*,
    NULLIF(e.value->>'timeStamp','') AS cell_ts_raw,
    NULLIF(e.value->>'isConnected','')::int AS is_connected_raw,
    lower(e.value->>'type') AS type_raw,
    e.value->'cell_identity' AS ci,

    COALESCE(
      e.value->'cell_identity'->>'Nci',
      e.value->'cell_identity'->>'nci',
      e.value->'cell_identity'->>'Ci',
      e.value->'cell_identity'->>'ci'
    ) AS cell_id_raw,

    COALESCE(
      e.value->'cell_identity'->>'Tac',
      e.value->'cell_identity'->>'tac',
      e.value->'cell_identity'->>'Lac',
      e.value->'cell_identity'->>'lac'
    ) AS lac_raw,

    COALESCE(
      e.value->'cell_identity'->>'mno',
      e.value->'cell_identity'->>'Mno',
      (e.value->'cell_identity'->>'mccString') ||
        lpad(COALESCE(e.value->'cell_identity'->>'mncString',''), 2, '0')
    ) AS plmn_id_raw
  FROM base b
  CROSS JOIN LATERAL jsonb_each(b.cell_infos_json) AS e(key, value)
  WHERE b.cell_infos_json IS NOT NULL
),
cell_infos_out AS (
  SELECT
    record_id,
    data_source,
    loc_method,
    did,
    ts,
    ip,
    sdk_ver,
    brand,
    model,
    oaid,
    gps_info_type,
    gps_raw,
    lon,
    lat,
    plmn_main,

    'cell_infos'::text AS parsed_from,
    'CELL_INFOS'::text AS match_status,

    cell_ts_raw AS cell_ts,
    CASE
      WHEN lower(type_raw) = 'nr'  THEN '5G'
      WHEN lower(type_raw) = 'lte' THEN '4G'
      WHEN lower(type_raw) = 'wcdma' THEN '3G'
      WHEN lower(type_raw) IN ('gsm','cdma') THEN '2G'
      ELSE NULL
    END AS tech,

    NULLIF(btrim(plmn_id_raw), '') AS "运营商id",
    NULLIF(btrim(lac_raw), '')     AS "原始lac",
    NULLIF(btrim(cell_id_raw), '') AS cell_id,

    CASE WHEN lac_raw ~ '^[0-9]+$' THEN lac_raw::bigint END AS lac_dec,
    CASE WHEN cell_id_raw ~ '^[0-9]+$' THEN cell_id_raw::bigint END AS cell_id_dec,

    (is_connected_raw = 1) AS is_connected
  FROM cell_infos_cells
),
ss1_groups AS (
  SELECT
    b.*,
    g.group_txt
  FROM base b
  CROSS JOIN LATERAL regexp_split_to_table(b.ss1, ';') AS g(group_txt)
  WHERE b.ss1 IS NOT NULL AND btrim(g.group_txt) <> ''
),
ss1_group_parts AS (
  SELECT
    sg.*,
    string_to_array(sg.group_txt, '&') AS parts
  FROM ss1_groups sg
),
ss1_cells_raw AS (
  SELECT
    sgp.*,
    parts[2] AS acquire_ts_raw,
    parts[4] AS cell_part
  FROM ss1_group_parts sgp
  WHERE array_length(parts, 1) >= 4
),
ss1_cell_tokens AS (
  SELECT
    s.*,
    token_txt
  FROM ss1_cells_raw s
  CROSS JOIN LATERAL regexp_split_to_table(s.cell_part, '\\+') AS t(token_txt)
  WHERE s.cell_part IS NOT NULL AND btrim(t.token_txt) <> ''
),
ss1_cells AS (
  SELECT
    record_id,
    data_source,
    loc_method,
    did,
    ts,
    ip,
    sdk_ver,
    brand,
    model,
    oaid,
    gps_info_type,
    gps_raw,
    lon,
    lat,
    plmn_main,

    'ss1'::text AS parsed_from,
    acquire_ts_raw AS cell_ts,

    split_part(btrim(token_txt), ',', 1) AS ss1_prefix,
    split_part(btrim(token_txt), ',', 2) AS cell_id_raw,
    split_part(btrim(token_txt), ',', 3) AS lac_raw,
    split_part(btrim(token_txt), ',', 4) AS plmn_id_raw,

    CASE
      WHEN split_part(btrim(token_txt), ',', 1) = 'n' THEN '5G'
      WHEN split_part(btrim(token_txt), ',', 1) = 'l' THEN '4G'
      WHEN split_part(btrim(token_txt), ',', 1) = 'w' THEN '3G'
      WHEN split_part(btrim(token_txt), ',', 1) = 'g' THEN '2G'
      ELSE NULL
    END AS tech,

    NULLIF(btrim(split_part(btrim(token_txt), ',', 4)), '') AS "运营商id",
    NULLIF(btrim(split_part(btrim(token_txt), ',', 3)), '') AS "原始lac",
    NULLIF(btrim(split_part(btrim(token_txt), ',', 2)), '') AS cell_id,

    CASE WHEN split_part(btrim(token_txt), ',', 3) ~ '^[0-9]+$'
      THEN split_part(btrim(token_txt), ',', 3)::bigint END AS lac_dec,
    CASE WHEN split_part(btrim(token_txt), ',', 2) ~ '^[0-9]+$'
      THEN split_part(btrim(token_txt), ',', 2)::bigint END AS cell_id_dec
  FROM ss1_cell_tokens
),
ss1_inherit AS (
  SELECT
    s.record_id,
    s.data_source,
    s.loc_method,
    s.did,
    s.ts,
    s.ip,
    s.sdk_ver,
    s.brand,
    s.model,
    s.oaid,
    s.gps_info_type,
    s.gps_raw,
    s.lon,
    s.lat,
    s.plmn_main,

    s.parsed_from,
    s.cell_ts,
    COALESCE(ci.tech, s.tech) AS tech,
    COALESCE(ci."运营商id", s."运营商id", NULLIF(btrim(s.plmn_main), '')) AS "运营商id",
    COALESCE(ci."原始lac", s."原始lac") AS "原始lac",
    COALESCE(ci.cell_id, s.cell_id) AS cell_id,
    COALESCE(ci.lac_dec, s.lac_dec) AS lac_dec,
    COALESCE(ci.cell_id_dec, s.cell_id_dec) AS cell_id_dec,

    'SS1_UNMATCHED'::text AS match_status,
    false AS is_connected
  FROM ss1_cells s
  LEFT JOIN cell_infos_out ci
    ON ci.record_id = s.record_id
   AND ci.cell_id_dec IS NOT NULL
   AND ci.cell_id_dec = s.cell_id_dec
),
unioned AS (
  SELECT * FROM cell_infos_out
  UNION ALL
  SELECT * FROM ss1_inherit s
  WHERE NOT EXISTS (
    SELECT 1 FROM cell_infos_out ci
    WHERE ci.record_id = s.record_id
      AND ci.cell_id_dec IS NOT NULL
      AND ci.cell_id_dec = s.cell_id_dec
  )
)
SELECT
  record_id AS "记录id",
  cell_ts,
  CASE
    WHEN cell_ts ~ '^[0-9]+$' AND char_length(cell_ts) <= 18 THEN
      CASE
        -- ss1 为 epoch 秒
        WHEN parsed_from = 'ss1'
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)

        -- cell_infos: 若像 epoch 毫秒/秒则转，否则留空（部分 timeStamp 为设备计数/非墙钟）
        WHEN parsed_from = 'cell_infos'
         AND char_length(cell_ts) >= 13
         AND cell_ts::bigint BETWEEN 946684800000 AND 4102444800000
        THEN to_timestamp(cell_ts::bigint / 1000.0)

        WHEN parsed_from = 'cell_infos'
         AND char_length(cell_ts) BETWEEN 10 AND 11
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)

        ELSE NULL
      END
  END AS cell_ts_std,

  tech,
  "运营商id",
  "原始lac",
  cell_id,

  lac_dec,
  CASE WHEN lac_dec IS NOT NULL THEN upper(to_hex(lac_dec)) END AS lac_hex,
  cell_id_dec,
  CASE WHEN cell_id_dec IS NOT NULL THEN upper(to_hex(cell_id_dec)) END AS cell_id_hex,

  CASE
    WHEN lower(tech) = '4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec / 256::bigint
    WHEN lower(tech) = '5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec / 4096::bigint
  END AS bs_id,
  CASE
    WHEN lower(tech) = '4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec % 256::bigint
    WHEN lower(tech) = '5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec % 4096::bigint
  END AS sector_id,

  gps_raw AS gps_raw,
  CASE
    WHEN gps_raw ~ '^-?[0-9.]+,-?[0-9.]+$'
      THEN split_part(gps_raw, ',', 1)::double precision
  END AS lon_raw,
  CASE
    WHEN gps_raw ~ '^-?[0-9.]+,-?[0-9.]+$'
      THEN split_part(gps_raw, ',', 2)::double precision
  END AS lat_raw,

  CASE WHEN lon IS NOT NULL AND lat IS NOT NULL THEN lon::text || ',' || lat::text END AS gps_final,
  lon,
  lat,
  gps_info_type,

  data_source AS "数据来源",
  loc_method AS "北京来源",
  did,
  ts,
  CASE WHEN ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN ts::timestamp END AS ts_std,
  ip,
  sdk_ver,
  brand,
  model,
  oaid,

  parsed_from,
  match_status,
  is_connected
FROM unioned;
```

### 4.2 LAC 源表 → `l0_lac_bj_detail_20251201_20251207_v1`

```sql
CREATE OR REPLACE VIEW public.l0_lac_bj_detail_20251201_20251207_v1 AS
WITH base AS (
  SELECT
    t."记录数唯一标识"       AS record_id,
    t."数据来源dna或daa"     AS data_source,
    t.did,
    t.ts,
    t.ip,
    t.sdk_ver,
    t."品牌"                AS brand,
    t."机型"                AS model,
    t.oaid,
    t.gps_info_type,
    t."原始上报gps"          AS gps_raw,
    t."当前数据最终经度"     AS lon,
    t."当前数据最终纬度"     AS lat,
    t."主卡运营商id"         AS plmn_main,
    NULLIF(btrim(t."cell_infos"), '')::jsonb AS cell_infos_json,
    NULLIF(btrim(t.ss1), '') AS ss1,
    t."lac定位北京来源ss1或daa" AS loc_method
  FROM public."网优项目_lac定位北京明细数据_20251201_20251207" t
),
cell_infos_cells AS (
  SELECT
    b.*,
    NULLIF(e.value->>'timeStamp','') AS cell_ts_raw,
    NULLIF(e.value->>'isConnected','')::int AS is_connected_raw,
    lower(e.value->>'type') AS type_raw,
    e.value->'cell_identity' AS ci,

    COALESCE(
      e.value->'cell_identity'->>'Nci',
      e.value->'cell_identity'->>'nci',
      e.value->'cell_identity'->>'Ci',
      e.value->'cell_identity'->>'ci'
    ) AS cell_id_raw,

    COALESCE(
      e.value->'cell_identity'->>'Tac',
      e.value->'cell_identity'->>'tac',
      e.value->'cell_identity'->>'Lac',
      e.value->'cell_identity'->>'lac'
    ) AS lac_raw,

    COALESCE(
      e.value->'cell_identity'->>'mno',
      e.value->'cell_identity'->>'Mno',
      (e.value->'cell_identity'->>'mccString') ||
        lpad(COALESCE(e.value->'cell_identity'->>'mncString',''), 2, '0')
    ) AS plmn_id_raw
  FROM base b
  CROSS JOIN LATERAL jsonb_each(b.cell_infos_json) AS e(key, value)
  WHERE b.cell_infos_json IS NOT NULL
),
cell_infos_out AS (
  SELECT
    record_id,
    data_source,
    loc_method,
    did,
    ts,
    ip,
    sdk_ver,
    brand,
    model,
    oaid,
    gps_info_type,
    gps_raw,
    lon,
    lat,
    plmn_main,

    'cell_infos'::text AS parsed_from,
    'CELL_INFOS'::text AS match_status,

    cell_ts_raw AS cell_ts,
    CASE
      WHEN lower(type_raw) = 'nr'  THEN '5G'
      WHEN lower(type_raw) = 'lte' THEN '4G'
      WHEN lower(type_raw) = 'wcdma' THEN '3G'
      WHEN lower(type_raw) IN ('gsm','cdma') THEN '2G'
      ELSE NULL
    END AS tech,

    NULLIF(btrim(plmn_id_raw), '') AS "运营商id",
    NULLIF(btrim(lac_raw), '')     AS "原始lac",
    NULLIF(btrim(cell_id_raw), '') AS cell_id,

    CASE WHEN lac_raw ~ '^[0-9]+$' THEN lac_raw::bigint END AS lac_dec,
    CASE WHEN cell_id_raw ~ '^[0-9]+$' THEN cell_id_raw::bigint END AS cell_id_dec,

    (is_connected_raw = 1) AS is_connected
  FROM cell_infos_cells
),
ss1_groups AS (
  SELECT
    b.*,
    g.group_txt
  FROM base b
  CROSS JOIN LATERAL regexp_split_to_table(b.ss1, ';') AS g(group_txt)
  WHERE b.ss1 IS NOT NULL AND btrim(g.group_txt) <> ''
),
ss1_group_parts AS (
  SELECT
    sg.*,
    string_to_array(sg.group_txt, '&') AS parts
  FROM ss1_groups sg
),
ss1_cells_raw AS (
  SELECT
    sgp.*,
    parts[2] AS acquire_ts_raw,
    parts[4] AS cell_part
  FROM ss1_group_parts sgp
  WHERE array_length(parts, 1) >= 4
),
ss1_cell_tokens AS (
  SELECT
    s.*,
    token_txt
  FROM ss1_cells_raw s
  CROSS JOIN LATERAL regexp_split_to_table(s.cell_part, '\\+') AS t(token_txt)
  WHERE s.cell_part IS NOT NULL AND btrim(t.token_txt) <> ''
),
ss1_cells AS (
  SELECT
    record_id,
    data_source,
    loc_method,
    did,
    ts,
    ip,
    sdk_ver,
    brand,
    model,
    oaid,
    gps_info_type,
    gps_raw,
    lon,
    lat,
    plmn_main,

    'ss1'::text AS parsed_from,
    acquire_ts_raw AS cell_ts,

    split_part(btrim(token_txt), ',', 1) AS ss1_prefix,
    split_part(btrim(token_txt), ',', 2) AS cell_id_raw,
    split_part(btrim(token_txt), ',', 3) AS lac_raw,
    split_part(btrim(token_txt), ',', 4) AS plmn_id_raw,

    CASE
      WHEN split_part(btrim(token_txt), ',', 1) = 'n' THEN '5G'
      WHEN split_part(btrim(token_txt), ',', 1) = 'l' THEN '4G'
      WHEN split_part(btrim(token_txt), ',', 1) = 'w' THEN '3G'
      WHEN split_part(btrim(token_txt), ',', 1) = 'g' THEN '2G'
      ELSE NULL
    END AS tech,

    NULLIF(btrim(split_part(btrim(token_txt), ',', 4)), '') AS "运营商id",
    NULLIF(btrim(split_part(btrim(token_txt), ',', 3)), '') AS "原始lac",
    NULLIF(btrim(split_part(btrim(token_txt), ',', 2)), '') AS cell_id,

    CASE WHEN split_part(btrim(token_txt), ',', 3) ~ '^[0-9]+$'
      THEN split_part(btrim(token_txt), ',', 3)::bigint END AS lac_dec,
    CASE WHEN split_part(btrim(token_txt), ',', 2) ~ '^[0-9]+$'
      THEN split_part(btrim(token_txt), ',', 2)::bigint END AS cell_id_dec
  FROM ss1_cell_tokens
),
ss1_inherit AS (
  SELECT
    s.record_id,
    s.data_source,
    s.loc_method,
    s.did,
    s.ts,
    s.ip,
    s.sdk_ver,
    s.brand,
    s.model,
    s.oaid,
    s.gps_info_type,
    s.gps_raw,
    s.lon,
    s.lat,
    s.plmn_main,

    s.parsed_from,
    s.cell_ts,
    COALESCE(ci.tech, s.tech) AS tech,
    COALESCE(ci."运营商id", s."运营商id", NULLIF(btrim(s.plmn_main), '')) AS "运营商id",
    COALESCE(ci."原始lac", s."原始lac") AS "原始lac",
    COALESCE(ci.cell_id, s.cell_id) AS cell_id,
    COALESCE(ci.lac_dec, s.lac_dec) AS lac_dec,
    COALESCE(ci.cell_id_dec, s.cell_id_dec) AS cell_id_dec,

    'SS1_UNMATCHED'::text AS match_status,
    false AS is_connected
  FROM ss1_cells s
  LEFT JOIN cell_infos_out ci
    ON ci.record_id = s.record_id
   AND ci.cell_id_dec IS NOT NULL
   AND ci.cell_id_dec = s.cell_id_dec
),
unioned AS (
  SELECT * FROM cell_infos_out
  UNION ALL
  SELECT * FROM ss1_inherit s
  WHERE NOT EXISTS (
    SELECT 1 FROM cell_infos_out ci
    WHERE ci.record_id = s.record_id
      AND ci.cell_id_dec IS NOT NULL
      AND ci.cell_id_dec = s.cell_id_dec
  )
)
SELECT
  record_id AS "记录id",
  cell_ts,
  CASE
    WHEN cell_ts ~ '^[0-9]+$' AND char_length(cell_ts) <= 18 THEN
      CASE
        WHEN parsed_from = 'ss1'
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)

        WHEN parsed_from = 'cell_infos'
         AND char_length(cell_ts) >= 13
         AND cell_ts::bigint BETWEEN 946684800000 AND 4102444800000
        THEN to_timestamp(cell_ts::bigint / 1000.0)

        WHEN parsed_from = 'cell_infos'
         AND char_length(cell_ts) BETWEEN 10 AND 11
         AND cell_ts::bigint BETWEEN 946684800 AND 4102444800
        THEN to_timestamp(cell_ts::bigint)

        ELSE NULL
      END
  END AS cell_ts_std,

  tech,
  "运营商id",
  "原始lac",
  cell_id,

  lac_dec,
  CASE WHEN lac_dec IS NOT NULL THEN upper(to_hex(lac_dec)) END AS lac_hex,
  cell_id_dec,
  CASE WHEN cell_id_dec IS NOT NULL THEN upper(to_hex(cell_id_dec)) END AS cell_id_hex,

  CASE
    WHEN lower(tech) = '4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec / 256::bigint
    WHEN lower(tech) = '5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec / 4096::bigint
  END AS bs_id,
  CASE
    WHEN lower(tech) = '4g' AND cell_id_dec IS NOT NULL THEN cell_id_dec % 256::bigint
    WHEN lower(tech) = '5g' AND cell_id_dec IS NOT NULL THEN cell_id_dec % 4096::bigint
  END AS sector_id,

  gps_raw AS gps_raw,
  CASE
    WHEN gps_raw ~ '^-?[0-9.]+,-?[0-9.]+$'
      THEN split_part(gps_raw, ',', 1)::double precision
  END AS lon_raw,
  CASE
    WHEN gps_raw ~ '^-?[0-9.]+,-?[0-9.]+$'
      THEN split_part(gps_raw, ',', 2)::double precision
  END AS lat_raw,

  CASE WHEN lon IS NOT NULL AND lat IS NOT NULL THEN lon::text || ',' || lat::text END AS gps_final,
  lon,
  lat,
  gps_info_type,

  data_source AS "数据来源",
  loc_method AS "北京来源",
  did,
  ts,
  CASE WHEN ts ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN ts::timestamp END AS ts_std,
  ip,
  sdk_ver,
  brand,
  model,
  oaid,

  parsed_from,
  match_status,
  is_connected
FROM unioned;
```

## 5. 必须产出的统计指标（L0 自检）

对每个源（GPS/LAC）分别产出下面统计结果：

1. **原表行数（raw_rows）**
2. **L0 解析后行数（l0_rows）**
3. **来源占比**
   - `cell_infos_rows` / `ss1_unmatched_rows`
   - `ss1_unmatched_pct`
4. **关键字段空值/异常**
   - `cell_id_dec IS NULL`
   - `"运营商id"` 为空
   - `"原始lac"` 为空或非数字
5. **ss1 匹配情况**
   - `ss1_total_rows`（解析出的 ss1 基站明细总数）
   - `ss1_matched_rows`（与 cell_infos 匹配的数量）
   - `ss1_unmatched_rows`（未匹配数量）

### 5.1 快速统计（基于 L0 视图）

> 注意：全量统计可能耗时较长；可先用 `TABLESAMPLE` 抽样估计比例。

```sql
-- 抽样 0.1% 估计比例（GPS 源示例）
WITH s AS (
  SELECT * FROM public.l0_gps_bj_detail_20251201_20251207_v1
  TABLESAMPLE SYSTEM (0.1)
)
SELECT
  COUNT(*) AS l0_rows_sample,
  COUNT(*) FILTER (WHERE parsed_from='cell_infos') AS cell_infos_rows_sample,
  COUNT(*) FILTER (WHERE parsed_from='ss1') AS ss1_unmatched_rows_sample,
  ROUND(100.0 * COUNT(*) FILTER (WHERE parsed_from='ss1') / NULLIF(COUNT(*),0), 2) AS ss1_unmatched_pct_sample,
  COUNT(*) FILTER (WHERE cell_id_dec IS NULL) AS cell_id_null_sample,
  COUNT(*) FILTER (WHERE "运营商id" IS NULL OR btrim("运营商id")='') AS plmn_null_sample,
  COUNT(*) FILTER (WHERE "原始lac" IS NULL OR btrim("原始lac")='' OR btrim("原始lac") !~ '^[0-9]+$') AS lac_null_or_bad_sample
FROM s;
```

### 5.2 ss1 匹配统计（同口径 CTE）

```sql
-- GPS 源示例：只统计 ss1 的 matched/unmatched（可抽样）
WITH base AS (
  SELECT
    t."记录数唯一标识" AS record_id,
    NULLIF(btrim(t."cell_infos"), '')::jsonb AS cell_infos_json,
    NULLIF(btrim(t.ss1), '') AS ss1
  FROM public."网优项目_gps定位北京明细数据_20251201_20251207" t
),
cell_infos_ids AS (
  SELECT
    b.record_id,
    CASE
      WHEN COALESCE(
        e.value->'cell_identity'->>'Nci',
        e.value->'cell_identity'->>'nci',
        e.value->'cell_identity'->>'Ci',
        e.value->'cell_identity'->>'ci'
      ) ~ '^[0-9]+$'
      THEN COALESCE(
        e.value->'cell_identity'->>'Nci',
        e.value->'cell_identity'->>'nci',
        e.value->'cell_identity'->>'Ci',
        e.value->'cell_identity'->>'ci'
      )::bigint
    END AS cell_id_dec
  FROM base b
  CROSS JOIN LATERAL jsonb_each(b.cell_infos_json) AS e(key, value)
  WHERE b.cell_infos_json IS NOT NULL
),
ss1_groups AS (
  SELECT
    b.record_id,
    g.group_txt
  FROM base b
  CROSS JOIN LATERAL regexp_split_to_table(b.ss1, ';') AS g(group_txt)
  WHERE b.ss1 IS NOT NULL AND btrim(g.group_txt) <> ''
),
ss1_group_parts AS (
  SELECT
    sg.record_id,
    string_to_array(sg.group_txt, '&') AS parts
  FROM ss1_groups sg
),
ss1_cell_tokens AS (
  SELECT
    sgp.record_id,
    token_txt
  FROM ss1_group_parts sgp
  CROSS JOIN LATERAL regexp_split_to_table(sgp.parts[4], '\\+') AS t(token_txt)
  WHERE array_length(sgp.parts,1) >= 4 AND btrim(t.token_txt) <> ''
),
ss1_ids AS (
  SELECT
    record_id,
    CASE
      WHEN split_part(btrim(token_txt), ',', 2) ~ '^[0-9]+$'
      THEN split_part(btrim(token_txt), ',', 2)::bigint
    END AS cell_id_dec
  FROM ss1_cell_tokens
)
ss1_labeled AS (
  SELECT
    s.*,
    EXISTS (
      SELECT 1 FROM cell_infos_ids ci
      WHERE ci.record_id = s.record_id
        AND ci.cell_id_dec = s.cell_id_dec
    ) AS is_matched
  FROM ss1_ids s
)
SELECT
  COUNT(*) AS ss1_total_rows,
  COUNT(*) FILTER (WHERE is_matched) AS ss1_matched_rows,
  COUNT(*) FILTER (WHERE NOT is_matched) AS ss1_unmatched_rows,
  ROUND(100.0 * COUNT(*) FILTER (WHERE NOT is_matched) / NULLIF(COUNT(*),0), 2) AS ss1_unmatched_pct
FROM ss1_labeled;
```
