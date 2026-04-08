SET statement_timeout = 0;
SET work_mem = '512MB';
\timing on

-- STEP 9：清理临时表
DROP TABLE IF EXISTS rebuild2._tmp_bs_gps;
DROP TABLE IF EXISTS rebuild2._tmp_bs_cnt;
DROP TABLE IF EXISTS rebuild2._tmp_bs_seeds;
DROP TABLE IF EXISTS rebuild2._tmp_bs_c1;
DROP TABLE IF EXISTS rebuild2._tmp_bs_c2;
DROP TABLE IF EXISTS rebuild2._tmp_bs_dist;

-- STEP 10：记录元数据
CREATE TABLE IF NOT EXISTS rebuild2_meta.enrich_result (
    id         SERIAL PRIMARY KEY,
    step_code  TEXT NOT NULL,
    run_label  TEXT DEFAULT 'default',
    stat_key   TEXT NOT NULL,
    stat_value JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO rebuild2_meta.enrich_result (step_code, stat_key, stat_value)
SELECT 'step1_bs_refined', 'summary',
    jsonb_build_object(
        'total_bs',  count(*),
        'usable',    count(*) FILTER (WHERE gps_quality = 'Usable'),
        'risk',      count(*) FILTER (WHERE gps_quality = 'Risk'),
        'unusable',  count(*) FILTER (WHERE gps_quality = 'Unusable'),
        'has_center', count(*) FILTER (WHERE gps_center_lon IS NOT NULL),
        'outlier_removed', count(*) FILTER (WHERE had_outlier_removal)
    )
FROM rebuild2.dim_bs_refined;
