# `Y_codex_Layer5_Cell_Profile` 字段说明（CELL 画像表）

> 说明：底表字段名为中文；如需英文列名可用视图 `public."Y_codex_Layer5_Cell_Profile_EN"`。

## 主键（唯一键）

- `运营商ID`
- `制式`
- `LAC`
- `CELL`

## 字段列表

| 字段名（中文） | 英文原名 | 含义/口径 |
|---|---|---|
| 运营商ID | operator_id_raw | 运营商原始 ID |
| 制式 | tech_norm | 4G/5G |
| LAC | lac_dec_final | LAC 十进制（Layer_4 最终值） |
| BS | bs_id_final | 该 Cell 对应的 BS 十进制（聚合属性，取 min） |
| CELL | cell_id_dec | Cell 十进制（Layer_4 最终值） |
| 行数 | row_cnt | 明细行数（聚合计数） |
| 最早时间UTC | first_cell_ts_utc | min(`event_ts_utc`)；`event_ts_utc = ts_fill AT TIME ZONE 'UTC'` |
| 最晚时间UTC | last_cell_ts_utc | max(`event_ts_utc`)；`event_ts_utc = ts_fill AT TIME ZONE 'UTC'` |
| 活跃天数UTC | active_days_utc | `count(distinct date(event_ts_utc at time zone 'UTC'))` |
| GPS有效行数 | gps_present_cnt | `lon_final/lat_final` 同时非空的行数 |
| GPS缺失行数 | gps_missing_cnt | `lon_final/lat_final` 任一为空的行数 |
| GPS有效率 | gps_present_ratio | 百分比（0~100），保留 2 位小数：`round(100 * GPS有效行数 / 行数, 2)` |
| GPS中心经度 | center_lon | GPS 中位数中心（lon p50） |
| GPS中心纬度 | center_lat | GPS 中位数中心（lat p50） |
| GPS距离P50_米 | gps_p50_dist_m | 点到中心距离 p50（米），保留 2 位小数 |
| GPS距离P90_米 | gps_p90_dist_m | 点到中心距离 p90（米），保留 2 位小数 |
| GPS距离MAX_米 | gps_max_dist_m | 点到中心距离最大值（米），保留 2 位小数 |
| RSRP非空行数 | sig_rsrp_nonnull_cnt | `sig_rsrp_final` 非空行数 |
| RSRQ非空行数 | sig_rsrq_nonnull_cnt | `sig_rsrq_final` 非空行数 |
| SINR非空行数 | sig_sinr_nonnull_cnt | `sig_sinr_final` 非空行数 |
| RSSI非空行数 | sig_rssi_nonnull_cnt | `sig_rssi_final` 非空行数 |
| DBM非空行数 | sig_dbm_nonnull_cnt | `sig_dbm_final` 非空行数 |
| ASU_LEVEL非空行数 | sig_asu_level_nonnull_cnt | `sig_asu_level_final` 非空行数 |
| LEVEL非空行数 | sig_level_nonnull_cnt | `sig_level_final` 非空行数 |
| SS非空行数 | sig_ss_nonnull_cnt | `sig_ss_final` 非空行数 |
| RSRP有效率 | sig_rsrp_nonnull_ratio | 百分比（0~100），保留 2 位小数：`round(100 * RSRP非空行数 / 行数, 2)` |
| RSRQ有效率 | sig_rsrq_nonnull_ratio | 百分比（0~100），保留 2 位小数：`round(100 * RSRQ非空行数 / 行数, 2)` |
| SINR有效率 | sig_sinr_nonnull_ratio | 百分比（0~100），保留 2 位小数：`round(100 * SINR非空行数 / 行数, 2)` |
| DBM有效率 | sig_dbm_nonnull_ratio | 百分比（0~100），保留 2 位小数：`round(100 * DBM非空行数 / 行数, 2)` |
| 原生有信号行数 | native_any_signal_row_cnt | 原始报文 `sig_*` 任一非空的行数 |
| 原生无信号行数 | native_no_signal_row_cnt | 原始报文 `sig_*` 全空的行数 |
| 需要补齐行数 | need_fill_row_cnt | `signal_missing_before_cnt > 0` 的行数 |
| 补齐成功行数 | filled_row_cnt | `signal_filled_field_cnt > 0` 的行数 |
| 补齐_同CELL_行数 | filled_by_cell_nearest_row_cnt | 补齐来源=同 Cell 时间最近，且补齐成功的行数 |
| 补齐_BS_TOP_行数 | filled_by_bs_top_cell_nearest_row_cnt | 补齐来源=同 BS 下 top cell 时间最近，且补齐成功的行数 |
| 补齐失败行数 | fill_failed_row_cnt | 需要补齐但 `signal_filled_field_cnt=0` 的行数 |
| 缺失字段数_补前合计 | missing_field_before_sum | 所有行 `signal_missing_before_cnt` 求和 |
| 缺失字段数_补后合计 | missing_field_after_sum | 所有行 `signal_missing_after_cnt` 求和 |
| 补齐字段数合计 | filled_field_sum | 所有行 `signal_filled_field_cnt` 求和 |
| 疑似碰撞标记 | is_collision_suspect | 该 Cell 所属桶是否命中“疑似碰撞”（来自 Layer_4 明细字段 `is_collision_suspect`，聚合取 max>0） |
| 严重碰撞桶标记 | is_severe_collision | 该 Cell 所属桶是否命中“严重碰撞桶”（来自 Layer_4 明细字段 `is_severe_collision`，聚合取 max=true） |
| 碰撞原因 | collision_reason | 碰撞判定原因（来自 Layer_4 明细字段 `collision_reason`，聚合取任一非空值） |
| GPS漂移行数 | gps_drift_row_cnt | `gps_status='Drift'` 的明细行数 |
| GPS漂移占比 | gps_drift_row_pct | 百分比（0~100），保留 2 位小数：`round(100 * GPS漂移行数 / 行数, 2)` |
| 移动CELL标记 | is_dynamic_cell | 是否为移动/动态 Cell（来自 Layer_3 Step35 结果映射；本表聚合取 max>0） |
| 移动原因 | dynamic_reason | 移动/动态判定原因（来自 Layer_3 Step35 结果） |
| 移动半长轴KM | half_major_dist_km | 轨迹椭圆半长轴（km，来自 Layer_3 Step35 结果） |
| 样本不足 | is_low_sample | `行数 < min_rows_for_profile` |
| 有GPS画像 | has_gps_profile | `GPS有效行数 > 0` |
| GPS不稳定 | is_gps_unstable | `GPS距离P90_米 > 阈值`（阈值=4G/5G 参数化） |
