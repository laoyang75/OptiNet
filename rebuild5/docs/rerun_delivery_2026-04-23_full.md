# 2026-04-23 Step 1-5 全链路重跑交付报告

## 1. 执行概况

- 数据库：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
- 数据集：`beijing_7d`
- 日期范围：`2025-12-01` ~ `2025-12-07`
- 正式有效运行窗口：约 `2026-04-23 01:38:43` ~ `2026-04-23 05:59`
- 收尾验收完成：`2026-04-23 06:03 CST`
- 最终源头状态：`rebuild5.raw_gps_full_backup = 25,442,069` 行；`raw_gps` / `raw_gps_full_backup_prod_hold` 均不存在

## 2. 自主修复与优化

1. `rebuild5/backend/app/profile/pipeline.py`
   - 修复：`_profile_gps_day_dedup` 补齐 DEDUP-V2.1 的 `ss1 -> record_id` 去重分支。
   - 原因：冒烟发现 Step 2 仍按所有 origin 共用 5min bucket，和 prompt 的 DEDUP-V2.1 语义不一致。
   - 影响：仅改变 `ss1` 下游去重键，消除 forward-fill 冗余；`cell_infos` 仍保持 5min bucket。

2. `rebuild5/backend/app/maintenance/window.py`
   - 优化：为 `cell_core_gps_stats` 增加不带 `batch_id` 前缀的 lookup index。
   - 优化：将 `build_cell_radius_stats()` 中的大 CTE 拆为 `_cell_radius_with_dist`、`_cell_radius_weighted_stats`、`_cell_radius_counts` 三个 UNLOGGED 中间表并 `ANALYZE`。
   - 原因：样本跑中 `cell_radius_stats` 查询计划把 `with_dist` 估成 1 行，最终 join 走 Nested Loop；拆分后让 planner 拿到真实统计。
   - 影响：不改变加权 p50/p90 业务口径，仅改变执行形态。

3. `rebuild5/backend/app/maintenance/window.py`
   - 修复：`build_cell_ta_stats()` 先计算 raw percentile，再对 `ta_p50 / ta_p90 / ta_dist_p90_m` 做 int 范围 clamp。
   - 原因：正式数据中存在 `timing_advance=2147483647`、`268435455` 哨兵值，`ta_p90 * 78.125` 或 percentile cast 触发 `integer out of range`。
   - 影响：避免类型溢出；不新增业务过滤规则，异常 TA 仍进入统计，只在写入 INTEGER 字段时防溢出。

## 3. 预跑与性能基线

- 样本表：`rebuild5_stage.raw_gps_sample_7d`
- 样本规模：`1,505,000` 行，7 天每天 `215,000` 行
- 样本验收：7 批齐、垃圾 cell 全 0、ODS-019/020/022 均有非零 drop、`cell_origin` 透传率 `100.00%`
- 样本 Step 1：每批约 `62-67s`
- 样本 Step 2-5：维护阶段最终批次约 `75s`；优化前曾观测 `cell_radius_stats` 单 SQL > `150s`

正式 Step 5 主要瓶颈为 `metrics_radius`，其次为 `daily_centroids / core_gps / ta_stats`。已完成的 Step 5 子阶段耗时如下：

| batch | daily_centroids | metrics_base | core_gps | metrics_radius | ta_stats |
|---:|---:|---:|---:|---:|---:|
| 1 | 60s | 7s | 13s | 87s | 21s |
| 2 | 118s | 13s | 29s | 312s | 34s |
| 3 | 137s | 20s | 50s | 704s | 51s |
| 4 | 164s | 26s | 65s | 1038s | 63s |
| 5 | 173s | 32s | 81s | 1399s | 74s |
| 6 | 218s | 40s | 100s | 914s | 93s |
| 7 | 242s | 47s | 119s | 1130s | 111s |

## 4. Step 1 耗时与行数

| run_id | raw | cleaned | start | finish | secs |
|---|---:|---:|---|---|---:|
| step1_20260423_013843 | 3,885,832 | 5,289,898 | 01:38:43 | 01:53:43 | 900 |
| step1_20260423_015536 | 3,893,994 | 5,354,863 | 01:55:36 | 02:11:41 | 965 |
| step1_20260423_021330 | 3,645,783 | 4,960,939 | 02:13:30 | 02:29:02 | 933 |
| step1_20260423_023041 | 3,556,320 | 4,805,467 | 02:30:41 | 02:44:28 | 828 |
| step1_20260423_024606 | 3,441,403 | 4,690,770 | 02:46:06 | 03:00:59 | 893 |
| step1_20260423_030232 | 3,394,782 | 4,665,448 | 03:02:32 | 03:16:25 | 834 |
| step1_20260423_031807 | 3,623,955 | 4,972,243 | 03:18:07 | 03:33:27 | 920 |

## 5. 最终产出行数

| batch | trusted_cell | trusted_bs | trusted_lac |
|---:|---:|---:|---:|
| 1 | 79,682 | 53,010 | 4,315 |
| 2 | 158,499 | 92,257 | 6,792 |
| 3 | 211,850 | 115,758 | 8,404 |
| 4 | 253,297 | 132,706 | 9,708 |
| 5 | 286,931 | 145,668 | 10,812 |
| 6 | 315,165 | 156,425 | 11,757 |
| 7 | 341,460 | 166,266 | 12,645 |

`step1_run_stats = 7`，`step5_run_stats = 7`。

## 6. 正式验收结果

- 三层 7 批齐：通过
- 垃圾 cell：所有批次 `g4g/g5g/glac = 0`
- batch 7 drift 分布：
  - `stable`: 337,480 (`98.83%`)
  - `insufficient`: 2,700 (`0.79%`)
  - `large_coverage`: 745 (`0.22%`)
  - `dual_cluster`: 442 (`0.13%`)
  - 其他合计 < `0.03%`
- batch 7 BS classification：
  - `normal`: 164,749
  - `insufficient`: 1,407
  - `dual_cluster_bs`: 87
  - `uncertain_bs`: 23

## 7. ODS drop 量

| run_id | ODS-019 rate | ODS-020 rate | ODS-022 rate |
|---|---:|---:|---:|
| step1_20260423_013843 | 17.18% | 5.68% | 3.93% |
| step1_20260423_015536 | 17.16% | 5.85% | 3.73% |
| step1_20260423_021330 | 17.55% | 5.81% | 4.04% |
| step1_20260423_023041 | 17.83% | 5.64% | 4.21% |
| step1_20260423_024606 | 17.75% | 5.50% | 3.86% |
| step1_20260423_030232 | 17.48% | 5.54% | 3.37% |
| step1_20260423_031807 | 17.24% | 5.51% | 3.05% |

均在 prompt 预期范围内。

## 8. DEDUP / TA 验收

- `cell_sliding_window.cell_origin` 透传率：`100.00%`
- `timing_advance` 非空率：`8.64%`，低于 prompt 的 15-25% 观察区间；主要原因是 `ss1` 无 TA 且 ODS-023 清空了大量 TDD 占位 TA。
- `freq_channel` 非空率：`72.60%`，低于 prompt 的 80-95% 观察区间；非硬门槛，已记录。
- 参考异常 cell（batch 7）：
  - `20752955`: `stable`, p90 `3m`, `ta_p90=1`, `ta_verification=ok`
  - `17539075`: `stable`, p90 `9m`, `ta_p90=0`, `ta_verification=not_checked`
  - `4855663`: `stable`, p90 `28m`, `ta_p90=1282`, `ta_verification=insufficient`
- ODS-023 TDD placeholder：
  - `null`: 1,314,230
  - `tdd_valid (0-15)`: 87,957
  - `timing_advance=-1`: 1 行
  - `timing_advance >= 16` placeholder 桶为 0
- `ta_verification` 分布：
  - `insufficient`: 179,475 (`52.6%`)
  - `ok`: 99,336 (`29.1%`)
  - `not_checked`: 47,566 (`13.9%`)
  - `xlarge`: 13,460 (`3.9%`)
  - `large`: 1,557 (`0.5%`)
  - `not_applicable`: 66

说明：`cell_radius_stats` 是 Step 5 临时中间表，续跑脚本 `_cleanup_after_step5()` 后已删除，因此 §5.8 的 `cell_radius_stats` raw-vs-weighted SQL 在收尾后不可直接执行。样本跑和代码路径已验证加权 p90 逻辑存在并执行；正式 Step 5 日志中 `metrics_radius` 子阶段完成。

## 9. 异常与处理

1. 本环境中 `nohup ... &` 启动后子进程没有保持；改用前台会话运行，pipeline 语义不变。
2. 样本预跑曾因 `build_cell_ta_stats()` integer overflow 失败；修复 TA int clamp 后重跑通过。
3. 正式 batch 6 首次运行也触发同类 TA overflow；补齐 `ta_p50/ta_p90/ta_dist_p90_m` 三字段 clamp 后，从 batch 6 `resume-phase=step5` 续跑，并完成 batch 6/7。
4. 性能瓶颈：`metrics_radius` 随累计窗口增长明显，batch 5 达 1399s，batch 7 达 1130s；未超过 30 分钟停机阈值，但后续仍有优化空间。

## 10. 最终结论

Step 1-5 全链路正式重跑完成，`trusted_cell_library`、`trusted_bs_library`、`trusted_lac_library` 均产出 batch `1..7`，核心硬验收通过。源头 `raw_gps_full_backup` 已恢复并校验完整。
