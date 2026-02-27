
# Layer_3 修订任务单（给 agent 执行）v3

## 0. 背景与目标（不再讨论决策口径）

决策 A~F 已冻结（不改）。本修订仅面向“**中文友好 + 人类可快速拍板验收**”的闭环增强：

* 所有输出表/字段 **COMMENT 双语覆盖 100%**，可机器校验。
* 每步报告 “预期/实际/PASS|FAIL|WARN/样本” 可一眼拍板，**不会吞 WARN**。
* RUNBOOK / 字典 / 模板 **三者口径一致**（尤其 Step34 是否允许 WARN）。

---

## 1. 阻断级修订（CR：必须完成，否则不允许进入全量验收）

### CR-01：把“COMMENT 双语覆盖率=100%”纳入硬验收（RUNBOOK+模板都要加）

**现状依据**：字典声明权威来源是 DB COMMENT + 99_layer3_comments.sql，但 RUNBOOK/模板未强制校验覆盖率。

**你要做的修改**

1. 更新 `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`

   * 覆盖对象：Step30/30_stats/31/32/33/34 **所有表 + 所有字段**
   * 每个 comment 统一格式：
     `CN: ...中文解释...; EN: ...English description...`
2. 在 RUNBOOK v3 增加 **Gate-0（文档与可读性）** 验收步骤：先跑 comment 覆盖检查，再进入 Step30 验收。
3. 在每份 Step 报告模板顶部增加 “DB COMMENT 覆盖情况” 一行（可复用同一检查 SQL 输出）。

**必须新增的验收 SQL（人类后台执行，agent 复核 PASS/FAIL）**

* 输出：每表 total_cols/missing_comment_cols/not_bilingual_cols
* 判定：任一 missing>0 或 not_bilingual>0 ⇒ **FAIL 阻断**

> SQL 内容按我上一轮给的版本写入 RUNBOOK/模板（可以放在总览报告中复用一次即可）。

**交付物**

* 更新后的 `99_layer3_comments.sql`
* RUNBOOK v3 增加 Gate-0 + SQL
* 报告模板 v3 增加 comment 检查项

---

### CR-02：修复 Step32 汇总会“吞 WARN”的问题（模板必须改）

**现状依据**：模板 Step32 用 `min(pass_flag)` 聚合，会在 PASS/WARN/FAIL 混合时错误隐藏 WARN。

**你要做的修改**

1. 修改 `Layer_3_验收报告模板` 的 Step32 汇总 SQL：

   * 禁止 `min(pass_flag)`
   * 必须用优先级：**FAIL > WARN > PASS**
2. 同步修改 RUNBOOK 中任何同类写法。

**验收标准**

* 汇总表必须给出 `overall_flag`，且规则符合优先级（FAIL 优先、WARN 次之）。

**交付物**

* `Layer_3_验收报告模板_v3.md`（Step32 汇总 SQL 已替换）
* RUNBOOK v3 同步替换

---

### CR-03：统一 Step34 的 WARN 口径（字典/Runbook/模板三者必须一致）

**现状依据**：字典 Step34 的 pass_flag=PASS/FAIL；模板却查 FAIL/WARN；RUNBOOK 又把 WARN 绑定到 Step33 的 none 占比。

**你必须选择并落地其一（推荐 A）**

**方案 A（推荐，最少改动）**

* Step34 指标表 `pass_flag` 只允许 PASS/FAIL（保持字典不变）。
* “signal_fill_source='none' 占比异常高”的 WARN **只出现在 Step33 报告**。
* 修改 Step34 报告模板：把 `where pass_flag in ('FAIL','WARN')` 改为只查 FAIL。
* 修改 RUNBOOK：Step34 不再描述 WARN；WARN 只在 Step33。

**方案 B（如果业务强需要 Step34 也出 WARN）**

* 扩展 Step34 指标表：新增可 WARN 的 metric_code（例如 NONE_RATIO），并修改字典枚举与模板、RUNBOOK 全部同步。

**验收标准**

* 三份材料对 Step34 的 pass_flag 枚举、查询过滤、判定口径 **一致**。

**交付物**

* 字典 v3 + RUNBOOK v3 + 模板 v3（口径统一）

---

## 2. 强烈建议修订（SR：不阻断，但会显著提升“可拍板/可复现”）

### SR-01：把所有“异常高/规模异常”写成量化阈值（默认值+可调）

**现状依据**：RUNBOOK 多处写“异常高”，缺阈值，导致不同审核人结论不一致。

**你要做的修改**

1. 在 RUNBOOK v3 增加一节《默认阈值表》（可配置参数）

   * Step30：Unusable 占比 WARN 阈值；collision 占比 WARN 阈值
   * Step31：Risk 回填占比 WARN 阈值；Drift 占比 WARN 阈值
   * Step33：none 占比 WARN 阈值；bs_agg 占比 WARN 阈值（可选）
2. 每个 WARN 在报告里必须附：**占比、阈值、Top10 样本、建议动作**。

**验收标准**

* RUNBOOK/模板中出现 “异常高/规模异常” 的地方全部替换为 “>X% 或 >N 条”。

---

### SR-02：新增 4 条“跨步一致性”硬检查（推荐 FAIL）

目的：拦截“行数丢失/键不一致/join 失败/枚举脏值”类事故。

**必须加到 RUNBOOK 的验收 SQL（建议放在 Step31/Step33 前后）**

1. 行数一致：Step31_cnt == Step06_cnt；Step33_cnt == Step31_cnt
2. Step31 join Step30 覆盖率：gps_valid_level/is_collision_suspect/is_multi_operator_shared 不得为 null
3. wuli_fentong_bs_key 符合 `concat_ws('|', tech_norm, bs_id, lac_dec_final)`（Step30、Step31 都要验）
4. 枚举合法性：gps_source、gps_status(_final)、signal_fill_source、pass_flag 集合校验

**验收标准**

* 任一 bad_cnt>0 ⇒ **FAIL 阻断**（除非在“任务理解”里明确允许过滤并写出预期比例）

---

### SR-03：落实“中文友好解释”到 Step31（满足冻结决策 E 的落地体验）

**现状依据**：字典已解释 gps_source/gps_status，但缺“面向业务的一句话解释产物”。

**二选一实现（任选其一即可）**

* 方案 1（推荐）：Step31 表新增 `gps_fix_reason_cn`（文本）
* 方案 2：不改表，但 Step31 报告必须生成“解释段落”，逐 gps_source 输出中文原因说明

**验收标准**

* Step31 报告中必须出现：

  * 各 gps_source 含义解释（中文）
  * Risk 回填为什么是风险（中文）
  * Drift 纠偏规则（中文）

---

## 3. agent 必须输出的 v3 交付物（清单式验收）

### 3.1 文档（必须）

1. `Layer_3_任务理解与口径对齐_v3.md`（只做口径一致性修订：Step34 枚举一致、补充“跨步一致性”说明）
2. `Layer_3_执行计划_RUNBOOK_v3.md`（加入 Gate-0、阈值表、跨步一致性、Step34 口径统一）
3. `Layer_3_Data_Dictionary_v3.md`（Step34 枚举一致、补充枚举集合校验项、可选 gps_fix_reason_cn）
4. `Layer_3_验收报告模板_v3.md`（修 Step32 汇总不吞 WARN；Step34 口径统一；新增 comment 检查项）

### 3.2 SQL（必须）

1. 更新后的 `99_layer3_comments.sql`（双语 + 全覆盖）
2. 如选择 SR-02：新增或补齐若干 “验收 SQL 块”（可写入报告模板，不强制成独立文件）

### 3.3 报告产出规则（必须）

* 每步报告 “一眼拍板表” 必须包含：

  * 检查项（中文）/阈值（中文）/实际值/结论/处理建议
  * FAIL ⇒ 明确阻断原因与排查路径
  * WARN ⇒ 必须 Top10 样本 + 是否接受
* Summary 报告必须包含：

  * Step30~34 每步总判定（PASS/FAIL/WARN）
  * Top3 风险（collision、Risk 回填、signal none）
  * 参数变更记录（阈值/漂移阈值等）

---

## 4. 最终判定规则（写入 RUNBOOK v3 的“拍板口径”）

* **FAIL（阻断）**：

  * CR-01/02/03 任一未满足；或任一步验收 SQL bad_cnt>0（定义为 FAIL 的项）
* **WARN（可继续）**：

  * 只有被定义为 WARN 的项触发，且报告提供 Top10 样本 + 解释 + 后续动作
* **PASS**：

  * 无 FAIL、无 WARN（或 WARN 已被明确接受并记录）

