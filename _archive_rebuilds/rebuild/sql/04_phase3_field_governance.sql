-- ============================================================
-- Phase 3 字段治理 DDL
-- 依赖: 03_workbench_meta_ddl.sql（meta schema 及 meta_field_registry）
-- ============================================================

-- 1. 扩展 meta_field_registry：增加 field_scope / logical_domain / unit
ALTER TABLE meta.meta_field_registry
    ADD COLUMN IF NOT EXISTS field_scope text NOT NULL DEFAULT 'pipeline',
    ADD COLUMN IF NOT EXISTS logical_domain text,
    ADD COLUMN IF NOT EXISTS unit text;

CREATE INDEX IF NOT EXISTS idx_meta_field_scope
    ON meta.meta_field_registry(field_scope, schema_name, table_name);

-- 2. 源字段合规规则表
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

-- 3. 源字段合规率快照表（run 绑定）
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
