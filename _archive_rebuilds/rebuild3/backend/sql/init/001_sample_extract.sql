SET statement_timeout = 0;

DROP TABLE IF EXISTS rebuild3_sample_meta.sample_key_scope;
CREATE TABLE rebuild3_sample_meta.sample_key_scope (
  scope_type text NOT NULL,
  scenario text NOT NULL,
  operator_code text,
  tech_norm text,
  lac text,
  bs_id bigint,
  cell_id bigint,
  expected_route text,
  coverage_note text,
  PRIMARY KEY (scope_type, scenario)
);

INSERT INTO rebuild3_sample_meta.sample_key_scope (
  scope_type, scenario, operator_code, tech_norm, lac, bs_id, cell_id, expected_route, coverage_note
)
VALUES
  ('bs', 'healthy_active_5g', '46000', '5G', '2097290', 1425701, NULL, 'fact_governed', '稳定 5G healthy + baseline 主路径'),
  ('bs', 'healthy_active_4g', '46000', '4G', '4335', 494747, NULL, 'fact_governed', '稳定 4G healthy + baseline 主路径'),
  ('bs', 'collision_suspect', '46011', '5G', '405510', 405908, NULL, 'fact_pending_issue', '对象级异常 collision_suspect'),
  ('bs', 'collision_confirmed', '46001', '5G', '98328', 140623, NULL, 'fact_pending_issue', '对象级异常 collision_confirmed'),
  ('bs', 'dynamic', '46001', '4G', '4149', 19469, NULL, 'fact_pending_issue', '对象级异常 dynamic'),
  ('bs', 'single_large', '46011', '5G', '409602', 417849, NULL, 'fact_governed', '记录级异常 single_large 应保留到 governed'),
  ('bs', 'normal_spread', '46001', '5G', '98310', 140755, NULL, 'fact_governed', '记录级异常 normal_spread 应保留到 governed'),
  ('cell', 'waiting_candidate', '46015', '5G', '2097261', 1390319, 5694746825, 'fact_pending_observation', '低证据 waiting 候选 Cell'),
  ('cell', 'observing_candidate', '46001', '5G', '90133', 188722, 773005570, 'fact_pending_observation', '有一定证据但未成熟的 observing 候选 Cell'),
  ('reject', 'reject_invalid_lac_l0_lac', NULL, NULL, NULL, NULL, NULL, 'fact_rejected', 'l0_lac 结构不合规样本'),
  ('reject', 'reject_invalid_lac_l0_gps', NULL, NULL, NULL, NULL, NULL, 'fact_rejected', 'l0_gps 结构不合规样本');

DROP TABLE IF EXISTS rebuild3_sample.source_l0_lac;
CREATE TABLE rebuild3_sample.source_l0_lac AS
WITH bs_rows AS (
  SELECT 'bs'::text AS scope_type, k.scenario, l.*
  FROM rebuild2.l0_lac l
  JOIN rebuild3_sample_meta.sample_key_scope k
    ON k.scope_type = 'bs'
   AND l."运营商编码" = k.operator_code
   AND l."标准制式" = k.tech_norm
   AND l."LAC"::text = k.lac
   AND l."基站ID" = k.bs_id
),
cell_rows AS (
  SELECT 'cell'::text AS scope_type, k.scenario, l.*
  FROM rebuild2.l0_lac l
  JOIN rebuild3_sample_meta.sample_key_scope k
    ON k.scope_type = 'cell'
   AND l."运营商编码" = k.operator_code
   AND l."标准制式" = k.tech_norm
   AND l."LAC"::text = k.lac
   AND l."基站ID" = k.bs_id
   AND l."CellID" = k.cell_id
),
reject_rows AS (
  SELECT 'reject'::text AS scope_type, 'reject_invalid_lac_l0_lac'::text AS scenario, x.*
  FROM (
    SELECT l.*
    FROM rebuild2.l0_lac l
    WHERE l."运营商编码" IS NULL OR l."LAC" IS NULL OR l."CellID" IS NULL
    ORDER BY l."L0行ID"
    LIMIT 200
  ) x
),
all_rows AS (
  SELECT * FROM bs_rows
  UNION ALL
  SELECT * FROM cell_rows
  UNION ALL
  SELECT * FROM reject_rows
)
SELECT DISTINCT ON ("L0行ID") *
FROM all_rows
ORDER BY "L0行ID", scope_type;

DROP TABLE IF EXISTS rebuild3_sample.source_l0_gps;
CREATE TABLE rebuild3_sample.source_l0_gps AS
WITH bs_rows AS (
  SELECT 'bs'::text AS scope_type, k.scenario, g.*
  FROM rebuild2.l0_gps g
  JOIN rebuild3_sample_meta.sample_key_scope k
    ON k.scope_type = 'bs'
   AND g."运营商编码" = k.operator_code
   AND g."标准制式" = k.tech_norm
   AND g."LAC"::text = k.lac
   AND g."基站ID" = k.bs_id
),
cell_rows AS (
  SELECT 'cell'::text AS scope_type, k.scenario, g.*
  FROM rebuild2.l0_gps g
  JOIN rebuild3_sample_meta.sample_key_scope k
    ON k.scope_type = 'cell'
   AND g."运营商编码" = k.operator_code
   AND g."标准制式" = k.tech_norm
   AND g."LAC"::text = k.lac
   AND g."基站ID" = k.bs_id
   AND g."CellID" = k.cell_id
),
reject_rows AS (
  SELECT 'reject'::text AS scope_type, 'reject_invalid_lac_l0_gps'::text AS scenario, x.*
  FROM (
    SELECT g.*
    FROM rebuild2.l0_gps g
    WHERE g."运营商编码" IS NULL OR g."LAC" IS NULL OR g."CellID" IS NULL
    ORDER BY g."L0行ID"
    LIMIT 200
  ) x
),
all_rows AS (
  SELECT * FROM bs_rows
  UNION ALL
  SELECT * FROM cell_rows
  UNION ALL
  SELECT * FROM reject_rows
)
SELECT DISTINCT ON ("L0行ID") *
FROM all_rows
ORDER BY "L0行ID", scope_type;

DROP TABLE IF EXISTS rebuild3_sample_meta.sample_source_summary;
CREATE TABLE rebuild3_sample_meta.sample_source_summary AS
SELECT 'l0_lac'::text AS source_name, scope_type, scenario, count(*) AS row_count
FROM rebuild3_sample.source_l0_lac
GROUP BY 1,2,3
UNION ALL
SELECT 'l0_gps'::text AS source_name, scope_type, scenario, count(*) AS row_count
FROM rebuild3_sample.source_l0_gps
GROUP BY 1,2,3;
