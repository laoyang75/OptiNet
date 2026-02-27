

## 0. 任务概览

### 0.1 你要交付的最终产物（Agent 输出）
1) `run_summary.json`：本次运行总体摘要（耗时、temp 增量、I/O 增量、瓶颈分类）
2) `samples_activity.csv`：运行时 `pg_stat_activity` 采样（含 wait_event/MessageQueueSend）
3) `samples_dbstat.csv`：运行时 `pg_stat_database` 采样（temp_bytes/temp_files/blks_read/hit/time）
4) `explain_smoke.json`：Smoke 的 `EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)` 结果
5) `explain_full_shape.json`：Full 的 `EXPLAIN (FORMAT JSON)`（仅形状，不跑全量）
6) `stage_profile.json`：分段 profiling 每段（耗时、行数、表大小、temp 增量）
7) `bottleneck_report.md`：人类可读报告（结论+证据+优先级实验清单）

---

## 1. 执行参数（可改，不需要改 SQL 正文）

> Agent 在执行前，请把这些变量写入运行上下文（MCP / env / config 均可）
```yaml
run:
  run_id: "20251222_001"
  application_name_prefix: "codex_step30"
  schema: "public"

db:
  # 由 Agent 自己从环境/连接器中获取，不在此硬编码
  # connection: "postgresql://..."

step30:
  # 你的 Step30 SQL 原文（整段）作为字符串输入给 Agent（从用户提供内容中读取）
  sql_text_source: "USER_PROVIDED_IN_CHAT"

mode:
  smoke: true
  smoke_report_date: "2025-12-01"
  smoke_operator_id_raw: "46000"

guc:
  statement_timeout: "0"
  jit: "off"
  work_mem: "512MB"                      # profiling 建议从 256~512MB 起；不要一上来 2GB
  max_parallel_workers_per_gather: 16
  parallel_setup_cost: 0
  parallel_tuple_cost: 0.01
  hash_mem_multiplier: 2.0

sampling:
  activity_interval_seconds: 2           # 1~5 秒均可
  dbstat_interval_seconds: 60            # 30~120 秒均可
  max_runtime_minutes: 180               # 止损：超过 3 小时直接结束并出报告（可改）
  stoploss_temp_bytes_gb: 500            # 止损：temp_bytes 增量超过 500GB 直接结束（可改）
  stoploss_temp_growth_gb_per_min: 20    # 止损：temp 增速持续高于 20GB/min（可改）

profiling:
  enable_stage_profiling: true
  stage_use_unlogged_tables: true
  stage_schema: "public"                # 或者用专用 schema 如 perf_tmp
  stage_table_prefix: "tmp_step30_prof"
````

---

## 2. 预置表（用于记录与可追溯）

> Agent：如果你无法创建表（权限不足），则退化为只导出 CSV/JSON 文件，不影响任务完成。

### 2.1 创建 perf 记录表（推荐）

```sql
CREATE TABLE IF NOT EXISTS public.codex_perf_runs (
  run_id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  application_name text NOT NULL,
  is_smoke boolean NOT NULL,
  smoke_report_date date,
  smoke_operator_id_raw text,
  guc jsonb,
  notes text
);

CREATE TABLE IF NOT EXISTS public.codex_perf_samples_activity (
  run_id text NOT NULL,
  ts timestamptz NOT NULL,
  pid int,
  leader_pid int,
  backend_type text,
  state text,
  wait_event_type text,
  wait_event text,
  q_age interval,
  query_prefix text
);

CREATE TABLE IF NOT EXISTS public.codex_perf_samples_dbstat (
  run_id text NOT NULL,
  ts timestamptz NOT NULL,
  temp_files bigint,
  temp_bytes bigint,
  blks_read bigint,
  blks_hit bigint,
  blk_read_time double precision,
  blk_write_time double precision
);

CREATE TABLE IF NOT EXISTS public.codex_perf_stage_summary (
  run_id text NOT NULL,
  stage_name text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz NOT NULL,
  elapsed_ms bigint NOT NULL,
  out_rows bigint,
  out_bytes bigint,
  temp_bytes_delta bigint,
  blks_read_delta bigint,
  notes text
);
```

---

## 3. 核心执行流程（Agent 必须按顺序执行）

### Step A — 生成 run 标识与会话标签

> 目的：让采样能精准过滤到本次 Step30 会话与 parallel workers。

```text
application_name = "{application_name_prefix}|run={run_id}|smoke={true/false}"
```

Agent 需在 Step30 运行会话中执行：

```sql
SET application_name = 'codex_step30|run=20251222_001|smoke=true';
```

---

### Step B — 设置 GUC + Smoke 开关（不修改 SQL 正文）

在 Step30 会话里执行（与你原 SQL 的 session 参数一致，但 work_mem 用 profiling 值）：

```sql
SET statement_timeout = 0;
SET jit = off;
SET work_mem = '512MB';
SET max_parallel_workers_per_gather = 16;
SET parallel_setup_cost = 0;
SET parallel_tuple_cost = 0.01;
SET hash_mem_multiplier = 2.0;

-- smoke 参数通过 current_setting('codex.*') 读取，因此用 set_config 注入
SELECT set_config('codex.is_smoke', 'true', true);
SELECT set_config('codex.smoke_report_date', '2025-12-01', true);
SELECT set_config('codex.smoke_operator_id_raw', '46000', true);
```

同时写入 run 元信息（如果可写表）：

```sql
INSERT INTO public.codex_perf_runs(run_id, application_name, is_smoke, smoke_report_date, smoke_operator_id_raw, guc, notes)
VALUES (
  '20251222_001',
  current_setting('application_name', true),
  true,
  '2025-12-01'::date,
  '46000',
  jsonb_build_object(
    'work_mem', current_setting('work_mem', true),
    'max_parallel_workers_per_gather', current_setting('max_parallel_workers_per_gather', true),
    'jit', current_setting('jit', true),
    'parallel_setup_cost', current_setting('parallel_setup_cost', true),
    'parallel_tuple_cost', current_setting('parallel_tuple_cost', true),
    'hash_mem_multiplier', current_setting('hash_mem_multiplier', true)
  ),
  'baseline smoke profiling'
)
ON CONFLICT (run_id) DO UPDATE SET guc=excluded.guc, notes=excluded.notes;
```

---

### Step C — 基线快照（运行前）

> Agent：在“监控会话”或任意会话执行均可（建议单独连接，避免影响主会话）。

#### C1. pg_stat_database 基线

```sql
SELECT now() AS ts,
       temp_files, temp_bytes,
       blks_read, blks_hit,
       blk_read_time, blk_write_time
FROM pg_stat_database
WHERE datname = current_database();
```

将结果保存为 `baseline_dbstat.json`

#### C2. 输入表体量与统计新鲜度（用于“计划误判”解释）

```sql
SELECT relname,
       pg_total_relation_size(relid) AS total_bytes,
       n_live_tup,
       last_analyze, last_autoanalyze
FROM pg_stat_all_tables
WHERE schemaname='public'
  AND relname IN (
    'Y_codex_Layer2_Step02_Gps_Compliance_Marked',
    'Y_codex_Layer2_Step04_Master_Lac_Lib',
    'Y_codex_Layer2_Step05_CellId_Stats_DB',
    'Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac',
    'Y_codex_Layer2_Step06_L0_Lac_Filtered'
  );
```

保存为 `baseline_tables.json`

---

### Step D — 启动采样器（与 Step30 并行）

> Agent：用第二连接执行循环采样，并写入表或导出 CSV。

#### D1. activity 采样 SQL（每 2 秒）

过滤条件：`application_name LIKE 'codex_step30|run=20251222_001%'`

```sql
SELECT now() AS ts,
       pid, leader_pid, backend_type,
       state, wait_event_type, wait_event,
       now()-query_start AS q_age,
       left(query, 120) AS query_prefix
FROM pg_stat_activity
WHERE application_name LIKE 'codex_step30|run=20251222_001%'
ORDER BY backend_type, pid;
```

写入表（可选）：

```sql
INSERT INTO public.codex_perf_samples_activity(run_id, ts, pid, leader_pid, backend_type, state, wait_event_type, wait_event, q_age, query_prefix)
SELECT '20251222_001', *
FROM (
  SELECT now(), pid, leader_pid, backend_type, state, wait_event_type, wait_event, now()-query_start, left(query,120)
  FROM pg_stat_activity
  WHERE application_name LIKE 'codex_step30|run=20251222_001%'
) x;
```

同时导出 `samples_activity.csv`

#### D2. dbstat 采样 SQL（每 60 秒）

```sql
SELECT now() AS ts,
       temp_files, temp_bytes,
       blks_read, blks_hit,
       blk_read_time, blk_write_time
FROM pg_stat_database
WHERE datname=current_database();
```

写入表（可选）：

```sql
INSERT INTO public.codex_perf_samples_dbstat(run_id, ts, temp_files, temp_bytes, blks_read, blks_hit, blk_read_time, blk_write_time)
SELECT '20251222_001', *
FROM (
  SELECT now(), temp_files, temp_bytes, blks_read, blks_hit, blk_read_time, blk_write_time
  FROM pg_stat_database WHERE datname=current_database()
) x;
```

同时导出 `samples_dbstat.csv`

#### D3. 止损逻辑（Agent 端实现）

Agent 需在采样循环里计算：

* `temp_bytes_delta = current.temp_bytes - baseline.temp_bytes`
* `temp_growth_rate = (temp_bytes_delta over last 5 minutes) / minutes`
  触发任一即 **中止主会话 Step30**（如果可控），并立即生成报告：
* `temp_bytes_delta > stoploss_temp_bytes_gb * 1024^3`
* `temp_growth_rate > stoploss_temp_growth_gb_per_min * 1024^3`
* `elapsed_minutes > max_runtime_minutes`

> 如果 Agent 无法 kill 查询：至少要停止等待、保存现场，并在报告里标注“未能中止，已保存证据”。

---

### Step E — 获取 explain 证据（Smoke 真实 + Full 形状）

#### E1. Smoke：EXPLAIN ANALYZE（强制、必须）

> 注意：这里不要真正 CREATE TABLE，避免污染/耗时；只解释最终 SELECT 形态。
> Agent 实现方式：

1. 从用户提供的 Step30 SQL 中提取 `CREATE TABLE ... AS WITH ... SELECT ...` 的 `WITH ... SELECT ...` 部分
2. 包装成：`EXPLAIN (...) WITH ... SELECT ...;`

执行：

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, TIMING OFF, SUMMARY, FORMAT JSON)
WITH ...  -- 你的 Step30 原 WITH 全文
SELECT ...; -- 你的 Step30 最终 SELECT 全文（不包含 CREATE TABLE）
```

保存 JSON 为 `explain_smoke.json`

#### E2. Full：只要形状（必须）

把 smoke 参数关掉（但只 explain，不运行）：

```sql
SELECT set_config('codex.is_smoke', 'false', true);
SELECT set_config('codex.smoke_report_date', '', true);
SELECT set_config('codex.smoke_operator_id_raw', '', true);

EXPLAIN (BUFFERS, SETTINGS, FORMAT JSON)
WITH ...
SELECT ...;
```

保存为 `explain_full_shape.json`

---

### Step F — 执行 Step30（Smoke CTAS 实跑，用于观察 MessageQueueSend/写入等真实行为）

> 目的：你要看到“实跑数据”，而不是只看 explain。

把 smoke 参数重新打开（同 Step B），然后执行你的原 Step30 SQL（保持 DROP/CREATE TABLE/ANALYZE 等原样）。

Agent 需记录：

* 主会话开始/结束时间
* 是否中途止损
* 生成表的行数与大小（如果成功）

成功后补充采集：

```sql
SELECT count(*) AS rows FROM public."Y_codex_Layer3_Step30_Master_BS_Library";
SELECT pg_total_relation_size('public."Y_codex_Layer3_Step30_Master_BS_Library"') AS bytes;
```

---

### Step G — 分段 Profiling（可选但强烈推荐，enable_stage_profiling=true 时执行）

> 目的：把“到底慢在哪”精确到阶段，而不是靠猜。
> 方法：把 Step30 拆成 8 段，每段落一个 UNLOGGED 表，记录耗时/行数/大小/temp 增量。

#### G0. Profiling 注意事项

* 所有临时表名包含 run_id，避免冲突：`{stage_table_prefix}_{run_id}_s01_xxx`
* 每段都做：

  * 段前基线：`pg_stat_database` 快照
  * 段后快照：算 delta
  * `ANALYZE` 临时表（帮助下一段 explain/计划稳定）
  * 记录 `out_rows` + `out_bytes`

#### G1. 建议分段（按你 SQL 逻辑，命名固定）

1. `s01_bucket_universe`（Step06 聚合）
2. `s02_map_unique`（Step05 唯一映射聚合）
3. `s03_gps_points_final`（Step02 过滤+lac_final）
4. `s04_center_init`（信号策略+初始中心直方图/窗口）
5. `s05_outlier_filter`（初始距离+剔除）
6. `s06_center_final`（最终中心）
7. `s07_dist_pcts`（最终距离分布 p50/p90/max）
8. `s08_anomaly_cell_cnt`（多 LAC 哨兵聚合）

> Agent 实现方式：从 Step30 CTE 里按“可重用边界”提取子查询；如果自动解析困难，可采用“复制原 WITH，并在末尾 SELECT 目标 CTE”的方式落表：

* 例如：

  ```sql
  CREATE UNLOGGED TABLE tmp... AS
  WITH (原 Step30 全部 CTE)
  SELECT * FROM bucket_universe;
  ```

  这样无需手写重构，只要从原 SQL 中能定位 CTE 名称即可。

#### G2. 每段通用模板（Agent 复用）

```sql
-- (1) 段前快照
SELECT now() AS ts, temp_files, temp_bytes, blks_read, blks_hit, blk_read_time, blk_write_time
FROM pg_stat_database WHERE datname=current_database();

-- (2) 落表
DROP TABLE IF EXISTS public.tmp_step30_prof_20251222_001_s01_bucket_universe;
CREATE UNLOGGED TABLE public.tmp_step30_prof_20251222_001_s01_bucket_universe AS
WITH ...  -- Step30 原 WITH 全文
SELECT * FROM bucket_universe;

ANALYZE public.tmp_step30_prof_20251222_001_s01_bucket_universe;

-- (3) 行数/大小
SELECT count(*) AS rows FROM public.tmp_step30_prof_20251222_001_s01_bucket_universe;
SELECT pg_total_relation_size('public.tmp_step30_prof_20251222_001_s01_bucket_universe') AS bytes;

-- (4) 段后快照（用于 delta）
SELECT now() AS ts, temp_files, temp_bytes, blks_read, blks_hit, blk_read_time, blk_write_time
FROM pg_stat_database WHERE datname=current_database();
```

Agent 需要在 `stage_profile.json` 里记录每段：

* `elapsed_ms`
* `out_rows`
* `out_bytes`
* `temp_bytes_delta`
* `blks_read_delta`
* 以及 explain（可选）：`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT count(*) FROM (WITH ... SELECT * FROM cte) t;`（更轻量）

---

## 4. 自动瓶颈分类规则（Agent 必须实现）

> 输出字段：`bottleneck_class` ∈ {`TEMP_SPILL`, `LEADER_SINGLE_THREAD`, `IO_BOUND`, `BAD_ESTIMATE`, `CPU_HEAVY`, `MIXED`}

### 4.1 TEMP_SPILL（最危险）

满足任一：

* `temp_bytes_delta > 50GB`（smoke 也很大时基本确定）
* `explain_smoke` 中出现 `Sort Method: external merge` 或 `Disk:` 或 HashAgg/Sort 标注 spilled
* `temp_growth_rate` 持续高（见止损）

输出证据：

* temp_bytes 时间序列 + explain 节点片段（JSON 里定位到节点）

### 4.2 LEADER_SINGLE_THREAD（你描述的“只剩 1 核跑”最像这个）

满足：

* activity 采样中，parallel worker 的 `wait_event=MessageQueueSend` 占比 > 60%
* explain 显示 `WindowAgg` / `Finalize Aggregate` / `Gather` 之后仍有重节点
* leader 长时间 active 且 wait_event 为空或不是 IO

输出证据：

* `samples_activity.csv` 中 MessageQueueSend 占比统计
* explain 中 Gather 上方的节点路径

### 4.3 IO_BOUND

满足：

* `blks_read_delta` 很大且 `blk_read_time` 增长显著
* activity 出现 `wait_event_type=IO`/`DataFileRead` 等频繁

输出证据：

* `samples_dbstat.csv` I/O 指标曲线（数值列表即可）
* explain 中大量 Seq Scan/大表 Join

### 4.4 BAD_ESTIMATE（计划误判）

满足：

* explain_smoke 中任一节点 `Actual Rows / Plan Rows >= 10` 或 `<= 0.1`（偏差巨大）

输出证据：

* Top 偏差节点列表（节点类型、plan rows、actual rows）

### 4.5 CPU_HEAVY

满足：

* temp 不大、I/O 不大，但总耗时高，且 explain 热点是大量函数计算（例如距离三角函数）
* activity 里不怎么 wait，持续 active

输出证据：

* explain 热点节点类型（ProjectSet/Function Scan/Compute-heavy projection）

### 4.6 MIXED

多个类型同时显著则归 MIXED，并按影响排序给出“先做哪个实验”。

---

## 5. 报告生成模板（Agent 输出 `bottleneck_report.md`）

Agent 按以下结构生成：

1. 运行摘要

* run_id / smoke 参数 / GUC
* 总耗时
* temp_bytes 增量
* blks_read 增量、blk_read_time 增量
* 是否触发止损

2. 运行时行为（基于 samples）

* parallel workers 数量
* MessageQueueSend 占比
* leader 是否 IO wait
* 关键阶段时间段（若 stage profiling 开启则引用 stage）

3. explain 证据（smoke + full 形状）

* Top 10 热点节点（按 Actual Total Time）
* 是否出现 spilled sort/hash（Disk）
* Gather 上方是否有 WindowAgg/Finalize/写入重节点
* 估计偏差 Top 节点

4. 分段 profiling（若开启）

* 每段：elapsed / rows / bytes / temp_delta / blks_read_delta
* 找出占比最大的 1~2 段作为“第一瓶颈”

5. 结论：bottleneck_class + 证据引用
6. 下一步实验清单（按优先级，且每个实验只改一个变量）

* 实验 1：针对第一瓶颈的最小改动（例如子集化 map_unique、去掉 text key 参与 join/group、降低 window 输入）
* 实验 2：并行策略（分片并行）验证 leader 单线程
* 实验 3：work_mem 扫描（256MB/512MB/1GB）验证 spill 点

---

## 6. 下一步“必做”的三项最小实验（Agent 仅给建议，不直接改 SQL）

> Agent 在报告末尾必须输出这三项建议（不需要你确认才能写入报告）：

1. **单测 map_unique**

* `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT ... FROM (map_unique 逻辑) t;`
* 判断是否全表扫+HashAgg spill

2. **wuli_fentong_bs_key 参与 join/group 的 A/B**

* A：保持现状
* B：join/group 只用 (tech_norm, bs_id, lac_dec_final)，wuli_key 最后再拼
* 比较 temp 与耗时

3. **WindowAgg 是否掐断并行**

* 从 explain_smoke 抽取路径：Gather 上方是否有 WindowAgg/Finalize
* 若是：建议试验“分片并行”（hash(bucket)%N 并发跑 N 份）

---

## 7. 重要执行要求（防止再次白跑）

* 任何一次运行都必须带 run_id 与 application_name
* 任何一次运行都必须开采样器
* 任何一次运行都必须记录 baseline 与 delta
* 任何一次运行如果 temp 失控必须止损并保存现场
* 任何一次修改必须 A/B，且一次只改一个变量

---

## 8. 附录：Agent 需要从用户 SQL 中抽取的两段文本（解析规则）

> 你提供的是：

* 一段 `CREATE TABLE ... AS WITH ... SELECT ...;`
* 后续还有统计表 CTAS（Step30_Gps_Level_Stats）

Agent 解析规则：

1. 抽取 Step30 主表的 `WITH ... SELECT ...`（用于 explain 与分段落表）
2. 保留原 SQL 全文用于 smoke 实跑（包含 DROP/CREATE/ANALYZE）
3. 第二段统计表可以不参与瓶颈核心（通常不慢），但可保留运行记录

如果自动解析失败：

* 允许退化方案：只做 “全 SQL smoke 实跑 + 采样 + dbstat + full shape explain”，并在报告中标注“未能完成 CTE 分段解析”。

