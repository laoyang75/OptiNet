# Layer_3 Step30 性能评估报告（v1，已完成 C3/C4 小样本评估）

更新时间：2025-12-18

范围：仅评估 Step30（`lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`）的“为何单核/为何无并行/瓶颈在哪/是否值得改 SQL 或改执行编排”。

约束遵守说明（按 `youhua.md`）：

- 本报告先给“评估结论 + 可选方案”，**不直接改生产执行方式**（不改全局参数/不删业务表/不改业务表结构）。
- C3/C4 的评估使用了 `public` 下的 **UNLOGGED** bench 表（可逆、可清理），仅做只读查询/EXPLAIN。

---

## 1) 结论摘要（给决策用）

当前生产 Step30（pid=21125）在采样时刻持续处于 **leader 串行阶段**（`leader_pid` 关联不到任何 `parallel worker`），且不在锁等待（`wait_event=NULL`），与“单核满载”现象一致；根因高度符合 PG15 对 **ordered-set aggregate（`percentile_cont`）/排序去重** 的并行限制：底层扫描可并行，但关键分位数/排序阶段常回到单进程。

你已选择的方案 **1+2** 的评估结论（bench 小样本）：

- C3（`CTE MATERIALIZED` A/B）：**几乎无收益**（152.867ms vs 151.302ms），且从计划看 `cell_points` 本就以 CTE InitPlan 形式执行一次，显式 `MATERIALIZED` 不改变主要瓶颈。
- C4（按 `mod(bs_id,N)` 分片并行）：**“只加分片过滤”在工程上可行，但必须先处理“重复扫描 Step05/map_best”**。bench 上每个 shard 仍要全量跑 `map_best`，导致单 shard 仅从 152ms 降到 ~45–47ms（远非 1/16），意味着在真实大表 Step05 上会被 N 倍放大，风险很高。

下一步我建议你从下面二选一（我会等你确认后再动 SQL/编排）：

1) **继续让生产 Step30 跑完**（不动）；我只做“运行态采样”帮你判断是否进入新阶段/是否 spill。  
2) **把方案 2 升级为“分片并行 + 先拆出一次性公共计算”**（例如先把 `map_best`/needed_cells 落盘一次，再分片跑 percentile/dist 主链），收益更可能显著且不会把 Step05 扫描放大 N 倍。  

---

## 2) 本轮已采集到的证据（来自 DBHub/MCP）

### 2.1 运行态（C1）——Step30 正在跑、无并行 worker

Step30 正在运行的会话（从 `pg_stat_activity` 过滤 `CREATE TABLE public."Y_codex_Layer3_Step30_Master_BS_Library" AS ...`）：

- `pid=21125`
- `state=active`
- `wait_event_type/wait_event=NULL`（非锁等待）
- `running_for≈3h10m`（2025-12-18 本轮采样）

Leader/worker 检查（你hua.md C1-1）：

- 查询 `pid=21125 OR leader_pid=21125` 仅返回 1 行（leader 本人），未出现任何 `backend_type='parallel worker'`。
- 结论：**该查询在采样时刻处于“纯 leader 串行阶段”**（这与“单核满载、其他 CPU idle”的现象一致）。

temp spill 证据（你hua.md C1-2）：

- `pg_stat_database.temp_files=20247`
- `pg_stat_database.temp_bytes=7354266515308`（约 7.35 TB，统计为自上次 reset 以来的累计值）
- 说明：本轮两次采样间 `temp_bytes` 未增长（并不否认 Step30 当前阶段可能曾经/将会 spill，只是这两次采样间未观察到增量）。

CTAS 进度（你hua.md C1-3）：

- PostgreSQL 15.13 下不存在 `pg_stat_progress_create_table` 视图（查询报“关系不存在”），因此无法用该视图给出 CTAS phase/blocks 的进度证据。

### 2.2 计划证据（C2）——并行“只发生在扫描”，关键 ordered-set 聚合仍串行

对 Step30 进行了“小样本计划”检查（`params.is_smoke=true` + 最终 `WHERE mod(b.bs_id,16)=0`），执行：

- `EXPLAIN (VERBOSE) <Step30_Equivalent_Query>`

关键观察：

1) **确实存在 parallel plan**（并非全程都无法并行）

- 在 Step06 的扫描处出现：
  - `Gather ... Workers Planned: 10`
  - `Parallel Seq Scan on public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`

- 在 Step05 的扫描/聚合处出现：
  - `Gather Merge ... Workers Planned: 5`
  - `Parallel Seq Scan on public."Y_codex_Layer2_Step05_CellId_Stats_DB"`

2) 但 `percentile_cont` 所在的 ordered-set 聚合节点是串行形态

- `CTE cell_points -> GroupAggregate -> Sort -> ... percentile_cont(0.5) WITHIN GROUP (ORDER BY lon/lat)`
- 这类 ordered-set aggregate 通常需要组内排序与精确分位数计算，PG15 很难做“并行部分聚合 + 合并”，往往导致该关键阶段以单进程执行。

综合解读：

- Step30 不是“完全没有并行能力”，而是 **并行覆盖在扫描/部分聚合**，但墙钟时间大概率被 ordered-set aggregate（`percentile_cont`）主导，导致整体表现为单核阶段很长。

### 2.3 并行相关参数（背景核对）

从 `pg_settings` 抽样到的配置（与 RUNBOOK/SQL 文件内的会话级 SET 可能不同，需以实际执行会话为准）：

- `max_worker_processes=40`
- `max_parallel_workers=32`
- `max_parallel_workers_per_gather=16`
- `parallel_setup_cost=100`
- `parallel_tuple_cost=0.001`
- `work_mem=262144 kB`（256MB）
- `maintenance_work_mem=8388608 kB`（8GB）
- `jit=on`（注意：Step30 SQL 文件会 `SET jit = off;`）

---

## 3) 根因判断（基于现有证据）

### 3.1 “为什么看起来没有用到并行 worker？”

结论：**在采样时刻（C1），Step30 确实没有并行 worker（leader_pid 关联不到 parallel worker）**，属于串行阶段。

解释（与 C2 一致）：

- 计划里并行主要出现在“扫描/部分聚合”；
- 但一旦进入 `percentile_cont` 为主的 ordered-set 聚合 + Sort 阶段，往往回到单进程执行；
- 如果该阶段耗时远大于并行扫描阶段，就会被观察为“几乎全程单核满载”。

### 3.2 当前最可疑瓶颈节点（优先级）

基于 bench `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` 的可见节点耗时 + Step30 结构：

1) `cell_points` 的 `percentile_cont(0.5)`（lon/lat）= 组内排序 + 精确中位数
2) `metric_init / metric_final` 的 `percentile_cont(0.5/0.9)`（dist_m）= 再次排序 + 精确分位数
3) `map_best` 的 `DISTINCT ON ... ORDER BY ...`（需要排序/去重，且表规模大）
4) 大表 Scan/Join 期间的 spill 风险（需用 `EXPLAIN (ANALYZE, BUFFERS)` + temp_bytes 增量进一步确认）

---

## 4) C3/C4 小样本评估结果（已完成）

### 4.1 bench 数据集（可逆、UNLOGGED）

用途：让 `EXPLAIN (ANALYZE)` 能在工具/交互窗口内完成，且不影响生产长跑 CTAS。

- `public._l3_bench_step06`：`Y_codex_Layer2_Step06_L0_Lac_Filtered` 抽样（5,000 行，单日/单运营商）
- `public._l3_bench_step02`：`Y_codex_Layer2_Step02_Gps_Compliance_Marked` 抽样（5,000 行，单日/单运营商）
- `public._l3_bench_step05`：`Y_codex_Layer2_Step05_CellId_Stats_DB` 按 bench cell 子集抽样（3,322 行）
- `public._l3_bench_anomaly`：`Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac` 按 bench cell 子集抽样（4 行）

清理方式：

```sql
DROP TABLE IF EXISTS public._l3_bench_step06;
DROP TABLE IF EXISTS public._l3_bench_step02;
DROP TABLE IF EXISTS public._l3_bench_step05;
DROP TABLE IF EXISTS public._l3_bench_anomaly;
```

### 4.2 C3：`CTE MATERIALIZED` A/B（bench，小样本）

对照口径：使用与 Step30 等价的 CTE 主链（替换为 bench 表），最终仅做聚合输出以强制引用 `metric_final` / `anomaly_cell_cnt`。

关键指标（`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`）：

| 版本 | 改动 | Execution Time (ms) | Planning Time (ms) | Temp blocks | 关键观察 |
|---|---|---:|---:|---:|---|
| A | 原版 | 152.867 | 10.323 | 0 | `CTE cell_points` 以 InitPlan 执行一次（57.703ms） |
| B | `bucket_universe`/`cell_points`/`bucket_base AS MATERIALIZED` | 151.302 | 7.730 | 0 | `CTE bucket_universe` 物化（36.627ms，Workers Planned/Launched=2），总体几乎不变 |

补充：`pg_stat_database.temp_bytes=7354266515308` 在本轮 A/B 前后未观测到增量（bench 未发生 spill，EXPLAIN 也显示 `Temp Read/Written Blocks=0`）。

结论：bench 规模下 **显式 `MATERIALIZED` 不带来可见收益**，且从计划形态看多次引用 CTE 已被作为 InitPlan 处理；因此若要优化生产墙钟，优先级应低于“减少 ordered-set aggregate 排序量/减少重复大扫描”。

### 4.3 C4：按 `mod(bs_id,16)` 分片并行（bench，可行性与风险）

#### 4.3.1 口径不重不漏（bench）

以 `bucket_universe`（=Step30 最终输出桶全集）做分片：

- `total_bucket_cnt=3005`
- `sum_shard_bucket_cnt=3005`（16 个 shard 全覆盖，且互斥）

#### 4.3.2 单 shard 运行时（bench）

同口径主链，在 `bucket_universe` 与 `gps_points` 两处下推 `mod(bs_id,16)=k` 过滤，得到：

- `k=0`：Execution Time `46.254ms`（其中 `CTE cell_points` `24.018ms`）
- `k=1`：Execution Time `47.188ms`（其中 `CTE cell_points` `24.672ms`）
- `k=2`：Execution Time `45.024ms`（其中 `CTE cell_points` `23.965ms`）
- `k=3`：Execution Time `45.154ms`（其中 `CTE cell_points` `24.310ms`）

对照：不分片（全量 bench）Execution Time `152.867ms`。

解读：

- 单 shard 耗时并未接近 `152ms/16≈9.6ms`，说明**存在“与 shard 无关的固定成本”**（bench 中最典型的是 `map_best` 仍需对 `_l3_bench_step05` 做 `DISTINCT ON + ORDER BY` 全量计算）。
- 因此，“只加分片过滤 + 多会话并行”在真实数据上会把 Step05/`map_best` 的扫描与排序 **放大 N 倍**，这往往会抵消甚至反转收益。

结论：方案 2（分片并行）要成立，必须升级为“**拆出一次性公共计算（尤其 Step05/map_best）** + 分片并行跑 percentile/dist 主链”；否则风险（IO/CPU 放大）极高。

---

## 5) 可选方案（按侵入性排序）

### 4.1 为什么没有并行 worker（最可能原因）

Step30 中存在多处会显著抑制并行的结构：

1) `percentile_cont(..) WITHIN GROUP (ORDER BY ..)` 属于 ordered-set aggregate。
   - 这类聚合通常需要对组内数据排序并计算分位数，PG15 很难做“部分聚合 + 合并”，因此经常导致 `Workers Planned=0` 或只有底层 scan 并行但上层聚合串行（总体仍近似单核）。
2) `SELECT DISTINCT ON (...) ... ORDER BY ...`（`map_best`）同样依赖排序去重，常使规划器选择串行 sort/unique 路径。

证据落点：`EXPLAIN` 中 `Workers Planned/Launched=0`，且最重节点为 `GroupAggregate + Sort`（含 percentile_cont）或 `Unique + Sort`。

### 4.2 性能瓶颈可能在哪些节点（按怀疑程度排序）

1) `cell_points`：按 `(tech, bs_id, lac_final, operator, cell)` 分组的 `percentile_cont(0.5)`（lon/lat）
2) `metric_init / metric_final`：对 dist_m 的 `percentile_cont(0.5/0.9)` + max
3) `map_best`：对 Step05 做 `DISTINCT ON` + 多列 ORDER BY（如未有效走索引或需要大 sort）
4) `bucket_universe`：对 Step06 全量聚合（count distinct/min/max/active_days）写盘压力大
5) temp spill：`work_mem` 不够或并行 hash/sort 溢出到磁盘（SSD 也会拖慢）

---

## 6) 风险与回滚

### 方案 0：不改 SQL，继续串行等待

适用：业务能接受长时运行；且证据显示不存在大量 temp spill/锁等待。

风险：墙钟时间不可控；单核跑满，整体资源利用率低。

### 方案 1：小改 SQL（MATERIALIZED / 限制大扫描范围）

目的：减少重复扫描与临时数据爆炸，不改变口径。

候选改动（需你确认后再动）：

- 对“多次引用且昂贵”的 CTE 显式 `MATERIALIZED`，并在物化点减少列宽（只保留后续必需列）。
- 约束 `map_best` 的扫描范围：仅针对本次会用到的 `(operator_id_raw, tech_norm, cell_id_dec)` 子集做计算（先抽取 needed_cells 再 join Step05）。

风险：物化会产生大量中间结果，可能增加磁盘写入；需要控制中间表大小与清理策略。

### 方案 2：改执行编排（按 bs_id 分片并行，多会话跑）

目标：把“不可自动并行的排序/分位数计算”拆到多个会话分别做，从 1 核扩到 N 核。

做法（不改口径，只改执行方式）：

- 建空壳目标表
- 用 `WHERE mod(bs_id, N) = k` 跑 N 份 INSERT（不同 k），并行执行
- 结束后做唯一性/行数校验

风险：需要严格保证分片过滤出现在“足够早”的层级，避免每个分片仍扫描全量；并行会加大 IO 压力，需要选合适 N。

### 方案 3：结构性改造（阶段性落盘 / 近似分位数）

适用：必须把 Step30 压到可控时间窗，但允许更大工程量或口径调整。

选项：

- 分阶段落盘：先把 `gps_points_lac_final` / `cell_points` 落临时/UNLOGGED 表 + 索引，再跑后续步骤
- 近似分位数（需要扩展或额外组件；口径需确认）

风险：工程量大；可能引入口径差异；需要更严格回归验收。

---

## 7) 你如何选择（我建议的决策路径）

- 方案 1/2：不改输入表结构，回滚方式=停止并行作业/删除新建临时表/恢复原 SQL 执行方式；对生产表仅写入 Step30 输出表（可先写到 `*_tmp` 再切换）。
- 方案 3：必须先做“冒烟 + 口径对账”；回滚=回到原 CTAS 路径。

---

## 8) 你确认后我再动手

你已选择并完成了 **1) C3** 与 **2) C4** 的评估。接下来请你只回复一个选项号（我再继续下一步）：

1) 继续等待生产 Step30 跑完（我只做运行态采样，不改 SQL/编排）  
2) 做“方案 2 升级版”：先把 `map_best`（或 `needed_cells`）落一个可复用的中间表/UNLOGGED 表，再按 `mod(bs_id,N)` 分片并行跑剩余主链  
3) 先做“结构性减负”：用 `needed_cells`（来自 Step02/Step06）把 Step05 的扫描范围缩到本次实际用到的 cell 子集（这一步完成后，再决定是否需要分片并行）  
