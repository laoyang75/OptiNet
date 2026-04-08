# 第二轮审计 — Gemini Agent

> 身份：**Gemini 审计 Agent（第二轮）**
> 审计目标：开发产出物的全面质量评估
> 输出路径：`rebuild/audit/audit_round2_gemini.md`

---

## ⚠️ 重要要求

**本次审计要求你对每个维度都给出详细的、有实质内容的评估。以下行为不可接受：**
- 仅给出"通过"而不列任何具体证据
- 用"整体不错"一类的模糊评价代替逐项检查
- 跳过 V2 HTML 文件的读取，凭假设评价 UI 完整性
- 给出的修改建议不包含文件名和具体代码位置

**你的评审结果将与 Codex 和 Claude 的报告交叉比对。如果其他 agent 发现了问题而你没有发现，将被视为审计不充分。**

---

## 1. 审计背景

第二阶段开发已完成：
- PG17 数据库 4 个 schema（legacy/pipeline/workbench/meta），68 张表有数据
- FastAPI 后端 21 个 API 端点，19 个测试通过
- 前端工作台（HTML/CSS/JS）
- Web Launcher 管理面板

**用户反馈了三个核心问题：**
1. **性能极慢**：每次打开页面实时查大表（2.5亿行 raw_records、3050万行 fact_final），需要缓存和手动刷新机制。治理链路逐步推进，前面调好的步骤不需要每次刷新。
2. **UI 与 V2 设计差距大**：原始设计有 4 主页面(P1~P4) + 3 抽屉(D1~D3)，当前只实现了粗略 P1 和简化 P2，缺失 P3 字段治理、P4 样本研究、D1~D3。
3. **英文表名不可理解**：pipeline 的 18 张新表全是英文名，用户无法理解含义，需要中文说明。

---

## 2. 待审计文件清单

**你必须完整读取以下所有文件。对于每个文件，请在报告中注明你已读取。**

### 后端代码（8文件）
1. `rebuild/backend/app/main.py`
2. `rebuild/backend/app/core/config.py`
3. `rebuild/backend/app/core/database.py`
4. `rebuild/backend/app/api/pipeline.py` — **重点：检查每个 SQL 查询的性能**
5. `rebuild/backend/app/api/runs.py`
6. `rebuild/backend/app/api/steps.py`
7. `rebuild/backend/app/api/metrics.py` — **重点：检查每个 SQL 查询的性能**
8. `rebuild/backend/app/models/schemas.py`

### 前端代码（3文件）
9. `rebuild/frontend/index.html`
10. `rebuild/frontend/style.css`
11. `rebuild/frontend/app.js` — **重点：检查数据加载和缓存策略**

### Launcher（1文件）
12. `rebuild/launcher_web.py`

### 原始 V2 UI 设计（8文件）
**你必须读取每个文件并在报告中引用其中的具体区块名称和功能描述。**
13. `docs/data_warehouse/Pre_UI/V2/index.html` — 读取后列出所有功能区块
14. `docs/data_warehouse/Pre_UI/V2/step-lac.html` — 读取后列出 P2 步骤工作台的 8 个区块
15. `docs/data_warehouse/Pre_UI/V2/step-bs.html` — 读取后对比 step-lac
16. `docs/data_warehouse/Pre_UI/V2/step-cell.html`
17. `docs/data_warehouse/Pre_UI/V2/step-gps.html`
18. `docs/data_warehouse/Pre_UI/V2/fields.html` — 读取后列出 P3 字段治理的所有功能
19. `docs/data_warehouse/Pre_UI/V2/samples.html` — 读取后列出 P4 样本研究的所有功能
20. `docs/data_warehouse/Pre_UI/V2/wb.css`

### 设计文档（4文件）
21. `rebuild/docs/00_重构上下文与范围.md`（§8 UI 结构）
22. `rebuild/docs/02_新旧表体系映射.md`（§2.1 中英文映射字典）
23. `rebuild/docs/04_指标注册表.md`
24. `rebuild/docs/05_工作台元数据DDL.md`

---

## 3. 审计维度（4个维度，全部必须详细评估）

### 维度 A：性能与缓存

**必须完成以下每一项：**

1. **API 性能逐一分析**：打开 `pipeline.py` 和 `metrics.py`，找出所有 SQL 查询，对每个查询标注：
   - 涉及哪些表
   - 是否全表扫描（count(*) FROM 大表）
   - 预估在 2.5 亿行表上的耗时
2. **前端缓存分析**：打开 `app.js`，检查：
   - 每次调用 loadOverview / loadStep 是否重新 fetch
   - 是否有任何 localStorage / sessionStorage / 变量缓存
3. **提出具体缓存方案**，包含：
   - 后端：加内存缓存的具体代码方案（带 TTL）
   - 后端：哪些查询适合用物化视图或预计算
   - 前端：哪些数据适合缓存、过期策略
   - 手动刷新按钮的 UI 位置和交互
4. **列出 Top 5 最慢的 API 调用**

### 维度 B：UI 完整性（对比 V2 设计）

**必须完成以下每一项：**

1. 读取 `V2/index.html`，列出所有功能区块（不少于 5 个），然后对比 `frontend/app.js` 的 `loadOverview` 函数
2. 读取 `V2/step-lac.html`（或任一 step 页面），列出 P2 步骤工作台的所有区块（Doc00 说有 8 个），然后对比 `loadStep` 函数
3. 读取 `V2/fields.html`，列出 P3 字段治理的功能，然后检查当前是否有任何对应实现
4. 读取 `V2/samples.html`，列出 P4 样本研究的功能
5. 检查当前是否有 D1/D2/D3 抽屉的任何实现
6. **输出一张 ≥15 行的对比矩阵**，格式如下：

| V2 组件 | V2 区块名 | V2 功能描述（从 HTML 中提取） | 当前实现状态 | 缺失程度 |
|---------|----------|--------------------------|------------|---------|

### 维度 C：可理解性（中英文标注）

**必须完成以下每一项：**

1. 打开 `app.js`，找出所有显示给用户的英文名（表名、字段名），列成清单
2. 检查 `pipeline.py` 和 `metrics.py` 的 API 响应，是否包含中文描述字段
3. 检查 `wb_step_registry` 的 `step_name`（中文）是否在前端使用
4. 阅读 `Doc02 §2.1 中英文映射字典`，提出如何在前端利用该字典
5. 提出具体中文化方案（至少 3 个层面：DB COMMENT / API 响应 / 前端翻译）

### 维度 D：代码质量与架构

**必须完成以下每一项：**

1. 检查 `pipeline.py` 中所有 SQL 拼接，是否存在 SQL 注入风险（f-string + 用户输入）
2. 检查 API 错误处理：查询失败时前端会看到什么？
3. 检查 `database.py` 的连接池配置
4. 检查后端 API 覆盖率：Doc05 定义了 22 张 workbench/meta 表，有多少张有对应 CRUD API？
5. 检查前端是否有组件化/复用（还是所有 HTML 都在 JS 字符串模板中拼接？）

---

## 4. 输出格式

```markdown
# Gemini 第二轮审计报告

> 审计日期：[日期]
> 审计文件数：24
> 已读取文件确认：[逐一列出已读取的文件名]

## 维度 A：性能与缓存
**评定：** [通过 / 部分通过 / 未通过]

### API 性能分析（逐个列出）
| # | API 端点 | SQL 查询 | 涉及表 | 是否全表扫描 | 预估耗时 |
|---|---------|---------|--------|------------|---------|

### 前端缓存分析
[具体分析]

### Top 5 最慢 API
1. ...

### 缓存方案
[代码级方案]

## 维度 B：UI 完整性
**评定：** [通过 / 部分通过 / 未通过]

### V2 vs 当前实现对比矩阵（≥15行）
| V2 组件 | V2 区块名 | V2 功能描述 | 当前状态 | 缺失程度 |
|---------|----------|-----------|---------|---------|

### 补齐建议

## 维度 C：可理解性
**评定：** [通过 / 部分通过 / 未通过]

### 前端英文名清单
[逐一列出]

### 中文化方案

## 维度 D：代码质量与架构
**评定：** [通过 / 部分通过 / 未通过]

### SQL 注入检查
[逐文件检查结果]

### API 覆盖率
| 表名 | 有 API | 缺失 API |
|------|--------|---------|

## 总体结论
**结论：** [可用 / 需修改后可用]

### 必须修改项
| # | 优先级 | 问题 | 涉及文件 | 修改方案 | 工作量 |
|---|--------|------|---------|---------|--------|

### 建议改进项
```

---

## 5. 注意事项

- **你的报告将与 Codex（最细致）和 Claude 的报告交叉比对**
- 如果你在某个维度仅给出"通过"而没有列出任何具体证据，该维度将被判定为审计不充分
- 对比矩阵必须 ≥15 行，从 V2 HTML 文件中实际提取功能描述
- API 性能分析必须逐个列出，不可以"大部分没问题"一笔带过
- 修改建议必须包含文件名、函数名、具体代码改动思路
- 不要修改任何文件
