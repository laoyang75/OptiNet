# 参数矩阵

| 域 | 参数 | 当前值 | 作用 | 备注 |
|---|---|---:|---|---|
| Cell 存在资格 | min_records | 5 | waiting -> observing 下限 | 样本阶段参数化 |
| Cell 存在资格 | min_devices | 1 | 最低设备数 | 样本阶段参数化 |
| Cell 存在资格 | min_active_days | 1 | 最低活跃天数 | 样本阶段参数化 |
| anchorable | min_gps_points | 10 | 锚点 GPS 点门槛 | 与冻结文档 v1 一致 |
| anchorable | min_devices | 2 | 锚点设备数门槛 | 与冻结文档 v1 一致 |
| anchorable | min_active_days | 1 | 锚点活跃天数门槛 | 与冻结文档 v1 一致 |
| anchorable | max_p90_m | 1500 | 锚点空间稳定性门槛 | 与冻结文档 v1 一致 |
| baseline | min_gps_points | 20 | baseline 成熟度门槛 | 样本阶段简化 |
| baseline | min_devices | 2 | baseline 设备数门槛 | 样本阶段简化 |
| baseline | min_active_days | 3 | baseline 活跃天数门槛 | 样本阶段简化 |
| baseline | min_signal_original_ratio | 0.50 | baseline 信号原始率门槛 | 样本阶段简化 |
| BS GPS quality | usable_min_gps_points | 10 | rebuild2 sample eval 中 usable 判定 | 样本缩放后保守使用 |
| BS GPS quality | usable_max_p90_m | 1500 | rebuild2 sample eval 中 usable 判定 | 对齐 anchorable |
| BS GPS quality | risk_min_gps_points | 3 | rebuild2 sample eval 中 risk 判定 | 样本缩放后保守使用 |
| BS GPS quality | risk_max_p90_m | 4000 | rebuild2 sample eval 中 risk 判定 | 样本缩放后保守使用 |
| GPS raw keep | raw_keep_max_dist_5g_m | 500 | 原始 GPS 保留阈值（5G） | 延续 rebuild2 step3 |
| GPS raw keep | raw_keep_max_dist_non5g_m | 1000 | 原始 GPS 保留阈值（非 5G） | 延续 rebuild2 step3 |
| anomaly mapping | dynamic_bs -> dynamic | true | 旧分类映射 | 审计决策 Q7 |
| anomaly mapping | collision_suspected -> collision_suspect | true | 旧分类映射 | 审计决策 Q7 |
| anomaly mapping | collision_confirmed -> collision_confirmed | true | 旧分类映射 | 审计决策 Q7 |
| anomaly mapping | collision_uncertain -> collision_suspect | true | 旧分类映射 | 审计决策 Q7 |
| record anomaly | single_large | record tag | 进入 governed 但打标签 | 审计决策 Q7 |
| record anomaly | normal_spread | record tag | 进入 governed 但打标签 | 审计决策 Q7 |
