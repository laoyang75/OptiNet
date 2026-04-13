# Prompt: rebuild5 V3 全量重跑与新数据交付

你在 `/Users/yangcongan/cursor/WangYou_Data` 继续 `rebuild5`。

本轮目标非常明确：

- 以 **V3 基线** 完成一版新的数据交付
- 允许删除旧派生数据
- 先用样例数据验证跑通
- 再用完整正式数据执行全链路重跑

注意：

- 旧的 runbook 和旧 rerun 脚本都已归档
- 当前必须以 **V3 基线** 作为唯一执行标准

---

## 0. 开始前必须先读

先读这些文件：

- `rebuild5/docs/fix1/10_M1-M5代码修补与重跑说明.md`
- `rebuild5/scripts/runbook_beijing_7d_daily_standard_v3.md`
- `rebuild5/docs/09_控制操作_初始化重算与回归.md`
- `rebuild5/docs/03_流式质量评估.md`
- `rebuild5/docs/04_知识补数.md`
- `rebuild5/docs/05_画像维护.md`

如果要看执行脚本，只看当前 V3 基线相关：

- `rebuild5/scripts/run_step1_to_step5_daily_loop.py`
- `rebuild5/scripts/run_daily_increment_batch_loop.py`
- `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql`
- `rebuild5/scripts/build_daily_sample_etl_input.py`

不要再把 archive 中的历史 runbook / 历史脚本当成主执行依据。

---

## 1. 本轮必须遵守的执行原则

### 1.1 先样例，后正式

必须先完成：

- 样例数据 `Step 2 -> Step 5` 的 7 天验证

确认通过后，才能执行：

- 正式数据 `Step 1 -> Step 5` 的 7 天完整重跑

### 1.2 正式交付必须是全链路

正式数据阶段必须按天执行：

```text
day1 原始数据 -> Step1(day1) -> Step2~5(batch1)
day2 原始数据 -> Step1(day2) -> Step2~5(batch2)
...
day7 原始数据 -> Step1(day7) -> Step2~5(batch7)
```

也就是说：

- `Step 1` 要跑 7 次
- `Step 2~5` 也要跑 7 次

### 1.3 允许删除旧派生数据

本次是 **完全重跑**。

可以删除：

- 旧 `etl_cleaned`
- 旧 `trusted_snapshot_*`
- 旧 `enriched_records / gps_anomaly_log`
- 旧 `trusted_*_library`
- 旧 `collision_id_list`
- 旧 `step1~5` 运行统计

目标不是保留历史派生结果，而是得到一版新的、与 V3 代码和设计一致的数据。

---

## 2. 样例阶段

样例基线：

- `rebuild5.etl_cleaned_top10_lac_sample`

先执行：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
psql "$REBUILD5_PG_DSN" -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

再执行样例验证：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5.etl_cleaned_top10_lac_sample \
  --start-day 2025-12-01 \
  --end-day 2025-12-07
```

样例通过标准：

- `step2/3/4/5` 都跑到 `batch7`
- `batch3` 起出现真实 `Path A`
- `step4_run_stats` 中 `donor_matched_count`、`gps_filled`、`gps_anomaly_count` 不再是 `0`
- `step5_run_stats` 中 `published_*`、`multi_centroid_cell_count`、`anomaly_bs_count` 有合理增长

如果样例没有通过：

- 先修代码
- 再重新从样例阶段开始
- 不要直接跳到正式数据

---

## 3. 正式阶段

样例通过后，执行正式完整重跑：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py
```

这条命令会自动：

1. `prepare_current_dataset`
2. 使用 `reset_step1_to_step5_for_full_rerun_v3.sql`
3. 按 `raw_gps.ts` 逐天切原始数据
4. 每天跑一次 Step 1
5. 每天跑一次 Step 2~5
6. 最后自动把累计 ETL 收口回正式 `rebuild5.etl_cleaned`

---

## 4. 正式交付完成后的必查项

必须检查：

```sql
SELECT batch_id, input_record_count, path_a_record_count, path_b_record_count, path_c_drop_count
FROM rebuild5_meta.step2_run_stats
ORDER BY batch_id;

SELECT batch_id, snapshot_version, qualified_cell_count, excellent_cell_count
FROM rebuild5_meta.step3_run_stats
ORDER BY batch_id;

SELECT batch_id, total_path_a, donor_matched_count, gps_filled, gps_anomaly_count
FROM rebuild5_meta.step4_run_stats
ORDER BY batch_id;

SELECT batch_id, published_cell_count, published_bs_count, published_lac_count
FROM rebuild5_meta.step5_run_stats
ORDER BY batch_id;

SELECT COUNT(*) FROM rebuild5.raw_gps;
SELECT COUNT(*) FROM rebuild5.etl_cleaned;
```

交付通过标准：

- `step2/3/4/5` 都到 `batch7`
- `trusted_cell_library / trusted_bs_library / trusted_lac_library` 最新 `batch_id = 7`
- `rebuild5.raw_gps` 是完整正式原始表
- `rebuild5.etl_cleaned` 是 7 天累计后的正式 ETL 表
- `enriched_records / gps_anomaly_log` 在调试期保留

---

## 5. 最终输出要求

完成后，最终回复至少包含：

1. 样例阶段是否通过
2. 正式阶段是否完成到 `batch7`
3. 最终：
   - `raw_gps` 行数
   - `etl_cleaned` 行数
   - `trusted_cell_library(batch7)` 行数
   - `trusted_bs_library(batch7)` 行数
   - `trusted_lac_library(batch7)` 行数
4. 是否还有未完成的索引 / 收尾动作

如果中途失败：

- 明确失败在哪一天、哪一步
- 给出当前数据库已完成到哪个 `batch`
- 说明下一次继续跑应该从哪里恢复

---

## 6. 当前基线强调

本轮不要再重新发明执行流程。

以这几个文件为基线：

- `runbook_beijing_7d_daily_standard_v3.md`
- `run_step1_to_step5_daily_loop.py`
- `run_daily_increment_batch_loop.py`

旧 runbook / 旧 rerun 脚本都只在 archive 中保留，不再作为执行标准。
