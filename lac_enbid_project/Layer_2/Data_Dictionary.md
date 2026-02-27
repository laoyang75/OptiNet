# Layer_2 字段字典（Data Dictionary）

约定：字段展示统一采用 **中文（English）** 的写法；SQL 中实际列名以 English 为主（便于查询），必要时保留 Layer_0 的中文列名（如 `"运营商id"`、`"原始lac"`）。

---

## 0. Layer_0 输入表（仅列出 Layer_2 关键字段）

输入表：

- `public."Y_codex_Layer0_Gps_base"`
- `public."Y_codex_Layer0_Lac"`

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 顺序ID（seq_id） | `seq_id` | bigint | 报文流顺序；可作为行级主键候选 |
| 记录ID（record_id） | `"记录id"` | varchar | 原始记录唯一标识（文本） |
| 制式（tech） | `tech` | text | 原始解析制式（常见 `4G/5G`，也可能有 `2G/3G/NULL`） |
| 运营商ID（operator_id） | `"运营商id"` | text | 原始运营商标识（PLMN） |
| 原始LAC（lac_raw） | `"原始lac"` | text | 原始 LAC（文本） |
| LAC十进制（lac_dec） | `lac_dec` | bigint | LAC 十进制（数值合规则非空） |
| Cell原始（cell_id_raw） | `cell_id` | text | 原始 cell_id（文本） |
| Cell十进制（cell_id_dec） | `cell_id_dec` | bigint | cell_id 十进制（数值合规则非空） |
| 报文时间（ts_std） | `ts_std` | timestamp | 墙钟时间标准化（用于 report_date） |
| 解析来源（parsed_from） | `parsed_from` | text | `cell_infos` / `ss1` |
| 设备DID（did） | `did` | varchar | 设备标识（优先用于 device_id） |
| 设备OAID（oaid） | `oaid` | varchar | 设备标识（did 空则使用） |
| 经度（lon） | `lon` | double precision | 最终经度（可能为空/异常） |
| 纬度（lat） | `lat` | double precision | 最终纬度（可能为空/异常） |

---

## 1. Step00：标准化视图派生字段（Y_codex_Layer2_Step00_*_Std）

对象：

- `public."Y_codex_Layer2_Step00_Gps_Std"`
- `public."Y_codex_Layer2_Step00_Lac_Std"`

| 中文（English） | 列名 | 类型 | 生成逻辑（摘要） |
|---|---|---|---|
| 制式_标准化（tech_norm） | `tech_norm` | text | `4G/5G/2_3G/其他`（由 `tech` 映射） |
| 运营商id_细粒度（operator_id_raw） | `operator_id_raw` | text | `NULLIF(trim("运营商id"),'')` |
| 运营商组_提示（operator_group_hint） | `operator_group_hint` | text | `46000/46015/46020→CMCC`；`46001→CUCC`；`46011→CTCC`；其他→OTHER |
| 上报日期（report_date） | `report_date` | date | `date(ts_std)` |
| 设备ID（device_id） | `device_id` | text | `coalesce(trim(did), trim(oaid))` |
| lac长度（lac_len） | `lac_len` | int | `length(trim("原始lac"))`（空则 NULL） |
| cell长度（cell_len） | `cell_len` | int | `length(trim(cell_id))`（空则 NULL） |
| 是否有cell（has_cellid） | `has_cellid` | boolean | `cell_id_dec is not null` |
| 是否有lac（has_lac） | `has_lac` | boolean | `lac_dec is not null` |
| 是否有gps（has_gps） | `has_gps` | boolean | `lon/lat` 非空且落在经纬度合法范围且不为 (0,0) |

tech_norm 枚举：

- `4G`：LTE
- `5G`：NR
- `2_3G`：2G/3G
- `其他`：NULL/未知/异常值

---

## 2. Step01：基础统计报表字段（Y_codex_Layer2_Step01_BaseStats_*）

对象：

- `public."Y_codex_Layer2_Step01_BaseStats_Raw"`
- `public."Y_codex_Layer2_Step01_BaseStats_ValidCell"`

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 制式_标准化（tech_norm） | `tech_norm` | text | 聚合维度 |
| 运营商id_细粒度（operator_id_raw） | `operator_id_raw` | text | 聚合维度 |
| 运营商组_提示（operator_group_hint） | `operator_group_hint` | text | 聚合维度 |
| 解析来源（parsed_from） | `parsed_from` | text | 聚合维度 |
| 行数（row_cnt） | `row_cnt` | bigint | 记录行数 |
| 行占比（row_pct） | `row_pct` | numeric | `row_cnt / sum(row_cnt)` |
| 去重小区数（cell_cnt） | `cell_cnt` | bigint | `count(distinct cell_id_dec)`（排除 NULL） |
| 去重LAC数（lac_cnt） | `lac_cnt` | bigint | `count(distinct lac_dec)`（排除 NULL） |
| 设备数（device_cnt） | `device_cnt` | bigint | `count(distinct device_id)`（排除 NULL） |
| 无cell行数（no_cellid_rows） | `no_cellid_rows` | bigint | `count(*) where has_cellid=false` |
| 无lac行数（no_lac_rows） | `no_lac_rows` | bigint | `count(*) where has_lac=false` |
| 无gps行数（no_gps_rows） | `no_gps_rows` | bigint | `count(*) where has_gps=false` |
| 无cell占比（no_cellid_pct） | `no_cellid_pct` | numeric | `no_cellid_rows/row_cnt` |
| 无lac占比（no_lac_pct） | `no_lac_pct` | numeric | `no_lac_rows/row_cnt` |
| 无gps占比（no_gps_pct） | `no_gps_pct` | numeric | `no_gps_rows/row_cnt` |

---

## 3. Step02：合规标记字段（Y_codex_Layer2_Step02_Gps_Compliance_Marked）

对象：`public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| LAC十六进制位数（lac_hex_len） | `lac_hex_len` | int | `char_length(to_hex(lac_dec))`（lac_dec>0 时） |
| LAC十六进制位数合规（is_lac_hex_len_ok） | `is_lac_hex_len_ok` | boolean | 移动系 `hex_len∈{4,6}`；联通/电信 `hex_len∈[4,6]` |
| Cell最大允许值（cell_id_max_allowed） | `cell_id_max_allowed` | bigint | 4G:268435455（28-bit ECI）；5G:68719476735（36-bit NCI） |
| Cell范围合规（is_cell_range_ok） | `is_cell_range_ok` | boolean | 4G `cell_id_dec∈[1,268435455]`；5G `cell_id_dec∈[1,68719476735]` |
| 是否L1_LAC合规（is_l1_lac_ok） | `is_l1_lac_ok` | boolean | 运营商∈5PLMN + `tech_norm∈{4G,5G}` + `lac_dec>0` + 非溢出/占位值 + `is_lac_hex_len_ok` |
| 是否L1_CELL合规（is_l1_cell_ok） | `is_l1_cell_ok` | boolean | 在 LAC 合规基础上，`cell_id_dec>0` + `!=2147483647` + `is_cell_range_ok` |
| 是否合规（is_compliant） | `is_compliant` | boolean | 当前口径：`is_l1_cell_ok`（行级绝对合规） |
| 不合规原因（non_compliant_reason） | `non_compliant_reason` | text | 多原因用 `;` 拼接（便于 TopN） |

常用原因枚举（可扩展）：

- `OPERATOR_OUT_OF_SCOPE`
- `TECH_NOT_4G_5G`
- `LAC_INVALID`
- `LAC_OVERFLOW_SENTINEL`
- `LAC_HEXLEN_NOT_4_OR_6_FOR_CMCC`
- `LAC_HEXLEN_NOT_4_TO_6_FOR_CU_CT`
- `LAC_HEXLEN_RULE_NO_MATCH`
- `CELLID_NULL_OR_NONNUMERIC`
- `CELLID_NONPOSITIVE`
- `CELLID_OVERFLOW_2147483647`
- `CELLID_OUT_OF_RANGE_4G`
- `CELLID_OUT_OF_RANGE_5G`

---

## 4. Step03：有效 LAC 汇总库字段（Y_codex_Layer2_Step03_Lac_Stats_DB）

对象：`public."Y_codex_Layer2_Step03_Lac_Stats_DB"`

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 运营商id_细粒度（operator_id_raw） | `operator_id_raw` | text | 主键维度 |
| 运营商组_提示（operator_group_hint） | `operator_group_hint` | text | 透传（报表视角） |
| 制式_标准化（tech_norm） | `tech_norm` | text | 主键维度 |
| LAC十进制（lac_dec） | `lac_dec` | bigint | 主键维度 |
| 总上报次数（record_count） | `record_count` | bigint | `count(*)` |
| 有效GPS次数（valid_gps_count） | `valid_gps_count` | bigint | `count(*) where has_gps=true` |
| 关联小区数（distinct_cellid_count） | `distinct_cellid_count` | bigint | `count(distinct cell_id_dec)` |
| 关联设备数（distinct_device_count） | `distinct_device_count` | bigint | `count(distinct device_id)` |
| 首次出现时间（first_seen_ts） | `first_seen_ts` | timestamp | `min(ts_std)` |
| 最后出现时间（last_seen_ts） | `last_seen_ts` | timestamp | `max(ts_std)` |
| 首次出现日期（first_seen_date） | `first_seen_date` | date | `min(report_date)` |
| 最后出现日期（last_seen_date） | `last_seen_date` | date | `max(report_date)` |
| 活跃天数（active_days） | `active_days` | int | `count(distinct report_date)` |

---

## 5. Step04：可信 LAC 库字段（Y_codex_Layer2_Step04_Master_Lac_Lib）

对象：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 是否可信LAC（is_trusted_lac） | `is_trusted_lac` | boolean | 当前版恒为 true（已按规则筛选） |
| 其余字段 |  |  | 透传 Step3 全字段 |

---

## 6. Step05：可信映射统计底座字段（Y_codex_Layer2_Step05_CellId_Stats_DB）

对象：`public."Y_codex_Layer2_Step05_CellId_Stats_DB"`

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 运营商id_细粒度（operator_id_raw） | `operator_id_raw` | text | 主键维度 |
| 运营商组_提示（operator_group_hint） | `operator_group_hint` | text | 透传（报表视角） |
| 制式_标准化（tech_norm） | `tech_norm` | text | 主键维度 |
| LAC十进制（lac_dec） | `lac_dec` | bigint | 主键维度 |
| Cell十进制（cell_id_dec） | `cell_id_dec` | bigint | 主键维度 |
| 总上报次数（record_count） | `record_count` | bigint | `count(*)` |
| 有效GPS次数（valid_gps_count） | `valid_gps_count` | bigint | `count(*) where has_gps=true` |
| 首次/末次时间（first/last_seen_ts） | `first_seen_ts/last_seen_ts` | timestamp | `min/max(ts_std)` |
| 首次/末次日期（first/last_seen_date） | `first_seen_date/last_seen_date` | date | `min/max(report_date)` |
| 活跃天数（active_days） | `active_days` | int | `count(distinct report_date)` |
| 关联设备数（distinct_device_count） | `distinct_device_count` | bigint | `count(distinct device_id)` |
| GPS中心点（gps_center_lon/gps_center_lat） | `gps_center_lon/gps_center_lat` | double precision | 当前版：对 has_gps=true 的 `avg(lon/lat)`（可后续升级为中位数） |

---

## 7. Step05：异常监测清单报表字段（Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac）

对象：`public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 运营商id_细粒度（operator_id_raw） | `operator_id_raw` | text | 粒度维度 |
| 运营商组_提示（operator_group_hint） | `operator_group_hint` | text | 透传（可选） |
| 制式_标准化（tech_norm） | `tech_norm` | text | 粒度维度 |
| Cell十进制（cell_id_dec） | `cell_id_dec` | bigint | 粒度维度 |
| 关联LAC去重数（lac_distinct_cnt） | `lac_distinct_cnt` | int | `count(distinct lac_dec)` |
| LAC列表（lac_list） | `lac_list` | text | `array_to_string(array_agg(distinct lac_dec order by lac_dec),',')` |
| 总上报次数（record_count） | `record_count` | bigint | `count(*)` |
| 首次/末次时间（first/last_seen_ts） | `first_seen_ts/last_seen_ts` | timestamp | `min/max(ts_std)` |

筛选规则：`lac_distinct_cnt > 1`。

---

## 8. Step6：反哺与对比报表字段

对象：

- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`：LAC 路反哺后可信明细（行级，继承 Step00 LAC 标准化视图字段 + 派生列）
- `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`：对比报表

说明：`public."Y_codex_Layer2_Step06_L0_Lac_Filtered"` 当前脚本默认 **落表（TABLE）**，便于后续评估与复用（而不是 VIEW）。

`Y_codex_Layer2_Step06_L0_Lac_Filtered` 关键派生字段（其余字段同 Step00 LAC 标准化视图）：

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 映射候选数（lac_choice_cnt） | `lac_choice_cnt` | bigint | 同一 `(operator,tech,cell)` 命中 lac 的候选数；>1 视为不唯一，本步骤不回填 |
| 映射LAC（lac_dec_from_map） | `lac_dec_from_map` | bigint | 映射得到的 lac（仅在 `lac_choice_cnt=1` 时有值） |
| 最终LAC（lac_dec_final） | `lac_dec_final` | bigint | 最终用于反哺的可信 lac（保证命中 Step04 白名单） |
| 原始是否可信（is_original_lac_trusted） | `is_original_lac_trusted` | boolean | 原始 `lac_dec` 是否在 Step04 白名单内 |
| 最终是否可信（is_final_lac_trusted） | `is_final_lac_trusted` | boolean | 最终 `lac_dec_final` 是否在 Step04 白名单内（视图已强制为 true） |
| 是否发生变化（is_lac_changed_by_mapping） | `is_lac_changed_by_mapping` | boolean | 原始 `lac_dec` 与 `lac_dec_final` 是否不同（补齐/纠偏发生） |
| 反哺状态（lac_enrich_status） | `lac_enrich_status` | text | KEEP_TRUSTED_LAC / BACKFILL_NULL_LAC / REPLACE_UNTRUSTED_LAC / ... |

`Y_codex_Layer2_Step06_GpsVsLac_Compare` 字段：

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 数据集（dataset） | `dataset` | text | `GPS_RAW / GPS_COMPLIANT / LAC_RAW / LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL / LAC_SUPPLEMENTED_TRUSTED / LAC_SUPPLEMENTED_BACKFILLED / LAC_RAW_HAS_CELL_NO_OPERATOR` |
| 制式_标准化（tech_norm） | `tech_norm` | text | 聚合维度 |
| 运营商id_细粒度（operator_id_raw） | `operator_id_raw` | text | 聚合维度 |
| 运营商组_提示（operator_group_hint） | `operator_group_hint` | text | 聚合维度 |
| 行数（row_cnt） | `row_cnt` | bigint | `count(*)` |
| 去重cell数（cell_cnt） | `cell_cnt` | bigint | `count(distinct cell_id_dec)` |
| 去重lac数（lac_cnt） | `lac_cnt` | bigint | `count(distinct lac_dec)` 或（对反哺数据集）`count(distinct lac_dec_final)` |
| 设备数（device_cnt） | `device_cnt` | bigint | `count(distinct device_id)` |

---

## 9. 未来接口预埋：字段结构（不在本轮实现）

### 9.1 Cleaned_Augmented_DB

建议对象名：`public.cleaned_augmented_db`（示例）

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 来源seq_id（src_seq_id） | `src_seq_id` | bigint | 回溯到 Layer_0 明细 |
| 来源记录ID（src_record_id） | `src_record_id` | text | 回溯到原始记录 |
| 处理状态（status） | `status` | text | Verified / Corrected_LAC / New_CellID_Candidate / Unverified_Omitted |
| 原始LAC（original_lac） | `original_lac` | bigint | 原始 lac_dec |
| 修正LAC（corrected_lac） | `corrected_lac` | bigint | 纠偏后的 lac_dec |
| GPS状态（gps_status） | `gps_status` | text | Verified / Drift / Missing |
| 数据来源（data_source） | `data_source` | text | APP / SS1 / ThirdParty / ... |
| GPS来源（gps_source） | `gps_source` | text | Original / Augmented_from_BS |

### 9.2 Master_BS_Library

建议对象名：`public.master_bs_library`（示例）

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| 基站ID（bs_id） | `bs_id` | bigint | eNodeB/gNodeB |
| 扇区ID（sector_id） | `sector_id` | bigint | 扇区 |
| 基站中心经度（bs_gps_center_lon） | `bs_gps_center_lon` | double precision | Verified GPS 聚合 |
| 基站中心纬度（bs_gps_center_lat） | `bs_gps_center_lat` | double precision | Verified GPS 聚合 |
| 关联LAC（associated_lac_list） | `associated_lac_list` | text | 关联 LAC 列表 |
| 小区数（cellid_count） | `cellid_count` | int | 关联 cell 数 |

### 9.3 Final_Master_DB

建议对象名：`public.final_master_db`（示例）

| 中文（English） | 列名 | 类型 | 说明 |
|---|---|---|---|
| GPS回填标记（gps_source） | `gps_source` | text | Original_Verified / Augmented_from_BS / ... |
| 其余字段 |  |  | 继承 Cleaned_Augmented_DB 并补齐最终 GPS |
