# 重跑 Prompt：优化验证与完整重跑

你在 `/Users/yangcongan/cursor/WangYou_Data` 中执行一轮 **rebuild5 优化验证 + 文档更新 + 数据清理 + 完整重跑**。

这是一轮 **成果落地型执行任务**，不是再次开放式分析。

你的任务不是重新讨论优化方案是否成立，而是：

1. 按既定修改项独立实现
2. 用样例库严格验证
3. 验证通过后更新文档
4. 清理样例数据
5. 尽快进入完整重跑

本轮工作分为四个阶段，必须按顺序执行，不能跳过。

## 一、背景

前一轮速度优化评估已完成，评估报告见：

- `rebuild5/docs/速度优化评估_claude.md`

优化方案已在样例库（`ip_loc2_fix4_codex`，batch1-3）上验证通过：

- 34 个单元测试全部通过
- 所有结果字段严格一致
- batch3 总耗时从约 `59s` 降至约 `48s`（约 `-19%`）

本轮任务是：

你作为一个全新会话，**独立落实这些优化**、完成样例验证、更新文档、清理样例数据，然后执行完整重跑。

### 非目标

以下内容不是本轮主目标：

1. 不再次做开放式优化研究
2. 不重新讨论 A-F 修改项是否值得做
3. 不把这轮工作带回“重新探索方向”

### 允许的审计

你可以在实施前做“修改点审计”，但目的只有两个：

1. 确认当前代码是否已经包含某项修改
2. 防止漏改、重复改、误改

**审计不是为了推翻方案。**

本轮判断标准不是“你主观觉得改法优不优”，而是：

- 样例结果是否严格对齐
- 流程是否按标准完成

## 二、必须先读的文档

按顺序阅读：

1. `rebuild5/docs/处理流程总览.md` — 全链路状态机
2. `rebuild5/docs/runbook_v5.md` — 当前执行基线
3. `rebuild5/docs/速度优化评估_claude.md` — 本轮优化方案和测试结果

## 三、业务前提（不可改动）

### 1. Step3 生命周期

- `waiting`: `independent_obs < 3`
- `observing`: `3 <= independent_obs < 10`
- `qualified`: `independent_obs >= 10`
- `excellent`: `independent_obs >= 30`

### 2. Step4 donor

- donor 由 Step2 确认
- Step4 不再对 `anchor_eligible` 做 donor 二次门槛

### 3. GPS / 质心

- 保留当前主热点 seed + 核心点过滤逻辑

### 4. 本轮判断标准

本轮不以“实现方式是否和上次一模一样”作为成功标准，而以：

1. 样例结果是否严格一致
2. 测试是否通过
3. 完整重跑是否顺利进入为准

## 四、环境

### 1. 样例库（阶段一用）

```bash
export REBUILD5_PG_DSN='postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_fix4_codex'
```

### 2. 样例数据

- 输入表：`rebuild5_fix4_work.etl_cleaned_shared_sample_local`
- 日期范围：`2025-12-01 ~ 2025-12-03`（batch1-3）

### 3. 推荐工具

- MCP `PG17` 或 `psql`
- SQL 要小、清晰、一次只回答一个问题

## 五、阶段一：独立验证优化方案

**目标：** 你需要独立落实下列 6 项代码修改，然后在样例库上验证。

这里的“独立落实”意思是：

- 不是 cherry-pick
- 不是机械照抄 diff
- 而是按方案说明自己实现

但你不应再重新讨论这 6 项要不要做。

### 5.1 需要落实的 6 项修改

#### 修改 A：合并 `metrics_activity` 到 `metrics_base`

**文件：** `rebuild5/backend/app/maintenance/window.py`

**函数：** `build_cell_metrics_base()`

**做法：**

1. 在 CTAS 开头加一个 CTE `window_max`，取 `MAX(event_time_std)` 作为时间参考点
2. 在 SELECT 末尾增加两个字段，**计算逻辑直接照搬当前 `build_cell_activity_stats()` 的现有逻辑**，不要自行发明新口径：
   - `active_days_30d`
     ```sql
     COUNT(DISTINCT DATE(event_time_std))
       FILTER (WHERE event_time_std >= (SELECT ref_time - INTERVAL '30 days' FROM window_max))
     ```
   - `consecutive_inactive_days`
     ```sql
     EXTRACT(DAY FROM (SELECT ref_time FROM window_max) - MAX(event_time_std))::integer
     ```
3. 在 CTAS 后、ANALYZE 前，增加复合索引：
   - `(batch_id, operator_code, lac, bs_id, cell_id, tech_norm)`

**函数：** `build_cell_metrics_window()`

**做法：**

1. 将 `COALESCE(a.active_days_30d, 0)` 改为 `COALESCE(m.active_days_30d, 0)`
2. 将 `COALESCE(a.consecutive_inactive_days, 0)` 改为 `COALESCE(m.consecutive_inactive_days, 0)`
3. 删除 `LEFT JOIN rebuild5.cell_activity_stats a ON ...`

**函数：** `recalculate_cell_metrics()`

**做法：**

- 删除对 `build_cell_activity_stats()` 的调用

#### 修改 B：为 `cell_radius_stats` 加索引

**文件：** `rebuild5/backend/app/maintenance/window.py`

**函数：** `build_cell_radius_stats()`

**做法：**

在 `SET (autovacuum_enabled = false)` 和 `ANALYZE` 之间，增加：

```sql
CREATE INDEX idx_cell_radius_stats_key
ON rebuild5.cell_radius_stats (operator_code, lac, bs_id, cell_id, tech_norm)
```

#### 修改 C：为 Step2 `_path_a_layer2` 加索引

**文件：** `rebuild5/backend/app/profile/pipeline.py`

**函数：** `build_path_a_records()`

**做法：**

在 `build_path_a_records()` 内，精确插入到下面两句代码之间：

```python
_disable_autovacuum('rebuild5._path_a_layer2')
execute('DROP TABLE IF EXISTS rebuild5._path_a_layer3_all')
```

也就是：**紧跟 `_disable_autovacuum('rebuild5._path_a_layer2')` 之后**，增加：

```sql
CREATE INDEX idx_path_a_layer2_source_tid
ON rebuild5._path_a_layer2 (source_tid)
```

#### 修改 D：为 Step2 `_profile_path_b_cells` 加索引

**文件：** `rebuild5/backend/app/profile/pipeline.py`

**函数：** `build_path_b_cells()`

**做法：**

在 `build_path_b_cells()` 内，精确插入到下面两句代码之间：

```python
_disable_autovacuum('rebuild5._profile_path_b_cells')
execute('DROP TABLE IF EXISTS rebuild5._profile_path_b_records')
```

也就是：**紧跟 `_disable_autovacuum('rebuild5._profile_path_b_cells')` 之后**，增加：

```sql
CREATE INDEX idx_profile_path_b_cells_key
ON rebuild5._profile_path_b_cells (operator_code, lac, cell_id, tech_norm)
```

然后执行：

```sql
ANALYZE rebuild5._profile_path_b_cells
```

#### 修改 E：`cell_sliding_window` 设置 `parallel_workers=16`

**文件：** `rebuild5/backend/app/maintenance/pipeline.py`

**函数：** `run_maintenance_pipeline()`

**做法：**

在 `idx_csw_lookup` 索引创建之后、`_tick('daily_centroids')` 之前，增加：

```python
execute('ALTER TABLE rebuild5.cell_sliding_window SET (parallel_workers = 16)')
```

同时，**在 `rebuild5/backend/app/maintenance/pipeline.py` 这个文件里**，移除：

1. 对 `build_cell_activity_stats()` 的调用
2. 对应的 `_tick('metrics_activity')` 行

说明：

- 这一步操作的是 `maintenance/pipeline.py`
- 不同于修改 A 操作的 `maintenance/window.py`
- 两边都需要改，不能只改一边

#### 修改 F：更新测试

**文件：** `rebuild5/tests/test_pipeline_version_guards.py`

**做法：**

删除 `test_build_cell_metrics_window_joins_materialized_stage_tables` 中对：

```sql
LEFT JOIN rebuild5.cell_activity_stats a
```

的断言。

### 5.2 阶段一的正确执行方式

先做修改点审计：

1. 当前代码是否已经包含其中一部分修改
2. 哪些仍缺失

然后：

- 补齐缺失项
- 不重复改已完成项

### 5.3 验证步骤

**第一步：运行单元测试**

```bash
pytest rebuild5/tests/test_pipeline_version_guards.py \
       rebuild5/tests/test_profile_logic.py \
       rebuild5/tests/test_publish_bs_lac.py \
       rebuild5/tests/test_publish_cell.py \
       rebuild5/tests/test_maintenance_queries.py \
       rebuild5/tests/test_enrichment_queries.py
```

预期：

- `34 passed`
- `0 failed`

**第二步：重置样例库**

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable \
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

**第三步：运行样例 batch1-3**

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-01 \
  --end-day 2025-12-03
```

**第四步：对比结果**

以下结果必须**严格一致**，偏差视为回归：

`batch1`
- Step2: `pathA=0`, `pathB=292,872`, `pathB_cell=13,490`, `pathC=334`
- Step3: `waiting=3,275`, `qualified=3,807`, `excellent=1,939`, `anchor=0`
- Step4: `pathA=0`, `donor_matched=0`, `gps_filled=0`, `gps_anomaly=0`
- Step5: `published_cell=5,746`, `published_bs=3,124`, `published_lac=18`, `multi_centroid=0`, `dynamic=0`

`batch2`
- Step2: `pathA=235,711`, `pathB=57,905`, `pathB_cell=7,672`, `pathC=184`
- Step3: `waiting=2,816`, `qualified=6,337`, `excellent=2,084`, `anchor=1,976`
- Step4: `pathA=235,711`, `donor_matched=235,711`, `gps_filled=14,362`, `gps_anomaly=6,450`
- Step5: `published_cell=8,421`, `published_bs=4,115`, `published_lac=21`, `multi_centroid=0`, `dynamic=0`

`batch3`
- Step2: `pathA=247,441`, `pathB=23,953`, `pathB_cell=4,748`, `pathC=210`
- Step3: `waiting=2,536`, `qualified=7,674`, `excellent=2,120`, `anchor=2,886`
- Step4: `pathA=247,441`, `donor_matched=247,441`, `gps_filled=15,161`, `gps_anomaly=7,108`
- Step5: `published_cell=9,794`, `published_bs=4,563`, `published_lac=21`, `multi_centroid=113`, `dynamic=0`

验证 SQL：

```sql
SELECT batch_id, path_a_record_count, path_b_record_count, path_b_cell_count, path_c_drop_count
FROM rebuild5_meta.step2_run_stats ORDER BY batch_id;

SELECT batch_id, waiting_cell_count, qualified_cell_count, excellent_cell_count, anchor_eligible_cell_count
FROM rebuild5_meta.step3_run_stats ORDER BY batch_id;

SELECT batch_id, total_path_a, donor_matched_count, gps_filled, gps_anomaly_count
FROM rebuild5_meta.step4_run_stats ORDER BY batch_id;

SELECT batch_id, published_cell_count, published_bs_count, published_lac_count,
       collision_cell_count, multi_centroid_cell_count, dynamic_cell_count
FROM rebuild5_meta.step5_run_stats ORDER BY batch_id;
```

**第五步：确认 Step5 子步骤耗时**

从日志中提取 `[Step 5 子步骤耗时]` 输出，确认：

- `metrics_activity` 子步骤已消除

### 5.4 阶段一完成标准

- 单元测试 `34 passed`
- batch1-3 所有结果字段严格一致
- Step5 日志中不再出现 `metrics_activity`
- 未引入新的测试失败或运行时错误

**如果阶段一失败，停止后续阶段。**

## 六、阶段二：更新文档

这一阶段是收尾，不是主目标。

只有阶段一通过后才更新。

### 6.1 更新 `runbook_v5.md`

需要更新的内容：

1. 日期和状态行
2. 在“当前代码基线”中增加：
   - `metrics_activity` 合并入 `metrics_base`
   - `cell_sliding_window` 设置 `parallel_workers=16`
   - Step2 / Step5 中间表索引优化
3. 如果样例耗时有变化，可补充说明

### 6.2 更新 `速度优化评估_claude.md`

在报告末尾增加：

```markdown
## 附录：独立验证记录

- 验证时间：<当前时间>
- 验证方式：新会话独立实施代码修改并跑样例
- 验证结果：<通过/失败>
- 单元测试：34 passed
- 样例结果：<严格一致/有偏差（说明）>
```

## 七、阶段三：清理样例数据

### 7.1 重置样例库

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable \
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

### 7.2 确认清理完成

```sql
SELECT COUNT(*) FROM rebuild5_meta.step2_run_stats;
SELECT COUNT(*) FROM rebuild5_meta.step3_run_stats;
SELECT COUNT(*) FROM rebuild5_meta.step4_run_stats;
SELECT COUNT(*) FROM rebuild5_meta.step5_run_stats;
SELECT COUNT(*) FROM rebuild5.trusted_cell_library;
```

全部应为 `0`。

补充说明：

- 当前 `reset_step2_to_step5_for_daily_rebaseline.sql` 的范围包含：
  - `step2/3/4/5` run stats
  - `trusted_cell_library`
- 所以这里要求全部为 `0` 是合理且预期中的结果，不是额外假设。

## 八、阶段四：完整重跑与监控

### 8.1 目标

这一阶段的目标不是继续研究，而是：

- 在样例验证通过后，尽快完成完整重跑

### 8.2 执行完整重跑（batch1-7）

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-01 \
  --end-day 2025-12-07
```

### 8.3 定期监控

```sql
SELECT 'step2' AS step, MAX(batch_id) AS max_batch FROM rebuild5_meta.step2_run_stats
UNION ALL SELECT 'step3', MAX(batch_id) FROM rebuild5_meta.step3_run_stats
UNION ALL SELECT 'step4', MAX(batch_id) FROM rebuild5_meta.step4_run_stats
UNION ALL SELECT 'step5', MAX(batch_id) FROM rebuild5_meta.step5_run_stats;
```

如果怀疑卡死，再查：

```sql
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS query_age,
       left(query, 300) AS query_snippet
FROM pg_stat_activity
WHERE datname = 'ip_loc2_fix4_codex'
  AND state <> 'idle'
ORDER BY query_start;
```

### 8.4 重跑完成后验证

- batch1-3 必须继续与阶段一结果严格一致
- batch4-7 结果可参考 `runbook_v5.md` 中历史记录

### 8.5 监控注意事项

参考：

- `rebuild5/docs/重跑监督Prompt.md`

原则：

1. 不要把“没有新日志”直接等同于卡死
2. Step5 `metrics_radius` 仍是已知热点
3. 如果真的卡死，再按监督 prompt 处理

### 8.6 阶段四完成标准

阶段四必须同时满足以下条件，才算完成：

1. `step2_run_stats` 的 `max(batch_id) = 7`
2. `step3_run_stats` 的 `max(batch_id) = 7`
3. `step4_run_stats` 的 `max(batch_id) = 7`
4. `step5_run_stats` 的 `max(batch_id) = 7`
5. batch1-3 结果继续与阶段一严格一致
6. batch4-7 没有运行时错误，没有中途批次缺失
7. 只要某一批 `pathA > 0`，就必须满足：
   - `donor_matched = total_path_a`

### 8.7 batch4-7 与历史记录的关系

batch4-7 的历史记录是**参考值**，不是当前 prompt 中的硬编码真值。

处理原则：

1. 如果 batch4-7 与历史记录大体一致，记录为“正常”
2. 如果 batch4-7 与历史记录有明显偏差：
   - 不要直接忽略
   - 必须记录偏差项
   - 必须判断是运行异常、代码回归，还是当前代码行为变化

也就是说：

- batch1-3 用于**严格回归验证**
- batch4-7 用于**完整重跑完成性验证 + 偏差审计**

## 九、必须产出

本轮工作完成后，至少产出：

1. 阶段一验证结论（通过/失败 + 结果对比）
2. 更新后的 `runbook_v5.md`
3. 更新后的 `速度优化评估_claude.md`（附录部分）
4. batch1-7 重跑结果记录
5. 过程中出现的异常记录（如有）

## 十、最核心的一句话

这份 prompt 的定位是：

**已确认优化方案的独立落实、验证、清理和重跑。**

不是重新做一轮开放式分析。
