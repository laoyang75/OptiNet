# Step1 与 Step2-5 跨天流水线临时方案

时间：2026-04-14
定位：正式重跑提速候选方案，当前仅做设计记录，不代表已切换执行

## 1. 背景

当前正式全链脚本 `rebuild5/scripts/run_step1_to_step5_daily_loop.py` 的执行方式是严格串行：

```text
prepare_current_dataset
  -> day1 Step1
  -> day1 Step2-5
  -> day2 Step1
  -> day2 Step2-5
  -> ...
```

这种方式的优点是简单、结果边界清晰；缺点是 `Step1` 与 `Step2-5` 没有重叠，墙钟时间接近两者逐日相加。

## 2. 目标

在不改变正式库最终口径、不改 UI 读取逻辑的前提下，临时提升一次正式重跑速度。

核心目标不是并行多个 `Step1`，而是：

```text
Step1(day N+1) 与 Step2-5(day N) 跨天流水线并行
```

## 3. 当前代码约束

### 3.1 Step1 约束

`Step1` 当前写死共享表名：

- `rebuild5.raw_gps`
- `rebuild5.etl_ci`
- `rebuild5.etl_ss1`
- `rebuild5.etl_clean_stage`
- `rebuild5.etl_cleaned`

因此：

1. 不能无改动并行跑多个 `Step1`
2. 不能让 `Step2-5` 直接读取正在被下一个 `Step1` 覆盖的 `rebuild5.etl_cleaned`

### 3.2 Step2-5 约束

`rebuild5/scripts/run_daily_increment_batch_loop.py` 支持从任意 `input_relation` 物化当天输入，然后只跑 `Step2-5`。

这意味着 `Step2-5` 可以天然作为“消费者”，前提是输入表已经冻结。

## 4. 方案核心

不要改 `Step1` 核心模块，只新增一个临时编排脚本。

建议脚本名：

`rebuild5/scripts/run_step1_step25_pipelined_temp.py`

核心思路：

1. `prepare_current_dataset()`
2. 执行全量 reset
3. Producer 串行逐天跑 `Step1`
4. 每完成一天，就把当天 `rebuild5.etl_cleaned` 快照成一张冻结 staging 表
5. 为当天生成一张“累计 view”，由历史累计 Step1 结果 + 当前及此前 staging 表做 `UNION ALL`
6. Consumer 读取当天累计 view，执行当天 `Step2-5`
7. 全部完成后，把最后一天的累计 view 物化回正式 `rebuild5.etl_cleaned`

## 5. 推荐流程

### 阶段 A：准备

1. 调 `prepare_current_dataset()`，得到完整正式 `raw_gps`
2. 把完整 `raw_gps` 备份到 `rebuild5.raw_gps_full_backup`
3. 执行 `reset_step1_to_step5_for_full_rerun_v3.sql`
4. 创建临时 schema，例如：

```sql
CREATE SCHEMA IF NOT EXISTS rebuild5_tmp;
```

### 阶段 B：Producer

对每一天执行：

1. 从 `raw_gps_full_backup` 切出当天 `rebuild5.raw_gps`
2. 跑 `run_step1_pipeline()`
3. 把 `rebuild5.etl_cleaned` 冻结成：

```text
rebuild5_tmp.etl_cleaned_20251201
rebuild5_tmp.etl_cleaned_20251202
...
```

4. 对该日表建最小索引：

- `event_time_std`
- `record_id`
- `(operator_filled, lac_filled, bs_id, cell_id, tech_norm)`

5. 基于“历史累计 Step1 结果 + 当前所有 staging 表”创建当天累计 view
6. 标记该日表状态为 `step1_ready`

### 阶段 C：Consumer

Consumer 不读正在被下一天 Step1 覆盖的正式 `rebuild5.etl_cleaned`，而是读已经冻结的“累计 view”。

例如：

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_tmp.etl_cumulative_20251201 \
  --start-day 2025-12-01 \
  --end-day 2025-12-01 \
  --start-batch-id 1
```

第二天开始可流水线：

```text
Producer:  生成 day2 的 staging etl + day2 cumulative view
Consumer:  消费 day1 cumulative view 跑 Step2-5
```

稳态后执行关系变成：

```text
T1: day1 Step1
T2: day2 Step1   || day1 Step2-5
T3: day3 Step1   || day2 Step2-5
...
```

## 6. 最小实现范围

为了保持低风险，这个临时脚本只做编排，不改业务逻辑。

### 需要新增的东西

1. 一个临时编排脚本
2. 一个 staging 表命名函数
3. 一个 cumulative view 构造函数
4. 一个 staging 状态记录（可以是本地 JSON，也可以是 `rebuild5_tmp.pipeline_stage_status`）
5. 一个最终 `etl_cleaned` 物化步骤

### 不建议本次做的东西

1. 不要参数化 Step1 全部表名
2. 不要并行多个 Step1
3. 不要改 Step2/3/4/5 核心 SQL
4. 不要改 UI 或服务层读取口径

## 7. 为什么这个方案比“先全量 Step1，再串行 Step2-5”更有价值

“先全量 Step1，再串行 Step2-5”只能节省编排固定开销，总时间仍近似：

```text
总 Step1 时间 + 总 Step2-5 时间
```

跨天流水线的理论收益来自重叠执行，总时间更接近：

```text
prepare + day1 Step1 + max(后续每日 Step1, 对应前一日 Step2-5) * (N-1) + 收尾
```

如果 `Step1` 明显比 `Step2-5` 重，这个方案才有可观收益。

## 8. 风险点

### 8.1 正式表覆盖风险

`Step1` 会反复覆盖 `rebuild5.etl_cleaned`，因此 `Step2-5` 不能直接读正式表，必须只读冻结累计 view。

### 8.2 批次对齐风险

`Step2-5` 的 `batch_id`、`day` 和 staging 表必须严格一一对应，不能跳天、不能复用错表。

### 8.3 清理风险

如果中途失败，需要明确：

1. 哪些 staging 日表已经可复用
2. 哪些 `batch_id` 已经发布
3. 是从某天 `Step1` 继续，还是从某天 `Step2-5` 继续

## 9. 验证标准

若后续决定切换到该方案，最少要验证：

1. `batch1-2` 与串行基线结果严格一致
2. `trusted_cell_library / trusted_bs_library / trusted_lac_library` 的最终最新批次与串行方案一致
3. `rebuild5.etl_cleaned` 最终行数和日期分布正确
4. 中途失败后支持从累计 Step1 基线 + 新 staging 日表断点恢复

## 10. 当前结论

当前最值得评估的不是“并行多个 Step1”，而是：

```text
单 Step1 串行生产日级 staging 表
  + 当天累计 view 冻结
  + Step2-5 作为消费者跨天并行回放
```

这是在当前项目约束下：

1. 改动最小
2. 风险可控
3. 最有可能带来实质墙钟收益

后续如果正式决定执行，应先用前两天做一次串行对照验证，再放大到完整 7 天。
