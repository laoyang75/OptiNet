# Layer_3 Data Dictionary v1（2025-12-18）

> v1 为“字段清单版”。  
> v2 已按“逐字段中文解释 + 示例 + 来源 + 验收 SQL”补齐：`lac_enbid_project/Layer_3/archive/Layer_3_Data_Dictionary_v2.md`。

---

## Step30：基站主库

对象：`public."Y_codex_Layer3_Step30_Master_BS_Library"`

核心字段：

- 主键：
  - `tech_norm`
  - `bs_id`
  - `wuli_fentong_bs_key`（`tech_norm|bs_id|lac_dec_final`）
- 共建：
  - `is_multi_operator_shared`
  - `shared_operator_list`
  - `shared_operator_cnt`
- GPS 可用性：
  - `gps_valid_cell_cnt`
  - `gps_valid_point_cnt`
  - `gps_valid_level`：Unusable/Risk/Usable
- 中心点与离散度：
  - `bs_center_lon`, `bs_center_lat`
  - `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_max_dist_m`
  - `outlier_removed_cnt`（v1 最多 0/1）
- 碰撞疑似：
  - `is_collision_suspect`（0/1）
  - `collision_reason`
  - `anomaly_cell_cnt`（命中 Step05 哨兵规模）
- 覆盖时间画像（来自 Step06）：
  - `first_seen_ts`, `last_seen_ts`, `active_days`

统计对象：`public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

- `tech_norm`, `operator_id_raw`, `gps_valid_level`, `bs_cnt`, `bs_pct`

---

## Step31：明细 GPS 修正/补齐

对象：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`

必须字段：

- 追溯：
  - `src_seq_id`
  - `src_record_id`
- 键：
  - `operator_id_raw`, `tech_norm`, `bs_id`, `cell_id_dec`, `lac_dec_final`, `wuli_fentong_bs_key`
- GPS：
  - `gps_status`（Verified/Missing/Drift）
  - `gps_status_final`（Verified/Missing）
  - `gps_source`（Original_Verified/Augmented_from_BS/Augmented_from_Risk_BS/Not_Filled）
  - `is_from_risk_bs`
  - `gps_dist_to_bs_m`
  - `lon_raw/lat_raw`，`lon_final/lat_final`

---

## Step32：修正前后对比报表

对象：`public."Y_codex_Layer3_Step32_Compare"`

- v1：聚合结果展示（已落为 `public."Y_codex_Layer3_Step32_Compare_Raw"`）
- v2：人类友好指标表（含 `metric_code/metric_name_cn/expected_rule_cn/actual_value_num/pass_flag`）

---

## Step33：信号补齐（摸底版）

对象：`public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`

- `signal_fill_source`：cell_agg / bs_agg / none
- `signal_missing_before_cnt` / `signal_missing_after_cnt`
- 信号最终字段（final）：
  - `sig_rsrp_final`, `sig_rsrq_final`, `sig_sinr_final`, `sig_rssi_final`
  - `sig_dbm_final`, `sig_asu_level_final`, `sig_level_final`, `sig_ss_final`

---

## Step34：信号补齐摸底报表

对象：`public."Y_codex_Layer3_Step34_Signal_Compare"`

- v1：聚合结果展示（已落为 `public."Y_codex_Layer3_Step34_Signal_Compare_Raw"`）
- v2：人类友好指标表（含 Pass 标记）
