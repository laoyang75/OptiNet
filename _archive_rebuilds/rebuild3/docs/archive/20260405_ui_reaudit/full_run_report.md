# 全量运行报告

## 执行阶段与门禁

1. Gate E-1：执行 `backend/sql/govern/002_rebuild3_full_pipeline.sql`，完成 rebuild3 全量对象、事实、baseline 构建。
2. Gate E-2：补写 `fact_pending_observation` 中缺失的未注册对象记录，并刷新批次快照与路由汇总。
3. Gate E-3：修正 BS / LAC 资格级联过滤，确保 BS 资格严格来源于 Cell、LAC 资格严格来源于 BS。
4. Gate E-4：执行 `backend/sql/compare/002_prepare_full_compare.sql`，准备 rebuild2 全量对比状态表。
5. Gate E-5：校验 `batch_snapshot` 与实际表计数一致，确认全量路由闭环后进入偏差评估。

## 批次上下文

- run_id：`RUN-FULL-20251201-20251207-V1`
- batch_id：`BATCH-FULL-20251201-20251207-V1`
- 窗口：`2025-12-01 00:00:00+08` 至 `2025-12-07 23:59:59+08`
- 状态：`completed`
- input_rows：`43771306`
- output_rows：`43771306`

## 输入规模

- rebuild2 全量输入：`43771306`
- 有效主键记录：`39271905`
- 无效主键记录：`4499401`
- 无效主键占比：10.28%

## rebuild3 全量批次快照

| stage_name | metric_name | metric_value |
| --- | --- | --- |
| baseline | baseline_bs | 93110 |
| baseline | baseline_cell | 194952 |
| baseline | baseline_lac | 866 |
| input | fact_standardized | 43771306 |
| objects | obj_bs | 193036 |
| objects | obj_cell | 573561 |
| objects | obj_lac | 50153 |
| routing | fact_governed | 24855605 |
| routing | fact_pending_issue | 3825562 |
| routing | fact_pending_observation | 10590738 |
| routing | fact_rejected | 4499401 |

## rebuild3 全量四分流

| fact_layer | row_count | row_ratio |
| --- | --- | --- |
| fact_governed | 24855605 | 0.5679 |
| fact_pending_issue | 3825562 | 0.0874 |
| fact_pending_observation | 10590738 | 0.2420 |
| fact_rejected | 4499401 | 0.1028 |

## rebuild2 对比侧准备结果

| table_name | row_count |
| --- | --- |
| r2_full_bs_state | 193036 |
| r2_full_cell_state | 573561 |
| r2_full_lac_state | 50153 |
| r2_full_route_summary | 43771306 |

## 运行说明

- 全量主链路已完成，并补齐了 `missing_object_registration` 观察池记录，保证四分流总量与 `fact_standardized` 完全闭环。
- 已修正 BS / LAC 资格级联过滤：BS 的 `anchorable` / `baseline_eligible` 严格来源于子 Cell，LAC 严格来源于子 BS。
- `batch_snapshot` 与实际落表计数一致，可直接作为 UI 与后续评估的读模型输入。
- 对比侧 `r2_full_*` 已按全量输入重建，可用于对象状态、资格、baseline 与四分流偏差评估。

## 日志位置

- `rebuild3/.logs/002_rebuild3_full_pipeline.log`
- `rebuild3/.logs/002_rebuild3_full_pipeline_resume.log`
- `rebuild3/.logs/002_prepare_full_compare.log`
