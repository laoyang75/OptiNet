# Standard Runbook V3: `rebuild5` 完整重跑基线

本文件是当前唯一推荐的 **V3 重跑基线 runbook**。

适用场景：

- `M1-M5` 修补后，重新交付一版全链路新数据
- 后续继续加数据后，再次整链重跑
- 先用样例数据验证，再用完整正式数据交付

前置必读：

- `rebuild5/docs/fix1/10_M1-M5代码修补与重跑说明.md`

---

## 1. V3 的核心原则

这次 V3 与历史 runbook 的根本区别是：

1. **先样例，再正式**
2. **正式交付必须从 Step 1 跑到 Step 5**
3. **按天推进**
4. **允许删除旧数据，按新代码完整重跑**
5. **后续重复执行时，优先复用同一套自动化脚本**

也就是说，正式链路必须是：

```text
day1 原始数据 -> Step1(day1) -> Step2~5(batch1)
day2 原始数据 -> Step1(day2) -> Step2~5(batch2)
...
day7 原始数据 -> Step1(day7) -> Step2~5(batch7)
```

而不是：

- 一次性把 7 天原始数据全跑成一张总 `etl_cleaned`
- 再只按天切下游

---

## 2. V3 基线脚本

当前 V3 只认下面三类脚本：

- `rebuild5/scripts/build_daily_sample_etl_input.py`
- `rebuild5/scripts/run_daily_increment_batch_loop.py`
- `rebuild5/scripts/run_step1_to_step5_daily_loop.py`

辅助 reset：

- `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql`

说明：

- 样例验证使用 `run_daily_increment_batch_loop.py`
- 正式交付使用 `run_step1_to_step5_daily_loop.py`

---

## 3. Phase A：样例数据验证

当前样例基线：

- `rebuild5.etl_cleaned_top10_lac_sample`

目标：

- 先验证 `M3/M4/M5` 改动后的下游闭环是否稳定
- 不在样例阶段重做完整 Step 1 原始切片
- 重点确认 Step 2~5 的结果口径已经切到新代码

### 3.1 先清旧 Step 2-5 状态

```bash
cd /Users/yangcongan/cursor/WangYou_Data
psql "$REBUILD5_PG_DSN" -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

### 3.2 查看样例日桶计划

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5.etl_cleaned_top10_lac_sample \
  --start-day 2025-12-01 \
  --end-day 2025-12-07 \
  --plan-only
```

### 3.3 跑通样例 7 天

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5.etl_cleaned_top10_lac_sample \
  --start-day 2025-12-01 \
  --end-day 2025-12-07
```

### 3.4 样例通过标准

至少检查：

```sql
SELECT batch_id, input_record_count, path_a_record_count, path_b_record_count, path_c_drop_count
FROM rebuild5_meta.step2_run_stats
ORDER BY batch_id;

SELECT batch_id, total_path_a, donor_matched_count, gps_filled, gps_anomaly_count
FROM rebuild5_meta.step4_run_stats
ORDER BY batch_id;

SELECT batch_id, published_cell_count, published_bs_count, published_lac_count,
       multi_centroid_cell_count, dynamic_cell_count, anomaly_bs_count
FROM rebuild5_meta.step5_run_stats
ORDER BY batch_id;
```

样例通过的最低要求：

- `step2/3/4/5` 全部跑到 `batch7`
- `batch3` 起出现真实 `Path A`
- `Step 4` 的 `donor_matched_count`、`gps_filled`、`gps_anomaly_count` 不再是 `0`
- `Step 5` 的 `published_cell_count`、`published_bs_count`、`published_lac_count` 持续增长

---

## 4. Phase B：正式完整重跑

这是最终交付动作。

### 4.1 目标

- 允许删除旧派生数据
- 从当前指定数据集完整重跑
- 最终得到新的：
  - `raw_gps`
  - `etl_cleaned`
  - `trusted_snapshot_*`
  - `enriched_records / gps_anomaly_log`
  - `trusted_*_library`
  - `collision_id_list`

### 4.2 先看计划

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py --plan-only
```

### 4.3 正式执行

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py
```

这条命令会自动：

1. `prepare_current_dataset`
2. 执行 `reset_step1_to_step5_for_full_rerun_v3.sql`
3. 按 `raw_gps.ts` 逐天切出原始数据
4. 每天跑一次 Step 1
5. 每天把当天 `etl_cleaned` 追加到累计 ETL
6. 每天继续跑 `Step 2 -> Step 5`
7. 最后把累计 ETL 收口回正式 `rebuild5.etl_cleaned`

### 4.4 如果原始数据已 prepare 完成

可复用当前全量原始表：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py --skip-prepare
```

---

## 5. 正式跑完后的交付检查

至少检查：

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

交付完成标准：

- `step2/3/4/5` 都到 `batch7`
- `trusted_*_library` 当前最新 `batch_id = 7`
- `rebuild5.raw_gps` 是完整正式原始表
- `rebuild5.etl_cleaned` 是 7 天累计后的正式 ETL 表
- `enriched_records / gps_anomaly_log` 调试期持久保留

---

## 6. 未来加数据后的推荐动作

以后如果继续新增数据，仍按 V3 执行：

1. 更新 `rebuild5/config/dataset.yaml`
2. 先样例验证
3. 再正式执行：

```bash
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py
```

不要再回到：

- 手工 prepare
- 手工切每天 raw
- 手工每天跑 Step 1
- 手工每天再拼接 Step 2~5

V3 的目标就是把这些动作收口到同一套自动化脚本。

---

## 7. 当前基线结论

后续所有“重新交付数据”的工作，都以本文件和以下脚本为新基线：

- `run_step1_to_step5_daily_loop.py`
- `run_daily_increment_batch_loop.py`
- `reset_step1_to_step5_for_full_rerun_v3.sql`

历史 runbook 和历史 rerun 脚本仅保留在 archive 中，不再作为执行标准。
