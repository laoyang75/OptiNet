# Layer_3 Data Dictionary v2（逐字段中文解释版，2025-12-18）

目标：做到“人类不看 SQL 也能理解每个字段”，并能用少量 SQL 快速验收。

权威来源：

- 数据库 COMMENT：`lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`
- 执行与验收口径：`lac_enbid_project/Layer_3/archive/Layer_3_执行计划_RUNBOOK_v2.md`

字段表模板（每列必须说明）：

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|

---

## 0) 枚举字典（必须先读）

### 0.1 `gps_valid_level`（Step30/Step31）

- Unusable：该基站桶下 `gps_valid_cell_cnt=0`，无可用 Verified GPS 点（中心点为空，不参与回填）
- Risk：`gps_valid_cell_cnt=1`，只有 1 个 cell 来源点（可回填，但必须显式标记风险）
- Usable：`gps_valid_cell_cnt>1`，可用（优先用于回填）

常见误用：

- 把“点行数”当作“cell 来源数”：本项目分级以 `gps_valid_cell_cnt` 为准（防止单 cell 大量点误判为可用）

### 0.2 `gps_status` / `gps_status_final`（Step31/Step33）

- `gps_status`（原始判定）：
  - Missing：原始无 GPS（`has_gps=false`）
  - Drift：原始有 GPS 但偏离基站中心点过大（`gps_dist_to_bs_m > drift_if_dist_m_gt`）
  - Verified：其余情况（不覆盖原值）
- `gps_status_final`（修正后）：
  - Verified：原始 Verified，或成功用基站中心点回填/纠偏
  - Missing：无法回填（Unusable 或中心点为空）

组合约束（必须满足）：

- 当 `gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS')` 时，`gps_status_final` 必须为 `Verified`

### 0.3 `gps_source`（Step31/Step33）

- Original_Verified：原始 Verified（不覆盖）
- Augmented_from_BS：来自 Usable 基站中心点回填/纠偏
- Augmented_from_Risk_BS：来自 Risk 基站中心点回填/纠偏（必须 `is_from_risk_bs=1`）
- Not_Filled：未回填（Unusable/无中心点/条件不满足）

### 0.4 `signal_fill_source`（Step33/Step34）

- none：原始已有值或无法补齐（聚合也没有可用值；或补齐前缺失为 0）
- cell_agg：从同一 `(operator_id_raw, tech_norm, cell_id_dec)` 的聚合画像补齐
- bs_agg：cell 画像无法补齐，回退到同一 `(tech_norm, bs_id, wuli_fentong_bs_key)` 的聚合画像补齐

### 0.5 `pass_flag`（Step32/Step34 v2 指标表）

- PASS：满足规则
- FAIL：不满足规则（阻断，需要修 SQL 或重跑）
- WARN：不阻断，但必须在报告里解释风险并给 TopN 样本

### 0.6 `metric_code`（Step32/Step34 v2 指标表）

Step32（GPS/风险）可能出现：

- HAS_GPS_BEFORE / HAS_GPS_AFTER
- MISSING_TO_FILLED / DRIFT_TO_CORRECTED
- FILLED_FROM_RISK_BS
- BS_TOTAL / BS_RISK_CNT / BS_COLLISION_SUSPECT_CNT

Step34（信号缺失）可能出现：

- SUM_MISSING_BEFORE / SUM_MISSING_AFTER
- AVG_MISSING_BEFORE / AVG_MISSING_AFTER

---

## 1) Step30：基站主库（Master BS Library）

对象：`public."Y_codex_Layer3_Step30_Master_BS_Library"`

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| tech_norm | 制式_标准化 | text | 否 | 4G/5G | Step06.tech_norm | 透传（作为物理分桶维度） | 5G | 主键维度，决定 bs_id 派生规则 | `select tech_norm,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1;` |
| bs_id | 基站ID | bigint | 否 | >=0 | Step06.bs_id | 透传（已在 Step06 解析/派生） | 123456 | 基站索引主键 | `select count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" where bs_id is null;` |
| wuli_fentong_bs_key | 物理分桶基站键 | text | 否 | tech_norm\|bs_id\|lac_dec_final | Step30 拼接 | 字符串拼接：tech_norm、bs_id、lac_dec_final（分隔符为竖线 `|`） | 5G\|123456\|2097288 | 防止跨 LAC 错配污染中心点/共建 | `select count(*) as dup_cnt from (select wuli_fentong_bs_key,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1 having count(*)>1)t;` |
| lac_dec_final | 最终可信LAC | bigint | 否 | >0（且已可信） | Step06.lac_dec_final | 透传（Step06 已保证可信） | 2097288 | 物理分桶/风险控制维度 | `select count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" where lac_dec_final is null;` |
| shared_operator_cnt | 共建运营商数量 | int | 否 | >=1 | Step06.operator_id_raw | bucket 内 distinct operator 数 | 2 | 共建判定输入 | `select min(shared_operator_cnt),max(shared_operator_cnt) from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| shared_operator_list | 共建运营商列表 | text | 否 | 逗号分隔 | Step06.operator_id_raw | distinct + 排序 + 拼接 | 46001,46011 | 人类可读共建证据 | `select shared_operator_list,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1 order by 2 desc limit 20;` |
| is_multi_operator_shared | 是否多运营商共建/共用 | boolean | 否 | true/false | Step30 | `shared_operator_cnt>1` | true | 站级共建标记 | `select is_multi_operator_shared,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1;` |
| gps_valid_cell_cnt | 有效GPS的cell来源数 | int | 否 | >=0 | Step02 | Verified 点→按 cell 代表点聚合→计数 | 5 | GPS 可用性分级依据 | `select gps_valid_cell_cnt,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1 order by 2 desc limit 20;` |
| gps_valid_point_cnt | 有效GPS点行数 | bigint | 否 | >=0 | Step02 | Verified 点行数累加 | 12345 | 点量评估（辅助） | `select percentile_cont(0.5) within group (order by gps_valid_point_cnt) from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| gps_valid_level | GPS可用性分级 | text | 否 | Unusable/Risk/Usable | Step30 | `gps_valid_cell_cnt` 0/1/>1 分级 | Usable | 决定回填是否允许 | `select gps_valid_level,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1;` |
| bs_center_lon | 基站中心经度 | double precision | 是 | [-180,180] 且非(0,0) | Step02.lon | 中位/鲁棒中心点；Unusable 置空 | 116.39 | 回填目标经度 | `select count(*) filter (where gps_valid_level in ('Usable','Risk') and (bs_center_lon is null or bs_center_lat is null)) as center_null_cnt from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| bs_center_lat | 基站中心纬度 | double precision | 是 | [-90,90] 且非(0,0) | Step02.lat | 同上 | 39.90 | 回填目标纬度 | `select count(*) filter (where gps_valid_level in ('Usable','Risk') and (bs_center_lon=0 and bs_center_lat=0)) as center_zero_cnt from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| gps_p50_dist_m | 离散度P50(米) | double precision | 是 | >=0 | Step02.lon/lat | cell 代表点到中心点距离分位数 | 120.5 | 评估散度（辅助） | `select max(gps_p50_dist_m) from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| gps_p90_dist_m | 离散度P90(米) | double precision | 是 | >=0 | Step02.lon/lat | 同上 | 850.2 | 碰撞判定输入 | `select tech_norm,bs_id,wuli_fentong_bs_key,gps_p90_dist_m from public."Y_codex_Layer3_Step30_Master_BS_Library" order by gps_p90_dist_m desc nulls last limit 10;` |
| gps_max_dist_m | 离散度MAX(米) | double precision | 是 | >=0 | Step02.lon/lat | 同上 | 2500.0 | 极端离散度参考 | `select tech_norm,bs_id,wuli_fentong_bs_key,gps_max_dist_m from public."Y_codex_Layer3_Step30_Master_BS_Library" order by gps_max_dist_m desc nulls last limit 10;` |
| outlier_removed_cnt | 剔除异常cell数 | int | 否 | 0/1 | Step30 | N>=3 时最多剔 1 个最大偏移 cell | 1 | 鲁棒性解释字段 | `select outlier_removed_cnt,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1;` |
| is_collision_suspect | 是否碰撞疑似 | int | 否 | 0/1 | Step30 + Step05 | 多LAC哨兵命中或 P90 超阈 | 1 | 下游降权/排除依据 | `select count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" where is_collision_suspect=1;` |
| collision_reason | 碰撞疑似原因 | text | 是 | 多原因用 ; 分隔 | Step30 | 规则命中原因编码 | STEP05_MULTI_LAC_CELL | 人类解释碰撞来源 | `select collision_reason,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" where is_collision_suspect=1 group by 1 order by 2 desc;` |
| anomaly_cell_cnt | 多LAC哨兵命中cell数 | bigint | 否 | >=0 | Step05 | bucket 内命中多LAC哨兵的 distinct cell 数 | 12 | 风险规模刻画 | `select max(anomaly_cell_cnt) from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| first_seen_ts | 首次出现时间 | timestamp | 是 | - | Step06.ts_std | min(ts_std) | 2025-12-01 00:00 | 覆盖/稳定性画像 | `select min(first_seen_ts),max(last_seen_ts) from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| last_seen_ts | 最后出现时间 | timestamp | 是 | - | Step06.ts_std | max(ts_std) | 2025-12-07 23:59 | 覆盖/稳定性画像 | `select min(first_seen_ts),max(last_seen_ts) from public."Y_codex_Layer3_Step30_Master_BS_Library";` |
| active_days | 活跃天数 | int | 否 | >=1 | Step06.report_date | distinct report_date 计数 | 7 | 稳定性特征 | `select active_days,count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1 order by 2 desc limit 20;` |

---

## 2) Step30：GPS可用性分级分布统计

对象：`public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| tech_norm | 制式_标准化 | text | 否 | 4G/5G | Step30.tech_norm | 透传 | 5G | 统计切片维度 | `select tech_norm,count(*) from public."Y_codex_Layer3_Step30_Gps_Level_Stats" group by 1;` |
| operator_id_raw | 运营商id_细粒度 | text | 否 | 460xx | Step30.shared_operator_list 拆分 | `unnest(string_to_array(shared_operator_list, ','))` | 46000 | 统计切片维度 | `select operator_id_raw,count(*) from public."Y_codex_Layer3_Step30_Gps_Level_Stats" group by 1;` |
| gps_valid_level | GPS可用性分级 | text | 否 | Unusable/Risk/Usable | Step30.gps_valid_level | 透传 | Usable | 统计切片维度 | `select gps_valid_level,count(*) from public."Y_codex_Layer3_Step30_Gps_Level_Stats" group by 1;` |
| bs_cnt | 基站数 | bigint | 否 | >=0 | Step30 | count(*) | 12345 | 分布检查 | `select sum(bs_cnt) from public."Y_codex_Layer3_Step30_Gps_Level_Stats";` |
| bs_pct | 占比 | numeric | 否 | [0,1] | Step30 | bs_cnt / sum(bs_cnt) over(...) | 0.12345678 | 分布检查（快速判断） | `select min(bs_pct),max(bs_pct) from public."Y_codex_Layer3_Step30_Gps_Level_Stats";` |

---

## 3) Step31：明细 GPS 修正/补齐（可追溯）

对象：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| src_seq_id | 来源seq_id | bigint | 否 | - | Step06.seq_id | 追溯字段透传 | 123 | 回溯到原始行/复现 | `select count(*) filter (where src_seq_id is null) as null_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| src_record_id | 来源记录ID | text | 否 | - | Step06."记录id" | 追溯字段透传 | abc | 回溯到原始行/复现 | `select count(*) filter (where src_record_id is null) as null_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| operator_id_raw | 运营商id_细粒度 | text | 否 | 460xx | Step06.operator_id_raw | 透传 | 46000 | 分布切片/碰撞排查 | `select operator_id_raw,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1 order by 2 desc;` |
| operator_group_hint | 运营商组_提示 | text | 是 | CMCC/CUCC/CTCC/OTHER | Step06.operator_group_hint | 透传 | CMCC | 报表展示 | `select operator_group_hint,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1;` |
| tech_norm | 制式_标准化 | text | 否 | 4G/5G | Step06.tech_norm | 透传 | 5G | 分布切片 | `select tech_norm,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1;` |
| bs_id | 基站ID | bigint | 否 | >=0 | Step06.bs_id | 透传 | 123456 | 与 Step30 关联键 | `select count(*) filter (where bs_id is null) as null_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sector_id | 扇区ID | bigint | 是 | - | Step06.sector_id | 透传 | 12 | 画像维度（可选） | `select count(*) filter (where sector_id is null) as null_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| cell_id_dec | Cell十进制 | bigint | 否 | >0 | Step06.cell_id_dec | 透传 | 5815000012 | 小区索引 | `select count(*) filter (where cell_id_dec is null) as null_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| lac_dec_final | 最终可信LAC | bigint | 否 | >0 | Step06.lac_dec_final | 透传 | 2097288 | 物理分桶键组成 | `select count(*) filter (where lac_dec_final is null) as null_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| wuli_fentong_bs_key | 物理分桶基站键 | text | 否 | tech\|bs\|lac_final | Step31 拼接 | 字符串拼接：tech_norm、bs_id、lac_dec_final（分隔符为竖线 `|`） | 5G\|123456\|2097288 | 防止跨 LAC 错配回填 | `select count(*) filter (where wuli_fentong_bs_key is null) as null_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| gps_status | GPS状态_原始判定 | text | 否 | Verified/Missing/Drift | Step31 | has_gps + 距离阈值判断 | Drift | 判断是否需要纠偏/回填 | `select gps_status,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1;` |
| gps_status_final | GPS状态_修正后 | text | 否 | Verified/Missing | Step31 | 成功回填则 Verified | Verified | 下游使用的 GPS 状态 | `select count(*) as bad_cnt from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" where gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS') and gps_status_final<>'Verified';` |
| gps_source | GPS来源 | text | 否 | 见枚举字典 | Step31 | 根据 gps_valid_level 与中心点可用性决定 | Augmented_from_BS | 审计/解释回填来源 | `select gps_source,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1 order by 2 desc;` |
| is_from_risk_bs | 是否来自风险基站回填 | int | 否 | 0/1 | Step31 | gps_valid_level=Risk 则 1 | 1 | 风险规模评估 | `select count(*) filter (where is_from_risk_bs=1) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| gps_dist_to_bs_m | 原GPS到基站中心距离(米) | double precision | 是 | >=0 | Step31 | Haversine 距离 | 1800.5 | Drift 判定与排障 | `select max(gps_dist_to_bs_m) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| lon_raw | 原始经度 | double precision | 是 | [-180,180] | Step06.lon | 透传（用于对比） | 116.39 | 回填前后对比 | `select count(*) filter (where lon_raw=0 and lat_raw=0) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| lat_raw | 原始纬度 | double precision | 是 | [-90,90] | Step06.lat | 透传（用于对比） | 39.90 | 回填前后对比 | `select count(*) filter (where lon_raw=0 and lat_raw=0) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| lon_final | 最终经度 | double precision | 是 | [-180,180] | Step31 | Verified 不改；Missing/Drift 视条件回填中心点 | 116.39 | 下游画像/聚类使用 | `select count(*) filter (where gps_status_final='Verified' and (lon_final is null or lat_final is null)) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| lat_final | 最终纬度 | double precision | 是 | [-90,90] | Step31 | 同上 | 39.90 | 下游画像/聚类使用 | `select count(*) filter (where gps_status_final='Verified' and (lon_final is null or lat_final is null)) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| gps_valid_level | 基站GPS可用性分级 | text | 是 | Unusable/Risk/Usable | Step30.gps_valid_level | join Step30 后透传 | Usable | 解释回填可用性 | `select gps_valid_level,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1;` |
| is_collision_suspect | 是否碰撞疑似 | int | 是 | 0/1 | Step30.is_collision_suspect | join Step30 后透传 | 1 | 回填风险标记 | `select count(*) filter (where is_collision_suspect=1) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| is_multi_operator_shared | 是否多运营商共建/共用 | boolean | 是 | true/false | Step30.is_multi_operator_shared | join Step30 后透传 | true | 共建站标记 | `select is_multi_operator_shared,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1;` |
| shared_operator_list | 共建运营商列表 | text | 是 | 逗号分隔 | Step30.shared_operator_list | join Step30 后透传 | 46001,46011 | 共建证据 | `select shared_operator_list,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1 order by 2 desc limit 20;` |
| shared_operator_cnt | 共建运营商数量 | int | 是 | >=1 | Step30.shared_operator_cnt | join Step30 后透传 | 2 | 共建规模 | `select shared_operator_cnt,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1 order by 2 desc;` |
| ts_std | 报文时间 | timestamp | 是 | - | Step06.ts_std | 透传 | 2025-12-01 12:00:00 | 按时间切片/最近时间补齐 | `select min(ts_std),max(ts_std) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| report_date | 上报日期 | date | 是 | - | Step06.report_date | 透传 | 2025-12-01 | 按天分布 | `select report_date,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1 order by 1;` |
| sig_rsrp | RSRP | int | 是 | - | Step06.sig_rsrp | 信号字段透传 | -95 | Step33 补齐输入 | `select count(*) filter (where sig_rsrp is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sig_rsrq | RSRQ | int | 是 | - | Step06.sig_rsrq | 透传 | -10 | Step33 补齐输入 | `select count(*) filter (where sig_rsrq is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sig_sinr | SINR | int | 是 | - | Step06.sig_sinr | 透传 | 12 | Step33 补齐输入 | `select count(*) filter (where sig_sinr is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sig_rssi | RSSI | int | 是 | - | Step06.sig_rssi | 透传 | -70 | Step33 补齐输入 | `select count(*) filter (where sig_rssi is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sig_dbm | DBM | int | 是 | - | Step06.sig_dbm | 透传 | -65 | Step33 补齐输入 | `select count(*) filter (where sig_dbm is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sig_asu_level | ASU Level | int | 是 | - | Step06.sig_asu_level | 透传 | 3 | Step33 补齐输入 | `select count(*) filter (where sig_asu_level is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sig_level | Level | int | 是 | - | Step06.sig_level | 透传 | 3 | Step33 补齐输入 | `select count(*) filter (where sig_level is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sig_ss | SS | int | 是 | - | Step06.sig_ss | 透传 | -63 | Step33 补齐输入 | `select count(*) filter (where sig_ss is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| parsed_from | 解析来源 | text | 是 | - | Step06.parsed_from | 透传 | cell_info | 解析策略追溯 | `select parsed_from,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1 order by 2 desc limit 20;` |
| match_status | 匹配状态 | text | 是 | - | Step06.match_status | 透传 | ok | 解析质量追溯 | `select match_status,count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed" group by 1 order by 2 desc limit 20;` |
| 数据来源 | 数据来源 | text | 是 | - | Step06."数据来源" | 透传 | xxx | 溯源/排障 | `select count(*) filter (where "数据来源" is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| 北京来源 | 北京来源 | text | 是 | - | Step06."北京来源" | 透传 | xxx | 溯源/排障 | `select count(*) filter (where "北京来源" is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| did | 设备ID(did) | text | 是 | - | Step06.did | 透传 | xxx | 设备级分析（可选） | `select count(*) filter (where did is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| ip | IP | text | 是 | - | Step06.ip | 透传 | 1.2.3.4 | 画像字段（可选） | `select count(*) filter (where ip is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| sdk_ver | SDK版本 | text | 是 | - | Step06.sdk_ver | 透传 | 3.1.0 | 画像字段（可选） | `select count(*) filter (where sdk_ver is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| brand | 品牌 | text | 是 | - | Step06.brand | 透传 | HUAWEI | 画像字段（可选） | `select count(*) filter (where brand is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| model | 机型 | text | 是 | - | Step06.model | 透传 | P60 | 画像字段（可选） | `select count(*) filter (where model is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |
| oaid | OAID | text | 是 | - | Step06.oaid | 透传 | xxx | 画像字段（可选） | `select count(*) filter (where oaid is null) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";` |

---

## 4) Step32：对比报表（Raw）

对象：`public."Y_codex_Layer3_Step32_Compare_Raw"`

说明：该表用于排障/复核；人类验收优先看 v2 指标表（下一节）。

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| report_section | 报表分区 | text | 否 | GPS_GAIN/BS_RISK | Step32 | 透传 | GPS_GAIN | 区分收益/风险口径 | `select report_section,count(*) from public."Y_codex_Layer3_Step32_Compare_Raw" group by 1;` |
| operator_id_raw | 运营商id_细粒度 | text | 否 | 460xx | Step31/Step30 | GPS_GAIN：来自 Step31；BS_RISK：拆 shared_operator_list | 46000 | 按运营商切片 | `select operator_id_raw,count(*) from public."Y_codex_Layer3_Step32_Compare_Raw" group by 1 order by 2 desc;` |
| tech_norm | 制式_标准化 | text | 否 | 4G/5G | Step31/Step30 | GPS_GAIN/BS_RISK 均按 tech 切片 | 5G | 按制式切片 | `select tech_norm,count(*) from public."Y_codex_Layer3_Step32_Compare_Raw" group by 1;` |
| report_date | 上报日期 | date | 是 | - | Step31.report_date | GPS_GAIN：按天；BS_RISK：为空 | 2025-12-01 | 日级收益对比 | `select count(*) filter (where report_section='BS_RISK' and report_date is not null) from public."Y_codex_Layer3_Step32_Compare_Raw";` |
| row_cnt | 行数 | bigint | 是 | >=0 | Step31 | GPS_GAIN 明细行数 | 123456 | 收益口径基数 | `select sum(row_cnt) from public."Y_codex_Layer3_Step32_Compare_Raw" where report_section='GPS_GAIN';` |
| missing_cnt_before | Missing数_修正前 | bigint | 是 | >=0 | Step31 | gps_status=Missing 计数 | 1000 | 收益拆解 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where missing_cnt_before<0 limit 1;` |
| drift_cnt_before | Drift数_修正前 | bigint | 是 | >=0 | Step31 | gps_status=Drift 计数 | 200 | 收益拆解 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where drift_cnt_before<0 limit 1;` |
| verified_cnt_before | Verified数_修正前 | bigint | 是 | >=0 | Step31 | gps_status=Verified 计数 | 120000 | 基线规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where verified_cnt_before<0 limit 1;` |
| missing_to_filled_cnt | Missing→Filled数 | bigint | 是 | >=0 | Step31 | Missing 且 final Verified 计数 | 800 | 回填收益 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where missing_to_filled_cnt>missing_cnt_before limit 1;` |
| drift_to_corrected_cnt | Drift→Corrected数 | bigint | 是 | >=0 | Step31 | Drift 且 final Verified 计数 | 150 | 纠偏收益 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where drift_to_corrected_cnt>drift_cnt_before limit 1;` |
| has_gps_before_cnt | 有GPS数_修正前 | bigint | 是 | >=0 | Step31 | Verified+Drift 计数 | 120200 | 口径对齐 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where has_gps_before_cnt<0 limit 1;` |
| has_gps_after_cnt | 有GPS数_修正后 | bigint | 是 | >=0 | Step31 | final Verified 计数 | 121000 | 核心收益 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where has_gps_after_cnt<has_gps_before_cnt limit 1;` |
| filled_from_usable_bs_cnt | 来自Usable基站回填数 | bigint | 是 | >=0 | Step31 | gps_source=Augmented_from_BS | 700 | 分来源解释 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where filled_from_usable_bs_cnt<0 limit 1;` |
| filled_from_risk_bs_cnt | 来自Risk基站回填数 | bigint | 是 | >=0 | Step31 | gps_source=Augmented_from_Risk_BS | 100 | 风险回填规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where filled_from_risk_bs_cnt<0 limit 1;` |
| not_filled_cnt | 未回填数 | bigint | 是 | >=0 | Step31 | gps_source=Not_Filled | 200 | 未覆盖尾巴规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where not_filled_cnt<0 limit 1;` |
| bs_cnt | 基站数 | bigint | 是 | >=0 | Step30 | BS_RISK：基站桶数 | 10000 | 风险口径基数 | `select sum(bs_cnt) from public."Y_codex_Layer3_Step32_Compare_Raw" where report_section='BS_RISK';` |
| unusable_bs_cnt | Unusable基站数 | bigint | 是 | >=0 | Step30 | gps_valid_level=Unusable | 2000 | 无法回填规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where unusable_bs_cnt>bs_cnt limit 1;` |
| risk_bs_cnt | Risk基站数 | bigint | 是 | >=0 | Step30 | gps_valid_level=Risk | 1500 | 风险回填规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where risk_bs_cnt>bs_cnt limit 1;` |
| usable_bs_cnt | Usable基站数 | bigint | 是 | >=0 | Step30 | gps_valid_level=Usable | 6500 | 可用基站规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where usable_bs_cnt>bs_cnt limit 1;` |
| collision_suspect_bs_cnt | 碰撞疑似基站数 | bigint | 是 | >=0 | Step30 | is_collision_suspect=1 | 200 | 碰撞规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where collision_suspect_bs_cnt>bs_cnt limit 1;` |
| multi_operator_shared_bs_cnt | 多运营共建基站数 | bigint | 是 | >=0 | Step30 | is_multi_operator_shared=true | 120 | 共建规模 | `select * from public."Y_codex_Layer3_Step32_Compare_Raw" where multi_operator_shared_bs_cnt>bs_cnt limit 1;` |

---

## 5) Step32：对比报表（v2 可读指标）

对象：`public."Y_codex_Layer3_Step32_Compare"`

说明：每行一条指标（metric row），直接用于生成 Step32 报告的“一眼拍板表”。

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| report_section | 报表分区 | text | 否 | GPS_GAIN/BS_RISK | Step32_Raw | 透传 | GPS_GAIN | 归类展示 | `select report_section,pass_flag,count(*) from public."Y_codex_Layer3_Step32_Compare" group by 1,2;` |
| operator_id_raw | 运营商id_细粒度 | text | 是 | 460xx | Step32_Raw | 部分指标可能为空（整体） | 46000 | 切片 | `select count(*) filter (where operator_id_raw is null) from public."Y_codex_Layer3_Step32_Compare";` |
| tech_norm | 制式_标准化 | text | 是 | 4G/5G | Step32_Raw | 部分指标可能为空（整体） | 5G | 切片 | `select count(*) filter (where tech_norm is null) from public."Y_codex_Layer3_Step32_Compare";` |
| report_date | 上报日期 | date | 是 | - | Step32_Raw | GPS_GAIN 指标按天；BS_RISK 指标为空 | 2025-12-01 | 日级收益趋势 | `select count(*) filter (where report_section='BS_RISK' and report_date is not null) from public."Y_codex_Layer3_Step32_Compare";` |
| metric_code | 指标编码 | text | 否 | 见枚举字典 | Step32 | 固定枚举 | HAS_GPS_AFTER | 程序化对齐报告 | `select metric_code,count(*) from public."Y_codex_Layer3_Step32_Compare" group by 1;` |
| metric_name_cn | 指标中文名 | text | 否 | - | Step32 | 人类可读中文名 | 修正后有GPS规模 | 人类阅读 | `select * from public."Y_codex_Layer3_Step32_Compare" order by report_section,metric_code limit 50;` |
| expected_rule_cn | 期望/规则（中文） | text | 否 | - | Step32 | 验收口径文本 | after>=before | 一眼判断 | `select * from public."Y_codex_Layer3_Step32_Compare" where pass_flag='FAIL';` |
| actual_value_num | 实际值（数值） | numeric | 否 | >=0 | Step32_Raw | 统一 numeric 输出 | 123456 | 对比/验收 | `select * from public."Y_codex_Layer3_Step32_Compare" order by actual_value_num desc nulls last limit 50;` |
| pass_flag | 结论 | text | 否 | PASS/FAIL/WARN | Step32 | 规则判定 | PASS | 快速拍板 | `select pass_flag,count(*) from public."Y_codex_Layer3_Step32_Compare" group by 1;` |
| remark_cn | 备注/建议（中文） | text | 是 | - | Step32 | WARN/FAIL 提示 | 检查 Step31 | 排障指引 | `select * from public."Y_codex_Layer3_Step32_Compare" where pass_flag<>'PASS' order by report_section,metric_code;` |

---

## 6) Step33：信号字段简单补齐（摸底版）

对象：`public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`

说明：本轮仅做“摸底 + 简单补齐”，不追求最优；输出 final 字段 + 缺失计数 + 来源。

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| src_seq_id | 来源seq_id | bigint | 否 | - | Step31.src_seq_id | 追溯字段透传 | 123 | 回溯 | `select count(*) filter (where src_seq_id is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| src_record_id | 来源记录ID | text | 否 | - | Step31.src_record_id | 追溯字段透传 | abc | 回溯 | `select count(*) filter (where src_record_id is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| operator_id_raw | 运营商id_细粒度 | text | 否 | 460xx | Step31.operator_id_raw | 透传 | 46000 | 分布切片 | `select operator_id_raw,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1 order by 2 desc;` |
| operator_group_hint | 运营商组_提示 | text | 是 | CMCC/CUCC/CTCC/OTHER | Step31.operator_group_hint | 透传 | CMCC | 报表展示 | `select operator_group_hint,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1;` |
| tech_norm | 制式_标准化 | text | 否 | 4G/5G | Step31.tech_norm | 透传 | 5G | 切片 | `select tech_norm,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1;` |
| bs_id | 基站ID | bigint | 否 | >=0 | Step31.bs_id | 透传 | 123456 | bs 画像/回退补齐 | `select count(*) filter (where bs_id is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sector_id | 扇区ID | bigint | 是 | - | Step31.sector_id | 透传 | 12 | 可选维度 | `select count(*) filter (where sector_id is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| cell_id_dec | Cell十进制 | bigint | 否 | >0 | Step31.cell_id_dec | 透传 | 5815000012 | cell 画像补齐键 | `select count(*) filter (where cell_id_dec is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| lac_dec_final | 最终可信LAC | bigint | 否 | >0 | Step31.lac_dec_final | 透传 | 2097288 | 分桶/防错配 | `select count(*) filter (where lac_dec_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| wuli_fentong_bs_key | 物理分桶基站键 | text | 否 | tech\|bs\|lac_final | Step31.wuli_fentong_bs_key | 透传 | 5G\|123456\|2097288 | bs 画像补齐键 | `select count(*) filter (where wuli_fentong_bs_key is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| report_date | 上报日期 | date | 是 | - | Step31.report_date | 透传 | 2025-12-01 | 切片 | `select report_date,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1 order by 1;` |
| ts_std | 报文时间 | timestamp | 是 | - | Step31.ts_std | 透传 | 2025-12-01 12:00:00 | 后续“最近时间补齐”准备 | `select min(ts_std),max(ts_std) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| gps_status | GPS状态_原始判定 | text | 否 | Verified/Missing/Drift | Step31.gps_status | 透传 | Drift | 排障维度 | `select gps_status,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1;` |
| gps_status_final | GPS状态_修正后 | text | 否 | Verified/Missing | Step31.gps_status_final | 透传 | Verified | 排障维度 | `select gps_status_final,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1;` |
| gps_source | GPS来源 | text | 否 | 见枚举字典 | Step31.gps_source | 透传 | Augmented_from_BS | 排障维度 | `select gps_source,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1 order by 2 desc;` |
| is_from_risk_bs | 是否来自风险基站回填 | int | 否 | 0/1 | Step31.is_from_risk_bs | 透传 | 1 | 风险切片 | `select count(*) filter (where is_from_risk_bs=1) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| lon_final | 最终经度 | double precision | 是 | [-180,180] | Step31.lon_final | 透传 | 116.39 | 下游定位 | `select count(*) filter (where lon_final is null or lat_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| lat_final | 最终纬度 | double precision | 是 | [-90,90] | Step31.lat_final | 透传 | 39.90 | 下游定位 | `select count(*) filter (where lon_final is null or lat_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| signal_fill_source | 信号补齐来源 | text | 否 | none/cell_agg/bs_agg | Step33 | 依据是否用到 cell/bs 聚合值 | cell_agg | 解释补齐来源 | `select signal_fill_source,count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1 order by 2 desc;` |
| signal_missing_before_cnt | 补齐前缺失字段数 | int | 否 | 0~8 | Step33 | 8 个信号字段缺失数之和 | 6 | 缺失摸底 | `select max(signal_missing_before_cnt) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| signal_missing_after_cnt | 补齐后缺失字段数 | int | 否 | 0~8 | Step33 | 同上（after） | 2 | 补齐收益验证 | `select count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" where signal_missing_after_cnt>signal_missing_before_cnt;` |
| sig_rsrp_final | 最终RSRP | int | 是 | - | Step31 + 聚合画像 | raw > cell_agg > bs_agg | -95 | 下游使用字段 | `select count(*) filter (where sig_rsrp_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sig_rsrq_final | 最终RSRQ | int | 是 | - | 同上 | 同上 | -10 | 下游使用字段 | `select count(*) filter (where sig_rsrq_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sig_sinr_final | 最终SINR | int | 是 | - | 同上 | 同上 | 12 | 下游使用字段 | `select count(*) filter (where sig_sinr_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sig_rssi_final | 最终RSSI | int | 是 | - | 同上 | 同上 | -70 | 下游使用字段 | `select count(*) filter (where sig_rssi_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sig_dbm_final | 最终DBM | int | 是 | - | 同上 | 同上 | -65 | 下游使用字段 | `select count(*) filter (where sig_dbm_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sig_asu_level_final | 最终ASU Level | int | 是 | - | 同上 | 同上 | 3 | 下游使用字段 | `select count(*) filter (where sig_asu_level_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sig_level_final | 最终Level | int | 是 | - | 同上 | 同上 | 3 | 下游使用字段 | `select count(*) filter (where sig_level_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |
| sig_ss_final | 最终SS | int | 是 | - | 同上 | 同上 | -63 | 下游使用字段 | `select count(*) filter (where sig_ss_final is null) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";` |

---

## 7) Step34：信号补齐摸底报表（Raw）

对象：`public."Y_codex_Layer3_Step34_Signal_Compare_Raw"`

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| report_section | 报表分区 | text | 否 | BY_DIM/OVERALL | Step34 | 透传 | BY_DIM | 区分维度统计/整体 | `select report_section,count(*) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw" group by 1;` |
| operator_id_raw | 运营商id_细粒度 | text | 是 | 460xx | Step33.operator_id_raw | BY_DIM 有值；OVERALL 为空 | 46000 | 切片 | `select count(*) filter (where report_section='OVERALL' and operator_id_raw is not null) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw";` |
| tech_norm | 制式_标准化 | text | 是 | 4G/5G | Step33.tech_norm | BY_DIM 有值；OVERALL 为空 | 5G | 切片 | `select count(*) filter (where report_section='OVERALL' and tech_norm is not null) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw";` |
| report_date | 上报日期 | date | 是 | - | Step33.report_date | BY_DIM 有值；OVERALL 为空 | 2025-12-01 | 日级摸底 | `select count(*) filter (where report_section='OVERALL' and report_date is not null) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw";` |
| signal_fill_source | 信号补齐来源 | text | 否 | none/cell_agg/bs_agg | Step33.signal_fill_source | 透传 | cell_agg | 按来源拆分收益 | `select signal_fill_source,count(*) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw" group by 1;` |
| row_cnt | 行数 | bigint | 否 | >=0 | Step33 | count(*) | 123456 | 维度下样本量 | `select sum(row_cnt) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw" where report_section='BY_DIM';` |
| avg_missing_before | 平均缺失字段数_补齐前 | numeric(18,6) | 否 | >=0 | Step33 | avg(signal_missing_before_cnt) | 5.123456 | 缺失程度 | `select max(avg_missing_before) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw";` |
| avg_missing_after | 平均缺失字段数_补齐后 | numeric(18,6) | 否 | >=0 | Step33 | avg(signal_missing_after_cnt) | 2.000000 | 补齐后缺失程度 | `select count(*) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw" where avg_missing_after>avg_missing_before;` |
| sum_missing_before | 缺失字段总量_补齐前 | bigint | 否 | >=0 | Step33 | sum(signal_missing_before_cnt) | 999999 | 缺失规模 | `select max(sum_missing_before) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw";` |
| sum_missing_after | 缺失字段总量_补齐后 | bigint | 否 | >=0 | Step33 | sum(signal_missing_after_cnt) | 888888 | 补齐后缺失规模 | `select count(*) from public."Y_codex_Layer3_Step34_Signal_Compare_Raw" where sum_missing_after>sum_missing_before;` |

---

## 8) Step34：信号补齐对比（v2 可读指标）

对象：`public."Y_codex_Layer3_Step34_Signal_Compare"`

说明：每行一条指标（metric row），对比 before/after 缺失量，并给出 PASS/FAIL。

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
|---|---|---:|:---:|---|---|---|---|---|---|
| report_section | 报表分区 | text | 否 | BY_DIM/OVERALL | Step34_Raw | 透传 | OVERALL | 分组展示 | `select report_section,pass_flag,count(*) from public."Y_codex_Layer3_Step34_Signal_Compare" group by 1,2;` |
| operator_id_raw | 运营商id_细粒度 | text | 是 | 460xx | Step34_Raw | BY_DIM 有值；OVERALL 为空 | 46000 | 切片 | `select count(*) filter (where report_section='OVERALL' and operator_id_raw is not null) from public."Y_codex_Layer3_Step34_Signal_Compare";` |
| tech_norm | 制式_标准化 | text | 是 | 4G/5G | Step34_Raw | 同上 | 5G | 切片 | `select count(*) filter (where report_section='OVERALL' and tech_norm is not null) from public."Y_codex_Layer3_Step34_Signal_Compare";` |
| report_date | 上报日期 | date | 是 | - | Step34_Raw | 同上 | 2025-12-01 | 按天评估 | `select count(*) filter (where report_section='OVERALL' and report_date is not null) from public."Y_codex_Layer3_Step34_Signal_Compare";` |
| signal_fill_source | 信号补齐来源 | text | 否 | none/cell_agg/bs_agg | Step34_Raw | 透传 | cell_agg | 分来源评估 | `select signal_fill_source,count(*) from public."Y_codex_Layer3_Step34_Signal_Compare" group by 1;` |
| metric_code | 指标编码 | text | 否 | 见枚举字典 | Step34 | 固定枚举 | SUM_MISSING_AFTER | 程序化对齐报告 | `select metric_code,count(*) from public."Y_codex_Layer3_Step34_Signal_Compare" group by 1;` |
| metric_name_cn | 指标中文名 | text | 否 | - | Step34 | 中文指标名 | 补齐后缺失字段总量 | 人类读 | `select * from public."Y_codex_Layer3_Step34_Signal_Compare" order by report_section,signal_fill_source,metric_code limit 50;` |
| expected_rule_cn | 期望/规则（中文） | text | 否 | - | Step34 | 规则文本 | after<=before | 一眼判断 | `select * from public."Y_codex_Layer3_Step34_Signal_Compare" where pass_flag='FAIL';` |
| actual_value_num | 实际值（数值） | numeric | 否 | >=0 | Step34_Raw | 统一 numeric 输出 | 123456 | 对比/验收 | `select * from public."Y_codex_Layer3_Step34_Signal_Compare" order by actual_value_num desc nulls last limit 50;` |
| pass_flag | 结论 | text | 否 | PASS/FAIL | Step34 | 按规则判定 | PASS | 一眼拍板 | `select pass_flag,count(*) from public."Y_codex_Layer3_Step34_Signal_Compare" group by 1;` |
| remark_cn | 备注/建议（中文） | text | 是 | - | Step34 | 可选建议 | 检查 Step33 | 指导下一步 | `select * from public."Y_codex_Layer3_Step34_Signal_Compare" where pass_flag='FAIL';` |
