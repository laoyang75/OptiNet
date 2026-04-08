# Layer_4 补齐效果报告（ip_loc2 / 全量）

> Date: 2025-12-26  
> DB: `ip_loc2`  
> Scope: `4G/5G` + `{46000,46001,46011,46015,46020}` + `cell_id_dec>0` + `bs_id_final>0`

## 0) 产物清单（已生成）

- Step40 明细：`public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"`
- Step40 指标：`public."Y_codex_Layer4_Step40_Gps_Metrics"`
- Final 明细：`public."Y_codex_Layer4_Final_Cell_Library"`
- Step41 指标：`public."Y_codex_Layer4_Step41_Signal_Metrics"`
- Step42 对比：`public."Y_codex_Layer4_Step42_Compare_Summary"`
- Step43 指标汇总：`public."Y_codex_Layer4_Step40_Gps_Metrics_All"` / `public."Y_codex_Layer4_Step41_Signal_Metrics_All"`
- Step44（可选，异常标记）：`public."Y_codex_Layer4_Step44_BsId_Lt_256_Detail"` / `public."Y_codex_Layer4_Step44_BsId_Lt_256_Summary"`

## 1) 总览结论（最重要）

- 明细规模：`30,491,963` 行（Step40=Final，未丢行）
- GPS（最终可用率）：`30369669 / 30491963 = 99.5989%`（final 缺失 `122,294` 行）
- GPS 缺失显著下降：raw `340,759` → final `122,294`（减少 `218,465`，下降 `64.1113%`）
- GPS 回填覆盖：`4,042,183` 行被回填（占 `13.2566%`；Usable BS 为主）
- 信号补齐（字段维度）：缺失字段总量 `73,150,482` → `63,561,699`（共补齐 `9,588,783` 个字段，覆盖缺失字段的 `13.1083%`）
- 风险止损：严重碰撞桶不回填 GPS，命中 `2,867` 行（占 `0.009402%`）
- ENBID/gNB 编码异常（仅标记）：`bs_id_final<256` 共 `2,102` 行（占 `0.006894%`）

## 2) Step40：GPS 过滤 + 按 BS 回填

阈值口径（城市模式）：

- 4G：`dist_threshold_m=1000`
- 5G：`dist_threshold_m=500`
- 严重碰撞桶：不回填 GPS（止损）

### 2.1 Step40 指标（表：`Y_codex_Layer4_Step40_Gps_Metrics`）

| metric | value |
|---|---:|
| row_cnt | 30,491,963 |
| gps_status=Missing（注意：包含 out-of-china/空坐标等） | 341,238 |
| gps_status=Drift（与 BS 中心距离超阈值） | 3,823,239 |
| gps_fill_from_bs_cnt | 3,959,928 |
| gps_fill_from_risk_bs_cnt | 82,255 |
| gps_not_filled_cnt（final 仍缺失） | 122,294 |
| severe_collision_row_cnt | 2,867 |

### 2.2 GPS 来源分布（字段：`gps_source`）

| gps_source | row_cnt | row_pct |
|---|---:|---:|
| Original_Verified | 26,327,486 | 86.3424% |
| Augmented_from_BS | 3,959,928 | 12.9868% |
| Augmented_from_Risk_BS | 82,255 | 0.2698% |
| Not_Filled | 122,294 | 0.4011% |

### 2.3 `Not_Filled` 的主要原因（`122,294` 行）

| reason | row_cnt |
|---|---:|
| 无法关联到 Layer_3 BS 库（`gps_valid_level is null`） | 119,156 |
| 严重碰撞桶止损（`is_severe_collision=true`） | 2,867 |
| BS 画像存在但不可回填（`gps_valid_level` 非 Usable/Risk） | 271 |

## 3) Step41：信号二阶段补齐（同 cell 最近 → 同 BS top cell 最近）

### 3.1 指标口径解释：`need_fill_row_cnt`

`need_fill_row_cnt` 表示：8 个信号字段中**至少 1 个为空**的行数。由于 `sig_ss/sig_rssi` 等字段天然缺失率高，这个数值通常会非常接近总行数；本报告以 `filled_field_sum / missing_field_before_sum` 作为“补齐收益”的主指标。

### 3.2 Step41 指标（表：`Y_codex_Layer4_Step41_Signal_Metrics`）

| metric | value |
|---|---:|
| row_cnt | 30,491,963 |
| need_fill_row_cnt | 30,491,963 |
| filled_by_cell_nearest_row_cnt | 30,140,602 |
| filled_by_bs_top_cell_row_cnt | 166,068 |
| missing_field_before_sum | 73,150,482 |
| missing_field_after_sum | 63,561,699 |
| filled_field_sum | 9,588,783 |

### 3.3 信号补齐来源分布（字段：`signal_fill_source`）

| signal_fill_source | row_cnt | row_pct |
|---|---:|---:|
| cell_nearest | 30,140,602 | 98.8477% |
| bs_top_cell_nearest | 166,068 | 0.5446% |
| none（无 donor） | 185,293 | 0.6077% |

> 说明：`signal_fill_source='none'` 等价于 `signal_donor_seq_id is null`（完全没有可用 donor）。

### 3.4 各字段空值下降（before → after）

| field | null_before | null_after | reduced | reduced_pct |
|---|---:|---:|---:|---:|
| sig_rsrq | 1,092,357 | 255,001 | 837,356 | 76.6559% |
| sig_rsrp | 1,862,137 | 712,723 | 1,149,414 | 61.7255% |
| sig_level | 2,761,035 | 1,168,084 | 1,592,951 | 57.6940% |
| sig_asu_level | 2,731,659 | 1,166,468 | 1,565,191 | 57.2982% |
| sig_dbm | 3,158,009 | 1,523,868 | 1,634,141 | 51.7459% |
| sig_sinr | 8,522,295 | 7,430,312 | 1,091,983 | 12.8133% |
| sig_ss | 28,287,370 | 27,280,570 | 1,006,800 | 3.5592% |
| sig_rssi | 24,735,620 | 24,024,673 | 710,947 | 2.8742% |

### 3.5 单行补齐“命中字段数”分布（字段：`signal_filled_field_cnt`）

| filled_field_cnt | row_cnt | row_pct |
|---:|---:|---:|
| 0 | 27,150,436 | 89.0413% |
| 1 | 1,160,614 | 3.8063% |
| 2 | 313,566 | 1.0284% |
| 3 | 669,997 | 2.1973% |
| 4 | 677,789 | 2.2228% |
| 5 | 60,795 | 0.1994% |
| 6 | 435,447 | 1.4281% |
| 7 | 23,319 | 0.0765% |

解释：大量行 `filled_field_cnt=0` 并不代表“没有 donor”，而是代表“该行缺失的字段在 donor 上也缺失/无法补齐”，因此需要结合“字段级空值下降表”来评估总体收益。

## 4) Step42：Raw vs Final 对比（表：`Y_codex_Layer4_Step42_Compare_Summary`）

| dataset | row_cnt | gps_present_cnt | gps_missing_cnt | sig_rsrp_null_cnt | sig_rsrq_null_cnt | sig_sinr_null_cnt | sig_rssi_null_cnt | sig_dbm_null_cnt | sig_asu_level_null_cnt | sig_level_null_cnt | sig_ss_null_cnt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw | 30,491,963 | 30,151,204 | 340,759 | 1,112,701 | 1,092,357 | 8,522,295 | 24,735,620 | 3,158,009 | 2,731,659 | 2,761,035 | 28,287,370 |
| final | 30,491,963 | 30,369,669 | 122,294 | 712,723 | 255,001 | 7,430,312 | 24,024,673 | 1,523,868 | 1,166,468 | 1,168,084 | 27,280,570 |

## 5) 异常标记：`bs_id_final < 256`（仅标记，不拦截）

规则说明已补充到：`lac_enbid_project/Layer_1/Enbid/Enbid_Filter_Rules_v1.md`

本次全量命中：`2,102` 行（占 `0.006894%`）。按运营商/制式汇总（表：`Y_codex_Layer4_Step44_BsId_Lt_256_Summary`）：

| operator_id_raw | tech_norm | row_cnt | distinct_bs_cnt | bs_id_min | bs_id_max |
|---|---|---:|---:|---:|---:|
| 46000 | 4G | 657 | 96 | 1 | 255 |
| 46000 | 5G | 605 | 16 | 1 | 149 |
| 46001 | 4G | 327 | 69 | 1 | 253 |
| 46011 | 5G | 236 | 4 | 1 | 23 |
| 46011 | 4G | 188 | 49 | 1 | 254 |
| 46001 | 5G | 87 | 12 | 1 | 253 |
| 46015 | 5G | 2 | 1 | 3 | 3 |

