# 步骤-SQL-参数映射

> 版本：v1.0 | 日期：2026-03-23
> 来源：lac_enbid_project/ 下所有 SQL 资产 + 6个补丁

---

## 1. 总览

### 1.1 SQL 资产清单

共 **28个核心SQL** + **6个补丁** + 若干SMOKE测试SQL。

| Layer | 步骤数 | SQL文件数 | 说明 |
|-------|--------|----------|------|
| Layer 0 | 1 | 1 | 原始数据构建 |
| Layer 2 | 7 (Step0~6) | 7 | 标准化→合规→可信LAC→Cell统计→合规过滤 |
| Layer 3 | 8 (Step30~37) + 交付 | 10 | BS主库→GPS修正→信号补齐→质量检测→交付 |
| Layer 4 | 5 (Step40~44) | 5 | 完整回归：GPS过滤→信号补齐→对比→合并→标记 |
| Layer 5 | 4 (Step50~53) | 4 | 三级画像 + 列名中文化 |
| 补丁 | — | 6 | 局部修正（已合入主链路逻辑） |

### 1.2 执行链路图

```
Layer 0: 原始数据
  │
Layer 2: Step0 → Step1 → Step2 → Step3 → Step4 → Step5 → Step6
         标准化    基础统计  合规标记  LAC统计  可信LAC  Cell统计  合规过滤
  │
Layer 3: Step30 → Step31 → Step32(报表) → Step33 → Step34(报表)
         BS主库    GPS修正   GPS对比报表   信号补齐  信号对比报表
                     │
                     ├── Step35 动态Cell检测（附加）
                     ├── Step36 BS ID异常标记（附加）
                     └── Step37 碰撞数据不足标记（附加）
                     │
                     └── Step40_delivery BS画像+Cell映射 交付
  │
Layer 4: Step40 → Step41 → Step42(报表) → Step43(合并) → Step44(标记)
         GPS过滤   信号补齐  最终对比报表   指标合并     BS_ID<256标记
  │
Layer 5: Step50 → Step51 → Step52 → Step53
         LAC画像   BS画像   Cell画像  列名中文化
```

---

## 2. 逐步骤详细映射

### 2.1 Layer 2: 标准化与合规筛选

---

#### Step 0: 标准化视图

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_2/sql/00_step0_std_views.sql` |
| **输入表** | Y_codex_Layer0_Gps_base, Y_codex_Layer0_Lac |
| **输出表** | Y_codex_Layer2_Step00_Gps_Std (VIEW), Y_codex_Layer2_Step00_Lac_Std (VIEW) |
| **新表映射** | 合并入 `pipeline.raw_records`（物化，非VIEW） |
| **业务逻辑** | 对原始数据派生标准化字段：tech_norm、operator_id_raw、operator_group_hint、report_date、has_cellid/has_lac/has_gps |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| tech_norm 映射 | 4G / 5G / 2_3G | 按原始 tech 字段分类 |
| operator_id_raw | 保留原始 PLMN 码（46000/46001/46011/46015/46020） | 原始运营商编码，全链路统一使用 |
| operator_group_hint | 46000/46015/46020→CMCC, 46001→CUCC, 46011→CTCC | 运营商分组标签（便于分组聚合） |
| GPS有效范围 | lon ∈ [-180, 180], lat ∈ [-90, 90], 排除 (0,0) | GPS坐标有效性判断 |
| hex长度规则 | CMCC系: 4或6位; CU/CT系: 4-6位 | LAC hex 编码长度合规性 |

---

#### Step 1: 基础统计

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_2/sql/01_step1_base_stats.sql` |
| **输入表** | Y_codex_Layer2_Step00_Gps_Std |
| **输出表** | Y_codex_Layer2_Step01_BaseStats_Raw (436行), Y_codex_Layer2_Step01_BaseStats_ValidCell (18行) |
| **新表映射** | `pipeline.stats_base_raw` |
| **业务逻辑** | 全量统计：行数、去重cell/lac/设备数、缺值率。ValidCell 统计经合规过滤后的数据 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| ValidCell 条件 | operator_id_raw ∈ {46000,46001,46011,46015,46020} | 五大运营商编码 |
| ValidCell 条件 | tech_norm ∈ {4G, 5G} | 仅4G/5G |
| ValidCell 条件 | lac_dec > 0, cell_id_dec > 0 且 ≠ 2147483647 | 排除无效值 |

---

#### Step 2: 合规标记

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_2/sql/02_step2_compliance_mark.sql` |
| **输入表** | Y_codex_Layer2_Step00_Gps_Std |
| **输出表** | Y_codex_Layer2_Step02_Gps_Compliance_Marked, Y_codex_Layer2_Step02_Compliance_Diff (502行) |
| **新表映射** | 中间产物，合并入 `pipeline.fact_filtered` 的标准化步骤 |
| **业务逻辑** | 行级绝对合规打标：运营商、制式、LAC数值/Hex长度、Cell范围。输出 is_compliant + 不合规原因 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 运营商范围 | {46000, 46001, 46011, 46015, 46020} | 五大PLMN |
| 制式范围 | {4G, 5G} | 排除2G/3G |
| LAC溢出值 | {0xFFFF, 0xFFFE, 0xFFFFFE, 0xFFFFFF, 0x7FFFFFFF} | 即 {65534, 65535, 16777214, 16777215, 2147483647} |
| 4G Cell范围 | [1, 268435455] | 0x0FFFFFFF |
| 5G Cell范围 | [1, 68719476735] | 0xFFFFFFFFF |

---

#### Step 3: LAC统计库

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_2/sql/03_step3_lac_stats_db.sql` |
| **输入表** | Y_codex_Layer2_Step02_Gps_Compliance_Marked (is_compliant=true) |
| **输出表** | Y_codex_Layer2_Step03_Lac_Stats_DB (11,416行) |
| **新表映射** | `pipeline.stats_lac` |
| **业务逻辑** | 按 operator+tech+lac 聚合：上报次数、有效GPS次数、关联小区数、活跃天数 |

**参数清单：** 无硬编码参数，仅使用 is_compliant=true 过滤。

---

#### Step 4: 可信LAC库

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_2/sql/04_step4_master_lac_lib.sql` |
| **输入表** | Y_codex_Layer2_Step03_Lac_Stats_DB |
| **输出表** | Y_codex_Layer2_Step04_Master_Lac_Lib (881行) |
| **新表映射** | `pipeline.dim_lac_trusted` |
| **业务逻辑** | 从LAC统计中筛选活跃且稳定的LAC，形成可信白名单 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| active_days 门槛 | = 7 | 必须满7天活跃 |
| LAC排除值 | {65534, 65535, 16777214, 16777215, 2147483647} | 溢出/占位值 |
| 设备数门槛（CMCC/CUCC/CTCC） | ≥ 5 | 最低设备数 |
| 设备数门槛（CU/CT-5G特例） | ≥ 3 | 5G小网 |
| 上报量门槛 | ≥ P80 百分位 | 按运营商+制式分组的P80 |
| 46015/46020 特例 | 仅需7天稳定 | 规模较小的CMCC子网 |
| 置信度排序依据 | valid_gps_count DESC | GPS有效上报量 |

---

#### Step 5: Cell统计与异常检测

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql` |
| **输入表** | Y_codex_Layer2_Step02_Gps_Compliance_Marked (is_compliant=true), Y_codex_Layer2_Step04_Master_Lac_Lib |
| **输出表** | Y_codex_Layer2_Step05_CellId_Stats_DB (502,199行), Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac |
| **新表映射** | `pipeline.dim_cell_stats` |
| **业务逻辑** | 基于可信LAC白名单，聚合cell级统计；识别"一cell多lac"异常 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 数据范围 | 仅可信LAC内的合规数据 | JOIN Step04 白名单 |
| 异常条件 | lac_distinct_cnt > 1 | 同一cell出现在多个lac下 |

---

#### Step 6: LAC合规过滤（含反哺）

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_2/sql/06_step6_apply_mapping_and_compare.sql` |
| **输入表** | Y_codex_Layer2_Step00_Lac_Std, Y_codex_Layer2_Step05_CellId_Stats_DB, Y_codex_Layer2_Step00_Gps_Std, Y_codex_Layer2_Step02_Gps_Compliance_Marked |
| **输出表** | Y_codex_Layer2_Step06_L0_Lac_Filtered (2178万行), Y_codex_Layer2_Step06_GpsVsLac_Compare |
| **新表映射** | `pipeline.fact_filtered` |
| **业务逻辑** | 用cell→lac映射对LAC路数据补齐/纠偏；多LAC收敛（选信号最优LAC）；仅保留最终LAC在可信白名单内的记录 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 数据范围 | 5PLMN + 4G/5G + has_cell | 基础过滤 |
| 多LAC收敛优先级 | ① good_sig_cnt (sig_rsrp≠-110的记录数) ② lac_confidence_score ③ record_count | 选择最优LAC |
| 信号清洗 | sig_rsrp = -110 / -1 / ≥0 → NULL | 无效RSRP值置空 |
| 输出条件 | is_final_lac_trusted = true | 最终LAC必须在可信白名单内 |

**相关补丁：**
- 补丁_20251218_LAC_溢出与占位值清理.sql — 清理Step03~06中残留的占位LAC值
- 补丁_20251218_Step06_输出LAC字段归一.sql — lac_dec/lac_hex 输出归一为最终可信值
- 补丁_20251219_无效RSRP置空_Step06_Step31.sql — sig_rsrp = -110/-1/≥0 → NULL
- 补丁_20251219_Layer2_Step06_多LAC按信号有效上报量收敛.sql — 按7天信号有效上报量收敛多LAC

---

### 2.2 Layer 3: BS主库与GPS/信号修正

---

#### Step 30: BS主库构建

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/30_step30_master_bs_library.sql` (单机版) + v4系列 (并行版) |
| **输入表** | Y_codex_Layer2_Step02_Gps_Compliance_Marked, Y_codex_Layer2_Step04_Master_Lac_Lib, Y_codex_Layer2_Step05_CellId_Stats_DB, Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac, Y_codex_Layer2_Step06_L0_Lac_Filtered |
| **输出表** | Y_codex_Layer3_Step30_Master_BS_Library (138,121行) |
| **新表映射** | `pipeline.dim_bs_trusted` |
| **业务逻辑** | 按 tech_norm+bs_id+lac_dec_final 分桶聚合；计算BS中心点（鲁棒中位数→剔漂移→重算）；标记多运营商共建、碰撞疑似、GPS质量等级 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| outlier_remove_if_dist_m_gt | 2500.0 米 | 离群点移除距离阈值 |
| collision_if_p90_dist_m_gt | 1500.0 米 | 碰撞判定距离阈值 |
| signal_keep_top50_n | 50 | 信号优先中心点策略：取Top50 |
| center_bin_scale | 10000 | 经纬度分桶精度（万分之一度≈11米） |
| 地理范围 | lon [73.0, 135.0], lat [3.0, 54.0] | 中国境内 |
| GPS质量等级 | Usable / Risk / Unusable | 基于gps_valid_point_cnt和p90判定 |

**并行优化（v4版本）：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 每桶最近N点 | 1000 | 用于重链路的采样上限 |
| work_mem | 512MB | 查询内并行内存 |
| max_parallel_maintenance_workers | 8 | 并行索引构建 |

**相关补丁：**
- 补丁_20251219_Layer3_Step30_点级剔除漂移GPS_局部更新.sql — trim_dist_m=2500，避免全量重跑
- 补丁_20251219_Layer3_Step30_信号优先中心点_局部更新.sql — 信号优先策略：TOP50/TOP20/TOP80%

---

#### Step 31: Cell GPS修正

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/31_step31_cell_gps_fixed.sql` |
| **输入表** | Y_codex_Layer2_Step06_L0_Lac_Filtered, Y_codex_Layer3_Step30_Master_BS_Library |
| **输出表** | Y_codex_Layer3_Step31_Cell_Gps_Fixed (2178万行) |
| **新表映射** | `pipeline.fact_gps_corrected` |
| **业务逻辑** | 按BS中心点回填缺失/漂移GPS；判定GPS状态（Verified/Missing/Drift）；标记gps_source |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| drift_if_dist_m_gt | 1500.0 米 | GPS漂移判定距离阈值 |
| 地理范围 | lon [73.0, 135.0], lat [3.0, 54.0] | 中国境内判定 |
| gps_source 枚举 | Original_Verified / Augmented_from_BS / Augmented_from_Risk_BS / Not_Filled | GPS来源标记 |
| gps_status 枚举 | Verified / Missing / Drift | 修正前状态 |
| gps_status_final 枚举 | Verified / Filled_from_BS / Filled_from_Risk_BS / Not_Filled | 修正后状态 |

---

#### Step 32: GPS修正对比报表

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/32_step32_compare.sql` |
| **输入表** | Y_codex_Layer3_Step31_Cell_Gps_Fixed, Y_codex_Layer3_Step30_Master_BS_Library |
| **输出表** | Y_codex_Layer3_Step32_Compare, Y_codex_Layer3_Step32_Compare_Raw |
| **新表映射** | `pipeline.compare_gps` |
| **业务逻辑** | 统计GPS修正前后对比：Missing→Filled、Drift→Corrected转换数；BS风险等级分布；PASS/FAIL/WARN验收 |

**参数清单：** 无硬阈值，仅对比统计。Risk基站回填占比高时标记 WARN。

---

#### Step 33: 信号字段简单补齐

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/33_step33_signal_fill_simple.sql` |
| **输入表** | Y_codex_Layer3_Step31_Cell_Gps_Fixed |
| **输出表** | Y_codex_Layer3_Step33_Signal_Fill_Simple (2178万行) |
| **新表映射** | `pipeline.fact_signal_filled` |
| **业务逻辑** | 按 cell/bs 聚合信号中位数进行补齐。优先同cell中位数，回退到同bs中位数 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 信号无效值清洗 | -110, -1, ≥0 → NULL | 适用于 sig_rsrp |
| 补齐优先级 | ① cell中位数 → ② bs中位数 → ③ none | 两级回退 |
| 补齐字段 | rsrp, rsrq, sinr, rssi, dbm, asu_level, level, ss | 共8个信号字段 |
| signal_fill_source 枚举 | by_cell_median / by_bs_median / none | 补齐来源标记 |

---

#### Step 34: 信号补齐对比报表

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/34_step34_signal_compare.sql` |
| **输入表** | Y_codex_Layer3_Step33_Signal_Fill_Simple |
| **输出表** | Y_codex_Layer3_Step34_Signal_Compare, Y_codex_Layer3_Step34_Signal_Compare_Raw |
| **新表映射** | `pipeline.compare_signal` |
| **业务逻辑** | 按 signal_fill_source 和维度统计缺失字段变化，PASS/FAIL验收（after ≤ before） |

---

#### Step 35: 动态Cell/BS检测（附加）

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/35_step35_dynamic_cell_bs_detection.sql` + `35_step35_dynamic_cell_28d_validation.sql` |
| **输入表** | Y_codex_Layer3_Step30_Master_BS_Library, Y_codex_Layer3_Step31_Cell_Gps_Fixed |
| **输出表** | Y_codex_Layer3_Step35_Dynamic_Cell_Profile, Y_codex_Layer3_Step35_Dynamic_BS_Profile |
| **新表映射** | 功能合并入 `pipeline.profile_cell` (is_dynamic_cell) |
| **业务逻辑** | 用坐标round到3位小数做日主导质心；按时间分半比较质心切换；标记动态cell |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| min_bs_p90_m | 5000.0 米 | 仅关注p90足够大的桶 |
| grid_round_decimals | 3 | ~100米级网格 |
| min_day_major_share | 0.50 | 日主导质心占比门槛 |
| min_half_major_day_share | 0.60 | 两半主导质心天占比门槛 |
| min_half_major_dist_km | 10.0 km | 两半间距门槛 |
| min_effective_days | 5 | 最少有效天数 |

---

#### Step 36: BS ID异常标记（附加）

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/36_step36_bs_id_anomaly_mark.sql` |
| **输入表** | Y_codex_Layer3_Final_BS_Profile |
| **输出表** | Y_codex_Layer3_Step36_BS_Id_Anomaly_Marked |
| **新表映射** | `pipeline.detect_anomaly_bs` |
| **业务逻辑** | 保守标注异常BS ID，不影响主链路 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 4G异常 | bs_id_hex长度 < 4（即 bs_id < 4096） | |
| 5G异常 | bs_id_hex长度 < 5 | |
| 特殊值 | bs_id = 0 或 1 | 标记 BS_ID_ZERO / BS_ID_ONE |

---

#### Step 37: 碰撞数据不足标记（附加）

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/37_step37_collision_data_insufficient_mark.sql` |
| **输入表** | Y_codex_Layer3_Step30_Master_BS_Library |
| **输出表** | Y_codex_Layer3_Step37_Collision_Data_Insufficient_BS |
| **新表映射** | `pipeline.detect_collision` |
| **业务逻辑** | 标注 is_collision_suspect=1 但 GPS点数过少的桶，建议延长窗口复核 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| low_point_cnt_lt | 20 | 可信GPS点数阈值 |
| 低样本分桶 | <5 / 5-9 / 10-19 / ≥20 | 风险等级分桶 |
| 标记值 | DATA_INSUFFICIENT_7D | 建议待28d窗口复核 |

---

#### Layer 3 交付: BS画像 + Cell映射

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_3/sql/40_layer3_delivery_bs_cell_tables.sql` |
| **输入表** | Y_codex_Layer3_Step30_Master_BS_Library, Y_codex_Layer3_Step31_Cell_Gps_Fixed |
| **输出表** | Y_codex_Layer3_Final_BS_Profile, Y_codex_Layer3_Final_Cell_BS_Map |
| **新表映射** | 部分功能已在 `pipeline.dim_bs_trusted` / `pipeline.map_cell_bs` 中覆盖 |
| **业务逻辑** | A) 聚合Step31明细到BS级画像；B) 构建cell→bs唯一映射表 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| BS聚合维度 | operator_id_raw + tech_norm + bs_id + lac_dec_final | |
| cell映射选择 | 按 report_cnt 最多, last_seen_ts 最近的桶 | 去重策略 |

---

### 2.3 Layer 4: 完整回归

---

#### Step 40: Cell GPS过滤与回填（完整回归）

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_4/sql/40_step40_cell_gps_filter_fill.sql` |
| **输入表** | **重构后**: pipeline.raw_records（合并两张Layer0，2.5亿行）, pipeline.dim_bs_trusted, pipeline.dim_lac_trusted, pipeline.dim_cell_stats。**旧SQL**: 仅使用 Y_codex_Layer0_Lac（LAC路） |
| **输出表** | Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill (3050万行), Y_codex_Layer4_Step40_Gps_Metrics |
| **新表映射** | 中间产物，合并入 `pipeline.fact_final` |
| **业务逻辑** | 基于可信BS库对**全量原始数据**进行完整GPS过滤回填。重构后输入为 raw_records（合并LAC路+GPS路），旧SQL仅处理LAC路。严重碰撞桶仍回填但强标注 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 4G距离阈值 | 1000 米 | GPS离BS中心距离阈值 |
| 5G距离阈值 | 500 米 | 5G更严格 |
| 地理范围 | lon [73, 135], lat [3, 54] | 中国境内 |
| 严重碰撞处理 | 回填但标记 is_severe_collision | 不丢弃，降权使用 |
| BS分片键 | bs_shard_key = tech_norm\|bs_id_final | 支持并行分片处理 |

---

#### Step 41: Cell信号补齐（完整回归）

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_4/sql/41_step41_cell_signal_fill.sql` |
| **输入表** | Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill |
| **输出表** | Y_codex_Layer4_Final_Cell_Library (3050万行), Y_codex_Layer4_Step41_Signal_Metrics |
| **新表映射** | `pipeline.fact_final` |
| **业务逻辑** | 二阶段信号补齐：优先同小区最近时间有信号记录→退化到同BS桶Top Cell |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 补齐优先级 | ① 同cell最近时间有信号记录 → ② 同BS Top Cell最近时间 | |
| donor条件 | 至少有一个信号字段非NULL | |
| min_center_point | 5 | 信号决策最低点数 |
| Top Cell选择 | 同BS下数据量最多的cell | |

---

#### Step 42: 最终对比报表

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_4/sql/42_step42_compare.sql` |
| **输入表** | Y_codex_Layer0_Lac, Y_codex_Layer4_Final_Cell_Library |
| **输出表** | Y_codex_Layer4_Step42_Compare_Summary |
| **新表映射** | 工作台指标替代 |
| **业务逻辑** | 对比原始库与最终库的条数、GPS、信号统计，验证数据质量提升 |

---

#### Step 43: 指标合并

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_4/sql/43_step43_merge_metrics.sql` |
| **输入表** | Y_codex_Layer4_Step40_Gps_Metrics (分片), Y_codex_Layer4_Step41_Signal_Metrics (分片) |
| **输出表** | Y_codex_Layer4_Step40_Gps_Metrics_All, Y_codex_Layer4_Step41_Signal_Metrics_All |
| **新表映射** | 工作台指标替代 |
| **业务逻辑** | 汇总分片指标表，每个shard一行 + rollup行 |

---

#### Step 44: BS_ID<256标记（附加）

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_4/sql/44_step44_bs_id_lt_256_mark.sql` |
| **输入表** | Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill |
| **输出表** | Y_codex_Layer4_Step44_BsId_Lt_256_Detail, Y_codex_Layer4_Step44_BsId_Lt_256_Summary |
| **新表映射** | 合并入 `pipeline.fact_final` 的 is_bs_id_lt_256 字段 |
| **业务逻辑** | 标记 bs_id_final < 256 的异常记录（仅标记不过滤） |

---

### 2.4 Layer 5: 三级画像

---

#### Step 50: LAC画像

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_5/sql/50_step50_lac_profile.sql` |
| **输入表** | Y_codex_Layer4_Final_Cell_Library |
| **输出表** | Y_codex_Layer5_Lac_Profile (878行) |
| **新表映射** | `pipeline.profile_lac` |
| **业务逻辑** | 按LAC维度汇总：行数、GPS有效率、GPS分布、信号完整度、补齐效果、多运营商标记 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 最小行数 | 5000 | 小于此值标记 is_insufficient_sample |
| GPS P90 WARN阈值 | 100,000 米 | LAC级GPS分散度告警 |
| 运营商分组 | G1: {46000,46015,46020}, G2: {46001,46011} | |

---

#### Step 51: BS画像

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_5/sql/51_step51_bs_profile.sql` |
| **输入表** | Y_codex_Layer4_Final_Cell_Library |
| **输出表** | Y_codex_Layer5_BS_Profile (163,778行) |
| **新表映射** | `pipeline.profile_bs` |
| **业务逻辑** | 按BS维度汇总：小区数、GPS指标、信号指标、碰撞/漂移标记、动态cell标记 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 最小行数 | 500 | is_insufficient_sample |
| 4G GPS P90 WARN | 1000 米 | |
| 5G GPS P90 WARN | 500 米 | |

---

#### Step 52: Cell画像

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_5/sql/52_step52_cell_profile.sql` |
| **输入表** | Y_codex_Layer4_Final_Cell_Library |
| **输出表** | Y_codex_Layer5_Cell_Profile (490,831行) |
| **新表映射** | `pipeline.profile_cell` |
| **业务逻辑** | 按Cell维度汇总：活跃天数、GPS画像、信号补齐情况、动态cell标记 |

**参数清单：**

| 参数名 | 值 | 说明 |
|--------|-----|------|
| 最小行数 | 200 | is_insufficient_sample |
| 4G GPS P90 WARN | 1000 米 | |
| 5G GPS P90 WARN | 500 米 | |

---

#### Step 53: 列名中文化

| 项目 | 内容 |
|------|------|
| **SQL文件** | `Layer_5/sql/53_step53_rename_profile_columns_cn.sql` |
| **输入表** | Layer5 三张画像表 |
| **输出表** | 同（列名重命名） |
| **新表映射** | **重构中废弃此步骤**，新表统一用英文列名 |
| **业务逻辑** | 将英文列名改为中文表头（幂等操作，列已中文则跳过） |

---

## 3. 参数注册表（汇总）

### 3.1 全局参数

| 参数名 | 值 | 适用范围 | 说明 |
|--------|-----|---------|------|
| 运营商白名单 | {46000, 46001, 46011, 46015, 46020} | Step0~Step6, Step40 | 五大PLMN |
| 制式白名单 | {4G, 5G} | 全链路 | 排除2G/3G |
| 中国地理范围 | lon [73, 135], lat [3, 54] | Step30, Step31, Step40 | GPS有效性 |
| LAC溢出/占位值 | {65534, 65535, 16777214, 16777215, 2147483647} | Step2, Step4 | 排除无效LAC |
| 信号无效值（RSRP） | {-110, -1, ≥0} → NULL | Step6, Step31, Step33 | 清洗无效信号 |

### 3.2 步骤级参数

| 步骤 | 参数名 | 值 | 说明 |
|------|--------|-----|------|
| Step4 | active_days_threshold | 7 | LAC最少活跃天数 |
| Step4 | min_device_count | 5（5G特例3） | 最少设备数 |
| Step4 | report_count_percentile | P80 | 上报量门槛 |
| Step30 | outlier_dist_m | 2500 | 离群点移除 |
| Step30 | collision_p90_dist_m | 1500 | 碰撞判定 |
| Step30 | signal_top_n | 50 | 信号优先Top N |
| Step30 | center_bin_scale | 10000 | 经纬度分桶精度（万分之一度≈11米） |
| Step31 | drift_dist_m | 1500 | 漂移判定 |
| Step35 | min_bs_p90_m | 5000 | 动态检测触发阈值 |
| Step35 | grid_round_decimals | 3 | ~100米级网格 |
| Step35 | min_day_major_share | 0.50 | 日主导质心占比门槛 |
| Step35 | min_half_major_day_share | 0.60 | 两半主导质心天占比门槛 |
| Step35 | min_half_major_dist_km | 10 | 动态判定间距 |
| Step35 | min_effective_days | 5 | 动态判定最少天数 |
| Step40 | gps_dist_threshold_4g | 1000 | 4G GPS距离阈值 |
| Step40 | gps_dist_threshold_5g | 500 | 5G GPS距离阈值 |
| Step50 | min_rows | 5000 | LAC画像最少行数 |
| Step50 | gps_p90_warn_m | 100000 | LAC GPS P90告警阈值 |
| Step51 | min_rows | 500 | BS画像最少行数 |
| Step51 | gps_p90_warn_4g_m | 1000 | BS 4G GPS P90告警 |
| Step51 | gps_p90_warn_5g_m | 500 | BS 5G GPS P90告警 |
| Step52 | min_rows | 200 | Cell画像最少行数 |
| Step52 | gps_p90_warn_4g_m | 1000 | Cell 4G GPS P90告警 |
| Step52 | gps_p90_warn_5g_m | 500 | Cell 5G GPS P90告警 |

---

## 4. 补丁清单与合并状态

| # | 补丁名 | 影响步骤 | 内容 | 重构处理 |
|---|--------|---------|------|---------|
| 1 | 补丁_20251218_LAC_溢出与占位值清理 | Step3~6 | 删除占位/溢出LAC值 | 合入Step4参数 |
| 2 | 补丁_20251218_Step06_输出LAC字段归一 | Step6 | lac_dec输出归一为lac_dec_final | 合入Step6逻辑 |
| 3 | 补丁_20251219_Layer3_Step30_点级剔除漂移GPS | Step30 | trim_dist_m=2500局部更新 | 合入Step30参数 |
| 4 | 补丁_20251219_无效RSRP置空 | Step6, Step31 | sig_rsrp无效值→NULL | 合入全局参数 |
| 5 | 补丁_20251219_多LAC按信号有效上报量收敛 | Step6 | 按good_sig_cnt收敛多LAC | 合入Step6逻辑 |
| 6 | 补丁_20251219_信号优先中心点 | Step30 | TOP50/TOP20/TOP80%策略 | 合入Step30参数 |

**重构原则**：所有补丁逻辑合并入对应步骤的主SQL中，不再单独维护补丁文件。

---

## 5. 重构后步骤与新表的映射总表

| 重构步骤 | 新表（pipeline.*） | 对应旧Step | SQL资产文件 |
|---------|-------------------|-----------|------------|
| 1. 数据标准化 | raw_records | Step0 | 00_step0_std_views.sql |
| 2. 基础统计 | stats_base_raw | Step1 | 01_step1_base_stats.sql |
| 3. 合规标记 | （中间过程） | Step2 | 02_step2_compliance_mark.sql |
| 4. LAC统计 | stats_lac | Step3 | 03_step3_lac_stats_db.sql |
| 5. 可信LAC | dim_lac_trusted | Step4 | 04_step4_master_lac_lib.sql |
| 6. Cell统计 | dim_cell_stats | Step5 | 05_step5_cellid_stats_and_anomalies.sql |
| 7. 合规过滤 | fact_filtered | Step6 | 06_step6_apply_mapping_and_compare.sql |
| 8. BS主库 | dim_bs_trusted | Step30 | 30_step30_master_bs_library*.sql |
| 9. GPS修正 | fact_gps_corrected | Step31 | 31_step31_cell_gps_fixed.sql |
| 10. GPS对比 | compare_gps | Step32 | 32_step32_compare.sql |
| 11. 信号补齐 | fact_signal_filled | Step33 | 33_step33_signal_fill_simple.sql |
| 12. 信号对比 | compare_signal | Step34 | 34_step34_signal_compare.sql |
| 13. 动态检测 | （合入profile_cell） | Step35 | 35_step35_dynamic_cell*.sql |
| 14. BS异常 | detect_anomaly_bs | Step36 | 36_step36_bs_id_anomaly_mark.sql |
| 15. 碰撞不足 | detect_collision | Step37 | 37_step37_collision_data_insufficient_mark.sql |
| 16. Cell映射 | map_cell_bs | Layer3交付 | 40_layer3_delivery_bs_cell_tables.sql |
| 17. 完整回归GPS | （合入fact_final） | Step40 | 40_step40_cell_gps_filter_fill.sql |
| 18. 完整回归信号 | fact_final | Step41 | 41_step41_cell_signal_fill.sql |
| 19. 最终对比 | （工作台指标） | Step42 | 42_step42_compare.sql |
| 20. LAC画像 | profile_lac | Step50 | 50_step50_lac_profile.sql |
| 21. BS画像 | profile_bs | Step51 | 51_step51_bs_profile.sql |
| 22. Cell画像 | profile_cell | Step52 | 52_step52_cell_profile.sql |
| — | ~~列名中文化~~ | Step53 | **废弃**，新表统一英文列名 |
