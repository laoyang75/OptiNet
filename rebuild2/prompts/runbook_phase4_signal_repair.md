# Runbook：Phase 4 信号补齐修复 — 重建 Step 3~5

> 身份：**执行 Agent**
> 任务：修复 Phase 4 审计发现的 3 个信号补齐 Bug，重建 _tmp_gps_fixed → dwd_fact_enriched → 回算列
> 产出：修复后的 `rebuild2.dwd_fact_enriched`（~30M 行）、更新后的 dim_cell_refined / dim_bs_refined `_recalc` 列
> **必须严格按步骤执行，每步有检查点，检查不通过不能继续**

---

## 修复的 3 个 Bug

| # | Bug | 根因 | 修复方式 |
|---|-----|------|---------|
| 1 | LAG/LEAD 传播 RSRP 哨兵值 -110 | _tmp_signal_s1 的窗口函数未过滤 -1/-110 | LAG/LEAD 中加 CASE 过滤 |
| 2 | SS原始值未被利用 | _tmp_gps_fixed 未携带 SS原始值字段 | 传递 SS原始值 + 加入 COALESCE 链 |
| 3 | bs_fill 被 cell_fill 吞掉（0 行） | Bug 1 导致 -110 被 LAG/LEAD 命中 → cell_fill | 修复 Bug 1 后自动恢复 |

---

## 环境信息

- **SSH**：`sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217`
- **PG17**：`PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2`
- **MCP 工具**：`mcp__PG17__execute_sql`（用于测试和验证）

---

## 前置条件

| 表 | 预期行数 | 作用 |
|----|----------|------|
| `rebuild2.l0_lac` | 43,771,306 | 明细源表 |
| `rebuild2.dim_lac_trusted` | 1,057 | 可信 LAC 白名单 |
| `rebuild2.dim_bs_refined` | 193,036 | BS 精算维表 |
| `rebuild2.dim_cell_refined` | 573,561 | Cell 精算维表 |

**先用 MCP 验证前置条件**：

```sql
SELECT 'l0_lac'          AS tbl, count(*) AS n FROM rebuild2.l0_lac
UNION ALL SELECT 'dim_lac_trusted',  count(*) FROM rebuild2.dim_lac_trusted
UNION ALL SELECT 'dim_bs_refined',   count(*) FROM rebuild2.dim_bs_refined
UNION ALL SELECT 'dim_cell_refined', count(*) FROM rebuild2.dim_cell_refined;
```

**✅ 检查点 0**：四张表存在且行数与预期一致。不通过则停止。

---

## 修复前基线快照

**在修复之前，先记录当前状态作为对比基线**：

```sql
-- 基线 B1: 当前 signal_fill_source 分布
SELECT
    signal_fill_source,
    count(*) AS cnt,
    ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1
ORDER BY 2 DESC;
```

```sql
-- 基线 B2: 当前各信号字段有值率
SELECT
    ROUND(100.0 * count(*) FILTER (WHERE rsrp_final IS NOT NULL) / count(*), 2) AS rsrp_pct,
    ROUND(100.0 * count(*) FILTER (WHERE rsrq_final IS NOT NULL) / count(*), 2) AS rsrq_pct,
    ROUND(100.0 * count(*) FILTER (WHERE sinr_final IS NOT NULL) / count(*), 2) AS sinr_pct,
    ROUND(100.0 * count(*) FILTER (WHERE dbm_final  IS NOT NULL) / count(*), 2) AS dbm_pct
FROM rebuild2.dwd_fact_enriched;
```

```sql
-- 基线 B3: rsrp_final = -110 的记录数（bug 验证基线）
SELECT count(*) AS rsrp_minus110 FROM rebuild2.dwd_fact_enriched WHERE rsrp_final = -110;
```

**记录以上三个查询结果，修复后对比。**

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

## STEP R1：重建 _tmp_gps_fixed（携带 SS原始值）

> 预计耗时：**10~20 分钟**（物化 30M 行 + JOIN 两张字典表 + 建索引）
> 注意：中间表已在之前被清理，需要完全重建

```sql
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step R1: 重建 _tmp_gps_fixed（增加 SS原始值 传递）
-- ============================================================

-- R1.1 物化可信 LAC 范围内的全量行（★ 增加 ss_raw 字段）
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
    l."SS原始值"                     AS ss_raw     -- ★ 新增
FROM rebuild2.l0_lac l
JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
   AND l."标准制式"   = t.tech_norm
   AND l."LAC"        = t.lac::bigint;

CREATE INDEX ON rebuild2._tmp_l0_trusted(op, tech, lac, cell_id);
CREATE INDEX ON rebuild2._tmp_l0_trusted(dev_id);
ANALYZE rebuild2._tmp_l0_trusted;

-- R1.2 Cell GPS 字典
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

-- R1.3 BS GPS 字典
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

-- R1.4 组装 GPS 修正结果（★ 增加 SS原始值 传递）
DROP TABLE IF EXISTS rebuild2._tmp_gps_fixed;
CREATE TABLE rebuild2._tmp_gps_fixed AS
SELECT
    l.l0_row_id,
    l.op,
    l.tech,
    l.lac,
    l.cell_id,
    l.bs_id,
    -- 最终经纬度（逻辑与原 Step 3 完全一致）
    CASE
        WHEN l.gps_valid = true
             AND l.raw_lon BETWEEN 73 AND 135
             AND l.raw_lat BETWEEN 3 AND 54
             AND c.cell_lon IS NOT NULL
             AND NOT COALESCE(c.gps_anomaly, false)
             AND SQRT(POWER((l.raw_lon - c.cell_lon) * 85300, 2) +
                      POWER((l.raw_lat - c.cell_lat) * 111000, 2))
                 <= CASE WHEN l.tech LIKE '%5G%' THEN 500 ELSE 1000 END
            THEN l.raw_lon
        WHEN c.cell_lon IS NOT NULL AND NOT COALESCE(c.gps_anomaly, false)
            THEN c.cell_lon
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
    -- GPS 来源标记（逻辑与原 Step 3 完全一致）
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
    l.ss_raw       AS "SS原始值"     -- ★ 新增
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

-- 清理中间字典表
DROP TABLE IF EXISTS rebuild2._tmp_l0_trusted;
DROP TABLE IF EXISTS rebuild2._tmp_cell_gps_dict;
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps_dict;

SELECT 'Step R1 完成: _tmp_gps_fixed 已重建（含 SS原始值）' AS status;
```

**✅ 检查点 R1**（MCP 验证）：

```sql
-- 总量核查
SELECT
    count(*) AS total_rows,
    count(*) FILTER (WHERE lon_final IS NOT NULL) AS rows_with_gps,
    ROUND(100.0 * count(*) FILTER (WHERE lon_final IS NOT NULL) / count(*), 2) AS gps_pct,
    count(*) FILTER (WHERE "SS原始值" IS NOT NULL) AS rows_with_ss
FROM rebuild2._tmp_gps_fixed;
```

- total_rows 必须 = **30,082,381**（与原 dwd_fact_enriched 一致）
- gps_pct 应 > 99.9%
- rows_with_ss 应 > 0（验证 SS 字段已传递）
- **不通过则停止排查**

```sql
-- GPS 来源分布（必须与原 dwd_fact_enriched 完全一致）
SELECT gps_source, count(*) AS cnt FROM rebuild2._tmp_gps_fixed GROUP BY 1 ORDER BY 2 DESC;
```

| gps_source | 期望行数 |
|---|---:|
| original | 23,433,892 |
| cell_center | 5,816,353 |
| bs_center | 815,114 |
| bs_center_risk | 13,889 |
| not_filled | 3,133 |

- **与原审计完全一致才能继续**。GPS 修正逻辑未变，行数必须匹配。

---

## STEP R2：重建信号补齐 → dwd_fact_enriched

> 预计耗时：**15~25 分钟**（窗口函数 + BS 回退 + 重建索引）

```sql
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step R2: 信号补齐修复版
-- ★ 修复 1: LAG/LEAD 过滤哨兵值 -1/-110
-- ★ 修复 2: 携带 SS原始值
-- ============================================================

-- R2.1 Stage 1：同 Cell 内 LAG/LEAD 时间最近邻补齐（修复版）
DROP TABLE IF EXISTS rebuild2._tmp_signal_s1;
CREATE TABLE rebuild2._tmp_signal_s1 AS
SELECT
    l0_row_id,
    op, tech, lac, cell_id, bs_id,
    lon_final, lat_final, gps_source,
    "上报时间",
    "设备标识"  AS dev_id,
    -- 原始信号
    "RSRP"     AS rsrp_raw,
    "RSRQ"     AS rsrq_raw,
    "SINR"     AS sinr_raw,
    "Dbm"      AS dbm_raw,
    "SS原始值"  AS ss_raw,     -- ★ 新增
    -- ★ 修复：LAG/LEAD 过滤哨兵值 -1 和 -110
    LAG(CASE WHEN "RSRP" < 0 AND "RSRP" NOT IN (-1, -110) THEN "RSRP" END)
        IGNORE NULLS OVER w AS rsrp_lag,
    LEAD(CASE WHEN "RSRP" < 0 AND "RSRP" NOT IN (-1, -110) THEN "RSRP" END)
        IGNORE NULLS OVER w AS rsrp_lead,
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

-- R2.2 同 BS 内记录数最多的主要 Cell（Stage 2 回退目标）
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

-- R2.3 主要 Cell 中最近的信号值
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

-- R2.4 组装最终 dwd_fact_enriched（修复版）
-- ★ 先备份旧表
ALTER TABLE rebuild2.dwd_fact_enriched RENAME TO dwd_fact_enriched_backup_pre_repair;

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
    -- ★ 修复：信号最终值（优先级：原始 → SS原始值 → 同Cell最近邻 → BS主Cell回退）
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
    -- ★ 修复：信号补齐来源（5 级优先级）
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

-- 清理临时表（保留 _tmp_gps_fixed 直到 Step R3 完成）
DROP TABLE IF EXISTS rebuild2._tmp_signal_s1;
DROP TABLE IF EXISTS rebuild2._tmp_bs_main_cell;
DROP TABLE IF EXISTS rebuild2._tmp_main_cell_signal;

SELECT 'Step R2 完成: dwd_fact_enriched 已修复重建' AS status;
```

**✅ 检查点 R2**（MCP 验证 — 核心检查）：

```sql
-- R2-C1: 总量必须一致
SELECT count(*) AS total FROM rebuild2.dwd_fact_enriched;
-- 必须 = 30,082,381
```

```sql
-- R2-C2: signal_fill_source 分布（核心验证）
SELECT
    signal_fill_source,
    count(*) AS cnt,
    ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1
ORDER BY 2 DESC;
```

**期望结果**：

| signal_fill_source | 期望 |
|---|---|
| original | ~88%（与修复前接近，略降因部分 -110 不再算 cell_fill） |
| original_ss | ~1~3%（新增，5G 为主） |
| cell_fill | ~5~8%（比修复前低，因为不再传播 -110） |
| bs_fill | ~0.5~3%（**不再为 0**，这是 Bug 3 修复的核心验证） |
| unfilled | ~2~4%（比修复前低，因为 SS 救回了一部分） |

**关键验证**：
- ✅ `bs_fill` 行数 > 0（Bug 3 已修复）
- ✅ `original_ss` 行数 > 0（Bug 2 已修复）
- ✅ 总行数 = 30,082,381

```sql
-- R2-C3: Bug 1 验证 — rsrp_final = -110 应为 0
SELECT count(*) AS rsrp_minus110 FROM rebuild2.dwd_fact_enriched WHERE rsrp_final = -110;
-- 必须 = 0
```

```sql
-- R2-C4: 各信号字段有值率
SELECT
    ROUND(100.0 * count(*) FILTER (WHERE rsrp_final IS NOT NULL) / count(*), 2) AS rsrp_pct,
    ROUND(100.0 * count(*) FILTER (WHERE rsrq_final IS NOT NULL) / count(*), 2) AS rsrq_pct,
    ROUND(100.0 * count(*) FILTER (WHERE sinr_final IS NOT NULL) / count(*), 2) AS sinr_pct,
    ROUND(100.0 * count(*) FILTER (WHERE dbm_final  IS NOT NULL) / count(*), 2) AS dbm_pct
FROM rebuild2.dwd_fact_enriched;
```

- rsrp_pct 应 > 95.85%（修复前 95.85%，SS 补救 + bs_fill 还原后应微升）
- **RSRP 有值率不应低于修复前**（如果显著下降说明修复有问题）

```sql
-- R2-C5: 按制式分布验证
SELECT
    tech_norm,
    signal_fill_source,
    count(*) AS cnt,
    ROUND(100.0 * count(*) FILTER (WHERE rsrp_final IS NOT NULL) / count(*), 1) AS rsrp_pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1, 2
ORDER BY 1, 2;
```

- 5G 的 original_ss 应有 ~30 万行
- 4G 的 original_ss 应极少（4G 中 SS 和 RSRP 几乎总是同时有值）

```sql
-- R2-C6: GPS 来源分布必须与修复前完全一致（GPS 逻辑未变）
SELECT gps_source, count(*) AS cnt FROM rebuild2.dwd_fact_enriched GROUP BY 1 ORDER BY 2 DESC;
```

| gps_source | 期望行数 |
|---|---:|
| original | 23,433,892 |
| cell_center | 5,816,353 |
| bs_center | 815,114 |
| bs_center_risk | 13,889 |
| not_filled | 3,133 |

- **与审计基线完全一致才能继续**

---

## STEP R3：重跑回算（更新 _recalc 列）

> 预计耗时：**3~8 分钟**
> GPS 逻辑未变，回算结果应与修复前一致。但必须重跑以保证一致性。

```sql
SET statement_timeout = 0;
SET work_mem = '256MB';
SET max_parallel_workers_per_gather = 0;

-- ============================================================
-- Step R3: 回算更新 _recalc 列
-- ============================================================

-- R3.1 按 Cell 重算中心点
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

-- R3.2 按 BS 重算中心点
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

-- R3.3 写回 dim_cell_refined
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

-- R3.4 写回 dim_bs_refined
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

SELECT 'Step R3 完成: _recalc 列已更新' AS status;
```

**✅ 检查点 R3**（MCP 验证）：

```sql
-- 回算覆盖
SELECT
    count(*) AS total_cells,
    count(*) FILTER (WHERE gps_center_lon_recalc IS NOT NULL) AS has_recalc
FROM rebuild2.dim_cell_refined;
```

```sql
SELECT
    count(*) AS total_bs,
    count(*) FILTER (WHERE gps_center_lon_recalc IS NOT NULL) AS has_recalc
FROM rebuild2.dim_bs_refined;
```

- Cell 回算覆盖数应与修复前一致（GPS 逻辑未变）
- BS 回算覆盖数同上

---

## 修复后完整审计

**修复完成后，重跑 Phase 4 审计关键查询验证修复效果**：

```sql
-- 审计 A1: signal_fill_source 分布（修复后 vs 修复前对比）
SELECT
    signal_fill_source,
    count(*) AS cnt,
    ROUND(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1
ORDER BY 2 DESC;
```

```sql
-- 审计 A2: 各信号字段有值率
SELECT
    ROUND(100.0 * count(*) FILTER (WHERE rsrp_final IS NOT NULL) / count(*), 2) AS rsrp_pct,
    ROUND(100.0 * count(*) FILTER (WHERE rsrq_final IS NOT NULL) / count(*), 2) AS rsrq_pct,
    ROUND(100.0 * count(*) FILTER (WHERE sinr_final IS NOT NULL) / count(*), 2) AS sinr_pct,
    ROUND(100.0 * count(*) FILTER (WHERE dbm_final  IS NOT NULL) / count(*), 2) AS dbm_pct
FROM rebuild2.dwd_fact_enriched;
```

```sql
-- 审计 A3: rsrp_final = -110 验证（必须 = 0）
SELECT count(*) AS rsrp_minus110 FROM rebuild2.dwd_fact_enriched WHERE rsrp_final = -110;
```

```sql
-- 审计 A4: 值域检查
SELECT
  MIN(rsrp_final) AS rsrp_min, MAX(rsrp_final) AS rsrp_max,
  MIN(rsrq_final) AS rsrq_min, MAX(rsrq_final) AS rsrq_max,
  MIN(sinr_final) AS sinr_min, MAX(sinr_final) AS sinr_max,
  MIN(dbm_final)  AS dbm_min,  MAX(dbm_final)  AS dbm_max,
  COUNT(*) FILTER (WHERE rsrp_final >= 0) AS rsrp_positive,
  COUNT(*) FILTER (WHERE rsrp_final = -1) AS rsrp_minus1,
  COUNT(*) FILTER (WHERE dbm_final >= 0)  AS dbm_positive
FROM rebuild2.dwd_fact_enriched;
```

```sql
-- 审计 A5: 按制式拆分信号有值率
SELECT
  tech_norm,
  signal_fill_source,
  count(*) AS total,
  ROUND(COUNT(*) FILTER (WHERE rsrp_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS rsrp_pct,
  ROUND(COUNT(*) FILTER (WHERE rsrq_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS rsrq_pct,
  ROUND(COUNT(*) FILTER (WHERE sinr_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS sinr_pct,
  ROUND(COUNT(*) FILTER (WHERE dbm_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS dbm_pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1, 2
ORDER BY 1, 2;
```

```sql
-- 审计 A6: GPS 来源分布（不应变化）
SELECT gps_source, count(*) AS cnt FROM rebuild2.dwd_fact_enriched GROUP BY 1 ORDER BY 2 DESC;
```

---

## 产出报告格式

修复完成后，产出 **修复前后对比表**：

| 指标 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| total_rows | 30,082,381 | ? | 必须一致 |
| rsrp_pct | 95.85% | ? | 应提升 |
| rsrq_pct | 95.49% | ? | 可能微变 |
| sinr_pct | 85.71% | ? | 可能微变 |
| dbm_pct | 93.33% | ? | 可能微变 |
| rsrp_minus110 | 42,458 | ? | 必须 = 0 |
| original 行数 | 26,659,361 | ? | 应一致 |
| original_ss 行数 | 0 | ? | 应 > 0 |
| cell_fill 行数 | 2,175,271 | ? | 应下降 |
| bs_fill 行数 | 0 | ? | **应 > 0** |
| unfilled 行数 | 1,247,749 | ? | 应下降 |

加上修复验证清单：

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | rsrp_final = -110 为 0 | ✅/❌ |
| 2 | bs_fill 行数 > 0 | ✅/❌ |
| 3 | original_ss 行数 > 0 | ✅/❌ |
| 4 | GPS 分布与修复前完全一致 | ✅/❌ |
| 5 | 总行数 = 30,082,381 | ✅/❌ |
| 6 | rsrp_pct >= 95.85% | ✅/❌ |
| 7 | 值域无异常（无正数、无 -1） | ✅/❌ |

**全部 7 项通过后，删除备份表**：

```sql
DROP TABLE IF EXISTS rebuild2.dwd_fact_enriched_backup_pre_repair;
```

**如有任何项不通过，回滚**：

```sql
-- 回滚
DROP TABLE IF EXISTS rebuild2.dwd_fact_enriched;
ALTER TABLE rebuild2.dwd_fact_enriched_backup_pre_repair RENAME TO dwd_fact_enriched;
```

---

## 估计耗时

| 步骤 | 预计耗时 | 说明 |
|------|----------|------|
| 基线快照 | 1~2 分钟 | 3 个查询 |
| STEP R1 | 10~20 分钟 | 重建 _tmp_gps_fixed（**重型步骤**） |
| STEP R2 | 15~25 分钟 | 信号补齐修复版（**最重步骤**） |
| STEP R3 | 3~8 分钟 | 回算 _recalc 列 |
| 修复后审计 | 2~5 分钟 | 6 个验证查询 |
| **总计** | **31~60 分钟** | 含 R1/R2 重型操作 |

> 注意：Steps R1 和 R2 均处理 30M+ 行，执行期间 PostgreSQL 会大量占用磁盘 I/O 和 CPU，请勿在此期间运行其他重型查询。
