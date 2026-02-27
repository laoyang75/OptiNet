# Layer_2（北京明细 20251201_20251207）Technical Manual

> Version: 1.0  
> Date: 2025-12-19  
> Scope: Layer_0 → Layer_2（Step00~Step06）  
> Status: In-use

## 1. 概述（Overview）

Layer_2 的定位：把 Layer_0 的“北京明细上报数据”整理成一套 **可信、可复跑、可审计** 的标准化底座，为 Layer_3（基站库/GPS修正/信号补齐）提供输入。

- 输入：`public."Y_codex_Layer0_Gps_base"`、`public."Y_codex_Layer0_Lac"`
- 输出（固定命名）：`public."Y_codex_Layer2_StepXX_*"`（Step00~Step06）
- 核心原则：
  1) **行级合规优先**：Step02 不合规的记录不进入 Step03+ 的统计底座  
  2) **口径可解释**：不强制中文列名，但必须通过 COMMENT 提供中文解释  
  3) **可重跑**：每个 Step SQL 自包含必要索引/清理旧命名兼容逻辑

本层执行手册：`lac_enbid_project/Layer_2/RUNBOOK_执行手册.md`

## 2. 核心架构（Architecture）

Layer_2 是“清洗+建库”的流水线：

1) **标准化（Step00）**：对原始字段做派生与统一（制式、运营商、时间、派生 key）
2) **摸底统计（Step01）**：回答“数据量/缺失结构/来源分布”
3) **绝对合规过滤（Step02）**：定义后续可用样本集合（is_compliant）
4) **LAC 统计库（Step03, XL）**：按 `(operator_id_raw, tech_norm, lac_dec)` 聚合 7 天统计
5) **可信 LAC 库（Step04）**：基于稳定性与规模门槛筛选可信 LAC（并提供置信度）
6) **cell→lac 映射底座（Step05, XL）**：为 Step06/Layer_3 提供映射证据 + 多LAC异常监测清单
7) **反哺与归一（Step06, XL）**：把“可信映射”回写到 LAC 明细中，产出可信明细库 `Step06_L0_Lac_Filtered`

## 3. 执行顺序（Execution Order）

严格按文件名顺序执行（服务器建议 `psql -f`）：

1. `lac_enbid_project/Layer_2/sql/00_step0_std_views.sql`
2. `lac_enbid_project/Layer_2/sql/01_step1_base_stats.sql`
3. `lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql`
4. `lac_enbid_project/Layer_2/sql/03_step3_lac_stats_db.sql`（XL）
5. `lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql`
6. `lac_enbid_project/Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql`（XL）
7. `lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`（XL）

## 4. 分步说明（Step-by-Step）

### Step00：标准化视图（不改原表）

- 文件：`lac_enbid_project/Layer_2/sql/00_step0_std_views.sql`
- 目的：统一字段口径，派生 `operator_id_raw` / `device_id` / `tech_norm` / `report_date` / `bs_id` / `sector_id` 等
- 输出：
  - `public."Y_codex_Layer2_Step00_Gps_Std"`（VIEW）
  - `public."Y_codex_Layer2_Step00_Lac_Std"`（VIEW）

关键点：
- `report_date` 来自 `ts_std::date`（不是 `cell_ts_std`）
- `device_id` 使用 `did/oaid` 兜底归一（用于去重设备数/活跃天数）

### Step01：基础统计（Raw + ValidCell）

- 文件：`lac_enbid_project/Layer_2/sql/01_step1_base_stats.sql`
- 目的：建立“输入画像”，并给后续异常解释提供基线对照
- 输出：
  - `public."Y_codex_Layer2_Step01_BaseStats_Raw"`
  - `public."Y_codex_Layer2_Step01_BaseStats_ValidCell"`（应用 cell 数值起点规则后的统计）

### Step02：合规标记（行级绝对合规）

- 文件：`lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql`
- 目的：把“是否进入后续统计”的规则前置成可审计字段 `is_compliant`
- 输出：
  - `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（VIEW）
  - `public."Y_codex_Layer2_Step02_Compliance_Diff"`（TABLE）

关键规则（工程实现必须一致）：
- 运营商在范围：`46000/46001/46011/46015/46020`
- 制式：只把 4G/5G 进入主流程（其它制式保留但不会进入 Step03+）
- 明确剔除占位/溢出值：
  - LAC：`FFFF/FFFE/FFFFFF/7FFFFFFF` 等
  - CELL：`2147483647` 等

### Step03：有效 LAC 汇总库（XL）

- 文件：`lac_enbid_project/Layer_2/sql/03_step3_lac_stats_db.sql`
- 目的：在合规集上构建 `(operator_id_raw, tech_norm, lac_dec)` 的 7 天统计主表
- 输出：`public."Y_codex_Layer2_Step03_Lac_Stats_DB"`

### Step04：可信 LAC 库（含置信度）

- 文件：`lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql`
- 目的：
  1) 在 Step03 的 LAC 统计上筛“可信 LAC”（白名单）
  2) 为后续“多 LAC 小区收敛”提供 **LAC 区域置信度**
- 输出：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`

关键点（与讨论一致）：
- 排除 LAC 溢出/占位值（避免误纳入白名单）
- `lac_confidence_score`：默认使用 `valid_gps_count`（即该 LAC 的有效 GPS 上报量；越大越“稳定可信”）

### Step05：cell→lac 映射证据底座 + 多LAC异常监测清单（XL）

- 文件：`lac_enbid_project/Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql`
- 目的：
  - 构建 `(operator_id_raw, tech_norm, cell_id_dec, lac_dec)` 的证据表（上报量/设备数/天数/GPS中心点等）
  - 识别“同一 cell 多 LAC”的异常集合，为后续止损与收敛提供异常监测信号
- 输出：
  - `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（TABLE）
  - `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`（VIEW）

### Step06：反哺 LAC 明细 + 多LAC收敛 + 信号字段清洗（XL）

- 文件：`lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`
- 目的：
  1) 把“可信 LAC / cell→lac 映射证据”反哺到 LAC 明细，形成可直接用于 Layer_3 的可信明细库
  2) 对“多 LAC 小区”收敛到主 LAC（避免口径抖动）
  3) 清洗无效信号值，为后续补数/聚合打底
- 输出：
  - `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE，Layer_3 硬依赖）
  - `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`（TABLE，对比报表）

多 LAC 收敛规则（工程实现要点）：
1) 仅对多 LAC cell 生效：`lac_choice_cnt>1`
2) **过滤无效信号**：`sig_rsrp IN (-110,-1) OR sig_rsrp>=0` 视为无效
3) 主 LAC 选择顺序：
   - `good_sig_cnt`（有效 RSRP 上报量）最大者优先
   - tie-break：`Step04.lac_confidence_score` 更大者优先
   - tie-break：`row_cnt` 更大者优先
   - 最终：`lac_dec` 更小者（保证稳定）

无效 RSRP 清洗（你已确认）：
- 在 Step06 末尾执行：`UPDATE ... SET sig_rsrp=NULL WHERE sig_rsrp IN (-110,-1) OR sig_rsrp>=0;`

## 5. 输出数据字典（Schema）

本层字段的权威字典与 COMMENT 以各 SQL 文件内 `COMMENT ON ...` 为准。

工程人员最常用的输出对象：
- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`：下游所有 Layer_3 分桶/回填/画像的输入底座
- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`：映射证据底座（排障/解释多LAC/碰撞）
- `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`：可信 LAC 白名单 + 置信度

## 6. 验收与自检（Verification）

最低验收（建议每次重跑后都执行）：

1) 输出对象存在且类型正确（Step06 必须是 TABLE）
2) 主键唯一性检查（Step03/04/05 的 pk/unique 索引应生效）
3) Step06 行数与预期一致（与输入窗口一致；不应异常膨胀）

更多可执行的验收 SQL 见：`lac_enbid_project/Layer_2/RUNBOOK_执行手册.md`

## 7. 常见问题（Troubleshooting）

1) `DO $$ ... $$` 执行失败  
- 现象：控制台按 `;` 拆分语句导致块失败  
- 处理：统一用 `psql -f` 执行整文件

2) Step06 极慢 / temp_files 爆炸  
- 原因：大表 join 触发 merge join/sort/hash spill  
- 处理：Step06 已内置关闭 mergejoin/并行 gather，并采用“先物化小表/必要范围明细”的两段式设计；仍慢时需要按 RUNBOOK 做拆分跑/分批策略
