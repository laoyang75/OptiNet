# Layer_2（北京明细 20251201_20251207）：统计建库 v1

本层目标（对应三段式路线的“阶段一：统计建库”）：以 `public."Y_codex_Layer0_Gps_base"` 为主输入，完成基础统计 → 行级合规标记 → 有效 LAC 统计库 → 可信 LAC 库 → 可信映射（LAC+Cell+运营商+制式）→ 用可信映射反哺 `public."Y_codex_Layer0_Lac"` 并与 GPS 路对比。

> 说明：本层不实现 share/top1 等“映射强度指标”；但 `record_count / valid_gps_count / active_days / first_seen / last_seen` 必须实现。

---

## README 大纲（你要的输出形式）

1. 背景与输入表
2. 命名规范与通用口径（Step0 标准化）
3. Step0~Step6：逐步 I/O、主键粒度、字段、指标、验证 SQL、验收标准
4. 表清单（Layer_2 输出对象）
5. SQL 文件清单（可按顺序执行）
6. 未来 3 个大步骤的接口预埋（字段结构）
7. 字段字典（Data Dictionary）索引

---

## 1. 背景与输入表

### 1.1 Layer_0 输入表

- GPS 路：`public."Y_codex_Layer0_Gps_base"`（你口径中的 `Y_codex_Layer0_GPS`）
- LAC 路：`public."Y_codex_Layer0_Lac"`

两表字段结构一致（均含：`seq_id/tech/"运营商id"/lac_dec/cell_id_dec/ts_std/parsed_from/...`）。

### 1.2 Layer_1 合规规则（Step1/Step2 复用）

- `lac_enbid_project/Layer_1/Cell/Cell_Filter_Rules_v1.md`
- `lac_enbid_project/Layer_1/Lac/Lac_Filter_Rules_v1.md`

北京源表版本（逻辑一致，换输入名）：  
- `lac_enbid_project/Layer_1/Cell/Cell_Filter_Rules_Beijing_Sources_v1.md`  
- `lac_enbid_project/Layer_1/Lac/Lac_Filter_Rules_Beijing_Sources_v1.md`

---

## 2. 命名规范与通用口径（Step0）

### 2.1 命名规范

- `v_*`：标准化/衍生视图（不落表）
- `d_*`：核心数据集（建议落表或物化视图）
- `rpt_*`：统计报表（小表，建议落表）

### 2.2 全局统一口径（必须遵守）

- 运营商字段策略：
  - 运营商 id（细粒度）：`operator_id_raw`（直接来自 `"运营商id"`，主键一律用它）
  - 运营商组提示：`operator_group_hint`（仅用于报表视角，不改变主键粒度）
    - 至少支持：`46000/46015/46020` → 同一组（移动系）
    - `46001`（联通）与 `46011`（电信）暂不强合并
- 上报日期：`report_date = date(ts_std)`（已确认以 `ts_std` 为准）
- 设备口径：`device_id = coalesce(did, oaid)`（优先 did，空则用 oaid）
- 制式标准化：`tech_norm ∈ {4G,5G,2_3G,其他}`
- “是否有值”字段：`has_cellid/has_lac/has_gps`（用于解决“抽取到了但无值也被统计”的问题）

---

## 3. Step0~Step6 详细计划与落地清单（含验证 SQL）

> 每步至少 3 条验证 SQL；完整 SQL 在对应 `sql/*.sql` 文件中也会包含。

### Step0：标准化视图（必须先做）

- **输入表**：`public."Y_codex_Layer0_Gps_base"`（建议同时为 LAC 路做对称视图）
- **输出视图**：
- `public."Y_codex_Layer2_Step00_Gps_Std"`
- `public."Y_codex_Layer2_Step00_Lac_Std"`（供 Step6）
- **主键粒度**：行级（沿用 `seq_id`）
- **核心字段（中文（English））**：
  - 制式_标准化（`tech_norm`）
  - 运营商id_细粒度（`operator_id_raw`）
  - 运营商组_提示（`operator_group_hint`）
  - 上报日期（`report_date`）
  - 设备ID（`device_id`）
  - lac长度（`lac_len`）、cell长度（`cell_len`）
  - 是否有cell（`has_cellid`）、是否有lac（`has_lac`）、是否有gps（`has_gps`）
- **验证 SQL（>=3）**：
  - `select count(*) from public."Y_codex_Layer2_Step00_Gps_Std";`
  - `select tech_norm, count(*) from public."Y_codex_Layer2_Step00_Gps_Std" group by 1 order by 2 desc;`
  - `select operator_group_hint, count(*) from public."Y_codex_Layer2_Step00_Gps_Std" group by 1 order by 2 desc;`
- **验收标准**：
- `Y_codex_Layer2_Step00_Gps_Std` 行数与 `Y_codex_Layer0_Gps_base` 一致
  - `tech_norm` 仅出现 `4G/5G/2_3G/其他`
  - `report_date` 基本落在本周期（异常值可接受但需可识别）

---

### Step1：Layer_2 基础统计（Raw + ValidCell 两套）

-- **输入表/视图**：`public."Y_codex_Layer2_Step00_Gps_Std"`
- **输出报表**：
  1. `public."Y_codex_Layer2_Step01_BaseStats_Raw"`（Raw：不引用合规）
  2. `public."Y_codex_Layer2_Step01_BaseStats_ValidCell"`（仅应用 L1-CELL “cell 正常值规则”，不做其它合规）
- **主键粒度**：按维度聚合（`tech_norm + operator_id_raw + operator_group_hint + parsed_from`）
- **核心统计指标（两套都要）**：
  - 行数（`row_cnt`）
  - 去重小区数（`cell_cnt`，`count distinct cell_id_dec`，排除 NULL）
  - 去重 LAC 数（`lac_cnt`，`count distinct lac_dec`，排除 NULL）
  - 设备数（`device_cnt`，`count distinct device_id`）
  - 来源分布（`parsed_from=cell_infos/ss1`）
  - 无值统计：`no_cellid_pct / no_lac_pct / no_gps_pct`
- **验证 SQL（>=3）**：
  - `select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_Raw";`
  - `select parsed_from, sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_Raw" group by 1;`
  - `select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_ValidCell";`
- **验收标准**：
  - `sum(row_cnt)` 与输入行数一致（raw）；valid_cell 的行数应小于等于 raw
  - `parsed_from='ss1'` 行理论上应主要对应 `match_status='SS1_UNMATCHED'`（若偏离需排查上游解析）

---

### Step2：合规标记（行级绝对合规）+ 合规前后对比

-- **输入表/视图**：`public."Y_codex_Layer2_Step00_Gps_Std"`
- **输出**：
  1. `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（视图/表）：全量保留，但带合规标记
  2. `public."Y_codex_Layer2_Step02_Compliance_Diff"`（报表）：合规前后结构对比 + 不合规原因 TopN
- **主键粒度**：行级（`seq_id`）
- **核心字段（中文（English））**：
  - 是否L1_LAC合规（`is_l1_lac_ok`）
  - 是否L1_CELL合规（`is_l1_cell_ok`）
  - 是否合规（`is_compliant`）
  - 不合规原因（`non_compliant_reason`，多原因用 `;` 拼接）
- **核心统计指标**：
  - 合规保留行数/剔除行数/剔除占比
  - 按 `tech_norm / operator_id_raw / operator_group_hint / parsed_from` 的前后变化
  - 不合规原因 TopN
- **验证 SQL（>=3）**：
  - `select is_compliant, count(*) from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" group by 1;`
  - `select non_compliant_reason, count(*) from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" where not is_compliant group by 1 order by 2 desc limit 20;`
  - `select count(*) from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" where is_compliant and (lac_dec is null or cell_id_dec is null or tech_norm not in ('4G','5G'));`
- **验收标准**：
  - `is_compliant=true` 的记录必须满足：运营商在 5 个 PLMN 内、`tech_norm` 为 4G/5G、`lac_dec/cell_id_dec` 数值合规
- `Y_codex_Layer2_Step02_Compliance_Diff` 能清晰看到“剔除比例”与主要剔除原因

---

### Step3：有效 LAC 汇总库（LAC 维度统计主表）

- **输入表/视图**：`public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（仅取 `is_compliant=true`）
- **输出表**：`public."Y_codex_Layer2_Step03_Lac_Stats_DB"`
- **主键粒度（已确认）**：`operator_id_raw + tech_norm + lac_dec`
- **核心字段/指标（必须实现）**：
  - 总上报次数（`record_count`）
  - 关联小区数（`distinct_cellid_count`）
  - 关联设备数（`distinct_device_count`）
  - 首次出现（`first_seen_ts` / `first_seen_date`）
  - 最后出现（`last_seen_ts` / `last_seen_date`）
  - 活跃天数（`active_days = count distinct report_date`）
  - （建议）有效 GPS 次数（`valid_gps_count`，`has_gps=true`）
- **验证 SQL（>=3）**：
  - `select sum(record_count) from public."Y_codex_Layer2_Step03_Lac_Stats_DB";`
  - `select min(active_days), max(active_days) from public."Y_codex_Layer2_Step03_Lac_Stats_DB";`
  - `select operator_id_raw, tech_norm, lac_dec, count(*) from public."Y_codex_Layer2_Step03_Lac_Stats_DB" group by 1,2,3 having count(*)>1;`
- **验收标准**：
  - `sum(record_count)` 等于 Step2 合规有效行数
  - 主键三元组无重复
  - `active_days` 落在合理范围（本周期 7 天窗口应 `<=7`）

---

### Step4：可信 LAC（先用 active_days 规则跑通）

- **输入表**：`public."Y_codex_Layer2_Step03_Lac_Stats_DB"`
- **输出表**：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`
- **主键粒度**：`operator_id_raw + tech_norm + lac_dec`
- **核心规则（当前版）**：
  - `active_days = 本周期最大 active_days`（7 天窗口可理解为“满天”）
- **核心字段**：
  - 透传 Step3 的指标列（`record_count/distinct_*/first/last/active_days/valid_gps_count`）
  - 是否可信LAC（`is_trusted_lac=true`）
- **验证 SQL（>=3）**：
  - `select count(*) from public."Y_codex_Layer2_Step04_Master_Lac_Lib";`
  - `select count(*) from public."Y_codex_Layer2_Step04_Master_Lac_Lib" where active_days <> (select max(active_days) from public."Y_codex_Layer2_Step03_Lac_Stats_DB");`
  - `select operator_id_raw, tech_norm, lac_dec, count(*) from public."Y_codex_Layer2_Step04_Master_Lac_Lib" group by 1,2,3 having count(*)>1;`
- **验收标准**：
  - 可信集合内每条记录的 `active_days` 等于 Step3 的最大值
  - 主键无重复

---

### Step5：可信映射（LAC + Cell + operator + tech）+ Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac

- **输入**：
  - `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（`is_compliant=true`）
  - `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（将映射限定在可信 LAC 内）
- **输出**：
  1. `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（可信映射统计底座）
  2. `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`（必须产出：同一 cell 对应多个 lac 的异常监测清单报表）
- **主键粒度**：
  - `Y_codex_Layer2_Step05_CellId_Stats_DB`：`operator_id_raw + tech_norm + lac_dec + cell_id_dec`
  - `Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac`：`operator_id_raw + tech_norm + cell_id_dec`（且 `count(distinct lac_dec) > 1`）
- **核心字段/指标（必须实现）**：
  - 总上报次数（`record_count`）
  - 有效GPS次数（`valid_gps_count`，`has_gps=true`）
  - 首次/末次/活跃天数（`first_seen_* / last_seen_* / active_days`）
- **验证 SQL（>=3）**：
  - `select count(*) from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" where lac_distinct_cnt <= 1;`
  - `select count(*) from public."Y_codex_Layer2_Step05_CellId_Stats_DB" where valid_gps_count > record_count;`
  - `select operator_id_raw, tech_norm, lac_dec, cell_id_dec, count(*) from public."Y_codex_Layer2_Step05_CellId_Stats_DB" group by 1,2,3,4 having count(*)>1;`
- **anomaly 查询样例（必须给出）**：
  - `select * from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac" order by lac_distinct_cnt desc, record_count desc limit 100;`
- **验收标准**：
  - `Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac` 仅包含 `lac_distinct_cnt>1` 的 cell
  - `Y_codex_Layer2_Step05_CellId_Stats_DB` 主键无重复，且 `valid_gps_count <= record_count`

---

### Step6：反哺 L0_Lac + 与 GPS 对比报表

- **输入**：
  - `public."Y_codex_Layer2_Step00_Lac_Std"`（LAC 路标准化视图）
  - `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（可信映射统计底座：`operator+tech+cell -> lac` 的候选集合）
  - `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（可信 LAC 白名单：最终 lac 必须落在此表中）
  - `public."Y_codex_Layer2_Step00_Gps_Std"` / `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（GPS 路基线/合规集，用于对比）
- **输出**：
  1. `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE）：LAC 路反哺后可信明细库（包含 `lac_dec_final/lac_enrich_status/lac_choice_cnt` 等派生列）
  2. `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`（TABLE）：对比报表（`dataset` 含：`GPS_RAW/GPS_COMPLIANT/LAC_RAW/LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL/LAC_SUPPLEMENTED_TRUSTED/LAC_SUPPLEMENTED_BACKFILLED/LAC_RAW_HAS_CELL_NO_OPERATOR`）
- **主键粒度**：
  - `Y_codex_Layer2_Step06_L0_Lac_Filtered`：行级（`seq_id`）
  - `Y_codex_Layer2_Step06_GpsVsLac_Compare`：按 `dataset + tech_norm + operator_id_raw + operator_group_hint` 聚合
- **核心对比指标**：
  - 行数（`row_cnt`）
  - 去重 cell 数（`cell_cnt`）
  - 去重 lac 数（`lac_cnt`）
  - 设备数（`device_cnt`）
- **验证 SQL（>=3）**：
  - `select dataset, sum(row_cnt) from public."Y_codex_Layer2_Step06_GpsVsLac_Compare" group by 1 order by 1;`
  - `select count(*) from public."Y_codex_Layer2_Step06_L0_Lac_Filtered" f left join public."Y_codex_Layer2_Step04_Master_Lac_Lib" t on f.operator_id_raw=t.operator_id_raw and f.tech_norm=t.tech_norm and f.lac_dec_final=t.lac_dec where t.lac_dec is null;`
  - `select operator_group_hint, tech_norm, lac_enrich_status, count(*) from public."Y_codex_Layer2_Step06_L0_Lac_Filtered" group by 1,2,3 order by 1,2,3;`
- **验收标准**：
  - 反哺后明细表中 `lac_dec_final` 必须全部命中 Step04 白名单（上面第 2 条应为 0）
  - 对比报表能清晰反映：LAC 可反哺范围、反哺后留存、实际发生补齐/纠偏的规模，以及“有 cell 无 operator”尾巴规模

---

## 4. 表清单（Layer_2 输出对象）

| 步骤 | 对象名 | 类型 | 主键粒度 | 说明 |
|---|---|---|---|---|
| Step0 | `public."Y_codex_Layer2_Step00_Gps_Std"` | VIEW | 行级（seq_id） | GPS 路标准化视图 |
| Step0 | `public."Y_codex_Layer2_Step00_Lac_Std"` | VIEW | 行级（seq_id） | LAC 路标准化视图（Step6 用） |
| Step1 | `public."Y_codex_Layer2_Step01_BaseStats_Raw"` | TABLE | 聚合维度 | Raw 基础统计 |
| Step1 | `public."Y_codex_Layer2_Step01_BaseStats_ValidCell"` | TABLE | 聚合维度 | 仅 cell 正常值过滤后的统计 |
| Step2 | `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"` | VIEW/TABLE | 行级（seq_id） | 合规标记明细（全量保留） |
| Step2 | `public."Y_codex_Layer2_Step02_Compliance_Diff"` | TABLE | 报表维度 | 合规前后对比 + TopN 原因 |
| Step3 | `public."Y_codex_Layer2_Step03_Lac_Stats_DB"` | TABLE | operator+tech+lac | 有效 LAC 汇总库 |
| Step4 | `public."Y_codex_Layer2_Step04_Master_Lac_Lib"` | TABLE | operator+tech+lac | 可信 LAC 库 |
| Step5 | `public."Y_codex_Layer2_Step05_CellId_Stats_DB"` | TABLE | operator+tech+lac+cell | 可信映射统计底座 |
| Step5 | `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"` | VIEW/TABLE | operator+tech+cell | 异常监测清单：同 cell 多 lac |
| Step6 | `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"` | TABLE | 行级（seq_id） | LAC 路反哺后可信明细库（`lac_dec_final` 等派生列） |
| Step6 | `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"` | TABLE | 报表维度 | GPS vs LAC 对比报表 |

---

## 5. SQL 文件清单（按顺序执行）

- `lac_enbid_project/Layer_2/sql/00_step0_std_views.sql`
- `lac_enbid_project/Layer_2/sql/01_step1_base_stats.sql`
- `lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql`
- `lac_enbid_project/Layer_2/sql/03_step3_lac_stats_db.sql`
- `lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql`
- `lac_enbid_project/Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql`
- `lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`
- （预埋接口）`lac_enbid_project/Layer_2/sql/90_future_interfaces_ddl.sql`

---

## 6. 未来 3 个大步骤的接口预埋（字段结构）

> 仅定义“可落地字段结构”，不在本轮实现数据填充逻辑。

### 阶段二：Cleaned_Augmented_DB（清洗补齐库）

核心字段结构建议（中文（English））：

- 主键/回溯：`src_seq_id`、`src_record_id`
- 处理状态（`status`）：Verified / Corrected_LAC / New_CellID_Candidate / Unverified_Omitted
- 原始LAC（`original_lac`）与 修正LAC（`corrected_lac`）
- GPS状态（`gps_status`）：Verified / Drift / Missing
- 数据来源（`data_source`）：APP / SS1 / ThirdParty / ...
- GPS来源（`gps_source`）：Original / Augmented_from_BS（为最终库回填预留）

### 阶段三：Master_BS_Library（基站库）

核心字段结构建议（中文（English））：

- 基站ID（`bs_id`）、扇区ID（`sector_id`）
- 基站中心点（`bs_gps_center_lon/bs_gps_center_lat`）
- 关联 LAC（`associated_lac_list` / `associated_lac_count`）
- 小区数（`cellid_count`）

### Final_Master_DB（最终主库）

核心字段结构建议（中文（English））：

- 继承 Cleaned_Augmented_DB 的记录级字段
- GPS回填标记（`gps_source`）：Original_Verified / Augmented_from_BS / ...

---

## 7. 字段字典（Data Dictionary）

详见：`lac_enbid_project/Layer_2/Data_Dictionary.md`
