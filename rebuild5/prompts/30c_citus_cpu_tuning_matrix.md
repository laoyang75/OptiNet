# 30c · Citus CPU 并发矩阵压测(自主模式)

> **更新日期**:2026-04-23
> **接续**:Round 2 已完工(`rb5_bench.notes.topic='ROUND2_COMPLETE'`,id=10)。
> **本轮目标**:在 Round 2 结论之上**找并发最优点**。Round 2 实测集群 160 核仅峰值用到 16.5 核(≈10%),明显没吃满。本轮专门 A/B 测几组关键并发参数,给下一阶段全量迁移选定最优值。

---

## 1. 为什么做这个压测

Round 2 的 run_results 显示:

| 阶段 | worker CPU 峰值(全集群合计) | 相当于几核 |
|---|---|---|
| B1 parse | 1057% | 10.6 / 160 |
| B2 clean | 110% | 1.1 |
| B3 profile | 99% | 1.0 |
| B4 spatial | 95-174% | 1-1.7 |
| **B6 create index** | **1654%** | **16.5** ← 本轮最高 |

说明 160 核集群大部分时间空闲。理论瓶颈:

- `max_parallel_workers_per_gather = 8` 对 **Citus 分布查询几乎不生效**(Citus 并行是 shard-level,不是 per-gather)
- `citus.max_adaptive_executor_pool_size = 32` 是 coordinator 同时向 worker 发的 task 上限 → 每 worker 同时只 8 task → 每 task 串行 1 核 → **理论 upper bound 32 核**
- 实测 10%(16/160)说明还没打到 upper bound

**历史原因**:本地单机版 `cell_sliding_window.parallel_workers = 16` 是保守 IO-bound 配置(本地盘是瓶颈)。集群 IO 不是瓶颈了,完全可以更激进。

**本轮做什么**:在已有 Round 2 数据基础上,只改并发参数、不动数据,做矩阵 A/B,找最优点。

---

## 2. 任务边界

### ✅ 做
1. 选 3 个关键 benchmark(§5):B1 parse、B4 by_cellid spatial、B6 create index
2. 按 §4 的参数矩阵(3 × 2 = 6 组配置),每组配置跑这 3 个 benchmark × 2 次取中位
3. 每次 run 前都**重启 coordinator 容器**(避免缓存效应,确保 cold cache 公平对比)
4. 指标落 `rb5_bench.cpu_tuning_matrix`(新表,自建)
5. CPU / WAL / temp 采样不能留 NULL
6. 出结论:**推荐最优并发组合**,含具体参数值 + 预期加速比

### ❌ 不做
- 不改任何应用代码
- 不新建数据(直接用 `rb5_src.raw_gps_day` 的 355 万样本)
- 不改 schema 结构 / 表定义
- 不改 `synchronous_commit` / `fsync` / `wal_level`
- 不 DROP 任何 Round 1 / Round 2 产物

---

## 3. 自主权

本轮**完全自主**:

- 重启容器多少次都行
- 改参数多少次都行
- 新加测试组合都行(超出 §4 矩阵时在 `rb5_bench.notes` 记录原因)
- 有意外发现就写 `rb5_bench.notes`,不要埋在日志
- 时间预算:**2-4 小时**;超过 6 小时仍无结论写 severity='blocker'

---

## 4. 参数矩阵(6 组基础配置)

维度 1 — `citus.max_adaptive_executor_pool_size`(coordinator 并行派 task 数)
- **P32**(Round 2 现值)
- **P64**
- **P128**

维度 2 — `max_parallel_workers_per_gather`(每查询内并行 worker)
- **G8**(Round 2 现值)
- **G2**(激进降低,让 Citus shard-level 并行自己占满)

矩阵(共 6 组):

| 组 | pool_size | per_gather | 假设 |
|---|---|---|---|
| C1 | 32 | 8 | Round 2 基准 |
| C2 | 64 | 8 | pool 翻倍 |
| C3 | 128 | 8 | pool 再翻倍(可能超过 worker 总容量,留观察) |
| C4 | 32 | 2 | per_gather 减小,看对比 |
| C5 | 64 | 2 | pool 翻倍 + per_gather 小 |
| C6 | 128 | 2 | 最激进 |

### 另加 2 组索引专项(仅跑 B6)

索引构建对 `max_parallel_maintenance_workers` 敏感,单独测:

| 组 | maintenance_workers | 备注 |
|---|---|---|
| I-M4 | 4(接近默认) | 基准 |
| I-M8 | 8 | Round 1-2 已应用 |
| I-M16 | 16 | 激进 |

这 3 组只跑 B6。

### 不动的参数(本轮保持 Round 2 现状)

- `max_worker_processes = 40`
- `max_parallel_workers = 30`
- `shared_buffers` / `work_mem` / `effective_cache_size`
- `citus.shard_count = 64`(重分片代价大)

---

## 5. 三个 benchmark

### B1 parse(CPU-heavy,JSON 展开)

```sql
DROP TABLE IF EXISTS rb5_etl.b1_parsed_cputest;
CREATE TABLE rb5_etl.b1_parsed_cputest (LIKE rb5_etl.b1_parsed INCLUDING ALL);
SELECT create_distributed_table('rb5_etl.b1_parsed_cputest','did',colocate_with=>'rb5_src.raw_gps_day');

INSERT INTO rb5_etl.b1_parsed_cputest
SELECT ... (和 Round 2 的 B1 语义一致,参考 rb5_etl.b1_parsed);

-- 跑完立即:
TRUNCATE rb5_etl.b1_parsed_cputest;    -- 下一轮干净起点
```

> **重要**:用 `INSERT INTO distributed_table SELECT ...`(预建 + 插入),不要用 CTAS + distribute。原因 Round 2 已证明 CTAS 后再 distribute 有搬运税(Top SQL 第 1 名 create_distributed_table 204 秒)。

### B4 by_cellid(self-join,colocation 验证)

```sql
DROP TABLE IF EXISTS rb5_pipe.b4_spread_cputest;
-- 从 rb5_etl.b2_clean_cell 输入(Round 2 产物,cell_id 分布)做 self-join
CREATE TABLE rb5_pipe.b4_spread_cputest (cell_id bigint, max_spread_m int);
SELECT create_distributed_table('rb5_pipe.b4_spread_cputest','cell_id',colocate_with=>'rb5_etl.b2_clean_cell');

INSERT INTO rb5_pipe.b4_spread_cputest
SELECT ... (Haversine self-join,参考 Round 2 B4 by_cellid);

TRUNCATE rb5_pipe.b4_spread_cputest;
```

### B6 create index(maintenance 并行)

```sql
DROP INDEX IF EXISTS rb5_etl.idx_cputest_did_cell;
CREATE INDEX idx_cputest_did_cell ON rb5_etl.b2_clean(did, cell_id);
-- 3 次平均,取中位
```

---

## 6. 测试流程(每组)

```
for 配置 in [C1, C2, C3, C4, C5, C6]:
    1. 改 postgresql.conf 到本组参数
    2. 重启 coordinator 容器(worker 不重启,只是 coordinator 的 citus 参数是 coord 级)
       + pg_stat_statements_reset()
    3. 验证 SHOW 值对得上
    4. 跑 B1(2 次) - 记录中位 + CPU 峰值采样
    5. 跑 B4 by_cellid(2 次)
    6. 每行写入 rb5_bench.cpu_tuning_matrix:
       - config_label('C1','C2',...)
       - pool_size / per_gather
       - query_name('B1'/'B4')
       - run_idx(1/2)
       - duration_ms
       - worker_cpu_peak_pct(全集群峰值,用 sar/top 采样)
       - coord_cpu_peak_pct
       - wal_bytes
       - explain_json
    7. TRUNCATE 测试输出表(C1 产物不污染 C2)

for 索引配置 in [I-M4, I-M8, I-M16]:
    1. 改 max_parallel_maintenance_workers
    2. 重启 coordinator
    3. DROP INDEX + CREATE INDEX × 3 次
    4. 写入 rb5_bench.cpu_tuning_matrix(query_name='B6')
```

CPU 采样方式(coordinator 上执行):

```bash
# 启动 benchmark 前先起一个后台采样器,每 1s 记一次 5 台机器 CPU
(while true; do
  for host in 217 216 219 220 221; do
    ssh postgres@192.168.200.$host "top -bn1 | grep 'Cpu(s)' | awk '{print \$2+\$4}'"
  done | paste -sd+ | bc
  sleep 1
done) > /tmp/cpu_sample_Cx.log &

# benchmark 跑完后:
kill %1
awk 'BEGIN{m=0}{if($1>m) m=$1}END{print m}' /tmp/cpu_sample_Cx.log
```

这个峰值(单位 %,可以 > 100)是全集群 CPU 合计 → 除以(4×100=400% 物理核峰值,或 4×4000%=16000% 基于 40 逻辑核基准,你选一个口径,在 notes 里说明)。

---

## 7. 结果表(自建)

```sql
CREATE TABLE rb5_bench.cpu_tuning_matrix (
  id              SERIAL PRIMARY KEY,
  config_label    TEXT,    -- 'C1','C2',...,'I-M4'...
  pool_size       INT,
  per_gather      INT,
  maintenance_workers INT,
  query_name      TEXT,    -- 'B1'|'B4'|'B6'
  run_idx         INT,
  duration_ms     BIGINT,
  worker_cpu_peak_pct INT,
  coord_cpu_peak_pct  INT,
  wal_bytes       BIGINT,
  temp_bytes      BIGINT,
  explain_json    JSONB,
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## 8. 最终交付(落 DB + md)

### 8.1 `rb5_bench.cpu_tuning_matrix` — 原始数据

每组 × 每 benchmark × 每次运行 一行。最少 6×2×2 + 3×3 = **33 行**。

### 8.2 `rb5_bench.notes` — 关键发现

必须包含:
- `topic='cpu_tuning_optimal'` severity='info':**你推荐的最优组合 + 预期加速**(具体哪组配置,B1 vs 基准快多少,B4 快多少,B6 快多少)
- `topic='cpu_tuning_surprise'`(若有):意外发现(比如 C6 反而慢,或者某组 CPU 打穿但耗时没降)
- `topic='CPU_TUNING_COMPLETE'` severity='info':**完工信号,最后一条**

### 8.3 `rb5_bench.report` — 新一行

`report_name='optinet_rebuild5_citus_cpu_tuning_YYYYMMDD'`,完整 md。

### 8.4 md 副本

agent 自己工作目录留一份 `optinet_rebuild5_citus_cpu_tuning_YYYYMMDD.md`。

### 8.5 md 必须回答

1. **推荐参数组合**:具体 `pool_size / per_gather / maintenance_workers` 值
2. **加速比**:这组配置相对 Round 2 基准(C1)的 B1/B4/B6 加速倍数
3. **CPU 利用率**:最高组合能达到多少核(集群 160 核的占比)
4. **意外发现**(如有)
5. **对全量迁移的建议**:这组参数下,Round 2 预测的 92 分钟全量 rerun 能否降到多少

---

## 9. 完成后

插入:
```sql
INSERT INTO rb5_bench.notes (topic, severity, body) VALUES (
  'CPU_TUNING_COMPLETE','info',
  '6 组并发参数矩阵 + 3 组索引并行测试完成,推荐组合见 rb5_bench.notes topic=cpu_tuning_optimal。'
);
```

上游会用 MCP 跑:
```sql
SELECT * FROM rb5_bench.notes WHERE topic='CPU_TUNING_COMPLETE';
SELECT * FROM rb5_bench.notes WHERE topic IN ('cpu_tuning_optimal','cpu_tuning_surprise');
SELECT config_label, query_name,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS median_ms
FROM rb5_bench.cpu_tuning_matrix
GROUP BY config_label, query_name
ORDER BY config_label, query_name;
```

验收通过后,上游会开 prompt 31 启动全量迁移 rerun,**使用你推荐的并发参数**。

---

## 10. 边界提醒

- **不动**应用代码 / schema / 已有数据
- **不改** fsync / synchronous_commit / wal_level
- 每组配置后 TRUNCATE 测试输出表,避免污染下组
- 每次重启 coordinator 后,等 pg_dist_node 的 4 worker 都 isactive=true 再开测
- 意外就写 notes,不硬推
