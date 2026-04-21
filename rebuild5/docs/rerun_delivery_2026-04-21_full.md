# 2026-04-21 全链路重跑交付记录

## 结论

本次 `beijing_7d`（2025-12-01 ~ 2025-12-07）Step 1-5 pipelined 全链路正式重跑已执行完成，但正式验收不通过。

阻塞项：`trusted_cell_library` 在 batch 3-7 各有 1 条 `tech_norm='5G' AND cell_id < 4096`，违反“垃圾 cell = 0”的硬要求。

异常明细：

| batch_id | operator_code | lac | bs_id | cell_id | tech_norm | rows |
|---:|---|---:|---:|---:|---|---:|
| 3 | 46000 | 2097187 | 0 | -1 | 5G | 1 |
| 4 | 46000 | 2097187 | 0 | -1 | 5G | 1 |
| 5 | 46000 | 2097187 | 0 | -1 | 5G | 1 |
| 6 | 46000 | 2097187 | 0 | -1 | 5G | 1 |
| 7 | 46000 | 2097187 | 0 | -1 | 5G | 1 |

按 prompt 约束，发现该硬验收失败后未做修正性写入。

## 执行概况

- 样本预跑：通过功能验收；样本表 1,505,000 行，每天 215,000 行。
- 正式重跑日志：`rebuild5/runtime/logs/full_rerun_20260421_135357.log`
- 正式运行时间：2026-04-21 13:53:57 ~ 17:00:11
- 源表状态：脚本结束后完整源数据位于 `rebuild5.raw_gps`，行数 25,442,069；`rebuild5.raw_gps_full_backup` 不存在，`raw_gps_full_backup_prod_hold` 不存在。

## Step 1

| run_id | raw_record_count | cleaned_record_count | clean_pass_rate | ODS-019 dropped | ODS-019 drop_rate |
|---|---:|---:|---:|---:|---:|
| step1_20260421_135450 | 3,885,832 | 6,222,080 | 0.9971 | 675,721 | 0.1534 |
| step1_20260421_141037 | 3,893,994 | 6,322,561 | 0.9973 | 677,176 | 0.1533 |
| step1_20260421_142737 | 3,645,783 | 5,838,185 | 0.9973 | 646,811 | 0.1561 |
| step1_20260421_144358 | 3,556,320 | 5,648,944 | 0.9974 | 644,354 | 0.1592 |
| step1_20260421_145923 | 3,441,403 | 5,503,032 | 0.9972 | 621,676 | 0.1587 |
| step1_20260421_151331 | 3,394,782 | 5,459,749 | 0.9972 | 600,193 | 0.1560 |
| step1_20260421_152850 | 3,623,955 | 5,807,664 | 0.9972 | 628,603 | 0.1542 |

ODS-019 drop_rate 均在 10%-25% 期望区间内。

## 行数

| batch_id | trusted_cell | trusted_bs | trusted_lac |
|---:|---:|---:|---:|
| 1 | 86,839 | 57,500 | 4,793 |
| 2 | 169,086 | 97,800 | 7,407 |
| 3 | 224,129 | 121,701 | 9,106 |
| 4 | 266,695 | 138,929 | 10,482 |
| 5 | 301,113 | 152,179 | 11,651 |
| 6 | 330,051 | 163,262 | 12,682 |
| 7 | 356,762 | 173,371 | 13,630 |

三层均有 7 批。

## Batch 7 分布

drift_pattern：

| drift_pattern | cnt | pct |
|---|---:|---:|
| stable | 349,255 | 97.90 |
| insufficient | 6,257 | 1.75 |
| large_coverage | 688 | 0.19 |
| dual_cluster | 421 | 0.12 |
| uncertain | 135 | 0.04 |
| oversize_single | 4 | 0.00 |
| migration | 2 | 0.00 |

BS classification：

| classification | cnt |
|---|---:|
| normal | 169,151 |
| insufficient | 4,084 |
| dual_cluster_bs | 93 |
| uncertain_bs | 39 |
| anomaly | 4 |

## 性能观察

样本预跑功能通过；正式 Step 5 子步骤耗时来自 `pipelined_step25_batch*_202512*.log`：

| batch_id | total_substeps_s | 主要耗时 |
|---:|---:|---|
| 1 | 185 | daily_centroids 64s, collision 41s, metrics_radius 39s |
| 2 | 387 | metrics_radius 155s, daily_centroids 132s |
| 3 | 695 | metrics_radius 368s, daily_centroids 176s |
| 4 | 1,051 | metrics_radius 587s, daily_centroids 215s |
| 5 | 815 | metrics_radius 387s, daily_centroids 203s |
| 6 | 986 | metrics_radius 483s, daily_centroids 239s |
| 7 | 1,191 | metrics_radius 597s, daily_centroids 276s |

主要慢点是 Step 5 的 `metrics_radius` 与 `daily_centroids`，运行中未出现单 SQL 超过 30 分钟的停下条件。

## 异常告警

1. 正式硬验收失败：batch 3-7 存在 5G `cell_id=-1` 的垃圾 cell。
2. 脚本结束后完整源表位于 `rebuild5.raw_gps`，不是 prompt 前置步骤使用的 `rebuild5.raw_gps_full_backup` 名称；内容行数仍为 25,442,069。
3. `step1_run_stats.started_at/finished_at` 存在时区显示不一致，未用该字段直接计算耗时。

