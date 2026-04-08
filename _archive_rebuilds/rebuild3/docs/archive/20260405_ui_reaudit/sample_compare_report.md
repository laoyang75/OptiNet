# 样本偏差评估

## 结论

- 样本双跑成功：`rebuild2_sample_eval` 与 `rebuild3_sample_pipeline` 均已完成。
- Gate E 建议结论：`可进入全量，但必须先由用户确认`。
- 无 P0 / P1 阻塞缺陷；当前偏差集中在 `gps_bias` 对象级语义收紧，是 rebuild3 冻结规则的可解释差异。
- rebuild3 相比 rebuild2：`fact_pending_issue +206`，`fact_governed -206`，占样本总量 0.59%。
- baseline 主要差异在 Cell：`+8`，相对 rebuild2 Cell baseline 数量偏差 33.33%。

## 四分流对比

| route | r2_cnt | r3_cnt | diff | diff_pct_vs_r2 |
| --- | --- | --- | --- | --- |
| fact_governed | 21273 | 21067 | -206 | 0.97% |
| fact_pending_issue | 13475 | 13681 | 206 | 1.53% |
| fact_pending_observation | 50 | 50 | 0 | 0.00% |
| fact_rejected | 200 | 200 | 0 | 0.00% |

## 差异场景定位

| scenario | route | r2_cnt | r3_cnt | diff | diff_pct_vs_r2 |
| --- | --- | --- | --- | --- | --- |
| normal_spread | fact_governed | 3913 | 3799 | -114 | 2.91% |
| normal_spread | fact_pending_issue | 0 | 114 | 114 | 0.00% |
| single_large | fact_governed | 4594 | 4502 | -92 | 2.00% |
| single_large | fact_pending_issue | 0 | 92 | 92 | 0.00% |

解释：`normal_spread` 与 `single_large` 场景中的 206 条记录，在 rebuild3 中因 `gps_bias` 被收紧为对象级问题，转入 `fact_pending_issue`。

## 对象状态分布对比

| obj | lifecycle_state | health_state | r2_cnt | r3_cnt | diff |
| --- | --- | --- | --- | --- | --- |
| bs | active | collision_confirmed | 1 | 1 | 0 |
| bs | active | collision_suspect | 1 | 1 | 0 |
| bs | active | dynamic | 1 | 1 | 0 |
| bs | active | healthy | 5 | 5 | 0 |
| bs | observing | insufficient | 1 | 1 | 0 |
| cell | active | collision_confirmed | 16 | 16 | 0 |
| cell | active | collision_suspect | 20 | 20 | 0 |
| cell | active | dynamic | 7 | 7 | 0 |
| cell | active | gps_bias | 13 | 2 | -11 |
| cell | active | healthy | 27 | 38 | 11 |
| cell | observing | collision_confirmed | 1 | 1 | 0 |
| cell | observing | collision_suspect | 2 | 2 | 0 |
| cell | observing | dynamic | 1 | 1 | 0 |
| cell | observing | healthy | 3 | 3 | 0 |
| cell | waiting | collision_confirmed | 1 | 1 | 0 |
| cell | waiting | collision_suspect | 2 | 2 | 0 |
| cell | waiting | dynamic | 1 | 1 | 0 |
| cell | waiting | gps_bias | 1 | 0 | -1 |
| cell | waiting | healthy | 5 | 6 | 1 |
| lac | active | collision_suspect | 3 | 3 | 0 |
| lac | active | healthy | 5 | 5 | 0 |
| lac | observing | insufficient | 1 | 1 | 0 |

解释：Cell 数量未变，但 `gps_bias -> healthy` 与 `healthy -> gps_bias` 的互换来自空间口径更新：rebuild2 依赖旧的 Cell-to-BS 异常标记，rebuild3 依赖样本画像 P90 空间离散度。

## 资格分布对比

| obj | anchorable | baseline_eligible | r2_cnt | r3_cnt | diff |
| --- | --- | --- | --- | --- | --- |
| bs | False | False | 5 | 5 | 0 |
| bs | True | False | 1 | 1 | 0 |
| bs | True | True | 3 | 3 | 0 |
| cell | False | False | 73 | 62 | -11 |
| cell | True | False | 3 | 6 | 3 |
| cell | True | True | 24 | 32 | 8 |
| lac | False | False | 5 | 5 | 0 |
| lac | True | False | 1 | 1 | 0 |
| lac | True | True | 3 | 3 | 0 |

## baseline 对比

| obj | r2_cnt | r3_cnt | diff | diff_pct_vs_r2 |
| --- | --- | --- | --- | --- |
| bs | 3 | 3 | 0 | 0.00% |
| cell | 24 | 32 | 8 | 33.33% |
| lac | 3 | 3 | 0 | 0.00% |

### baseline Cell 交集与画像指标

| obj | common_cnt | center_diff_p90_m | center_diff_max_m | p90_diff_p90_m | gps_ratio_diff_max | signal_ratio_diff_max |
| --- | --- | --- | --- | --- | --- | --- |
| cell | 22 | 0 | 15.4561996459961 | 398.4769 | 0.1696 | 0.0384 |
| bs | 3 | 0 | 0 | 0 | 0.1407 | 0.0035 |
| lac | 3 | 0 | 0 |  | 0.1407 | 0.0035 |

说明：共同 baseline 对象上，Cell/BS/LAC 的质心差异 P90 均为 0，Cell 质心最大偏差约 15.46m；说明主空间口径稳定。

### baseline Cell 差异清单

| membership | operator_code | tech_norm | lac | bs_id | cell_id | r2_health | r3_health | r2_p90 | r3_p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r2_only | 46001 | 5G | 98310 | 140755 | 576533513 | healthy | gps_bias | 133.2356 | 25597.7888907294 |
| r2_only | 46011 | 5G | 409602 | 417849 | 1711509505 | healthy | gps_bias | 121.7226 | 5555.50137231222 |
| r3_only | 46001 | 5G | 98310 | 140755 | 576532484 | gps_bias | healthy | 0 | 461.19698364292 |
| r3_only | 46001 | 5G | 98310 | 140755 | 576532485 | gps_bias | healthy | 0 | 266.650505320158 |
| r3_only | 46001 | 5G | 98310 | 140755 | 576532486 | gps_bias | healthy | 0 | 247.333854287125 |
| r3_only | 46001 | 5G | 98310 | 140755 | 576532740 | gps_bias | healthy | 0 | 502.362858524741 |
| r3_only | 46001 | 5G | 98310 | 140755 | 576532741 | gps_bias | healthy | 0 | 312.550619593022 |
| r3_only | 46001 | 5G | 98310 | 140755 | 576532742 | gps_bias | healthy | 0 | 455.945097231132 |
| r3_only | 46011 | 5G | 409602 | 417849 | 1711509512 | gps_bias | healthy | 0 | 881.949470951016 |
| r3_only | 46011 | 5G | 409602 | 417849 | 1711509513 | gps_bias | healthy | 0 | 1202.52511709706 |
| r3_only | 46011 | 5G | 409602 | 417849 | 1711509767 | gps_bias | healthy | 0 | 288.99876352862 |
| r3_only | 46011 | 5G | 409602 | 417849 | 1711509768 | gps_bias | healthy | 0 | 183.960518385603 |

解释：`r2_only` 的 2 个 Cell 在 rebuild3 中被识别为 `gps_bias` 并从 baseline 剔除；`r3_only` 的 10 个 Cell 来自 rebuild2 旧口径误判 `gps_bias`、而在 rebuild3 画像 P90 下恢复为 `healthy`。

## Gate E 门禁判断

- 通过项：样本双跑成功；关键对象数量一致；路由偏差可解释；共同 baseline 对象的空间指标稳定。
- 非阻塞偏差：`gps_bias` 语义收紧导致 `fact_pending_issue` 增加 206 条、Cell baseline 净增 8 个。
- 建议：保持当前实现进入全量，但按照正式流程，必须等待用户确认后才能进入 Gate F 全量构建。
