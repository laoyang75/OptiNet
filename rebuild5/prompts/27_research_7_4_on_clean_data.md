# 27 方案 7.4 标签研究（ETL 过滤重跑后 · 新会话）

> **创建日期**：2026-04-20
> **前置**：`prompts/26_rerun_with_etl_filter.md` 的重跑已完成（ETL 过滤 + Step 1-5 重跑 batch 7）
> **数据库**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **仓库**：`/Users/yangcongan/cursor/WangYou_Data`
> **本 prompt 用途**：独立新对话从此处继续研究工作，不需要回看历史

---

## 0. 你的任务

重跑已产出一份干净的 batch 7 数据（ETL 层剔除了垃圾 cell_id / lac；标签按方案 7.4 + GPS 硬过滤产出）。你需要：

1. **对标签分布做最终审视**（§4）：看方案 7.4 在干净数据上的真实表现
2. **识别剩余标签问题**（§5）：抽样发现任何"还不对"的 case
3. **评估参数是否需要微调**（§6）：`1300m entry / 8 dedup / 3 dev / 3 day` 门槛是否合理
4. **产出研究报告**（§7）：为后续 BS/LAC 修复 + 最终重跑提供决策依据

**范围限制**：本 prompt **只做研究不改代码**。任何参数 / 代码改动建议都等用户拍板。

---

## 1. 必读文档（按顺序）

### 1.1 先读 20 分钟建立上下文

| 文件 | 重点 | 估计时间 |
|---|---|---|
| `rebuild5/docs/gps研究/09_标签规则重构方案7_4.md` | §4 规则 + §5 评估方法 + §6 遗留 | 5 分钟 |
| `rebuild5/docs/gps研究/10_异常数据研究_方案7_4后.md` | §3 oversize + §5 真多簇 | 3 分钟 |
| `rebuild5/docs/03_流式质量评估.md` §GPS 有效性 + §生命周期判定 | Step 3 晋级原则 | 3 分钟 |
| `rebuild5/docs/01b_数据源接入_处理规则.md` §LAC / CellID 清洗 | ETL 过滤规则 | 2 分钟 |
| 最新重跑报告 `rebuild5/docs/rerun_delivery_2026-04-20_etl_filter.md`（如存在） | 实际分布 | 3 分钟 |

### 1.2 方案 7.4 核心规则（一页纸摘要）

```
规则 1：p90 < 1300m → stable
  （Step 3 已验证数据量支撑单簇；整体紧凑不做多质心分析）

规则 2：p90 ≥ 1300m 进入多质心分析
  2a 稀疏门槛：dedup_pts < 8 OR dev < 3 OR day < 3 → insufficient
  2b 按 k_eff 判：
     k_eff=0 → insufficient
     k_eff=1 + p90 ≤ 10km → large_coverage
     k_eff=1 + p90 > 10km → oversize_single
     k_eff=2 + 距离 ≥ 100km → collision
     k_eff=2 + 近 + 重叠 ≥ 0.5 → dual_cluster
     k_eff=2 + 近 + 重叠 = 0 + no_comeback → migration
     k_eff=2 其他 → uncertain
     k_eff ≥ 3 → uncertain/dynamic
```

---

## 2. 用户核心原则

- **精度优先不是覆盖率优先**：宁可说"不知道"（insufficient），不乱贴 stable
- **状态机**：Step 5 信任 Step 3；不重新质疑前置步骤
- **每观察点必须有 GPS**（设计原则）
- **先研究再工程**：阈值调整、规则变更前先出数据依据，等用户拍板
- **分批验证**：任何改动先在小样本模拟，再放大
- **SQL 拆小步**：禁止 ≥3 层 CTE、禁止复杂自 join

---

## 研究范围说明

重跑产出了 **batch 1-7 共 7 个完整批次**。本次研究：

- **主要焦点**：最新批次（通常是 batch 7），因为它继承了前 6 批的累积状态，最能反映稳态
- **跨批稳定性验证**：各 batch 的分布应相近（±2pp），若某批偏离要单独分析
- 以下 SQL 中 `batch_id = 7` 可替换为 `batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)`，确保总是取最新批

---

## 3. 起手 — 确认数据状态

### 3.0 确认全部 7 批已产出

```sql
SELECT 'cell' AS layer, COUNT(DISTINCT batch_id) AS batches,
       MIN(batch_id) AS min_b, MAX(batch_id) AS max_b
FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs', COUNT(DISTINCT batch_id), MIN(batch_id), MAX(batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id), MIN(batch_id), MAX(batch_id) FROM rebuild5.trusted_lac_library;
-- batches 都应 = 7；若 < 7 说明上游重跑不完整，先回问用户
```

### 3.0a 跨 batch 稳定性检查

```sql
SELECT batch_id, drift_pattern, COUNT(*) AS cnt,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (PARTITION BY batch_id), 2) AS pct
FROM rebuild5.trusted_cell_library
GROUP BY batch_id, drift_pattern
ORDER BY batch_id, cnt DESC;
-- 各 batch 的 stable/insufficient 比例应相近（±2pp）；若某 batch 明显偏离，记到报告里
```

### 3.1 确认快照存在（供 diff 对比）

```sql
SELECT 'cell_before' AS t, COUNT(*) FROM rebuild5._snapshot_before_etl_filter_cell
UNION ALL SELECT 'bs_before', COUNT(*) FROM rebuild5._snapshot_before_etl_filter_bs
UNION ALL SELECT 'lac_before', COUNT(*) FROM rebuild5._snapshot_before_etl_filter_lac;
-- 都应该 > 0；如不存在，说明上一轮重跑没保快照，回问用户
```

### 3.2 确认当前分布

```sql
SELECT drift_pattern, COUNT(*) AS cnt,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(), 2) AS pct
FROM rebuild5.trusted_cell_library WHERE batch_id = 7
GROUP BY 1 ORDER BY 2 DESC;
```

**预期**（方案 7.4 + ETL 过滤后）：
- stable ≈ 93-96%
- insufficient ≈ 1-3%
- 其他合计 < 1%
- 垃圾 cell (lac<100 / cell_id<1000 4G / cell_id<4096 5G) 应该 = 0

### 3.3 确认 ETL 过滤生效

```sql
SELECT
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm = '4G') AS "残4G",
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm = '5G') AS "残5G",
  COUNT(*) FILTER (WHERE lac < 100) AS "残lac"
FROM rebuild5.trusted_cell_library WHERE batch_id = 7;
-- 都应该为 0
```

如不为 0，说明过滤没彻底，**先回问用户**，不要继续。

---

## 4. 标签分布最终审视

### 4.1 总览

按方案 7.4 的每条规则路径拆分现在的分布，看是否有意料之外的堆积。

```sql
WITH base AS (
  SELECT t.*, lr.k_raw, lr.k_eff, lr.pair_dist_m, lr.pair_overlap_ratio
  FROM rebuild5.trusted_cell_library t
  LEFT JOIN rebuild5.label_results lr USING (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)
  WHERE t.batch_id = 7
)
SELECT
  drift_pattern,
  COUNT(*) AS cnt,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY p90_radius_m)::int AS p90_p50,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY gps_valid_count)::int AS gps_p50,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY distinct_dev_id)::int AS dev_p50,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY active_days)::int AS days_p50,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY k_eff)::int AS keff_p50
FROM base
GROUP BY drift_pattern
ORDER BY cnt DESC;
```

**检查点**：
- `insufficient` 的 `p90_p50` 是不是 0 或 ≥1300（不应该有 100-1200 的）？
- `stable` 的 `p90_p50` 应该 < 1300
- `large_coverage` 的 `p90_p50` 应该 1300-10000
- `oversize_single` 的 `p90_p50` 应该 > 10000
- `dual_cluster / uncertain / collision / migration` 的 `keff_p50` 应该 ≥ 2

### 4.2 ETL 过滤带来的净变化

```sql
-- cell 总量变化
SELECT 'before' AS phase, COUNT(*) FROM rebuild5._snapshot_before_etl_filter_cell
UNION ALL SELECT 'after', COUNT(*) FROM rebuild5.trusted_cell_library WHERE batch_id = 7;

-- 按标签看减量分布
WITH before_dist AS (
  SELECT drift_pattern, COUNT(*) AS cnt_before FROM rebuild5._snapshot_before_etl_filter_cell GROUP BY 1
), after_dist AS (
  SELECT drift_pattern, COUNT(*) AS cnt_after FROM rebuild5.trusted_cell_library WHERE batch_id = 7 GROUP BY 1
)
SELECT COALESCE(b.drift_pattern, a.drift_pattern) AS drift,
  COALESCE(b.cnt_before, 0) AS before, COALESCE(a.cnt_after, 0) AS after,
  COALESCE(a.cnt_after, 0) - COALESCE(b.cnt_before, 0) AS delta
FROM before_dist b FULL OUTER JOIN after_dist a USING (drift_pattern)
ORDER BY ABS(delta) DESC;
```

**预期**：insufficient 减少最多（垃圾 cell 多集中在此），其他标签变化小。

---

## 5. 抽样识别剩余问题

### 5.1 边界 case 1：p90 刚好接近 1300m

```sql
-- p90 在 1250-1350m 的 cell，规则 1 和规则 2 的边界
SELECT drift_pattern, COUNT(*) AS cnt
FROM rebuild5.trusted_cell_library
WHERE batch_id = 7 AND p90_radius_m BETWEEN 1250 AND 1350
GROUP BY drift_pattern;
-- 期望：大部分 stable（p90<1300），少部分 large_coverage 或 insufficient（p90>=1300）
```

抽 5 个 p90 在 1280-1320 的 cell，查 raw_gps 分布，判断"1300m 作为门槛"是合理的分界还是太严/太松。

### 5.2 边界 case 2：oversize_single 里的 p90>=50km

```sql
-- 超大 p90 的 cell 应该是飞跃残留
SELECT operator_code, lac, bs_id, cell_id, tech_norm,
  p50_radius_m::int AS p50, p90_radius_m::int AS p90,
  gps_valid_count, distinct_dev_id
FROM rebuild5.trusted_cell_library
WHERE batch_id = 7 AND drift_pattern = 'oversize_single' AND p90_radius_m >= 50000
ORDER BY p90_radius_m DESC LIMIT 10;
```

**研究**：如果全是 p50/p90 比例悬殊（p50<100m 但 p90>50km），说明单点飞跃没清；建议 Step 4 / Step 5 补外点剔除规则。

### 5.3 边界 case 3：insufficient 里 p90>=1300 的稀疏 cell

```sql
SELECT
  percentile_cont(0.5) WITHIN GROUP (ORDER BY gps_valid_count)::int AS gps,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY distinct_dev_id)::int AS dev,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY active_days)::int AS days,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY p90_radius_m)::int AS p90,
  COUNT(*) AS cnt
FROM rebuild5.trusted_cell_library
WHERE batch_id = 7 AND drift_pattern = 'insufficient'
  AND p90_radius_m >= 1300;
```

**研究**：如果数量多 + 数据量不算极低（如 gps>=8），说明稀疏门槛（`dedup_pts<8 OR dev<3 OR day<3`）可能偏严；如果数量少 / 数据量极低，说明阈值合适。

### 5.4 抽 20 个样本逐 cell 审视

```sql
-- 从各标签各抽 2-3 个，看 raw_gps 分布是否与标签一致
DROP TABLE IF EXISTS rebuild5._research_samples_v2;
CREATE UNLOGGED TABLE rebuild5._research_samples_v2 AS
(SELECT 'stable' AS layer, * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'stable' ORDER BY random() LIMIT 3)
UNION ALL
(SELECT 'insufficient', * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'insufficient' ORDER BY random() LIMIT 3)
UNION ALL
(SELECT 'large_coverage', * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'large_coverage' ORDER BY random() LIMIT 3)
UNION ALL
(SELECT 'dual_cluster', * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'dual_cluster' ORDER BY random() LIMIT 3)
UNION ALL
(SELECT 'uncertain', * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'uncertain' ORDER BY random() LIMIT 3)
UNION ALL
(SELECT 'oversize_single', * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'oversize_single' ORDER BY random() LIMIT 3)
UNION ALL
(SELECT 'collision', * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'collision')
UNION ALL
(SELECT 'migration', * FROM rebuild5.trusted_cell_library
 WHERE batch_id = 7 AND drift_pattern = 'migration');
```

对每个样本：
1. 看 label_results 的 k_raw / k_eff / pair_dist_m / pair_overlap_ratio
2. 看 cell_centroid_detail 里的 cluster 分布（若有）
3. 判断标签是否"站得住脚"

### 5.5 所有 collision / migration 逐一人工审查

```sql
-- collision 和 migration 样本少但重要，全部审查
SELECT t.operator_code, t.lac, t.bs_id, t.cell_id, t.tech_norm,
       t.p50_radius_m::int, t.p90_radius_m::int, t.gps_valid_count,
       lr.k_raw, lr.k_eff, lr.pair_dist_m::int AS dist_m, lr.pair_overlap_ratio,
       lr.pair_no_comeback
FROM rebuild5.trusted_cell_library t
LEFT JOIN rebuild5.label_results lr USING (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)
WHERE t.batch_id = 7 AND t.drift_pattern IN ('collision', 'migration')
ORDER BY t.drift_pattern, t.cell_id;
```

对每个 cell 看 `cell_centroid_detail` 的两个质心位置，确认是否真的是跨区复用 / 真迁移。

---

## 6. 参数微调评估（只出结论，不改代码）

针对以下每个阈值，给出"是否需要调整 + 数据依据"：

### 6.1 `multi_centroid_entry_p90_m = 1300`

- 当前 p90 < 1300 全判 stable。如果发现 p90=1300-1500 段有大量应该是 large_coverage 的 cell 被漏判，说明 1300 偏严
- 查 p90 在 1300-1800 的 cell 的 k_eff 分布

### 6.2 `min_cluster_dev_day_pts = 4`

- 当前值与 DBSCAN `min_points=4` 对齐。要不要再降到 3？查当前 k_eff=1 的 cell 的 dev_day_pts 分布，看有无 dev_day=3 的次簇被抛弃

### 6.3 `min_total_dedup_pts=8 / min_total_devs=3 / min_total_active_days=3`

- 稀疏门槛是否合理？
- 在 p90>=1300 且 k_eff=0 的 cell 里（insufficient），dev/day 分布在哪
- 如果大多在 dev=2/days=2，说明门槛偏严；如果大多是 dev=1/days=1，说明门槛合适

### 6.4 `collision_min_dist_m = 100km`

- 当前 collision 样本少（个位数）。p50 已查过 k=2 的 dist_m 分布，只有极少数 >100km
- 建议保留当前值（除非业务要求更松）

---

## 7. 产出报告

完成后写一份简短报告（放到 `rebuild5/docs/gps研究/11_方案7_4_clean_data_review.md`），包含：

### 必含章节

**1. 分布最终态**
- 标签分布表（cnt + pct）
- vs 过滤前对比（用 §4.2 的 diff）
- 跟 09_标签规则重构方案7_4.md §5.3 的预期对比

**2. 各标签抽样审视结论**
- stable / insufficient / large_cov / dual / uncertain / oversize / collision / migration 各抽样结论：**标签对不对**
- 特别列出所有"看着不对的 case"

**3. 参数微调建议**
- 按 §6 四个参数，每个给"保留 / 建议调整到 X / 数据依据"
- 列出 confidence：高 / 中 / 低

**4. 标签规则补强建议**
- 有没有规则层面的 gap（比如 "p50<<p90 拖尾" 是否需要单独处理）
- 现有规则边界是否太简单

**5. 下一轮工作的线索**
- BS/LAC 研究（下一主对话会做）的重点应该在哪？
  - 比如哪些 BS 的 classification 不对？
  - 哪些 LAC 的 anomaly_bs_ratio 可疑？
- 这一步不要动手解决，只列线索

**6. 遗留风险**
- 已知还未解决的 case
- 建议下一轮是"直接进 BS/LAC"还是"先把标签规则再调一轮"

---

## 8. 安全约束

### 8.1 不要改代码

只看、只查、只报告。任何改动建议都等用户拍板。

### 8.2 不要重跑 pipeline

不要调用 `run_step*_pipeline` 或 `run_maintenance_pipeline`。如果觉得必要，先停下汇报。

### 8.3 不要删快照表

- `rebuild5._snapshot_before_etl_filter_cell`
- `rebuild5._snapshot_before_etl_filter_bs`
- `rebuild5._snapshot_before_etl_filter_lac`
- `rebuild5._drift_before_etl_filter`

这些是下一轮 BS/LAC 研究要用的。

### 8.4 SQL 拆小步

- 单条 SQL 只做一件事
- 禁 ≥3 层 CTE、禁复杂自 join
- 需要大查询时先物化成 `_research_*` 小表再 JOIN

### 8.5 5 元组业务键

查单 cell 用完整键：`(operator_code, lac, bs_id, cell_id, tech_norm)`。不要只用 `cell_id` 查（存在 cell_id 跨运营商复用）。

### 8.6 基线确认

开始前先跑 §3，确认 batch 7 数据是"重跑后干净数据"。如不一致（比如发现还有垃圾 cell、或者分布差太远），停下汇报。

---

## 9. 不在本 prompt 范围的事

1. **BS/LAC 问题研究** — 下一主对话单独做
2. **标签代码修改** — 仅给建议，由用户决定是否动
3. **Step 3 晋级逻辑审计** — 已登记独立工单
4. **其他批次（1-6）重跑** — 业务后续安排

---

## 附录 A. 常用 SQL 模板

### A.1 单 cell 的完整画像（含 raw_gps 点）

```sql
-- 替换 CELL_ID 和 TECH_NORM
WITH src AS (
  SELECT batch_id, source_row_uid FROM rebuild5.enriched_records WHERE gps_fill_source_final = 'raw_gps'
  UNION ALL
  SELECT batch_id, source_row_uid FROM rebuild5.snapshot_seed_records WHERE gps_fill_source_final = 'raw_gps'
)
SELECT
  w.event_time_std,
  COALESCE(NULLIF(w.dev_id,''), w.record_id) AS dev,
  w.lon_final, w.lat_final
FROM rebuild5.cell_sliding_window w
JOIN src ON src.batch_id = w.batch_id AND src.source_row_uid = w.source_row_uid
WHERE w.cell_id = CELL_ID AND w.tech_norm = 'TECH_NORM'
  AND w.gps_valid IS TRUE AND w.lon_final IS NOT NULL
ORDER BY w.event_time_std
LIMIT 100;
```

### A.2 查进度（监控用）

```sql
SELECT pid, state, EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       LEFT(regexp_replace(query,'\s+',' ','g'), 200) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND state='active' AND pid != pg_backend_pid()
ORDER BY query_start LIMIT 3;
```

### A.3 多簇细节

```sql
-- 查某 cell 的 cluster 中心
SELECT cluster_id, is_primary,
       ROUND(center_lon::numeric, 5) AS lon,
       ROUND(center_lat::numeric, 5) AS lat,
       obs_count, dev_count, share_ratio
FROM rebuild5.cell_centroid_detail
WHERE batch_id = 7 AND cell_id = CELL_ID
ORDER BY cluster_id;
```

---

## 附录 B. 关键参数清单（确认当前值）

| 参数 | 当前值 | 位置 |
|---|---|---|
| `multi_centroid_v2.min_cluster_dev_day_pts` | 4 | `config/antitoxin_params.yaml` |
| `multi_centroid_v2.multi_centroid_entry_p90_m` | 1300 | 同上 |
| `multi_centroid_v2.min_total_dedup_pts` | 8 | 同上 |
| `multi_centroid_v2.min_total_devs` | 3 | 同上 |
| `multi_centroid_v2.min_total_active_days` | 3 | 同上 |
| `label_rules.collision_min_dist_m` | 100000 | 同上 |
| `label_rules.large_coverage_max_p90_m` | 10000 | 同上 |
| `label_rules.dual_cluster_max_dist_m` | 5000 | 同上 |
| `label_rules.dual_cluster_min_overlap_ratio` | 0.5 | 同上 |
| `label_rules.migration_max_overlap_ratio` | 0.0 | 同上 |
| `cell.qualified.min_independent_obs` | 10 | `config/profile_params.yaml` |
| `cell.excellent.min_independent_obs` | 30 | 同上 |

## 附录 C. 相关文档

- **本轮原始任务**：`rebuild5/prompts/24_ui_label_alignment_and_refinement.md`
- **7.4 方案调研**：`rebuild5/docs/gps研究/09_标签规则重构方案7_4.md`
- **异常数据研究（第一版）**：`rebuild5/docs/gps研究/10_异常数据研究_方案7_4后.md`
- **Step 3 设计**：`rebuild5/docs/03_流式质量评估.md`
- **ETL 处理规则**：`rebuild5/docs/01b_数据源接入_处理规则.md`
- **前一次重跑 prompt**（ETL 过滤+全链路）：`rebuild5/prompts/26_rerun_with_etl_filter.md`
- **重跑报告**（如存在）：`rebuild5/docs/rerun_delivery_2026-04-20_etl_filter.md`
