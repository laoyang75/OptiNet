# Phase 3 审计报告 — Codex

> 审计日期：2026-03-24

## 1. 维度评定

| 维度 | 评定 | 关键发现 |
|------|------|---------|
| F 字段治理 | 部分通过 | DDL 与种子 SQL 基本对齐，但合规 SQL 编译不完整，源字段快照实库为 0，源字段映射规则实库也为 0 |
| A V2 还原度 | 部分通过 | P3 统一表格、P2 参数 diff、D1/D3 骨架已落地，但 SQL resolved、对象级 diff、P4 完整筛选、Gate 主路径展示未完成 |
| B 性能缓存 | 未通过 | 读接口仍会触发 `ensure_snapshot_bundle()`，请求路径可重算快照；`gate_count` 未纳入 bundle 完整性判断 |
| C 代码架构 | 部分通过 | 后端/前端已拆分且 ESM 链路成立，但 facade 不完整，多个文件和函数仍明显超标 |
| D 中文化 | 部分通过 | PG17 字段中文覆盖率 98.2%，但前端主路径仍残留 `Run`、`Compare`、`SQL`、`WangYou Data Governance Workbench` 等英文 |
| E 业务逻辑 | 部分通过 | `steps/{id}/parameters` 已 run 绑定，但历史只读、compare 语义和 Gate 落库仍未真正闭环 |

## 2. 详细发现

### F 字段治理

1. DDL 正确性：通过  
证据：
- `rebuild/sql/04_phase3_field_governance.sql:7-67` 与 `rebuild/audit/phase3_final.md:127-187` 一致，包含 `field_scope / logical_domain / unit`、`meta_source_field_compliance`、`meta_source_field_compliance_snapshot`。
- PG17 查询结果：`meta.meta_field_registry` 已有 `field_scope`、`logical_domain`、`unit` 三列；两张新表均存在。

2. 种子数据完整性：部分通过  
证据：
- `rebuild/sql/05_phase3_field_governance_seed.sql:7-177` 覆盖 10 个源字段和 10 条活跃规则，`rule_type`、`rule_config`、`parameter_refs` 与计划主表基本一致。
- PG17 查询结果：`meta.meta_field_registry WHERE field_scope='source' = 10`；`meta.meta_source_field_compliance WHERE is_active=true = 10`。
- 但 PG17 查询结果：源字段到过程字段的映射规则数 `= 0`，`meta.meta_source_field_compliance_snapshot` 行数 `= 0`，实库闭环未形成。

3. 合规语义隔离：通过  
证据：
- 规则独立存于 `meta.meta_source_field_compliance`，快照独立存于 `meta.meta_source_field_compliance_snapshot`；`fields.py` 的过程字段详情仍从 `meta_field_mapping_rule` / `meta_field_health` 读过程字段语义，未把合规规则塞回旧表。见 `rebuild/backend/app/services/workbench/fields.py:134-152,187-198,259-278`。

4. `compile_compliance_sql()` 正确性：未通过  
证据：
- 已覆盖四种 rule type：`whitelist`、`numeric_range`、`range_by_tech`、`bbox_pair`，见 `rebuild/backend/app/services/workbench/fields.py:342-391`。
- 但 `numeric_range` 未处理 `invalid_from_param`，`sig_rsrp` 的 `global.rsrp_invalid_values` 实际未进入 SQL。
- `range_by_tech` 未处理 `overflow_from_param`，`lac_dec` 的 `global.lac_overflow_values` 未进入 SQL。
- `bbox_pair` 读取了 `pair_field`，但未真正使用配对字段做联合判断，只检查单字段范围。
- 刷新时固定写 `dimension_key='ALL'`，没有计划要求的 `operator:*` / `tech:*` / 组合切片，也没有 `GROUPING SETS`。见 `rebuild/backend/app/services/workbench/fields.py:453-507`。

5. `list_fields()` 修正：通过  
证据：
- `rebuild/backend/app/services/workbench/fields.py:61-67` 明确限制 `schema_name='pipeline' AND field_scope='pipeline'`。

6. `get_field_detail()` 列名修正：通过  
证据：
- `meta_field_mapping_rule` 使用 `rule_type / rule_expression / source_field / source_table`，见 `rebuild/backend/app/services/workbench/fields.py:141-145`。
- `meta_field_change_log` 使用 `reason`，见 `rebuild/backend/app/services/workbench/fields.py:147-152`。

7. P3 页面：部分通过  
证据：
- 已实现统一表格 + 同页展开，见 `rebuild/frontend/js/pages/fields.js:84-138,143-159,335-397`。
- 但仍有 4 个落差：
- “标准字段”列语义错误，当前 source 行显示自身字段名、pipeline 行显示表名，不是标准字段映射目标。见 `rebuild/frontend/js/pages/fields.js:92,125`。
- 缺少“影响步骤”过滤，仅有搜索 / 范围 / 状态。见 `rebuild/frontend/js/pages/fields.js:373-393`。
- 顶部概览卡未实现计划中的“缺失字段数”，当前是“字段总数 / 正常 / 关注 / 异常”。见 `rebuild/frontend/js/pages/fields.js:366-371`。
- source 展开区未渲染变更历史；即使后端返回 `change_log`，前端也未展示。见 `rebuild/frontend/js/pages/fields.js:161-232`。

### A V2 还原度

| # | 组件 | 结果 | 证据 / 差距 |
|---|------|------|------------|
| 1 | P3 统一治理表 | 部分实现 | 已有统一表格和同页展开：`rebuild/frontend/js/pages/fields.js:84-138,335-397`；但“标准字段”列语义错误，影响步骤筛选缺失 |
| 2 | P3 合规趋势/规则 | 部分实现 | API 与 UI 骨架存在：`rebuild/backend/app/api/source_fields.py:20-75`、`rebuild/frontend/js/pages/fields.js:161-232`；但 PG17 中 `meta_source_field_compliance_snapshot = 0`，趋势无实数，映射规则实库也为 0 |
| 3 | D3 原始值 vs 修正值 | 部分实现 | `openSampleDrawer()` 会把原始值和修正值并排高亮：`rebuild/frontend/js/ui/drawers.js:98-125`；但它是“样本集抽屉”，不是单对象详情抽屉，也没有 compare run 差异 |
| 4 | P4 问题类型筛选 | 部分实现 | 现有筛选只有 `sample_type` 和 `step`：`rebuild/frontend/js/pages/samples.js:21-27,71-77,104-116`；缺少 V2 的问题类型 tag bar 与 run 过滤 |
| 5 | D1 版本变化摘要 | 部分实现 | 已有版本抽屉和参数变化表：`rebuild/frontend/js/ui/drawers.js:17-76`；但没有按参数/规则/SQL/契约分别给出摘要与原因链 |
| 6 | P2 参数 diff | 已实现 | 后端 `get_step_parameter_diff()` + 前端 G2 区都已落地：`rebuild/backend/app/services/workbench/steps.py:211-249`、`rebuild/frontend/js/pages/step.js:238-266` |
| 7 | P2 SQL resolved | 未实现 | `get_step_sql()` 只返回默认 SQL bundle 的原文件文本：`rebuild/backend/app/services/workbench/steps.py:118-153`；D2 抽屉仅展示 raw SQL：`rebuild/frontend/js/ui/drawers.js:78-89` |
| 8 | P2 对象级 diff | 未实现 | `get_step_object_diff()` 明确写明当前是简化版，只比较异常类型计数，不是对象新增/消失/变化：`rebuild/backend/app/services/workbench/steps.py:259-287,291-327` |
| 9 | P1 Focus 字段变化 | 部分实现 | P1 只展示聚合级“源字段异常数”而非字段级变化链路：`rebuild/frontend/js/pages/overview.js:87-96`；`href` 也未在渲染时使用：`rebuild/frontend/js/pages/overview.js:232-237` |
| 10 | Gate 与关键指标 | 部分实现 | 后端已定义 Gate 端点与 10 个 Gate：`rebuild/backend/app/api/metrics.py:85-100`、`rebuild/backend/app/services/workbench/snapshots.py:498-524`；但 PG17 `workbench.wb_gate_result = 0`，P1 也未展示 Gate 区块 |

### B 性能与缓存

1. 页面请求仍会触发快照计算：未通过  
证据：
- `rebuild/backend/app/services/workbench/steps.py:33-34,80-81` 在步骤指标/规则读接口里直接调用 `ensure_snapshot_bundle()`。
- `rebuild/backend/app/services/workbench/snapshots.py:672-804` 的 layer/step/anomaly/distribution 读接口也会调用 `ensure_snapshot_bundle()`。
- 这意味着一旦快照缺失，请求路径就会触发 `_compute_step_metrics()` / `_compute_rule_hits()` 等全表聚合，与 `phase3_final.md:316-318,429-430` 的约束冲突。

2. `ensure_snapshot_bundle` 锁机制：部分通过  
证据：
- 正面：`snapshot_lock(run_id)` 提供按 run 的异步锁，见 `rebuild/backend/app/services/workbench/base.py:159-165`。
- 问题：bundle 完整性判断只看 `layer_count / metric_count / anomaly_count`，没看 `rule_count / gate_count`。见 `rebuild/backend/app/services/workbench/snapshots.py:580-588`。
- 实库结果：run 3/4/5 已有 `layer_cnt=12, metric_cnt=41, anomaly_cnt=9, rule_cnt=13`，但 `gate_cnt=0`；后续读请求不会自动补 Gate。

3. `cache/refresh` 限制最新 completed run：部分通过  
证据：
- `rebuild/backend/app/api/workbench.py:77-83` 对显式传入的 `run_id` 做了“只允许最新 completed run”限制。
- 但 `rebuild/backend/app/services/workbench/snapshots.py:814-815` 在未传 `run_id` 时会回退到 `latest_completed_run_id() or latest_run_id()`，理论上仍可能刷到运行中 run。
- 同时 `rebuild/backend/app/services/workbench/snapshots.py:818` 使用了未导入的 `now_iso()`，`/cache/refresh` 存在运行时 500 风险。

### C 代码架构

1. 后端拆分质量：部分通过  
证据：
- 业务代码已拆到 `catalog.py / snapshots.py / steps.py / fields.py / samples.py`，FastAPI 入口使用新模块，见 `rebuild/backend/app/main.py:29-34`。
- facade 存在，见 `rebuild/backend/app/services/workbench/__init__.py`。
- 但 facade 漏导出 `get_version_change_log`、`get_step_parameter_diff`、`get_step_object_diff`；审计脚本比对结果如此。
- 同时 router 已直接改为从子模块导入，见 `rebuild/backend/app/api/steps.py:10-18`，与“现有 router import 无需改动”的目标不一致。

2. 前端拆分质量：通过  
证据：
- `rebuild/frontend/index.html:80` 已改为 `type="module"`。
- ES Module import/export 链路完整：`rebuild/frontend/js/main.js:5-12`、`rebuild/frontend/js/core/api.js`、`rebuild/frontend/js/ui/*`、`rebuild/frontend/js/pages/*`。
- 仓库内未发现 `package.json`、Vite、Webpack 等构建链证据；前端目录仅保留 `app_legacy.js` 作为旧文件，不在当前入口引用。

3. 单文件行数统计  

| 文件 | 行数 | 备注 |
|------|------|------|
| `rebuild/backend/app/services/workbench/__init__.py` | 94 |  |
| `rebuild/backend/app/services/workbench/base.py` | 268 |  |
| `rebuild/backend/app/services/workbench/catalog.py` | 482 |  |
| `rebuild/backend/app/services/workbench/snapshots.py` | 822 | 超过 500 |
| `rebuild/backend/app/services/workbench/steps.py` | 328 |  |
| `rebuild/backend/app/services/workbench/fields.py` | 517 | 超过 500 |
| `rebuild/backend/app/services/workbench/samples.py` | 101 |  |
| `rebuild/backend/app/main.py` | 54 |  |
| `rebuild/backend/app/api/steps.py` | 199 |  |
| `rebuild/backend/app/api/runs.py` | 127 |  |
| `rebuild/backend/app/api/workbench.py` | 154 |  |
| `rebuild/backend/app/api/metrics.py` | 100 |  |
| `rebuild/backend/app/api/source_fields.py` | 87 |  |
| `rebuild/backend/app/services/labels.py` | 225 |  |
| `rebuild/backend/app/services/cache.py` | 84 |  |
| `rebuild/frontend/index.html` | 82 |  |
| `rebuild/frontend/style.css` | 816 | 超过 500 |
| `rebuild/frontend/js/main.js` | 124 |  |
| `rebuild/frontend/js/core/api.js` | 92 |  |
| `rebuild/frontend/js/core/state.js` | 58 |  |
| `rebuild/frontend/js/ui/common.js` | 186 |  |
| `rebuild/frontend/js/ui/drawers.js` | 197 |  |
| `rebuild/frontend/js/pages/overview.js` | 275 |  |
| `rebuild/frontend/js/pages/step.js` | 302 |  |
| `rebuild/frontend/js/pages/fields.js` | 418 |  |
| `rebuild/frontend/js/pages/samples.js` | 126 |  |
| `rebuild/sql/04_phase3_field_governance.sql` | 67 |  |
| `rebuild/sql/05_phase3_field_governance_seed.sql` | 194 |  |

补充：
- 旧单体文件仍保留：`rebuild/backend/app/services/workbench_legacy.py = 2045` 行，`rebuild/frontend/app_legacy.js = 1184` 行，但当前入口不再直接使用它们。

4. 函数粒度：未通过  
证据：
- 后端超过 80 行的函数：
- `ensure_reference_data()`：131 行，`rebuild/backend/app/services/workbench/catalog.py:31`
- `_compute_step_metrics()`：181 行，`rebuild/backend/app/services/workbench/snapshots.py:69`
- `_compute_rule_hits()`：196 行，`rebuild/backend/app/services/workbench/snapshots.py:298`
- `ensure_snapshot_bundle()`：95 行，`rebuild/backend/app/services/workbench/snapshots.py:573`
- `refresh_source_field_snapshots()`：124 行，`rebuild/backend/app/services/workbench/fields.py:394`
- 前端超过 80 行的函数：
- `loadOverview()`：157 行，`rebuild/frontend/js/pages/overview.js:119`
- `loadStep()`：279 行，`rebuild/frontend/js/pages/step.js:24`

### D 中文化

1. `labels.py` 覆盖度：部分通过  
证据：
- `rebuild/backend/app/services/labels.py` 中 `FIELD_LABELS` 共 79 个字段名。
- PG17 中 `meta.meta_field_registry` 在 `pipeline/source` 范围内共有 212 个去重字段名，故 `labels.py` 兜底覆盖约为 37.3%，符合“fallback”定位，但本身不是主覆盖来源。

2. `meta_field_registry.field_name_cn` 覆盖率：通过  
证据：
- PG17 查询结果：`total=571`，`has_cn=561`，覆盖率 `98.2%`，已高于计划要求的 80%。
- 当前残留英文/未翻译字段主要是：`brand`、`ip`、`lat`、`lon`、`model`。

3. 前端主路径中文化：部分通过  
证据：
- 页面标题、按钮、空状态主体大部分已中文化。
- 但主路径仍残留英文：
- `rebuild/frontend/index.html:13` `WangYou Data Governance Workbench`
- `rebuild/frontend/index.html:19-23` `Run / Compare / SQL`
- `rebuild/frontend/js/main.js:38-42` `Run / Compare / SQL`
- `rebuild/frontend/js/pages/overview.js:204` `Compare Run`
- `rebuild/frontend/js/pages/step.js:234` `Compare Run 差异`
- `rebuild/frontend/js/pages/overview.js:263`、`rebuild/frontend/js/pages/step.js:175,185` 直接显示 `pipeline.<table>`

### E 业务逻辑

1. run 绑定参数：部分通过  
证据：
- 正面：`/steps/{step_id}/parameters` 已按 `run_id -> wb_run.parameter_set_id -> wb_parameter_set.parameters` 取数，见 `rebuild/backend/app/api/steps.py:115-137`。
- 风险：
- 代码库仍有 `is_active = true` 查询，见 `rebuild/backend/app/services/workbench/catalog.py:36,128` 和 `rebuild/backend/app/api/runs.py:25`。
- `ensure_reference_data()` 还会把 NULL 版本引用的 `wb_run` 回填为当前 active/default 版本，见 `rebuild/backend/app/services/workbench/catalog.py:124-155`；这不是严格的历史只读策略。

2. 历史只读：未通过  
证据：
- `/cache/refresh` 只挡住了显式非最新 run，见 `rebuild/backend/app/api/workbench.py:77-83`。
- 但多个读接口会在快照缺失时自动计算任意 `run_id` 的快照，见 `rebuild/backend/app/services/workbench/snapshots.py:672-804` 与 `rebuild/backend/app/services/workbench/steps.py:33-34,80-81`。
- `POST /source-fields/refresh` 没有 latest completed run 限制，见 `rebuild/backend/app/api/source_fields.py:78-87` 和 `rebuild/backend/app/services/workbench/fields.py:401-403`。

3. compare 语义：未通过  
证据：
- `previous_completed_run_id()` 的实现是“找当前 run 之外最新的一次 completed run”，不是“找当前 run 之前最近的一次 completed run”。见 `rebuild/backend/app/services/workbench/catalog.py:250-259`。
- PG17 实库示例：当 `run_id=3` 时，该逻辑会返回 `run_id=5`，而不是更合理的 `run_id=2`。
- 因此，历史 run 页面若未显式传 `compare_run_id`，compare 结果可能指向未来 run。

4. 快照触发：部分通过  
证据：
- 代码层面，`PATCH /runs/{id}/status?status=completed` 已触发 `ensure_snapshot_bundle()` 与 `refresh_source_field_snapshots()`，见 `rebuild/backend/app/api/runs.py:116-121`。
- 但 PG17 实库结果显示：5 个 run 全部 `completed`，`meta.meta_source_field_compliance_snapshot = 0`，`workbench.wb_gate_result = 0`，说明实际产物并未闭环到位。

5. Gate：部分通过  
证据：
- `_compute_gate_results()` 定义了 10 个 Gate，覆盖 `raw_records / dim_lac_trusted / fact_filtered / dim_bs_trusted / fact_gps_corrected / fact_signal_filled / fact_final / profile_bs / profile_cell / profile_lac`，见 `rebuild/backend/app/services/workbench/snapshots.py:498-524`，已超过 8 个核心节点。
- 但 PG17 `workbench.wb_gate_result = 0`，当前无法证明 Gate 已真正落库并参与页面展示。

## 3. 问题清单

| # | 严重性 | 问题 | 涉及文件 | 建议修复方案 |
|---|--------|------|---------|------------|
| 1 | 严重 | `ensure_snapshot_bundle()` 的完整性判断忽略 `gate_count`，导致有 layer/metric/anomaly 但无 Gate 的 run 会被误判为“已完整”，PG17 中 run 3/4/5 全部 `gate_cnt=0` | `rebuild/backend/app/services/workbench/snapshots.py` | 在 `existing` 判定中纳入 `rule_count` 和 `gate_count`，并为缺 Gate 的历史 run 提供一次性补算脚本 |
| 2 | 严重 | 多个读接口在请求路径直接调用 `ensure_snapshot_bundle()`，会对缺快照 run 触发全表聚合，违反“页面请求不重算”和“历史只读”纪律 | `rebuild/backend/app/services/workbench/snapshots.py`, `rebuild/backend/app/services/workbench/steps.py`, `rebuild/backend/app/api/metrics.py` | 把读接口改为只读；若快照缺失则返回“未生成快照”；重算只允许 run completed 回调或显式 repair API |
| 3 | 严重 | 历史 compare 语义仍错误，`previous_completed_run_id()` 会把旧 run 对比到未来 run；PG17 中 `run_id=3` 会选到 `run_id=5` | `rebuild/backend/app/services/workbench/catalog.py` | 改为按 `started_at < current.started_at` 或 `run_id < current_run_id` 取最近 completed run；优先尊重 `wb_run.compare_run_id` |
| 4 | 严重 | 源字段合规刷新未按计划落地：无 `GROUPING SETS`、无 operator/tech 切片、无 invalid/overflow 处理、`bbox_pair` 非联合校验，且实库快照数为 0 | `rebuild/backend/app/services/workbench/fields.py`, `rebuild/backend/app/api/source_fields.py` | 重写 `compile_compliance_sql()` 与 `refresh_source_field_snapshots()`；至少补齐 4 类规则语义、4 类 dimension_key、latest completed run 限制，并跑一次全量回填 |
| 5 | 高 | P2 SQL 证据链未实现，`/steps/{id}/sql` 既不 run 绑定，也不返回 resolved SQL / compare SQL；D2 只展示原文件文本 | `rebuild/backend/app/services/workbench/steps.py`, `rebuild/backend/app/api/steps.py`, `rebuild/frontend/js/ui/drawers.js`, `rebuild/frontend/js/pages/step.js` | 给 SQL API 增加 `run_id/compare_run_id`，解析 run 绑定版本与参数，返回执行顺序、resolved SQL、compare SQL |
| 6 | 高 | `object-diff` 不是对象级 diff，只是在比异常类型计数；源码已明确承认是“简化版本” | `rebuild/backend/app/services/workbench/steps.py`, `rebuild/frontend/js/pages/step.js` | 基于对象主键快照或 run 隔离结果，返回 `added / removed / changed` 对象列表，而不是 anomaly_type 汇总 |
| 7 | 高 | P4 / D3 仍未达到 V2：无 run 过滤、无问题类型 tag bar、无 `get_sample_object_detail()`，D3 不是单对象详情抽屉 | `rebuild/backend/app/services/workbench/samples.py`, `rebuild/frontend/js/pages/samples.js`, `rebuild/frontend/js/ui/drawers.js` | 增加对象详情 API，按对象 ID 打开 D3；P4 增加问题类型与 run 过滤，并把 compare diff 放进 D3 |
| 8 | 高 | `/fields/{field_name}` 仍允许不传 `table_name`，而 PG17 中大量字段重名；例如 `tech_norm` 有 17 份、`operator_id_raw` 有 12 份 | `rebuild/backend/app/services/workbench/fields.py`, `rebuild/backend/app/api/workbench.py` | 强制要求 `table_name` 或 `field_scope + table_name`；前端统一携带精确定位键 |
| 9 | 中 | `/cache/refresh` 存在运行时风险：`refresh_all()` 返回 `now_iso()`，但当前模块未导入它 | `rebuild/backend/app/services/workbench/snapshots.py` | 补充 `now_iso` import，并为 `/cache/refresh` 增加最小 API smoke test |
| 10 | 中 | P3 虽然改成统一表格，但“标准字段”列语义错误，且缺少影响步骤筛选、缺失卡片和 source 变更历史 | `rebuild/frontend/js/pages/fields.js` | 后端返回 source->pipeline target 字段映射；前端补“影响步骤”筛选、“缺失字段数”卡片和 source change log |
| 11 | 中 | facade 兼容性不完整，未导出 `get_version_change_log / get_step_parameter_diff / get_step_object_diff`，router 也已改为直接依赖子模块 | `rebuild/backend/app/services/workbench/__init__.py`, `rebuild/backend/app/api/steps.py`, `rebuild/backend/app/api/workbench.py` | 补全 facade 导出，并统一恢复 router 仅依赖 facade，降低后续拆分耦合 |
| 12 | 低 | 中文化未完全收口，主路径仍残留 `Run / Compare / SQL / Compare Run / WangYou Data Governance Workbench / pipeline.` 等英文 | `rebuild/frontend/index.html`, `rebuild/frontend/js/main.js`, `rebuild/frontend/js/pages/overview.js`, `rebuild/frontend/js/pages/step.js` | 把运行上下文和辅助标签完全替换为中文，表前缀可改成“数据表”或弱化展示 |

## 4. 总体评估

不通过

阻塞项与建议优先级：

1. P0：修正快照只读与请求路径重算问题  
先把 `ensure_snapshot_bundle()` 从读路径移走，并修正 `gate_count` / `rule_count` 完整性判断。

2. P0：补齐源字段治理闭环  
重写 `compile_compliance_sql()` 与 `refresh_source_field_snapshots()`，然后对最新 completed run 回填 source snapshot。

3. P0：修正历史 compare 语义  
`previous_completed_run_id()` 必须变成“当前 run 之前最近一次 completed run”，否则历史 diff 全部不可靠。

4. P1：补齐 P2 SQL / object diff 证据链  
这两项目前都只是骨架，尚未达到 `phase3_final.md` 的交付标准。

5. P1：补齐 P4 / D3  
把“样本集预览”升级成“对象级详情 + compare diff + 问题类型 / run 过滤”。

6. P2：收口 P3 语义与中文化  
修正“标准字段”列、影响步骤筛选、source 变更历史和残留英文。
