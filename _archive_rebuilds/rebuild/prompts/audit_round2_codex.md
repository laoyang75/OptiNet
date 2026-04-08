# 第二轮审计 — Codex Agent

> 身份：**Codex 审计 Agent（第二轮）**
> 审计目标：开发产出物的全面质量评估
> 输出路径：`rebuild/audit/audit_round2_codex.md`

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

**你必须完整读取以下所有文件，不得跳过。**

### 后端代码（8文件）
1. `rebuild/backend/app/main.py`
2. `rebuild/backend/app/core/config.py`
3. `rebuild/backend/app/core/database.py`
4. `rebuild/backend/app/api/pipeline.py`
5. `rebuild/backend/app/api/runs.py`
6. `rebuild/backend/app/api/steps.py`
7. `rebuild/backend/app/api/metrics.py`
8. `rebuild/backend/app/models/schemas.py`

### 前端代码（3文件）
9. `rebuild/frontend/index.html`
10. `rebuild/frontend/style.css`
11. `rebuild/frontend/app.js`

### Launcher（1文件）
12. `rebuild/launcher_web.py`

### 原始 V2 UI 设计（8文件，对比基准，必须全部读取）
13. `docs/data_warehouse/Pre_UI/V2/index.html` — P1 链路总览
14. `docs/data_warehouse/Pre_UI/V2/step-lac.html` — P2 步骤工作台（LAC示例）
15. `docs/data_warehouse/Pre_UI/V2/step-bs.html` — P2 步骤工作台（BS示例）
16. `docs/data_warehouse/Pre_UI/V2/step-cell.html` — P2 步骤工作台（Cell示例）
17. `docs/data_warehouse/Pre_UI/V2/step-gps.html` — P2 步骤工作台（GPS示例）
18. `docs/data_warehouse/Pre_UI/V2/fields.html` — P3 字段治理
19. `docs/data_warehouse/Pre_UI/V2/samples.html` — P4 样本研究
20. `docs/data_warehouse/Pre_UI/V2/wb.css` — 样式表

### 设计文档（4文件，参考）
21. `rebuild/docs/00_重构上下文与范围.md`（§8 UI 结构）
22. `rebuild/docs/02_新旧表体系映射.md`（表名中英文对照 + 字段映射字典）
23. `rebuild/docs/04_指标注册表.md`（指标定义）
24. `rebuild/docs/05_工作台元数据DDL.md`（workbench/meta 表定义）

---

## 3. 审计维度（4个维度，全部必须评估）

### 维度 A：性能与缓存

1. **逐个 API 分析**：列出每个 API 端点的查询复杂度，标注哪些对大表执行了全表 count(*) 或全表扫描
2. **前端数据加载分析**：前端是否每次切换页面都重新拉取？是否有任何缓存层？
3. **具体缓存方案**：
   - 后端：哪些数据适合内存缓存（TTL）？哪些适合物化视图？
   - 前端：哪些数据适合 localStorage / sessionStorage？
   - 手动刷新 vs 自动刷新：UI 如何设计刷新按钮？
4. **给出代码级修改建议**：具体到哪个文件的哪个函数怎么改

### 维度 B：UI 完整性（对比 V2 设计）

**你必须逐个读取 V2 设计的 8 个 HTML 文件，提取每个文件的功能区块，然后与当前实现对比。**

1. **P1 链路总览**（V2: index.html vs 当前: frontend/app.js loadOverview）
   - V2 有哪些区块？当前实现了哪些？缺了哪些？
2. **P2 步骤工作台**（V2: step-lac/bs/cell/gps.html vs 当前: frontend/app.js loadStep）
   - V2 定义了 8 个区块（说明/IO/规则/参数/SQL/数据变化/差异/样本），当前实现了几个？
   - 逐区块列出覆盖情况
3. **P3 字段治理**（V2: fields.html vs 当前：完全缺失？）
   - V2 的 fields.html 有什么功能？
   - 后端 meta schema 5 张表是否有对应 API？
4. **P4 样本研究**（V2: samples.html vs 当前：完全缺失？）
5. **D1 版本与运行抽屉** / **D2 SQL查看抽屉** / **D3 样本详情抽屉**
6. **输出一张完整的"V2 设计 vs 当前实现"对比矩阵**

### 维度 C：可理解性（中英文标注）

1. 列出前端展示给用户的所有英文名（表名、字段名、步骤名）
2. 检查 pipeline 表是否有 COMMENT ON TABLE / COMMENT ON COLUMN
3. 检查 wb_step_registry.step_name（中文）是否在 UI 中正确使用
4. 检查 Doc02 §2.1 的中英文映射字典是否可直接用于前端翻译
5. 提出具体的中文化方案

### 维度 D：代码质量与架构

1. SQL 注入风险检查（是否使用了 f-string 拼接 SQL？是否有参数化？）
2. 错误处理是否完善（API 错误时前端会怎样？）
3. 连接池配置是否合理
4. 前端代码是否有组件复用
5. 后端是否有 service 层抽象

---

## 4. 输出格式

```markdown
# Codex 第二轮审计报告

> 审计日期：[日期]
> 审计文件数：24

## 维度 A：性能与缓存
**评定：** [通过 / 部分通过 / 未通过]

### API 性能分析表
| API 端点 | 涉及表 | 查询类型 | 预估耗时 | 问题 |
|---------|--------|---------|---------|------|
| ... | ... | ... | ... | ... |

### 前端缓存分析
[分析结果]

### 缓存方案建议
[具体方案，代码级别]

## 维度 B：UI 完整性
**评定：** [通过 / 部分通过 / 未通过]

### V2 设计 vs 当前实现对比矩阵
| V2 组件 | V2 功能描述 | 当前状态 | 缺失项 |
|---------|-----------|---------|--------|
| P1 链路总览 | ... | ... | ... |
| P2 区块1 说明 | ... | ... | ... |
| ... | ... | ... | ... |

### 补齐建议
[具体建议]

## 维度 C：可理解性
**评定：** [通过 / 部分通过 / 未通过]
[英文名清单 + 中文化方案]

## 维度 D：代码质量与架构
**评定：** [通过 / 部分通过 / 未通过]
[具体问题]

## 总体结论
**结论：** [可用 / 需修改后可用]

### 必须修改项
| # | 优先级 | 问题 | 涉及文件 | 修改方案 | 工作量 |
|---|--------|------|---------|---------|--------|

### 建议改进项
```

---

## 5. 注意事项
- **你是最细致的审计者**，V2 vs 当前的 UI 对比矩阵是你的核心产出
- 必须实际读取每个 V2 HTML 文件，提取具体区块，不要凭想象
- 每个"部分通过"或"未通过"必须有具体的文件位置和代码行号
- 修改建议必须具体到文件名、函数名、代码片段
- 不要修改任何文件
