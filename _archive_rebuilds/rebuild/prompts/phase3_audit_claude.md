# 第三阶段审计 — Claude Agent

> 身份：**Claude 审计 Agent（第三阶段）**
> 审计目标：对 Phase 3 全部开发产出做独立质量评估，对照 `phase3_final.md` 的 13 个任务和 6 个关键决策，逐项核验是否真正落地
> 输出路径：`rebuild/audit/phase3_audit_claude.md`

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
11. `rebuild/backend/app/api/steps.py` — 步骤 API
12. `rebuild/backend/app/api/runs.py` — Run API
13. `rebuild/backend/app/api/workbench.py` — 版本/字段/样本 API
14. `rebuild/backend/app/api/metrics.py` — 指标 API
15. `rebuild/backend/app/api/source_fields.py` — 源字段 API（T06 新增）

### 后端支撑
16. `rebuild/backend/app/services/labels.py` — 中文标签字典
17. `rebuild/backend/app/services/cache.py` — 缓存层

### 前端（10 文件 — 由 T02 拆分产出）
18. `rebuild/frontend/index.html`
19. `rebuild/frontend/style.css`
20. `rebuild/frontend/js/main.js`
21. `rebuild/frontend/js/core/api.js`
22. `rebuild/frontend/js/core/state.js`
23. `rebuild/frontend/js/ui/common.js`
24. `rebuild/frontend/js/ui/drawers.js`
25. `rebuild/frontend/js/pages/overview.js`
26. `rebuild/frontend/js/pages/step.js`
27. `rebuild/frontend/js/pages/fields.js`
28. `rebuild/frontend/js/pages/samples.js`

### SQL（2 文件 — T05 新增）
29. `rebuild/sql/04_phase3_field_governance.sql`
30. `rebuild/sql/05_phase3_field_governance_seed.sql`

### V2 原型（对比基准，必须全部读取）
31. `docs/data_warehouse/Pre_UI/V2/fields.html`
32. `docs/data_warehouse/Pre_UI/V2/samples.html`
33. `docs/data_warehouse/Pre_UI/V2/index.html`
34. `docs/data_warehouse/Pre_UI/V2/step-lac.html`

### 设计文档
35. `rebuild/docs/04_指标注册表.md`
36. `rebuild/docs/05_工作台元数据DDL.md`

---

## 3. 审计维度（6 个维度，全部必须评估）

### 维度 F：字段治理实现质量

**这是本轮审计的最高优先级维度。**

你需要逐一核验以下 7 个检查点：

1. **DDL 正确性**：对照 `phase3_final.md` §3.1 的 DDL 块，逐列检查 `04_phase3_field_governance.sql` 是否完全一致
2. **种子数据**：10 个源字段是否在 `05_phase3_field_governance_seed.sql` 中全部写入？`rule_type` 和 `parameter_refs` 是否匹配计划中的种子表？
3. **合规语义隔离**：在 `fields.py` 中搜索，确认没有把合规规则写入 `meta_field_mapping_rule`，没有把合规率写入 `meta_field_health`
4. **`compile_compliance_sql()`**：逐个检查 `whitelist`、`numeric_range`、`range_by_tech`、`bbox_pair` 四种规则类型的 SQL 生成逻辑是否正确。特别关注 SQL 注入风险
5. **`/api/v1/fields` 只返回 pipeline 字段**：检查 `list_fields()` 的 WHERE 条件是否包含 `field_scope = 'pipeline'`
6. **`get_field_detail()` 列名**：确认查询用了 `rule_type/rule_expression/source_field/source_table` 和 `reason`
7. **P3 同页展开**：读取 `fields.js` 和 V2 原型 `fields.html`，确认使用了"统一表格 + scope 筛选 + 点击行展开"，而非 Tab 切换或纯抽屉

### 维度 A：V2 还原度

逐项核对 `phase3_final.md` §5 的 10 项清单。对每一项，你需要：
- 找到对应的代码实现位置（文件名 + 函数名）
- 判断是否真正实现了计划描述的功能
- 如果只是部分实现，明确指出缺失部分

### 维度 B：性能与缓存

1. 追踪 `refresh_source_field_snapshots` 的所有调用路径，确认它不会被普通 GET 请求触发
2. 检查 `ensure_snapshot_bundle` 中的锁和幂等检查是否正确
3. 检查 `cache/refresh` 的历史 run 只读约束

### 维度 C：代码架构

1. 检查 `__init__.py` facade 的 `__all__` 是否完整覆盖了所有公开函数
2. 检查前端 ES Module import/export 链路：从 `index.html` → `main.js` → 各页面模块，是否有断链
3. 列出所有超过 500 行的文件，标注超标原因是否合理
4. 抽查 5 个函数，确认是否在 80 行以内

### 维度 D：中文化

1. 检查 `labels.py` 的 `FIELD_LABELS` 字典覆盖范围
2. 查询 PG17 中 `field_name_cn` 覆盖率
3. 前端所有 `empty-state`、按钮文字、页面标题是否中文

### 维度 E：业务逻辑正确性

1. **run 绑定**：在所有后端文件中搜索 `is_active`，确认没有用 `is_active = true` 读取参数的残留路径
2. **历史只读**：检查 `cache/refresh` 端点是否有 `latest_completed_run_id` 校验
3. **快照触发链**：从 `runs.py` 的 `update_run_status` 追踪，确认 `status=completed` 同时触发了工作台快照和源字段合规快照
4. **Gate 定义**：检查 `GATE_DEFINITIONS` 是否至少 8 个，是否覆盖了原始记录、LAC、BS、GPS修正、信号补齐、最终明细、碰撞、画像等关键节点

---

## 4. PG17 实库核验

**你必须连接 PG17 数据库执行以下查询并记录结果：**

```sql
-- 1. 新增列是否存在
SELECT column_name FROM information_schema.columns
WHERE table_schema='meta' AND table_name='meta_field_registry' AND column_name IN ('field_scope','logical_domain','unit');

-- 2. 新增表是否存在
SELECT table_name FROM information_schema.tables
WHERE table_schema='meta' AND table_name IN ('meta_source_field_compliance','meta_source_field_compliance_snapshot');

-- 3. 种子数据计数
SELECT count(*) AS source_fields FROM meta.meta_field_registry WHERE field_scope='source';
SELECT count(*) AS compliance_rules FROM meta.meta_source_field_compliance WHERE is_active=true;

-- 4. 中文覆盖率
SELECT count(*) AS total,
       count(*) FILTER (WHERE field_name_cn IS NOT NULL AND field_name_cn != field_name) AS has_cn,
       round(count(*) FILTER (WHERE field_name_cn IS NOT NULL AND field_name_cn != field_name)::numeric / count(*), 3) AS coverage
FROM meta.meta_field_registry WHERE schema_name IN ('pipeline','source');

-- 5. Gate 表
SELECT count(*) FROM workbench.wb_gate_result;
```

---

## 5. 输出格式

```markdown
# Phase 3 审计报告 — Claude

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
[逐一列出 7 个检查点的结果，每个检查点标注：通过/问题（含具体描述）]

### A V2 还原度
[10 项清单逐项结果]

... 其他维度 ...

## 3. 问题清单

| # | 严重性 | 问题 | 涉及文件 | 建议修复方案 |
|---|--------|------|---------|------------|

## 4. 总体评估

[通过 / 需修改后通过 / 不通过]
```

---

## 6. 审计纪律

- 你是 **Claude 审计 Agent**，独立于 Codex Agent，不要假设其他人会补充你的遗漏
- 每个"通过"必须有证据；每个"未通过"必须有问题描述和修复建议
- 不要因为文件很多就浅读，特别是 `fields.py`（517 行）和 `snapshots.py`（822 行），这两个文件集中了本阶段最重要的业务逻辑
- **特别关注 `compile_compliance_sql()` 的安全性**：参数是否直接拼接进 SQL？是否有注入风险？
- 对照 V2 原型 HTML 做前端核对，不要只看代码结构，要看交互是否匹配
- 不要降低 `phase3_final.md` 的标准，如果计划说"必须"，那就必须
