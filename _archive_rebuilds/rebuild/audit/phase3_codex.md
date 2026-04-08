# Codex 第三阶段规划审计报告

> 审计日期：2026-03-24
> 审计文件数：25
> 补充核对：PG17 实库（pipeline / workbench / meta）+ 3 条代表性 `EXPLAIN ANALYZE`

本报告基于 25 个指定文件的完整阅读，以及 PG17 实库核对后形成。结论不是“还能继续优化”，而是“第三阶段必须先把历史正确性、原始字段治理、V2 关键缺口和代码拆分一次性补到位”，否则工作台会继续停留在“可演示但不可作为稳定验证工具”的状态。

当前最关键的 5 个事实：

1. `meta.meta_field_registry` 561 行全部是 `pipeline` 过程字段，`description` 561/561 为空，`mapped_from_other_source` 为 0，说明“原始字段治理层”实际上不存在。
2. `meta.meta_field_health` / `meta.meta_field_mapping_rule` / `meta.meta_field_change_log` / `meta.meta_exposure_matrix` 全为空，P3 的趋势、变更、合规展示没有真实数据底座。
3. `workbench.wb_baseline`、`wb_step_execution`、`wb_gate_result`、`wb_reconciliation` 全为空；`wb_run.compare_run_id` 全为空，版本体系只闭合了“展示标签”，没有闭合“验证链路”。
4. `workbench.py` 当前既做 bootstrap、快照、版本、字段、样本、SQL、规则，又直接写重 SQL，2,045 行已经成为第三阶段最大的后端重构阻塞。
5. 代表性全表聚合实测：
   - `pipeline.fact_filtered`（2,178 万行 / 13GB）约 3.1s
   - `pipeline.fact_final`（3,049 万行 / 18GB）约 3.8s
   - `pipeline.raw_records`（2.51 亿行 / 109GB）约 21.9s  
   所以“原始字段合规率”可以做，但必须做成离线快照，不能做成 API 实时查询。

## 1. 各维度评估

### 维度 F：字段治理完整性

**当前状态评估：**

- 当前 P3 只覆盖“过程字段注册（Pipeline Column Registry）”，没有覆盖“原始字段定义与合规规则（Source Field Governance）”。
- `rebuild/backend/app/services/workbench.py` 的 `ensure_field_registry()` 只从 `information_schema.columns` 拉 `pipeline` schema 字段，并把 `source_field/source_table` 回填成自己本身；这意味着它不是“映射注册表”，只是“列目录快照”。
- `rebuild/frontend/app.js` 的 `loadFields()` 只渲染 `/fields` 返回的 pipeline 字段列表，没有“原始字段”标签页、没有合规率、没有趋势、没有变更历史、没有批次切片。
- 实库中：
  - `meta.meta_field_registry = 561`
  - `description` 空值 = `561`
  - `schema_name <> 'pipeline'` 的记录 = `0`
  - `source_field/source_table` 与当前字段不同的记录 = `0`
- 更严重的是，`get_field_detail()` 当前查询的 `meta_field_mapping_rule` / `meta_field_change_log` 列名与真实 DDL 不一致，P3 字段详情不只是“能力弱”，而是存在直接 500 的风险。

**结论：** 当前字段治理得分仍然只有 30~35/100。第三阶段必须把 P3 改成“双层模型”：

1. 原始字段治理：字段定义、合规规则、合规率、趋势、影响步骤。
2. 过程字段注册：保留当前 pipeline 列目录与映射信息。

#### F1. 数据库层

**三种候选方案对比：**

| 方案 | 说明 | 优点 | 问题 | 结论 |
|------|------|------|------|------|
| A. 扩展 `meta.meta_field_registry` | 在现有表直接加合规列 | 变更最少 | 会把 source / pipeline 两层语义混在一张表里；不同字段规则形态差异太大，表会迅速膨胀成大量空列 | 不推荐 |
| B. 新建 `meta.meta_source_field_compliance` | 用独立表管理原始字段合规规则 | 语义清晰、可版本化、可引用 `wb_parameter_set`、便于快照化 | 需要新增 1~2 张表和一套刷新逻辑 | **推荐** |
| C. 复用 `meta.meta_field_mapping_rule` | `rule_type='compliance'` | 看起来省表 | 该表当前是“映射规则”语义，不适合承载范围、黑名单、bbox、枚举白名单；而且当前服务层和 DDL 已经失配 | 不推荐 |

**推荐落地：B，但不新起第二套 field registry。**

具体做法：

1. 继续使用 `meta.meta_field_registry` 作为统一字段主表。
2. 给它增加 `field_scope`，区分 `pipeline` 与 `source`。
3. 原始字段行写入 `schema_name='source'`、`table_name='raw_records'`，不和当前 `/fields` 冲突。
4. 新建 `meta.meta_source_field_compliance` 存规则定义。
5. 新建 `meta.meta_source_field_compliance_snapshot` 存按 run / operator / tech / batch 的合规快照。
6. 现有 `meta.meta_field_mapping_rule` 继续承载“原始字段 -> 标准字段 / 过程字段”的映射说明，不再承载合规规则。

**推荐 DDL：**

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
    field_category      text            NOT NULL,   -- network / identity / signal / location
    unit                text,
    rule_config         jsonb           NOT NULL,   -- 统一存范围、无效值、bbox、枚举等
    parameter_refs      jsonb           NOT NULL DEFAULT '[]'::jsonb,
    repair_strategy     text            NOT NULL DEFAULT 'mark_only',  -- keep_and_mark / normalize / fill / reject
    severity            text            NOT NULL DEFAULT 'HIGH',
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
    compliance_version  text            NOT NULL,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
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

**示例数据：**

```sql
INSERT INTO meta.meta_field_registry (
    field_name, field_name_cn, table_name, schema_name, field_scope,
    data_type, is_nullable, source_field, source_table,
    logical_domain, unit, introduced_version, description
) VALUES
('operator_id_raw', '运营商ID', 'raw_records', 'source', 'source', 'text', true, 'operator_id_raw', 'raw_records', 'network', NULL, 'SRC-001', '五大核心 PLMN 编码。'),
('tech',            '原始制式',   'raw_records', 'source', 'source', 'text', true, 'tech',            'raw_records', 'network', NULL, 'SRC-001', '原始上报制式，需标准化为 4G/5G。'),
('lac_dec',         'LAC',       'raw_records', 'source', 'source', 'bigint', true, 'lac_dec',       'raw_records', 'identity', NULL, 'SRC-001', '位置区码，需校验范围与溢出值。'),
('cell_id_dec',     'Cell ID',   'raw_records', 'source', 'source', 'bigint', true, 'cell_id_dec',   'raw_records', 'identity', NULL, 'SRC-001', '终端连接小区标识。'),
('sig_rsrp',        'RSRP',      'raw_records', 'source', 'source', 'integer', true, 'sig_rsrp',      'raw_records', 'signal',   'dBm', 'SRC-001', '参考信号接收功率。'),
('sig_rsrq',        'RSRQ',      'raw_records', 'source', 'source', 'integer', true, 'sig_rsrq',      'raw_records', 'signal',   'dB',  'SRC-001', '参考信号接收质量。'),
('sig_sinr',        'SINR',      'raw_records', 'source', 'source', 'integer', true, 'sig_sinr',      'raw_records', 'signal',   'dB',  'SRC-001', '信噪比。'),
('sig_rssi',        'RSSI',      'raw_records', 'source', 'source', 'integer', true, 'sig_rssi',      'raw_records', 'signal',   'dBm', 'SRC-001', '接收信号强度。'),
('lon_raw',         '原始经度',   'raw_records', 'source', 'source', 'double precision', true, 'lon_raw', 'raw_records', 'location', 'deg', 'SRC-001', '原始经度。'),
('lat_raw',         '原始纬度',   'raw_records', 'source', 'source', 'double precision', true, 'lat_raw', 'raw_records', 'location', 'deg', 'SRC-001', '原始纬度。');

INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category, unit,
    rule_config, parameter_refs, repair_strategy, severity, applies_to_tech
)
SELECT id, 'SRC-C-001',
       'LAC 位置区码；4G 范围 0~65535，5G 范围 0~16777215，且需避开溢出黑名单值。',
       'identity', NULL,
       '{
          "type": "numeric_range_by_tech",
          "ranges": {"4G": {"min": 0, "max": 65535}, "5G": {"min": 0, "max": 16777215}},
          "invalid_values": [65534, 65535, 16777214, 16777215, 2147483647]
        }'::jsonb,
       '["global.lac_overflow_values"]'::jsonb,
       'keep_and_mark', 'HIGH', ARRAY['4G','5G']
FROM meta.meta_field_registry
WHERE schema_name = 'source' AND table_name = 'raw_records' AND field_name = 'lac_dec';

INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category, unit,
    rule_config, parameter_refs, repair_strategy, severity, applies_to_tech
)
SELECT id, 'SRC-C-001',
       'RSRP 参考信号接收功率；有效范围 [-140,-44]，无效值 {-110,-1,>=0}。',
       'signal', 'dBm',
       '{
          "type": "numeric_range",
          "range": {"min": -140, "max": -44},
          "invalid_values": [-110, -1],
          "must_be_negative": true
        }'::jsonb,
       '["global.rsrp_invalid_values","global.rsrp_max_valid"]'::jsonb,
       'keep_and_mark', 'HIGH', ARRAY['4G','5G']
FROM meta.meta_field_registry
WHERE schema_name = 'source' AND table_name = 'raw_records' AND field_name = 'sig_rsrp';

INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category, unit,
    rule_config, parameter_refs, repair_strategy, severity, applies_to_tech
)
SELECT id, 'SRC-C-001',
       '原始经纬度需落在中国边界框内；lon:[73,135]，lat:[3,54]。',
       'location', 'deg',
       '{
          "type": "bbox",
          "lon_field": "lon_raw",
          "lat_field": "lat_raw",
          "bbox": {"lon_min": 73, "lon_max": 135, "lat_min": 3, "lat_max": 54}
        }'::jsonb,
       '["global.china_bbox"]'::jsonb,
       'keep_and_mark', 'MEDIUM', ARRAY['4G','5G']
FROM meta.meta_field_registry
WHERE schema_name = 'source' AND table_name = 'raw_records' AND field_name = 'lon_raw';
```

**与 `wb_parameter_set` 的关联方式：**

- 规则定义不直接复制参数值，只保存 `parameter_refs`，例如 `global.operator_whitelist`。
- 生成快照时，用 `run_id -> wb_run.parameter_set_id -> wb_parameter_set.parameters` 解析出本次运行的生效参数，并写入 `meta.meta_source_field_compliance_snapshot.parameter_values`。
- 这样既保留“规则定义版本”，也保留“本次运行实际参数值”，历史可追溯。

**合规率计算方案：**

- **计算源表：** 必须以 `pipeline.raw_records` 为准。  
  `fact_filtered` / `fact_final` 已经发生过滤、纠偏、补齐，不适合回答“原始字段本身是否合规”。
- **计算方式：** 不做实时 API，统一做离线快照。
- **切片维度：** `dimension_key = ALL / operator:46000 / tech:4G / operator:46000|tech:4G`；批次通过 `run_id + batch_label(input_window_start~end)` 表示。
- **触发时机：**
  1. `full_rerun` 完成后自动刷新；
  2. `partial_rerun` 只有当参数集涉及 `global` 合规参数时才刷新；
  3. `sample_rerun` 不刷新全量源字段快照；
  4. 保留手动刷新按钮作为 repair path。
- **性能结论：**
  - `raw_records` 2.51 亿行 / 109GB 的代表性全表合规聚合实测约 `21.85s`
  - `fact_filtered` 同类聚合约 `3.07s`
  - `fact_final` 同类聚合约 `3.85s`
  - 因此：
    - 全量源字段快照可以作为离线任务执行；
    - 不应在 `/fields` 或字段详情 API 中实时触发；
    - 应尽量把多个字段聚合合并成 1~3 次扫描，而不是“每个字段一条 SQL”。

**推荐 SQL 生成策略：**

```sql
INSERT INTO meta.meta_source_field_compliance_snapshot (...)
SELECT
    :field_id,
    :compliance_version,
    :run_id,
    :batch_label,
    dimension_key,
    count(*) AS total_rows,
    count(*) FILTER (WHERE field_value IS NOT NULL) AS nonnull_rows,
    count(*) FILTER (WHERE is_compliant) AS compliant_rows,
    count(*) FILTER (WHERE field_value IS NOT NULL AND NOT is_compliant) AS anomalous_rows,
    count(*) FILTER (WHERE field_value IS NULL) AS null_rows,
    count(*) FILTER (WHERE is_invalid_value) AS invalid_value_rows,
    count(*) FILTER (WHERE is_out_of_range) AS out_of_range_rows,
    round(count(*) FILTER (WHERE is_compliant)::numeric / NULLIF(count(*) FILTER (WHERE field_value IS NOT NULL), 0), 4) AS compliance_rate,
    round(count(*) FILTER (WHERE field_value IS NULL)::numeric / NULLIF(count(*), 0), 4) AS null_rate,
    :parameter_values::jsonb
FROM (
    SELECT
        CASE
            WHEN GROUPING(operator_id_raw) = 0 AND GROUPING(tech) = 0 THEN 'operator:' || operator_id_raw || '|tech:' || tech
            WHEN GROUPING(operator_id_raw) = 0 THEN 'operator:' || operator_id_raw
            WHEN GROUPING(tech) = 0 THEN 'tech:' || tech
            ELSE 'ALL'
        END AS dimension_key,
        sig_rsrp AS field_value,
        sig_rsrp NOT IN (-110, -1) AND sig_rsrp < 0 AND sig_rsrp BETWEEN -140 AND -44 AS is_compliant,
        sig_rsrp IN (-110, -1) OR sig_rsrp >= 0 AS is_invalid_value,
        sig_rsrp IS NOT NULL AND NOT (sig_rsrp BETWEEN -140 AND -44) AS is_out_of_range
    FROM pipeline.raw_records
    GROUP BY GROUPING SETS ((), (operator_id_raw), (tech), (operator_id_raw, tech))
) t;
```

#### F2. 后端 API 层

**建议新增或重组 API：**

| 接口 | 作用 | 备注 |
|------|------|------|
| `GET /api/v1/fields/source` | 原始字段列表与合规摘要 | 支持 `run_id/search/domain/operator/tech/status` |
| `GET /api/v1/fields/source/{field_name}` | 原始字段详情 | 基本信息 + 规则 + 当前快照 + 映射 + 影响步骤 |
| `GET /api/v1/fields/source/{field_name}/trend` | 原始字段趋势 | 返回近 N 次 run 的合规率 / 空值率 / 异常率 |
| `POST /api/v1/fields/source/refresh` | 强制刷新源字段快照 | 默认刷新 latest completed run |
| `GET /api/v1/fields/{field_name}` | 过程字段详情 | 修复当前 schema/query 失配问题 |
| `GET /api/v1/version/change-log` | 参数 / 规则 / SQL / 契约变化摘要 | 供 D1 抽屉使用 |

**推荐 service 模块：**

- `app/services/source_fields/registry.py`
  - `list_source_fields()`
  - `get_source_field_detail()`
- `app/services/source_fields/compliance.py`
  - `compile_rule_sql()`
  - `refresh_source_field_snapshots()`
  - `list_source_field_trend()`
- `app/services/source_fields/mapping.py`
  - `list_source_to_pipeline_mappings()`

**关键函数签名建议：**

```python
async def list_source_fields(
    db: AsyncSession,
    *,
    run_id: int | None = None,
    search: str | None = None,
    logical_domain: str | None = None,
    operator_id_raw: str | None = None,
    tech: str | None = None,
    status: str | None = None,
) -> dict[str, Any]: ...

async def get_source_field_detail(
    db: AsyncSession,
    field_name: str,
    *,
    run_id: int | None = None,
    compare_run_id: int | None = None,
) -> dict[str, Any] | None: ...

async def refresh_source_field_snapshots(
    db: AsyncSession,
    run_id: int,
    *,
    force: bool = False,
    dimension_keys: list[str] | None = None,
) -> dict[str, Any]: ...
```

#### F3. 前端展示层

**P3 推荐结构：**

1. 顶部 summary 卡片
   - 原始字段总数
   - 当前 run 平均合规率
   - 高风险字段数
   - 相比 compare run 变化最大的字段数
2. Tabs
   - `原始字段治理`
   - `过程字段注册`
3. 原始字段列表
   - 字段
   - 业务含义
   - 适用范围（operator / tech）
   - 合规率
   - 空值率
   - 异常率
   - 影响步骤
   - 最近变化
4. 字段详情抽屉
   - 基本信息
   - 合规规则
   - 合规率趋势
   - operator / tech 切片
   - 映射规则
   - 影响步骤
   - 变更历史

**与现有代码的集成方式：**

- `loadFields()` 不再直接代表整个 P3，而改为：
  - `loadFieldGovernance()`
  - `renderSourceFieldTab()`
  - `renderPipelineFieldTab()`
- `openFieldDrawer()` 拆为：
  - `openSourceFieldDrawer()`
  - `openPipelineFieldDrawer()`
- 先修复当前 `/fields/{field_name}` 的 schema/query 失配，再上线新 tab；否则 P3 会继续有 500 风险。

**合规率可视化建议：**

- 列表页：单元格内 progress bar + 百分比 + 变化箭头
- 详情页：近 6 次 run 的小型趋势表，不强依赖重图表
- operator / tech 切片：二维表优先，热力色块次之

---

### 维度 A：V2 设计还原度

**总体判断：**

- P1：70/100，主干已回到 V2，但 D1 和“字段变化 / 版本变化”仍弱。
- P2：65/100，A-H 区块都在，但大多是“有盒子、少证据”，还原的是骨架，不是验证工作台。
- P3：25/100，当前实现与 V2 最核心诉求错位。
- P4：45/100，已有样本卡片，但缺筛选、对象详情和 compare 解释。
- D1/D2/D3：40/100，抽屉存在，但仍是“内容容器”，不是“验证工具”。

**V2 vs 当前实现对比矩阵**

| 组件/区块 | V2 设计 | 当前状态 | 差距 | 优先级 | 工作量 | 所需后端支持 |
|-----------|---------|---------|------|--------|--------|-------------|
| P1 上下文条 + D1 | 显示当前版本体系、最近运行、参数/规则变更 | 仅平铺 run 列表 | 缺“当前版本体系”“参数变更”“规则变更”3 个关键块 | P1 | M | `/version/change-log` |
| P1 链路节点 | 节点值 + compare 差异 + 可跳步骤 | 已实现 | 基本可用，但 compare 信号弱，伪日更仍占位 | P2 | S | 无 |
| P1 当前/对比 Run 摘要 | 结构接近 V2 | 已实现 | `compare_run` 实际来自“上一 completed run fallback”，不是显式版本比较 | P1 | S | run 绑定 compare |
| P1 重点关注 | V2 含步骤变化/新增问题/字段变化/改善 | 当前只有步骤变化 + 异常分布 + 运行上下文 | 缺“字段变化”和“版本变化原因” | P1 | M | 源字段快照 + 版本变更接口 |
| P1 操作区 | 全链路重跑 + 局部重跑选择 | 当前只有全链路重跑登记 | 缺步骤选择器和 compare 入口 | P2 | S | `/runs` 支持 compare/baseline 选择 |
| P2 A 步骤说明 | 名称、目的、上下游、状态、当前库映射 | 仅目的 + 技术标识 | 缺上下游链路、当前状态、当前库映射 | P1 | S | `/steps/{id}` 扩展 |
| P2 B 输入/输出 | 同屏展示库名/行数/主键/维度/vs compare | 当前只展示输入表和输出表行数 | 缺主键、对象维度、compare diff、输入输出矩阵 | P1 | M | `/steps/{id}/io-summary` 扩展 |
| P2 C 规则区 | 规则名、目的、关键参数、命中/过滤、影响 | 当前只到命中率 | 缺关键参数展开与“影响范围”列 | P1 | S | 现有 `key_params` 可直接下发 |
| P2 D 参数区 | 当前值、上次值、变化 | 当前只看本次参数 | 缺 parameter diff | P1 | M | `/steps/{id}/parameter-diff` |
| P2 E SQL 区 | SQL 名称、用途、顺序、展开 SQL | 当前只有文件路径 + 查看 SQL | 缺用途、顺序、resolved SQL、版本 diff | P1 | M | `/steps/{id}/sql` 扩展 |
| P2 F 数据变化 | 处理前后指标 + 过滤/补齐分项表 | 当前只有 metric cards + json | 缺“过程前后”解释视图 | P1 | M | `/steps/{id}/metrics` 扩展视图模型 |
| P2 G 差异区 | 指标差异 + 新增/消失对象 | 当前只有数值 diff | 缺对象级 diff（新增 LAC/消失 LAC/新增 BS 等） | P0 | L | `/steps/{id}/object-diff` |
| P2 H 样本区 | 典型/新增/边界样本分类 | 当前只按 sample set 平铺 | 缺样本分类和代表样本说明 | P1 | M | `/steps/{id}/samples` 扩展标签 |
| P3 原始字段层 | 原始字段、标准字段、状态、空值率、异常率、影响步骤 | 完全没有 | 当前 P3 不是 V2 的同一页面 | **P0** | **L** | 新增源字段 API |
| P3 详情展开 | 基本信息 / 映射规则 / 健康趋势 / 影响步骤 / 变更历史 | 仅基础信息 + 健康 + 影响步骤 + 映射规则 | 缺趋势、变更历史，且当前后端查询与 DDL 失配 | **P0** | **L** | 修复 `/fields/{field}` + 新增 trend/change |
| P4 问题类型筛选 | 问题类型 tag + 来源步骤 + run filter | 当前无过滤 | 缺研究入口，样本页不可钻取 | P1 | M | `/samples` 支持 filter 参数 |
| P4 样本集列表 | 表格化样本集 + 状态 + 展开 | 当前是 card 列表 | 缺来源步骤、状态、展开/折叠体验 | P2 | M | `/samples` 增加 summary |
| D2 SQL 抽屉 | SQL 列表、参数替换、版本 diff | 当前只显示原始文件文本 | 仍是“文件查看器” | P1 | M | resolved SQL / compare SQL |
| D3 样本/对象抽屉 | 原始值 vs 修正值、命中规则、compare 原因 | 当前只有样本记录表 | 缺对象信息、处理后信息、命中规则、compare 解释 | P1 | L | `/samples/{id}/objects/{object_id}` |

**补齐方案：**

1. P1 不需要大改布局，第三阶段重点补“字段变化摘要”和 D1 版本变化抽屉。
2. P2 不是继续加卡片，而是加“上下游/参数 diff/对象 diff/resolved SQL”四类验证证据。
3. P3 必须按“原始字段治理 + 过程字段注册”重做，不能继续在现有 `/fields` 上缝补。
4. P4 优先补“问题类型筛选 + 对象详情抽屉 + compare 原因”，不必先做生命周期流转。

---

### 维度 B：性能与缓存

**评估：**

1. **当前 snapshot + `AsyncTTLCache` 架构方向是对的。**
   - `wb_layer_snapshot` / `wb_step_metric` / `wb_anomaly_stats` 已经构成数据库物化层。
   - `APP_CACHE` 适合作为本地单实例 L1 缓存和请求去重层。
2. **但 snapshot 刷新触发点仍然放在 API 请求路径上。**
   - `ensure_snapshot_bundle()` 在首次访问时可能触发全套统计。
   - 当前因为只覆盖少量步骤，代价还能接受；第三阶段加入源字段合规快照后，这条路径就会变成首屏风险。
3. **不需要 Redis。**
   - 当前工作台是本地单 FastAPI 进程，`AsyncTTLCache` 已足够。
   - Redis 只会增加运维复杂度，不解决“历史快照不真实”这个核心问题。
4. **真正的性能风险不是缓存，而是“扫描对象选错了”。**
   - 原始字段合规率如果做实时 API，会直接把 21.9s 的 `raw_records` 全表扫描带回首屏路径。

**代表性性能测量：**

| 目标表 | 行数 / 大小 | 查询形态 | 实测时间 |
|--------|-------------|----------|---------|
| `pipeline.fact_filtered` | 21,788,532 / 13GB | 4 个 `COUNT FILTER` 全表聚合 | 约 3.07s |
| `pipeline.fact_final` | 30,492,108 / 18GB | 4 个 `COUNT FILTER` 全表聚合 | 约 3.85s |
| `pipeline.raw_records` | 251,172,880 / 109GB | 6 个 `COUNT FILTER` 全表聚合 | 约 21.85s |

**建议：**

1. **保留 `AsyncTTLCache`，定位为 L1。**
   - 继续承担 60s~600s 的短 TTL。
   - 继续做 inflight dedupe。
   - 不再赋予“跨进程一致性”职责。
2. **把 snapshot 刷新从“API 首次请求触发”改为“run 完成后触发”。**
   - Worker 在 `run status -> completed` 后执行：
     1. `refresh_workbench_snapshots(run_id)`
     2. `refresh_source_field_snapshots(run_id)`（仅当需要）
   - `ensure_snapshot_bundle()` 只保留为 repair path。
3. **新增源字段快照表，不把合规率塞进 `meta_field_health`。**
   - `meta_field_health` 偏“过程字段健康快照”；
   - 原始字段合规率本质是“版本化规则 + 批次切片”的独立读模型。
4. **切片策略优先级：**
   - Phase 3 必做：`ALL` / `operator` / `tech` / `operator+tech`
   - Phase 3 不做：原始表 ad-hoc 日级钻取
   - 如果后续要做日级切片，再考虑 `raw_records` 的日期表达式索引或分区。

---

### 维度 C：代码架构改造

**当前状态：**

- `rebuild/backend/app/services/workbench.py`：2,045 行，职责混杂。
- `rebuild/frontend/app.js`：1,184 行，页面、数据层、抽屉、全局状态全部堆在一起。
- 两处超长文件都已经不是“可读性问题”，而是“第三阶段任何新增功能都要冒着回归风险继续往一个巨石里塞”。

#### C1. 后端拆分方案

**推荐目录结构：**

```text
rebuild/backend/app/services/workbench/
  __init__.py
  base.py              # _all/_first/_scalar/_json/_number/_format_duration
  bootstrap.py         # ensure_reference_data / seed 默认版本与样本
  versions.py          # latest_run_id / build_run_summary / get_version_context/history
  snapshot_builders.py # _compute_layer_snapshot / _compute_step_metrics / _compute_anomaly_stats / _compute_rule_hits
  snapshots.py         # ensure_snapshot_bundle / list_layer_snapshot / list_step_summary / list_anomaly_summary
  steps.py             # get_step_metrics / get_step_rules / get_step_sql / get_step_diff
  fields.py            # ensure_field_registry / list_fields / get_field_detail / _steps_by_field
  samples.py           # list_sample_sets / get_sample_set_detail / get_step_samples
  source_fields.py     # 第三阶段新增：原始字段治理与合规快照
```

**职责与依赖方向：**

| 模块 | 职责 | 允许依赖 |
|------|------|---------|
| `base.py` | 通用 DB helper / 序列化 helper | SQLAlchemy、标准库 |
| `bootstrap.py` | 默认规则/SQL/契约/样本自举 | `base.py`、`labels.py` |
| `versions.py` | run/compare/baseline 视图 | `base.py`、`bootstrap.py` |
| `snapshot_builders.py` | 纯计算与写入前组装 | `base.py`、`labels.py` |
| `snapshots.py` | snapshot 读写和缓存协调 | `versions.py`、`snapshot_builders.py` |
| `steps.py` | P2 所需读模型 | `snapshots.py`、`base.py` |
| `fields.py` | P3 pipeline 字段治理 | `base.py`、`labels.py` |
| `samples.py` | P4 与 D3 | `base.py`、`labels.py` |
| `source_fields.py` | 第三阶段原始字段治理 | `base.py`、`versions.py` |

**必须同步修正的两类逻辑：**

1. 参数读取必须从 `run_id -> parameter_set_id` 走，不能继续读“当前 active 参数集”。
2. snapshot builder 必须明确区分“历史 snapshot 只读”与“重建当前 run snapshot”，不能让旧 run 被当前 pipeline 状态覆盖。

#### C2. 前端拆分方案

**不引入框架时的推荐方式：原生 ES Modules。**

原因：

- 当前浏览器环境足够支持；
- 比“多个 script 标签 + 全局命名空间”更易控依赖；
- 未来若要接 Vite / 构建器，迁移成本最低。

**推荐结构：**

```text
rebuild/frontend/js/
  main.js
  core/
    api.js
    state.js
    router.js
    dom.js
  components/
    tables.js
    cards.js
    drawers.js
    badges.js
  pages/
    overview.js
    step.js
    fields.js
    samples.js
```

**模块职责：**

| 文件 | 职责 |
|------|------|
| `core/api.js` | `api()`、TTL、sessionStorage、timeout、invalidate |
| `core/state.js` | 全局状态与 route 状态 |
| `core/router.js` | hash 解析与 page dispatch |
| `core/dom.js` | `setMain`、toast、open/close drawer、escapeHtml |
| `components/tables.js` | `renderMetricTable`、key-value table |
| `components/cards.js` | stat card / chips / empty state |
| `pages/overview.js` | `loadOverview()` 与 overview renderer |
| `pages/step.js` | `loadStep()` 与 A-H 区块 renderer |
| `pages/fields.js` | source/pipeline 字段治理页 |
| `pages/samples.js` | 样本研究页与 filter 逻辑 |

**HTML 入口改造：**

```html
<script type="module" src="js/main.js"></script>
```

#### C3. 函数级重构

**`loadOverview()` 拆分建议：**

- `fetchOverviewBundle(runId, compareRunId, force)`
- `buildOverviewViewModel(bundle)`
- `renderOverviewHeader(vm)`
- `renderOverviewStats(vm)`
- `renderOverviewFlow(vm)`
- `renderOverviewRunCards(vm)`
- `renderOverviewFocus(vm)`
- `renderOverviewSupplement(vm)`

**`loadStep()` 拆分建议：**

- `fetchStepBundle(stepId, runId, compareRunId, force)`
- `renderStepIntro(vm)`
- `renderStepIO(vm)`
- `renderStepRules(vm)`
- `renderStepParameters(vm)`
- `renderStepSql(vm)`
- `renderStepMetrics(vm)`
- `renderStepDiff(vm)`
- `renderStepSamples(vm)`
- `renderStepActions(vm)`

**应提取的公共模板：**

- `renderSectionCard(title, body, subtitle?)`
- `renderStatGrid(cards)`
- `renderDatasetTable(rows)`
- `renderChipList(values)`
- `renderDiffBadge(value)`

---

### 维度 D：中文化完善

**当前状态：**

- `meta.meta_field_registry.description` 561 条全空。
- `field_name_cn` 中仍有 285 条是空值或直接等于英文原名。
- 上下文条仍保留 `Run` / `Compare` / `SQL` / `WangYou Data Governance Workbench` 等英文主展示。
- 原始字段业务含义没有权威数据源，仍依赖 `labels.py` 的轻量兜底。

**方案：**

1. **把 `labels.py` 从“主数据”降级为“fallback”。**
   - 权威来源应转为：
     - `meta.meta_field_registry.field_name_cn`
     - `meta.meta_field_registry.description`
     - `meta.meta_source_field_compliance.business_definition`
2. **批量回填 pipeline 字段 description。**
   - 优先级：
     1. Doc02 映射字典
     2. PG `COMMENT ON COLUMN`
     3. fallback 模板  
       例如：`{field_name_cn}。来源 {source_table}.{source_field}，用于 {table_name_cn}。`
3. **上下文条中文主展示。**
   - `Run` -> `当前 Run`
   - `Compare` -> `对比 Run`
   - `SQL` -> `SQL版本`
   - 顶部 kicker 改为中文主标题，英文作为次要副标题
4. **原始字段业务注释维护位置：**
   - 统一维护在 `meta.meta_source_field_compliance.business_definition`
   - UI 不再从代码硬编码解释 `LAC/RSRP/SINR`

**建议执行顺序：**

1. 先把 source field registry 与 compliance 落库；
2. 再批量回填 pipeline field description；
3. 最后收拢前端英文展示与 `labels.py` 依赖。

---

### 维度 E：业务逻辑正确性

**检查结果：**

| 检查项 | 当前结果 | 结论 |
|--------|---------|------|
| `wb_rule_set / wb_sql_bundle / wb_contract` | 各 1 条 | 版本标签存在 |
| `wb_baseline` | 0 条 | 基线版本未闭环 |
| `wb_run.compare_run_id` | 5 个 run 全为 NULL | compare 仅靠“上一 completed run fallback” |
| `wb_step_execution` | 0 条 | 没有真实 step run 历史 |
| `wb_gate_result` | 0 条 | Doc04 门控未落地 |
| `wb_reconciliation` | 0 条 | 对账体系未落地 |
| `wb_step_metric` | 仅覆盖 10 个 step 组 | 与 Doc04 的 19 组定义差距大 |
| `meta_field_health / mapping_rule / change_log` | 全空 | 字段治理链路未闭环 |

**关键问题 1：参数与规则命中不是 run 绑定，而是 active 参数集绑定。**

- `steps.py` 的 `/steps/{step_id}/parameters` 直接读取 `WHERE is_active = true ORDER BY id DESC LIMIT 1`
- `workbench.py` 的 `_compute_rule_hits()` 也先读 `_active_parameter_json()`  
这意味着一旦参数集切换，历史 run 页面会被“当前 active 参数”污染，无法保证“看见的是当时跑的版本”。

**第三阶段必须改为：**

```text
run_id -> wb_run.parameter_set_id -> wb_parameter_set.parameters
```

而不是：

```text
active wb_parameter_set
```

**关键问题 2：snapshot 以 run_id 存储，但计算并不按 run 隔离数据源。**

- `_compute_layer_snapshot()`、`_compute_step_metrics()`、`_compute_anomaly_stats()`、`_compute_rule_hits()` 全都直接扫描当前 `pipeline.*`
- 它们把 `run_id` 只当“写入标签”，没有当“历史数据范围”
- 实库中 run 3/4/5 的 layer snapshot 和 step metric 值完全一致，说明当前 compare-run 很可能比较的是“同一份当前数据”

这意味着：

1. 如果后续规则改动并重刷 snapshot，旧 run 的快照会被当前 pipeline 结果覆盖。
2. 当前 compare-run 能展示，不代表历史 run 真正可比。

**第三阶段必须明确二选一：**

- 方案 1：snapshot 一经写入就不可重算旧 run，只允许重算 latest run；历史 run 只读。
- 方案 2：保留 run 级别的中间结果 / manifest / object diff 数据，支持真正的历史重建。  

对当前本地工作台，推荐方案 1。

**关键问题 3：Doc04 指标体系与当前实现存在结构性缺口。**

当前未进入 `wb_step_metric` 的步骤：

- `s1` 基础统计
- `s2` 合规标记
- `s3` LAC统计
- `s5` Cell统计
- `s32` GPS对比
- `s34` 信号对比
- `s35` 动态检测
- `s36` BS异常标记
- `s37` 碰撞不足标记
- `s38` Cell映射交付
- `s40` 完整回归GPS
- `s42` 最终对比

因此 P2 当前虽然有 A-H 区块，但很多步骤的 F/G 区本质上还没有底层指标。

**关键问题 4：同一页面混用了“近似行数”和“精确行数”。**

- `wb_layer_snapshot` 用的是 `pg_stat_user_tables.n_live_tup`
- `wb_step_metric` 用的是 `COUNT(*)`

所以：

- `L0_raw` layer snapshot = `251,172,880`
- `s0.total` step metric = `251,208,334`

这会让 P1 出现“同一层级、两个数字”的低可信体验。  
第三阶段应统一：

- 首页与步骤页主展示统一使用 snapshot 固化值；
- 若必须显示近似值，明确标注 `estimated`。

---

## 2. 第三阶段开发计划

### 开发顺序建议

| 序号 | 任务 | 依赖 | 工作量 | 涉及文件 |
|------|------|------|--------|---------|
| 1 | 修正历史正确性：run 绑定参数、禁止历史 snapshot 被当前数据重写 | 无 | M | `rebuild/backend/app/api/steps.py`、`rebuild/backend/app/services/workbench.py`、`rebuild/backend/app/api/runs.py` |
| 2 | 建立 source field 数据模型：`field_scope` + `meta_source_field_compliance` + snapshot 表 + seed 数据 | 1 | L | `rebuild/docs/05_工作台元数据DDL.md`、新增 SQL/seed、后端 services |
| 3 | 实现原始字段合规快照任务与 API | 2 | L | 新增 `app/api/source_fields.py`、`app/services/source_fields/*.py` |
| 4 | 重做 P3：原始字段 tab + 过程字段 tab + 详情抽屉 + 趋势/变更历史 | 2,3 | L | `rebuild/frontend/app.js` 或拆分后的 `pages/fields.js`、`index.html`、`style.css` |
| 5 | 补 P2 证据链：参数 diff、resolved SQL、对象级 diff、分类样本 | 1 | L | `app/api/steps.py`、`services/workbench/steps.py`、前端 step page |
| 6 | 补 P1/P4/D1/D2/D3 的 V2 关键缺口 | 3,5 | M | `frontend/app.js`、`frontend/index.html`、`services/*` |
| 7 | 后端拆分 `workbench.py` | 1,2,3,5 | M | `rebuild/backend/app/services/workbench/` 新目录 |
| 8 | 前端拆分 `app.js` 为 ES Modules | 4,5,6 | M | `rebuild/frontend/js/*`、`index.html` |
| 9 | 中文化收口：field description、context bar、version change 文案 | 2,6 | S | `labels.py`、seed 脚本、前端模板 |

### 里程碑定义

| 里程碑 | 包含任务 | 验收标准 |
|--------|---------|---------|
| M1 历史正确性收口 | 任务 1 | 历史 run 页面读取 run 绑定参数；历史 snapshot 只读；compare-run 不再默认“假比较” |
| M2 原始字段治理闭环 | 任务 2,3,4 | P3 能展示原始字段定义、合规规则、合规率、趋势、影响步骤；字段详情无 500 |
| M3 V2 关键交互补齐 | 任务 5,6 | P2/P4/D1/D2/D3 补齐关键证据链，V2 还原度提升到 80/100 左右 |
| M4 架构与中文化收口 | 任务 7,8,9 | `workbench.py` / `app.js` 均拆分到单文件 500 行以内；中文主展示完成 |

### 有争议/需决策的问题

1. **原始字段主表是复用 `meta_field_registry` 还是单独建 `meta_source_field_registry`？**  
   推荐：复用 `meta_field_registry`，新增 `field_scope`。  
   优点：减少重复主键和变更日志体系。  
   缺点：现有 `/fields` 代码要从 `schema_name='pipeline'` 改成 `field_scope='pipeline'`。

2. **原始字段合规切片做到哪一层？**  
   推荐：Phase 3 先做 `ALL / operator / tech / operator+tech + batch_label(run)`。  
   不推荐 Phase 3 就做“任意日期 ad-hoc 下钻”，否则会把 `raw_records` 再推回实时查询路径。

3. **snapshot 刷新机制选 post-run worker 还是 cron？**  
   推荐：`post-run worker + manual fallback`。  
   原因：历史正确性最好，用户刷新语义最清晰。  
   cron 只适合作为兜底。

4. **前端模块化选 ES Modules 还是继续全局脚本？**  
   推荐：ES Modules。  
   原因：当前文件规模已经需要模块边界；继续靠全局函数会让 P3/P4/D1-D3 继续互相污染。

5. **历史 run 是否支持“重新计算 snapshot”？**  
   推荐：默认不支持。  
   如果要修旧 run，只允许专门 repair 命令，并在 UI 标记“snapshot regenerated”。  
   否则 compare-run 语义会继续漂移。

## 3. 最终建议

第三阶段不应再按“先补几个页面”推进，而应按下面的顺序推进：

1. 先把“历史正确性”修好：run 绑定参数、snapshot 只读、compare 语义明确。
2. 再把“原始字段治理”补成独立读模型：source registry + compliance rule + snapshot。
3. 然后补 V2 的关键交互缺口：P2 证据链、P4 研究入口、D1/D2/D3 抽屉。
4. 最后做架构拆分与中文化收口。

如果跳过第 1 步直接补 UI，第三阶段会得到一个“更好看但仍然不可信”的工作台；如果跳过第 2 步，P3 仍然不是用户要的字段治理页，而只是更复杂的列目录页。
