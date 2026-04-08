# 工作台元数据 DDL

> 版本：v1.0 | 日期：2026-03-23
> 依据：context.md UI设计 + 04指标注册表 + 现有obs表参考

---

## 1. Schema 与表总览

### 1.1 workbench schema（工作台核心，17张表）

| # | 表名 | 说明 | 预估行数级别 |
|---|------|------|------------|
| 1 | wb_run | 运行实例注册 | 百 |
| 2 | wb_parameter_set | 参数集版本 | 十 |
| 3 | wb_rule_set | 规则集版本 | 十 |
| 4 | wb_sql_bundle | SQL资源版本 | 十 |
| 5 | wb_contract | 字段契约版本 | 十 |
| 6 | wb_baseline | 基线版本 | 十 |
| 7 | wb_step_registry | 步骤注册表 | 22 |
| 8 | wb_step_execution | 步骤执行记录 | 千 |
| 9 | wb_step_metric | 步骤指标快照 | 万 |
| 10 | wb_layer_snapshot | 层级快照 | 千 |
| 11 | wb_gate_result | 质量门控结果 | 千 |
| 12 | wb_anomaly_stats | 异常统计 | 千 |
| 13 | wb_reconciliation | 对账校验 | 千 |
| 14 | wb_rule_hit | 规则命中记录 | 万 |
| 15 | wb_issue_log | 问题日志 | 百 |
| 16 | wb_patch_log | 补丁日志 | 百 |
| 17 | wb_sample_set | 样本集定义 | 百 |

### 1.2 meta schema（字段治理，5张表）

| # | 表名 | 说明 | 预估行数级别 |
|---|------|------|------------|
| 18 | meta_field_registry | 字段注册表 | 千 |
| 19 | meta_field_health | 字段健康快照 | 万 |
| 20 | meta_field_mapping_rule | 字段映射规则 | 百 |
| 21 | meta_field_change_log | 字段变更日志 | 千 |
| 22 | meta_exposure_matrix | 字段曝光矩阵 | 万 |

---

## 2. workbench schema DDL

### 2.1 wb_run — 运行实例注册

```sql
CREATE TABLE workbench.wb_run (
    run_id              serial          PRIMARY KEY,
    run_mode            text            NOT NULL,       -- full_rerun / partial_rerun / sample_rerun / pseudo_daily
    origin_scope        text            NOT NULL DEFAULT 'layer0_start',  -- layer0_start / filtered_start
    started_at          timestamptz     NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    status              text            NOT NULL DEFAULT 'running',  -- running / completed / failed / cancelled
    duration_seconds    integer,

    -- 版本绑定（均使用外键引用版本表）
    parameter_set_id    integer         REFERENCES workbench.wb_parameter_set(id),
    rule_set_id         integer         REFERENCES workbench.wb_rule_set(id),
    sql_bundle_id       integer         REFERENCES workbench.wb_sql_bundle(id),
    contract_id         integer         REFERENCES workbench.wb_contract(id),
    baseline_id         integer         REFERENCES workbench.wb_baseline(id),

    -- 运行配置
    input_window_start  date,           -- 输入数据窗口起始日期
    input_window_end    date,           -- 输入数据窗口结束日期
    compare_run_id      integer,        -- 对比基准 run_id
    shard_count         integer         DEFAULT 1,

    -- 运行模式扩展字段
    rerun_from_step     text,           -- 局部重跑起始步骤（run_mode=partial_rerun 时必填）
    sample_set_id       integer,        -- 样本重跑关联样本集（run_mode=sample_rerun 时必填）
    pseudo_daily_anchor date,           -- 伪日更锚点日期（run_mode=pseudo_daily 时必填）

    -- 备注
    triggered_by        text,           -- user / scheduler / api
    note                text,

    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_run_started ON workbench.wb_run(started_at DESC);
CREATE INDEX idx_wb_run_status ON workbench.wb_run(status);
```

### 2.2 wb_parameter_set — 参数集版本

```sql
CREATE TABLE workbench.wb_parameter_set (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,    -- 'P-001', 'P-002' ...
    description         text,
    parameters          jsonb           NOT NULL,           -- 完整参数快照 (JSON)
    is_active           boolean         NOT NULL DEFAULT true,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

COMMENT ON COLUMN workbench.wb_parameter_set.parameters IS '
结构示例：
{
  "global": {
    "operator_whitelist": ["46000","46001","46011","46015","46020"],
    "tech_whitelist": ["4G","5G"],
    "china_bbox": {"lon_min":73,"lon_max":135,"lat_min":3,"lat_max":54},
    "lac_overflow_values": [65534,65535,16777214,16777215,2147483647],
    "rsrp_invalid_values": [-110,-1],
    "rsrp_max_valid": -1
  },
  "step4": {
    "active_days_threshold": 7,
    "min_device_count": 5,
    "min_device_count_5g": 3,
    "report_count_percentile": 80
  },
  "step30": {
    "outlier_dist_m": 2500,
    "collision_p90_dist_m": 1500,
    "signal_top_n": 50,
    "center_bin_scale": 10000
  },
  "step31": {"drift_dist_m": 1500},
  "step35": {
    "min_bs_p90_m": 5000,
    "min_half_major_dist_km": 10,
    "min_effective_days": 5
  },
  "step40": {"gps_dist_threshold_4g": 1000, "gps_dist_threshold_5g": 500},
  "step50": {"min_rows": 5000},
  "step51": {"min_rows": 500},
  "step52": {"min_rows": 200}
}';
```

### 2.3 wb_rule_set — 规则集版本

```sql
CREATE TABLE workbench.wb_rule_set (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,    -- 'R1', 'R2' ...
    description         text,
    rules               jsonb           NOT NULL,           -- 规则定义快照
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.4 wb_sql_bundle — SQL资源版本

```sql
CREATE TABLE workbench.wb_sql_bundle (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,    -- 'S-001', 'S-002' ...
    description         text,
    file_manifest       jsonb           NOT NULL,           -- [{file, sha256, step}]
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.5 wb_contract — 字段契约版本

```sql
CREATE TABLE workbench.wb_contract (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,    -- 'C1', 'C2' ...
    description         text,
    contract_fields     jsonb           NOT NULL,           -- 必须存在的字段清单
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.6 wb_baseline — 基线版本

```sql
CREATE TABLE workbench.wb_baseline (
    id                  serial          PRIMARY KEY,
    version_tag         text            NOT NULL UNIQUE,    -- 'B1', 'B2' ...
    description         text,
    source_run_id       integer         REFERENCES workbench.wb_run(run_id),
    frozen_at           timestamptz,
    is_active           boolean         NOT NULL DEFAULT false,
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.7 wb_step_registry — 步骤注册表

```sql
CREATE TABLE workbench.wb_step_registry (
    step_id             text            PRIMARY KEY,        -- 's0', 's1', ..., 's52'
    step_order          integer         NOT NULL,           -- 执行顺序
    step_name           text            NOT NULL,           -- '数据标准化'
    step_name_en        text            NOT NULL,           -- 'Standardization'
    layer               text            NOT NULL,           -- 'L2', 'L3', 'L4', 'L5'
    is_main_chain       boolean         NOT NULL DEFAULT true,  -- 主链路 vs 附加步骤
    input_tables        text[]          NOT NULL,           -- 输入表名数组
    output_tables       text[]          NOT NULL,           -- 输出表名数组
    sql_file            text,                               -- 对应SQL文件路径
    description         text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.8 wb_step_execution — 步骤执行记录

```sql
CREATE TABLE workbench.wb_step_execution (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    step_id             text            NOT NULL REFERENCES workbench.wb_step_registry(step_id),
    started_at          timestamptz     NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    status              text            NOT NULL DEFAULT 'running',  -- running / completed / failed / skipped
    duration_seconds    integer,
    output_row_count    bigint,
    error_message       text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_step_exec_run ON workbench.wb_step_execution(run_id, step_id);
```

### 2.9 wb_step_metric — 步骤指标快照

```sql
CREATE TABLE workbench.wb_step_metric (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    step_id             text            NOT NULL REFERENCES workbench.wb_step_registry(step_id),
    metric_code         text            NOT NULL,           -- 's4_trusted_lac_cnt' 等
    metric_name         text            NOT NULL,           -- '可信LAC数'
    dimension_key       text            NOT NULL DEFAULT 'ALL',  -- 'ALL' / 'operator:46000' / 'tech:4G'
    value_num           numeric,                            -- 数值型指标
    value_text          text,                               -- 文本型指标
    value_json          jsonb,                              -- 结构化指标
    unit                text,                               -- '行' / '个' / '%' / '米'
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_step_metric_run ON workbench.wb_step_metric(run_id, step_id);
CREATE INDEX idx_wb_step_metric_code ON workbench.wb_step_metric(metric_code);
```

### 2.10 wb_layer_snapshot — 层级快照

```sql
CREATE TABLE workbench.wb_layer_snapshot (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    layer_id            text            NOT NULL,           -- 'L0', 'L2', 'L3', 'L4', 'L5_LAC', 'L5_BS', 'L5_CELL'
    row_count           bigint,
    pass_flag           boolean,                            -- 本层验收是否通过
    pass_note           text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_layer_snap_run ON workbench.wb_layer_snapshot(run_id);
```

### 2.11 wb_gate_result — 质量门控结果

```sql
CREATE TABLE workbench.wb_gate_result (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    gate_code           text            NOT NULL,           -- 'G01_ROW_CONSERVATION' 等
    gate_name           text            NOT NULL,
    severity            text            NOT NULL,           -- CRITICAL / HIGH / MEDIUM / LOW
    expected_rule       text,                               -- 期望规则描述
    actual_value        numeric,
    pass_flag           boolean         NOT NULL,
    remark              text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_gate_run ON workbench.wb_gate_result(run_id);
CREATE INDEX idx_wb_gate_pass ON workbench.wb_gate_result(pass_flag);
```

### 2.12 wb_anomaly_stats — 异常统计

```sql
CREATE TABLE workbench.wb_anomaly_stats (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    object_level        text            NOT NULL,           -- 'BS' / 'CELL' / 'LAC'
    anomaly_type        text            NOT NULL,           -- 'collision_suspect' / 'dynamic_cell' 等
    total_count         bigint          NOT NULL,
    anomaly_count       bigint          NOT NULL,
    anomaly_ratio       numeric,
    dimension_key       text            NOT NULL DEFAULT 'ALL',
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_anomaly_run ON workbench.wb_anomaly_stats(run_id);
```

### 2.13 wb_reconciliation — 对账校验

```sql
CREATE TABLE workbench.wb_reconciliation (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    check_code          text            NOT NULL,           -- 'row_conservation' / 'metric_reconcile' 等
    check_name          text            NOT NULL,
    source_label        text,                               -- 来源描述
    target_label        text,                               -- 目标描述
    source_value        numeric,
    target_value        numeric,
    diff_value          numeric,
    pass_flag           boolean         NOT NULL,
    remark              text,
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.14 wb_rule_hit — 规则命中记录

```sql
CREATE TABLE workbench.wb_rule_hit (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL REFERENCES workbench.wb_run(run_id),
    step_id             text            NOT NULL REFERENCES workbench.wb_step_registry(step_id),
    rule_code           text            NOT NULL,           -- 规则代码
    rule_name           text            NOT NULL,           -- 规则名称
    rule_purpose        text,                               -- 规则目的
    hit_count           bigint,                             -- 命中行数
    total_count         bigint,                             -- 总行数
    hit_ratio           numeric,                            -- 命中率
    key_params          jsonb,                              -- 关键参数快照
    dimension_key       text            NOT NULL DEFAULT 'ALL',
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_wb_rule_hit_run ON workbench.wb_rule_hit(run_id, step_id);
```

### 2.15 wb_issue_log — 问题日志

```sql
CREATE TABLE workbench.wb_issue_log (
    id                  serial          PRIMARY KEY,
    run_id              integer         REFERENCES workbench.wb_run(run_id),
    severity            text            NOT NULL,           -- critical / high / medium / low
    category            text,                               -- data_quality / logic / performance
    title               text            NOT NULL,
    description         text,
    evidence_sql        text,                               -- 证据查询SQL
    status              text            NOT NULL DEFAULT 'open',  -- open / investigating / resolved / wontfix
    owner               text,
    resolved_at         timestamptz,
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.16 wb_patch_log — 补丁日志

```sql
CREATE TABLE workbench.wb_patch_log (
    id                  serial          PRIMARY KEY,
    issue_id            integer         REFERENCES workbench.wb_issue_log(id),
    patch_name          text            NOT NULL,
    affected_steps      text[],                             -- 影响的步骤ID
    affected_tables     text[],                             -- 影响的表
    description         text,
    merge_status        text            NOT NULL DEFAULT 'pending',  -- pending / merged / rejected
    merged_at           timestamptz,
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 2.17 wb_sample_set — 样本集定义

```sql
CREATE TABLE workbench.wb_sample_set (
    id                  serial          PRIMARY KEY,
    name                text            NOT NULL,
    description         text,
    sample_type         text            NOT NULL,           -- bs / cell / lac / record
    filter_criteria     jsonb           NOT NULL,           -- 筛选条件
    object_ids          jsonb,                              -- 具体对象ID列表
    created_by          text,
    is_active           boolean         NOT NULL DEFAULT true,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

COMMENT ON COLUMN workbench.wb_sample_set.filter_criteria IS '
示例：
{
  "operator_id_raw": "46000",
  "tech_norm": "4G",
  "is_collision_suspect": true,
  "bs_id_range": [100, 500]
}';
```

---

## 3. meta schema DDL

### 3.1 meta_field_registry — 字段注册表

```sql
CREATE TABLE meta.meta_field_registry (
    id                  serial          PRIMARY KEY,
    field_name          text            NOT NULL,           -- 字段英文名
    field_name_cn       text,                               -- 字段中文名
    table_name          text            NOT NULL,           -- 所属表（pipeline.*）
    schema_name         text            NOT NULL DEFAULT 'pipeline',
    data_type           text            NOT NULL,           -- PG数据类型
    is_nullable         boolean         NOT NULL DEFAULT true,
    source_field        text,                               -- 旧表中的原始字段名
    source_table        text,                               -- 旧表名
    lifecycle_status    text            NOT NULL DEFAULT 'active',  -- active / deprecated / drifted / missing
    introduced_version  text,                               -- 引入的契约版本
    description         text,
    created_at          timestamptz     NOT NULL DEFAULT now(),
    updated_at          timestamptz     NOT NULL DEFAULT now(),

    UNIQUE(schema_name, table_name, field_name)
);

CREATE INDEX idx_meta_field_table ON meta.meta_field_registry(table_name);
CREATE INDEX idx_meta_field_status ON meta.meta_field_registry(lifecycle_status);
```

### 3.2 meta_field_health — 字段健康快照

```sql
CREATE TABLE meta.meta_field_health (
    id                  bigserial       PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    run_id              integer         NOT NULL,           -- 关联 wb_run
    batch_label         text,                               -- 批次标签（如日期范围）

    -- 健康指标
    total_rows          bigint,
    null_count          bigint,
    null_rate           numeric,
    distinct_count      bigint,
    zero_count          bigint,                             -- 零值数（数值字段）

    -- 分布指标（数值字段）
    min_value           numeric,
    max_value           numeric,
    avg_value           numeric,
    p50_value           numeric,
    stddev_value        numeric,

    -- 漂移检测
    distribution_drift  numeric,                            -- 与基线的分布偏移度
    is_anomalous        boolean         NOT NULL DEFAULT false,
    anomaly_reason      text,

    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_meta_health_field ON meta.meta_field_health(field_id, run_id);
```

### 3.3 meta_field_mapping_rule — 字段映射规则

```sql
CREATE TABLE meta.meta_field_mapping_rule (
    id                  serial          PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    rule_type           text            NOT NULL,           -- 'rename' / 'type_cast' / 'transform' / 'derive'
    rule_expression     text            NOT NULL,           -- 转换表达式或映射描述
    source_field        text,                               -- 来源字段
    source_table        text,                               -- 来源表
    priority            integer         NOT NULL DEFAULT 0, -- 多规则时的优先级
    is_active           boolean         NOT NULL DEFAULT true,
    version_tag         text,                               -- 适用的契约版本
    created_at          timestamptz     NOT NULL DEFAULT now()
);
```

### 3.4 meta_field_change_log — 字段变更日志

```sql
CREATE TABLE meta.meta_field_change_log (
    id                  bigserial       PRIMARY KEY,
    field_id            integer         NOT NULL REFERENCES meta.meta_field_registry(id),
    change_type         text            NOT NULL,           -- 'added' / 'renamed' / 'type_changed' / 'deprecated' / 'restored'
    old_value           text,                               -- 变更前值
    new_value           text,                               -- 变更后值
    reason              text,
    changed_by          text,                               -- 变更人/系统
    contract_version    text,                               -- 关联契约版本
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_meta_change_field ON meta.meta_field_change_log(field_id);
```

### 3.5 meta_exposure_matrix — 字段曝光矩阵

```sql
CREATE TABLE meta.meta_exposure_matrix (
    id                  bigserial       PRIMARY KEY,
    run_id              integer         NOT NULL,
    object_level        text            NOT NULL,           -- 'BS' / 'CELL' / 'LAC'
    field_name          text            NOT NULL,
    total_objects       bigint          NOT NULL,
    exposed_objects     bigint          NOT NULL,           -- 该字段非NULL的对象数
    exposure_rate       numeric,                            -- 曝光率
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX idx_meta_exposure_run ON meta.meta_exposure_matrix(run_id, object_level);
```

---

## 4. Schema 创建脚本

```sql
-- 创建四个 schema
CREATE SCHEMA IF NOT EXISTS legacy;
CREATE SCHEMA IF NOT EXISTS pipeline;
CREATE SCHEMA IF NOT EXISTS workbench;
CREATE SCHEMA IF NOT EXISTS meta;

-- 设置搜索路径
ALTER DATABASE ip_loc2 SET search_path TO pipeline, workbench, meta, legacy, public;
```

---

## 5. 初始化数据

### 5.1 步骤注册表初始数据

```sql
INSERT INTO workbench.wb_step_registry (step_id, step_order, step_name, step_name_en, layer, is_main_chain, input_tables, output_tables, sql_file) VALUES
('s0',  10, '数据标准化',     'Standardization',          'L2', true,  ARRAY['raw_records'],                     ARRAY['raw_records'],           '00_step0_std_views.sql'),
('s1',  20, '基础统计',       'Base Statistics',           'L2', true,  ARRAY['raw_records'],                     ARRAY['stats_base_raw'],        '01_step1_base_stats.sql'),
('s2',  30, '合规标记',       'Compliance Marking',        'L2', true,  ARRAY['raw_records'],                     ARRAY['fact_filtered'],          '02_step2_compliance_mark.sql'),
('s3',  40, 'LAC统计',        'LAC Statistics',            'L2', true,  ARRAY['fact_filtered'],                    ARRAY['stats_lac'],             '03_step3_lac_stats_db.sql'),
('s4',  50, '可信LAC',        'Trusted LAC Library',       'L2', true,  ARRAY['stats_lac'],                       ARRAY['dim_lac_trusted'],       '04_step4_master_lac_lib.sql'),
('s5',  60, 'Cell统计',       'Cell Statistics',           'L2', true,  ARRAY['fact_filtered','dim_lac_trusted'],  ARRAY['dim_cell_stats'],        '05_step5_cellid_stats_and_anomalies.sql'),
('s6',  70, '合规过滤',       'Compliance Filtering',      'L2', true,  ARRAY['raw_records','dim_cell_stats'],     ARRAY['fact_filtered'],         '06_step6_apply_mapping_and_compare.sql'),
('s30', 80, 'BS主库',         'Master BS Library',         'L3', true,  ARRAY['fact_filtered','dim_lac_trusted','dim_cell_stats'], ARRAY['dim_bs_trusted'], '30_step30_master_bs_library.sql'),
('s31', 90, 'GPS修正',        'GPS Correction',            'L3', true,  ARRAY['fact_filtered','dim_bs_trusted'],   ARRAY['fact_gps_corrected'],    '31_step31_cell_gps_fixed.sql'),
('s32', 100,'GPS对比',        'GPS Comparison',            'L3', true,  ARRAY['fact_gps_corrected','dim_bs_trusted'], ARRAY['compare_gps'],        '32_step32_compare.sql'),
('s33', 110,'信号补齐',       'Signal Fill',               'L3', true,  ARRAY['fact_gps_corrected'],              ARRAY['fact_signal_filled'],    '33_step33_signal_fill_simple.sql'),
('s34', 120,'信号对比',       'Signal Comparison',         'L3', true,  ARRAY['fact_signal_filled'],              ARRAY['compare_signal'],        '34_step34_signal_compare.sql'),
('s35', 130,'动态检测',       'Dynamic Cell Detection',    'L3', false, ARRAY['dim_bs_trusted','fact_gps_corrected'], ARRAY['profile_cell'],        '35_step35_dynamic_cell_bs_detection.sql'),
('s36', 140,'BS异常标记',     'BS ID Anomaly Mark',        'L3', false, ARRAY['dim_bs_trusted'],                  ARRAY['detect_anomaly_bs'],     '36_step36_bs_id_anomaly_mark.sql'),
('s37', 150,'碰撞不足标记',   'Collision Insufficient Mark','L3', false, ARRAY['dim_bs_trusted'],                 ARRAY['detect_collision'],      '37_step37_collision_data_insufficient_mark.sql'),
('s38', 160,'Cell映射交付',   'Cell-BS Map Delivery',      'L3', true,  ARRAY['dim_bs_trusted','fact_gps_corrected'], ARRAY['map_cell_bs'],        '40_layer3_delivery_bs_cell_tables.sql'),
('s40', 170,'完整回归GPS',    'Full Return GPS',           'L4', true,  ARRAY['raw_records','dim_bs_trusted','dim_lac_trusted','dim_cell_stats'], ARRAY['fact_final'], '40_step40_cell_gps_filter_fill.sql'),
('s41', 180,'完整回归信号',   'Full Return Signal',        'L4', true,  ARRAY['fact_final'],                      ARRAY['fact_final'],            '41_step41_cell_signal_fill.sql'),
('s42', 190,'最终对比',       'Final Comparison',          'L4', true,  ARRAY['raw_records','fact_final'],         ARRAY['compare_gps','compare_signal'], '42_step42_compare.sql'),
('s50', 200,'LAC画像',        'LAC Profile',               'L5', true,  ARRAY['fact_final'],                      ARRAY['profile_lac'],           '50_step50_lac_profile.sql'),
('s51', 210,'BS画像',         'BS Profile',                'L5', true,  ARRAY['fact_final'],                      ARRAY['profile_bs'],            '51_step51_bs_profile.sql'),
('s52', 220,'Cell画像',       'Cell Profile',              'L5', true,  ARRAY['fact_final'],                      ARRAY['profile_cell'],          '52_step52_cell_profile.sql');
```

### 5.2 默认参数集

```sql
INSERT INTO workbench.wb_parameter_set (version_tag, description, parameters) VALUES
('P-001', '初始参数集（基于现有SQL硬编码值）', '{
  "global": {
    "operator_whitelist": ["46000","46001","46011","46015","46020"],
    "tech_whitelist": ["4G","5G"],
    "china_bbox": {"lon_min":73,"lon_max":135,"lat_min":3,"lat_max":54},
    "lac_overflow_values": [65534,65535,16777214,16777215,2147483647],
    "rsrp_invalid_values": [-110,-1],
    "rsrp_max_valid": -1
  },
  "step4": {"active_days_threshold":7,"min_device_count":5,"min_device_count_5g":3,"report_count_percentile":80},
  "step30": {"outlier_dist_m":2500,"collision_p90_dist_m":1500,"signal_top_n":50,"center_bin_scale":10000},
  "step31": {"drift_dist_m":1500},
  "step35": {"min_bs_p90_m":5000,"min_half_major_dist_km":10,"min_effective_days":5,"grid_round_decimals":3,"min_day_major_share":0.50,"min_half_major_day_share":0.60},
  "step40": {"gps_dist_threshold_4g":1000,"gps_dist_threshold_5g":500},
  "step50": {"min_rows":5000,"gps_p90_warn_m":100000},
  "step51": {"min_rows":500,"gps_p90_warn_4g_m":1000,"gps_p90_warn_5g_m":500},
  "step52": {"min_rows":200,"gps_p90_warn_4g_m":1000,"gps_p90_warn_5g_m":500}
}'::jsonb);
```

---

## 6. 表关系图

```
wb_run (1)
  ├──< wb_step_execution (N)  ──> wb_step_registry
  ├──< wb_step_metric (N)     ──> wb_step_registry
  ├──< wb_layer_snapshot (N)
  ├──< wb_gate_result (N)
  ├──< wb_anomaly_stats (N)
  ├──< wb_reconciliation (N)
  ├──< wb_rule_hit (N)        ──> wb_step_registry
  ├──> wb_parameter_set
  └──< wb_baseline (N)

wb_issue_log (1)
  └──< wb_patch_log (N)

meta_field_registry (1)
  ├──< meta_field_health (N)
  ├──< meta_field_mapping_rule (N)
  └──< meta_field_change_log (N)

meta_exposure_matrix (独立)
```
