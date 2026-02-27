# Layer_3 Summary（20251224）

## 执行结果

- Step30~34 + Step99 已完成（全量）。
- Gate-0（DB COMMENT 双语覆盖）通过：missing=0 且 not_bilingual=0。
- SR-02（跨步一致性）通过：Step06=Step31=Step33 行数一致；Step31 join Step30 覆盖率=100%；键一致；枚举集合无脏值。

## 一眼拍板（结论）

- Step30：PASS（Unusable 占比 `0.005785`；collision 疑似占比 `0.049623`；中心点合法性异常=0）
- Step31：PASS（src_id 空值=0；Risk 回填占比 `0.00260636`；Drift 占比 `0.06286962`）
- Step32：WARN（`PASS=232, WARN=72, FAIL=0`；主要 WARN 来自 `FILLED_FROM_RISK_BS`）
- Step33：PASS（`none_ratio=0.02887178`；`bs_agg_ratio=0.08957302`）
- Step34：PASS（`PASS=684, FAIL=0`）

## Step32 WARN 摘要

- WARN 计数（按 `metric_code`）：
  - `FILLED_FROM_RISK_BS`: 56
  - `BS_COLLISION_SUSPECT_CNT`: 8
  - `BS_RISK_CNT`: 8
- 需要在报告里解释/给 TopN：直接查看 `public."Y_codex_Layer3_Step32_Compare"` 中 `pass_flag='WARN'` 的明细即可。

## 清理

- 已清理 Step30 v4 中间/分片表（`public."Y_codex_Layer3_Step30__v4_*"` 及 `__shard_*`），释放临时空间；不影响最终输出表与 Step31~34 结果。

