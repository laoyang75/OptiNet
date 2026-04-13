# Fix4 batch1-3 差异审计

## 1. 审计口径

共同区间只认 `batch1-3`。

审计证据：

- `codex`：`ip_loc2_fix4_codex`
- `claude`：默认库 `ip_loc2` 的 `rebuild5_fix4` schema

## 2. Step1 / ETL 基底

两边都没有替换共享样例表。

| 表 | 共享行数 | codex 本地副本 | claude 直接使用 |
|---|---:|---:|---:|
| `raw_gps_shared_sample` | 1,232,037 | 1,232,037 | 未使用 |
| `etl_cleaned_shared_sample` | 1,937,395 | 1,937,395 | 1,937,395 |
| `focus_cells_shared` | 40 | 40 | 40 |

结论：

- 样例基底一致
- `claude` 只用了 ETL 层，不做原始层审计

## 3. Step2 审计

### 3.1 Codex

| batch | Path A | Path B | Path B Cell | Path C |
|---|---:|---:|---:|---:|
| 1 | 0 | 292,872 | 13,490 | 334 |
| 2 | 235,711 | 57,905 | 7,672 | 184 |
| 3 | 247,441 | 23,953 | 4,748 | 210 |

### 3.2 Claude

无对应产物。

根因：

- `claude` 侧路脚本直接把 `etl_cleaned_shared_sample` 装入 `c_window`
- 没有主链 Step2 的 Path A / Path B / Path C

结论：

- Step2 无法做同口径数值对比
- 这本身就是一条设计偏差，不是“文档没写”

## 4. Step3 审计

### 4.1 生命周期分布

| batch | codex total | claude total | codex observing | claude observing | codex qualified | claude qualified | codex excellent | claude excellent |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 13,490 | 13,306 | 7,744 | 9,306 | 3,807 | 3,218 | 1,939 | 782 |
| 2 | 15,159 | 15,234 | 6,738 | 8,518 | 6,337 | 4,277 | 2,084 | 2,439 |
| 3 | 15,929 | 16,135 | 6,135 | 7,923 | 7,674 | 4,383 | 2,120 | 3,829 |

### 4.2 锚点资格

| batch | codex anchor_eligible | claude 可复算 proxy |
|---|---:|---:|
| 1 | 0 | 0 |
| 2 | 1,976 | 8,439 |
| 3 | 2,886 | 9,835 |

`claude` 的 proxy 不是正式 Step3 口径，原因：

1. 用的是 `active_days >= 2`
2. 不是文档要求的 `observed_span_hours >= 24`
3. 当前 `c_cell_lib` 也没有主链 Step3 所需的完整资格字段

### 4.3 差异根因

这组差异不能归因为“小调参”，根因是执行语义不同：

- `codex`：主链 `Step2 -> Step3`
- `claude`：ETL 侧路窗口直接重算生命周期

因此：

- `codex` 的 Step3 结果是“主链准入结果”
- `claude` 的 Step3 结果是“研究侧窗口统计结果”

## 5. Step4 审计

### 5.1 Codex

| batch | total_path_a | donor_matched | gps_filled | gps_anomaly | donor_excellent | donor_qualified |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2 | 235,711 | 235,711 | 14,362 | 6,450 | 137,528 | 98,183 |
| 3 | 247,441 | 247,441 | 15,161 | 7,108 | 130,736 | 116,705 |

### 5.2 Claude

无对应产物。

根因：

- 没走主链 Path A
- 没走 Step4 donor 补数
- 没有 `enriched_records` 与 `gps_anomaly_log` 闭环

结论：

- `claude` 不能回答 Step4 是否打通
- 这也是它不能成为最终 runbook 的核心原因之一

## 6. Step5 审计

### 6.1 Codex

| batch | published_cell | published_bs | published_lac | collision_cell | multi_centroid | dynamic | anomaly_bs |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5,746 | 3,124 | 18 | 0 | 0 | 0 | 13 |
| 2 | 8,421 | 4,115 | 21 | 0 | 0 | 0 | 20 |
| 3 | 9,794 | 4,563 | 21 | 0 | 113 | 0 | 12 |

Batch3 `centroid_pattern`：

| pattern | count |
|---|---:|
| `<null>` | 9,681 |
| `dual_cluster` | 106 |
| `multi_cluster` | 7 |

### 6.2 Claude

当前真实库里：

- 没有 `claude_cell_centroid_detail`
- 没有 `claude_bs_library`
- 没有 `claude_batch_stats`

实际可审计表只有：

- `c_window`
- `c_cell_lib`

结论：

- `claude` 没有同口径 Step5 发布证据
- 也没有可复核的 DBSCAN 明细证据

## 7. Focus Cell 面积对比（batch3）

| bucket | codex avg p90 | claude avg p90 | 备注 |
|---|---:|---:|---|
| high_obs | 129.5m | 150.3m | 两边都明显收敛 |
| high_p90 | 128.6m | 129.0m | 基本一致 |
| moving | 818.4m | 779.3m | `claude` 更激进 |
| multi_cluster | 799.2m | 678.1m | `claude` 更激进 |

裁决：

- 面积收敛方向两边一致
- 但动态/多簇桶上，`codex` 更保守，更符合“不因硬裁剪而洗掉真实展布”的要求

## 8. 差异总结

### 8.1 可接受差异

- 核心点过滤参数与实现细节差异
- focus cell 半径略有不同

### 8.2 不可接受差异

1. `claude` 绕过主链 Step2 Path split
2. `claude` 绕过 Step4 donor
3. `claude` 没有可审计 Step5 发布结果
4. `claude` anchor 口径替换成了非正式 proxy
5. `claude` 仓库脚本与真实落表状态不一致

## 9. 本文件结论

`batch1-3` 的公平审计结果不是“双方都差不多”，而是：

- `codex` 是主链整合验证
- `claude` 是侧路研究验证

因此最终 runbook 只能建立在 `codex` 样例链路之上。

