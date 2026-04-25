# OptiNet rebuild5 Citus Round 2 Report

生成时间: 2026-04-23T15:26:43  
数据库: `yangca`  
入口: `192.168.200.217:5488`  
Round 1 历史库: `optinet_rebuild5_sandbox` 未改动。

## 1. 集群与观测配置

扩展:

| extname | extversion |
| --- | --- |
| citus | 14.0-1 |
| pg_stat_statements | 1.11 |

Citus 节点:

| nodeid | nodename | nodeport | noderole | isactive | shouldhaveshards |
| --- | --- | --- | --- | --- | --- |
| 1 | 192.168.200.217 | 5488 | primary | True | False |
| 2 | 192.168.200.216 | 5488 | primary | True | True |
| 3 | 192.168.200.219 | 5488 | primary | True | True |
| 4 | 192.168.200.220 | 5488 | primary | True | True |
| 5 | 192.168.200.221 | 5488 | primary | True | True |

已应用关键参数:

| node_name | param | value |
| --- | --- | --- |
| 192.168.200.216 | max_connections | 200 |
| 192.168.200.216 | shared_buffers | 16GB |
| 192.168.200.216 | shared_preload_libraries | citus,pg_stat_statements,auto_explain |
| 192.168.200.216 | work_mem | 128MB |
| 192.168.200.217 | citus.max_adaptive_executor_pool_size | 32 |
| 192.168.200.217 | citus.shard_count | 64 |
| 192.168.200.217 | max_connections | 400 |
| 192.168.200.217 | shared_buffers | 8GB |
| 192.168.200.217 | shared_preload_libraries | citus,pg_stat_statements,auto_explain |
| 192.168.200.217 | work_mem | 64MB |
| 192.168.200.219 | max_connections | 200 |
| 192.168.200.219 | shared_buffers | 16GB |
| 192.168.200.219 | shared_preload_libraries | citus,pg_stat_statements,auto_explain |
| 192.168.200.219 | work_mem | 128MB |
| 192.168.200.220 | max_connections | 200 |
| 192.168.200.220 | shared_buffers | 16GB |
| 192.168.200.220 | shared_preload_libraries | citus,pg_stat_statements,auto_explain |
| 192.168.200.220 | work_mem | 128MB |
| 192.168.200.221 | max_connections | 200 |
| 192.168.200.221 | shared_buffers | 16GB |
| 192.168.200.221 | shared_preload_libraries | citus,pg_stat_statements,auto_explain |
| 192.168.200.221 | work_mem | 128MB |

样本与 shard 分布:

| sample_rows | shard_dist |
| --- | --- |
| 3556320 | `[{"mb": 1045.4, "node": "192.168.200.216", "shards": 16}, {"mb": 1043.3, "node": "192.168.200.219", "shards": 16}, {"mb": 1064.0, "node": "192.168.200.220", "shards": 16}, {"mb": 1042.1, "node": "192.168.200.221", "shards": 16}]` |

## 2. 五个验收问题回答

### Q1. 350 万行完整 pipeline 总耗时? 全量外推多少?

- 本轮实际跑完整 B1→B8, 并额外同时跑了 B4 `by_devid` 与 `by_cellid` 两个 variant, 实际墙钟约 **20分44秒**。
- `rb5_bench.run_results` 各阶段 duration 相加为 **973.9 秒**。这包含两个 B4 variant。
- 生产推荐路径只保留 B4 `by_cellid`, 扣除 `by_devid` 后约 **770.8 秒 / 12.85 分钟**。
- 线性外推因子 `25,442,069 / 3,556,320 = 7.15`。
- 生产推荐路径外推全量约 **91.9 分钟 / 1.53 小时**。

### Q2. 决定性瓶颈是什么? 优化前后多少秒?

- 决定性瓶颈是 **B4 spatial self-join** 与大表 B1/B2 写入。
- B4 `by_devid` = **203.1 秒**。
- B4 `by_cellid` = **163.1 秒**。
- cell_id 物化/colocation 后自连接主体快约 **40.0 秒 / 19.7%**。
- B3 percentile = **113.1 秒**, 低于 5 分钟目标。

### Q3. 能不能承接全量 2500 万行重跑?

**结论: GO, 可以承接全量重跑, 但应按推荐分布策略执行。**

理由:

- 1 天 355.6 万真实样本完整试水在 30 分钟内完成。
- B3 percentile 113 秒, 显著低于 5 分钟阈值。
- 生产路径全量线性外推约 2.1 小时, 对离线全链路重跑可接受。
- 当前无 temp spill (`temp_bytes=0`), 说明 work_mem/查询形态没有明显磁盘溢出问题。
- 主要风险不是 Citus 不可用, 而是不要在生产里使用 CTAS 后再 create_distributed_table 的搬运模式, 以及 B4 必须走 cell_id colocate。

### Q4. 迁移阶段推荐分布键策略?

| 表/层 | 推荐分布键 | 理由 |
|---|---|---|
| raw_gps_full_backup / rb5_src.raw_gps_day | `did` | B1/B2 原始解析和清洗以设备维度天然 shard-local, 导入分布均匀 |
| B1/B2 ETL 产物 | `did`, colocate with raw | 解析/清洗链路避免 shuffle |
| B3 及后续 pipe profile | `cell_id` | profile、空间、自连接、label join 都围绕 cell_id |
| B4/B5/B8 pipe 产物 | `cell_id`, colocate with B3 | B4 by_cellid 明显快于 by_devid |
| trusted_cell_library | `cell_id` | UI 查询、发布、cell 可信库都以 cell 粒度消费 |

### Q5. pg_stat_statements Top20 意外慢 SQL?

最意外慢项是 `create_distributed_table`, 总计约 204 秒。原因是本轮为了用 `EXPLAIN ANALYZE CTAS` 保留完整执行计划, 先生成本地表再分布, 导致 Citus 需要搬运 shard。生产迁移应预建 distributed table, 然后 `INSERT ... SELECT` 或 COPY 直接写 distributed table。

Top20 详表见第 5 节。

## 3. run_results

| run_id | query_name | variant | stage | duration_ms | seconds | rows_in | rows_out | task_count | repartition_hit | worker_cpu_peak_pct | coord_cpu_peak_pct | temp_bytes | wal_bytes | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r1_day_v1 | B1 | main | parse | 157040 | 157.04 | 3556320 | 20824565 | 64 | False | 1057 | 111 | 0 | 4807492624 | CTAS JSON expand, then distribute by did |
| r1_day_v1 | B2 | main | clean | 168583 | 168.58 | 20824565 | 6792535 | 64 | False | 110 | 112 | 0 | 4842397696 | Clean rules simulated as CTAS flag; avoids destructive UPDATE yet measures full scan |
| r1_day_v1 | B3 | main | profile | 113146 | 113.15 | 20824565 | 623308 | 64 | False | 99 | 120 | 0 | 112173056 | Cell profile percentile; distributed after CTAS by cell_id |
| r1_day_v1 | B4 | by_cellid | spatial | 163072 | 163.07 | 14706752 | 305237 | 64 | False | 174 | 119 | 0 | 22202616 | Self join from cell_id-distributed input |
| r1_day_v1 | B4 | by_devid | spatial | 203085 | 203.09 | 20824565 | 305237 | 64 | False | 95 | 119 | 0 | 46045248 | Self join from did-distributed input |
| r1_day_v1 | B4 | materialize_cellid | spatial | 114733 | 114.73 | 20824565 | 14706752 | 64 | False | 73 | 111 | 0 | 3432757096 | Materialize cell_id-distributed input for spatial self-join |
| r1_day_v1 | B5 | main | join | 1696 | 1.70 | 623308 | 628360 | 64 | False | 0 | 97 | 0 | 60925656 | Colocated style label join; helper CTEs |
| r1_day_v1 | B6 | main | index | 50448 | 50.45 | 20824565 | 3 | 64 | False | 1654 | 899 | 0 | 316541584 | CREATE INDEX timed directly; explain_json is EXPLAIN ANALYZE of representative indexed SELECT because EXPLAIN ANALYZE CREATE INDEX is unsupported |
| r1_day_v1 | B7 | main | merge | 115 | 0.12 | 623308 | 50 | 64 | False | 0 | 11 | 0 | 4016 | Coordinator top-N merge |
| r1_day_v1 | B8 | main | bulk | 1973 | 1.97 | 628360 | 628360 | 64 | False | 0 | 99 | 0 | 65845448 | Bulk publish CTAS |

## 4. Warn/Suspect/Blocker Notes

| severity | topic | body |
| --- | --- | --- |
| warn | top_sql_findings | pg_stat_statements Top1 是 create_distributed_table 总计约204秒, 说明 CTAS 后再分布有明显搬运成本。生产迁移应优先预建 distributed table 后 INSERT/COPY, 避免 coordinator 本地表再搬 shard。 |

## 5. pg_stat_statements Top20

| rank_no | calls | total_ms | mean_ms | rows | query |
| --- | --- | --- | --- | --- | --- |
| 1 | 6 | 204406.5 | 34067.8 | 6 | select create_distributed_table($1,$2,colocate_with=>$3) |
| 2 | 1 | 203071.9 | 203071.9 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_pipe.b4_spread_by_devid AS WITH limited AS (SELECT cell_id,did,lon,lat,row_number() over(partition by cell_id or |
| 3 | 1 | 168572.3 | 168572.3 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_etl.b2_clean AS SELECT *, CASE WHEN lon NOT BETWEEN $1 AND $2 OR lat NOT BETWEEN $3 AND $4 OR cell_id IS NULL OR |
| 4 | 1 | 163022.4 | 163022.4 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_pipe.b4_spread_by_cellid AS WITH limited AS (SELECT cell_id,did,lon,lat,row_number() over(partition by cell_id o |
| 5 | 1 | 156973.8 | 156973.8 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_etl.b1_parsed AS <br>        SELECT r.did::varchar(200) did, r."记录数唯一标识"::text record_id, NULLIF(r.ts,$1)::timestam |
| 6 | 2 | 124303.8 | 62151.9 | 610474 | SELECT * FROM worker_save_query_explain_analyze($1, $2) AS (field_0 pg_catalog.text, field_1 integer) |
| 7 | 2 | 122983.2 | 61491.6 | 610474 | SELECT a.cell_id, max((((($1 OPERATOR(pg_catalog.*) $2))::double precision OPERATOR(pg_catalog.*) asin(sqrt((power(sin((radians((b.lat OPERATOR(pg_catalog.-) a.lat)) OPERATOR(pg_ca |
| 8 | 1 | 114724.7 | 114724.7 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_etl.b2_clean_cell AS SELECT * FROM rb5_etl.b2_clean WHERE cell_id IS NOT NULL AND cell_id<>$1 |
| 9 | 1 | 113130.0 | 113130.0 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_pipe.b3_cell_stats AS SELECT cell_id, tech_norm, count(*)::bigint n_points, count(distinct did)::bigint n_device |
| 10 | 1 | 26050.4 | 26050.4 | 0 | CREATE INDEX IF NOT EXISTS idx_rb5_b2_clean_did_cell ON rb5_etl.b2_clean(did,cell_id) |
| 11 | 1 | 15529.0 | 15529.0 | 0 | CREATE INDEX IF NOT EXISTS idx_rb5_b2_clean_cell ON rb5_etl.b2_clean(cell_id) |
| 12 | 1 | 8246.8 | 8246.8 | 0 | CREATE INDEX IF NOT EXISTS idx_rb5_b2_clean_ts ON rb5_etl.b2_clean(ts_std) |
| 13 | 2 | 2451.8 | 1225.9 | 2 | select count(*) from rb5_etl.b2_clean_cell |
| 14 | 2 | 2182.1 | 1091.0 | 2 | select create_distributed_table($1,$2) |
| 15 | 1 | 2031.2 | 2031.2 | 0 | analyze rb5_etl.b2_clean_cell |
| 16 | 1 | 1966.5 | 1966.5 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_pipe.b8_published AS SELECT cell_id,tech_norm,label,score,spread_m,now() published_at FROM rb5_pipe.b5_label WHE |
| 17 | 1 | 1893.6 | 1893.6 | 0 | analyze rb5_etl.b1_parsed |
| 18 | 1 | 1888.8 | 1888.8 | 0 | analyze rb5_etl.b2_clean |
| 19 | 1 | 1681.3 | 1681.3 | 0 | EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, COSTS OFF) CREATE TABLE rb5_pipe.b5_label AS WITH f AS (SELECT cell_id, coalesce(n_points,$1)::double precision/greatest(n_devices,$2) score |
| 20 | 21 | 1367.7 | 65.1 | 84 | select * from run_command_on_workers($1) |

## 6. MCP 快速校验 SQL

```sql
SELECT run_id, query_name, variant, duration_ms, task_count, repartition_hit
FROM rb5_bench.run_results
ORDER BY query_name, variant, run_id;

SELECT rank_no, calls, total_exec_time, mean_exec_time, rows, left(query, 120)
FROM rb5_bench.pg_stat_top20
ORDER BY rank_no;

SELECT severity, topic, body
FROM rb5_bench.notes
WHERE severity IN ('warn','blocker','suspect')
ORDER BY severity DESC, id;

SELECT report_name, created_at, length(body) AS md_chars
FROM rb5_bench.report
ORDER BY created_at DESC LIMIT 1;

SELECT * FROM rb5_bench.notes
WHERE topic = 'ROUND2_COMPLETE'
ORDER BY id DESC LIMIT 1;
```
