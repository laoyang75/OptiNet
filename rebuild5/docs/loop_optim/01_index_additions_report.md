# loop_optim / 01 索引补全报告

## 0. TL;DR

- 18 张 rb5.* 大表现有索引矩阵已盘点；当前未创建的生成表按 "not created" 标记。
- 新增 live 索引: 25 条(P0=8, P1=13, P2=4)，全部已通过 Citus `pg_indexes` 复核可见。
- 数据库实际建索引耗时: 总约 26 秒，最长一条 5 秒(`idx_csw_source_uid`)；无单条超 10 分钟。
- schema/pipeline 文件改动: 34 处 `CREATE INDEX IF NOT EXISTS` 模板/持久化索引 DDL，其中 25 条已在当前库实际建立，9 条作用于下次重建生成表或 Step2 fallback 表。
- 对 fix6_optim 02A/02B 修订: 无。02A helper 矩阵只作为 distributed/reference 背景；未改 `citus_compat` / 02C 守护 / runner。
- commit SHA: 待 commit；push 状态: 待 push。

## 1. 现有索引矩阵

### 1.1 18 张大表的 pg_indexes 输出

| schema.table | indexname | indexdef | 推测用途 |
| --- | --- | --- | --- |
| `rb5.raw_gps` | `idx_rb5_raw_gps_work_ts` | `CREATE INDEX idx_rb5_raw_gps_work_ts ON rb5.raw_gps USING btree (ts)` | Step1/source refill 时间过滤 |
| `rb5.raw_gps` | `idx_rb5_raw_gps_work_uid` | `CREATE INDEX idx_rb5_raw_gps_work_uid ON rb5.raw_gps USING btree ("记录数唯一标识")` | 去重/record uid |
| `rb5.etl_parsed` | `idx_etl_parsed_cell_lookup` | `CREATE INDEX idx_etl_parsed_cell_lookup ON rb5.etl_parsed USING btree (operator_code, lac, cell_id, tech_norm)` | 新增；clean 前维度过滤 |
| `rb5.etl_parsed` | `idx_etl_parsed_record` | `CREATE INDEX idx_etl_parsed_record ON rb5.etl_parsed USING btree (record_id)` | 新增；record 级访问 |
| `rb5.etl_cleaned` | `idx_etl_cleaned_dim_time` | `CREATE INDEX idx_etl_cleaned_dim_time ON rb5.etl_cleaned USING btree (operator_filled, lac_filled, cell_id, tech_norm, event_time_std)` | 新增；Step2 维度+时间 |
| `rb5.etl_cleaned` | `idx_etl_cleaned_event_time_std` | `CREATE INDEX idx_etl_cleaned_event_time_std ON rb5.etl_cleaned USING btree (event_time_std)` | daily scope 时间过滤 |
| `rb5.etl_cleaned` | `idx_etl_cleaned_path_lookup` | `CREATE INDEX idx_etl_cleaned_path_lookup ON rb5.etl_cleaned USING btree (operator_filled, lac_filled, bs_id, cell_id, tech_norm)` | Step2 path lookup |
| `rb5.etl_cleaned` | `idx_etl_cleaned_record` | `CREATE INDEX idx_etl_cleaned_record ON rb5.etl_cleaned USING btree (record_id)` | record 级查找 |
| `rb5.etl_cleaned` | `idx_etl_cleaned_source_uid` | `CREATE INDEX idx_etl_cleaned_source_uid ON rb5.etl_cleaned USING btree (source_row_uid)` | 新增；Path-A source uid join |
| `rb5.etl_filled` | not indexed | `etl_filled` 当前是 `etl_cleaned` 兼容 view，不能建普通表索引 | 走 base table 索引 |
| `rb5.step2_batch_input` | `idx_step2_batch_input_cell` | `CREATE INDEX idx_step2_batch_input_cell ON rb5.step2_batch_input USING btree (cell_id)` | Step2 cell filter |
| `rb5.step2_batch_input` | `idx_step2_batch_input_dim_time` | `CREATE INDEX idx_step2_batch_input_dim_time ON rb5.step2_batch_input USING btree (operator_filled, lac_filled, cell_id, tech_norm, event_time_std)` | 新增；Step2 维度+时间 |
| `rb5.step2_batch_input` | `idx_step2_batch_input_event_time` | `CREATE INDEX idx_step2_batch_input_event_time ON rb5.step2_batch_input USING btree (event_time_std)` | 新增；daily scope 时间 |
| `rb5.step2_batch_input` | `idx_step2_batch_input_lookup` | `CREATE INDEX idx_step2_batch_input_lookup ON rb5.step2_batch_input USING btree (operator_filled, lac_filled, bs_id, cell_id, tech_norm)` | 新增；Path-B lookup |
| `rb5.step2_batch_input` | `idx_step2_batch_input_op_lac_cell` | `CREATE INDEX idx_step2_batch_input_op_lac_cell ON rb5.step2_batch_input USING btree (operator_filled, lac_filled, cell_id)` | existing Step2 lookup |
| `rb5.step2_batch_input` | `idx_step2_batch_input_record` | `CREATE INDEX idx_step2_batch_input_record ON rb5.step2_batch_input USING btree (record_id)` | existing record lookup |
| `rb5.step2_batch_input` | `idx_step2_batch_input_source_uid` | `CREATE INDEX idx_step2_batch_input_source_uid ON rb5.step2_batch_input USING btree (source_row_uid)` | 新增；Path-A source uid |
| `rb5.cell_sliding_window` | `cell_sliding_window_pkey` | `CREATE UNIQUE INDEX cell_sliding_window_pkey ON rb5.cell_sliding_window USING btree (batch_id, source_row_uid, cell_id)` | primary key / batch delete |
| `rb5.cell_sliding_window` | `idx_csw_cell` | `CREATE INDEX idx_csw_cell ON rb5.cell_sliding_window USING btree (batch_id, operator_code, lac, bs_id, cell_id)` | Step5 cell lookup |
| `rb5.cell_sliding_window` | `idx_csw_dim_time` | `CREATE INDEX idx_csw_dim_time ON rb5.cell_sliding_window USING btree (operator_code, lac, cell_id, tech_norm, event_time_std)` | 新增；window trim / group/order |
| `rb5.cell_sliding_window` | `idx_csw_event_time` | `CREATE INDEX idx_csw_event_time ON rb5.cell_sliding_window USING btree (event_time_std)` | 新增；max/range scan |
| `rb5.cell_sliding_window` | `idx_csw_lookup` | `CREATE INDEX idx_csw_lookup ON rb5.cell_sliding_window USING btree (batch_id, operator_code, lac, bs_id, cell_id, tech_norm, event_time_std)` | Step5 batch lookup |
| `rb5.cell_sliding_window` | `idx_csw_source_uid` | `CREATE INDEX idx_csw_source_uid ON rb5.cell_sliding_window USING btree (source_row_uid)` | 新增；anomaly uid join |
| `rb5.trusted_cell_library` | `idx_tcl_abs_collision` | `CREATE INDEX idx_tcl_abs_collision ON rb5.trusted_cell_library USING btree (batch_id, operator_code, tech_norm, lac, cell_id, bs_id)` | collision/path lookup |
| `rb5.trusted_cell_library` | `idx_tcl_batch_cell_id` | `CREATE INDEX idx_tcl_batch_cell_id ON rb5.trusted_cell_library USING btree (batch_id, cell_id)` | cell search |
| `rb5.trusted_cell_library` | `idx_tcl_bs` | `CREATE INDEX idx_tcl_bs ON rb5.trusted_cell_library USING btree (batch_id, operator_code, lac, bs_id)` | BS aggregation |
| `rb5.trusted_cell_library` | `idx_tcl_collision` | `CREATE INDEX idx_tcl_collision ON rb5.trusted_cell_library USING btree (batch_id, operator_code, lac, cell_id)` | collision lookup |
| `rb5.trusted_cell_library` | `idx_tcl_service_bs_cells` | `CREATE INDEX idx_tcl_service_bs_cells ON rb5.trusted_cell_library USING btree (batch_id, operator_code, lac, bs_id, p90_radius_m, cell_id)` | 新增；service BS detail |
| `rb5.trusted_cell_library` | `idx_tcl_service_cell` | `CREATE INDEX idx_tcl_service_cell ON rb5.trusted_cell_library USING btree (batch_id, cell_id, operator_code, lac, tech_norm)` | 新增；service cell detail |
| `rb5.trusted_cell_library` | `idx_trusted_cell_library_lookup` | `CREATE INDEX idx_trusted_cell_library_lookup ON rb5.trusted_cell_library USING btree (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)` | donor lookup |
| `rb5.trusted_cell_library` | `trusted_cell_library_pkey` | `CREATE UNIQUE INDEX trusted_cell_library_pkey ON rb5.trusted_cell_library USING btree (batch_id, operator_code, lac, cell_id, tech_norm)` | primary key |
| `rb5.snapshot_seed_records` | `idx_snapshot_seed_batch` | `CREATE INDEX idx_snapshot_seed_batch ON rb5.snapshot_seed_records USING btree (batch_id)` | batch delete/read |
| `rb5.snapshot_seed_records` | `idx_snapshot_seed_batch_cell` | `CREATE INDEX idx_snapshot_seed_batch_cell ON rb5.snapshot_seed_records USING btree (batch_id, operator_code, lac, bs_id, cell_id, tech_norm)` | Step5 insert/read |
| `rb5.snapshot_seed_records` | `idx_snapshot_seed_batch_time` | `CREATE INDEX idx_snapshot_seed_batch_time ON rb5.snapshot_seed_records USING btree (batch_id, event_time_std)` | 新增；time stats |
| `rb5.snapshot_seed_records` | `idx_snapshot_seed_record_cell` | `CREATE INDEX idx_snapshot_seed_record_cell ON rb5.snapshot_seed_records USING btree (batch_id, record_id, cell_id)` | 新增；record anti-join |
| `rb5.snapshot_seed_records` | `snapshot_seed_records_pkey` | `CREATE UNIQUE INDEX snapshot_seed_records_pkey ON rb5.snapshot_seed_records USING btree (batch_id, source_row_uid, cell_id)` | primary key |
| `rb5.candidate_seed_history` | `candidate_seed_history_pkey` | `CREATE UNIQUE INDEX candidate_seed_history_pkey ON rb5.candidate_seed_history USING btree (batch_id, source_row_uid, cell_id)` | primary key |
| `rb5.candidate_seed_history` | `idx_candidate_seed_history_batch_record` | `CREATE INDEX idx_candidate_seed_history_batch_record ON rb5.candidate_seed_history USING btree (batch_id, record_id, cell_id, lac, tech_norm)` | 新增；snapshot anti-join |
| `rb5.candidate_seed_history` | `idx_candidate_seed_history_cell` | `CREATE INDEX idx_candidate_seed_history_cell ON rb5.candidate_seed_history USING btree (operator_code, lac, bs_id, cell_id, tech_norm, batch_id)` | existing candidate lookup |
| `rb5.candidate_seed_history` | `idx_candidate_seed_history_dim_time` | `CREATE INDEX idx_candidate_seed_history_dim_time ON rb5.candidate_seed_history USING btree (operator_code, lac, cell_id, tech_norm, batch_id, event_time_std)` | 新增；candidate newest seed |
| `rb5.candidate_seed_history` | `idx_candidate_seed_history_event_time` | `CREATE INDEX idx_candidate_seed_history_event_time ON rb5.candidate_seed_history USING btree (batch_id, event_time_std)` | batch time |
| `rb5.candidate_seed_history` | `idx_csh_join_batch` | `CREATE INDEX idx_csh_join_batch ON rb5.candidate_seed_history USING btree (operator_code, lac, cell_id, tech_norm, batch_id)` | Step4 join |
| `rb5.enriched_records` | `enriched_records_pkey` | `CREATE UNIQUE INDEX enriched_records_pkey ON rb5.enriched_records USING btree (batch_id, source_row_uid, cell_id)` | primary key |
| `rb5.enriched_records` | `idx_enriched_batch` | `CREATE INDEX idx_enriched_batch ON rb5.enriched_records USING btree (batch_id)` | batch delete/read |
| `rb5.enriched_records` | `idx_enriched_batch_cell` | `CREATE INDEX idx_enriched_batch_cell ON rb5.enriched_records USING btree (batch_id, operator_code, lac, bs_id, cell_id)` | Step5 merge |
| `rb5.enriched_records` | `idx_enriched_batch_record_cell` | `CREATE INDEX idx_enriched_batch_record_cell ON rb5.enriched_records USING btree (batch_id, record_id, cell_id, lac, tech_norm)` | snapshot anti-join |
| `rb5.enriched_records` | `idx_enriched_batch_time` | `CREATE INDEX idx_enriched_batch_time ON rb5.enriched_records USING btree (batch_id, event_time_std)` | 新增；time scan |
| `rb5.enriched_records` | `idx_enriched_source_uid` | `CREATE INDEX idx_enriched_source_uid ON rb5.enriched_records USING btree (source_row_uid)` | 新增；uid lookup |
| `rb5.cell_metrics_base` | not created | no pg_indexes rows | generated table; new `idx_cell_metrics_base_dim` template added in `maintenance/window.py` |
| `rb5.cell_radius_stats` | not created | no pg_indexes rows | generated table; new `idx_cell_radius_stats_cell` template added in `maintenance/window.py` |
| `rb5.cell_drift_stats` | not created | no pg_indexes rows | generated table; new `idx_cell_drift_stats_key` template added in `maintenance/cell_maintain.py` |
| `rb5.cell_daily_centroid` | not created | no pg_indexes rows | generated table; indexes created when `build_daily_centroids()` rebuilds it |
| `rb5.gps_anomaly_log` | `gps_anomaly_log_pkey` | `CREATE UNIQUE INDEX gps_anomaly_log_pkey ON rb5.gps_anomaly_log USING btree (batch_id, source_row_uid, cell_id)` | primary key |
| `rb5.gps_anomaly_log` | `idx_gps_anomaly_batch_cell` | `CREATE INDEX idx_gps_anomaly_batch_cell ON rb5.gps_anomaly_log USING btree (batch_id, operator_code, lac, cell_id)` | anomaly summary |
| `rb5.gps_anomaly_log` | `idx_gps_anomaly_batch_time` | `CREATE INDEX idx_gps_anomaly_batch_time ON rb5.gps_anomaly_log USING btree (batch_id, event_time_std)` | 新增；time summary |
| `rb5.gps_anomaly_log` | `idx_gps_anomaly_source_uid` | `CREATE INDEX idx_gps_anomaly_source_uid ON rb5.gps_anomaly_log USING btree (source_row_uid)` | 新增；Step5 anomaly uid join |
| `rb5.cell_core_gps_day_dedup` | `idx_cell_core_gps_day_dedup_key` | `CREATE INDEX idx_cell_core_gps_day_dedup_key ON rb5.cell_core_gps_day_dedup USING btree (operator_code, lac, bs_id, cell_id, tech_norm)` | core GPS key |
| `rb5.cell_core_gps_day_dedup` | `idx_cell_core_gps_day_dedup_time` | `CREATE INDEX idx_cell_core_gps_day_dedup_time ON rb5.cell_core_gps_day_dedup USING btree (event_time_std)` | 新增；time/order scan |
| `rb5.trusted_bs_library` | `idx_tbl_service_bs` | `CREATE INDEX idx_tbl_service_bs ON rb5.trusted_bs_library USING btree (batch_id, bs_id, operator_code, lac)` | 新增；service BS detail |
| `rb5.trusted_bs_library` | `idx_tbl_service_lac` | `CREATE INDEX idx_tbl_service_lac ON rb5.trusted_bs_library USING btree (batch_id, operator_code, lac, anomaly_cell_ratio, total_cells)` | 新增；service LAC detail |
| `rb5.trusted_bs_library` | `trusted_bs_library_pkey` | `CREATE UNIQUE INDEX trusted_bs_library_pkey ON rb5.trusted_bs_library USING btree (batch_id, operator_code, lac, bs_id)` | primary key |
| `rb5.trusted_lac_library` | `idx_tll_service_lac` | `CREATE INDEX idx_tll_service_lac ON rb5.trusted_lac_library USING btree (batch_id, lac, operator_code)` | 新增；service LAC detail |
| `rb5.trusted_lac_library` | `trusted_lac_library_pkey` | `CREATE UNIQUE INDEX trusted_lac_library_pkey ON rb5.trusted_lac_library USING btree (batch_id, operator_code, lac)` | primary key |

### 1.2 SQL access pattern x 列

| 表 | 文件:行号 | SQL access(WHERE/JOIN/GROUP BY/ORDER BY) | 列 |
| --- | --- | --- | --- |
| `raw_gps` | `etl/parse.py:68,125,162` | parse source scan + JSON expansion | `ts`, `"记录数唯一标识"` |
| `etl_parsed` | `etl/clean.py:69,73` | `COUNT(*)`, CTAS to clean stage; clean rules filter dimensions before derived time exists | `record_id`, `operator_code`, `lac`, `cell_id`, `tech_norm` |
| `etl_cleaned` | `profile/pipeline.py:555,777,816,1023,1072` | Step2 fallback/source; joins on path candidates and source uid | `event_time_std`, `source_row_uid`, `operator_filled`, `lac_filled`, `bs_id`, `cell_id`, `tech_norm`, `record_id` |
| `etl_filled` | `etl/fill.py:10`, `scripts/reset_step1_to_step5_for_full_rerun_v3.sql:9` | compatibility view over `etl_cleaned` | base table columns from `etl_cleaned` |
| `step2_batch_input` | `scripts/run_daily_increment_batch_loop.py:148-174`, `profile/pipeline.py:get_step2_input_relation` | daily scoped Step2 input, same Step2 lookup pattern as `etl_cleaned` | `event_time_std`, `source_row_uid`, `operator_filled`, `lac_filled`, `bs_id`, `cell_id`, `tech_norm`, `record_id` |
| `cell_sliding_window` | `maintenance/window.py:68,146,191,215,243,327,765,816,825,926` | batch delete, retention ranking, max time, per-cell GROUP BY, anomaly source uid join | `batch_id`, `source_row_uid`, `event_time_std`, `operator_code`, `lac`, `bs_id`, `cell_id`, `tech_norm` |
| `trusted_cell_library` | `profile/pipeline.py:580,598,674,699`, `enrichment/pipeline.py:381`, `maintenance/publish_bs_lac.py:956`, `service_query/queries.py:129,145,198` | donor lookup, publish aggregation, service latest batch search/order | `batch_id`, `operator_code`, `lac`, `bs_id`, `cell_id`, `tech_norm`, `p90_radius_m` |
| `snapshot_seed_records` | `maintenance/window.py:61,99,116`, `enrichment/pipeline.py:416` | batch delete/insert into sliding window; record anti-join | `batch_id`, `source_row_uid`, `record_id`, `operator_code`, `lac`, `bs_id`, `cell_id`, `tech_norm`, `event_time_std` |
| `candidate_seed_history` | `profile/pipeline.py:1546`, `enrichment/pipeline.py:459` | batch delete, join new snapshot seeds, newest candidate ordering | `batch_id`, `record_id`, `operator_code`, `lac`, `cell_id`, `tech_norm`, `event_time_std` |
| `enriched_records` | `enrichment/pipeline.py:78,322,347,468`, `maintenance/window.py:72,89` | batch delete/read, anomaly insert, snapshot anti-join, sliding window merge | `batch_id`, `source_row_uid`, `record_id`, `operator_code`, `lac`, `bs_id`, `cell_id`, `tech_norm`, `event_time_std` |
| `cell_metrics_base` | `maintenance/window.py:877` | join into final metrics window | `batch_id`, `operator_code`, `lac`, `bs_id`, `cell_id`, `tech_norm` |
| `cell_radius_stats` | `maintenance/window.py:878` | join into final metrics window | `operator_code`, `lac`, `bs_id`, `cell_id`, `tech_norm` |
| `cell_drift_stats` | `maintenance/window.py:847`, `cell_maintain.py:24-98` | drift table build and metrics join | `batch_id`, `operator_code`, `lac`, `cell_id`, `tech_norm` |
| `cell_daily_centroid` | `maintenance/cell_maintain.py:32,56` | self-join and endpoint aggregation | `batch_id`, `operator_code`, `lac`, `cell_id`, `tech_norm`, `obs_date` |
| `gps_anomaly_log` | `maintenance/window.py:290`, `cell_maintain.py:142`, `enrichment/pipeline.py:532` | anomaly uid dedup, cell-level summary, batch count | `source_row_uid`, `batch_id`, `operator_code`, `lac`, `cell_id`, `tech_norm`, `event_time_std` |
| `cell_core_gps_day_dedup` | `maintenance/window.py:396,426` | core GPS center/distance GROUP BY and joins | `operator_code`, `lac`, `bs_id`, `cell_id`, `tech_norm`, `event_time_std` |
| `trusted_bs_library` | `maintenance/publish_bs_lac.py:1090,1178,1247`, `service_query/queries.py:165,178,241` | BS publish/LAC aggregation and service lookup | `batch_id`, `operator_code`, `lac`, `bs_id`, `anomaly_cell_ratio`, `total_cells` |
| `trusted_lac_library` | `maintenance/publish_bs_lac.py:1218,1279`, `service_query/queries.py:211,221,286` | LAC publish replace and service lookup | `batch_id`, `operator_code`, `lac` |

## 2. 新增索引清单

| 表 | 列(组合) | 索引名 | 优先级 | 加在哪个文件 | 数据库实际建立耗时 |
| --- | --- | --- | --- | --- | ---: |
| `etl_parsed` | `(record_id)` | `idx_etl_parsed_record` | P2 | `backend/app/etl/parse.py` | 3s |
| `etl_parsed` | `(operator_code, lac, cell_id, tech_norm)` | `idx_etl_parsed_cell_lookup` | P2 | `backend/app/etl/parse.py` | 1s |
| `etl_cleaned` | `(source_row_uid)` | `idx_etl_cleaned_source_uid` | P0 | `backend/app/etl/pipeline.py`, `profile/pipeline.py` | 2s |
| `etl_cleaned` | `(operator_filled, lac_filled, cell_id, tech_norm, event_time_std)` | `idx_etl_cleaned_dim_time` | P0 | `backend/app/etl/pipeline.py`, `profile/pipeline.py` | 1s |
| `step2_batch_input` | `(operator_filled, lac_filled, bs_id, cell_id, tech_norm)` | `idx_step2_batch_input_lookup` | P0 | `scripts/run_daily_increment_batch_loop.py` | 0s |
| `step2_batch_input` | `(operator_filled, lac_filled, cell_id, tech_norm, event_time_std)` | `idx_step2_batch_input_dim_time` | P0 | `scripts/run_daily_increment_batch_loop.py` | 1s |
| `step2_batch_input` | `(source_row_uid)` | `idx_step2_batch_input_source_uid` | P1 | `scripts/run_daily_increment_batch_loop.py` | 1s |
| `step2_batch_input` | `(event_time_std)` | `idx_step2_batch_input_event_time` | P1 | `scripts/run_daily_increment_batch_loop.py` | 1s |
| `candidate_seed_history` | `(batch_id, record_id, cell_id, lac, tech_norm)` | `idx_candidate_seed_history_batch_record` | P1 | `backend/app/profile/pipeline.py` | 1s |
| `candidate_seed_history` | `(operator_code, lac, cell_id, tech_norm, batch_id, event_time_std)` | `idx_candidate_seed_history_dim_time` | P1 | `backend/app/profile/pipeline.py` | 1s |
| `cell_sliding_window` | `(operator_code, lac, cell_id, tech_norm, event_time_std)` | `idx_csw_dim_time` | P0 | `backend/app/maintenance/schema.py` | 3s |
| `cell_sliding_window` | `(source_row_uid)` | `idx_csw_source_uid` | P0 | `backend/app/maintenance/schema.py` | 5s |
| `cell_sliding_window` | `(event_time_std)` | `idx_csw_event_time` | P0 | `backend/app/maintenance/schema.py` | 2s |
| `cell_core_gps_day_dedup` | `(event_time_std)` | `idx_cell_core_gps_day_dedup_time` | P2 | `backend/app/maintenance/window.py` | 0s |
| `enriched_records` | `(batch_id, event_time_std)` | `idx_enriched_batch_time` | P1 | `backend/app/enrichment/schema.py`, `enrichment/pipeline.py` | 1s |
| `enriched_records` | `(source_row_uid)` | `idx_enriched_source_uid` | P1 | `backend/app/enrichment/schema.py`, `enrichment/pipeline.py` | 2s |
| `gps_anomaly_log` | `(source_row_uid)` | `idx_gps_anomaly_source_uid` | P1 | `backend/app/enrichment/schema.py`, `enrichment/pipeline.py` | 0s |
| `gps_anomaly_log` | `(batch_id, event_time_std)` | `idx_gps_anomaly_batch_time` | P1 | `backend/app/enrichment/schema.py`, `enrichment/pipeline.py` | 0s |
| `snapshot_seed_records` | `(batch_id, event_time_std)` | `idx_snapshot_seed_batch_time` | P1 | `backend/app/enrichment/schema.py`, `enrichment/pipeline.py` | 1s |
| `snapshot_seed_records` | `(batch_id, record_id, cell_id)` | `idx_snapshot_seed_record_cell` | P1 | `backend/app/enrichment/schema.py`, `enrichment/pipeline.py` | 1s |
| `trusted_cell_library` | `(batch_id, cell_id, operator_code, lac, tech_norm)` | `idx_tcl_service_cell` | P1 | `backend/app/maintenance/schema.py` | 1s |
| `trusted_cell_library` | `(batch_id, operator_code, lac, bs_id, p90_radius_m, cell_id)` | `idx_tcl_service_bs_cells` | P1 | `backend/app/maintenance/schema.py` | 1s |
| `trusted_bs_library` | `(batch_id, bs_id, operator_code, lac)` | `idx_tbl_service_bs` | P2 | `backend/app/maintenance/schema.py` | 0s |
| `trusted_bs_library` | `(batch_id, operator_code, lac, anomaly_cell_ratio, total_cells)` | `idx_tbl_service_lac` | P1 | `backend/app/maintenance/schema.py` | 0s |
| `trusted_lac_library` | `(batch_id, lac, operator_code)` | `idx_tll_service_lac` | P2 | `backend/app/maintenance/schema.py` | 1s |

Deferred templates added for generated/fallback tables and therefore not counted in the 25 live-created indexes: `idx_step2_cell_input_dim_time`, `idx_step2_cell_input_event_time`, `idx_cell_metrics_base_dim`, `idx_cell_radius_stats_cell`, `idx_cell_drift_stats_key`. `cell_daily_centroid` index creation was moved into its builder as well, matching its drop/recreate lifecycle.

## 3. 已知限制 / 未做

- `etl_filled` is a compatibility view over `etl_cleaned`; no direct btree index can be created on the view.
- `cell_metrics_base`, `cell_radius_stats`, `cell_drift_stats`, and `cell_daily_centroid` were not present in the current Citus catalog at survey time, because they are rebuilt/drop-created by Step5. Their index templates are now in the builders and will materialize on the next run.
- No existing indexes were deleted or audited for usage, by user decision.
- No partial/covering indexes were introduced.
- `pg_stat_user_indexes` was not used for decision-making; this phase is positive completion only.

## 4. 给 02 artifact pipelined 的输入

- For immutable `rb5_stage.step2_input_b<N>_<YYYYMMDD>` artifacts, copy the Step2 scope index set from this phase:
  - `(cell_id)`
  - `(operator_filled, lac_filled, cell_id)`
  - `(operator_filled, lac_filled, bs_id, cell_id, tech_norm)`
  - `(operator_filled, lac_filled, cell_id, tech_norm, event_time_std)`
  - `(record_id)`
  - `(source_row_uid)`
  - `(event_time_std)`
- Keep `ANALYZE <artifact_table>` immediately after index creation.

## 5. 验证

- Citus live CREATE INDEX: 25/25 ok, all visible in `pg_indexes`.
- `ANALYZE`: run for all current live target tables.
- `python3 -m py_compile rebuild5/backend/app/etl/*.py rebuild5/backend/app/maintenance/*.py rebuild5/backend/app/enrichment/*.py rebuild5/backend/app/profile/pipeline.py rebuild5/scripts/run_daily_increment_batch_loop.py`: pass.
- `git rev-parse HEAD == git rev-parse origin/main`: pending until commit/push.
- `rb5_bench.notes topic='loop_optim_01_done'`: pending until commit SHA is known.
