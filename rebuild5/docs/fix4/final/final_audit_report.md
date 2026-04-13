# Fix4 最终整合审计报告

时间：2026-04-13  
执行人：Codex 独立审计  
范围：只审计共享样例 `2025-12-01 ~ 2025-12-07`，当前先以双方共同区间 `batch1-3` 为主，不进入正式全量。

## 1. 审计结论

最终裁决：

1. 最终方案应以 `codex` 的主链整合版为唯一执行基线。
2. `claude` 产物可保留为“位置过滤研究参考”，但不能直接作为最终 runbook。
3. 当前主链里已经落下并应保留的关键改动包括：
   - Step2 核心点主中心过滤
   - Step5 滑动窗口核心点过滤
   - `_detect_geographic_collision`
   - Step4 donor gate 修复
   - Step5 PostGIS 分阶段物化
   - 多质心候选扩大到 `raw_p90 / max_spread / core_outlier_ratio / gps_anomaly`
4. 当前仍未开放“正式全量运行”闸门。
   - 原因不是工程链路没打通。
   - 原因是 `dual_cluster` 仍明显偏多，必须先完成 `batch4-7` 样例验证。

## 2. 审计证据来源

本次不是只读文档互评，而是做了数据库与代码双重取证。

### 2.1 共享样例核对

共享样例表实际行数：

| 表 | 行数 |
|---|---:|
| `rebuild5_fix4.raw_gps_shared_sample` | 1,232,037 |
| `rebuild5_fix4.etl_cleaned_shared_sample` | 1,937,395 |
| `rebuild5_fix4.focus_cells_shared` | 40 |

`codex` 独立库 `ip_loc2_fix4_codex` 中的本地工作表：

| 表 | 行数 |
|---|---:|
| `rebuild5_fix4_work.raw_gps_shared_sample_local` | 1,232,037 |
| `rebuild5_fix4_work.etl_cleaned_shared_sample_local` | 1,937,395 |
| `rebuild5_fix4_work.focus_cells_shared_local` | 40 |

结论：双方至少在共享样例基底上没有换样。

### 2.2 `codex` 真实可审计产物

已直接连库核对 `ip_loc2_fix4_codex`：

- `rebuild5_meta.step2_run_stats`
- `rebuild5_meta.step3_run_stats`
- `rebuild5_meta.step4_run_stats`
- `rebuild5_meta.step5_run_stats`
- `rebuild5.trusted_snapshot_cell`
- `rebuild5.trusted_cell_library`
- `rebuild5.trusted_bs_library`

这意味着 `codex` 的 `batch1-3` 不是停留在文档声称，而是有真实样例库证据。

### 2.3 `claude` 真实可审计产物

已直接核对默认库 `ip_loc2` 中的 `rebuild5_fix4` schema：

- 实际存在：`c_window`、`c_cell_lib`
- 实际不存在：`claude_cell_library`、`claude_cell_centroid_detail`、`claude_bs_library`、`claude_batch_stats`

并且：

- `rebuild5_fix4.c_cell_lib` 的 `batch1-3` 指标可直接复算，与 `claude/metrics_summary.json` 一致
- 但 Step2 Path A/B/C、Step4 donor、Step5 发布、DBSCAN 明细、BS/LAC 样例发布，都没有可审计落表

结论：`claude` 当前留下的是“侧路研究结果”，不是同口径端到端跑通结果。

## 3. batch1-3 公平对比

### 3.1 `codex`：完整主链样例结果

`codex` 已在共享样例上真实跑通 `Step2 -> Step3 -> Step4 -> Step5`：

| batch | pathA | pathB | pathB_cell | pathC | donor_matched | gps_filled | published_cell | multi_centroid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 292,872 | 13,490 | 334 | 0 | 0 | 5,746 | 0 |
| 2 | 235,711 | 57,905 | 7,672 | 184 | 235,711 | 14,362 | 8,421 | 0 |
| 3 | 247,441 | 23,953 | 4,748 | 210 | 247,441 | 15,161 | 9,794 | 113 |

### 3.2 `claude`：只完成侧路生命周期与 core filter 统计

`claude` 当前能核对到的只有 `c_cell_lib`：

| batch | total_cells | observing | qualified | excellent |
|---|---:|---:|---:|---:|
| 1 | 13,306 | 9,306 | 3,218 | 782 |
| 2 | 15,234 | 8,518 | 4,277 | 2,439 |
| 3 | 16,135 | 7,923 | 4,383 | 3,829 |

但以下关键链路指标缺失：

- Step2 `Path A / Path B / Path C`
- Step4 `donor_matched / gps_filled / gps_anomaly`
- Step5 `published_cell / published_bs / published_lac`
- 已执行的 `cell_centroid_detail / bs_centroid_detail`

这不是“指标没整理出来”，而是当前执行路径本身绕过了这些步骤。

## 4. 根因追踪

### 4.1 为什么两边 Step3 分布明显不同

`codex` 的 `batch1-3` Cell 总量与 `claude` 接近，但生命周期分布差异很大：

| batch | codex total | claude total | codex observing | claude observing | codex qualified | claude qualified | codex excellent | claude excellent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 13,490 | 13,306 | 7,744 | 9,306 | 3,807 | 3,218 | 1,939 | 782 |
| 2 | 15,159 | 15,234 | 6,738 | 8,518 | 6,337 | 4,277 | 2,084 | 2,439 |
| 3 | 15,929 | 16,135 | 6,135 | 7,923 | 7,674 | 4,383 | 2,120 | 3,829 |

根因不是“同一主链只调了几个阈值”，而是执行边界不同：

- `codex` 复用了主链 Step2/3 的真实语义：
  - Step2 先做 Path A/B/C 分流
  - Step3 再做候选池累计与生命周期评估
- `claude` 直接从 `etl_cleaned_shared_sample` 装入 `c_window`
  - 直接在侧路表上重算 `lifecycle_state`
  - 没走主链 Step2 Path split
  - 没走 Step3 候选池合并

因此这组分布差异不能解释为“谁参数更优”，而应解释为“执行语义已经不同”。

### 4.2 为什么 `claude` 的 anchor 口径不能直接采纳

`codex` 的 Step3 锚点数：

| batch | anchor_eligible |
|---|---:|
| 1 | 0 |
| 2 | 1,976 |
| 3 | 2,886 |

`claude` 文档里的锚点验证，实际改成了：

- `gps_valid_count >= 10`
- `distinct_dev_id >= 2`
- `p90_radius_m < 1500`
- `active_days >= 2`

问题在于：

1. 正式设计要求的是 `observed_span_hours >= 24`，不是 `active_days >= 2`
2. 当前实际 `c_cell_lib` 表并没有主链 Step3 所需的完整资格字段
3. 这会把大量“不满足正式锚点语义”的对象提前算进 donor 可用池

所以 `claude` 的 anchor 口径不能作为最终主流程依据。

### 4.3 为什么 `codex` 的 Step4 donor 闭环更可信

`codex` 已在真实样例链路上证明：

- `batch2 total_path_a = 235,711`
- `batch2 donor_matched_count = 235,711`
- `batch3 total_path_a = 247,441`
- `batch3 donor_matched_count = 247,441`

并且代码上明确把 donor 使用条件从“二次锚点门槛”改成了“已命中 published donor 即可用”。

`claude` 方案没有真实 Step4 运行产物，因此它无法证明：

- donor 是否闭环
- Path A 是否真实起量
- gps anomaly 是否仍和 donor 行为兼容

### 4.4 为什么 `claude` 的 DBSCAN 结论不能直接入选最终 runbook

`claude/report.md` 说 DBSCAN 修复已经完成，但同时也明确写了：

- 本轮没有在共享样例上实际跑 DBSCAN 端到端

数据库侧证据也支持这一点：

- `rebuild5_fix4` schema 里没有 `claude_cell_centroid_detail`
- 没有 `claude_bs_library`
- 没有 `claude_batch_stats`

再加一层问题：

- 仓库里的 `fix4_claude_pipeline.py` 使用 `claude_*` 表名
- 实际落地和文档/runbook 使用的是 `c_*` 表名

这说明 `claude` 当前连“最终使用哪条脚本”都没有完全收口。

## 5. 专项裁决

### 5.1 位置计算

裁决：

- 保留“两阶段核心点过滤”
- 但必须采用已经接进主链的版本，而不是侧路脚本版

原因：

1. `claude` 对面积收敛的研究结论是有价值的
2. 但真正满足 Step2 / Step5 分工的，是当前主链代码：
   - Step2 用核心点过滤稳住候选域主中心
   - Step5 在滑动窗口上再做一次维护态重算
3. 这正好符合文档要求的“Step3 与 Step5 分工，不把两层职责混掉”

### 5.2 覆盖面积

Batch3 focus cell 平均 `p90` 对比：

| bucket | codex | claude |
|---|---:|---:|
| high_obs | 129.5m | 150.3m |
| high_p90 | 128.6m | 129.0m |
| moving | 818.4m | 779.3m |
| multi_cluster | 799.2m | 678.1m |

裁决：

- 两边都证明核心点过滤能显著压缩极端面积
- 但 `codex` 在 `moving / multi_cluster` 桶上保留了更高的空间展布
- 这比更激进地压到更小半径更稳妥，过度裁剪风险更低

因此面积问题上，最终应选：

- `codex` 主链整合版作为最终实现
- `claude` 的“动态 Cell 可能要放宽过滤”作为后续专项观察，不进入本轮主流程

### 5.3 多质心 / moving / migration / dual_cluster / multi_cluster

裁决：

- 最终以 `codex` 当前主链分类器为基础
- 但 full run 之前必须先做 `batch4-7` 样例收敛

原因：

1. `codex` 是唯一有真实 Step5 多质心落表与发布结果的一边
2. 当前 batch3 结果：
   - `<null> = 9,681`
   - `dual_cluster = 106`
   - `multi_cluster = 7`
   - `moving = 0`
   - `migration = 0`
3. 这说明工程链路已通，但 `dual_cluster` 偏多风险真实存在

### 5.4 速度优化

裁决：

- 速度基线只承认主链真实 Step5 数据
- 因此保留 `codex` 的分阶段物化优化

原因：

1. `codex` 已在真实 `batch3` 把 `publish_cell_centroid_detail()` 从分钟级压回秒级
2. `claude` 的速度数据只覆盖侧路 core filter，不覆盖完整 Step5、DBSCAN、BS/LAC 发布

## 6. 最终推荐方案

最终方案不是“折中拼接”，而是：

1. 以当前主链整合代码为唯一基线
2. 保留已经在主链落地的核心点过滤、地理碰撞、候选扩大、PostGIS 分阶段物化
3. 保留 Step4 donor gate 修复，不回退
4. 不采用 `claude` 的侧路 runbook 作为最终执行流程
5. 先按 `batch1 -> batch2 -> batch3 前置测试 -> batch4-7 样例验证` 继续
6. 只有 `batch4-7` 样例验证通过，才允许进入真正的主流程代码冻结、测试和后续全量计划

当前 full-run readiness：

- `false`

原因：

- 工程闭环已通过
- 多质心边界仍需 `batch4-7` 样例确认

