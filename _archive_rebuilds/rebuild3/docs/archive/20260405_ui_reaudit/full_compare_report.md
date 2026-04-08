# 全量偏差评估

## 结论

- 全量双跑已完成：`rebuild3` 全量构建、`rebuild2` 全量对比态准备与全量偏差评估均已落地。
- 对象总量已对齐：Cell / BS / LAC 在 rebuild2 对比态与 rebuild3 中均一致。
- 四分流主偏差集中在 `gps_bias`：`fact_pending_issue +2036318`，对应 rebuild3 将 `gps_bias` 明确路由到问题池。
- 在把 rebuild2 未注册对象覆盖折算到观察池后，`fact_pending_observation` 残余偏差仅 `-116201`，占全量输入 0.27%。
- baseline 偏差为：Cell `+2274`、BS `+109`、LAC `+0`；BS / LAC 偏差在修正级联过滤后已显著收敛。
- 共同 baseline 对象上的中心点与画像指标完全一致，说明全量空间读模型稳定；当前差异主要来自状态/资格规则，而不是坐标计算漂移。

## 四分流对比

| route | r2_cnt | r3_cnt | diff | diff_pct_vs_r2 |
| --- | --- | --- | --- | --- |
| fact_governed | 26775722 | 24855605 | -1920117 | 7.17% |
| fact_pending_issue | 1789244 | 3825562 | 2036318 | 113.81% |
| fact_pending_observation | 10706939 | 10590738 | -116201 | 1.09% |
| fact_rejected | 4499401 | 4499401 | 0 | 0.00% |

说明：rebuild3 比 rebuild2 少 `1920117` 条 governed、 多 `2036318` 条 issue；核心原因是 `gps_bias` 由 rebuild3 明确升级为对象级问题事实。

## rebuild3 观察池构成

| route_reason | missing_layer | row_count | row_ratio_vs_total |
| --- | --- | --- | --- |
| missing_object_registration | existence | 9189629 | 20.99% |
| insufficient_object_evidence | anchorable | 1107813 | 2.53% |
| insufficient_object_evidence | existence | 293296 | 0.67% |

说明：`missing_object_registration` 共 `9189629` 条，占全量输入 20.99%；这些记录主键有效，但在 rebuild2 既有对象层中没有对应 Cell 注册，因此 rebuild3 统一纳入观察池。

## rebuild3 问题池构成

| health_state | row_count | row_ratio_vs_total |
| --- | --- | --- |
| gps_bias | 2036318 | 4.65% |
| dynamic | 983153 | 2.25% |
| collision_confirmed | 726109 | 1.66% |
| collision_suspect | 79982 | 0.18% |

说明：`gps_bias` 问题事实共 `2036318` 条，与 `fact_pending_issue` 的主差值量级一致，说明全量偏差延续了样本阶段的冻结语义。

## 对象总量对比

| obj | r2_cnt | r3_cnt | diff |
| --- | --- | --- | --- |
| bs | 193036 | 193036 | 0 |
| cell | 573561 | 573561 | 0 |
| lac | 50153 | 50153 | 0 |

## 对象状态分布对比

| obj | lifecycle_state | health_state | r2_cnt | r3_cnt | diff |
| --- | --- | --- | --- | --- | --- |
| bs | active | collision_confirmed | 1855 | 1855 | 0 |
| bs | active | collision_suspect | 181 | 181 | 0 |
| bs | active | dynamic | 4702 | 4702 | 0 |
| bs | active | healthy | 119891 | 119871 | -20 |
| bs | active | insufficient | 1 | 20 | 19 |
| bs | observing | collision_confirmed | 158 | 158 | 0 |
| bs | observing | collision_suspect | 5 | 5 | 0 |
| bs | observing | dynamic | 422 | 422 | 0 |
| bs | observing | insufficient | 65821 | 65822 | 1 |
| cell | active | collision_confirmed | 9086 | 9086 | 0 |
| cell | active | collision_suspect | 961 | 961 | 0 |
| cell | active | dynamic | 11503 | 11503 | 0 |
| cell | active | gps_bias | 6136 | 27473 | 21337 |
| cell | active | healthy | 286639 | 265299 | -21340 |
| cell | observing | collision_confirmed | 3675 | 3675 | 0 |
| cell | observing | collision_suspect | 418 | 418 | 0 |
| cell | observing | dynamic | 3274 | 3274 | 0 |
| cell | observing | gps_bias | 4995 | 10499 | 5504 |
| cell | observing | healthy | 99619 | 94118 | -5501 |
| cell | waiting | collision_confirmed | 3982 | 3982 | 0 |
| cell | waiting | collision_suspect | 414 | 414 | 0 |
| cell | waiting | dynamic | 3308 | 3308 | 0 |
| cell | waiting | gps_bias | 9596 | 3871 | -5725 |
| cell | waiting | healthy | 129955 | 135680 | 5725 |
| lac | active | collision_suspect | 717 | 717 | 0 |
| lac | active | healthy | 212 | 212 | 0 |
| lac | observing | collision_suspect | 2 | 2 | 0 |
| lac | observing | insufficient | 49222 | 49222 | 0 |

解释：Cell 侧的 `healthy <-> gps_bias` 互换仍是主偏差；BS / LAC 侧在修正级联过滤后已基本对齐。

## 资格分布对比

| obj | anchorable | baseline_eligible | r2_cnt | r3_cnt | diff |
| --- | --- | --- | --- | --- | --- |
| bs | False | False | 77884 | 77713 | -171 |
| bs | True | False | 22151 | 22213 | 62 |
| bs | True | True | 93001 | 93110 | 109 |
| cell | False | False | 311898 | 308262 | -3636 |
| cell | True | False | 68985 | 70347 | 1362 |
| cell | True | True | 192678 | 194952 | 2274 |
| lac | False | False | 49225 | 49225 | 0 |
| lac | True | False | 62 | 62 | 0 |
| lac | True | True | 866 | 866 | 0 |

## baseline 对比

| obj | r2_cnt | r3_cnt | diff | diff_pct_vs_r2 |
| --- | --- | --- | --- | --- |
| bs | 93001 | 93110 | 109 | 0.12% |
| cell | 192678 | 194952 | 2274 | 1.18% |
| lac | 866 | 866 | 0 | 0.00% |

## baseline 差异清单（汇总）

| obj | membership | row_count |
| --- | --- | --- |
| bs | r3_only | 109 |
| cell | r3_only | 2274 |

### baseline Cell 差异样例

| membership | operator_code | tech_norm | lac | bs_id | cell_id | r2_health | r3_health | r2_p90 | r3_p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r3_only | 46000 | 4G | 4116 | 358983 | 91899852 | gps_bias | healthy | 578.1298 | 578.129822645673 |
| r3_only | 46000 | 4G | 4136 | 17004 | 4353026 | gps_bias | healthy | 1449.8346 | 1449.83455720807 |
| r3_only | 46000 | 4G | 4144 | 358078 | 91668222 | gps_bias | healthy | 149.9026 | 149.902569377451 |
| r3_only | 46000 | 4G | 4144 | 492535 | 126089141 | gps_bias | healthy | 1118.7123 | 1118.7122849317 |
| r3_only | 46000 | 4G | 4144 | 492535 | 126089143 | gps_bias | healthy | 904.3688 | 904.368807308381 |
| r3_only | 46000 | 4G | 4148 | 492043 | 125963198 | gps_bias | healthy | 257.8876 | 257.88759034994 |
| r3_only | 46000 | 4G | 4163 | 70262 | 17987088 | gps_bias | healthy | 4.4645 | 4.46449686936615 |
| r3_only | 46000 | 4G | 4167 | 498337 | 127574405 | gps_bias | healthy | 1405.2922 | 1405.29215953198 |
| r3_only | 46000 | 4G | 4194 | 496852 | 127194299 | gps_bias | healthy | 153.6553 | 153.655335283234 |
| r3_only | 46000 | 4G | 4194 | 496852 | 127194300 | gps_bias | healthy | 1289.0031 | 1289.00306372147 |
| r3_only | 46000 | 4G | 4199 | 359396 | 92005574 | gps_bias | healthy | 52.8473 | 52.8473277746786 |
| r3_only | 46000 | 4G | 4199 | 951848 | 243673338 | gps_bias | healthy | 2.6895 | 2.68954687635876 |
| r3_only | 46000 | 4G | 4203 | 888886 | 227555018 | gps_bias | healthy | 115.5296 | 115.529571752809 |
| r3_only | 46000 | 4G | 4205 | 351350 | 89945794 | gps_bias | healthy | 45.0529 | 45.0529012060267 |
| r3_only | 46000 | 4G | 4205 | 351350 | 89945796 | gps_bias | healthy | 270.5981 | 270.59810222605 |
| r3_only | 46000 | 4G | 4233 | 500371 | 128095127 | gps_bias | healthy | 214.4249 | 214.424887130583 |
| r3_only | 46000 | 4G | 4233 | 500371 | 128095128 | gps_bias | healthy | 89.684 | 89.6840407268112 |
| r3_only | 46000 | 4G | 4233 | 500371 | 128095129 | gps_bias | healthy | 174.6289 | 174.62894877203 |
| r3_only | 46000 | 4G | 4241 | 74288 | 19017729 | gps_bias | healthy | 1441.1077 | 1441.10774077621 |
| r3_only | 46000 | 4G | 4241 | 74288 | 19017731 | gps_bias | healthy | 4.8291 | 4.82912873741852 |

解释：Cell baseline 差异几乎全部表现为 `r3_only`，即 rebuild2 旧口径下被标记为 `gps_bias`、而在 rebuild3 冻结规则中恢复为 `healthy` 的对象。BS baseline 修正后只剩 `+109` 个 `r3_only`，已收敛到由新增 baseline Cell 直接驱动的合理范围。

## 共同 baseline 对象画像稳定性

| obj | common_cnt | center_diff_p90_m | center_diff_max_m | p90_diff_p90_m | gps_ratio_diff_max | signal_ratio_diff_max |
| --- | --- | --- | --- | --- | --- | --- |
| cell | 192678 | 0 | 0 | 0 | 0.0000 | 0.0000 |
| bs | 93001 | 0 | 0 | 0 | 0.0000 | 0.0000 |
| lac | 866 | 0 | 0 |  | 0.0000 | 0.0000 |

说明：Cell / BS / LAC 在共同 baseline 上的 `center_diff_p90_m` 与 `center_diff_max_m` 均为 0，表明坐标基线与热力层主读模型稳定。

## batch_snapshot 一致性校验

| metric_name | snapshot_value | actual_value | diff |
| --- | --- | --- | --- |
| baseline_bs | 93110 | 93110 | 0 |
| baseline_cell | 194952 | 194952 | 0 |
| baseline_lac | 866 | 866 | 0 |
| fact_governed | 24855605 | 24855605 | 0 |
| fact_pending_issue | 3825562 | 3825562 | 0 |
| fact_pending_observation | 10590738 | 10590738 | 0 |
| fact_rejected | 4499401 | 4499401 | 0 |
| fact_standardized | 43771306 | 43771306 | 0 |
| obj_bs | 193036 | 193036 | 0 |
| obj_cell | 573561 | 573561 | 0 |
| obj_lac | 50153 | 50153 | 0 |

## 全量门禁判断

- 通过项：四分流已闭环；批次快照与实际表一致；对象总量一致；共同 baseline 空间指标稳定。
- 需明确接受的规则偏差：`gps_bias` 问题池扩大、BS baseline 较 rebuild2 增加 109 个、Cell baseline 增加 2,274 个。
- 当前判断：可作为 rebuild3 首版全量结果候选；若要进入正式切换，建议先由业务确认 `gps_bias` 收紧与 Cell baseline 增量的预期。
