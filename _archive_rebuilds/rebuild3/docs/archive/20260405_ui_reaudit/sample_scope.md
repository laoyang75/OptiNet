# 样本范围定义

- 样本窗口：`2025-12-01` 至 `2025-12-07`
- rebuild3 样本主输入：`rebuild3_sample.source_l0_lac`
- rebuild2 对比输入：同一份 `rebuild3_sample.source_l0_lac`，另保留 `rebuild3_sample.source_l0_gps` 作为配对参考样本
- 样本总量：`l0_lac = 34998`，`l0_gps = 36170`
- 目标覆盖：`healthy / issue / waiting / observing / rejected / baseline`

| scope_type | scenario | operator_code | tech_norm | lac | bs_id | cell_id | expected_route | l0_lac_rows | l0_gps_rows | coverage_note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bs | collision_confirmed | 46001 | 5G | 98328 | 140623 |  | fact_pending_issue | 3646 | 3772 | 对象级异常 collision_confirmed |
| bs | collision_suspect | 46011 | 5G | 405510 | 405908 |  | fact_pending_issue | 6318 | 6596 | 对象级异常 collision_suspect |
| bs | dynamic | 46001 | 4G | 4149 | 19469 |  | fact_pending_issue | 3511 | 3510 | 对象级异常 dynamic |
| bs | healthy_active_4g | 46000 | 4G | 4335 | 494747 |  | fact_governed | 4296 | 4187 | 稳定 4G healthy + baseline 主路径 |
| bs | healthy_active_5g | 46000 | 5G | 2097290 | 1425701 |  | fact_governed | 8480 | 8511 | 稳定 5G healthy + baseline 主路径 |
| bs | normal_spread | 46001 | 5G | 98310 | 140755 |  | fact_governed | 3913 | 4467 | 记录级异常 normal_spread 应保留到 governed |
| bs | single_large | 46011 | 5G | 409602 | 417849 |  | fact_governed | 4612 | 4905 | 记录级异常 single_large 应保留到 governed |
| cell | observing_candidate | 46001 | 5G | 90133 | 188722 | 773005570 | fact_pending_observation | 20 | 20 | 有一定证据但未成熟的 observing 候选 Cell |
| cell | waiting_candidate | 46015 | 5G | 2097261 | 1390319 | 5694746825 | fact_pending_observation | 2 | 2 | 低证据 waiting 候选 Cell |
| reject | reject_invalid_lac_l0_gps |  |  |  |  |  | fact_rejected | 0 | 200 | l0_gps 结构不合规样本 |
| reject | reject_invalid_lac_l0_lac |  |  |  |  |  | fact_rejected | 200 | 0 | l0_lac 结构不合规样本 |
