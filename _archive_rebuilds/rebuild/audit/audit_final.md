# 最终审计报告

> 合并日期：2026-03-23
> 审计来源：Codex Agent / Claude Agent / Gemini Agent

## 1. 维度评定总表

| 维度 | Codex | Claude | Gemini | 合并判定 |
|------|-------|--------|--------|---------|
| A 完整性 | 部分通过 | 通过 | 通过 | ✅ 基本通过（附注意事项） |
| B 一致性 | 未通过 | 部分通过 | 通过 | ⚠️ 需关注 |
| C 可执行性 | 未通过 | 部分通过 | 通过 | ⚠️ 需关注 |
| D 业务正确性 | 部分通过 | 部分通过 | 通过 | ⚠️ 需关注 |
| E 遗漏检测 | 未通过 | 部分通过 | 通过 | ⚠️ 需关注 |

---

## 2. 各维度详细分析

### 维度 A：完整性
**合并判定：** ✅ 基本通过

#### 各 Agent 评定
- Codex：部分通过 — 指标注册表缺少 Step32/34/35/36/37/42/43/44；Doc00/context.md 仍写 27 张表
- Claude：通过 — 5 个缺口文档内容详实，决策问题全部明确
- Gemini：通过 — 所有文档就位且充实

#### 裁定
Codex 指出的"指标注册表未覆盖全部步骤"属实——Doc04 确实缺少对比报表步骤和附加步骤的指标。"27 vs 22 表"也属实。但这些是细节遗漏而非框架缺失。**判定基本通过，需补齐遗漏指标并对齐表数量描述。**

---

### 维度 B：一致性
**合并判定：** ⚠️ 需关注

#### 各 Agent 评定
- Codex：未通过 — 6 个一致性问题（完整回归口径、operator_id_raw 语义、27vs22 表、参数不一致、步骤编号不齐、列数统计不一致）
- Claude：部分通过 — 7 个问题（步骤编号双轨制、wb_run 外键不统一、27vs22 表、距离阈值混淆、is_collision_suspect 写法）
- Gemini：通过 — 未发现问题

#### 裁定
Codex 和 Claude 指出的问题经核实均属实：

| # | 问题 | 核实结果 | 处理 |
|---|------|---------|------|
| 1 | Doc00/context.md 写 27 表，Doc05 实际 22 表 | 属实 | **必须修改** Doc00 和 context.md |
| 2 | Doc02 列数统计不一致（总览 vs 逐表） | 属实，fact_filtered 50→56，fact_final 70→74 | **必须修改** Doc02 总览表 |
| 3 | Doc03 汇总参数表缺少部分参数 | 属实，缺 center_bin_scale 等 | **必须修改** Doc03 |
| 4 | Doc05 rsrp_invalid_values 缺少 ≥0 条件 | 属实 | **必须修改** Doc05 参数集 |
| 5 | Step50/51/52 参数名不统一（min_rows_lac vs min_rows） | 属实 | **必须修改** 统一命名 |
| 6 | Step31 距离阈值在 Doc00 描述不准确 | 属实，Doc00 写了 Step40 的阈值 | **必须修改** Doc00 |
| 7 | is_collision_suspect=1 vs =true | 属实，Doc04 仍用旧写法 | 低优先级修改 |

---

### 维度 C：可执行性
**合并判定：** ⚠️ 需关注

#### 各 Agent 评定
- Codex：未通过 — 中间表占位符、Step36 输入不对、无索引/分区、运行模式不完整
- Claude：部分通过 — pipeline DDL 缺失、索引缺失、物化策略不明
- Gemini：通过 — 可直接开发

#### 裁定
核心问题：
1. **pipeline 表索引策略缺失** — Codex 和 Claude 均指出，对亿级大表确实必须补充。
2. **wb_step_registry 中间表占位符** — `(intermediate)`/`(compliant_records)` 等确实需要明确。
3. **Step36 输入表不对** — 旧 SQL 输入是 Final_BS_Profile，新表映射到 dim_bs_trusted 缺少 bs_id_hex。属实，需补充该字段或调整逻辑。
4. **wb_run 缺少运行模式关键字段** — 局部重跑、样本重跑需要额外字段。

pipeline DDL 可从 Doc02 推导（Gemini 观点正确），但索引/分区策略确实需要补充。

---

### 维度 D：业务正确性
**合并判定：** ⚠️ 需关注

#### 各 Agent 评定
- Codex：部分通过 — 完整回归口径不清、operator_id_raw 不清、Step44 断链
- Claude：部分通过 — Step40 数据源矛盾、Step33 vs Step41 补齐策略混淆
- Gemini：通过

#### 裁定
核心问题：
1. **Step40 完整回归数据源** — 旧 SQL 仅处理 Layer0_Lac，Doc01 决策是从两张 Layer0 开始。需明确重构后 Step40 的输入是 `pipeline.raw_records`（合并后）。
2. **Step33 vs Step41 信号补齐策略差异** — Step33 用中位数（摸底），Step41 用最近时间点对点（精确）。这是有意设计，但 Doc00 描述不准确。
3. **operator_id_raw** — 实际在旧 SQL 中就是 PLMN 码（46000 等），operator_group_hint 才是 CMCC/CUCC/CTCC。Doc03 Step0 描述不准确。

---

### 维度 E：遗漏检测
**合并判定：** ⚠️ 需关注

#### 各 Agent 评定
- Codex：未通过 — 5 个遗漏项
- Claude：部分通过 — 9 个遗漏项
- Gemini：通过

#### 裁定
| 遗漏项 | Codex | Claude | 处理 |
|--------|-------|--------|------|
| pipeline 索引/分区策略 | ✓ | ✓ | **必须补充** |
| 运行模式差异化设计 | ✓ | ✓ | **必须补充**（wb_run 增加字段） |
| 错误处理/重试机制 | ✓ | ✓ | 建议补充（非一期阻塞） |
| 步骤依赖表 | ✓ | ✓ | 建议补充 |
| 伪日更详细设计 | — | ✓ | 二期范围，记录即可 |

---

## 3. 必须修改项清单

| # | 涉及维度 | 问题描述 | 涉及文档 | 建议修改方式 | 提出者 |
|---|---------|---------|---------|------------|--------|
| 1 | B | Doc00/context.md 写 27 表，实际 22 表 | Doc00, context.md | 更新表数量描述 | Codex+Claude |
| 2 | B | Doc02 总览表列数与逐表映射不一致 | Doc02 §1.2 | 修正 fact_filtered→56, fact_final→74 | Codex |
| 3 | B | Doc03 汇总参数表缺少 center_bin_scale、grid_round_decimals 等 | Doc03 §3.2 | 补全所有步骤级参数 | Codex |
| 4 | B | Doc05 rsrp_invalid_values 缺少 ≥0 条件 | Doc05 §5.2 | 增加 rsrp_max_valid 参数 | Codex+Claude |
| 5 | B | Step50/51/52 参数名不统一 | Doc03 §3.2, Doc05 §5.2 | 统一为 min_rows（参数集内按步骤区分） | Codex |
| 6 | A | Doc04 缺少 Step32/34/35/36/37/42 指标 | Doc04 | 补齐对比报表和附加步骤的指标 | Codex |
| 7 | C | wb_run 缺少运行模式关键字段 | Doc05 §2.1 | 增加 rerun_from_step, sample_set_id | Codex+Claude |
| 8 | C | wb_step_registry 中间表占位符 | Doc05 §5.1 | 明确临时物化策略或改为实际表名 | Codex |
| 9 | D | Step40 完整回归数据源需明确 | Doc03 Step40 | 明确输入为 pipeline.raw_records | Codex+Claude |
| 10 | C+E | pipeline 表索引策略缺失 | Doc02 | 补充核心索引定义 | Codex+Claude |
| 11 | D | Doc00 Step5 距离阈值描述不准确 | Doc00 §4 | 修正为 Step31 的 1500m | Claude |
| 12 | D | Doc03 Step0 operator_id_raw 语义描述不准确 | Doc03 §2.1 | 明确 operator_id_raw=PLMN码, operator_group_hint=运营商组 | Codex |

---

## 4. 建议改进项清单

| # | 建议内容 | 提出者 | 优先级 |
|---|---------|--------|--------|
| 1 | 增加"步骤→输入表→输出表→指标→门控"总矩阵 | Codex | 高 |
| 2 | pipeline 表生成独立 DDL 脚本（06_pipeline_ddl.sql） | Gemini | 高 |
| 3 | wb_run 版本字段统一为外键引用 | Claude | 中 |
| 4 | 补充错误处理/重试基本策略 | Codex+Claude | 中 |
| 5 | 补充大表分区策略评估 | Claude | 中 |
| 6 | Doc00 的"8步骤"描述标注技术步骤编号 | Claude | 低 |
| 7 | 补充 API 端点最小契约示例 | Codex | 低（二期） |

---

## 5. 最终结论

**结论：需修改后可开发**

**理由：**
文档体系已达到高完成度，5 个缺口文档内容详实，业务逻辑大方向正确。但存在 12 个必须修改项，主要集中在文档间一致性（表数量、列数、参数名）和关键遗漏（索引策略、运行模式字段、部分步骤指标）。这些问题不影响整体架构设计，但会导致开发时产生歧义或需要反推。

**下一步行动：**
1. 按必须修改项清单逐项修复文档
2. 修复后可直接进入开发阶段，建议开发启动顺序：
   - 第一步：创建 4 个 schema + pipeline DDL + workbench/meta DDL
   - 第二步：实现 Step0~Step6（Layer2 标准化与合规筛选）
   - 第三步：实现 Step30~Step37（Layer3 BS主库与修正）
   - 第四步：实现 Step40~Step41（Layer4 完整回归）
   - 第五步：实现 Step50~Step52（Layer5 画像）
   - 第六步：实现工作台 API 和前端
