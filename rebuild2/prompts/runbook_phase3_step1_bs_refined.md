# Runbook：Phase 3 Step 1 — BS 中心点精算

> 身份：**执行 Agent**
> 任务：从 l0_lac 提取 GPS+RSRP 有效记录，通过信号加权选种 + 设备去重 + 分箱中位数 + 异常剔除，精算 BS 中心点
> 产出：`rebuild2.dim_bs_refined`（193,036 行，含 GPS 质量分级）
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
| `rebuild2.l0_lac` | ~4377 万 | GPS/信号明细源表 |
| `rebuild2.dim_lac_trusted` | 1,057 | 可信 LAC 白名单 |
| `rebuild2.dim_bs_stats` | 193,036 | Phase 2 BS 统计（简单中位数，本步要替换） |
| `rebuild2.dim_cell_stats` | 573,561 | Cell 统计 |

**先用 MCP 验证前置条件**：

```sql
SELECT 'l0_lac' AS tbl, count(*) AS n FROM rebuild2.l0_lac
UNION ALL SELECT 'dim_lac_trusted', count(*) FROM rebuild2.dim_lac_trusted
UNION ALL SELECT 'dim_bs_stats', count(*) FROM rebuild2.dim_bs_stats
UNION ALL SELECT 'dim_cell_stats', count(*) FROM rebuild2.dim_cell_stats;
```

**✅ 检查点 0**：四张表都存在且行数与预期一致。不通过则停止。

---

## 算法概述

1. 从 l0_lac 提取可信 LAC 范围内、GPS 有效、RSRP 有效的记录
2. 按 BS 分组 `(运营商, 制式, LAC, bs_id)` 统计 GPS 点数
3. 设备去重：GPS 点 > 100 的 BS，每设备取 RSRP 最强的一条
4. 信号加权选种：按 RSRP 降序 — ≥50点取top50, ≥20取top20, ≥5取top80%, <5全部
5. 第一轮中心：分箱中位数 `round(lon*10000)`（精度≈11m）
6. 异常剔除：种子距中心 > 2500m → 剔除 → 重算中心（第二轮）
7. 距离指标：p50 / p90 / max
8. GPS 质量分级：Usable(≥2 Cell 有 GPS) / Risk(1 Cell) / Unusable(0 Cell)

---

## STEP 1：SSH 到服务器，设置环境

```bash
sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217

PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2

-- 进入 psql 后：
SET statement_timeout = 0;
SET work_mem = '512MB';
\timing on
```

---

## STEP 2：提取 GPS+RSRP 有效记录

从 l0_lac（~4377万行）JOIN dim_lac_trusted（1057行），过滤 GPS 有效 + RSRP 有效。

```sql
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
```

**✅ 检查点 2**（MCP 验证）：

```sql
SELECT count(*) AS total_rows,
       count(DISTINCT (op, tech, lac, bs_id)) AS distinct_bs
FROM rebuild2._tmp_bs_gps;
```

- 预期 total_rows 约 **2000~2500 万**（l0_lac 可信范围 3008万 × GPS 84% × RSRP 89% ≈ 2250万）
- 预期 distinct_bs 约 **15~19 万**
- 如果行数 < 1000万 或 > 3500万，停止排查

---

## STEP 3：BS 级 GPS 点数统计

```sql
DROP TABLE IF EXISTS rebuild2._tmp_bs_cnt;
CREATE TABLE rebuild2._tmp_bs_cnt AS
SELECT op, tech, lac, bs_id,
    count(*)              AS n,
    count(DISTINCT dev)   AS n_dev,
    count(DISTINCT cell_id) AS n_cell
FROM rebuild2._tmp_bs_gps
GROUP BY op, tech, lac, bs_id;

CREATE UNIQUE INDEX ON rebuild2._tmp_bs_cnt(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_cnt;
```

**✅ 检查点 3**（MCP 验证）：

```sql
SELECT count(*) AS total_bs,
       count(*) FILTER (WHERE n > 100) AS bs_gt100,
       count(*) FILTER (WHERE n <= 100) AS bs_le100,
       count(*) FILTER (WHERE n_cell >= 2) AS usable_preview,
       count(*) FILTER (WHERE n_cell = 1) AS risk_preview,
       ROUND(AVG(n)::numeric, 0) AS avg_points,
       MAX(n) AS max_points
FROM rebuild2._tmp_bs_cnt;
```

- 确认 total_bs 合理
- bs_gt100 反映需要设备去重的 BS 数量
- usable_preview / risk_preview 与预览数据对比（Usable~132756, Risk~59280）

---

## STEP 4：设备去重 + 信号加权选种

```sql
DROP TABLE IF EXISTS rebuild2._tmp_bs_seeds;
CREATE TABLE rebuild2._tmp_bs_seeds AS
WITH
-- >100 点 BS：每设备取 RSRP 最强的一条
deduped AS (
    SELECT DISTINCT ON (g.op, g.tech, g.lac, g.bs_id, g.dev)
        g.op, g.tech, g.lac, g.bs_id, g.lon, g.lat, g.rsrp
    FROM rebuild2._tmp_bs_gps g
    JOIN rebuild2._tmp_bs_cnt c USING (op, tech, lac, bs_id)
    WHERE c.n > 100
    ORDER BY g.op, g.tech, g.lac, g.bs_id, g.dev, g.rsrp DESC
),
-- 合并去重后 + 原始（≤100点）
all_pts AS (
    SELECT op, tech, lac, bs_id, lon, lat, rsrp FROM deduped
    UNION ALL
    SELECT g.op, g.tech, g.lac, g.bs_id, g.lon, g.lat, g.rsrp
    FROM rebuild2._tmp_bs_gps g
    JOIN rebuild2._tmp_bs_cnt c USING (op, tech, lac, bs_id)
    WHERE c.n <= 100
),
-- 按 RSRP 降序排名
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY op, tech, lac, bs_id ORDER BY rsrp DESC) AS rn,
        COUNT(*)     OVER (PARTITION BY op, tech, lac, bs_id) AS grp
    FROM all_pts
)
-- 选种：≥50→top50, ≥20→top20, ≥5→top80%, <5→全部
SELECT op, tech, lac, bs_id, lon, lat, rsrp
FROM ranked
WHERE CASE
    WHEN grp >= 50 THEN rn <= 50
    WHEN grp >= 20 THEN rn <= 20
    WHEN grp >= 5  THEN rn <= GREATEST(CEIL(grp * 0.8)::int, 1)
    ELSE true
END;

CREATE INDEX ON rebuild2._tmp_bs_seeds(op, tech, lac, bs_id);
ANALYZE rebuild2._tmp_bs_seeds;
```

**✅ 检查点 4**（MCP 验证）：

```sql
SELECT count(*) AS total_seeds,
       count(DISTINCT (op, tech, lac, bs_id)) AS distinct_bs,
       ROUND(AVG(cnt)::numeric, 1) AS avg_seeds_per_bs,
       MAX(cnt) AS max_seeds
FROM (
    SELECT op, tech, lac, bs_id, count(*) AS cnt
    FROM rebuild2._tmp_bs_seeds
    GROUP BY op, tech, lac, bs_id
) t;
```

- distinct_bs 应与 STEP 3 的 total_bs 一致
- max_seeds 应 ≤ 50（选种上限）
- avg_seeds_per_bs 应远小于 STEP 3 的 avg_points（因为做了截取）

---

## STEP 5：第一轮中心点（分箱中位数）

```sql
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
```

**✅ 检查点 5**（MCP 验证）：

```sql
SELECT count(*) AS total,
       count(*) FILTER (WHERE clon BETWEEN 115 AND 118 AND clat BETWEEN 39 AND 41) AS in_beijing,
       count(*) FILTER (WHERE clon NOT BETWEEN 73 AND 135 OR clat NOT BETWEEN 3 AND 54) AS out_of_china
FROM rebuild2._tmp_bs_c1;
```

- out_of_china 应为 0
- in_beijing 应占绝大多数（数据源是北京）

---

## STEP 6：异常剔除 + 第二轮中心点

```sql
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
```

**✅ 检查点 6**（MCP 验证）：

```sql
SELECT count(*) AS total,
       count(*) FILTER (WHERE had_outlier) AS had_outlier_cnt,
       ROUND(100.0 * count(*) FILTER (WHERE had_outlier) / count(*), 2) AS outlier_pct
FROM rebuild2._tmp_bs_c2;
```

- total 应与 STEP 5 一致（异常剔除不会消除 BS，只减少种子点）
- had_outlier_cnt 反映有多少 BS 做了异常剔除（预期占少数）

---

## STEP 7：距离指标

```sql
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
```

**✅ 检查点 7**（MCP 验证）：

```sql
SELECT
    count(*) AS total,
    ROUND(AVG(p50_m)::numeric, 0) AS avg_p50,
    ROUND(AVG(p90_m)::numeric, 0) AS avg_p90,
    count(*) FILTER (WHERE p90_m > 1500) AS collision_suspect,
    count(*) FILTER (WHERE p90_m > 2500) AS high_risk
FROM rebuild2._tmp_bs_dist;
```

- avg_p50 预期几百米（城区 BS 覆盖范围）
- collision_suspect (p90>1500m) 是碰撞嫌疑，后续 Part B 处理
- 如果 avg_p50 > 2000，说明数据异常，停止排查

---

## STEP 8：组装 dim_bs_refined

```sql
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
```

**✅ 检查点 8**（MCP 验证）：

```sql
-- 总览
SELECT
    count(*) AS total_bs,
    count(*) FILTER (WHERE gps_quality = 'Usable') AS usable,
    count(*) FILTER (WHERE gps_quality = 'Risk') AS risk,
    count(*) FILTER (WHERE gps_quality = 'Unusable') AS unusable,
    count(*) FILTER (WHERE gps_center_lon IS NOT NULL) AS has_center,
    count(*) FILTER (WHERE had_outlier_removal) AS outlier_removed
FROM rebuild2.dim_bs_refined;
```

- total_bs 应 = **193,036**（与 dim_bs_stats 一致）
- usable + risk + unusable = total_bs
- has_center ≈ usable + risk（有 GPS Cell 的 BS 才有中心点）

```sql
-- 新旧中心点偏移
SELECT
    count(*) AS compared,
    count(*) FILTER (WHERE
        SQRT(POWER((gps_center_lon - old_center_lon) * 85300, 2) +
             POWER((gps_center_lat - old_center_lat) * 111000, 2)) > 100
    ) AS drift_gt_100m,
    count(*) FILTER (WHERE
        SQRT(POWER((gps_center_lon - old_center_lon) * 85300, 2) +
             POWER((gps_center_lat - old_center_lat) * 111000, 2)) > 500
    ) AS drift_gt_500m,
    ROUND(AVG(
        SQRT(POWER((gps_center_lon - old_center_lon) * 85300, 2) +
             POWER((gps_center_lat - old_center_lat) * 111000, 2))
    )::numeric, 0) AS avg_drift_m
FROM rebuild2.dim_bs_refined
WHERE gps_center_lon IS NOT NULL AND old_center_lon IS NOT NULL;
```

- 大部分 BS 偏移应 < 100m（精算 vs 简单中位数差异不大）
- drift_gt_500m 应占少数（这些是信号加权 + 异常剔除真正修正的）

```sql
-- 按运营商+制式
SELECT operator_cn, tech_norm,
    count(*) AS bs,
    count(*) FILTER (WHERE gps_quality = 'Usable') AS usable,
    count(*) FILTER (WHERE gps_quality = 'Risk') AS risk,
    count(*) FILTER (WHERE gps_quality = 'Unusable') AS unusable,
    ROUND(AVG(gps_p50_dist_m) FILTER (WHERE gps_p50_dist_m IS NOT NULL)::numeric, 0) AS avg_p50
FROM rebuild2.dim_bs_refined
GROUP BY operator_cn, tech_norm
ORDER BY bs DESC;
```

---

## STEP 9：清理临时表

```sql
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps;
DROP TABLE IF EXISTS rebuild2._tmp_bs_cnt;
DROP TABLE IF EXISTS rebuild2._tmp_bs_seeds;
DROP TABLE IF EXISTS rebuild2._tmp_bs_c1;
DROP TABLE IF EXISTS rebuild2._tmp_bs_c2;
DROP TABLE IF EXISTS rebuild2._tmp_bs_dist;
```

---

## STEP 10：记录元数据

```sql
CREATE TABLE IF NOT EXISTS rebuild2_meta.enrich_result (
    id         SERIAL PRIMARY KEY,
    step_code  TEXT NOT NULL,
    run_label  TEXT DEFAULT 'default',
    stat_key   TEXT NOT NULL,
    stat_value JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO rebuild2_meta.enrich_result (step_code, stat_key, stat_value)
SELECT 'step1_bs_refined', 'summary',
    jsonb_build_object(
        'total_bs',  count(*),
        'usable',    count(*) FILTER (WHERE gps_quality = 'Usable'),
        'risk',      count(*) FILTER (WHERE gps_quality = 'Risk'),
        'unusable',  count(*) FILTER (WHERE gps_quality = 'Unusable'),
        'has_center', count(*) FILTER (WHERE gps_center_lon IS NOT NULL),
        'outlier_removed', count(*) FILTER (WHERE had_outlier_removal)
    )
FROM rebuild2.dim_bs_refined;
```

---

## 最终验证摘要

执行完成后，向用户报告以下信息：

1. **dim_bs_refined 行数**（应 = 193,036）
2. **GPS 质量分级分布**：Usable / Risk / Unusable 各多少
3. **距离指标**：avg_p50, avg_p90, 碰撞嫌疑数(p90>1500m)
4. **新旧中心偏移**：drift_gt_100m, drift_gt_500m, avg_drift_m
5. **各步骤耗时**（psql `\timing` 输出）
6. **异常项**：如有异常（行数不匹配、out_of_china > 0、avg_p50 > 2000 等）需报告

---

## 估计耗时

| 步骤 | 预计耗时 | 说明 |
|------|----------|------|
| STEP 2 | 3~8 分钟 | 扫描 4377万行 + 建索引 |
| STEP 3 | 1~2 分钟 | GROUP BY ~2000万行 |
| STEP 4 | 2~5 分钟 | 设备去重 + 选种（最重的步骤） |
| STEP 5 | < 1 分钟 | GROUP BY ~几百万种子 |
| STEP 6 | < 1 分钟 | 距离计算 + 过滤 + 重算 |
| STEP 7 | < 1 分钟 | 距离指标 |
| STEP 8 | < 1 分钟 | LEFT JOIN 组装 |
| **总计** | **8~18 分钟** | |
