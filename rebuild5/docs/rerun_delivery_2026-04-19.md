# Rebuild5 重跑交付记录

时间：2026-04-19
数据库：`ip_loc2`
范围：恢复正确 Step1 基线后，重跑 `Step2 -> Step5` `batch1-7`

## 1. Step1 恢复结论

本次正式重跑前，先确认并修复了 Step1 正式表状态异常：

- `rebuild5.raw_gps_full_backup` 为完整 7 天原始表，共 `25,442,069` 行
- `rebuild5_tmp.etl_cumulative_20251207` 为完整 7 天累计 ETL，共 `45,314,465` 行
- 当时正式 `rebuild5.raw_gps` 只剩 `2025-12-07`
- 当时正式 `rebuild5.etl_cleaned` 只等于 `rebuild5_tmp.etl_step1_20251207`

恢复动作：

1. 将正式 `rebuild5.raw_gps` 恢复为 `raw_gps_full_backup`
2. 将正式 `rebuild5.etl_cleaned` 物化为 `rebuild5_tmp.etl_cumulative_20251207`

恢复后 7 天分布：

| relation | 2025-12-01 | 2025-12-02 | 2025-12-03 | 2025-12-04 | 2025-12-05 | 2025-12-06 | 2025-12-07 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rebuild5.raw_gps` | 3,885,832 | 3,893,994 | 3,645,783 | 3,556,320 | 3,441,403 | 3,394,782 | 3,623,955 |
| `rebuild5.etl_cleaned` | 6,920,279 | 6,952,221 | 6,441,960 | 6,274,687 | 6,114,178 | 6,094,285 | 5,988,071 |

## 2. 重点 Cell 监控

监控键统一使用业务主键：

- `5792399381 -> 46000 / 5G / lac 2097238 / bs 1414160`
- `608244101 -> 46001 / 5G / lac 81928 / bs 148497`
- `1691226115 -> 46001 / 5G / lac 405509 / bs 412897`
- `1353583(main) -> 46001 / 4G / lac 6423 / bs 5287`
- `1353583(side) -> 46011 / 4G / lac 6423 / bs 5287`

### 2.1 原始层与 Step1

| cell | raw_days | raw_rows | etl_days | etl_rows |
|---|---:|---:|---:|---:|
| `5792399381` | 7 | 90 | 7 | 90 |
| `608244101` | 5 | 23 | 5 | 23 |
| `1691226115` | 7 | 117 | 7 | 117 |
| `1353583(main+side)` | 7 | 509 | 8 | 509 |

### 2.2 两轮流转确认

`batch1 -> batch2` 已用 MCP 逐键核对：

| cell | batch1 snapshot | batch2 snapshot | batch2 seed/window | batch2 library |
|---|---|---|---|---|
| `608244101` | `observing obs=7` | `qualified obs=18` | `18 minute_obs / 2 days` | `qualified obs=18` |
| `5792399381` | `observing obs=9` | `qualified obs=16` | `16 minute_obs / 2 days` | `qualified obs=16` |
| `1691226115` | `observing obs=9` | `qualified obs=20` | `20 minute_obs / 2 days` | `qualified obs=20` |
| `1353583(main)` | `excellent obs=61` | `excellent obs=61` | 当前批无新 seed，下一批走 `Path A` | `excellent obs=88` |

说明：

- 当前批新晋级对象（如 `608244101`、`5792399381`、`1691226115`）在 `batch2` 已正常进入 `snapshot_seed_records -> cell_sliding_window -> trusted_cell_library`
- 已发布对象（如 `1353583(main)`）在 `batch2` 不再走 seed，而是进入 `Path A / enriched_records`

### 2.3 batch7 终态

| cell | batch7 state | obs | devs | days | p90_radius_m | centroid_pattern |
|---|---|---:|---:|---:|---:|---|
| `5792399381` | `qualified` | 44 | 7 | 4 | 384.31 | `<null>` |
| `608244101` | `qualified` | 21 | 8 | 4 | 126.16 | `<null>` |
| `1691226115` | `qualified` | 101 | 22 | 7 | 307.32 | `multi_cluster` |
| `1353583(main)` | `excellent` | 447 | 11 | 6 | 92539.62 | `<null>` |

备注：

- `1353583` 存在 side combo：`46011 / 4G / lac 6423 / bs 5287`，该组合在 `batch1-2` 保持 `waiting`
- 监控与发布判断必须按完整业务键，不可只按 `cell_id`

## 3. 正式重跑结果

### 3.1 Step2

| batch | Path A | Path B | Path B Cell | Path C |
|---|---:|---:|---:|---:|
| 1 | 0 | 6,153,534 | 591,980 | 766,745 |
| 2 | 3,803,202 | 2,424,085 | 445,797 | 724,934 |
| 3 | 4,465,220 | 1,274,854 | 323,629 | 701,886 |
| 4 | 4,690,281 | 900,561 | 260,454 | 683,845 |
| 5 | 4,746,135 | 707,970 | 221,061 | 660,073 |
| 6 | 4,833,277 | 608,997 | 190,051 | 652,011 |
| 7 | 4,911,749 | 499,254 | 164,953 | 577,068 |

### 3.2 Step4

| batch | total_path_a | donor_matched | gps_filled | gps_anomaly |
|---|---:|---:|---:|---:|
| 1 | 0 | 0 | 0 | 0 |
| 2 | 3,803,202 | 3,803,202 | 371,564 | 98,580 |
| 3 | 4,465,220 | 4,465,220 | 459,135 | 123,549 |
| 4 | 4,690,218 | 4,690,218 | 487,057 | 134,882 |
| 5 | 4,746,069 | 4,746,069 | 510,204 | 141,672 |
| 6 | 4,833,218 | 4,833,218 | 502,889 | 141,681 |
| 7 | 4,911,671 | 4,911,671 | 486,183 | 141,256 |

### 3.3 Step5

| batch | published_cell | published_bs | published_lac | collision | multi_centroid | dynamic | anomaly_bs |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 128,306 | 80,709 | 6,973 | 0 | 0 | 0 | 127 |
| 2 | 224,402 | 124,478 | 10,268 | 0 | 0 | 0 | 221 |
| 3 | 284,005 | 148,802 | 12,255 | 0 | 4 | 0 | 254 |
| 4 | 328,573 | 166,042 | 13,857 | 0 | 12 | 0 | 295 |
| 5 | 363,996 | 179,620 | 15,172 | 0 | 20 | 0 | 338 |
| 6 | 393,781 | 190,910 | 16,298 | 0 | 42 | 0 | 405 |
| 7 | 418,834 | 200,427 | 17,271 | 0 | 71 | 0 | 421 |

### 3.4 batch7 多质心分布

| centroid_pattern | count |
|---|---:|
| `<null>` | 416,598 |
| `dual_cluster` | 2,159 |
| `multi_cluster` | 76 |
| `migration` | 1 |

## 4. 事实层结果

### 4.1 enriched_records

| batch | rows |
|---|---:|
| 2 | 3,803,202 |
| 3 | 4,465,220 |
| 4 | 4,690,218 |
| 5 | 4,746,069 |
| 6 | 4,833,218 |
| 7 | 4,911,671 |

### 4.2 snapshot_seed_records

| batch | rows |
|---|---:|
| 1 | 4,311,643 |
| 2 | 2,076,734 |
| 3 | 1,117,446 |
| 4 | 794,217 |
| 5 | 614,276 |
| 6 | 518,523 |
| 7 | 424,288 |

### 4.3 cell_sliding_window

| batch | source_type | rows |
|---|---|---:|
| 1 | `snapshot_seed` | 4,311,643 |
| 2 | `enriched` | 3,803,202 |
| 2 | `snapshot_seed` | 2,076,734 |
| 3 | `enriched` | 4,465,220 |
| 3 | `snapshot_seed` | 1,117,436 |
| 4 | `enriched` | 4,690,218 |
| 4 | `snapshot_seed` | 794,217 |
| 5 | `enriched` | 4,746,069 |
| 5 | `snapshot_seed` | 614,276 |
| 6 | `enriched` | 4,833,218 |
| 6 | `snapshot_seed` | 518,523 |
| 7 | `enriched` | 4,911,671 |
| 7 | `snapshot_seed` | 424,288 |

## 5. 交付内容

本次交付的有效结果为当前库中的：

- `rebuild5.raw_gps`
- `rebuild5.etl_cleaned`
- `rebuild5.candidate_seed_history`
- `rebuild5.snapshot_seed_records`
- `rebuild5.enriched_records`
- `rebuild5.cell_sliding_window`
- `rebuild5.trusted_snapshot_*`
- `rebuild5.trusted_*_library`
- `rebuild5_meta.step2_run_stats`
- `rebuild5_meta.step4_run_stats`
- `rebuild5_meta.step5_run_stats`

本文件用于记录恢复与重跑过程，作为本轮交付的说明文件。
