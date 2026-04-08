# 第二轮审计 — Claude Agent

> 身份：**Claude 审计 Agent（第二轮）**
> 审计目标：开发产出物的全面质量评估
> 输出路径：`rebuild/audit/audit_round2_claude.md`

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
13. `docs/data_warehouse/Pre_UI/V2/index.html`
14. `docs/data_warehouse/Pre_UI/V2/step-lac.html`
15. `docs/data_warehouse/Pre_UI/V2/step-bs.html`
16. `docs/data_warehouse/Pre_UI/V2/step-cell.html`
17. `docs/data_warehouse/Pre_UI/V2/step-gps.html`
18. `docs/data_warehouse/Pre_UI/V2/fields.html`
19. `docs/data_warehouse/Pre_UI/V2/samples.html`
20. `docs/data_warehouse/Pre_UI/V2/wb.css`

### 设计文档（4文件，参考）
21. `rebuild/docs/00_重构上下文与范围.md`（§8 UI 结构）
22. `rebuild/docs/02_新旧表体系映射.md`（表名中英文对照 + 字段映射字典）
23. `rebuild/docs/04_指标注册表.md`（指标定义）
24. `rebuild/docs/05_工作台元数据DDL.md`（workbench/meta 表定义）

---

## 3. 审计维度（4个维度，全部必须评估）

### 维度 A：性能与缓存

1. 逐个 API 分析查询复杂度，标注大表全表扫描
2. 前端数据加载策略分析
3. 提出分层缓存方案：
   - DB 层：物化视图 / 预计算汇总表
   - 后端层：内存缓存（TTL 策略）
   - 前端层：localStorage / sessionStorage
4. 手动刷新 vs 自动刷新的 UI 交互设计
5. 代码级修改建议

### 维度 B：UI 完整性（对比 V2 设计）

**必须读取 V2 设计的 8 个 HTML 文件，逐组件与当前实现对比。**

1. P1 链路总览对比
2. P2 步骤工作台 8 区块逐一对比
3. P3 字段治理（V2 fields.html vs 当前）
4. P4 样本研究（V2 samples.html vs 当前）
5. D1/D2/D3 抽屉
6. 输出完整对比矩阵

### 维度 C：可理解性（中英文标注）

1. 列出前端所有英文文本
2. 检查 COMMENT ON TABLE
3. 检查 step_name 中文使用情况
4. 提出中文化方案

### 维度 D：代码质量与架构

1. SQL 注入风险
2. 错误处理
3. 连接池配置
4. 后端 API 覆盖率（哪些 workbench/meta 表没有 API？）
5. 前端架构（组件复用、状态管理）

---

## 4. 输出格式

```markdown
# Claude 第二轮审计报告

> 审计日期：[日期]
> 审计文件数：24

## 维度 A：性能与缓存
**评定：** [通过 / 部分通过 / 未通过]
[逐 API 性能分析 + 缓存方案]

## 维度 B：UI 完整性
**评定：** [通过 / 部分通过 / 未通过]

### V2 vs 当前对比矩阵
| V2 组件 | V2 功能 | 当前状态 | 缺失项 |
|---------|--------|---------|--------|

### 补齐建议

## 维度 C：可理解性
**评定：** [通过 / 部分通过 / 未通过]
[中文化方案]

## 维度 D：代码质量与架构
**评定：** [通过 / 部分通过 / 未通过]

## 总体结论
**结论：** [可用 / 需修改后可用]

### 必须修改项
| # | 优先级 | 问题 | 涉及文件 | 修改方案 | 工作量 |
|---|--------|------|---------|---------|--------|

### 建议改进项
```

---

## 5. 注意事项
- 四个维度同等重要，不可偏科
- 必须读取 V2 HTML 文件做实际对比，不要凭假设
- 修改建议具体到文件名、函数名
- 不要修改任何文件
