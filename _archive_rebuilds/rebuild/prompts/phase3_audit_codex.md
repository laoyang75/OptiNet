# 第三阶段审计 — Codex Agent

> 身份：**Codex 审计 Agent（第三阶段）**
> 审计目标：对 Phase 3 全部开发产出做独立质量评估，对照 `phase3_final.md` 的 13 个任务和 6 个关键决策，逐项核验是否真正落地
> 输出路径：`rebuild/audit/phase3_audit_codex.md`

---

## 1. 审计背景

第三阶段的开发计划来自 `rebuild/audit/phase3_final.md`，该计划由 Codex / Claude / Gemini 三方独立审计后合并裁决生成。现在需要核验执行结果是否完整、正确地实现了计划中的所有要求。

第三阶段的核心目标：
1. **M1 架构与历史正确性**：拆分 2045 行 `workbench.py` 和 1184 行 `app.js`；修复 run 绑定参数；历史快照只读
2. **M2 字段治理闭环**：新增源字段合规 DDL/种子/API/P3 页面重做
3. **M3 V2 关键交互补齐**：P2 参数/对象 diff；P4 筛选；D1 版本变化；D3 增强
4. **M4 门控与中文化收口**：Gate 补齐；中文覆盖率 > 80%

---

## 2. 待审计文件清单

**你必须完整读取以下所有文件，不得跳过任何一个。**

### 核心计划（审计基准）
1. `rebuild/audit/phase3_final.md` — 唯一主计划，所有核验以此为准
2. `rebuild/prompts/context.md` — 项目背景

### 后端服务层（7 文件 — 由 T01 拆分产出）
3. `rebuild/backend/app/services/workbench/__init__.py` — 兼容 facade
4. `rebuild/backend/app/services/workbench/base.py` — 共用 helper
5. `rebuild/backend/app/services/workbench/catalog.py` — 引导数据、版本上下文
6. `rebuild/backend/app/services/workbench/snapshots.py` — 快照计算、Gate
7. `rebuild/backend/app/services/workbench/steps.py` — P2 步骤读模型
8. `rebuild/backend/app/services/workbench/fields.py` — 字段治理 + 源字段合规
9. `rebuild/backend/app/services/workbench/samples.py` — 样本集

### 后端 API 层（6 文件）
10. `rebuild/backend/app/main.py` — FastAPI 入口
11. `rebuild/backend/app/api/steps.py` — 步骤 API（含 T03 参数修正、T09 diff）
12. `rebuild/backend/app/api/runs.py` — Run API（含 T04 快照触发）
13. `rebuild/backend/app/api/workbench.py` — 版本/字段/样本 API（含 T11 change-log）
14. `rebuild/backend/app/api/metrics.py` — 指标 API（含 T12 gate-results）
15. `rebuild/backend/app/api/source_fields.py` — 源字段 API（T06 新增）

### 后端支撑
16. `rebuild/backend/app/services/labels.py` — 中文标签字典
17. `rebuild/backend/app/services/cache.py` — 缓存层

### 前端（10 文件 — 由 T02 拆分产出）
18. `rebuild/frontend/index.html` — 入口（须为 `type="module"`）
19. `rebuild/frontend/style.css` — 样式（含 P3 新增样式）
20. `rebuild/frontend/js/main.js` — 路由、全局事件
21. `rebuild/frontend/js/core/api.js` — fetch 封装
22. `rebuild/frontend/js/core/state.js` — 全局状态
23. `rebuild/frontend/js/ui/common.js` — 公共 UI 组件
24. `rebuild/frontend/js/ui/drawers.js` — D1/D2/D3 抽屉
25. `rebuild/frontend/js/pages/overview.js` — P1 总览
26. `rebuild/frontend/js/pages/step.js` — P2 步骤
27. `rebuild/frontend/js/pages/fields.js` — P3 字段治理（T08 重做）
28. `rebuild/frontend/js/pages/samples.js` — P4 样本研究（T10 增强）

### SQL（2 文件 — T05 新增）
29. `rebuild/sql/04_phase3_field_governance.sql` — 字段治理 DDL
30. `rebuild/sql/05_phase3_field_governance_seed.sql` — 种子数据

### V2 原型（对比基准）
31. `docs/data_warehouse/Pre_UI/V2/fields.html` — P3 原型
32. `docs/data_warehouse/Pre_UI/V2/samples.html` — P4 原型
33. `docs/data_warehouse/Pre_UI/V2/index.html` — P1 原型
34. `docs/data_warehouse/Pre_UI/V2/step-lac.html` — P2 原型

### 设计文档（参考）
35. `rebuild/docs/04_指标注册表.md`
36. `rebuild/docs/05_工作台元数据DDL.md`

---

## 3. 审计维度（6 个维度，全部必须评估）

### 维度 F：字段治理实现质量

**这是本轮审计的最高优先级维度。**

1. **DDL 正确性**：`04_phase3_field_governance.sql` 是否与 `phase3_final.md` §3.1 的 DDL 完全一致？有没有遗漏列或约束？
2. **种子数据完整性**：是否包含 10 个首批种子字段？每个字段的 `rule_type`、`rule_config`、`parameter_refs` 是否与计划匹配？
3. **合规语义隔离**：
   - 合规规则是否独立在 `meta.meta_source_field_compliance`？有没有塞回 `meta_field_mapping_rule` 或 `meta_field_health`？
   - 合规率快照是否独立在 `meta.meta_source_field_compliance_snapshot`？
4. **`compile_compliance_sql()` 正确性**：是否覆盖了 `whitelist`、`numeric_range`、`range_by_tech`、`bbox_pair` 四种规则类型？每种的 SQL 生成是否正确？
5. **`list_fields()` 修正**：是否只返回 `field_scope='pipeline'`？
6. **`get_field_detail()` 列名修正**：`meta_field_mapping_rule` 是否用了 `rule_type/rule_expression/source_field/source_table`？`meta_field_change_log` 是否用了 `reason` 而非 `change_reason`？
7. **P3 页面**：是否实现了"统一字段表格 + scope 筛选 + 同页展开"？有没有退回到 Tab 切换或纯抽屉？

### 维度 A：V2 还原度

逐项核对 `phase3_final.md` §5 的 10 项还原清单：

| # | 组件 | 计划优先级 | 是否已实现？证据在哪？|
|---|------|-----------|---------------------|
| 1 | P3 统一治理表 | P0 | |
| 2 | P3 合规趋势/规则 | P0 | |
| 3 | D3 原始值 vs 修正值 | P1 | |
| 4 | P4 问题类型筛选 | P1 | |
| 5 | D1 版本变化摘要 | P1 | |
| 6 | P2 参数 diff | P1 | |
| 7 | P2 SQL resolved | P1 | |
| 8 | P2 对象级 diff | P1 | |
| 9 | P1 Focus 字段变化 | P2 | |
| 10 | Gate 与关键指标 | P2 | |

对每项给出：已实现 / 部分实现（差什么）/ 未实现。

### 维度 B：性能与缓存

1. `refresh_source_field_snapshots` 是否只在 run completed 或手动 refresh 时触发？页面请求是否会触发 `fact_filtered` 全表扫描？
2. `ensure_snapshot_bundle` 的锁机制是否正确？
3. `cache/refresh` 是否限制了只能重算 latest completed run？

### 维度 C：代码架构

1. **后端拆分质量**：`__init__.py` facade 是否完整导出所有公开函数？现有 router 的 import 是否都不需要修改？
2. **前端拆分质量**：`index.html` 是否改为 `type="module"`？ES Module 的 import/export 链路是否完整？有没有引入 npm/vite？
3. **单文件行数**：列出每个新文件的行数，标注超过 500 行的文件
4. **函数粒度**：是否有超过 80 行的函数？

### 维度 D：中文化

1. `labels.py` 覆盖了多少字段？
2. 数据库 `meta_field_registry.field_name_cn` 的覆盖率是多少？（需查 PG17）
3. 前端主路径（页面标题、按钮、空状态、筛选标签）是否全部中文？列出残留英文

### 维度 E：业务逻辑正确性

1. **run 绑定参数**：`steps/{step_id}/parameters` 是否走 `run_id -> parameter_set_id -> parameters`？是否还有任何路径读取 `is_active = true`？
2. **历史只读**：`cache/refresh` 是否拒绝非最新 run 的重算请求？
3. **快照触发**：`PATCH /runs/{id}/status?status=completed` 是否触发了 `ensure_snapshot_bundle` 和 `refresh_source_field_snapshots`？
4. **Gate**：`_compute_gate_results` 定义了多少个 Gate？是否至少覆盖了 8 个核心链路节点？

---

## 4. PG17 实库核验

**你必须连接 PG17 数据库执行以下查询：**

```sql
-- 1. 新增列
SELECT column_name FROM information_schema.columns
WHERE table_schema='meta' AND table_name='meta_field_registry' AND column_name IN ('field_scope','logical_domain','unit');

-- 2. 新增表
SELECT table_name FROM information_schema.tables
WHERE table_schema='meta' AND table_name IN ('meta_source_field_compliance','meta_source_field_compliance_snapshot');

-- 3. 种子数据
SELECT count(*) FROM meta.meta_field_registry WHERE field_scope='source';
SELECT count(*) FROM meta.meta_source_field_compliance WHERE is_active=true;

-- 4. 中文覆盖率
SELECT count(*) AS total,
       count(*) FILTER (WHERE field_name_cn IS NOT NULL AND field_name_cn != field_name) AS has_cn
FROM meta.meta_field_registry WHERE schema_name IN ('pipeline','source');

-- 5. Gate 表
SELECT count(*) FROM workbench.wb_gate_result;
```

---

## 5. 输出格式

```markdown
# Phase 3 审计报告 — Codex

> 审计日期：[日期]

## 1. 维度评定

| 维度 | 评定 | 关键发现 |
|------|------|---------|
| F 字段治理 | 通过/部分通过/未通过 | |
| A V2 还原度 | | |
| B 性能缓存 | | |
| C 代码架构 | | |
| D 中文化 | | |
| E 业务逻辑 | | |

## 2. 详细发现

### F 字段治理
[逐项列出 §3 维度 F 的 7 个检查点的结果]

### A V2 还原度
[§5 的 10 项还原清单逐项核对结果]

... 其他维度类似 ...

## 3. 问题清单

| # | 严重性 | 问题 | 涉及文件 | 建议修复方案 |
|---|--------|------|---------|------------|

## 4. 总体评估

[通过 / 需修改后通过 / 不通过]

[如果"需修改"，列出阻塞项和建议优先级]
```

---

## 6. 审计纪律

- 你是独立审计 agent，不要假设其他 agent 会补充你遗漏的内容
- 每个"通过"判定都必须有证据（具体文件、行号或 SQL 结果）
- 每个"未通过"必须有具体问题描述和修复建议
- 不要因为代码量大就跳过任何文件
- 不要把"代码存在"等同于"实现正确"，必须阅读逻辑
- 对照 `phase3_final.md` 的原始要求，不要降低标准
