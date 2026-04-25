# OptiNet rebuild5 Citus Benchmark Report

生成时间: 2026-04-23T13:54:44  
数据库: `optinet_rebuild5_sandbox`  
入口: `192.168.200.217:5488`  
样本来源: 旧库 `192.168.200.217:5433/ip_loc2.rebuild5.raw_gps_full_backup` 只读抽样。

## 1. 集群摘要

扩展版本:

| extname | extversion |
| --- | --- |
| citus | 14.0-1 |

Citus 节点:

| nodeid | nodename | nodeport | noderole | isactive | shouldhaveshards |
| --- | --- | --- | --- | --- | --- |
| 1 | 192.168.200.217 | 5488 | primary | True | False |
| 3 | 192.168.200.216 | 5488 | primary | True | True |
| 4 | 192.168.200.219 | 5488 | primary | True | True |
| 5 | 192.168.200.220 | 5488 | primary | True | True |
| 6 | 192.168.200.221 | 5488 | primary | True | True |

Sandbox 数据库大小:

| sandbox_db_size |
| --- |
| 11 MB |

样本与 shard 分布:

| sample_rows | shard_distribution |
| --- | --- |
| 1527715 | `[{"mb": 460.4, "node": "192.168.200.216", "n_shards": 8}, {"mb": 459.4, "node": "192.168.200.219", "n_shards": 8}, {"mb": 458.8, "node": "192.168.200.220", "n_shards": 8}, {"mb": 466.0, "node": "192.168.200.221", "n_shards": 8}]` |

## 2. 机器规格汇总

以下来自 `SELECT * FROM bench.machine_spec` 的结构化结果摘要:

| node_role | node_name | cpu_model | cpu_physical | cpu_logical | numa_nodes | mem_gb | disk_model | fs_type | kernel_ver | thp_state | extra_jsonb |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| coordinator | 192.168.200.217 | Intel(R) Xeon(R) CPU E5-2660 v2 @ 2.20GHz | 20 | 40 | 2 | 251 | WDC WDS200T2B0A RAID5 | xfs | 3.10.0-1160.119.1.el7.x86_64 | always madvise [never] | `{"fio_note": "fio present on coordinator; full fio benchmark skipped to avoid destructive/long disk test in shared environment", "data_size": "6.7T", "data_mount": "/data", "ping_ms_avg": 5.486}` |
| worker | 192.168.200.216 | Intel(R) Xeon(R) CPU E5-2660 v2 @ 2.20GHz | 20 | 40 | 2 | 251 | WDC WDS200T2B0A RAID5 | xfs | 3.10.0-1160.71.1.el7.x86_64 | always madvise [never] | `{"fio_note": "fio not installed", "data_size": "8.7T", "data_mount": "/", "docker_bip": "172.31.0.1/16", "ping_ms_avg": 4.363}` |
| worker | 192.168.200.219 | Intel(R) Xeon(R) CPU E5-2660 v2 @ 2.20GHz | 20 | 40 | 2 | 251 | Samsung SSD 860 RAID5 | xfs | 3.10.0-1160.119.1.el7.x86_64 | always madvise [never] | `{"fio_note": "fio not installed", "data_size": "7.9T", "data_mount": "/data", "ping_ms_avg": 4.59}` |
| worker | 192.168.200.220 | Intel(R) Xeon(R) CPU E5-2660 v2 @ 2.20GHz | 20 | 40 | 2 | 251 | Samsung SSD 860 RAID5 | xfs | 3.10.0-1160.119.1.el7.x86_64 | always madvise [never] | `{"fio_note": "fio not installed", "data_size": "7.9T", "data_mount": "/data", "ping_ms_avg": 4.963}` |
| worker | 192.168.200.221 | Intel(R) Xeon(R) CPU E5-2660 v2 @ 2.20GHz | 20 | 40 | 2 | 251 | Samsung SSD 860 RAID5 | xfs | 3.10.0-1160.119.1.el7.x86_64 | always madvise [never] | `{"fio_note": "fio not installed", "data_size": "7.9T", "data_mount": "/data", "docker_bip": "172.31.0.1/16", "other_load": "python/freqtrade observed historically", "ping_ms_avg": 4.799}` |

## 3. 参数推荐 vs 当前应用

说明: `bench.pg_conf_recommended` 已给出推荐值；当前没有重启容器应用需要 restart 的 PostgreSQL 参数，因为 prompt §4.4 写明需用户审核后再 apply。`bench.pg_conf_applied` 记录的是当前实际值。

| node_name | param | recommended | applied | rationale |
| --- | --- | --- | --- | --- |
| 192.168.200.216 | log_min_duration_statement | 5000 | -1 | 记录慢 SQL |
| 192.168.200.216 | maintenance_work_mem | 2GB | 4GB | 公共推荐起点 |
| 192.168.200.216 | max_connections | 200 | 100 | coordinator/worker 分工 |
| 192.168.200.216 | max_parallel_workers | 15 | 20 | floor(N*0.75), N=20 |
| 192.168.200.216 | max_parallel_workers_per_gather | 5 | 16 | max(2,floor(N/4)), N=20 |
| 192.168.200.216 | max_worker_processes | 20 | 40 | 按物理核 N=20 |
| 192.168.200.216 | shared_buffers | 16GB | 64GB | coordinator 偏协调, worker 偏计算 |
| 192.168.200.216 | shared_preload_libraries | citus,pg_stat_statements,auto_explain | citus | 可观测性: Citus + pg_stat_statements + auto_explain; 需要重启 |
| 192.168.200.216 | wal_compression | on | off | 降低 WAL 写入 |
| 192.168.200.216 | work_mem | 128MB | 512MB | 避免当前 512MB 在并发下放大内存 |
| 192.168.200.217 | log_min_duration_statement | 5000 | -1 | 记录慢 SQL |
| 192.168.200.217 | maintenance_work_mem | 2GB | 4GB | 公共推荐起点 |
| 192.168.200.217 | max_connections | 400 | 100 | coordinator/worker 分工 |
| 192.168.200.217 | max_parallel_workers | 15 | 20 | floor(N*0.75), N=20 |
| 192.168.200.217 | max_parallel_workers_per_gather | 5 | 16 | max(2,floor(N/4)), N=20 |
| 192.168.200.217 | max_worker_processes | 20 | 40 | 按物理核 N=20 |
| 192.168.200.217 | shared_buffers | 8GB | 64GB | coordinator 偏协调, worker 偏计算 |
| 192.168.200.217 | shared_preload_libraries | citus,pg_stat_statements,auto_explain | citus | 可观测性: Citus + pg_stat_statements + auto_explain; 需要重启 |
| 192.168.200.217 | wal_compression | on | off | 降低 WAL 写入 |
| 192.168.200.217 | work_mem | 32MB | 512MB | 避免当前 512MB 在并发下放大内存 |
| 192.168.200.219 | log_min_duration_statement | 5000 | -1 | 记录慢 SQL |
| 192.168.200.219 | maintenance_work_mem | 2GB | 4GB | 公共推荐起点 |
| 192.168.200.219 | max_connections | 200 | 100 | coordinator/worker 分工 |
| 192.168.200.219 | max_parallel_workers | 15 | 20 | floor(N*0.75), N=20 |
| 192.168.200.219 | max_parallel_workers_per_gather | 5 | 16 | max(2,floor(N/4)), N=20 |
| 192.168.200.219 | max_worker_processes | 20 | 40 | 按物理核 N=20 |
| 192.168.200.219 | shared_buffers | 16GB | 64GB | coordinator 偏协调, worker 偏计算 |
| 192.168.200.219 | shared_preload_libraries | citus,pg_stat_statements,auto_explain | citus | 可观测性: Citus + pg_stat_statements + auto_explain; 需要重启 |
| 192.168.200.219 | wal_compression | on | off | 降低 WAL 写入 |
| 192.168.200.219 | work_mem | 128MB | 512MB | 避免当前 512MB 在并发下放大内存 |
| 192.168.200.220 | log_min_duration_statement | 5000 | -1 | 记录慢 SQL |
| 192.168.200.220 | maintenance_work_mem | 2GB | 4GB | 公共推荐起点 |
| 192.168.200.220 | max_connections | 200 | 100 | coordinator/worker 分工 |
| 192.168.200.220 | max_parallel_workers | 15 | 20 | floor(N*0.75), N=20 |
| 192.168.200.220 | max_parallel_workers_per_gather | 5 | 16 | max(2,floor(N/4)), N=20 |
| 192.168.200.220 | max_worker_processes | 20 | 40 | 按物理核 N=20 |
| 192.168.200.220 | shared_buffers | 16GB | 64GB | coordinator 偏协调, worker 偏计算 |
| 192.168.200.220 | shared_preload_libraries | citus,pg_stat_statements,auto_explain | citus | 可观测性: Citus + pg_stat_statements + auto_explain; 需要重启 |
| 192.168.200.220 | wal_compression | on | off | 降低 WAL 写入 |
| 192.168.200.220 | work_mem | 128MB | 512MB | 避免当前 512MB 在并发下放大内存 |
| 192.168.200.221 | log_min_duration_statement | 5000 | -1 | 记录慢 SQL |
| 192.168.200.221 | maintenance_work_mem | 2GB | 4GB | 公共推荐起点 |
| 192.168.200.221 | max_connections | 200 | 100 | coordinator/worker 分工 |
| 192.168.200.221 | max_parallel_workers | 15 | 20 | floor(N*0.75), N=20 |
| 192.168.200.221 | max_parallel_workers_per_gather | 5 | 16 | max(2,floor(N/4)), N=20 |
| 192.168.200.221 | max_worker_processes | 20 | 40 | 按物理核 N=20 |
| 192.168.200.221 | shared_buffers | 16GB | 64GB | coordinator 偏协调, worker 偏计算 |
| 192.168.200.221 | shared_preload_libraries | citus,pg_stat_statements,auto_explain | citus | 可观测性: Citus + pg_stat_statements + auto_explain; 需要重启 |
| 192.168.200.221 | wal_compression | on | off | 降低 WAL 写入 |
| 192.168.200.221 | work_mem | 128MB | 512MB | 避免当前 512MB 在并发下放大内存 |

关键差异:

- 当前 `shared_preload_libraries = citus`，推荐为 `citus,pg_stat_statements,auto_explain`，因此本轮无法提供 pg_stat_statements Top20。
- 当前 `shared_buffers=64GB`、`work_mem=512MB` 偏激进；推荐 coordinator `8GB/32MB`，worker `16GB/128MB`。
- 当前 `synchronous_commit=off` 是历史容器参数；prompt 要求不主动改 fsync/synchronous_commit，本轮未改。

## 4. Benchmark 结果对照

以下来自 `bench.run_results`:

| run_id | query_name | variant | stage | duration_ms | rows_in | rows_out | task_count | repartition_hit | work_mem_peak_mb | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| r01_default | B1 | main | parse | 11835 | 1527715 | 9010060 | 32 | False | 512 | JSONB expand + DISTINCT-like cell extraction; output distributed by did colocated with raw sample |
| r02_recommended | B1 | main | parse | 12876 | 1527715 | 9010060 | 32 | False | 128 | JSONB expand + DISTINCT-like cell extraction; output distributed by did colocated with raw sample |
| r01_default | B2 | main | clean | 4819 | 9010060 | 2938775 | 32 | False | 512 | Distributed UPDATE on did-colocated parsed table |
| r02_recommended | B2 | main | clean | 5598 | 9010060 | 2938775 | 32 | False | 128 | Distributed UPDATE on did-colocated parsed table |
| r01_default | B3 | main | profile | 52264 | 9010060 | 474736 | 32 | False | 512 | Cell profile with percentile_cont; output distributed by cell_id |
| r02_recommended | B3 | main | profile | 52608 | 9010060 | 474736 | 32 | False | 128 | Cell profile with percentile_cont; output distributed by cell_id |
| r01_default | B4 | by_cellid | spatial | 65988 | 6362574 | 233985 | 32 | False | 512 | Self-join from cell_id-distributed input; expected colocated |
| r02_recommended | B4 | by_cellid | spatial | 64851 | 6362574 | 233985 | 32 | False | 128 | Self-join from cell_id-distributed input; expected colocated |
| r01_default | B4 | by_devid | spatial | 81084 | 9010060 | 233985 | 32 | False | 512 | Self-join from did-distributed input; expected repartition risk |
| r02_recommended | B4 | by_devid | spatial | 86250 | 9010060 | 233985 | 32 | False | 128 | Self-join from did-distributed input; expected repartition risk |
| r01_default | B5 | main | join | 471 | 474736 | 478042 | 32 | False | 512 | Multi-table colocated left join by cell_id |
| r02_recommended | B5 | main | join | 420 | 474736 | 478042 | 32 | False | 128 | Multi-table colocated left join by cell_id |
| r01_default | B6 | main | index | 1827 | 9010060 | 3 | 32 | False | 512 | Distributed CREATE INDEX on b2_clean; resumed after multi-command prepared failure |
| r02_recommended | B6 | main | index | 1803 | 9010060 | 3 | 32 | False | 128 | Distributed CREATE INDEX on b2_clean |
| r01_default | B7 | main | merge | 106 | 474736 | 50 | 32 | False | 512 | ORDER BY LIMIT across shards |
| r02_recommended | B7 | main | merge | 118 | 474736 | 50 | 32 | False | 128 | ORDER BY LIMIT across shards |
| r01_default | B8 | main | bulk | 93 | 478042 | 478042 | 32 | False | 512 | Bulk INSERT SELECT from label output |
| r02_recommended | B8 | main | bulk | 96 | 478042 | 478042 | 32 | False | 128 | Bulk INSERT SELECT from label output |

观察:

- B1 JSON 展开 1,527,715 行样本生成约 9,010,060 行解析结果，32 个 task，无 repartition。
- B3 percentile profile 是明显重负载，约 52 秒，产出 474,736 个 cell profile。
- B4 self-join 是最慢场景；按 cell_id 物化后快于 did 分布输入。r01: 65.988s vs 81.084s；r02: 64.851s vs 86.250s。
- B5/B7/B8 都较快，B7 ORDER BY LIMIT 约 0.1s，满足 <500ms 目标。
- r02 session-level 参数未比 r01 当前容器参数明显更快，因此未追加 r03_tuned。

## 5. pg_stat_statements Top 20

本轮无法提供。原因: 当前容器 `shared_preload_libraries` 只有 `citus`，没有 `pg_stat_statements`。该事实已写入 `bench.notes(topic='pg_stat_statements_unavailable')`，推荐配置已写入 `bench.pg_conf_recommended`，需要用户审核后重启容器才能启用。

## 6. 未决问题 / 建议清单

以下来自 `bench.notes` 中 severity 为 warn/suspect/blocker 的条目:

| severity | topic | body |
| --- | --- | --- |
| suspect | pg_conf_apply_scope | prompt §4.4 要求参数推荐先写 bench.pg_conf_recommended, 用户审核后再 apply + restart。当前仅记录推荐值和现状值到 bench.pg_conf_applied；未重启容器、未应用 shared_preload_libraries/连接数/shared_buffers 等需要重启的参数。基准 r01/r02 将使用 session-level SET 模拟可变参数, 并在报告中标注。 |
| warn | fio_iperf_scope | prompt 要求 fio/iperf3；当前仅 coordinator 有 fio，worker 未安装 fio/iperf3。为避免安装额外工具和长时间/破坏性磁盘压测，machine_spec 中 fio_* 留 NULL，并以 ping 延迟 + 已知 SSD RAID5 记录。 |
| warn | benchmark_retry | 首次 benchmark runner 在 B1 create_distributed_table 前失败: did text 与 src.raw_gps_sample.did varchar(200) 类型不匹配, 无数据写入。已将空表重命名为 etl.b1_parsed_r01_default_failed_colocation_type 并修正脚本 did 类型后重跑。 |
| warn | pg_stat_statements_unavailable | 当前 shared_preload_libraries 仅 citus, 未包含 pg_stat_statements/auto_explain；未重启容器前无法提供 pg_stat_statements Top20。已在 pg_conf_recommended 中列出需要重启启用的可观测参数。 |

## 7. 给迁移阶段的建议

1. 原始层 `src.raw_gps_sample` 用 `did` 分布是合理起点，B1/B2 shard-local，结果稳定。
2. pipe/profile 层建议按 `cell_id` 重新物化并 colocate。B4 by_cellid 比 by_devid 稳定快，说明 self-join/空间类逻辑更受益于 cell_id colocate。
3. B3 percentile 聚合是主要计算成本之一，迁移时要重点观察 coordinator merge 和 work_mem/temp spill。
4. 启用 `pg_stat_statements` 和 `auto_explain` 后应重跑一轮，补齐 Top SQL 与 temp spill 证据。
5. 生产参数不要直接沿用当前容器的 `work_mem=512MB`；在并发场景下内存放大风险很高。

## 8. MCP 快速校验 SQL

```sql
-- 1. 两档配置下每个 benchmark 耗时对照
SELECT run_id, query_name, variant, duration_ms, task_count, repartition_hit
FROM bench.run_results
ORDER BY query_name, variant, run_id;

-- 2. shard 分布均匀度
SELECT nodename, COUNT(*) AS n_shards, SUM(shard_size)/1024/1024 AS mb
FROM citus_shards WHERE table_name = 'src.raw_gps_sample'::regclass
GROUP BY nodename;

-- 3. 所有 warn/blocker/suspect 备注
SELECT severity, topic, body FROM bench.notes
WHERE severity IN ('warn','blocker','suspect')
ORDER BY severity DESC, id;

-- 4. 参数应用核对
SELECT node_name, param, value FROM bench.pg_conf_applied ORDER BY node_name, param;

-- 5. 取完整报告
SELECT report_name, created_at, length(body) AS md_chars
FROM bench.report ORDER BY created_at DESC LIMIT 1;

-- 6. 确认完工信号
SELECT * FROM bench.notes
WHERE topic = 'DELIVERY_COMPLETE'
ORDER BY id DESC LIMIT 1;
```
