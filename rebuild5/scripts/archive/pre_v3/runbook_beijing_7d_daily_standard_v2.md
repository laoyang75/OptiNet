# Standard Runbook V2: `rebuild5` 北京 7 天自动化重跑

本文件是当前推荐的 **v2 自动化 runbook**。

目标：

- 用一条自动化脚本完成按天 `Step 1 -> Step 5`
- 支持未来加数据后再次重跑
- 避免人工分步拼接命令

对应脚本：

- `rebuild5/scripts/run_step1_to_step5_daily_loop.py`

---

## 1. 适用范围

适用：

- 当前指定数据集的完整按天重跑
- 更新 `dataset.yaml` 后的再次全量重跑
- 想从原始层按天自动推进到正式库 `batch7`

不适用：

- 只想重跑 Step 2-5
- 只想重跑某一批 Step 4/5
- 只做固定数据的验证性 replay

这些场景继续使用：

- `run_daily_increment_batch_loop.py`
- `run_standard_batch_loop.py`
- `runbook_beijing_7d_standard.md`

---

## 2. v2 的核心语义

脚本会自动做下面几件事：

1. 可选执行 `prepare_current_dataset`
2. 生成全量 `raw_gps` 备份
3. 按 `raw_gps.ts` 切出每天原始数据
4. 每天单独运行 Step 1
5. 把每天的 `etl_cleaned` 追加到累计 ETL 表
6. 每天继续运行 `Step 2 -> Step 5`
7. 最后把累计 ETL 切回正式表 `rebuild5.etl_cleaned`

也就是说，它不是“每天只跑下游”，而是：

```text
raw_gps(day1) -> Step1(day1) -> Step2~5(batch1)
raw_gps(day2) -> Step1(day2) -> Step2~5(batch2)
...
raw_gps(day7) -> Step1(day7) -> Step2~5(batch7)
```

---

## 3. 最常用命令

### 3.1 先看计划

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py --plan-only
```

### 3.2 标准全量自动化重跑

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py
```

这条命令会：

- 重新 prepare 当前数据集
- 清空 Step 2-5 状态
- 按 `dataset.yaml` 中的时间范围逐天跑完

### 3.3 已经 prepare 过，只重跑主链

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py --skip-prepare
```

### 3.4 只跑部分日期

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py \
  --start-day 2025-12-03 \
  --end-day 2025-12-07
```

### 3.5 跳过 Step 2-5 reset

只在你非常明确当前状态可复用时使用：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py \
  --skip-prepare \
  --skip-reset-step2-5
```

---

## 4. 未来加数据后的推荐动作

如果未来基础数据表增加了新数据，推荐动作是：

1. 更新 `rebuild5/config/dataset.yaml`
2. 确认时间范围、源表配置正确
3. 执行：

```bash
cd /Users/yangcongan/cursor/WangYou_Data
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py
```

默认建议仍然是 **全自动从 Step 1 开始按天重跑**，不要手工拼接多个脚本。

原因：

- 它能确保 `raw_gps / etl_cleaned / trusted_*_library` 口径一致
- 它能自动保留调试期 `enriched_records / gps_anomaly_log`
- 它能避免“Step 1 是一天口径、Step 2-5 是另一套口径”的错位

---

## 5. 跑完后的检查

至少检查：

```sql
SELECT batch_id, input_record_count, path_a_record_count, path_b_record_count, path_c_drop_count
FROM rebuild5_meta.step2_run_stats
ORDER BY batch_id;

SELECT batch_id, published_cell_count, published_bs_count, published_lac_count
FROM rebuild5_meta.step5_run_stats
ORDER BY batch_id;

SELECT COUNT(*) FROM rebuild5.raw_gps;
SELECT COUNT(*) FROM rebuild5.etl_cleaned;
```

应满足：

- `step2/3/4/5` 都跑到 `batch7`
- `trusted_*_library` 的最新 `batch_id = 7`
- `raw_gps` 和最终 `etl_cleaned` 都是正式表，不是中间备份表

---

## 6. 当前 v2 结论

后续再次重跑，优先使用：

- `run_step1_to_step5_daily_loop.py`

不要再人工做：

- 手工 prepare
- 手工每天切 raw
- 手工每天跑 Step 1
- 手工再接 Step 2-5

这些都已经收口进 v2 自动化脚本。
