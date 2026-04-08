# Phase 4 Prompt：数据补齐完整性审计

> 用途：启动新会话，系统性检查 Phase 2~3 整条数据管线的补齐是否完整、有无遗漏
> 产出：每个环节的 **补齐前有值率 → 补齐后有值率 → 期望有值率** 对比表，标出所有异常
> 不做任何修复，只出报告。确认问题后再单独讨论修复方案

---

## 1. 环境信息

- **数据库**：PostgreSQL 17 @ 192.168.200.217:5433/ip_loc2（用户 postgres，密码 123456）
- **SSH**：`sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217`
- **MCP 工具**：`mcp__PG17__execute_sql`（查询）
- **原则**：只读不写，只查不改

---

## 2. 数据管线全景

```
原始 Legacy 表（JSON 解析 + ss1 字符串展开）
  ↓
l0_lac (43.77M)  /  l0_gps (38.43M)     ← L0 原始层
  ↓  过滤：trusted LAC + 4G/5G
dim_lac_trusted (1,057)                   ← 可信 LAC 白名单
dim_cell_stats (573,561)                  ← Cell 聚合维表
dim_bs_stats (193,036)                    ← BS 聚合维表
  ↓  Phase 3 Step 1: BS GPS 精算
dim_bs_refined (193,036)                  ← BS 精算维表（GPS 质量分级）
  ↓  Phase 3 Step 2: Cell GPS 校验
dim_cell_refined (573,561)                ← Cell 精算维表（异常标记）
  ↓  Phase 3 Step 3: GPS 修正（4 级回退）
_tmp_gps_fixed (~30.08M)                  ← GPS 修正中间表
  ↓  Phase 3 Step 4: 信号补齐（2 阶段）
dwd_fact_enriched (30,082,381)            ← 最终明细表
  ↓  Phase 3 Step 5: 反算更新维表
dim_cell_refined / dim_bs_refined (更新 _recalc 列)
```

---

## 3. 审计检查清单

按数据管线顺序逐步执行，**每步都跑 SQL 验证**。

### 检查 A：L0 原始层完整性

**目标**：确认两张 L0 表的字段覆盖率，作为后续补齐的基线。

```sql
-- A1: l0_lac 总量 + 关键字段有值率
SELECT
  COUNT(*) AS total,
  -- GPS
  COUNT(*) FILTER (WHERE "经度" IS NOT NULL AND "纬度" IS NOT NULL) AS gps_both,
  COUNT(*) FILTER (WHERE "经度" IS NOT NULL AND "纬度" IS NULL)     AS gps_lon_only,
  COUNT(*) FILTER (WHERE "经度" IS NULL AND "纬度" IS NOT NULL)     AS gps_lat_only,
  COUNT(*) FILTER (WHERE "经度" IS NULL AND "纬度" IS NULL)         AS gps_both_null,
  -- 信号
  COUNT(*) FILTER (WHERE "RSRP" IS NOT NULL)     AS rsrp_has,
  COUNT(*) FILTER (WHERE "RSRQ" IS NOT NULL)     AS rsrq_has,
  COUNT(*) FILTER (WHERE "SINR" IS NOT NULL)     AS sinr_has,
  COUNT(*) FILTER (WHERE "Dbm" IS NOT NULL)      AS dbm_has,
  COUNT(*) FILTER (WHERE "SS原始值" IS NOT NULL)  AS ss_has,
  -- SS原始值有但RSRP没有（关键遗漏指标）
  COUNT(*) FILTER (WHERE "SS原始值" IS NOT NULL AND "RSRP" IS NULL) AS ss_only_no_rsrp,
  -- 制式分布
  COUNT(*) FILTER (WHERE "标准制式" = '4G') AS cnt_4g,
  COUNT(*) FILTER (WHERE "标准制式" = '5G') AS cnt_5g
FROM rebuild2.l0_lac;

-- A2: l0_gps 同样检查
-- (同上 SQL 改 FROM rebuild2.l0_gps)
```

```sql
-- A3: l0_lac 中 SS原始值 的值域分析（确认是否等价于 RSRP）
SELECT
  "标准制式",
  COUNT(*) AS cnt,
  MIN("SS原始值"::int) AS ss_min,
  MAX("SS原始值"::int) AS ss_max,
  AVG("SS原始值"::numeric)::int AS ss_avg,
  -- 同时有 RSRP 和 SS 时，差异有多大？
  AVG(ABS("RSRP"::numeric - "SS原始值"::numeric)) FILTER (WHERE "RSRP" IS NOT NULL AND "SS原始值" IS NOT NULL)::numeric(10,1) AS avg_diff
FROM rebuild2.l0_lac
WHERE "SS原始值" IS NOT NULL
GROUP BY 1;
```

**期望**：
- SS原始值 值域 -157~0，均值约 -87~-90，与 RSRP 一致
- 5G 中有大量 SS原始值 有值但 RSRP 空的记录
- 同时有值时差异应接近 0（说明是同一指标的不同字段名）

---

### 检查 B：Trusted 过滤损耗

**目标**：确认从 L0 到 trusted 范围过滤了多少数据，过滤是否合理。

```sql
-- B1: l0_lac 按 trusted 过滤后保留多少
SELECT
  COUNT(*) AS l0_total,
  COUNT(*) FILTER (WHERE t.lac IS NOT NULL) AS trusted_match,
  COUNT(*) FILTER (WHERE t.lac IS NULL) AS filtered_out
FROM rebuild2.l0_lac l
LEFT JOIN rebuild2.dim_lac_trusted t
  ON l."运营商编码" = t.operator_code
  AND l."标准制式" = t.tech_norm
  AND l."LAC" = t.lac::bigint;
```

```sql
-- B2: 被过滤掉的数据中，有多少有 GPS 和信号？（确认不是误杀好数据）
SELECT
  COUNT(*) AS filtered_total,
  COUNT(*) FILTER (WHERE l."RSRP" IS NOT NULL) AS has_rsrp,
  COUNT(*) FILTER (WHERE l."经度" IS NOT NULL AND l."纬度" IS NOT NULL) AS has_gps,
  COUNT(*) FILTER (WHERE l."标准制式" = '2G') AS cnt_2g,
  COUNT(*) FILTER (WHERE l."标准制式" = '3G') AS cnt_3g
FROM rebuild2.l0_lac l
LEFT JOIN rebuild2.dim_lac_trusted t
  ON l."运营商编码" = t.operator_code
  AND l."标准制式" = t.tech_norm
  AND l."LAC" = t.lac::bigint
WHERE t.lac IS NULL;
```

**期望**：
- trusted 过滤后约 30M 行
- 被过滤的主要是 2G/3G 和不活跃 LAC

---

### 检查 C：GPS 修正完整性（Step 3）

**目标**：确认 GPS 4 级回退是否正确执行。

```sql
-- C1: dwd_fact_enriched GPS 来源分布
SELECT
  gps_source,
  COUNT(*) AS cnt,
  ROUND(COUNT(*)::numeric / (SELECT COUNT(*) FROM rebuild2.dwd_fact_enriched) * 100, 2) AS pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1
ORDER BY 2 DESC;
```

```sql
-- C2: not_filled 的记录分析 — 为什么补不上？
SELECT
  e.tech_norm,
  b.gps_quality,
  COUNT(*) AS cnt
FROM rebuild2.dwd_fact_enriched e
LEFT JOIN rebuild2.dim_bs_refined b
  ON e.operator_code = b.operator_code
  AND e.tech_norm = b.tech_norm
  AND e.lac = b.lac
  AND e.bs_id = b.bs_id
WHERE e.gps_source = 'not_filled'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

```sql
-- C3: GPS 完整性 — 有没有经度有纬度空、或反过来的异常？
SELECT
  gps_source,
  COUNT(*) FILTER (WHERE lon_final IS NOT NULL AND lat_final IS NULL) AS lon_only,
  COUNT(*) FILTER (WHERE lon_final IS NULL AND lat_final IS NOT NULL) AS lat_only
FROM rebuild2.dwd_fact_enriched
GROUP BY 1;
```

```sql
-- C4: GPS 坐标范围检查 — 有没有超出中国范围的？
SELECT
  COUNT(*) FILTER (WHERE lon_final < 73 OR lon_final > 135) AS lon_out_of_range,
  COUNT(*) FILTER (WHERE lat_final < 3 OR lat_final > 54) AS lat_out_of_range
FROM rebuild2.dwd_fact_enriched
WHERE lon_final IS NOT NULL;
```

**期望**：
- original ~77%, cell_center ~19%, bs_center ~2.7%, not_filled < 0.1%
- not_filled 应对应 BS quality = 'Unusable' 的记录
- 不应存在 lon_only 或 lat_only
- 所有坐标在中国范围内

---

### 检查 D：信号补齐完整性（Step 4）— 核心审计

**目标**：逐字段检查信号补齐前后的有值率变化。

```sql
-- D1: signal_fill_source 分布
SELECT
  signal_fill_source,
  COUNT(*) AS cnt,
  ROUND(COUNT(*)::numeric / (SELECT COUNT(*) FROM rebuild2.dwd_fact_enriched) * 100, 2) AS pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1
ORDER BY 1;
```

```sql
-- D2: 各信号字段在不同 fill_source 下的有值率
SELECT
  signal_fill_source,
  COUNT(*) AS total,
  -- RSRP
  ROUND(COUNT(*) FILTER (WHERE rsrp_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS rsrp_pct,
  -- RSRQ
  ROUND(COUNT(*) FILTER (WHERE rsrq_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS rsrq_pct,
  -- SINR
  ROUND(COUNT(*) FILTER (WHERE sinr_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS sinr_pct,
  -- DBM
  ROUND(COUNT(*) FILTER (WHERE dbm_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS dbm_pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1
ORDER BY 1;
```

```sql
-- D3: 按制式拆分的信号有值率（4G vs 5G 差异分析）
SELECT
  tech_norm,
  signal_fill_source,
  COUNT(*) AS total,
  ROUND(COUNT(*) FILTER (WHERE rsrp_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS rsrp_pct,
  ROUND(COUNT(*) FILTER (WHERE rsrq_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS rsrq_pct,
  ROUND(COUNT(*) FILTER (WHERE sinr_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS sinr_pct,
  ROUND(COUNT(*) FILTER (WHERE dbm_final IS NOT NULL)::numeric / COUNT(*) * 100, 1) AS dbm_pct
FROM rebuild2.dwd_fact_enriched
GROUP BY 1, 2
ORDER BY 1, 2;
```

```sql
-- D4: 关键问题 — unfilled 记录中，原始 L0 是否有 SS原始值 可以救回？
-- 通过 l0_row_id 回溯到 l0_lac
SELECT
  e.tech_norm,
  COUNT(*) AS unfilled_total,
  COUNT(*) FILTER (WHERE l."SS原始值" IS NOT NULL) AS has_ss,
  COUNT(*) FILTER (WHERE l."RSRP" IS NOT NULL) AS has_rsrp_in_l0,
  COUNT(*) FILTER (WHERE l."SS原始值" IS NOT NULL AND l."RSRP" IS NULL) AS recoverable_by_ss
FROM rebuild2.dwd_fact_enriched e
JOIN rebuild2.l0_lac l ON e.l0_row_id = l.ctid
WHERE e.signal_fill_source = 'unfilled'
GROUP BY 1;
```

```sql
-- D5: cell_fill 记录中，RSRQ/SINR/DBM 补齐是否跟上了 RSRP？
-- 如果 rsrp_final 有值但 rsrq_final 空，说明 RSRQ 补齐漏了
SELECT
  signal_fill_source,
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE rsrp_final IS NOT NULL AND rsrq_final IS NULL) AS rsrp_ok_rsrq_null,
  COUNT(*) FILTER (WHERE rsrp_final IS NOT NULL AND sinr_final IS NULL) AS rsrp_ok_sinr_null,
  COUNT(*) FILTER (WHERE rsrp_final IS NOT NULL AND dbm_final IS NULL)  AS rsrp_ok_dbm_null
FROM rebuild2.dwd_fact_enriched
GROUP BY 1
ORDER BY 1;
```

```sql
-- D6: 信号补齐前后对比 — L0 原始有值率 vs enriched 最终有值率
-- L0 基线（trusted LAC 范围内）
WITH l0_baseline AS (
  SELECT
    l."标准制式" AS tech,
    COUNT(*) AS total,
    ROUND(COUNT(*) FILTER (WHERE l."RSRP" IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS l0_rsrp_pct,
    ROUND(COUNT(*) FILTER (WHERE l."RSRQ" IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS l0_rsrq_pct,
    ROUND(COUNT(*) FILTER (WHERE l."SINR" IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS l0_sinr_pct,
    ROUND(COUNT(*) FILTER (WHERE l."Dbm" IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS l0_dbm_pct,
    ROUND(COUNT(*) FILTER (WHERE l."SS原始值" IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS l0_ss_pct,
    ROUND(COUNT(*) FILTER (WHERE COALESCE(l."RSRP", l."SS原始值") IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS l0_rsrp_with_ss_pct
  FROM rebuild2.l0_lac l
  JOIN rebuild2.dim_lac_trusted t
    ON l."运营商编码" = t.operator_code
    AND l."标准制式" = t.tech_norm
    AND l."LAC" = t.lac::bigint
  GROUP BY 1
),
enriched_result AS (
  SELECT
    tech_norm AS tech,
    COUNT(*) AS total,
    ROUND(COUNT(*) FILTER (WHERE rsrp_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS enr_rsrp_pct,
    ROUND(COUNT(*) FILTER (WHERE rsrq_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS enr_rsrq_pct,
    ROUND(COUNT(*) FILTER (WHERE sinr_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS enr_sinr_pct,
    ROUND(COUNT(*) FILTER (WHERE dbm_final IS NOT NULL)::numeric / COUNT(*) * 100, 2) AS enr_dbm_pct
  FROM rebuild2.dwd_fact_enriched
  GROUP BY 1
)
SELECT
  l.tech,
  l.total AS l0_rows,
  r.total AS enriched_rows,
  -- RSRP 对比
  l.l0_rsrp_pct,
  l.l0_rsrp_with_ss_pct AS l0_rsrp_if_use_ss,
  r.enr_rsrp_pct,
  -- RSRQ 对比
  l.l0_rsrq_pct,
  r.enr_rsrq_pct,
  -- SINR 对比
  l.l0_sinr_pct,
  r.enr_sinr_pct,
  -- DBM 对比
  l.l0_dbm_pct,
  r.enr_dbm_pct
FROM l0_baseline l
JOIN enriched_result r ON l.tech = r.tech
ORDER BY l.tech;
```

**期望**：
- enriched 的 RSRP 有值率应 > L0 原始有值率（补齐了）
- 如果 `l0_rsrp_if_use_ss` 显著高于 `enr_rsrp_pct`，说明 SS原始值 未被利用
- RSRQ/SINR/DBM 在 cell_fill 下的空值率应该和 original 下接近（因为 LAG/LEAD 用的也是同一 Cell 的邻近记录）

---

### 检查 E：信号值域合法性

```sql
-- E1: 各信号字段的值域检查
SELECT
  MIN(rsrp_final) AS rsrp_min, MAX(rsrp_final) AS rsrp_max,
  MIN(rsrq_final) AS rsrq_min, MAX(rsrq_final) AS rsrq_max,
  MIN(sinr_final) AS sinr_min, MAX(sinr_final) AS sinr_max,
  MIN(dbm_final)  AS dbm_min,  MAX(dbm_final)  AS dbm_max,
  -- 异常值计数
  COUNT(*) FILTER (WHERE rsrp_final >= 0)  AS rsrp_positive,
  COUNT(*) FILTER (WHERE rsrp_final = -1)  AS rsrp_minus1,
  COUNT(*) FILTER (WHERE rsrp_final = -110) AS rsrp_minus110,
  COUNT(*) FILTER (WHERE dbm_final >= 0)   AS dbm_positive
FROM rebuild2.dwd_fact_enriched;
```

**期望**：
- RSRP: -156 ~ -1（不含 0 和正数）
- 不应存在哨兵值 -1、-110（enrich 阶段应已过滤）
- DBM: 全部 < 0

---

### 检查 F：行数一致性

```sql
-- F1: 管线各环节行数
SELECT
  (SELECT COUNT(*) FROM rebuild2.l0_lac) AS l0_lac,
  (SELECT COUNT(*) FROM rebuild2.l0_gps) AS l0_gps,
  (SELECT COUNT(*) FROM rebuild2.dim_lac_trusted) AS trusted_lac,
  (SELECT COUNT(*) FROM rebuild2.dim_cell_refined) AS cell_refined,
  (SELECT COUNT(*) FROM rebuild2.dim_bs_refined) AS bs_refined,
  (SELECT COUNT(*) FROM rebuild2.dwd_fact_enriched) AS enriched,
  (SELECT COUNT(*) FROM rebuild2._research_bs_classification_v2) AS bs_classification;
```

---

### 检查 G：signal_fill_source 标记是否有 bs_fill？

根据代码逻辑，signal_fill_source 应有 4 个值：original / cell_fill / bs_fill / unfilled。
但实际数据中可能缺少 bs_fill。

```sql
-- G1: signal_fill_source 实际值
SELECT DISTINCT signal_fill_source FROM rebuild2.dwd_fact_enriched ORDER BY 1;
```

```sql
-- G2: 如果没有 bs_fill，说明 Stage 2（BS main cell fallback）的标记逻辑可能有问题
-- 检查：有没有记录的 RSRP 来自 BS fallback 但被标记成了 cell_fill？
-- 这个需要回溯中间表，如果中间表已删除则跳过
```

---

## 4. 产出格式

审计完成后，产出一张 **补齐前后对比表**：

| 环节 | 字段 | L0 原始有值率 | enriched 有值率 | 差值 | 理论最大有值率 | 是否异常 | 说明 |
|------|------|-------------|---------------|------|-------------|---------|------|
| GPS | lon+lat | ?% | ?% | +?% | ~99.9% | ? | |
| 信号 | RSRP | ?% | ?% | +?% | ?% | ? | 含 SS原始值可提升到?% |
| 信号 | RSRQ | ?% | ?% | +?% | ?% | ? | |
| 信号 | SINR | ?% | ?% | +?% | ?% | ? | 4G 原始就低 |
| 信号 | DBM | ?% | ?% | +?% | ?% | ? | |

加上每个发现的问题清单：

| # | 严重度 | 问题描述 | 影响行数 | 影响比例 | 可修复性 |
|---|--------|---------|---------|---------|---------|
| 1 | 高/中/低 | ... | ... | ... | ... |

**不做修复，只出报告。**

---

## 5. 注意事项

1. **所有查询只读**，不执行任何 INSERT/UPDATE/DELETE
2. **大表查询** 可能慢（l0_lac 4400 万行），用 MCP 工具查询时注意超时
3. 如果某个查询超时，分制式或分 LAC 执行
4. D4 检查需要通过 ctid 回溯 l0_lac，这个 JOIN 可能很慢，可以用 LIMIT 采样
5. 中间表 `_tmp_gps_fixed`、`_tmp_signal_s1` 等可能已被删除，跳过需要这些表的检查
