# Layer_3 本期交付库（Final 实体表）

本文档用于确认“本期交付”的两个实体表已可直接用于下一阶段（基于 BS 画像为 cell 补齐/过滤），并记录本期口径与已知问题（不回写历史数据）。

## 1) 交付对象（实体表）

### 1.1 BS 聚合画像表（按 BS 桶）

表：`public."Y_codex_Layer3_Final_BS_Profile"`

主键：

- `(operator_id_raw, tech_norm, bs_id, lac_dec_final)`

核心字段（满足你提出的交付要求）：

- `operator_id_raw`：运营商
- `operator_group_hint`：运营商组（CMCC/CUCC/CTCC/OTHER）
- `tech_norm`：网络制式（4G/5G）
- `bs_id`、`bs_id_hex`
- `lac_dec_final`、`lac_hex`
- `device_cnt`：设备量（本期口径：`did2` 的去重数，见 2.1）
- `report_cnt`：上报量（行数）
- `cell_cnt`：cell 数量（distinct `cell_id_dec`）
- `bs_center_lon/bs_center_lat`：站中心点（来自 Step30）
- `gps_p50_dist_m/gps_p90_dist_m/gps_max_dist_m`：站内距离统计（来自 Step30）
- `lon_raw_min/lon_raw_max/lat_raw_min/lat_raw_max/gps_bbox_diag_m`：Verified 原始点的粗范围
- `is_multi_operator_shared/shared_operator_cnt/shared_operator_list`：多运营商共建信息（来自 Step30）
- `is_collision_suspect/collision_reason/anomaly_cell_cnt`：碰撞/风险相关字段（来自 Step30）

### 1.2 Cell → BS 映射表（每 cell 一行）

表：`public."Y_codex_Layer3_Final_Cell_BS_Map"`

主键：

- `(operator_id_raw, tech_norm, cell_id_dec)`

核心字段：

- `operator_id_raw`、`operator_group_hint`、`tech_norm`
- `cell_id_dec`、`cell_id_hex`
- `bs_id`、`bs_id_hex`
- `lac_dec_final`、`lac_hex`
- `wuli_fentong_bs_key`（`tech_norm|bs_id|lac_dec_final`）
- `device_cnt`：设备量（同 did2 口径）
- `report_cnt`：本映射 bucket 下的上报量
- `cell_total_report_cnt`：该 cell 在所有 bucket 上报量总和（用于判断映射歧义）
- `bucket_cnt_per_cell`、`is_ambiguous_mapping`
- `bs_center_lon/bs_center_lat/gps_valid_level/is_collision_suspect/is_multi_operator_shared/shared_operator_list`：站级画像字段（来自 Step30，便于下游策略）

## 2) 本期口径与过滤（不回写历史）

### 2.1 设备量口径：`did2`

本期 `device_cnt` 统一使用：

- `did2 = COALESCE(NULLIF(did,''), NULLIF(oaid,''))`
- `device_cnt = count(distinct did2)`

同时保留对照字段：

- `device_cnt_did = count(distinct did)`（用于核对 did vs did2 的差异）

### 2.2 非法占位过滤：`bs_id=0` / `cell_id_dec=0`

发现 Step31 明细中存在少量占位值：

- `bs_id=0`、`cell_id_dec=0`

这类记录会污染基站画像与 cell 映射，因此本期交付表做了**硬过滤（strict drop）**：

- Final_BS_Profile：过滤 `bs_id<>0` 且 `cell_id_dec<>0`
- Final_Cell_BS_Map：过滤 `bs_id<>0` 且 `cell_id_dec<>0`

说明：

- 本期不回写/不重跑 Step31/Step33 等历史产物，只在交付层面保证“交付库可用”。
- 已把“上游也应过滤”的建议写入 SQL 文件，作为后续治理记录（见 3.2）。

## 3) 验收自检（你可以复跑）

### 3.1 必须为 0 的检查

```sql
select
  count(*) filter (where bs_id=0) as bs_id_zero,
  count(*) filter (where cell_id_dec=0) as cell_id_zero,
  count(*) as total
from public."Y_codex_Layer3_Final_Cell_BS_Map";

select
  count(*) filter (where bs_id=0) as bs_id_zero,
  count(*) as total
from public."Y_codex_Layer3_Final_BS_Profile";
```

### 3.2 生成逻辑位置（代码记录，不代表已回写历史）

- 交付表生成 SQL：`lac_enbid_project/Layer_3/sql/40_layer3_delivery_bs_cell_tables.sql`
- Step31 的上游过滤建议：`lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql`

