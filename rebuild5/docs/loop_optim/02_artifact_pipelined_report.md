# loop_optim / 02 artifact pipelined + Step1 40 核报告

## 0. TL;DR + 对上游修订

- `rb5_stage` schema + `rb5_meta.pipeline_artifacts` 已在 Citus 建立；`pipeline_artifacts` 为 reference table。
- `freeze_step2_input_artifact` 已实施，smoke on batch 7 成功：`rows=4,428,601`，耗时 `14.02s`，验证后已清理 batch 99 artifact/state。
- `run_profile_pipeline` 新增显式 `input_relation` 参数，旧 caller 不传参时保留原 fallback 链。
- Step1 的 CTAS populate `INSERT ... SELECT` 通过 `PARALLEL_40_SETUP` 注入 40 核 session SET；覆盖 Step1 11 处 CTAS 物化路径。
- 新 runner `run_citus_artifact_pipelined.py` 已实施：producer freeze artifact，consumer 从 `pipeline_artifacts` ready state 取 artifact 并传给 Step2。
- 02C 守护扩展 1 个 test，通过手工 invoke；py_compile 全过。
- 对 fix6_optim 02A/02B/02C 修订：无。对 loop_optim 02 prompt 修订：`ON CONFLICT DO UPDATE ... NOW()` 在 Citus reference/distributed table 上触发 IMMUTABLE 限制，改为 `DELETE + INSERT` 写 running state。
- commit SHA：见完工 note/话术；push 状态：见完工话术。

## 1. 设计实施细节

### 1.1 etl_cleaned 实际分布键

查询：

```sql
SELECT p.logicalrelid::regclass::text, p.partmethod, a.attname AS dist_col
FROM pg_dist_partition p
LEFT JOIN pg_attribute a
  ON a.attrelid = p.logicalrelid
 AND a.attnum = (regexp_match(p.partkey::text, ':varattno ([0-9]+)'))[1]::int
WHERE p.logicalrelid = 'rb5.etl_cleaned'::regclass;
```

结果：`rb5.etl_cleaned | h | dev_id`。

artifact 创建方式：`CREATE UNLOGGED TABLE rb5_stage.step2_input_b<N>_<YYYYMMDD> (LIKE rb5.etl_cleaned INCLUDING DEFAULTS)`，随后 `create_distributed_table(artifact, 'dev_id', colocate_with => 'rb5.etl_cleaned')`。

### 1.2 freeze_step2_input_artifact

- state：`running -> ready`，异常时 `failed`。
- 数据：只做 `SELECT * FROM source_relation WHERE event_time_std >= day AND < day+1`，不修改 `etl_cleaned`。
- 索引复用 loop_optim/01 §4 的 7 个模板：`cell_id`、`operator/lac/cell`、lookup、dim_time、`record_id`、`source_row_uid`、`event_time_std`。
- 索引名使用短 hash，避免 PostgreSQL 63 字符限制。

### 1.3 run_profile_pipeline 显式参数

`run_profile_pipeline(input_relation=...)` 透传到 Step2 内部，`build_path_a_records`、`build_path_b_cells`、`persist_candidate_seed_history`、`write_step2_run_stats` 共用同一个 resolved input。`get_step2_input_relation(override=...)` 会先验证 relation 存在；无 override 时沿用 `step2_batch_input -> _step2_cell_input -> etl_cleaned fallback`。

### 1.4 Step1 40 核 SETUP

`PARALLEL_40_SETUP`：

```text
SET max_parallel_workers_per_gather = 40
SET max_parallel_workers = 40
SET max_parallel_maintenance_workers = 16
SET parallel_tuple_cost = 0.01
SET parallel_setup_cost = 100
```

实现点：`etl/pipeline.py` 在 Step1 执行期间临时包裹 parse/clean/fill 的 CTAS executor，保留原 Citus CTAS split/distribution 逻辑，并将 populate 阶段改为 `execute_distributed_insert(..., session_setup_sqls=PARALLEL_40_SETUP)`。静态扫描 Step1 CTAS 物化路径为 11 处。

### 1.5 producer/consumer 流程

```text
producer: load raw day -> run_step1_pipeline -> freeze_step2_input_artifact -> queue(batch_id)
consumer: queue(batch_id) -> rb5_meta.pipeline_artifacts ready -> run_profile_pipeline(input_relation=artifact)
          -> run_enrichment_pipeline -> run_maintenance_pipeline -> sentinels -> status consumed
```

默认失败策略：consumer fail-fast 并写 `failed` state；producer 检查 stop_event 后不再启动下一天。`--producer-fail-fast` 保留给需要更激进停止的场景。

### 1.6 reset SQL

`reset_step1_to_step5_for_full_rerun_v3.sql` 末尾新增：

```sql
DROP SCHEMA IF EXISTS rb5_stage CASCADE;
CREATE SCHEMA rb5_stage;
TRUNCATE rb5_meta.pipeline_artifacts;
```

实际实现用 `DO` guard 包住 truncate，避免首次 reset 时 state 表尚未创建而失败。

## 2. Smoke 验证

- `rb5_stage` schema：存在。
- `rb5_meta.pipeline_artifacts`：存在，`pg_dist_partition.partmethod='n'`，即 Citus reference table。
- batch 7 freeze：`artifact='rb5_stage.step2_input_b99_20251207'`，`rows=4,428,601`，`build_time=14.02s`。
- smoke artifact 索引：7/7 创建完成。
- cleanup：`DROP TABLE rb5_stage.step2_input_b99_20251207` + `DELETE FROM rb5_meta.pipeline_artifacts WHERE batch_id=99`，cleanup 后 state 行数 0。

## 3. 02C 守护扩展

- 新 test：`test_artifact_pipelined_runner_freezes_before_consumer`。
- 守护内容：producer 中 `run_step1_pipeline < freeze_step2_input_artifact < queue.put`；consumer 必须从 `rb5_meta.pipeline_artifacts` ready state 取 relation，并调用 `run_profile_pipeline(input_relation=...)`。
- 手工 invoke 当前文件 4 个 `test_`：全部 PASS。
- `python3 -m py_compile` 覆盖新 runner、daily loop、profile、etl、maintenance schema、test 文件：PASS。

## 4. 已知限制 / 未做

- 不跑全 7 批；完整 artifact pipeline 实战留给 03 阶段。
- 未跑 Step2-5 smoke；本阶段只验证 freeze artifact。
- producer/consumer 资源压力和死锁行为留给 03 阶段长跑观察。
- artifact 空间监控留给 03 跑后评估。

## 5. 给 03 重跑阶段的输入

启动命令建议：

```bash
export REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'
export PGOPTIONS='-c auto_explain.log_analyze=off'
python3 rebuild5/scripts/run_citus_artifact_pipelined.py \
  --start-day 2025-12-01 \
  --end-day 2025-12-07 \
  --start-batch-id 1
```

03 阶段验收沿用 fix6 03 口径：每批内置 4 哨兵，终点 TCL b7 对 fix6 03 的 `340,767` 做 ±5%，对 PG17 的 `341,460` 做 ±20%，sliding 日期范围仍要求 `2025-12-01..2025-12-07`。
