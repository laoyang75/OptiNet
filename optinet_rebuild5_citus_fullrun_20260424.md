# OptiNet rebuild5 Citus Gate 3 Full Run 2026-04-24

## 1. Runtime

7 批 Citus 串行重跑总耗时 145.96 分钟。Round 2 外推为 92 分钟，本轮差值 +53.96 分钟。该耗时按 gate3 正式开始 note 到报告写入时刻的 wall-clock 计算，包含 batch 2 seed 修复重跑时间。

| batch_id | day | raw_rows | duration_seconds | n_cells | dynamic | xlarge |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-12-01 | 3885832 | 774.37 | 87206 | 0 | 74 |
| 2 | 2025-12-02 | 3893994 | 320.87 | 175974 | 0 | 199 |
| 3 | 2025-12-03 | 3645783 | 948.03 | 211209 | 0 | 334 |
| 4 | 2025-12-04 | 3556320 | 626.17 | 262351 | 0 | 419 |
| 5 | 2025-12-05 | 3441403 | 467.53 | 347038 | 0 | 564 |
| 6 | 2025-12-06 | 3394782 | 1050.97 | 347038 | 0 | 692 |
| 7 | 2025-12-07 | 3623955 | 1142.33 | 347038 | 0 | 773 |

Source rows loaded from rb5.raw_gps_full_backup:

| day | source_rows |
| --- | --- |
| 2025-12-01 | 3885832 |
| 2025-12-02 | 3893994 |
| 2025-12-03 | 3645783 |
| 2025-12-04 | 3556320 |
| 2025-12-05 | 3441403 |
| 2025-12-06 | 3394782 |
| 2025-12-07 | 3623955 |

## 2. Batch Cell And Drift Distribution

| batch_id | n_cells | stable | large_coverage | uncertain | dynamic | dual_cluster | xlarge |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 87206 | 85978 | 0 | 0 | 0 | 0 | 74 |
| 2 | 175974 | 171234 | 0 | 0 | 0 | 0 | 199 |
| 3 | 211209 | 204361 | 0 | 0 | 0 | 0 | 334 |
| 4 | 262351 | 250439 | 0 | 0 | 0 | 0 | 419 |
| 5 | 347038 | 320512 | 0 | 0 | 0 | 0 | 564 |
| 6 | 347038 | 320573 | 0 | 0 | 0 | 0 | 692 |
| 7 | 347038 | 320575 | 0 | 0 | 0 | 0 | 773 |

TA verification distribution:

| batch_id | ta_verification | n |
| --- | --- | --- |
| 1 | insufficient | 68929 |
| 1 | large | 114 |
| 1 | not_checked | 7636 |
| 1 | ok | 10453 |
| 1 | xlarge | 74 |
| 2 | insufficient | 131580 |
| 2 | large | 273 |
| 2 | not_checked | 21242 |
| 2 | ok | 22680 |
| 2 | xlarge | 199 |
| 3 | insufficient | 143532 |
| 3 | large | 469 |
| 3 | not_checked | 27822 |
| 3 | ok | 39052 |
| 3 | xlarge | 334 |
| 4 | insufficient | 173317 |
| 4 | large | 557 |
| 4 | not_checked | 38401 |
| 4 | ok | 49657 |
| 4 | xlarge | 419 |
| 5 | insufficient | 222785 |
| 5 | large | 742 |
| 5 | not_checked | 58622 |
| 5 | ok | 64325 |
| 5 | xlarge | 564 |
| 6 | insufficient | 208082 |
| 6 | large | 902 |
| 6 | not_checked | 58621 |
| 6 | ok | 78741 |
| 6 | xlarge | 692 |
| 7 | insufficient | 198389 |
| 7 | large | 992 |
| 7 | not_checked | 58621 |
| 7 | ok | 88263 |
| 7 | xlarge | 773 |

## 3. Dynamic

dynamic 首次出现 batch: none；7 批总量: 0。
这与 Gate 3 health signal 中 batch 3/4 起 dynamic > 0 的预期不一致；本轮未调整 min_total_active_days / min_total_dedup_pts 等业务阈值，已作为 suspect 观察记录。

## 4. Xlarge ODS-023b Check

batch 7 xlarge=773，本地 batch 7 基线=13460，减少 12687，降幅 94.26%。

## 5. Snapshot Diff And pg_stat_statements Top 20

snapshot_diff_cell batch counts:

| batch_id | n |
| --- | --- |
| 1 | 542622 |
| 2 | 542622 |
| 3 | 542622 |
| 4 | 542622 |
| 5 | 542622 |
| 6 | 542622 |
| 7 | 542622 |

pg_stat_statements Top 20:

| rank | calls | total_exec_time_ms | query |
| --- | --- | --- | --- |
| 1 | 1 | 2497256.41 | COPY rb5.raw_gps_full_backup FROM STDIN |
| 2 | 23 | 1615027.79 | WITH grp AS ( SELECT r."记录数唯一标识" AS record_id, t.grp, t.grp_idx, split_part(t.grp, $1, $2) AS sig_block, split_part(t.grp, $3, $4) AS cell_block, CASE WHEN split_part(t.grp, $5, $6) ~ $7 AND length(split_part(t.grp, $8, $9)) <= $10 THEN ... |
| 3 | 14 | 472588.17 | WITH ranked AS ( SELECT batch_id, source_row_uid, operator_code, lac, cell_id, tech_norm, event_time_std, ROW_NUMBER() OVER ( PARTITION BY operator_code, lac, cell_id, tech_norm ORDER BY event_time_std DESC, source_row_uid DESC ) AS obs_... |
| 4 | 1 | 321733.16 | INSERT INTO rb5._label_input_points WITH source_meta AS ( SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.enriched_records UNION ALL SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.snapshot_seed_records ) ... |
| 5 | 1 | 286628.78 | INSERT INTO rb5._label_input_points WITH source_meta AS ( SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.enriched_records UNION ALL SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.snapshot_seed_records ) ... |
| 6 | 56 | 272518.45 | INSERT INTO rb5.cell_sliding_window ( batch_id, source_row_uid, record_id, operator_code, lac, bs_id, cell_id, tech_norm, cell_origin, timing_advance, freq_channel, dev_id, event_time_std, gps_valid, lon_final, lat_final, rsrp_final, rsr... |
| 7 | 23 | 267226.14 | SELECT count(*) AS count FROM (SELECT intermediate_result.record_id, intermediate_result.grp, intermediate_result.grp_idx, intermediate_result.sig_block, intermediate_result.cell_block, intermediate_result.ts_sec, intermediate_result.bat... |
| 8 | 1 | 251358.49 | INSERT INTO rb5._label_input_points WITH source_meta AS ( SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.enriched_records UNION ALL SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.snapshot_seed_records ) ... |
| 9 | 23 | 240732.13 | SELECT count(*) AS count FROM (SELECT intermediate_result.record_id, intermediate_result.grp, intermediate_result.grp_idx, intermediate_result.sig_block, intermediate_result.cell_block, intermediate_result.ts_sec, intermediate_result.bat... |
| 10 | 12 | 224929.09 | INSERT INTO rb5.raw_gps SELECT * FROM rb5.raw_gps_full_backup WHERE ts::date = $1::date |
| 11 | 1544 | 203207.91 | SELECT citus_drop_all_shards(v_obj.objid, v_obj.schema_name, v_obj.object_name, drop_shards_metadata_only := $10) |
| 12 | 1 | 195531.66 | INSERT INTO rb5._label_input_points WITH source_meta AS ( SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.enriched_records UNION ALL SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.snapshot_seed_records ) ... |
| 13 | 19 | 149874.78 | SELECT d.operator_code, d.lac, d.bs_id, d.cell_id, d.tech_norm, d.dedup_dev_id, d.obs_date, d.event_time_std, d.lon_final, d.lat_final FROM ((SELECT intermediate_result.operator_code, intermediate_result.lac, intermediate_result.bs_id, i... |
| 14 | 1105 | 145351.71 | SELECT create_distributed_table($1, $2) |
| 15 | 6 | 132554.49 | SELECT s1.record_id, s1.data_source_detail, s1.ts_raw, s1.gps_ts_raw, s1.gps_info_type, s1.dev_id, s1.ip, s1.plmn_main, s1.brand, s1.model, s1.sdk_ver, s1.oaid, s1.pkg_name, s1.wifi_name, s1.wifi_mac, s1.cpu_info, s1.pressure, s1.grp, s1... |
| 16 | 1 | 116204.98 | INSERT INTO rb5.etl_ci SELECT DISTINCT ON (record_id, cell_id) $1 AS dataset_key, $2 AS source_table, r."记录数唯一标识" AS record_id, $3 AS data_source, r."数据来源dna或daa" AS data_source_detail, $4 AS cell_origin, lower(cell->>$5) AS tech_raw, CA... |
| 17 | 1 | 115680.05 | INSERT INTO rb5._label_input_points WITH source_meta AS ( SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.enriched_records UNION ALL SELECT batch_id, source_row_uid, gps_fill_source_final FROM rb5.snapshot_seed_records ) ... |
| 18 | 1 | 115613.41 | INSERT INTO rb5.etl_ci SELECT DISTINCT ON (record_id, cell_id) $1 AS dataset_key, $2 AS source_table, r."记录数唯一标识" AS record_id, $3 AS data_source, r."数据来源dna或daa" AS data_source_detail, $4 AS cell_origin, lower(cell->>$5) AS tech_raw, CA... |
| 19 | 23 | 114238.44 | SELECT COUNT(*) FILTER (WHERE (e.cell->>$1)::int = $2) AS total_connected, COUNT(*) FILTER ( WHERE (e.cell->>$3)::int = $4 AND e.cell->>$5 ~ $6 AND e.cell->>$7 ~ $8 AND length(e.cell->>$9) <= $10 AND split_part((e.cell->>$11), $12, $13):... |
| 20 | 16 | 113279.0 | INSERT INTO rb5.trusted_bs_library ( batch_id, snapshot_version, snapshot_version_prev, dataset_key, run_id, published_at, operator_code, operator_cn, lac, bs_id, lifecycle_state, anchor_eligible, baseline_eligible, total_cells, qualifie... |

Top SQL 中仍出现 create_distributed_table，说明当前 helper 仍会对不少临时/中间表重复做 Citus layout 初始化；这不是业务 CTAS 回退，但值得收敛表生命周期和 layout 检查。
Step 5 的窗口/半径/label 聚合仍是后半程主要耗时，尤其 _label_input_points 与 collision。

## 6. Next Optimization Points

- 继续观察 raw_gps_full_backup 的 did shard 倾斜；本轮接受，但如果 Step 1 成为主耗时，应优先重评分布键或预分桶。
- Step 5 仍是最可能的主要耗时区，建议按 pg_stat_statements Top SQL 对 cell_sliding_window、cell_metrics_window、label stage 做定向 EXPLAIN。
- 如果 CPU 仍未打满，再评估 pool_size / parallel workers；不要先改业务阈值。
