# Layer_3 Data Dictionary v3（口径一致性修订版，2025-12-18）

> v3 目标：保证“字典 / RUNBOOK / 模板 / DB COMMENT”四者口径一致，且可机器校验。  
> v3 不重写逐字段说明：逐字段字典仍以 v2 为底稿（已逐字段覆盖）。

底稿（逐字段字典，权威解释）：

- `lac_enbid_project/Layer_3/archive/Layer_3_Data_Dictionary_v2.md`

与 v2 的差异（v3 新增/修订点）：

1. DB COMMENT 格式改为可机器校验（CR-01）  
2. Step34 WARN 口径统一为“无 WARN”（CR-03，方案 A）  
3. 增加枚举集合校验与跨步一致性检查清单（SR-02）  

---

## 0) DB COMMENT 口径（CR-01）

权威来源：

- `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`

格式要求（用于机器校验）：

- TABLE：`CN: ...; EN: ...`
- COLUMN：`CN: 中文名=...; 说明=...; EN: ...`

Gate-0 校验 SQL：见 `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md` 与 `lac_enbid_project/Layer_3/Layer_3_验收报告模板_v3.md`。

---

## 1) v3 枚举字典（最终口径）

### 1.1 `gps_valid_level`（Step30/Step31）

- Unusable：`gps_valid_cell_cnt=0`（该桶没有可信 GPS 点；中心点为空；不参与回填）
- Risk：`gps_valid_cell_cnt=1`（只有 1 个 cell 来源点；允许回填但必须显式标记风险）
- Usable：`gps_valid_cell_cnt>1`（可用；优先用于回填）

### 1.2 `gps_status / gps_status_final`（Step31/Step33）

- gps_status：Verified / Missing / Drift
- gps_status_final：Verified / Missing

组合约束（建议 FAIL）：

- `gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS')` ⇒ `gps_status_final='Verified'`

### 1.3 `gps_source`（Step31/Step33）

- Original_Verified
- Augmented_from_BS
- Augmented_from_Risk_BS
- Not_Filled

### 1.4 `signal_fill_source`（Step33/Step34）

- none
- cell_agg
- bs_agg

### 1.5 `pass_flag`（Step32 v2 指标表）

- PASS / FAIL / WARN

说明：Step32 的 WARN 是允许的，但必须在报告中解释，并提供 TopN 样本；汇总必须按 FAIL>WARN>PASS 的优先级，不得吞 WARN（CR-02）。

### 1.6 `pass_flag`（Step34 v2 指标表，v3 口径）

- PASS / FAIL

说明：本轮采用方案 A：Step34 不输出 WARN；“none 占比异常高”的 WARN 只在 Step33 报告中体现（CR-03）。

---

## 2) 枚举集合校验（SR-02，建议 FAIL）

以下查询建议纳入验收（bad_cnt>0 即 FAIL 阻断），SQL 见 RUNBOOK v3：

- Step30：`gps_valid_level in ('Unusable','Risk','Usable')`
- Step31：`gps_status/gps_status_final/gps_source` 合法集合
- Step33：`signal_fill_source in ('none','cell_agg','bs_agg')`
- Step32：`pass_flag in ('PASS','FAIL','WARN')`
- Step34：`pass_flag in ('PASS','FAIL')`

---

## 3) 跨步一致性检查（SR-02，建议 FAIL）

检查项（bad_cnt>0 即 FAIL 阻断）：

1. 行数一致：Step31_cnt == Step06_cnt；Step33_cnt == Step31_cnt  
2. Step31 join Step30 覆盖率：Step31 的 `gps_valid_level/is_collision_suspect/is_multi_operator_shared` 不得为 NULL  
3. key 一致性：`wuli_fentong_bs_key == concat_ws('|', tech_norm, bs_id, lac_dec_final)`（Step30/Step31 都检查）  

对应 SQL：见 `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md`。

---

## 4) Step34（v3 口径）补充说明

- Step34 的职责是输出“补齐前后缺失量对比”的 PASS/FAIL（after<=before），用于硬验收补齐逻辑是否反向恶化。
- Step34 不再承载 WARN；任何 “none 占比异常高 / bs_agg 占比异常高” 统一在 Step33 报告中按阈值触发 WARN，并给 Top10 样本与后续动作。
