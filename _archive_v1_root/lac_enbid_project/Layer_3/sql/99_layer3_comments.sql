-- Layer_3：集中写 COMMENT（v3：双语覆盖=100%）
-- 运行时机：Step30~Step34 的输出表全部生成后执行。
-- 格式要求（用于机器校验）：
--   - TABLE：'CN: ...; EN: ...'
--   - COLUMN：'CN: 中文名=...; 说明=...; EN: ...'
-- 验收：缺任一字段注释 / 不满足 CN+EN 格式 => FAIL 阻断（见 RUNBOOK v3 Gate-0）。

SET statement_timeout = 0;

/* ============================================================================
 * Step30：基站主库 + GPS分级统计
 * ==========================================================================*/

COMMENT ON TABLE public."Y_codex_Layer3_Step30_Master_BS_Library" IS
'CN: Step30 基站主库：按物理分桶键 wuli_fentong_bs_key=tech_norm|bs_id|lac_dec_final 聚合可信 GPS 点，生成基站中心点/离散度、共建标记、碰撞疑似与覆盖时间画像; EN: Step30 master BS library aggregated by physical bucket key (tech_norm|bs_id|lac_dec_final) with center/scatter/shared/collision/time profile.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".tech_norm IS 'CN: 中文名=制式_标准化; 说明=制式归一化值（4G/5G）; EN: Normalized tech (4G/5G).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".bs_id IS 'CN: 中文名=基站ID; 说明=基站编号（优先用已解析 bs_id；缺失时 4G=cell/256, 5G=cell/4096 回退派生）; EN: BS id (prefer parsed; fallback derived by tech).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".wuli_fentong_bs_key IS 'CN: 中文名=物理分桶基站键; 说明=tech_norm|bs_id|lac_dec_final，用于防止跨 LAC 错配污染中心点/共建判断; EN: Physical bucket key = tech_norm|bs_id|lac_dec_final.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".lac_dec_final IS 'CN: 中文名=最终可信LAC; 说明=来自 Layer2 Step06 的可信 LAC（已过白名单/反哺口径）; EN: Final trusted LAC from Layer2 Step06.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".shared_operator_cnt IS 'CN: 中文名=共建运营商数量; 说明=该基站桶下出现的 distinct operator 数量（按 Step06）; EN: Count of distinct operators within bucket.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".shared_operator_list IS 'CN: 中文名=共建运营商列表; 说明=按字典序拼接的 operator_id_raw（逗号分隔）; EN: Comma-separated operator_id_raw list.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".is_multi_operator_shared IS 'CN: 中文名=是否多运营商共建/共用; 说明=shared_operator_cnt>1; EN: Multi-operator shared flag (shared_operator_cnt>1).';

COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".gps_valid_cell_cnt IS 'CN: 中文名=有效GPS的cell来源数; 说明=参与聚合的可信 GPS 点按 cell 聚合后计数（用于 Unusable/Risk/Usable 分级）; EN: Distinct cell sources with verified GPS.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".gps_valid_point_cnt IS 'CN: 中文名=有效GPS点行数; 说明=参与聚合的可信 GPS 点行数（点级规模）; EN: Count of verified GPS rows.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".gps_valid_level IS 'CN: 中文名=GPS可用性分级; 说明=Unusable(0)/Risk(1)/Usable(>1)，以 gps_valid_cell_cnt 为准; EN: GPS validity level by distinct cell sources.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".bs_center_lon IS 'CN: 中文名=基站中心经度; 说明=基于 cell 代表点的鲁棒中心点（经纬度合法且非(0,0)）；Unusable 置空; EN: BS center longitude (robust median), NULL for Unusable.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".bs_center_lat IS 'CN: 中文名=基站中心纬度; 说明=基于 cell 代表点的鲁棒中心点；Unusable 置空; EN: BS center latitude (robust median), NULL for Unusable.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".gps_p50_dist_m IS 'CN: 中文名=离散度P50(米); 说明=cell 代表点到中心点距离的 50 分位（米）; EN: P50 distance (meters).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".gps_p90_dist_m IS 'CN: 中文名=离散度P90(米); 说明=cell 代表点到中心点距离的 90 分位（米）; EN: P90 distance (meters).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".gps_max_dist_m IS 'CN: 中文名=离散度MAX(米); 说明=cell 代表点到中心点距离的最大值（米）; EN: Max distance (meters).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".outlier_removed_cnt IS 'CN: 中文名=剔除异常GPS点数; 说明=鲁棒中心点算法剔除的漂移/异常 GPS 点数量（按距离阈值）；EN: Outlier removed GPS point count (trimmed by distance threshold).';

COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".is_collision_suspect IS 'CN: 中文名=是否碰撞疑似; 说明=1 表示疑似存在跨小区/跨 LAC 错配或共建污染（综合离散度阈值与 Step05 多LAC哨兵）; EN: Collision suspect flag.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".collision_reason IS 'CN: 中文名=碰撞疑似原因; 说明=原因短语（可能为多原因，用 ; 分隔）; EN: Collision reason text.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".anomaly_cell_cnt IS 'CN: 中文名=多LAC哨兵命中cell数; 说明=命中 Layer2 Step05 多LAC哨兵的 distinct cell 数; EN: Count of cells hitting Step05 multi-LAC sentinel.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".first_seen_ts IS 'CN: 中文名=首次出现时间; 说明=该桶在 Step06 中的最早 ts_std; EN: First seen timestamp from Step06.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".last_seen_ts IS 'CN: 中文名=最后出现时间; 说明=该桶在 Step06 中的最晚 ts_std; EN: Last seen timestamp from Step06.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Master_BS_Library".active_days IS 'CN: 中文名=活跃天数; 说明=该桶在 Step06 中出现的 distinct report_date 天数; EN: Active days (distinct report_date) from Step06.';

COMMENT ON TABLE public."Y_codex_Layer3_Step30_Gps_Level_Stats" IS
'CN: Step30 GPS可用性分布统计：将 Step30 物理分桶表按运营商拆分后，统计 Unusable/Risk/Usable 的基站数与占比; EN: Step30 gps_valid_level stats by operator and tech (bucket split by shared_operator_list).';

COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Gps_Level_Stats".tech_norm IS 'CN: 中文名=制式_标准化; 说明=4G/5G; EN: Normalized tech.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Gps_Level_Stats".operator_id_raw IS 'CN: 中文名=运营商id_细粒度; 说明=例如 46000/46001/46011/46015/46020; EN: Raw operator id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Gps_Level_Stats".gps_valid_level IS 'CN: 中文名=GPS可用性分级; 说明=Unusable/Risk/Usable; EN: GPS validity level.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Gps_Level_Stats".bs_cnt IS 'CN: 中文名=基站数; 说明=该运营商×制式下的基站桶数量; EN: BS bucket count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step30_Gps_Level_Stats".bs_pct IS 'CN: 中文名=占比; 说明=该运营商×制式内的比例; EN: Share within operator+tech.';

/* ============================================================================
 * Step31：明细 GPS 修正/补齐
 * ==========================================================================*/

COMMENT ON TABLE public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" IS
'CN: Step31 明细GPS回填/纠偏：基于 Step06 明细与 Step30 基站中心点，对 Missing/Drift 记录回填/纠偏经纬度，保留追溯字段与来源标记; EN: Step31 cell-level GPS fixed by BS center with traceability fields and source/status labels.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".src_seq_id IS 'CN: 中文名=来源seq_id; 说明=追溯字段，来自 Step06.seq_id; EN: Trace field from Step06.seq_id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".src_record_id IS 'CN: 中文名=来源记录ID; 说明=追溯字段，来自 Step06."记录id"; EN: Trace field from Step06."记录id".';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".operator_id_raw IS 'CN: 中文名=运营商id_细粒度; 说明=原始运营商编码（例如 46000）; EN: Raw operator id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".operator_group_hint IS 'CN: 中文名=运营商组_提示; 说明=用于报表展示（例如 CMCC/CUCC/CTCC/OTHER）; EN: Operator family hint.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".tech_norm IS 'CN: 中文名=制式_标准化; 说明=4G/5G; EN: Normalized tech.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".bs_id IS 'CN: 中文名=基站ID; 说明=站级索引（与 Step30 对齐）; EN: BS id aligned to Step30.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sector_id IS 'CN: 中文名=扇区ID; 说明=如源数据可得则透传；否则可能为空; EN: Sector id (optional).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".cell_id_dec IS 'CN: 中文名=Cell十进制; 说明=小区标识（十进制）; EN: Cell id (decimal).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".lac_dec_final IS 'CN: 中文名=最终可信LAC; 说明=来自 Step06 的可信 LAC; EN: Final trusted LAC from Step06.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".wuli_fentong_bs_key IS 'CN: 中文名=物理分桶基站键; 说明=tech_norm|bs_id|lac_dec_final; EN: Physical bucket key.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".gps_status IS 'CN: 中文名=GPS状态_原始判定; 说明=Verified/Missing/Drift（Drift=距基站中心点超过阈值）; EN: Raw GPS status (Verified/Missing/Drift).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".gps_status_final IS 'CN: 中文名=GPS状态_修正后; 说明=Verified/Missing（回填成功则 Verified）; EN: Final GPS status (Verified/Missing).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".gps_source IS 'CN: 中文名=GPS来源; 说明=Original_Verified/Augmented_from_BS/Augmented_from_Risk_BS/Not_Filled; EN: GPS source label.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".is_from_risk_bs IS 'CN: 中文名=是否来自风险基站回填; 说明=1 表示来自 Risk 基站中心点回填/纠偏; EN: 1 if filled from Risk-level BS.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".gps_dist_to_bs_m IS 'CN: 中文名=原GPS到基站中心距离(米); 说明=用于 Drift 判定与排障；原始无 GPS 则为空; EN: Distance (m) from raw GPS to BS center.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".lon_raw IS 'CN: 中文名=原始经度; 说明=回填/纠偏前经度; EN: Raw longitude before fix.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".lat_raw IS 'CN: 中文名=原始纬度; 说明=回填/纠偏前纬度; EN: Raw latitude before fix.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".lon_final IS 'CN: 中文名=最终经度; 说明=回填/纠偏后经度（可能等于原值）; EN: Final longitude after fix.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".lat_final IS 'CN: 中文名=最终纬度; 说明=回填/纠偏后纬度（可能等于原值）; EN: Final latitude after fix.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".gps_valid_level IS 'CN: 中文名=基站GPS可用性分级; 说明=来自 Step30（Unusable/Risk/Usable）; EN: GPS validity level from Step30.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".is_collision_suspect IS 'CN: 中文名=是否碰撞疑似; 说明=来自 Step30（1=疑似）; EN: Collision suspect from Step30.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".is_multi_operator_shared IS 'CN: 中文名=是否多运营商共建/共用; 说明=来自 Step30; EN: Multi-operator shared from Step30.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".shared_operator_list IS 'CN: 中文名=共建运营商列表; 说明=来自 Step30（逗号分隔）; EN: Shared operator list from Step30.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".shared_operator_cnt IS 'CN: 中文名=共建运营商数量; 说明=来自 Step30; EN: Shared operator count from Step30.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".ts_std IS 'CN: 中文名=报文时间; 说明=标准化后的时间戳（用于按时间切片/最近时间补齐）; EN: Standardized timestamp.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".report_date IS 'CN: 中文名=上报日期; 说明=按天切片口径（date）; EN: Report date.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_rsrp IS 'CN: 中文名=RSRP; 说明=信号字段（原始透传，可为空）; EN: Signal RSRP (raw pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_rsrq IS 'CN: 中文名=RSRQ; 说明=信号字段（原始透传，可为空）; EN: Signal RSRQ (raw pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_sinr IS 'CN: 中文名=SINR; 说明=信号字段（原始透传，可为空）; EN: Signal SINR (raw pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_rssi IS 'CN: 中文名=RSSI; 说明=信号字段（原始透传，可为空）; EN: Signal RSSI (raw pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_dbm IS 'CN: 中文名=DBM; 说明=信号字段（原始透传，可为空）; EN: Signal dBm (raw pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_asu_level IS 'CN: 中文名=ASU Level; 说明=信号字段（原始透传，可为空）; EN: Signal ASU level (raw pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_level IS 'CN: 中文名=Level; 说明=信号字段（原始透传，可为空）; EN: Signal level (raw pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sig_ss IS 'CN: 中文名=SS; 说明=信号字段（原始透传，可为空）; EN: Signal SS (raw pass-through).';

COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".parsed_from IS 'CN: 中文名=解析来源; 说明=解析策略/来源标记（透传）; EN: Parsed-from marker (pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".match_status IS 'CN: 中文名=匹配状态; 说明=解析匹配结果（透传）; EN: Match status (pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"."数据来源" IS 'CN: 中文名=数据来源; 说明=源字段透传（用于排障/溯源）; EN: Data source (pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"."北京来源" IS 'CN: 中文名=北京来源; 说明=源字段透传（用于排障/溯源）; EN: Beijing source (pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".did IS 'CN: 中文名=设备ID(did); 说明=源字段透传; EN: Device id (did), pass-through.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".ip IS 'CN: 中文名=IP; 说明=源字段透传; EN: IP, pass-through.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".sdk_ver IS 'CN: 中文名=SDK版本; 说明=源字段透传; EN: SDK version, pass-through.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".brand IS 'CN: 中文名=品牌; 说明=源字段透传; EN: Brand, pass-through.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".model IS 'CN: 中文名=机型; 说明=源字段透传; EN: Model, pass-through.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step31_Cell_Gps_Fixed".oaid IS 'CN: 中文名=OAID; 说明=源字段透传; EN: OAID, pass-through.';

/* ============================================================================
 * Step32：对比报表（Raw + v2 指标表）
 * ==========================================================================*/

COMMENT ON TABLE public."Y_codex_Layer3_Step32_Compare_Raw" IS
'CN: Step32 对比报表（Raw）：保留 v1 聚合结果（收益/风险规模），用于排障与复核; EN: Step32 raw aggregated compare table (v1-style) for debugging.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".report_section IS 'CN: 中文名=报表分区; 说明=GPS_GAIN（修正收益）/BS_RISK（站级风险）; EN: Section: GPS_GAIN / BS_RISK.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".operator_id_raw IS 'CN: 中文名=运营商id_细粒度; 说明=按运营商切片（BS_RISK 从 shared_operator_list 拆分）; EN: Raw operator id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".tech_norm IS 'CN: 中文名=制式_标准化; 说明=4G/5G; EN: Normalized tech.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".report_date IS 'CN: 中文名=上报日期; 说明=GPS_GAIN 按天统计；BS_RISK 为空; EN: Report date (GPS_GAIN only).';

COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".row_cnt IS 'CN: 中文名=行数; 说明=GPS_GAIN 明细行数; EN: Row count (GPS_GAIN).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".missing_cnt_before IS 'CN: 中文名=Missing数_修正前; 说明=gps_status=Missing 的行数; EN: Missing count before fix.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".drift_cnt_before IS 'CN: 中文名=Drift数_修正前; 说明=gps_status=Drift 的行数; EN: Drift count before fix.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".verified_cnt_before IS 'CN: 中文名=Verified数_修正前; 说明=gps_status=Verified 的行数; EN: Verified count before fix.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".missing_to_filled_cnt IS 'CN: 中文名=Missing→Filled数; 说明=Missing 且修正后 Verified 的行数; EN: Missing→Filled count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".drift_to_corrected_cnt IS 'CN: 中文名=Drift→Corrected数; 说明=Drift 且修正后 Verified 的行数; EN: Drift→Corrected count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".has_gps_before_cnt IS 'CN: 中文名=有GPS数_修正前; 说明=gps_status in (Verified,Drift); EN: Has-GPS before count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".has_gps_after_cnt IS 'CN: 中文名=有GPS数_修正后; 说明=gps_status_final=Verified; EN: Has-GPS after count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".filled_from_usable_bs_cnt IS 'CN: 中文名=来自Usable基站回填数; 说明=gps_source=Augmented_from_BS; EN: Filled from Usable BS.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".filled_from_risk_bs_cnt IS 'CN: 中文名=来自Risk基站回填数; 说明=gps_source=Augmented_from_Risk_BS; EN: Filled from Risk BS.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".not_filled_cnt IS 'CN: 中文名=未回填数; 说明=gps_source=Not_Filled; EN: Not filled count.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".bs_cnt IS 'CN: 中文名=基站数; 说明=BS_RISK 下基站桶数（按运营商拆分口径）; EN: BS count (BS_RISK).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".unusable_bs_cnt IS 'CN: 中文名=Unusable基站数; 说明=gps_valid_level=Unusable; EN: Unusable BS count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".risk_bs_cnt IS 'CN: 中文名=Risk基站数; 说明=gps_valid_level=Risk; EN: Risk BS count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".usable_bs_cnt IS 'CN: 中文名=Usable基站数; 说明=gps_valid_level=Usable; EN: Usable BS count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".collision_suspect_bs_cnt IS 'CN: 中文名=碰撞疑似基站数; 说明=is_collision_suspect=1; EN: Collision suspect BS count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare_Raw".multi_operator_shared_bs_cnt IS 'CN: 中文名=多运营共建基站数; 说明=is_multi_operator_shared=true; EN: Multi-operator shared BS count.';

COMMENT ON TABLE public."Y_codex_Layer3_Step32_Compare" IS
'CN: Step32 对比报表（v2 指标表）：输出人类可读指标（metric_code/中文名/规则/实际值/pass_flag/备注），直接用于 PASS/FAIL/WARN 拍板; EN: Step32 human-friendly metric table with PASS/FAIL/WARN.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".report_section IS 'CN: 中文名=报表分区; 说明=GPS_GAIN/BS_RISK; EN: Section: GPS_GAIN / BS_RISK.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".operator_id_raw IS 'CN: 中文名=运营商id_细粒度; 说明=按运营商切片（部分指标可为空表示整体）; EN: Raw operator id (nullable for overall).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".tech_norm IS 'CN: 中文名=制式_标准化; 说明=4G/5G（部分指标可为空表示整体）; EN: Normalized tech (nullable for overall).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".report_date IS 'CN: 中文名=上报日期; 说明=GPS_GAIN 指标按天；BS_RISK 指标为空; EN: Report date (GPS_GAIN only).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".metric_code IS 'CN: 中文名=指标编码; 说明=稳定的机器可读编码（用于对齐报告/验收）; EN: Metric code (stable, machine-readable).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".metric_name_cn IS 'CN: 中文名=指标中文名; 说明=人类可读指标名称; EN: Metric name (Chinese).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".expected_rule_cn IS 'CN: 中文名=期望/规则（中文）; 说明=该指标的验收口径（可含阈值描述）; EN: Expected rule (Chinese).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".actual_value_num IS 'CN: 中文名=实际值（数值）; 说明=统一 numeric 输出，便于排序/比较; EN: Actual value as numeric.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".pass_flag IS 'CN: 中文名=结论; 说明=PASS/FAIL/WARN（FAIL 阻断，WARN 需解释）; EN: PASS/FAIL/WARN.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step32_Compare".remark_cn IS 'CN: 中文名=备注/建议（中文）; 说明=FAIL/WARN 的排障提示或建议; EN: Remark / suggestion.';

/* ============================================================================
 * Step33：信号字段简单补齐（摸底版）
 * ==========================================================================*/

COMMENT ON TABLE public."Y_codex_Layer3_Step33_Signal_Fill_Simple" IS
'CN: Step33 信号字段简单补齐：以 Step31 为输入，先按 cell 中位数画像补齐，失败则回退到 bs 中位数画像补齐，并输出补齐来源与缺失量对比; EN: Step33 simple signal fill (cell median then BS median) with fill-source and missing counts.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".src_seq_id IS 'CN: 中文名=来源seq_id; 说明=追溯字段（来自 Step31/Step06）; EN: Trace seq id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".src_record_id IS 'CN: 中文名=来源记录ID; 说明=追溯字段（来自 Step31/Step06）; EN: Trace record id.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".operator_id_raw IS 'CN: 中文名=运营商id_细粒度; 说明=透传; EN: Raw operator id (pass-through).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".operator_group_hint IS 'CN: 中文名=运营商组_提示; 说明=透传; EN: Operator family hint.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".tech_norm IS 'CN: 中文名=制式_标准化; 说明=透传; EN: Normalized tech.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".bs_id IS 'CN: 中文名=基站ID; 说明=透传; EN: BS id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sector_id IS 'CN: 中文名=扇区ID; 说明=透传; EN: Sector id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".cell_id_dec IS 'CN: 中文名=Cell十进制; 说明=透传; EN: Cell id (decimal).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".lac_dec_final IS 'CN: 中文名=最终可信LAC; 说明=透传; EN: Final trusted LAC.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".wuli_fentong_bs_key IS 'CN: 中文名=物理分桶基站键; 说明=透传; EN: Physical bucket key.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".report_date IS 'CN: 中文名=上报日期; 说明=透传; EN: Report date.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".ts_std IS 'CN: 中文名=报文时间; 说明=透传; EN: Timestamp.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".gps_status IS 'CN: 中文名=GPS状态_原始判定; 说明=透传 Step31.gps_status; EN: Raw GPS status from Step31.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".gps_status_final IS 'CN: 中文名=GPS状态_修正后; 说明=透传 Step31.gps_status_final; EN: Final GPS status from Step31.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".gps_source IS 'CN: 中文名=GPS来源; 说明=透传 Step31.gps_source; EN: GPS source from Step31.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".is_from_risk_bs IS 'CN: 中文名=是否来自风险基站回填; 说明=透传 Step31.is_from_risk_bs; EN: From-risk-BS flag.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".lon_final IS 'CN: 中文名=最终经度; 说明=透传 Step31.lon_final; EN: Final longitude.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".lat_final IS 'CN: 中文名=最终纬度; 说明=透传 Step31.lat_final; EN: Final latitude.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".signal_fill_source IS 'CN: 中文名=信号补齐来源; 说明=cell_agg/bs_agg/none（优先 cell_agg）; EN: Signal fill source (cell_agg/bs_agg/none).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".signal_missing_before_cnt IS 'CN: 中文名=补齐前缺失字段数; 说明=按配置的信号字段（8个）逐列缺失计数求和; EN: Missing signal field count before fill.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".signal_missing_after_cnt IS 'CN: 中文名=补齐后缺失字段数; 说明=补齐后的缺失计数（after 应不大于 before）; EN: Missing signal field count after fill.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_rsrp_final IS 'CN: 中文名=最终RSRP; 说明=原值优先，其次 cell_agg，再次 bs_agg; EN: Final RSRP (raw > cell_agg > bs_agg).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_rsrq_final IS 'CN: 中文名=最终RSRQ; 说明=同上; EN: Final RSRQ.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_sinr_final IS 'CN: 中文名=最终SINR; 说明=同上; EN: Final SINR.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_rssi_final IS 'CN: 中文名=最终RSSI; 说明=同上; EN: Final RSSI.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_dbm_final IS 'CN: 中文名=最终DBM; 说明=同上; EN: Final dBm.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_asu_level_final IS 'CN: 中文名=最终ASU Level; 说明=同上; EN: Final ASU level.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_level_final IS 'CN: 中文名=最终Level; 说明=同上; EN: Final level.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step33_Signal_Fill_Simple".sig_ss_final IS 'CN: 中文名=最终SS; 说明=同上; EN: Final SS.';

/* ============================================================================
 * Step34：信号补齐摸底报表（Raw + v2 指标表）
 * ==========================================================================*/

COMMENT ON TABLE public."Y_codex_Layer3_Step34_Signal_Compare_Raw" IS
'CN: Step34 信号补齐摸底报表（Raw）：保留 v1 聚合结果（按维度/整体，缺失 before/after 的 sum/avg），用于排障与复核; EN: Step34 raw signal compare aggregates (sum/avg missing before/after) for debugging.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".report_section IS 'CN: 中文名=报表分区; 说明=BY_DIM（按 operator/tech/date）/OVERALL（整体）; EN: Section: BY_DIM / OVERALL.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".operator_id_raw IS 'CN: 中文名=运营商id_细粒度; 说明=BY_DIM 有值；OVERALL 为空; EN: Raw operator id (BY_DIM only).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".tech_norm IS 'CN: 中文名=制式_标准化; 说明=BY_DIM 有值；OVERALL 为空; EN: Normalized tech (BY_DIM only).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".report_date IS 'CN: 中文名=上报日期; 说明=BY_DIM 有值；OVERALL 为空; EN: Report date (BY_DIM only).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".signal_fill_source IS 'CN: 中文名=信号补齐来源; 说明=none/cell_agg/bs_agg; EN: Signal fill source.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".row_cnt IS 'CN: 中文名=行数; 说明=该维度下明细行数; EN: Row count.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".avg_missing_before IS 'CN: 中文名=平均缺失字段数_补齐前; 说明=signal_missing_before_cnt 的平均值; EN: Avg missing-before.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".avg_missing_after IS 'CN: 中文名=平均缺失字段数_补齐后; 说明=signal_missing_after_cnt 的平均值; EN: Avg missing-after.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".sum_missing_before IS 'CN: 中文名=缺失字段总量_补齐前; 说明=signal_missing_before_cnt 的求和; EN: Sum missing-before.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare_Raw".sum_missing_after IS 'CN: 中文名=缺失字段总量_补齐后; 说明=signal_missing_after_cnt 的求和; EN: Sum missing-after.';

COMMENT ON TABLE public."Y_codex_Layer3_Step34_Signal_Compare" IS
'CN: Step34 信号补齐摸底报表（v2 指标表）：在 Raw 基础上输出可读指标（metric_code/中文名/规则/实际值/pass_flag/备注），本表 pass_flag 仅允许 PASS/FAIL; EN: Step34 human-friendly metric table with PASS/FAIL only.';

COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".report_section IS 'CN: 中文名=报表分区; 说明=BY_DIM/OVERALL; EN: Section: BY_DIM / OVERALL.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".operator_id_raw IS 'CN: 中文名=运营商id_细粒度; 说明=BY_DIM 有值；OVERALL 为空; EN: Raw operator id.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".tech_norm IS 'CN: 中文名=制式_标准化; 说明=BY_DIM 有值；OVERALL 为空; EN: Normalized tech.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".report_date IS 'CN: 中文名=上报日期; 说明=BY_DIM 有值；OVERALL 为空; EN: Report date.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".signal_fill_source IS 'CN: 中文名=信号补齐来源; 说明=none/cell_agg/bs_agg; EN: Signal fill source.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".metric_code IS 'CN: 中文名=指标编码; 说明=稳定的机器可读编码（例如 SUM_MISSING_AFTER）; EN: Metric code.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".metric_name_cn IS 'CN: 中文名=指标中文名; 说明=人类可读指标名称; EN: Metric name (Chinese).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".expected_rule_cn IS 'CN: 中文名=期望/规则（中文）; 说明=该指标的验收口径（例如 after<=before）; EN: Expected rule (Chinese).';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".actual_value_num IS 'CN: 中文名=实际值（数值）; 说明=统一 numeric 输出，便于排序/比较; EN: Actual value as numeric.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".pass_flag IS 'CN: 中文名=结论; 说明=PASS/FAIL（当前 Step34 仅输出 PASS/FAIL）; EN: PASS/FAIL flag.';
COMMENT ON COLUMN public."Y_codex_Layer3_Step34_Signal_Compare".remark_cn IS 'CN: 中文名=备注/建议（中文）; 说明=FAIL 时给出排障提示; EN: Remark / suggestion.';
