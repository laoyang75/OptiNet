# Standard Runbook: `rebuild5` 北京 7 天按天增量处理

本文件是 `rebuild5` 的**产品语义标准 runbook**。

适用场景：

- 按天导入新数据
- 以上一版正式库为只读基线继续流式累计
- 历史数据重基线时，按天重放 `Step 2 -> Step 5`

不适用场景：

- 对同一份固定全量数据做多轮重放验证

验证性重放请使用：

- `rebuild5/scripts/runbook_beijing_7d_standard.md`

## 1. 先说结论

- 当前库里的 `batch1-7` 属于固定 `beijing_7d` 全量数据的验证性重放结果，不属于产品日批产物。
- 在产品语义下，要从 `batch1` 重新开始，必须先清空 **Step 2 -> Step 5** 的全部状态；`Step 1` 产物可保留。
- 当前历史重基线的日切分主键是 `rebuild5.etl_cleaned.event_time_std`。
- 对未来真实日批，如果需要在原始层先做日期过滤，使用 `rebuild5.raw_gps.ts` 作为上游时间索引，不使用脏值较多的 `gps上报时间`。

## 2. 批次语义

- `batch_id = 1`：第一天（或首次初始化）
- `batch_id = N`：第 N 天导入的新数据完成处理后的版本

产品语义中：

- `batch_id` 不等于“重复重跑同一全量数据的次数”
- 每个批次都必须对应新的日期范围输入
- `Step 2 ~ Step 5` 当前批次只消费“当天新增记录”

## 3. 当前 `beijing_7d` 的日映射

对当前历史 `beijing_7d` 重基线，直接按 `etl_cleaned.event_time_std` 的**存储日桶**切分：

- `day1 = 2025-12-01`
- `day2 = 2025-12-02`
- `day3 = 2025-12-03`
- `day4 = 2025-12-04`
- `day5 = 2025-12-05`
- `day6 = 2025-12-06`
- `day7 = 2025-12-07`

说明：

- 当前 Step 2/3/5 统一使用 `event_time_std`，历史重基线不能退回到各步骤自行解释原始时间。
- 对当前库，`event_time_std` 的这 7 个日桶与 `dataset.yaml` 中 `2025-12-01 ~ 2025-12-07` 对齐，可直接作为 `batch1..7` 输入。

## 4. 执行原则

- `Step 1` 在产品语义中应每天处理“当天新增原始数据”
- 本次历史重基线允许**复用现有 Step 1 产物**（`raw_gps` / `etl_cleaned`），不重跑 Step 1
- `Step 2 ~ Step 5` 只读取上一版已发布库 / 冻结快照
- 当前批次的直接输入必须是“当天新数据”，不是重复处理整份历史全量
- 冻结快照原则始终生效：当前批次不能读取本批刚发布的结果

## 5. 日期索引检查（强制）

按天处理前，必须确认原始层和清洗层存在日期过滤可用索引。

至少检查：

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'rebuild5'
  AND tablename IN ('etl_cleaned', 'raw_gps')
ORDER BY tablename, indexname;
```

必须具备：

```sql
CREATE INDEX IF NOT EXISTS idx_etl_cleaned_event_time_std
ON rebuild5.etl_cleaned (event_time_std);

CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_ts
ON rebuild5.raw_gps (ts);

ANALYZE rebuild5.etl_cleaned;
ANALYZE rebuild5.raw_gps;
```

索引口径说明：

- `idx_etl_cleaned_event_time_std` 对应当前产品语义下 `Step 2 ~ Step 5` 的日切分主键。
- `idx_rebuild5_raw_gps_ts` 对应未来 `Step 1` 的原始接入日过滤；`ts -> report_ts -> event_time_std` 是稳定主链。

## 6. 先重置旧的 Step 2-5 状态

在当前库里，不能直接继续跑 `batch7 / batch8`。

必须先执行：

- `rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql`

这个 reset 只清：

- `Step 2 -> Step 5` 的批次产物
- `candidate_cell_pool`
- `cell_sliding_window`
- `step2/3/4/5` 运行统计

这个 reset **不清**：

- `rebuild5.raw_gps`
- `rebuild5.etl_cleaned`
- `Step 1` 运行结果

## 7. 推荐执行脚本

当前生产 / 重基线标准脚本：

- `rebuild5/scripts/run_daily_increment_batch_loop.py`
- `rebuild5/scripts/build_daily_sample_etl_input.py`

它的行为是：

- 先检查并补日期索引
- 拒绝在已有 `Step 2 -> Step 5` 状态下直接续跑
- 每天把一个 `event_time_std` 日桶物化到 `rebuild5.step2_batch_input`
- 顺序执行 `Step 2/3 -> Step 4 -> Step 5`

先看计划：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --start-day 2025-12-01 \
  --end-day 2025-12-07 \
  --plan-only
```

确认 reset 已做完后正式执行：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --start-day 2025-12-01 \
  --end-day 2025-12-07
```

## 8. 快速测试样本（推荐）

为了快速做代码回归和性能测试，推荐先构建“每天最多 100 万行”的小样本：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/build_daily_sample_etl_input.py \
  --rows-per-day 1000000 \
  --target-relation rebuild5.etl_cleaned_daily_sample_1m
```

然后对样本表先看日桶计划：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5.etl_cleaned_daily_sample_1m \
  --start-day 2025-12-01 \
  --end-day 2025-12-07 \
  --plan-only
```

## 9. 并发注意事项

不要回滚以下执行层修复：

- `cell_sliding_window` 写入并发保持 `4`，不要加回 `12`
- `enriched_records` 遇到 `ENOSPC` 时保留“自动降并发重试”逻辑
- 当前调试 / 复核阶段，`enriched_records` 与 `gps_anomaly_log` 按 `batch_id` 持久保留，不在 `Step 5` 后删除

背景：

- 之前踩过的是 PostgreSQL 多 backend 同时扩展同一关系文件时的底层分配异常，本质是并发写入模式不稳定
- 这类问题优先通过降低并发和重试兜底解决，不要只追求理论吞吐

## 10. Day 1（首次初始化）

```text
当天数据导入
  -> Step 1
  -> Step 2/3
  -> Step 4
  -> Step 5
```

当前历史重基线的等价执行：

```text
保留现有 Step 1
  -> 取 day1 = 2025-12-01 的 event_time_std 日桶
  -> Step 2/3
  -> Step 4
  -> Step 5
```

目标：

- 发布 `v1`
- 建立首版 `trusted_*_library`

## 11. Day N（N > 1）

```text
仅导入当天新增数据
  -> Step 1
  -> Step 2/3（读取上一版正式库）
  -> Step 4（只用上一版 donor）
  -> Step 5（维护 + 发布新版本）
```

当前历史重基线的等价执行：

```text
保留现有 Step 1
  -> 取 dayN 的 event_time_std 日桶
  -> Step 2/3（只读上一版正式库）
  -> Step 4（只读上一版 donor）
  -> Step 5
```

## 12. 每日验证

```sql
SELECT batch_id, snapshot_version, finished_at
FROM rebuild5_meta.step3_run_stats
ORDER BY batch_id;

SELECT batch_id, snapshot_version, finished_at
FROM rebuild5_meta.step4_run_stats
ORDER BY batch_id;

SELECT batch_id, snapshot_version, snapshot_version_prev, finished_at
FROM rebuild5_meta.step5_run_stats
ORDER BY batch_id;

SELECT batch_id, input_record_count, path_a_record_count, path_b_record_count, path_c_drop_count
FROM rebuild5_meta.step2_run_stats
ORDER BY batch_id;
```

重基线完成后，应看到：

- `batch_id = 1..7`
- 每批 `input_record_count` 与对应日桶行数一致
- 不再出现从 `batch2` 起 `path_a/path_b/path_c` 完全恒定的“全量重放”特征

## 13. 分支重跑

如果某一天批次失败：

- 只清理该批次未完成的发布结果
- 不回滚更早批次的正式库
- 分支重跑前应先确认日期索引仍然有效
- 不要回到“把整份 `etl_cleaned` 再跑一遍”的验证性语义

脚本已支持从指定批次和阶段继续：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --start-day 2025-12-05 \
  --end-day 2025-12-07 \
  --start-batch-id 5 \
  --resume-phase step4
```

可选 `resume_phase`：

- `step2_3`：从当天 Step 2/3 重新开始
- `step4`：保留当天 Step 2/3 结果，只重做 Step 4/5
- `step5`：保留当天 `enriched_records` / `gps_anomaly_log`，只重做 Step 5
