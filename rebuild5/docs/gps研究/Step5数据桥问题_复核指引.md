# Step5 数据桥问题复核指引

> 创建日期：2026-04-18  
> 目的：给独立 agent 一份**只聚焦“Step3 -> Step5 数据桥缺失”**的问题核实说明，避免再次把问题误判成“历史数据被删”或“标签算法问题”。  
> 范围：只讨论数据流转，不讨论多质心标签算法调参。

---

## 1. 这份文档要回答什么

请独立 agent 只回答下面两个问题：

1. **问题是否存在？**  
   即：某个 cell 在 Step 3 已经凭借当前批/历史累计证据晋级，但 Step 5 在首次发布批次没有获得足够记录级事实，导致后续维护窗口偏瘦。

2. **正确修法是什么？**  
   即：是在 Step 3 和 Step 5 之间补一条“当前批 seed bridge”，还是要改动主流程边界。

**不要把这次任务变成：**

- 重新讨论标签规则是否合理
- 把 `enriched_records` 强行和 Step 3 历史 `independent_obs` 做一一对齐
- 误判为“历史数据删除”问题

---

## 2. 必读文档顺序

独立 agent 必须按下面顺序阅读：

1. [02_基础画像.md](../02_基础画像.md)
2. [03_流式质量评估.md](../03_流式质量评估.md)
3. [05_画像维护.md](../05_画像维护.md)
4. [runbook_v5.md](../runbook_v5.md)
5. [数据错误问题.md](./数据错误问题.md)
6. [处理流程总览.md](../处理流程总览.md)

阅读目标：

- `02_基础画像.md`：确认 Path A / Path B 分流语义
- `03_流式质量评估.md`：确认 Step 3 只评估候选域，已发布对象不进入 Step 3 当前批维护
- `05_画像维护.md`：确认 Step 5 事实层来自 `enriched_records`
- `runbook_v5.md`：确认历史样例 runbook 中 batch1 可以在 Step4=0 的情况下正常发布
- `数据错误问题.md`：看现象与本轮修订结论
- `处理流程总览.md`：看总流程边界与“不同事实层 + 当前批 bridge”的约束

---

## 3. 必查代码文件与检查点

### 3.1 Step 2

文件：

- [profile/pipeline.py](../../backend/app/profile/pipeline.py)

重点函数：

- `build_path_a_records()`
- `build_path_b_cells()`
- `build_profile_base()`

要确认的点：

1. Path A 是否只面向“上一轮已发布对象命中记录”
2. Path B 是否只面向“未命中可信库但有有效 GPS 的记录”
3. `profile_base` 是否只来自 Path B

### 3.2 Step 3

文件：

- [evaluation/pipeline.py](../../backend/app/evaluation/pipeline.py)
- [profile/pipeline.py](../../backend/app/profile/pipeline.py)

重点对象：

- `trusted_snapshot_cell`

要确认的点：

1. 当前批新晋级对象是否直接写入 `trusted_snapshot_cell`
2. Step 3 是否只评估候选域，而不是已发布对象维护
3. `trusted_snapshot_cell` 是否足以让 Step 5 在首次发布批次完成正式发布

### 3.3 Step 4

文件：

- [enrichment/pipeline.py](../../backend/app/enrichment/pipeline.py)

重点函数：

- `run_enrichment_pipeline()`
- `_insert_enriched_records()`
- `_insert_gps_anomaly_log()`

要确认的点：

1. `_insert_enriched_records()` 是否只 `FROM rebuild5.path_a_records`
2. 当前实现是否完全没有写入“本批首次晋级对象的当前批事实”
3. `gps_anomaly_log` 是否只对 donor 已存在的已发布对象记录生效

### 3.4 Step 5

文件：

- [maintenance/window.py](../../backend/app/maintenance/window.py)
- [maintenance/publish_cell.py](../../backend/app/maintenance/publish_cell.py)

重点函数：

- `refresh_sliding_window()`
- `publish_cell_library()`

要确认的点：

1. `refresh_sliding_window()` 是否只从 `enriched_records` 追加
2. `publish_cell_library()` 是否直接消费 `trusted_snapshot_cell`
3. 新晋级对象在首次发布时，是否能发布，但没有维护事实进入窗口

### 3.5 调度脚本

文件：

- [run_daily_increment_batch_loop.py](../../scripts/run_daily_increment_batch_loop.py)
- [run_step1_step25_pipelined_temp.py](../../scripts/run_step1_step25_pipelined_temp.py)

要确认的点：

1. batch 与日期是一一对应的
2. Step 2 作用域是按天 materialize 到 `step2_batch_input`
3. Step 3 -> Step 4 -> Step 5 的当前批顺序没有乱

---

## 4. 直接核实样本：cell 608244101

这个 cell 是本次复核的核心例子。

### 4.1 当前库里已核实到的事实

#### trusted_cell_library

| batch | lifecycle | independent_obs | distinct_dev_id | active_days | p90_radius_m |
|------|-----------|----------------:|----------------:|------------:|-------------:|
| 2 | qualified | 18 | 4 | 2 | 213743.81 |
| 3 | qualified | 1 | 1 | 1 | 0 |
| 4 | qualified | 1 | 1 | 1 | 0 |
| 5 | qualified | 3 | 3 | 2 | 844577.86 |
| 6 | qualified | 3 | 3 | 2 | 844577.86 |
| 7 | qualified | 3 | 3 | 2 | 844577.86 |

#### etl_cleaned 按天原始事实

| 日期 | 总行数 | gps_valid | 设备数 | 分钟观测数 | raw_gps | ss1_own |
|------|-------:|----------:|-------:|-----------:|--------:|--------:|
| 2025-12-01 | 7 | 5 | 4 | 7 | 5 | 2 |
| 2025-12-02 | 12 | 12 | 2 | 11 | 2 | 10 |
| 2025-12-03 | 1 | 1 | 1 | 1 | 0 | 1 |
| 2025-12-05 | 2 | 2 | 2 | 2 | 1 | 1 |
| 2025-12-07 | 1 | 1 | 1 | 1 | 1 | 0 |

#### enriched_records / cell_sliding_window

| batch | 日期 | 行数 |
|------|------|----:|
| 3 | 2025-12-03 | 1 |
| 5 | 2025-12-05 | 2 |
| 7 | 2025-12-07 | 1 |

### 4.2 这个例子说明了什么

1. `batch2` 的 `qualified + independent_obs=18` 是有来源的  
   它来自：
   - `2025-12-01` 的 7 个分钟观测
   - `2025-12-02` 的 11 个分钟观测
   - 合计正好是 18

2. 所以 Step 3 的晋级**不是假的**

3. 但 Step 5 窗口里只看到了后续 Path A 进入的：
   - `2025-12-03`: 1
   - `2025-12-05`: 2
   - `2025-12-07`: 1
   - 合计 4

4. 这证明：

> **batch2 首次晋级时，促成晋级的当前批记录级事实没有进入 Step 5。**

这不是“历史数据被删”，而是**当前批 bridge 缺失**。

5. 同时也要注意：
   - 即便不把 `2025-12-01` 那批历史候选证据带进 Step 5，
   - `2025-12-02` 当前批也至少有 12 条记录 / 11 个分钟观测，
   - 但当前 Step 5 里是 0。

这说明最小修复也至少要把“**当前批新晋级对象的当前批记录**”送入 Step 5。

---

## 5. 独立 agent 必跑 SQL

### 5.1 核实 608244101

```sql
-- 1) 历史发布结果
SELECT batch_id, lifecycle_state, independent_obs, distinct_dev_id, active_days, p90_radius_m
FROM rebuild5.trusted_cell_library
WHERE cell_id = 608244101
ORDER BY batch_id;

-- 2) Step1 最终事实（跨天）
SELECT
  DATE(event_time_std) AS d,
  COUNT(*) AS rows,
  COUNT(*) FILTER (WHERE gps_valid) AS gps_valid_rows,
  COUNT(DISTINCT COALESCE(NULLIF(dev_id,''), record_id)) AS devs,
  COUNT(DISTINCT date_trunc('minute', event_time_std)) AS minute_obs,
  COUNT(*) FILTER (WHERE gps_fill_source = 'raw_gps') AS raw_gps_rows,
  COUNT(*) FILTER (WHERE gps_fill_source = 'ss1_own') AS ss1_rows
FROM rebuild5.etl_cleaned
WHERE cell_id = 608244101
GROUP BY 1
ORDER BY 1;

-- 3) Step4 / Step5 维护事实层
SELECT batch_id, DATE(event_time_std) AS d, COUNT(*) AS rows
FROM rebuild5.enriched_records
WHERE cell_id = 608244101
GROUP BY 1,2
ORDER BY 1,2;

SELECT batch_id, DATE(event_time_std) AS d, COUNT(*) AS rows
FROM rebuild5.cell_sliding_window
WHERE cell_id = 608244101
GROUP BY 1,2
ORDER BY 1,2;
```

### 5.2 核实全局范围

```sql
SELECT batch_id, COUNT(*) AS rows
FROM rebuild5.enriched_records
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS rows
FROM rebuild5.cell_sliding_window
GROUP BY batch_id
ORDER BY batch_id;
```

### 5.3 要求 agent 给出结论

独立 agent 必须明确回答：

1. `608244101` 的 batch2 晋级证据来自哪里？
2. batch2 当前批是否有足够记录应当进入 Step 5？
3. 当前实现缺的是：
   - 历史数据修复
   - 还是“当前批新晋级对象 -> Step5 事实层”的桥接

---

## 6. 推荐修法（供独立 agent 复核）

### 6.1 不改主边界

不要改下面这些边界：

- Path A / Path B 分流
- Step 3 只评估候选域
- Step 4 仍然负责已发布对象 donor 补数
- Step 5 仍然主要消费 `enriched_records`

### 6.2 增加当前批 seed bridge

推荐新增一张持久表，例如：

`rebuild5.snapshot_seed_records`

语义：

- 存当前批**首次晋级对象**的当前批记录级事实
- 只供 Step 5 维护使用
- 不回灌 Step 2 / Step 3

### 6.3 生成逻辑

在 Step 3 完成后、Step 5 开始前：

1. 找出 `trusted_snapshot_cell(batch_id=t)` 中 `lifecycle_state in ('qualified','excellent')` 的 cell
2. 回到当前批原始作用域（`step2_batch_input` 或当前批的 `etl_cleaned` slice）
3. 提取这些 cell 的当前批所有记录
4. 允许走“晋级后更宽松补数逻辑”
5. 写入 `snapshot_seed_records(batch_id=t)`

### 6.4 Step 5 窗口更新改法

`refresh_sliding_window()` 改成：

```text
cell_sliding_window
  += enriched_records(batch=t)
  += snapshot_seed_records(batch=t)
```

按 `batch_id + source_row_uid` 去重。

### 6.5 复核时要特别判断的一点

独立 agent 需要再评估一个实现细节：

对于像 `608244101` 这种在 `batch2` 晋级、且其 18 个 obs 来自 `batch1 + batch2` 累计证据的 cell，

最终 bridge 应该带入 Step 5 的是：

1. **只带当前批 batch2 的记录**  
   这是最小修复，能把 Step 5 从 0 条拉到至少 12 条

还是

2. **带入晋级时的累计候选证据（batch1 + batch2）**  
   这样 Step 5 可以和 Step 3 的晋级证据更一致

这点需要独立 agent 结合设计语义再做最终确认。

---

## 7. 期望的 agent 输出格式

请独立 agent 最终输出：

1. 结论：
   - 问题是否存在
   - 根因是什么

2. 证据：
   - 608244101 的原始数据、晋级数据、维护数据

3. 建议修改点：
   - 具体文件
   - 具体函数
   - 是否新增 `snapshot_seed_records`
   - Step 5 窗口怎么接入

4. 风险说明：
   - 只带当前批
   - 还是带累计候选证据
   两种方案的利弊
