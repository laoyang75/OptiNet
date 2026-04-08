# Runbook：Phase 3 Steps 2–5 — Cell 校验 → GPS 修正 → 信号补齐 → 回算

> 身份：**执行 Agent**
> 任务：在 dim_bs_refined 基础上，完成 Cell GPS 校验（Step 2）、明细 GPS 修正（Step 3）、信号补齐（Step 4）、中心点回算（Step 5）
> 产出：`rebuild2.dim_cell_refined`（573,561 行）、`rebuild2._tmp_gps_fixed`（~30M 行）、`rebuild2.dwd_fact_enriched`（~30M 行）、dim_cell_refined / dim_bs_refined 新增 `_recalc` 列
> **必须严格按步骤执行，每步有检查点，检查不通过不能继续**

---

## 环境信息

- **SSH**：`sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217`
- **PG17**：`PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2`
- **MCP 工具**：`mcp__PG17__execute_sql`（用于测试和验证）

---

## 前置条件

| 表 | 预期行数 | 作用 |
|----|----------|------|
| `rebuild2.l0_lac` | ~4377 万 | 明细源表 |
| `rebuild2.dim_lac_trusted` | 1,057 | 可信 LAC 白名单 |
| `rebuild2.dim_bs_refined` | 193,036 | Step 1 精算 BS 中心点（**必须已完成**） |
| `rebuild2.dim_cell_stats` | 573,561 | Phase 2 Cell 统计 |

**先用 MCP 验证前置条件**：

```sql
SELECT 'l0_lac' AS tbl, count(*) AS n FROM rebuild2.l0_lac
UNION ALL SELECT 'dim_lac_trusted', count(*) FROM rebuild2.dim_lac_trusted
UNION ALL SELECT 'dim_bs_refined',  count(*) FROM rebuild2.dim_bs_refined
UNION ALL SELECT 'dim_cell_stats',  count(*) FROM rebuild2.dim_cell_stats;
```

**✅ 检查点 0**：四张表都存在且行数与预期一致；dim_bs_refined 必须存在。不通过则停止，先完成 Phase 3 Step 1。

---

## 算法概述

| Step | 产出 | 核心逻辑 |
|------|------|---------|
| Step 2 | dim_cell_refined | 计算 Cell GPS 中心点；与 BS 中心比距离，标记 GPS 异常（5G>1000m / non-5G>2000m） |
| Step 3 | _tmp_gps_fixed | 30M+ 行逐行判断 GPS 来源：original → cell_center → bs_center / bs_center_risk → not_filled |
| Step 4 | dwd_fact_enriched | 两阶段信号补齐：Stage1 同 Cell LAG/LEAD 最近邻；Stage2 同 BS 主要 Cell 回退 |
| Step 5 | _recalc 列更新 | 用 dwd_fact_enriched 修正后 GPS 重算 Cell / BS 中心点，新增 _recalc 列不覆盖原值 |

---

## 进入服务器

```bash
sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217

PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2

-- 进入 psql 后：
SET statement_timeout = 0;
SET work_mem = '256MB';
\timing on
```

---

## STEP 2：Cell GPS 校验 → dim_cell_refined

> 预计耗时：**3~8 分钟**（扫描 l0_lac ~4377万行，JOIN dim_lac_trusted，再 JOIN dim_bs_refined）

从 l0_lac 提取 Cell 粒度 GPS 有效记录，计算 Cell GPS 中心点，与 dim_bs_refined 中 BS 中心对比距离，标记 GPS 异常，最终组装 dim_cell_refined（573,561 行）。

```sql
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
```

**✅ 检查点 2**（MCP 验证）：

```sql
-- 总览：行数 + 异常率
SELECT
    count(*)                                              AS total_cells,
    count(*) FILTER (WHERE gps_center_lon IS NOT NULL)   AS cells_with_gps,
    count(*) FILTER (WHERE gps_anomaly = true)           AS anomaly_cells,
    ROUND(100.0 * count(*) FILTER (WHERE gps_anomaly = true)
          / NULLIF(count(*) FILTER (WHERE gps_center_lon IS NOT NULL), 0), 2) AS anomaly_rate_pct,
    count(*) FILTER (WHERE bs_gps_quality = 'Usable')    AS bs_usable,
    count(*) FILTER (WHERE bs_gps_quality = 'Risk')      AS bs_risk,
    count(*) FILTER (WHERE bs_gps_quality = 'Unusable')  AS bs_unusable
FROM rebuild2.dim_cell_refined;
```

- 预期 total_cells = **573,561**（与 dim_cell_stats 一致），偏差超 100 行则停止排查
- cells_with_gps 预期约 **40~50 万**（有 GPS 的 Cell 比例 70%+）
- anomaly_rate_pct 预期 < **5%**，超 10% 需排查 BS GPS 质量

```sql
-- Cell 到 BS 距离分布
SELECT
    count(*) FILTER (WHERE dist_to_bs_m IS NULL)          AS no_bs_ref,
    count(*) FILTER (WHERE dist_to_bs_m <= 500)           AS dist_le_500m,
    count(*) FILTER (WHERE dist_to_bs_m BETWEEN 500 AND 1000) AS dist_500_1000m,
    count(*) FILTER (WHERE dist_to_bs_m BETWEEN 1000 AND 2000) AS dist_1000_2000m,
    count(*) FILTER (WHERE dist_to_bs_m > 2000)           AS dist_gt_2000m,
    ROUND(AVG(dist_to_bs_m) FILTER (WHERE dist_to_bs_m IS NOT NULL)::numeric, 0) AS avg_dist_m
FROM rebuild2.dim_cell_refined;
```

- dist_le_500m 应占绝大多数（城区 Cell 通常距 BS 很近）
- dist_gt_2000m 是高异常嫌疑，过多需排查

```sql
-- 按制式查看 GPS 覆盖
SELECT tech_norm,
    count(*)                                             AS cells,
    count(*) FILTER (WHERE gps_center_lon IS NOT NULL)  AS with_gps,
    count(*) FILTER (WHERE gps_anomaly = true)          AS anomaly
FROM rebuild2.dim_cell_refined
GROUP BY tech_norm
ORDER BY cells DESC;
```

---

## STEP 3：明细 GPS 修正 → _tmp_gps_fixed

> 预计耗时：**10~20 分钟**（处理 ~3000 万条可信 LAC 范围内记录，JOIN 两张字典表）
> 这是重型步骤，执行期间 psql 会持续占用 CPU，请勿中断

对 l0_lac 中全部可信 LAC 范围内记录（~30M 行），逐行判断最终 GPS 来源：
1. **original**：原始 GPS 有效 + 到 Cell 中心距离在阈值内（4G≤1000m，5G≤500m）
2. **cell_center**：原始 GPS 超阈值或无 GPS，但 Cell 有有效中心（非异常）
3. **bs_center**：Cell 无有效 GPS，BS 质量 Usable，用 BS 中心填充
4. **bs_center_risk**：Cell 无有效 GPS，BS 质量 Risk，用 BS 中心填充（风险标记）
5. **not_filled**：Cell 无有效 GPS 且 BS 质量 Unusable，不填充

```sql
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 3: 明细 GPS 修正（_tmp_gps_fixed）
-- 对 30M+ 条可信 LAC 范围内记录，逐行判断 GPS 来源
-- ============================================================

-- 3.1 先物化可信 LAC 范围内的全量行（含行号供后续关联）
DROP TABLE IF EXISTS rebuild2._tmp_l0_trusted;
CREATE TABLE rebuild2._tmp_l0_trusted AS
SELECT
    l.ctid                          AS l0_row_id,
    l."运营商编码"                   AS op,
    l."标准制式"                     AS tech,
    l."LAC"::text                   AS lac,
    l."CellID"                      AS cell_id,
    l."基站ID"                      AS bs_id,
    l."GPS有效"                      AS gps_valid,
    l."经度"                         AS raw_lon,
    l."纬度"                         AS raw_lat,
    l."上报时间"                     AS report_time,
    l."设备标识"                     AS dev_id,
    l."RSRP"                        AS rsrp,
    l."RSRQ"                        AS rsrq,
    l."SINR"                        AS sinr,
    l."Dbm"                         AS dbm,
    l."SS原始值"                     AS ss_raw
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
   AND l."标准制式"   = t.tech_norm
   AND l."LAC"        = t.lac::bigint;

CREATE INDEX ON rebuild2._tmp_l0_trusted(op, tech, lac, cell_id);
CREATE INDEX ON rebuild2._tmp_l0_trusted(dev_id);
ANALYZE rebuild2._tmp_l0_trusted;

-- 3.2 Cell GPS 字典（仅取非异常 Cell 的有效中心，异常 Cell 视为无 GPS）
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps_dict;
CREATE TABLE rebuild2._tmp_cell_gps_dict AS
SELECT
    operator_code  AS op,
    tech_norm      AS tech,
    lac,
    cell_id,
    bs_id,
    gps_center_lon AS cell_lon,
    gps_center_lat AS cell_lat,
    gps_anomaly,
    bs_gps_quality
FROM rebuild2.dim_cell_refined;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_gps_dict(op, tech, lac, cell_id);
ANALYZE rebuild2._tmp_cell_gps_dict;

-- 3.3 BS GPS 字典
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps_dict;
CREATE TABLE rebuild2._tmp_bs_gps_dict AS
SELECT
    operator_code  AS op,
    tech_norm      AS tech,
    lac,
    bs_id,
    gps_center_lon AS bs_lon,
    gps_center_lat AS bs_lat,
    gps_quality
FROM rebuild2.dim_bs_refined;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_gps_dict(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_gps_dict;

-- 3.4 组装 GPS 修正结果
DROP TABLE IF EXISTS rebuild2._tmp_gps_fixed;
CREATE TABLE rebuild2._tmp_gps_fixed AS
SELECT
    l.l0_row_id,
    l.op,
    l.tech,
    l.lac,
    l.cell_id,
    l.bs_id,
    -- 最终经纬度
    CASE
        -- 原始 GPS 有效且到 Cell 中心距离 ≤ 阈值 → 保留原始
        WHEN l.gps_valid = true
             AND l.raw_lon BETWEEN 73 AND 135
             AND l.raw_lat BETWEEN 3 AND 54
             AND c.cell_lon IS NOT NULL
             AND NOT COALESCE(c.gps_anomaly, false)
             AND SQRT(POWER((l.raw_lon - c.cell_lon) * 85300, 2) +
                      POWER((l.raw_lat - c.cell_lat) * 111000, 2))
                 <= CASE WHEN l.tech LIKE '%5G%' THEN 500 ELSE 1000 END
            THEN l.raw_lon
        -- 原始 GPS 超阈值或无 GPS，Cell 有有效中心 → Cell 中心
        WHEN c.cell_lon IS NOT NULL AND NOT COALESCE(c.gps_anomaly, false)
            THEN c.cell_lon
        -- Cell 无有效 GPS，BS Usable 或 Risk → BS 中心
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL
             AND b.gps_quality IN ('Usable', 'Risk')
            THEN b.bs_lon
        ELSE NULL
    END AS lon_final,
    CASE
        WHEN l.gps_valid = true
             AND l.raw_lon BETWEEN 73 AND 135
             AND l.raw_lat BETWEEN 3 AND 54
             AND c.cell_lon IS NOT NULL
             AND NOT COALESCE(c.gps_anomaly, false)
             AND SQRT(POWER((l.raw_lon - c.cell_lon) * 85300, 2) +
                      POWER((l.raw_lat - c.cell_lat) * 111000, 2))
                 <= CASE WHEN l.tech LIKE '%5G%' THEN 500 ELSE 1000 END
            THEN l.raw_lat
        WHEN c.cell_lon IS NOT NULL AND NOT COALESCE(c.gps_anomaly, false)
            THEN c.cell_lat
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL
             AND b.gps_quality IN ('Usable', 'Risk')
            THEN b.bs_lat
        ELSE NULL
    END AS lat_final,
    -- GPS 来源标记
    CASE
        WHEN l.gps_valid = true
             AND l.raw_lon BETWEEN 73 AND 135
             AND l.raw_lat BETWEEN 3 AND 54
             AND c.cell_lon IS NOT NULL
             AND NOT COALESCE(c.gps_anomaly, false)
             AND SQRT(POWER((l.raw_lon - c.cell_lon) * 85300, 2) +
                      POWER((l.raw_lat - c.cell_lat) * 111000, 2))
                 <= CASE WHEN l.tech LIKE '%5G%' THEN 500 ELSE 1000 END
            THEN 'original'
        WHEN c.cell_lon IS NOT NULL AND NOT COALESCE(c.gps_anomaly, false)
            THEN 'cell_center'
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL AND b.gps_quality = 'Usable'
            THEN 'bs_center'
        WHEN (c.cell_lon IS NULL OR COALESCE(c.gps_anomaly, false))
             AND b.bs_lon IS NOT NULL AND b.gps_quality = 'Risk'
            THEN 'bs_center_risk'
        ELSE 'not_filled'
    END AS gps_source,
    l.report_time  AS "上报时间",
    l.dev_id       AS "设备标识",
    l.rsrp         AS "RSRP",
    l.rsrq         AS "RSRQ",
    l.sinr         AS "SINR",
    l.dbm          AS "Dbm",
    l.ss_raw       AS "SS原始值"
FROM rebuild2._tmp_l0_trusted l
LEFT JOIN rebuild2._tmp_cell_gps_dict c
    ON l.op      = c.op
   AND l.tech    = c.tech
   AND l.lac     = c.lac
   AND l.cell_id = c.cell_id
LEFT JOIN rebuild2._tmp_bs_gps_dict b
    ON l.op   = b.op
   AND l.tech = b.tech
   AND l.lac  = b.lac
   AND l.bs_id = b.bs_id;

CREATE INDEX ON rebuild2._tmp_gps_fixed(op, tech, lac, cell_id);
CREATE INDEX ON rebuild2._tmp_gps_fixed(op, tech, lac, bs_id);
CREATE INDEX ON rebuild2._tmp_gps_fixed(gps_source);
CREATE INDEX ON rebuild2._tmp_gps_fixed("设备标识");
CREATE INDEX ON rebuild2._tmp_gps_fixed("上报时间");
ANALYZE rebuild2._tmp_gps_fixed;

-- 清理中间字典表（保留 _tmp_gps_fixed 供 Step 4 使用）
DROP TABLE IF EXISTS rebuild2._tmp_l0_trusted;
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps_dict;
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps_dict;

SELECT 'Step 3 完成: _tmp_gps_fixed 已创建' AS status;
```

**✅ 检查点 3**（MCP 验证）：

```sql
-- 总量核查
SELECT
    count(*)                                              AS total_rows,
    count(*) FILTER (WHERE lon_final IS NOT NULL)        AS rows_with_gps,
    count(*) FILTER (WHERE lon_final IS NULL)            AS rows_no_gps,
    ROUND(100.0 * count(*) FILTER (WHERE lon_final IS NOT NULL) / count(*), 2) AS gps_coverage_pct,
    count(DISTINCT "设备标识")                            AS distinct_devices
FROM rebuild2._tmp_gps_fixed;
```

- total_rows 预期约 **3000 万**（可信 LAC 范围内全量）
- gps_coverage_pct 预期 > **90%**（原始 GPS 84% + Cell 中心填充 + BS 中心填充后应大幅提升）
- 如果 total_rows < 2000 万或 > 4000 万，停止排查

```sql
-- GPS 来源分布（核心指标）
SELECT
    gps_source,
    count(*)                                              AS row_count,
    ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2)   AS pct,
    count(DISTINCT "设备标识")                            AS device_count
FROM rebuild2._tmp_gps_fixed
GROUP BY gps_source
ORDER BY row_count DESC;
```

- **original** 预期约 **60~75%**（保留原始 GPS 的行）
- **cell_center** 预期约 **15~25%**（用 Cell 中心替换的行）
- **bs_center** 预期约 **5~15%**（用 BS 中心填充的行，BS Usable）
- **bs_center_risk** 预期占少数（BS Risk 填充，精度较低）
- **not_filled** 预期 < **5%**（无法填充的行，BS Unusable）

```sql
-- 按制式查看 GPS 来源覆盖改善
SELECT tech, gps_source, count(*) AS cnt
FROM rebuild2._tmp_gps_fixed
GROUP BY tech, gps_source
ORDER BY tech, cnt DESC;
```

---

## STEP 4：信号补齐 → dwd_fact_enriched

> 预计耗时：**15~25 分钟**（两阶段 LAG/LEAD 窗口函数 + 主要 Cell 回退，处理 ~30M 行）
> 这是最重的步骤，Stage 1 窗口函数对全量排序，耗时最长

在 _tmp_gps_fixed 基础上，对 RSRP / RSRQ / SINR / Dbm 进行两阶段信号补齐：
- **Stage 1**：同 Cell 按时间排序，LAG/LEAD 取最近有效值
- **Stage 2**：同 BS 内找记录最多的主要 Cell，取其最近有效信号值回退

```sql
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 4: 信号补齐（dwd_fact_enriched）
-- Stage 1: 同 Cell 时间最近邻补齐
-- Stage 2: 同 BS 主要 Cell 回退补齐
-- ============================================================

-- 4.1 Stage 1：同 Cell 内 LAG/LEAD 时间最近邻补齐
-- 先物化带行号的 Cell 窗口信号
DROP TABLE IF EXISTS rebuild2._tmp_signal_s1;
CREATE TABLE rebuild2._tmp_signal_s1 AS
SELECT
    l0_row_id,
    op, tech, lac, cell_id, bs_id,
    lon_final, lat_final, gps_source,
    "上报时间",
    "设备标识"  AS dev_id,
    -- 原始信号
    "RSRP"  AS rsrp_raw,
    "RSRQ"  AS rsrq_raw,
    "SINR"  AS sinr_raw,
    "Dbm"   AS dbm_raw,
    "SS原始值" AS ss_raw,
    -- 窗口：同 Cell 按时间排序，LAG/LEAD 各取最近有效值
    -- ★ 过滤哨兵值 -1 和 -110，避免传播无效信号
    LAG(CASE WHEN "RSRP" < 0 AND "RSRP" NOT IN (-1, -110) THEN "RSRP" END)  IGNORE NULLS OVER w AS rsrp_lag,
    LEAD(CASE WHEN "RSRP" < 0 AND "RSRP" NOT IN (-1, -110) THEN "RSRP" END) IGNORE NULLS OVER w AS rsrp_lead,
    LAG("RSRQ")  IGNORE NULLS OVER w AS rsrq_lag,
    LEAD("RSRQ") IGNORE NULLS OVER w AS rsrq_lead,
    LAG("SINR")  IGNORE NULLS OVER w AS sinr_lag,
    LEAD("SINR") IGNORE NULLS OVER w AS sinr_lead,
    LAG("Dbm")   IGNORE NULLS OVER w AS dbm_lag,
    LEAD("Dbm")  IGNORE NULLS OVER w AS dbm_lead
FROM rebuild2._tmp_gps_fixed
WINDOW w AS (PARTITION BY op, tech, lac, cell_id ORDER BY "上报时间");

CREATE INDEX ON rebuild2._tmp_signal_s1(op, tech, lac, cell_id);
CREATE INDEX ON rebuild2._tmp_signal_s1(bs_id) WHERE rsrp_raw IS NULL AND rsrp_lag IS NULL AND rsrp_lead IS NULL;
ANALYZE rebuild2._tmp_signal_s1;

-- 4.2 找出同 BS 内记录数最多的主要 Cell（Stage 2 回退目标）
DROP TABLE IF EXISTS rebuild2._tmp_bs_main_cell;
CREATE TABLE rebuild2._tmp_bs_main_cell AS
SELECT DISTINCT ON (op, tech, lac, bs_id)
    op, tech, lac, bs_id, cell_id AS main_cell_id
FROM (
    SELECT op, tech, lac, bs_id, cell_id, count(*) AS cnt
    FROM rebuild2._tmp_gps_fixed
    WHERE "RSRP" IS NOT NULL AND "RSRP" < 0 AND "RSRP" NOT IN (-1, -110)
    GROUP BY op, tech, lac, bs_id, cell_id
) sub
ORDER BY op, tech, lac, bs_id, cnt DESC;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_main_cell(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_main_cell;

-- 4.3 主要 Cell 中最近的信号值（时间最近的一条有效信号记录）
-- 用于 Stage 2 回退
DROP TABLE IF EXISTS rebuild2._tmp_main_cell_signal;
CREATE TABLE rebuild2._tmp_main_cell_signal AS
SELECT DISTINCT ON (g.op, g.tech, g.lac, g.bs_id)
    g.op, g.tech, g.lac, g.bs_id,
    g."RSRP"  AS bs_rsrp,
    g."RSRQ"  AS bs_rsrq,
    g."SINR"  AS bs_sinr,
    g."Dbm"   AS bs_dbm
FROM rebuild2._tmp_gps_fixed g
JOIN rebuild2._tmp_bs_main_cell mc
    ON g.op      = mc.op
   AND g.tech    = mc.tech
   AND g.lac     = mc.lac
   AND g.cell_id = mc.main_cell_id
WHERE g."RSRP" IS NOT NULL AND g."RSRP" < 0 AND g."RSRP" NOT IN (-1, -110)
ORDER BY g.op, g.tech, g.lac, g.bs_id, g."上报时间" DESC;

CREATE UNIQUE INDEX ON rebuild2._tmp_main_cell_signal(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_main_cell_signal;

-- 4.4 组装最终 dwd_fact_enriched
DROP TABLE IF EXISTS rebuild2.dwd_fact_enriched;
CREATE TABLE rebuild2.dwd_fact_enriched AS
SELECT
    s.l0_row_id,
    s.op         AS operator_code,
    s.tech       AS tech_norm,
    s.lac,
    s.cell_id,
    s.bs_id,
    s.lon_final,
    s.lat_final,
    s.gps_source,
    s."上报时间"  AS report_time,
    s.dev_id,
    -- 信号最终值（优先级：原始 → SS原始值 → 同Cell最近邻 → BS主Cell回退）
    COALESCE(
        CASE WHEN s.rsrp_raw IS NOT NULL AND s.rsrp_raw < 0
                  AND s.rsrp_raw NOT IN (-1, -110) THEN s.rsrp_raw END,
        CASE WHEN s.ss_raw IS NOT NULL AND s.ss_raw::int < 0
                  AND s.ss_raw::int NOT IN (-1, -110) THEN s.ss_raw::int END,
        s.rsrp_lag,
        s.rsrp_lead,
        mcs.bs_rsrp
    ) AS rsrp_final,
    COALESCE(
        CASE WHEN s.rsrq_raw IS NOT NULL THEN s.rsrq_raw END,
        s.rsrq_lag,
        s.rsrq_lead,
        mcs.bs_rsrq
    ) AS rsrq_final,
    COALESCE(
        CASE WHEN s.sinr_raw IS NOT NULL THEN s.sinr_raw END,
        s.sinr_lag,
        s.sinr_lead,
        mcs.bs_sinr
    ) AS sinr_final,
    COALESCE(
        CASE WHEN s.dbm_raw IS NOT NULL THEN s.dbm_raw END,
        s.dbm_lag,
        s.dbm_lead,
        mcs.bs_dbm
    ) AS dbm_final,
    -- 信号补齐来源（5 级优先级）
    CASE
        WHEN s.rsrp_raw IS NOT NULL AND s.rsrp_raw < 0
             AND s.rsrp_raw NOT IN (-1, -110)          THEN 'original'
        WHEN s.ss_raw IS NOT NULL AND s.ss_raw::int < 0
             AND s.ss_raw::int NOT IN (-1, -110)       THEN 'original_ss'
        WHEN COALESCE(s.rsrp_lag, s.rsrp_lead) IS NOT NULL THEN 'cell_fill'
        WHEN mcs.bs_rsrp IS NOT NULL                   THEN 'bs_fill'
        ELSE 'unfilled'
    END AS signal_fill_source
FROM rebuild2._tmp_signal_s1 s
LEFT JOIN rebuild2._tmp_main_cell_signal mcs
    ON s.op   = mcs.op
   AND s.tech = mcs.tech
   AND s.lac  = mcs.lac
   AND s.bs_id = mcs.bs_id;

CREATE INDEX ON rebuild2.dwd_fact_enriched(operator_code, tech_norm, lac, cell_id);
CREATE INDEX ON rebuild2.dwd_fact_enriched(operator_code, tech_norm, lac, bs_id);
CREATE INDEX ON rebuild2.dwd_fact_enriched(dev_id);
CREATE INDEX ON rebuild2.dwd_fact_enriched(report_time);
CREATE INDEX ON rebuild2.dwd_fact_enriched(gps_source);
CREATE INDEX ON rebuild2.dwd_fact_enriched(signal_fill_source);
ANALYZE rebuild2.dwd_fact_enriched;

-- 清理临时表（保留 _tmp_gps_fixed 直到 Step 5 完成）
DROP TABLE IF EXISTS rebuild2._tmp_signal_s1;
DROP TABLE IF EXISTS rebuild2._tmp_bs_main_cell;
DROP TABLE IF EXISTS rebuild2._tmp_main_cell_signal;

SELECT 'Step 4 完成: dwd_fact_enriched 已创建' AS status;
```

**✅ 检查点 4**（MCP 验证）：

```sql
-- 总量核查 + 信号覆盖
SELECT
    count(*)                                              AS total_rows,
    count(*) FILTER (WHERE rsrp_final IS NOT NULL)       AS rsrp_filled,
    ROUND(100.0 * count(*) FILTER (WHERE rsrp_final IS NOT NULL) / count(*), 2) AS rsrp_fill_pct,
    count(*) FILTER (WHERE rsrq_final IS NOT NULL)       AS rsrq_filled,
    count(*) FILTER (WHERE sinr_final IS NOT NULL)       AS sinr_filled,
    count(*) FILTER (WHERE dbm_final  IS NOT NULL)       AS dbm_filled,
    count(*) FILTER (WHERE lon_final  IS NOT NULL)       AS gps_filled,
    count(DISTINCT dev_id)                               AS distinct_devices
FROM rebuild2.dwd_fact_enriched;
```

- total_rows 应与 _tmp_gps_fixed 一致（~3000 万），偏差 0 行
- rsrp_fill_pct 预期 > **85%**（信号补齐后大幅提升）
- 如果 rsrp_fill_pct < 70%，说明信号补齐效果不佳，需排查

```sql
-- 信号补齐来源分布
SELECT
    signal_fill_source,
    count(*)                                              AS row_count,
    ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2)   AS pct,
    count(DISTINCT dev_id)                               AS device_count
FROM rebuild2.dwd_fact_enriched
GROUP BY signal_fill_source
ORDER BY row_count DESC;
```

- **original** 预期约 **60~80%**（原始有效 RSRP）
- **original_ss** 预期约 **1~5%**（RSRP 空但 SS原始值 有效，5G 为主）
- **cell_fill** 预期约 **5~15%**（LAG/LEAD 同 Cell 时间最近邻补齐）
- **bs_fill** 预期约 **1~5%**（BS 主要 Cell 回退补齐）
- **unfilled** 预期 < **5%**（无法补齐，通常是孤立 BS 或全 Cell 无信号）

```sql
-- GPS 来源 × 信号补齐来源交叉（top 10）
SELECT gps_source, signal_fill_source, count(*) AS cnt
FROM rebuild2.dwd_fact_enriched
GROUP BY gps_source, signal_fill_source
ORDER BY cnt DESC
LIMIT 10;
```

---

## STEP 5：回算 → 更新 dim_cell_refined + dim_bs_refined

> 预计耗时：**3~8 分钟**（GROUP BY ~30M 行 + UPDATE ~573K / ~193K 行）

基于 dwd_fact_enriched 的修正后 GPS（lon_final / lat_final），用同样的分箱中位数方法重算 Cell 和 BS 的 GPS 中心点。结果写入新增的 `_recalc` 列，**不覆盖**原始精算值，用于对比和后续分析。

```sql
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step 5: 回算
-- 基于 dwd_fact_enriched 修正后 GPS 重算 Cell / BS 中心点
-- 新增 _recalc 列，不覆盖原始精算值
-- ============================================================

-- 5.1 按 Cell 重算中心点（分箱中位数，使用修正后 GPS）
DROP TABLE IF EXISTS rebuild2._tmp_cell_recalc;
CREATE TABLE rebuild2._tmp_cell_recalc AS
SELECT
    operator_code, tech_norm, lac, cell_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lon_final * 10000)::int)
        / 10000.0 AS new_clon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(lat_final * 10000)::int)
        / 10000.0 AS new_clat,
    count(*) AS gps_count_recalc
FROM rebuild2.dwd_fact_enriched
WHERE lon_final IS NOT NULL
GROUP BY operator_code, tech_norm, lac, cell_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_cell_recalc(operator_code, tech_norm, lac, cell_id);
ANALYZE rebuild2._tmp_cell_recalc;

-- 5.2 按 BS 重算中心点（从 Cell 回算中心聚合）
DROP TABLE IF EXISTS rebuild2._tmp_bs_recalc;
CREATE TABLE rebuild2._tmp_bs_recalc AS
SELECT
    cr.operator_code, cr.tech_norm, cr.lac, cr.bs_id,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(rc.new_clon * 10000)::int)
        / 10000.0 AS new_bs_lon,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY round(rc.new_clat * 10000)::int)
        / 10000.0 AS new_bs_lat,
    sum(rc.gps_count_recalc) AS gps_count_recalc
FROM rebuild2.dim_cell_refined cr
JOIN rebuild2._tmp_cell_recalc rc
    ON cr.operator_code = rc.operator_code
   AND cr.tech_norm     = rc.tech_norm
   AND cr.lac           = rc.lac
   AND cr.cell_id       = rc.cell_id
GROUP BY cr.operator_code, cr.tech_norm, cr.lac, cr.bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_recalc(operator_code, tech_norm, lac, bs_id);
ANALYZE rebuild2._tmp_bs_recalc;

-- 5.3 写回 dim_cell_refined（新增 _recalc 列）
ALTER TABLE rebuild2.dim_cell_refined
    ADD COLUMN IF NOT EXISTS gps_center_lon_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_center_lat_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_count_recalc       int;

UPDATE rebuild2.dim_cell_refined cr
SET
    gps_center_lon_recalc = rc.new_clon,
    gps_center_lat_recalc = rc.new_clat,
    gps_count_recalc      = rc.gps_count_recalc
FROM rebuild2._tmp_cell_recalc rc
WHERE cr.operator_code = rc.operator_code
  AND cr.tech_norm     = rc.tech_norm
  AND cr.lac           = rc.lac
  AND cr.cell_id       = rc.cell_id;

-- 5.4 写回 dim_bs_refined（新增 _recalc 列）
ALTER TABLE rebuild2.dim_bs_refined
    ADD COLUMN IF NOT EXISTS gps_center_lon_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_center_lat_recalc float8,
    ADD COLUMN IF NOT EXISTS gps_count_recalc       int;

UPDATE rebuild2.dim_bs_refined br
SET
    gps_center_lon_recalc = rc.new_bs_lon,
    gps_center_lat_recalc = rc.new_bs_lat,
    gps_count_recalc      = rc.gps_count_recalc
FROM rebuild2._tmp_bs_recalc rc
WHERE br.operator_code = rc.operator_code
  AND br.tech_norm     = rc.tech_norm
  AND br.lac           = rc.lac
  AND br.bs_id         = rc.bs_id;

-- 清理临时表
DROP TABLE IF EXISTS rebuild2._tmp_cell_recalc;
DROP TABLE IF EXISTS rebuild2._tmp_bs_recalc;
DROP TABLE IF EXISTS rebuild2._tmp_gps_fixed;

SELECT 'Step 5 完成: dim_cell_refined / dim_bs_refined 回算列已更新' AS status;
```

**✅ 检查点 5**（MCP 验证）：

```sql
-- Cell 中心点回算覆盖情况
SELECT
    count(*)                                                          AS total_cells,
    count(*) FILTER (WHERE gps_center_lon IS NOT NULL
        AND gps_center_lon_recalc IS NOT NULL)                       AS comparable_cells,
    count(*) FILTER (WHERE gps_center_lon_recalc IS NOT NULL
        AND gps_center_lon IS NULL)                                  AS newly_covered_cells,
    count(*) FILTER (WHERE gps_center_lon_recalc IS NULL)            AS no_recalc
FROM rebuild2.dim_cell_refined;
```

- comparable_cells 是可以做新旧对比的 Cell 数
- newly_covered_cells > 0 说明 GPS 填充后新增了有 GPS 的 Cell（符合预期）

```sql
-- Cell 中心点漂移分析（新旧对比）
SELECT
    count(*) FILTER (WHERE
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) <= 50
    ) AS drift_le_50m,
    count(*) FILTER (WHERE
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) BETWEEN 50 AND 100
    ) AS drift_50_100m,
    count(*) FILTER (WHERE
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 100
    ) AS drift_gt_100m,
    count(*) FILTER (WHERE
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 500
    ) AS drift_gt_500m,
    ROUND(AVG(
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2))
    ) FILTER (WHERE gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL)::numeric, 0) AS avg_drift_m
FROM rebuild2.dim_cell_refined
WHERE gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL;
```

- 大部分 Cell avg_drift_m 应 < 100m（填充后 Cell 中心对多数 Cell 影响小）
- drift_gt_500m 是填充明显改变中心点估计的 Cell，属正常

```sql
-- BS 中心点回算对比
SELECT
    count(*) FILTER (WHERE gps_center_lon IS NOT NULL
        AND gps_center_lon_recalc IS NOT NULL)          AS comparable_bs,
    count(*) FILTER (WHERE gps_center_lon_recalc IS NOT NULL
        AND gps_center_lon IS NULL)                     AS newly_covered_bs,
    count(*) FILTER (WHERE
        gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL AND
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 100
    ) AS drift_gt_100m,
    count(*) FILTER (WHERE
        gps_center_lon IS NOT NULL AND gps_center_lon_recalc IS NOT NULL AND
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2)) > 500
    ) AS drift_gt_500m,
    ROUND(AVG(
        SQRT(POWER((gps_center_lon_recalc - gps_center_lon) * 85300, 2) +
             POWER((gps_center_lat_recalc - gps_center_lat) * 111000, 2))
    ) FILTER (WHERE gps_center_lon IS NOT NULL
        AND gps_center_lon_recalc IS NOT NULL)::numeric, 0) AS avg_drift_m
FROM rebuild2.dim_bs_refined;
```

---

## 最终验证摘要

执行完成后，用 MCP 运行以下汇总查询并报告：

```sql
-- Phase 3 Steps 2-5 产出汇总
SELECT 'dim_cell_refined'    AS tbl, count(*) AS n FROM rebuild2.dim_cell_refined
UNION ALL
SELECT 'dwd_fact_enriched',           count(*) FROM rebuild2.dwd_fact_enriched
UNION ALL
SELECT 'dim_bs_refined(总)',           count(*) FROM rebuild2.dim_bs_refined
UNION ALL
SELECT 'dim_bs_refined(有recalc)',     count(*) FROM rebuild2.dim_bs_refined
    WHERE gps_center_lon_recalc IS NOT NULL;
```

```sql
-- dwd_fact_enriched 信号覆盖最终值
SELECT
    ROUND(100.0 * count(*) FILTER (WHERE rsrp_final IS NOT NULL) / count(*), 2) AS rsrp_fill_pct,
    ROUND(100.0 * count(*) FILTER (WHERE lon_final  IS NOT NULL) / count(*), 2) AS gps_fill_pct
FROM rebuild2.dwd_fact_enriched;
```

向用户报告以下信息：

1. **dim_cell_refined 行数**（应 = 573,561）
2. **GPS 异常率**：anomaly_cells / cells_with_gps
3. **_tmp_gps_fixed GPS 覆盖率**：gps_coverage_pct（预期 > 90%）
4. **GPS 来源分布**：original / cell_center / bs_center / bs_center_risk / not_filled 各占比
5. **dwd_fact_enriched 行数 + RSRP 补齐率**（预期 > 85%）
6. **信号补齐来源分布**：original / original_ss / cell_fill / bs_fill / unfilled 各占比
7. **Cell / BS 中心点漂移**：avg_drift_m（回算 vs 原始精算）、newly_covered 数量
8. **各步骤耗时**（psql `\timing` 输出）
9. **异常项**：如有异常（行数不匹配、gps_coverage_pct < 80%、rsrp_fill_pct < 70% 等）需报告

---

## 估计耗时

| 步骤 | 预计耗时 | 说明 |
|------|----------|------|
| STEP 2 | 3~8 分钟 | 扫描 l0_lac + JOIN BS 中心 + 建索引 |
| STEP 3 | 10~20 分钟 | 物化 30M 行 + JOIN 两张字典表 + 建多个索引（**重型步骤**） |
| STEP 4 | 15~25 分钟 | 窗口函数 LAG/LEAD 全量排序 + 主 Cell 信号回退 + 建索引（**最重步骤**） |
| STEP 5 | 3~8 分钟 | GROUP BY 30M 行 + UPDATE Cell/BS 两张表 |
| **总计** | **31~61 分钟** | 含 Step 3/4 重型操作 |

> 注意：Steps 3 和 4 均处理 30M+ 行，执行期间 PostgreSQL 会大量占用磁盘 I/O 和 CPU，请勿在此期间运行其他重型查询。
