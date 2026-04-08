-- ============================================================
-- Phase 3 字段治理种子数据
-- 依赖: 04_phase3_field_governance.sql
-- ============================================================

-- 1. 注册源字段到 meta_field_registry（field_scope='source'）
INSERT INTO meta.meta_field_registry (
    field_name, field_name_cn, table_name, schema_name, data_type,
    is_nullable, field_scope, logical_domain, unit, description
) VALUES
    ('operator_id_raw', '运营商编码', 'fact_filtered', 'source', 'text', false, 'source', 'network', NULL, '原始运营商编码，如 46000/46001/46011'),
    ('tech',            '原始制式',   'fact_filtered', 'source', 'text', true,  'source', 'network', NULL, '原始上报的网络制式'),
    ('lac_dec',         'LAC',        'fact_filtered', 'source', 'bigint', true, 'source', 'identity', NULL, 'Location Area Code'),
    ('cell_id_dec',     'Cell ID',    'fact_filtered', 'source', 'bigint', true, 'source', 'identity', NULL, 'Cell 标识符'),
    ('lon_raw',         '原始经度',   'fact_filtered', 'source', 'double precision', true, 'source', 'location', '°', '上报的原始经度'),
    ('lat_raw',         '原始纬度',   'fact_filtered', 'source', 'double precision', true, 'source', 'location', '°', '上报的原始纬度'),
    ('sig_rsrp',        'RSRP',       'fact_filtered', 'source', 'double precision', true, 'source', 'signal', 'dBm', '参考信号接收功率'),
    ('sig_rsrq',        'RSRQ',       'fact_filtered', 'source', 'double precision', true, 'source', 'signal', 'dB',  '参考信号接收质量'),
    ('sig_sinr',        'SINR',       'fact_filtered', 'source', 'double precision', true, 'source', 'signal', 'dB',  '信号与干扰噪声比'),
    ('sig_rssi',        'RSSI',       'fact_filtered', 'source', 'double precision', true, 'source', 'signal', 'dBm', '接收信号强度')
ON CONFLICT (schema_name, table_name, field_name) DO UPDATE SET
    field_name_cn = EXCLUDED.field_name_cn,
    field_scope = EXCLUDED.field_scope,
    logical_domain = EXCLUDED.logical_domain,
    unit = EXCLUDED.unit,
    description = EXCLUDED.description,
    updated_at = now();

-- 2. 写入源字段合规规则
-- operator_id_raw: 白名单规则
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='operator_id_raw'),
    'SRC-C-001',
    '运营商编码必须属于已知白名单',
    'network',
    'whitelist',
    '{"values_from_param": true}'::jsonb,
    '["global.operator_whitelist"]'::jsonb,
    'high'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- tech: 白名单规则
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='tech'),
    'SRC-C-001',
    '制式必须属于已知白名单（2G/3G/4G/5G/NR等）',
    'network',
    'whitelist',
    '{"values_from_param": true}'::jsonb,
    '["global.tech_whitelist"]'::jsonb,
    'high'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- lac_dec: 按制式的范围规则
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='lac_dec'),
    'SRC-C-001',
    'LAC 必须在有效范围内且不属于溢出值',
    'identity',
    'range_by_tech',
    '{"min": 1, "max_4g": 65535, "max_5g": 16777215, "overflow_from_param": true}'::jsonb,
    '["global.lac_overflow_values"]'::jsonb,
    'high'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- cell_id_dec: 范围规则
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='cell_id_dec'),
    'SRC-C-001',
    'Cell ID 必须在合同约定的有效范围内',
    'identity',
    'range_by_tech',
    '{"min": 1, "max_4g": 268435455, "max_5g": 1099511627775}'::jsonb,
    '[]'::jsonb,
    'high'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- lon_raw + lat_raw: 经纬度联合边界框
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='lon_raw'),
    'SRC-C-001',
    '经度须在中国边界框范围内',
    'location',
    'bbox_pair',
    '{"pair_field": "lat_raw", "bbox_from_param": true}'::jsonb,
    '["global.china_bbox"]'::jsonb,
    'medium'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='lat_raw'),
    'SRC-C-001',
    '纬度须在中国边界框范围内',
    'location',
    'bbox_pair',
    '{"pair_field": "lon_raw", "bbox_from_param": true}'::jsonb,
    '["global.china_bbox"]'::jsonb,
    'medium'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- sig_rsrp: 数值范围
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category, unit,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='sig_rsrp'),
    'SRC-C-001',
    'RSRP 须在物理合理范围内且不属于无效标记值',
    'signal', 'dBm',
    'numeric_range',
    '{"min": -156, "max": -30, "invalid_from_param": true}'::jsonb,
    '["global.rsrp_invalid_values"]'::jsonb,
    'medium'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- sig_rsrq: 数值范围
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category, unit,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='sig_rsrq'),
    'SRC-C-001',
    'RSRQ 须在物理合理范围内',
    'signal', 'dB',
    'numeric_range',
    '{"min": -34, "max": 3.5}'::jsonb,
    '[]'::jsonb,
    'medium'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- sig_sinr: 数值范围
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category, unit,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='sig_sinr'),
    'SRC-C-001',
    'SINR 须在物理合理范围内',
    'signal', 'dB',
    'numeric_range',
    '{"min": -23, "max": 40}'::jsonb,
    '[]'::jsonb,
    'medium'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- sig_rssi: 数值范围
INSERT INTO meta.meta_source_field_compliance (
    field_id, version_tag, business_definition, field_category, unit,
    rule_type, rule_config, parameter_refs, severity
) VALUES (
    (SELECT id FROM meta.meta_field_registry WHERE schema_name='source' AND table_name='fact_filtered' AND field_name='sig_rssi'),
    'SRC-C-001',
    'RSSI 须在物理合理范围内',
    'signal', 'dBm',
    'numeric_range',
    '{"min": -120, "max": -20}'::jsonb,
    '[]'::jsonb,
    'medium'
) ON CONFLICT (field_id, version_tag) DO NOTHING;

-- 3. 补充源字段到过程字段的映射说明
INSERT INTO meta.meta_field_mapping_rule (
    field_id, rule_type, rule_expression, source_field, source_table, priority, is_active, version_tag
)
SELECT r.id, 'rename', 'sig_rsrq -> sig_rsrq_final', 'sig_rsrq', 'fact_filtered', 1, true, 'M-001'
FROM meta.meta_field_registry r
WHERE r.schema_name = 'source' AND r.table_name = 'fact_filtered' AND r.field_name = 'sig_rsrq'
ON CONFLICT DO NOTHING;

INSERT INTO meta.meta_field_mapping_rule (
    field_id, rule_type, rule_expression, source_field, source_table, priority, is_active, version_tag
)
SELECT r.id, 'transform', 'lon_raw/lat_raw -> lon_final/lat_final (经 GPS 修正)', 'lon_raw', 'fact_filtered', 1, true, 'M-001'
FROM meta.meta_field_registry r
WHERE r.schema_name = 'source' AND r.table_name = 'fact_filtered' AND r.field_name = 'lon_raw'
ON CONFLICT DO NOTHING;
