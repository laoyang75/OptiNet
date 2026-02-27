

> 标题：Layer_3 对齐与交付要求（监督修订版 v2）
> 日期：2025-12-18
> 目的：在现有 v1 的基础上，补齐“中文友好 + 人类可快速验收”两大缺口，并形成可执行、可审计、可复跑的 Layer_3 交付包。

### 0) 你要以哪些 v1 文档为底稿修订（不要重写成另一套）

你必须以以下 v1 为“底稿”，直接修订成 v2（保留思路一致性）：

* `Layer_3_任务理解与口径对齐_v1.md`（已写清目标/依赖/决策 A~F）
* `Layer_3_执行计划_RUNBOOK_v1.md`（已有冒烟与 Summary Queries，但缺“判定标准与报告结构”）
* `Layer_3_Data_Dictionary_v1.md`（当前只列字段清单，几乎没有逐字段中文解释/取值说明/示例/验收口径）

---

### 1) 本轮“硬性问题”与修订目标（必须写进 v2 文档开头）

#### 1.1 中文友好不足（硬伤）

目前字段字典虽声明会用 COMMENT 提供中文标签，但正文基本只有字段列表，缺少逐字段中文含义、取值范围、示例、来源与计算逻辑。 
**v2 目标：做到“人类不看 SQL 也能理解每个字段”。**

#### 1.2 每步完成后的结果“不可快速判断是否满足条件”

RUNBOOK 目前提供了 Summary Queries，但没有把**验收条件 → 实际值 → Pass/Fail**做成一页式报告，人类无法快速拍板。
**v2 目标：每步执行后必须生成“可读报告”，一眼能看出是否通过、风险在哪里、要不要重跑/调参。**

---

### 2) 决策口径冻结（A~F，不再讨论，直接按此实现）

你必须原样沿用 v1 口径（仅补文档表达与验收机制）：

* 输入依赖冻结：只依赖 Layer2 Step02/04/05/06（Step06 必须 TABLE）
* A：bs_id 优先用已解析字段；缺失才按 4G/5G 回退派生
* B：共建两视角；物理分桶键字段固定 `wuli_fentong_bs_key=tech_norm|bs_id|lac_dec_final`
* C：有效 GPS 分级：`gps_valid_cell_cnt=0 不可用，=1 风险，>1 可用`，且风险可定位
* D：中心点简单鲁棒：N>=3 时最多剔 1 个最大偏移点；离散仍大则标碰撞疑似
* E：Step31 必须保留 `gps_source/gps_status` 与回溯字段
* F：信号补齐本轮做摸底 + 简单补齐（不追求最优），并输出来源分布

---

### 3) v2 交付物清单（必须交付，不少于这些）

你必须输出并提交到项目目录（按约定命名）：

#### 3.1 两份“必须文档”（你之前已经有 v1，现在升级成 v2）

1. `Layer_3_任务理解与口径对齐_v2.md`
2. `Layer_3_执行计划_RUNBOOK_v2.md`

#### 3.2 两份“为中文友好补齐的必须文档”（本轮新增为强制）

3. `Layer_3_Data_Dictionary_v2.md`（逐字段中文解释，模板见第 4 节）
4. `Layer_3_验收报告模板_v2.md`（每步报告模板，模板见第 5 节）

#### 3.3 SQL/脚本（保持 v1 的 Step30~34，补齐注释与验收输出）

* `Layer_3/sql/30_step30_master_bs_library.sql`
* `Layer_3/sql/31_step31_cell_gps_fixed.sql`
* `Layer_3/sql/32_step32_compare.sql`
* `Layer_3/sql/33_step33_signal_fill_simple.sql`
* `Layer_3/sql/34_step34_signal_compare.sql`
* `Layer_3/sql/99_layer3_comments.sql`（**强制：集中写 COMMENT，双语**）
* `Layer_3/RUNLOG_YYYYMMDD.md`（每步至少 5 条 summary 结果，沿用 v1 要求）

---

### 4) 中文友好“硬性标准”（写进 v2 文档并落实）

> 注意：中文友好不是“字段名中文”，而是“任何字段/枚举/报表行都必须有中文解释可读”。

#### 4.1 Data Dictionary v2 必须是“逐字段”字典（禁止只列字段清单）

对每张输出表（Step30/31/32/33/34），必须用 markdown 表格写清：

| 英文列名 | 中文名称 | 类型 | 可空 | 取值/范围/枚举（中文） | 来源（表.字段） | 生成逻辑（中文） | 示例值 | 人类用途（为什么要这个字段） | 相关验收SQL |
| ---- | ---- | -: | -: | ------------ | -------- | -------- | --- | -------------- | ------- |

并且：

* `gps_valid_level / gps_source / gps_status / signal_fill_source` 等枚举，必须单独开“枚举字典小节”，给中文含义、组合约束、常见错误示例。
* 对 `wuli_fentong_bs_key` 必须解释：为什么要引入 lac 分桶、它如何防止跨 LAC 错配。

#### 4.2 数据库 COMMENT 必须覆盖全部新增字段

在 `99_layer3_comments.sql` 中对**所有输出表**执行：

* `COMMENT ON TABLE ... IS '中文说明 | English description'`
* `COMMENT ON COLUMN ... IS '中文名：xxx；说明：... | English: ...'`

---

### 5) “每步可读验收报告”机制（本轮核心新增）

你必须在每一步（Step30~34）全量跑完后，产出一份 markdown 报告，路径固定：

* `Layer_3/reports/Step30_Report_YYYYMMDD.md`
* `Layer_3/reports/Step31_Report_YYYYMMDD.md`
* `Layer_3/reports/Step32_Report_YYYYMMDD.md`
* `Layer_3/reports/Step33_Report_YYYYMMDD.md`
* `Layer_3/reports/Step34_Report_YYYYMMDD.md`
* 并额外产出总览：`Layer_3/reports/Layer_3_Summary_YYYYMMDD.md`

#### 5.1 报告必须包含“一眼拍板表”（Pass/Fail 对照）

每份报告必须包含下面这张表（强制）：

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
| ------- | --------- | ---------: | ------------------ | ---- |

示例（Step30 必须至少包含这些检查项）：

* 主键是否唯一：重复数=0（FAIL 直接阻断）
* `gps_valid_level` 分布是否合理：不可全为 Unusable（WARN/FAIL 视规模）
* 中心点合法性：`Usable/Risk` 的中心点不得为 NULL，不得 (0,0)，经纬度合法（FAIL）
* 碰撞疑似规模：`is_collision_suspect=1` 数量（给出 TopN 列表，供人类抽检）

Step31 必须至少包含：

* 回溯字段空值数=0（FAIL）
* `gps_status × gps_source` 组合是否合理（例如 Augmented 不应 final=Missing）（FAIL）
* 风险基站回填规模（给数值 + TopN 样本）

Step33/34 必须至少包含：

* `signal_fill_source` 分布（none / cell_agg / bs_agg）
* 补齐前后缺失变化：after 不应 > before（WARN/FAIL）

#### 5.2 报告必须包含“可定位样本”

每步至少给 2 个 TopN 列表（每个 Top10）：

* Step30：最大离散度 Top10、碰撞疑似 Top10、风险基站 Top10
* Step31：Drift→Corrected Top10、Augmented_from_Risk_BS Top10
* Step33：补齐来源为 bs_agg 的 Top10、依然 none 的 Top10（为后续策略准备）

> 你可以用 RUNBOOK 里的 Summary Queries 做基础，但必须把“预期/阈值/结论”补上，否则人类无法快速判断。

---

### 6) 对比表结构的“人类友好增强”（建议做成 v2 必做）

你现有 Step32/34 的 compare 只是查询结果展示，不够像“验收表”。
v2 需要至少满足其中一个方案（优先方案 A）：

**方案 A（推荐）：在 Compare 表内增加可读列 + Pass 标记**

* 新增字段：`metric_code, metric_name_cn, expected_rule_cn, actual_value_num, pass_flag, remark_cn`
* 这样人类打开表就能看“哪些指标过线/没过线”，不必读 SQL。

**方案 B：保持 Compare 表不动，但把上述内容写入每步 Report.md**

* 仍然可接受，但必须保证报告“可读、可拍板”。

---

### 7) 执行模型（不变，但文档要写得更像操作手册）

继续沿用 v1：每个 Step 顶部 params 支持冒烟 → 全量后台执行。
你负责：

* 冒烟跑通、输出对象检查、报告生成、RUNLOG 记录；人类负责全量 SQL 后台执行。

---

### 8) 你交付 v2 前的自检清单（你必须逐条打钩）

* [ ] v2 字段字典逐字段中文解释齐全（不是字段清单）
* [ ] `99_layer3_comments.sql` 覆盖所有表/字段 COMMENT
* [ ] 每步都有 Report.md，包含“预期/实际/结论”对照表
* [ ] 总览报告 Summary.md 可一页判断：本轮是否通过、主要风险是什么、下一轮要怎么做
* [ ] RUNLOG 写满每步至少 5 条 Summary 结果
