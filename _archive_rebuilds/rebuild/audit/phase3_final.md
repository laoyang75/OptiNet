# 第三阶段开发计划（最终版）

> 合并日期：2026-03-24
> 基于：Codex / Claude / Gemini 三方独立审计
> 额外核验：PG17 实库、`docs/data_warehouse/Pre_UI/V2/fields.html`、当前实现文件

## 1. 三方评估汇总

### 1.1 维度评估对比

| 维度 | Codex 评估 | Claude 评估 | Gemini 评估 | 合并判定 |
|------|-----------|-----------|-----------|---------|
| F 字段治理 | 最充分。给出兼容 DDL、种子字段、API、快照和性能实测；明确指出 `get_field_detail()` 与真实 DDL 失配 | 充分。V2 交互和任务分解清晰，但把合规规则塞回 `meta_field_mapping_rule`、把合规率塞回 `meta_field_health`，语义过载 | 方向正确，但字段治理缺少兼容 DDL、种子字段清单和函数级方案；采样方案偏简化 | 采纳 Codex 的数据模型主干，吸收 Claude 的页面与任务优先级；Gemini 在维度 F 标注“审计不充分” |
| A V2 还原度 | 缺口矩阵最完整，明确指出 P3/P4/D1/D3 的证据链缺失 | 优先级排序清楚，P1/P2/P3/P4 的缺口描述可直接转任务 | 只覆盖主页面缺口，深度不足 | 以 Codex + Claude 的缺口矩阵为准；P3、D3、P4 筛选、D1 变更历史列为 P0/P1 |
| B 性能缓存 | 最强。提供 `raw_records` / `fact_filtered` / `fact_final` 的实测聚合时间，准确定位“请求路径触发快照”的风险 | 判断合理。保留现有三层缓存思路，建议把刷新后移到快照流程 | 强调异步和采样，但把 `TABLESAMPLE` 当主方案过于激进 | 保留 `AsyncTTLCache` 作为 L1；快照改为 run 完成后触发；拒绝实时扫描和采样主方案 |
| C 代码架构 | 模块职责边界最清晰，后端/前端拆分均落到函数名 | 用真实行号做拆分映射，可执行性高 | 方向正确，但后端拆分粒度偏粗 | 后端采纳中粒度 5 个业务模块，前端采纳原生 ES Modules |
| D 中文化 | 明确“数据库元数据为主、`labels.py` 为兜底” | 给出批量补齐策略和用户路径英文清单 | 提出静态字典种子，但维护位置偏代码侧 | 采纳“DB 为权威来源 + seed/SQL 回填 + `labels.py` fallback”的方案 |
| E 业务逻辑 | 最关键。明确指出 run 绑定参数缺失、历史快照被当前数据覆盖、compare 语义失真 | 对 Gate 缺失和 Doc04 指标覆盖不足分析充分 | 只指出 gate 薄弱，深度不足 | Phase 3 先修历史正确性，再补 Gate 和关键指标，基线/伪日更继续延后 |

### 1.2 审计质量评估

- Codex：审计充分。数据库、代码、前端、性能、V2 原型四条线都落到了具体表、接口和函数。少数方案拆分略细，但细节可直接吸收。
- Claude：基本充分。页面还原、任务排序、风险控制都可执行；但字段治理方案复用 `meta_field_mapping_rule` / `meta_field_health`，与现有 DDL 语义冲突，不宜直接采纳。
- Gemini：部分充分。架构方向、ES Modules、样本与字段页优先级可参考；但维度 F 缺少兼容 DDL、字段种子和函数级方案，按 prompt 规则标注“审计不充分”。

## 2. 关键决策

### 决策1：合规规则存储

**结论：** 选项 B，新建 `meta.meta_source_field_compliance` 独立表，并给 `meta.meta_field_registry` 增加 `field_scope`

**理由：**

- `meta.meta_field_registry` 继续作为统一字段主表最省心，但必须增加 `field_scope='source'/'pipeline'`，否则原始字段和过程字段无法共存。
- 合规规则与映射规则不是同一语义。真实 DDL 中 `meta.meta_field_mapping_rule` 只有 `rule_type` / `rule_expression` / `source_field` / `source_table`，继续复用会把“映射”与“合规”混成一张表。
- 对调试工具来说，B 比“把规则 JSON 塞到 registry”更稳定；列意义清楚、快照独立、后端代码更直。

**少数意见：**

- Claude 倾向选项 C，但该方案会继续放大当前 DDL 与服务层查询失配问题。
- Gemini 提到选项 A 的低改动优势，但长期会把 registry 变成大杂烩。

### 决策2：合规率计算源表

**结论：** 选项 B，使用 `pipeline.fact_filtered`

**理由：**

- 已核验 `fact_filtered` 现有 63 列，包含 Phase 3 需要的核心原始字段：`operator_id_raw`、`tech`、`tech_norm`、`lac_dec`、`cell_id_dec`、`lon_raw`、`lat_raw`、`sig_rsrp`、`sig_rsrq`、`sig_sinr`、`sig_rssi`。
- 已核验 `fact_filtered` 约 21,788,532 行，而 `raw_records` 约 251,172,880 行；在本地 PG17 下，Phase 3 需要的是“可重复重算”的调试能力，不是生产级审计中心。
- prompt 的裁决标准明确写了：如果 `fact_filtered` 已包含所有待检字段且数据量合理，优先选 `fact_filtered`。当前满足这个条件。

**少数意见：**

- Codex 和 Gemini 倾向 `raw_records`，理由是“更代表源数据原貌”。这个意见有道理，但不适合放进 Phase 3 主路径；后续如需做离线审计，可补充 `raw_records` 旁路验证任务，不进入 P3 请求路径。

### 决策3：合规率计算策略

**结论：** 选项 A，全量计算 + 快照存储

**理由：**

- 既然源表选的是 `fact_filtered`，全量 `COUNT + CASE/FILTER` 在 PG17 上可控，不需要用采样换误差。
- 采样会让“调参前后对比”失去稳定性，尤其在字段异常率较低时，趋势容易抖动。
- Phase 3 是工作台，不是在线接口。把计算放到 run 完成后或手动刷新，等待 30~60 秒是可接受的；把结果做成快照后，页面读取仍是毫秒级。

**少数意见：**

- Gemini 提议 `TABLESAMPLE`，但这只适合近似监控，不适合 Phase 3 的“重跑前后对比”。

### 决策4：前端模块化方案

**结论：** 选项 A，原生 ES Module

**理由：**

- 三方意见一致。
- 现代浏览器已支持 `<script type="module">`，不需要引入 Vite/Webpack。
- 对当前仓库最小改动、依赖边界最清晰，也最符合“不引入新框架”的纪律。

### 决策5：`workbench.py` 拆分粒度

**结论：** 中粒度，5 个业务模块 + 1 个辅助 `base.py`

**理由：**

- 2,045 行总量按 5 个业务模块拆分，单模块控制在约 250~450 行，最符合“单文件不超过 500 行”的开发纪律。
- Codex/Claude 的 7+ 模块划分里有不少边界值得保留，但直接全部落地会让 Phase 3 首轮拆分过细。
- 用 5 个业务模块先切清职责，再由 `base.py` 承接共用 SQL helper，是当前最稳妥的中线方案。

**少数意见：**

- Codex 和 Claude 倾向细粒度 7+ 模块；其函数分配将作为二级拆分参考，不直接按 7+ 个业务模块实施。

### 决策6：P3 字段治理前端组织

**结论：** 选项 C，统一表格；但不是生硬地加一个 `field_type` 列，而是保留 V2 的“原始字段 / 标准字段”双列 + 同页展开

**理由：**

- 已核验 `docs/data_warehouse/Pre_UI/V2_草图设计说明.md` 和 `docs/data_warehouse/Pre_UI/V2/fields.html`。V2 明确要求：
  - 一个字段注册表；
  - 点击字段行后在下方同页展开；
  - 展示基本信息、映射与解析规则、健康趋势、影响步骤、变更历史。
- 因此，不应使用 Tab 切换，也不应做成上下两块互不关联的区域。
- 最终实现采用“统一治理表格 + `scope` 快速筛选（全部/原始/过程）+ 同页展开区”的方式，既贴合 V2，也能兼容新的 `field_scope` 模型。

**少数意见：**

- Codex 倾向 Tab 切换，适合工程组织，但不符合 V2 原型。
- Claude 倾向上下双区，信息可读性尚可，但会弱化“原始字段到标准字段”的映射链路。

## 3. 字段治理实施方案（最终版）

### 3.1 数据库变更

**总原则：**

- `meta.meta_field_registry` 继续作为统一字段主表。
- `meta.meta_source_field_compliance` 承载原始字段合规规则定义。
- `meta.meta_source_field_compliance_snapshot` 承载 run 绑定的合规率快照。
- `meta.meta_field_mapping_rule` 继续只承载“原始字段 -> 过程字段/标准字段”的映射与解析说明，不承载合规规则。
- `meta.meta_field_health` 继续只承载过程字段健康历史，不扩成第二套源字段规则表。

**DDL：**

```sql
ALTER TABLE meta.meta_field_registry
    ADD COLUMN IF NOT EXISTS field_scope text NOT NULL DEFAULT 'pipeline',
    ADD COLUMN IF NOT EXISTS logical_domain text,
    ADD COLUMN IF NOT EXISTS unit text;

CREATE INDEX IF NOT EXISTS idx_meta_field_scope
    ON meta.meta_field_registry(field_scope, schema_name, table_name);

CREATE TABLE IF NOT EXISTS meta.meta_source_field_compliance (
    id                  serial          PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    version_tag         text            NOT NULL DEFAULT 'SRC-C-001',
    business_definition text            NOT NULL,
    field_category      text            NOT NULL,
    unit                text,
    rule_type           text            NOT NULL,
    rule_config         jsonb           NOT NULL,
    parameter_refs      jsonb           NOT NULL DEFAULT '[]'::jsonb,
    repair_strategy     text            NOT NULL DEFAULT 'keep_and_mark',
    severity            text            NOT NULL DEFAULT 'high',
    applies_to_operator text[]          NOT NULL DEFAULT ARRAY[]::text[],
    applies_to_tech     text[]          NOT NULL DEFAULT ARRAY[]::text[],
    is_active           boolean         NOT NULL DEFAULT true,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    updated_at          timestamptz     NOT NULL DEFAULT now(),
    UNIQUE(field_id, version_tag)
);

CREATE INDEX IF NOT EXISTS idx_meta_source_compliance_field
    ON meta.meta_source_field_compliance(field_id, is_active);

CREATE TABLE IF NOT EXISTS meta.meta_source_field_compliance_snapshot (
    id                  bigserial       PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    compliance_version  text            NOT NULL,
    source_table        text            NOT NULL DEFAULT 'pipeline.fact_filtered',
    batch_label         text,
    dimension_key       text            NOT NULL DEFAULT 'ALL',
    total_rows          bigint          NOT NULL,
    nonnull_rows        bigint          NOT NULL,
    compliant_rows      bigint          NOT NULL,
    anomalous_rows      bigint          NOT NULL,
    null_rows           bigint          NOT NULL,
    invalid_value_rows  bigint          NOT NULL DEFAULT 0,
    out_of_range_rows   bigint          NOT NULL DEFAULT 0,
    compliance_rate     numeric(8,4),
    null_rate           numeric(8,4),
    sample_payload      jsonb,
    parameter_values    jsonb,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    UNIQUE(field_id, run_id, dimension_key, compliance_version)
);

CREATE INDEX IF NOT EXISTS idx_meta_source_snapshot_run
    ON meta.meta_source_field_compliance_snapshot(run_id, dimension_key);

CREATE INDEX IF NOT EXISTS idx_meta_source_snapshot_field
    ON meta.meta_source_field_compliance_snapshot(field_id, run_id);
```

**首批种子字段：**

| 字段 | 中文名 | `logical_domain` | 合规规则类型 | 规则来源 |
|------|------|------------------|-------------|---------|
| `operator_id_raw` | 运营商编码 | `network` | `whitelist` | `global.operator_whitelist` |
| `tech` | 原始制式 | `network` | `whitelist` | `global.tech_whitelist` |
| `lac_dec` | LAC | `identity` | `range_by_tech` | `global.lac_overflow_values` |
| `cell_id_dec` | Cell ID | `identity` | `range_by_tech` | 合同约定固定范围 |
| `lon_raw` | 原始经度 | `location` | `bbox_pair` | `global.china_bbox` |
| `lat_raw` | 原始纬度 | `location` | `bbox_pair` | `global.china_bbox` |
| `sig_rsrp` | RSRP | `signal` | `numeric_range` | `global.rsrp_invalid_values` |
| `sig_rsrq` | RSRQ | `signal` | `numeric_range` | 固定范围 |
| `sig_sinr` | SINR | `signal` | `numeric_range` | 固定范围 |
| `sig_rssi` | RSSI | `signal` | `numeric_range` | 固定范围 |

**种子策略：**

- 在 `meta.meta_field_registry` 中写入 `schema_name='source'`、`table_name='fact_filtered'`、`field_scope='source'` 的字段记录。
- 在 `meta.meta_field_mapping_rule` 中写入源字段到过程字段的映射说明，例如 `sig_rsrq -> sig_rsrq -> sig_rsrq_final`、`lon_raw/lat_raw -> lon_final/lat_final`。
- 在 `meta.meta_source_field_compliance` 中写入首批 10 条规则，`parameter_refs` 只保存参数键路径，不复制参数值。

**兼容性修正：**

- 修复当前 `get_field_detail()` 查询列名：
  - `meta_field_mapping_rule` 应读取 `rule_type` / `rule_expression` / `source_field` / `source_table`
  - `meta_field_change_log` 应读取 `reason`，而不是不存在的 `change_reason`

### 3.2 后端 API 新增

| 接口 | 处理文件 | 请求 | 响应摘要 |
|------|---------|------|---------|
| `GET /api/v1/source-fields` | `backend/app/api/source_fields.py` | `run_id/search/logical_domain/operator_id_raw/tech/status/scope` | `{summary, items[]}`，返回原始字段列表、最新合规率、空值率、异常率、影响步骤 |
| `GET /api/v1/source-fields/{field_name}` | `backend/app/api/source_fields.py` | `run_id/compare_run_id` | `{field, compliance_rule, latest_snapshot, trend, mappings, related_steps, change_log}` |
| `GET /api/v1/source-fields/{field_name}/trend` | `backend/app/api/source_fields.py` | `limit` | `{field_name, history[]}`，按 run 返回合规率、空值率、异常率趋势 |
| `POST /api/v1/source-fields/refresh` | `backend/app/api/source_fields.py` | `{run_id?, force?, dimension_keys?}` | `{run_id, refreshed_fields, duration_seconds}` |
| `GET /api/v1/version/change-log` | `backend/app/api/workbench.py` | `run_id/compare_run_id` | `{parameter_changes, rule_changes, sql_changes, contract_changes}` |
| `GET /api/v1/steps/{step_id}/parameter-diff` | `backend/app/api/steps.py` | `run_id/compare_run_id` | `{global_diff, step_diff}` |
| `GET /api/v1/steps/{step_id}/object-diff` | `backend/app/api/steps.py` | `run_id/compare_run_id` | `{added, removed, changed}` |

**现有接口必须同步修正：**

- `/api/v1/fields`
  - 保持“过程字段注册表”语义，只返回 `field_scope='pipeline'`
  - 支持前端合并展示时的 `scope=pipeline`
- `/api/v1/fields/{field_name}`
  - 修正列名失配
  - 明确要求 `table_name` 或 `field_scope` 参与定位，避免同名字段混淆
- `/api/v1/steps/{step_id}/parameters`
  - 改为 `run_id -> wb_run.parameter_set_id -> wb_parameter_set.parameters`
  - 严禁继续读取 `is_active=true`

**响应模型补充：**

- `backend/app/models/schemas.py` 新增：
  - `SourceFieldSummaryOut`
  - `SourceFieldDetailOut`
  - `SourceFieldTrendPointOut`
  - `VersionChangeLogOut`
  - `StepParameterDiffOut`
  - `StepObjectDiffOut`

### 3.3 前端改造

**P3 页面结构：**

1. 顶部过滤栏
   - 搜索
   - 状态
   - 影响步骤
   - 范围筛选：`全部 / 原始字段 / 过程字段`
2. 顶部概览卡片
   - 正常字段数
   - 关注字段数
   - 异常字段数
   - 缺失字段数
3. 统一字段治理表
   - 原始字段
   - 标准字段
   - 范围
   - 类型
   - 状态
   - 空值率
   - 异常率
   - 合规率
   - 影响步骤
4. 同页展开区
   - 基本信息
   - 映射与解析规则
   - 合规/健康趋势
   - 影响步骤
   - 变更历史

**前端文件落点：**

- `frontend/js/pages/fields.js`
  - `loadFields()`
  - `mergeFieldRows()`
  - `renderFieldSummary()`
  - `renderFieldTable()`
  - `toggleFieldExpansion(fieldKey)`
  - `renderFieldExpansion(detail)`
- `frontend/js/ui/common.js`
  - `renderMetricTable()`
  - `renderStatCards()`
  - `renderBadge()`
- `frontend/js/ui/drawers.js`
  - 删除 `openFieldDrawer()` 的主路径职责，仅保留 D1/D2/D3
- `frontend/style.css`
  - 新增 P3 展开区、状态色、scope badge、合规率条样式

**交互原则：**

- 字段详情不再走抽屉主路径，改为“同页展开”。
- 影响步骤中的每一行都可跳转到 `#step/{step_id}`。
- `source-fields` 与 `fields` 两类接口在前端合并成一张表，不引入双页或双路由。

### 3.4 合规率计算

**触发时机：**

- `PATCH /api/v1/runs/{run_id}/status?status=completed` 成功后触发：
  - `refresh_workbench_snapshots(run_id)`
  - `refresh_source_field_snapshots(run_id)`
- `POST /api/v1/source-fields/refresh` 作为手动 repair path

**计算约束：**

- 只允许重算最新 completed run，历史 run 默认只读。
- 页面请求绝不直接触发 `fact_filtered` 全表扫描。
- 运行参数一律从 `wb_run.parameter_set_id` 解析，不读取 active 参数集。

**切片维度：**

- `ALL`
- `operator:{operator_id_raw}`
- `tech:{tech_norm}`
- `operator:{operator_id_raw}|tech:{tech_norm}`

**SQL 生成策略：**

- Phase 3 采用“单字段一条 `INSERT ... SELECT` + `GROUPING SETS`”的简单方案。
- 每条规则由 `fields.py::compile_compliance_sql()` 根据 `rule_type + rule_config + parameter_values` 编译成布尔表达式。
- 每次刷新写入 `parameter_values`，确保历史 run 可追溯。

**不做的事：**

- 不做 `TABLESAMPLE`
- 不做 API 实时聚合
- 不做任意日期 ad-hoc 钻取
- 不做 `raw_records` 主路径计算

## 4. 代码拆分方案（最终版）

### 4.1 `workbench.py` → 5 个业务模块

> 说明：`app/services/workbench/base.py` 作为辅助文件存在，承接 `_scalar` / `_first` / `_all` / `_json` / `_number` / lock；不计入 5 个业务模块。

| 模块 | 职责 | 预估行数 | 关键函数 |
|------|------|---------|---------|
| `app/services/workbench/catalog.py` | bootstrap、字段注册同步、run/version 上下文、版本变更摘要、run 参数解析 | 320~380 | `ensure_reference_data`、`ensure_field_registry`、`latest_run_id`、`latest_completed_run_id`、`previous_completed_run_id`、`build_run_summary`、`get_version_context`、`get_version_history`、`get_version_change_log`、`resolve_run_parameters` |
| `app/services/workbench/snapshots.py` | 快照计算、快照刷新、快照读取、Gate 计算 | 380~460 | `_compute_layer_snapshot`、`_compute_step_metrics`、`_compute_anomaly_stats`、`_compute_rule_hits`、`_compute_gate_results`、`ensure_snapshot_bundle`、`list_layer_snapshot`、`list_step_summary`、`list_anomaly_summary`、`refresh_all` |
| `app/services/workbench/steps.py` | P2 读模型、参数对比、对象级差异、分布读模型 | 300~380 | `get_step_metrics`、`get_step_rules`、`get_step_sql`、`get_step_diff`、`get_step_parameter_diff`、`get_step_object_diff`、`list_operator_tech_distribution`、`list_gps_status_distribution`、`list_signal_fill_distribution` |
| `app/services/workbench/fields.py` | 过程字段详情、原始字段治理、合规规则编译、合规快照刷新 | 420~480 | `_steps_by_field`、`list_fields`、`get_field_detail`、`list_source_fields`、`get_source_field_detail`、`list_source_field_trend`、`compile_compliance_sql`、`refresh_source_field_snapshots` |
| `app/services/workbench/samples.py` | P4 样本集、样本过滤、D3 详情载荷 | 240~320 | `_build_sample_sql`、`list_sample_sets`、`get_sample_set_detail`、`get_step_samples`、`get_sample_object_detail` |

### 4.2 `app.js` → 9 个模块

| 模块 | 职责 | 预估行数 | 关键函数 |
|------|------|---------|---------|
| `frontend/js/main.js` | 入口、路由、全局事件挂载 | 60~100 | `init`、`renderRoute` |
| `frontend/js/core/api.js` | `fetch` 封装、超时、sessionStorage 缓存、失效 | 120~180 | `api`、`getCached`、`setCached`、`clearApiCache` |
| `frontend/js/core/state.js` | 全局状态与路由状态 | 40~80 | `state`、`resetPageState` |
| `frontend/js/ui/common.js` | HTML escape、格式化、表格/卡片/徽标、toast、drawer shell | 140~220 | `escapeHtml`、`fmt`、`pct`、`renderMetricTable`、`renderStatCards`、`openDrawer`、`closeDrawer` |
| `frontend/js/ui/drawers.js` | D1/D2/D3 抽屉内容与交互 | 120~180 | `openVersionDrawer`、`openSqlDrawer`、`openSampleDrawer` |
| `frontend/js/pages/overview.js` | P1 总览页 | 220~280 | `loadOverview`、`buildOverviewDiffRows`、`buildFocusItems` |
| `frontend/js/pages/step.js` | P2 步骤页 | 240~320 | `loadStep`、`renderParametersTable`、`renderJsonMetrics` |
| `frontend/js/pages/fields.js` | P3 字段治理页 | 220~300 | `loadFields`、`mergeFieldRows`、`renderFieldTable`、`toggleFieldExpansion` |
| `frontend/js/pages/samples.js` | P4 样本研究页 + D3 入口 | 160~220 | `loadSamples`、`applySampleFilters`、`openSampleDrawer` |

## 5. V2 还原补齐清单

### 按优先级排序

| # | 组件 | 当前 | 目标 | 优先级 | 工作量 | 前置依赖 |
|---|------|------|------|--------|--------|---------|
| 1 | P3 字段治理主表 | 当前只有过程字段列表和抽屉详情，且详情查询列名失配 | 统一治理表格 + 同页展开 + 原始/过程字段同屏 | P0 | 大 | 字段治理 DDL、`source-fields` API |
| 2 | P3 合规趋势/规则 | 无源字段合规规则、无 run 趋势、无参数联动 | 展示规则定义、参数值、近 6 次 run 趋势 | P0 | 大 | 合规快照服务 |
| 3 | D3 样本详情抽屉 | 只有样本记录表，没有“原始值 vs 修正值” | 展示原始值、处理后值、命中规则、compare 差异 | P1 | 中 | 样本对象详情 API |
| 4 | P4 问题类型筛选 | 无问题类型 tag、无来源步骤筛选、无 run 过滤 | 完整问题类型筛选条 + 来源步骤 + run 选择 | P1 | 中 | 样本 API 扩展 |
| 5 | D1 版本与运行抽屉 | 只有 run 列表 | 展示参数/规则/SQL/契约变化摘要 | P1 | 小 | `version/change-log` |
| 6 | P2 参数区 | 只看本次参数 | 当前值 vs 对比 run 值 + 变化标记 | P1 | 小 | `parameter-diff` API |
| 7 | P2 SQL 区 / D2 | 只看原文件文本 | 展示执行顺序、resolved SQL、compare SQL | P1 | 中 | `steps/{id}/sql` 扩展 |
| 8 | P2 差异区 | 只有数值 diff | 增加对象级 diff：新增/消失/变化对象 | P1 | 中 | `object-diff` API |
| 9 | P1 Focus Areas | 只有步骤变化和异常分布 | 增加字段变化、版本变化原因、可回跳链接 | P2 | 小 | 版本变更 + 字段趋势 |
| 10 | Gate 与关键指标 | `wb_gate_result=0`，Doc04 多数指标未落地 | 先补 8~10 个核心 Gate 和主链路指标 | P2 | 中 | 历史正确性修复 |

## 6. 开发计划

### 6.1 里程碑定义

| 里程碑 | 包含任务 | 验收标准 | 预估复杂度 |
|--------|---------|---------|-----------|
| M1 架构与历史正确性 | T01~T04 | `workbench.py` / `app.js` 完成拆分；`steps/{id}/parameters` 改为 run 绑定；历史快照默认只读；compare 语义不再依赖假 fallback | 中 |
| M2 字段治理闭环 | T05~T08 | `source-fields` API 可用；P3 能展示原始字段定义、合规规则、合规率、趋势、影响步骤；当前字段详情不再 500 | 大 |
| M3 V2 关键交互补齐 | T09~T11 | P2 参数/SQL/对象 diff 可用；P4 有问题类型筛选；D3 能展示原始值 vs 修正值；D1 有版本变化 | 大 |
| M4 门控与中文化收口 | T12~T13 | Gate 落库；主链路核心指标补齐；字段中文说明覆盖率 > 80%；前端主路径中文化完成 | 中 |

### 6.2 任务排序（含依赖关系）

| # | 任务 | 里程碑 | 前置 | 涉及层 | 涉及文件 | 工作量 |
|---|------|--------|------|--------|---------|--------|
| T01 | 后端拆分：`workbench.py` → `app/services/workbench/*.py`，保留兼容 facade | M1 | 无 | 后端 | `backend/app/services/workbench.py`、新增 `backend/app/services/workbench/base.py`、`catalog.py`、`snapshots.py`、`steps.py`、`fields.py`、`samples.py` | 中 |
| T02 | 前端拆分：`app.js` → ES Modules | M1 | 无 | 前端 | `frontend/app.js`、新增 `frontend/js/main.js`、`core/api.js`、`core/state.js`、`ui/common.js`、`ui/drawers.js`、`pages/*.js`、`index.html` | 中 |
| T03 | 修正历史正确性：run 绑定参数、run 绑定 compare、禁止 active 参数污染历史页面 | M1 | T01 | 后端 | `backend/app/api/steps.py`、`backend/app/api/runs.py`、`backend/app/services/workbench/catalog.py` | 中 |
| T04 | 修正快照语义：run 完成后刷新、历史 run 默认只读、repair 仅允许 latest run | M1 | T01,T03 | 后端 | `backend/app/api/runs.py`、`backend/app/services/workbench/snapshots.py` | 中 |
| T05 | 新增字段治理 DDL 与种子 SQL | M2 | T03 | 数据库 | 新增 `rebuild/sql/04_phase3_field_governance.sql`、新增 `rebuild/sql/05_phase3_field_governance_seed.sql` | 小 |
| T06 | 实现 `source-fields` 服务与 API | M2 | T01,T04,T05 | 后端 | 新增 `backend/app/api/source_fields.py`、`backend/app/services/workbench/fields.py`、`backend/app/models/schemas.py`、`backend/app/main.py` | 中 |
| T07 | 修复现有 `/fields/{field_name}` 查询失配 | M2 | T01 | 后端 | `backend/app/services/workbench/fields.py`、`backend/app/api/workbench.py` | 小 |
| T08 | 重做 P3 页面：统一治理表格 + 同页展开 | M2 | T02,T06,T07 | 前端 | `frontend/js/pages/fields.js`、`frontend/js/ui/common.js`、`frontend/style.css` | 中 |
| T09 | 补 P2 证据链：参数 diff、resolved SQL、对象级 diff | M3 | T01,T03,T04 | 后端+前端 | `backend/app/api/steps.py`、`backend/app/services/workbench/steps.py`、`frontend/js/pages/step.js`、`frontend/js/ui/drawers.js` | 中 |
| T10 | 补 P4 与 D3：问题类型筛选、来源步骤筛选、样本详情载荷 | M3 | T01,T02 | 后端+前端 | `backend/app/services/workbench/samples.py`、`backend/app/api/workbench.py` 或新增 `api/samples.py`、`frontend/js/pages/samples.js`、`frontend/js/ui/drawers.js` | 中 |
| T11 | 补 D1 与 P1：版本变化摘要、字段变化 Focus | M3 | T03,T06 | 后端+前端 | `backend/app/api/workbench.py`、`backend/app/services/workbench/catalog.py`、`frontend/js/pages/overview.js`、`frontend/js/ui/drawers.js` | 小 |
| T12 | Gate 结果与主链路缺口指标补齐 | M4 | T04,T09 | 后端 | `backend/app/services/workbench/snapshots.py`、`backend/app/api/metrics.py` | 中 |
| T13 | 字段中文说明回填与前端中文化收口 | M4 | T05,T08 | 数据库+前端 | `rebuild/sql/05_phase3_field_governance_seed.sql`、`backend/app/services/labels.py`、`frontend/js/pages/*.js`、`frontend/style.css` | 小 |

### 6.3 实施顺序

1. 先拆分后端和前端，再做功能开发。原因很直接：在 2,045 行 `workbench.py` 和 1,184 行 `app.js` 上继续堆功能，回归风险只会继续扩大。
2. 拆分后先修“历史正确性”，再做字段治理。否则 P3 新增的合规率、趋势和 compare 仍然会绑定错误参数或被当前数据覆盖，页面再完整也不可信。
3. 数据库变更放在字段治理后端实现之前。`field_scope`、合规规则表、快照表不落地，`source-fields` API 无法稳定设计。
4. P3 先于 P2/P4/D1/D3。字段治理是本阶段最高优先级，也是 V2 缺口里最严重的一块；P2/P4 证据链随后补齐。
5. Gate 和中文化最后收口。它们重要，但不应阻塞“历史正确性 + 字段治理闭环 + V2 关键交互”这三件 P0 任务。

## 7. AI 开发纪律检查清单

- [ ] 新增业务文件不超过 500 行，目标 200~400 行
- [ ] 单个函数不超过 80 行，渲染和 SQL 生成必须继续拆小
- [ ] 不引入新框架，不引入构建链；前端只用原生 ES Modules
- [ ] 修改前先读取目标文件及直接调用方，禁止盲改
- [ ] 任何 run 相关读取都必须走 `run_id` 绑定版本，禁止读取 active 参数替代历史
- [ ] 重计算不得进入请求路径；`fact_filtered` 全量扫描只能在 run 完成后或手动 refresh 中发生
- [ ] 历史 snapshot 默认只读；若后续做 repair，必须显式标记“snapshot regenerated”
- [ ] 拆分期保留兼容 facade，不能一次性打断现有 router import
- [ ] 新增 service/API 函数必须有清晰 docstring 和 schema
- [ ] 每完成一个里程碑都要跑后端 API 测试和一次前端 smoke test
- [ ] 不修改与任务无关的业务逻辑，不顺手重写现有页面结构
- [ ] 所有字段治理展示以数据库元数据为主，`labels.py` 只做兜底

## 8. 待用户裁决的问题

当前无新增待裁决问题。

原因：

- 6 个关键决策均已按 prompt 规则完成裁决。
- P3 前端组织虽然三方意见不同，但 V2 原型已明确要求“统一字段表 + 同页展开”，无需再额外出 `Q05`。
