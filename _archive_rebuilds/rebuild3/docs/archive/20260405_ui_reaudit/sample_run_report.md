# 样本运行记录

## 执行步骤

1. 执行 `backend/sql/schema/001_foundation.sql`，创建 `rebuild3 / rebuild3_meta / rebuild3_sample / rebuild3_sample_meta` 独立 schema。
2. 执行 `backend/sql/init/001_sample_extract.sql`，抽取同一份样本到 `rebuild3_sample.source_l0_lac` 与 `rebuild3_sample.source_l0_gps`。
3. 执行 `backend/sql/init/002_rebuild2_sample_eval.sql`，在 `rebuild3_sample_meta.r2_*` 下完成 rebuild2 样本重跑。
4. 执行 `backend/sql/govern/001_rebuild3_sample_pipeline.sql`，在 `rebuild3_sample*` 下完成 rebuild3 样本治理链路。

## rebuild3 样本批次快照

| stage_name | metric_name | metric_value |
| --- | --- | --- |
| baseline | baseline_bs | 3 |
| baseline | baseline_cell | 32 |
| baseline | baseline_lac | 3 |
| input | fact_standardized | 34998 |
| objects | obj_bs | 9 |
| objects | obj_cell | 100 |
| objects | obj_lac | 9 |
| routing | fact_governed | 21067 |
| routing | fact_pending_issue | 13681 |
| routing | fact_pending_observation | 50 |
| routing | fact_rejected | 200 |

## rebuild2 样本路由统计

| fact_route | row_count |
| --- | --- |
| fact_governed | 21273 |
| fact_pending_issue | 13475 |
| fact_pending_observation | 50 |
| fact_rejected | 200 |

## rebuild3 样本路由统计

| fact_route | row_count |
| --- | --- |
| fact_governed | 21067 |
| fact_pending_issue | 13681 |
| fact_pending_observation | 50 |
| fact_rejected | 200 |

## 日志位置

- `rebuild3/.logs/001_foundation.log`
- `rebuild3/.logs/001_sample_extract.log`
- `rebuild3/.logs/002_rebuild2_sample_eval.log`
- `rebuild3/.logs/001_rebuild3_sample_pipeline.log`
