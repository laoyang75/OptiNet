# Claude 审计报告

> 审计人：Claude Agent（Gemini 环境执行）
> 审计日期：2026-03-23
> 审计文档数：11（6份文档 + 4份决策记录 + 1份上下文）

---

## 审计结果

### 维度 A：完整性
**评定：通过**

**逐项检查：**

| 缺口 | 对应文档 | 内容到位 | 评估 |
|------|---------|---------|------|
| 数据起点决策 | `01_数据起点与表体系决策.md` + `Q01` | ✅ 决策明确（选 A：从 Layer0 开始），理由充分 | 通过 |
| 新旧表映射 | `02_新旧表体系映射.md` + `Q02` + `Q04` | ✅ 包含 12 张核心产物表 + 6 张辅助表的完整逐字段映射 | 通过 |
| 步骤SQL参数映射 | `03_步骤SQL参数映射.md` | ✅ 覆盖 Layer0-5 共 22 个步骤，逐步骤列出 SQL 文件、输入输出表、参数清单 | 通过 |
| 指标注册表 | `04_指标注册表.md` | ✅ 包含 13 个步骤的指标定义 + 异常统计 + 质量门控 + 维度 + 计算时机 | 通过 |
| 工作台DDL | `05_工作台元数据DDL.md` | ✅ 包含 17 张 workbench 表 + 5 张 meta 表的完整 DDL + 初始化数据 | 通过 |

**决策问题：**

| 问题 | 用户回答 | 评估 |
|------|---------|------|
| Q01 数据起点 | 选 A（从 Layer0 开始） | ✅ 明确 |
| Q02 命名策略 | 选 A（完全新命名，放独立 schema） | ✅ 明确 |
| Q03 PG17连接 | 已提供完整 DSN | ✅ 明确 |
| Q04 旧表策略 | 有效表移 legacy schema，无效表删除 | ✅ 明确 |

---

### 维度 B：一致性
**评定：部分通过**

**一致的方面：**
1. **Schema 规划**：四个 schema（legacy / pipeline / workbench / meta）在 Doc00、Doc01、Doc02、Doc05 中统一使用 ✅
2. **新表命名**：Doc01 定义的 12+6 张 pipeline 表名在 Doc02（字段映射）、Doc03（步骤映射）、Doc05（step_registry 初始数据）中统一使用 ✅
3. **参数值**：Doc03 §3 汇总的参数值与 Doc05 §5.2 默认参数集 JSON 一致 ✅
4. **字段命名规范**（dim_ / fact_ / profile_ / map_ / stats_ / detect_ / compare_）在 Doc01 和 Doc02 中一致 ✅

**发现的不一致问题：**

| # | 问题描述 | 涉及文档 | 严重程度 |
|---|---------|---------|---------|
| B-1 | **表名不一致：`raw_records` vs `raw_standardized`**。Doc01 §2.2 将数据起点命名为 `pipeline.raw_records`，Q02 选项 A 中列出的候选名为 `raw_standardized`。最终文档体系已统一为 `raw_records`，但 Q02 原文的候选名残留可能造成混淆。 | Q02 vs Doc01/Doc02/Doc03/Doc05 | 低（Q02 是决策过程记录，非规范文档） |
| B-2 | **Doc04 中出现了 Doc05 未定义的表名**。Doc04 §1.1 引用了 `workbench.wb_step_metric`（Doc05 中确实存在 §2.9），但同时引用了 `workbench.wb_layer_snapshot`、`workbench.wb_gate_result`、`workbench.wb_anomaly_stats`、`workbench.wb_reconciliation`——这些都在 Doc05 中定义 ✅。无不一致。 | Doc04 vs Doc05 | N/A（复查后无问题） |
| B-3 | **步骤编号体系的双轨制**。Doc00 §4 定义治理链路为 8 个步骤（Step 1~8），但 Doc03 使用旧的 Layer/Step 编号（Step0, Step1, ..., Step30, Step31, ..., Step40~44, Step50~52）。Doc05 的 step_registry 使用缩写 `s0`, `s1`, ..., `s52`。三套编号需要开发者理解对应关系——Doc03 §5 有映射总表但未与 Doc00 的"8个步骤"编号对齐。 | Doc00 vs Doc03 vs Doc05 | 中 |
| B-4 | **Doc05 wb_run 表的版本字段类型不统一**。`parameter_set_id` 是 `integer REFERENCES`（外键），而 `rule_set_version`、`sql_bundle_version`、`contract_version`、`baseline_version` 是 `text`（非外键引用）。Doc05 中确实定义了 `wb_rule_set`、`wb_sql_bundle`、`wb_contract`、`wb_baseline` 表，但 `wb_run` 中只有 `parameter_set_id` 使用外键引用，其余四个版本标识仅存文本值而非外键引用。这是设计选择还是遗漏？ | Doc05 §2.1 vs §2.3-2.6 | 中 |
| B-5 | **Doc05 表数量与 Doc00 §10 不一致**。Doc00 §10 列出 27 张工作台新增表名（含 wb_dataset_registry、wb_step_dataset_map、wb_step_dependency、wb_sql_asset、wb_step_sql_map、wb_metric_diff_summary、wb_distribution_snapshot、wb_issue_type、wb_issue_case、wb_sample_row、wb_rerun_scope、meta_field_dependency 等），但 Doc05 实际定义了 17 + 5 = 22 张表，许多 Doc00 中列出的表在 Doc05 DDL 中没有出现，被合并或替换了。 | Doc00 §10 vs Doc05 | 中 |
| B-6 | **Step 31 GPS 漂移距离阈值不一致**。Doc00 §4 Step 5 写"距离 ≤ 阈值（4G:1000m, 5G:500m）"，而 Doc03 §2.2 Step 31 参数 `drift_if_dist_m_gt` = 1500 米（统一的，未分 4G/5G）。到了 Layer4 Step 40（完整回归）才使用 4G:1000m / 5G:500m 的分制式阈值。Doc00 的描述将 Layer4 的阈值写在了 Step 5（Layer3 Step31）的描述里，产生混淆。 | Doc00 §4 Step5 vs Doc03 Step31 vs Doc03 Step40 | 高 |
| B-7 | **Doc04 指标 `s30_collision_suspect_cnt` 公式用 `is_collision_suspect=1`（整数）**，而 Doc02 已将该字段类型从 int 改为 boolean。应使用 `is_collision_suspect=true`。 | Doc04 §2.8 vs Doc02 §5.1 | 低（SQL 中 PG 会自动转换，但文档应一致） |

---

### 维度 C：可执行性
**评定：部分通过**

**可以直接开始编写的部分：**
1. ✅ **pipeline schema DDL**：Doc02 的逐表字段映射已包含完整字段名、数据类型、变更说明
2. ✅ **workbench/meta schema DDL**：Doc05 包含完整可执行的 CREATE TABLE SQL
3. ✅ **step_registry 初始化数据**：Doc05 §5.1 可直接执行
4. ✅ **参数集初始化数据**：Doc05 §5.2 可直接执行

**需要补充才能开始的部分：**

| # | 需补充信息 | 影响范围 | 说明 |
|---|-----------|---------|------|
| C-1 | **pipeline 表的 DDL 未直接提供**。Doc02 提供了逐字段映射表，但没有可直接执行的 `CREATE TABLE pipeline.raw_records (...)` SQL 语句。开发者需要手工将映射表转换为 DDL。 | pipeline schema 所有 18 张表 | 建议补充完整 DDL |
| C-2 | **pipeline 表的索引策略完全缺失**。Doc02 仅在旧表中提到 Step04/Step05 的索引，新表的索引设计未定义。对于 2.5 亿行的 `raw_records` 和 3050 万行的 `fact_final`，缺乏索引策略将严重影响查询性能。 | 所有 pipeline 表 | **必须补充** |
| C-3 | **pipeline.raw_records 的物化策略未明确**。Doc03 Step0 说"合并入 pipeline.raw_records（物化，非VIEW）"，但两张 Layer0 表合计 2.5 亿行 101GB，物化策略（全量 INSERT INTO 还是分批？是否需要分区？）未定义。 | raw_records 表 | 建议补充 |
| C-4 | **FastAPI 后端 API 设计文档缺失**。Doc00 §8 提到 UI 结构但未定义 API 端点。步骤执行 API、指标查询 API、对比查询 API 等接口规范未提供。 | 后端开发 | 本阶段非必须（文档阶段），但下阶段需要 |
| C-5 | **前端步骤工作台页面的数据需求未明确**。Doc00 §8 列出了 P2 步骤工作台的 8 个区块，但每个区块需要查询哪些表、哪些字段，未在文档中定义。 | 前端开发 | 本阶段非必须 |
| C-6 | **Step 0 标准化逻辑中 `tech_norm` 映射的完整映射表缺失**。Doc03 仅说"4G / 5G / 2_3G"，未列出哪些原始 `tech` 值映射到哪个类别。 | Step0 SQL 编写 | 需查阅旧 SQL 文件 |
| C-7 | **Step 6 的多 LAC 收敛逻辑较复杂**，Doc03 仅列出优先级规则（good_sig_cnt → lac_confidence_score → record_count），但完整 SQL 逻辑（如窗口函数 / 去重策略）需要参考旧 SQL 文件才能实现。 | Step6 SQL 编写 | 旧 SQL 可参考 |

---

### 维度 D：业务正确性
**评定：部分通过**

**符合业务原则的方面：**

1. ✅ **原则1（有效 cell_id = 有效上报）**：Doc03 的完整回归（Step40）明确"基于可信BS库对原始LAC明细（非Step06过滤后）进行完整GPS过滤回填"，体现了从原始数据重处理的完整回归思路。
2. ✅ **原则2（修正优于丢弃）**：Step31 GPS修正"所有情况都保留整条记录"，Step40"严重碰撞桶仍回填但强标注"。
3. ✅ **原则3（层层收敛、互相印证）**：正向 LAC→Cell→BS→GPS，反向 BS→Cell（Step35 动态检测），完整回归（Step40-41）。
4. ✅ **原则4（基线驱动）**：Doc05 定义了 wb_baseline 表，Doc00 提到伪日更四分流。

**发现的业务问题：**

| # | 问题描述 | 涉及文档 | 严重程度 |
|---|---------|---------|---------|
| D-1 | **Step 40 完整回归的输入数据源矛盾**。Doc03 Step40 输入表列出 `Y_codex_Layer0_Lac`（仅 LAC 路）；但 Doc01 决策是从 Layer0 两张表（Lac + Gps_base）合并为 `raw_records` 开始。完整回归应回到 `pipeline.raw_records`（合并后 2.5亿行），但 Step40 的旧 SQL 只处理 Layer0_Lac 路。**旧逻辑仅对 LAC 路数据做完整回归，Gps_base 路数据是否也需要回归？这涉及 3050 万 vs 可能更多行的差异。** | Doc03 Step40 vs Doc01 | 高 |
| D-2 | **Step 33 信号补齐使用的是"中位数"而非"时间最近的有信号记录"**。Doc00 §4 Step 6 明确说"同 Cell 补齐：同 cell_id 下时间最近的有信号记录作为 donor"。但 Doc03 Step33 的业务逻辑写的是"按 cell/bs 聚合信号中位数进行补齐"。而 Step41（完整回归中信号补齐）使用的才是"同cell最近时间有信号记录"策略。这两个步骤的补齐策略不同——Step33 是中位数，Step41 是最近时间点对点。Doc00 的描述将 Step41 的策略写在了 Step 6 位置。 | Doc00 §4 Step6 vs Doc03 Step33 vs Doc03 Step41 | 中（策略差异是有意设计，但 Doc00 描述不准确） |
| D-3 | **Step 5（Cell 统计）遗漏了"位置离散、偶尔出现、样本量过小"的筛选标准**。Doc00 §4 Step 3 说要"剔除：位置离散、偶尔出现、样本量过小"，但 Doc03 Step5 的参数清单仅列出"数据范围=仅可信LAC内的合规数据"和"异常条件=lac_distinct_cnt>1"，未见位置离散度、最低活跃天数、最小上报量等筛选参数。 | Doc00 §4 vs Doc03 Step5 | 中 |
| D-4 | **Step 30 BS 中心点计算说"中位数"，但实际用的是鲁棒中位数+剔漂移+重算。** Doc00 §4 Step 4 简化描述"GPS 中位数，不是平均值"，但 Doc03 Step30 显示实际算法更复杂（分桶密度→鲁棒中位数→按距离剔漂移→重算中心→信号优先 Top50）。文档间不矛盾但 Doc00 的描述过度简化。 | Doc00 vs Doc03 | 低（信息丰富度不同，非矛盾） |

---

### 维度 E：遗漏检测
**评定：部分通过**

| # | 遗漏项 | 严重程度 | 说明 |
|---|--------|---------|------|
| E-1 | **pipeline 表索引策略完全缺失** | 高 | 见 C-2。对于亿级大表 raw_records、千万级 fact_filtered / fact_gps_corrected / fact_signal_filled / fact_final，索引设计是性能关键。旧表（Step04/Step05）有索引定义，新表应继承并优化。 |
| E-2 | **4 种运行模式的差异化处理未在文档中体现** | 中 | Doc00 §6 定义了全链路重跑、局部重跑、样本重跑、伪日更 4 种模式。Doc05 `wb_run.run_mode` 字段支持这 4 种值。但文档中未说明：局部重跑如何确定从哪个步骤开始？样本重跑如何关联样本集？表级数据如何隔离不同 run 的产出？ |
| E-3 | **伪日更模式的设计仅有概念描述** | 中 | Doc00 §4 Step8 提到"四分流：范围内/漂移/新增/异常"，但未有 Doc 对四分流的判定逻辑、存储表结构、触发条件做具体定义。可理解为二期范围。 |
| E-4 | **错误处理与重试机制未定义** | 中 | Doc05 `wb_step_execution.error_message` 可记录错误，但文档中未定义：步骤失败后是否自动重试？重试策略？部分失败后如何恢复？事务边界（每步骤一个事务还是每 SQL 一个事务）？ |
| E-5 | **步骤依赖关系表缺失** | 低 | Doc00 §10.A 提到 `wb_step_dependency`，但 Doc05 DDL 中未包含此表。步骤间的依赖关系通过 step_registry 的 input_tables/output_tables 可推断，但显式依赖表更适合调度引擎使用。 |
| E-6 | **数据集注册表缺失** | 低 | Doc00 §10.C 列出 `wb_dataset_registry` 和 `wb_step_dataset_map`，Doc05 中未定义。pipeline 表与步骤的关系通过 step_registry 的 input/output_tables 隐式表达，但不够灵活（如"一步骤多产物版本"场景）。 |
| E-7 | **分区策略未定义** | 中 | raw_records 2.5 亿行、fact_final 3050 万行，是否需要按 report_date 或 operator_id_raw 分区？Doc02 和 Doc05 均未涉及。 |
| E-8 | **Step 2 合规标记的输出表在 pipeline 中无独立表** | 低 | Doc03 Step2 输出 `Y_codex_Layer2_Step02_Gps_Compliance_Marked`，但 Doc01/Doc02 中未为其分配新表名（说明是"中间产物，合并入 fact_filtered 的标准化步骤"）。但 Step3/Step5 的输入均引用此表——在新体系中，这个中间标记是在内存中(CTE/临时表)处理还是需要物化？未明确。 |
| E-9 | **RSRP 无效值判定条件 ≥0 在 Doc03 多处出现，但 Doc05 参数集仅列出 [-110, -1]** | 低 | Doc03 §3.1 全局参数写"信号无效值（RSRP）: {-110, -1, ≥0} → NULL"，但 Doc05 §5.2 参数集 JSON 中 `rsrp_invalid_values: [-110, -1]`，缺少"≥0"条件。因 ≥0 是范围而非枚举值，不适合放在数组中，需要参数化支持（如额外字段 `rsrp_max_valid`）。 |

---

## 总体评估

**结论：需修改后可开发**

文档体系已达到高完成度，5 个缺口文档内容详实，决策问题全部有明确回答。主要问题集中在一致性细节和部分遗漏项。

### 必须修改项

1. **【B-6 / D-1】修正 Doc00 §4 Step 5 的距离阈值描述**。当前写"4G:1000m, 5G:500m"实际是 Layer4 Step40 的参数，Step31 统一使用 1500m。应更正以避免开发时使用错误参数。

2. **【B-5】对齐 Doc00 §10 与 Doc05 的表清单**。Doc00 列出 27 张表名，Doc05 实际定义了 22 张。需明确说明哪些表被合并/替代，或更新 Doc00 §10。

3. **【C-1】补充 pipeline schema 的完整 DDL**。Doc02 的字段映射表需转换为可执行的 CREATE TABLE 语句（或至少为核心产物表提供 DDL）。

4. **【C-2 / E-1】补充索引策略**。至少为以下表定义核心索引：
   - `raw_records`：(operator_id_raw, tech_norm, lac_dec, cell_id_dec)
   - `fact_filtered`：(operator_id_raw, tech_norm, lac_dec_final, cell_id_dec)
   - `dim_lac_trusted`：(operator_id_raw, tech_norm, lac_dec) UNIQUE
   - `dim_cell_stats`：(operator_id_raw, tech_norm, lac_dec, cell_id_dec) UNIQUE
   - `dim_bs_trusted`：(tech_norm, bs_id, lac_dec_final) UNIQUE
   - `fact_final`：(seq_id)、(operator_id_raw, tech_norm, bs_id_final, cell_id_dec)

5. **【D-1】明确完整回归（Step40）的数据范围**。旧 SQL 仅处理 Layer0_Lac 路，需确认重构后是否需要同时回归 Layer0_Gps_base 路数据。

### 建议改进项

1. **【B-3】考虑统一步骤编号**。建议在 Doc00 的"8个步骤"描述中标注对应的技术步骤编号（如"Step 5：GPS修正 → 技术步骤 s31"），消除歧义。

2. **【B-4】wb_run 的版本引用方式统一化**。建议将 `rule_set_version`、`sql_bundle_version` 等也改为外键引用各自版本表，或说明不使用外键的设计理由。

3. **【E-2】补充运行模式的差异化文档**。至少说明局部重跑的起始步骤确定规则、样本重跑的样本集关联方式。

4. **【E-4】补充错误处理基本策略**。至少定义步骤级事务边界和失败后的恢复策略。

5. **【E-7】补充大表分区策略**。对 raw_records、fact_final 等大表评估是否需要按日期或运营商分区。

6. **【E-9】参数集中补充 RSRP 上限条件**。增加类似 `rsrp_max_valid: -1` 的参数，覆盖"≥0 → NULL"的规则。

7. **【D-2】修正 Doc00 §4 Step 6 的信号补齐描述**。Step 6（对应 Step33）使用的是中位数策略，而非"时间最近的有信号记录"。后者是 Step41 的策略。
