# 30 Citus 4+1 新集群基准调优与测试(迁移前准备)

> **更新日期**:2026-04-23
> **项目定位**:OptiNet-main(项目) / rebuild5(阶段) / **citus-benchmark**(本任务)
> **本 prompt 用途**:把新搭好的 Citus 集群调到能承接 rebuild5 pipeline 负载的状态,并用 150 万行样本覆盖未来迁移会遇到的**所有负载模式**,产出结构化报告。
> **你的范围**:**集群配置 + 基准测试**。不做业务迁移、不改应用代码、不决定生产分布策略。
> **交付方式**:两样东西 —— (1) 一份 markdown 报告 (2) `optinet_rebuild5_sandbox` 库里的 `bench.*` 数据表。两样都要留着,上游(Claude + 用户)会用 MCP 直接 SELECT 你的成果规划迁移。

---

## 0. 集群事实(已知)

- 拓扑:**Citus,1 coordinator + 4 worker**,共 5 台机器
- PG 版本:17(和本地一致);Citus 版本由你确认
- 硬件:5 台机器**同构**(CPU / 内存 / 盘 / 网络 = 本地开发机一致)
- 密码:和本地一致(`postgres` / `123456`)
- coordinator 入口:**`192.168.200.217:5488`**
- 理论并行:worker × 4 层面约为本地单机的 **4 倍**

---

## 1. 任务边界

### ✅ 做
1. 集群健康检查(Citus 拓扑 + 4 worker 注册)
2. 5 台机器的 OS / PG / Citus 参数推荐与应用
3. 内核层调优(THP / swappiness / scheduler)
4. **建立干净的分层库**(§6)
5. 导入 150 万样本(用户提供 pg_dump)
6. 跑基准测试(§7 的 B1-B8 八个场景,每个场景**至少一个代表性 SQL**,你可以根据需要加多几条)
7. 两档配置对比(`r01_default` + `r02_recommended`);若有明显瓶颈信号,最多再加 `r03_tuned` 一轮
8. 所有结果落入 `bench.*` 表 + 输出 markdown 报告(§10)

### ❌ 不做
- 不导入业务数据(除用户提供的 150 万样本)
- 不决定**生产**环境的分布键 / shard_count / colocation(你只在 sandbox 为测试目的做一次,写到 `bench.notes` 里当建议,不是定论)
- 不改 `pg_hba.conf` 认证方式 / 新增用户
- 不关 `fsync` / `synchronous_commit`
- 不配复制 / standby / rebalancer
- 不装除 `pg_stat_statements` / `auto_explain` / `citus` 外的扩展
- 不清空 PGDATA
- 不 DROP `bench.*` 或测试产物表(要留给上游 MCP 校验)

### 🔍 上游 MCP 校验(决定你报告风格的关键)

- 上游有一个 MCP 客户端(名 `PG_Citus`)可以直接连 coordinator 跑 SELECT
- **所有关键数字必须落到 `bench.*` 表**;不要只写在日志或 markdown
- 报告里任何数字都必须能用一条 SELECT 复算出来
- 报告末尾附一段 "MCP 快速校验 SQL"(§10.3),让上游直接粘贴验证
- 有疑问的发现直接写 `bench.notes` 表,标 severity,不要犹豫

### 🎯 给你的空间(重要)

- 本 prompt 给的是**测试意图**和 **骨架样例**,**不是死命令**
- 具体 SQL 写法、分布键选择、colocation 策略、shard_count 取值,**由你决定**
- 你认为某条基准测 X 维度更合适换种写法,就换,把理由写 `bench.notes`
- 如果 150 万样本跑完某条基准时长 < 100ms,说明样本偏小测不出,加大或多跑几轮都行
- 工具、脚本、观测方式随意,**结果能写进 `bench.*` 表就行**

---

## 2. 集群健康检查

coordinator(`192.168.200.217:5488`)上:

```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'citus';
SELECT nodeid, nodename, nodeport, noderole, isactive
FROM pg_dist_node ORDER BY noderole, nodeid;
SELECT run_command_on_workers($$ SHOW server_version $$);
SELECT run_command_on_workers($$ SELECT extversion FROM pg_extension WHERE extname='citus' $$);
```

任何一项异常先停下报告,不继续。

---

## 3. 机器盘点(5 台)

每台机器汇报:

- **CPU**:型号、物理核、逻辑核、NUMA 节点数(`lscpu`、`numactl -H`)
- **内存**:总量、当前 `free -h`
- **数据盘**:型号、挂载点、文件系统;`fio` 测 4k 随机读写 + 128k 顺序读(自选测法,跑几分钟有结果就行)
- **内核**:`vm.swappiness` / `vm.overcommit_memory` / `vm.dirty_*` / THP 状态
- **网络**:coordinator ↔ 每 worker 之间 `iperf3` 带宽 + `ping` 平均时延

**全部写入 `bench.machine_spec` 表**(§6 会建)。

---

## 4. PostgreSQL 参数推荐(coordinator vs worker)

### 4.1 两类节点公共项

```ini
# CPU 并行(按本机物理核 N)
max_worker_processes             = N
max_parallel_workers             = floor(N * 0.75)
max_parallel_workers_per_gather  = max(2, floor(N / 4))
max_parallel_maintenance_workers = min(8, floor(N / 2))

# 内存(按本机内存 M GB)
effective_cache_size             = M * 0.7 GB
maintenance_work_mem             = 2 GB
temp_buffers                     = 32 MB

# IO / WAL
random_page_cost                 = 1.1   # SSD/NVMe;HDD 改 4.0
effective_io_concurrency         = 200   # SSD/NVMe;HDD 改 2
max_wal_size                     = 8 GB
min_wal_size                     = 2 GB
checkpoint_completion_target     = 0.9
wal_compression                  = on

# 可观测
shared_preload_libraries         = 'citus,pg_stat_statements,auto_explain'
pg_stat_statements.max           = 10000
pg_stat_statements.track         = all
auto_explain.log_min_duration    = 10s
auto_explain.log_analyze         = on
log_checkpoints                  = on
log_lock_waits                   = on
log_temp_files                   = 0
log_min_duration_statement       = 5000

# 保持默认,不改
# synchronous_commit / fsync / wal_level
```

### 4.2 coordinator 独有

coordinator 偏协调,不吃太多内存:

```ini
shared_buffers                   = min(8 GB, M * 0.15)
work_mem                         = 32 MB
max_connections                  = 400

citus.max_adaptive_executor_pool_size = 16   # 起点,按 §9 迭代
citus.shard_count                      = 32  # 4 worker × 8 shard
citus.shard_replication_factor         = 1
citus.task_executor_type               = 'adaptive'
citus.local_table_join_policy          = 'auto'
citus.enable_repartition_joins         = on
```

### 4.3 worker 独有

worker 吃 CPU + 内存:

```ini
shared_buffers                   = min(16 GB, M * 0.25)
work_mem                         = 128 MB          # 起点;有溢出调 256 MB
max_connections                  = 200
```

### 4.4 落地流程

1. 每台的最终推荐值**先写到 `bench.pg_conf_recommended`**
2. 用户审核通过后再 apply + `systemctl restart postgresql`
3. 重启后再跑 §2 健康检查
4. 实际 `SHOW ALL` 值写入 `bench.pg_conf_applied`

---

## 5. 内核层调优(每台)

```bash
# 关 THP
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag
# 永久化:写 /etc/rc.local 或 systemd unit

cat >> /etc/sysctl.d/99-postgres.conf <<EOF
vm.swappiness = 10
vm.overcommit_memory = 2
vm.dirty_background_ratio = 5
vm.dirty_ratio = 20
EOF
sysctl -p /etc/sysctl.d/99-postgres.conf

# NVMe 确认 scheduler = [none] 或 [mq-deadline]
cat /sys/block/nvme0n1/queue/scheduler
```

改动写 `bench.kernel_tuning` 表。

---

## 6. 数据库结构(分层,隔离,可追溯)

### 6.1 命名约定

项目-阶段-任务三级命名,方便未来扩展:

| 级别 | 值 | 说明 |
|---|---|---|
| 项目 | `optinet` | OptiNet-main 主线 |
| 阶段 | `rebuild5` | 当前阶段(未来 rebuild6 另起新库) |
| 任务分隔 | schema 层面 | `src / etl / pipe / bench` 各管一层 |

**库名固定**:`optinet_rebuild5_sandbox`

> `_sandbox` 后缀表示这是**测试用,不是生产**。未来如果有真 Citus 生产库,会叫 `optinet_rebuild5_prod` 或 `optinet_rebuild5`,互不干扰。

### 6.2 建库 + schema

```sql
-- coordinator 上
CREATE DATABASE optinet_rebuild5_sandbox;
\c optinet_rebuild5_sandbox
CREATE EXTENSION citus;

-- 注册 worker(具体 SQL 按你集群版本来;通常是 citus_add_node 或从 pg_dist_node 复用)

-- 四层 schema
CREATE SCHEMA src   AUTHORIZATION postgres;
CREATE SCHEMA etl   AUTHORIZATION postgres;
CREATE SCHEMA pipe  AUTHORIZATION postgres;
CREATE SCHEMA bench AUTHORIZATION postgres;

COMMENT ON SCHEMA src   IS '原始数据层 - 用户提供,只读';
COMMENT ON SCHEMA etl   IS 'ETL 层 - B1/B2 基准产物(解析 / 清洗)';
COMMENT ON SCHEMA pipe  IS '画像层 - B3-B5,B8 基准产物(聚合 / 多质心 / JOIN / 发布)';
COMMENT ON SCHEMA bench IS '基准测试控制面 - 指标 / 配置 / 机器规格 / 备注';
```

### 6.3 控制面表(`bench` schema 下)

```sql
-- 机器规格
CREATE TABLE bench.machine_spec (
  node_role    TEXT,     -- 'coordinator' | 'worker'
  node_name    TEXT,
  cpu_model    TEXT,
  cpu_physical INT,
  cpu_logical  INT,
  numa_nodes   INT,
  mem_gb       INT,
  disk_model   TEXT,
  fs_type      TEXT,
  fio_rand4k_rw_iops BIGINT,
  fio_seq128k_rd_mbps BIGINT,
  kernel_ver   TEXT,
  thp_state    TEXT,
  extra_jsonb  JSONB,    -- 放自由发挥的额外数据
  recorded_at  TIMESTAMPTZ DEFAULT now()
);

-- PG 参数 推荐 vs 应用
CREATE TABLE bench.pg_conf_recommended (
  node_name TEXT, param TEXT, value TEXT, rationale TEXT,
  PRIMARY KEY (node_name, param)
);
CREATE TABLE bench.pg_conf_applied (
  node_name TEXT, param TEXT, value TEXT,
  applied_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (node_name, param)
);

-- 内核改动
CREATE TABLE bench.kernel_tuning (
  node_name TEXT, setting TEXT, before_val TEXT, after_val TEXT,
  applied_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (node_name, setting)
);

-- 基准测试结果(核心表)
CREATE TABLE bench.run_results (
  run_id          TEXT,            -- 'r01_default' | 'r02_recommended' | 'r03_tuned'
  query_name      TEXT,            -- 'B1' ... 'B8'
  variant         TEXT DEFAULT 'main',  -- 同一 benchmark 不同写法对比可用
  stage           TEXT,            -- 对应 pipeline:'parse' | 'clean' | 'profile' | 'spatial' | 'join' | 'index' | 'merge' | 'bulk'
  config_label    TEXT,            -- 简短描述,如 'wm=128M,pg=4'
  started_at      TIMESTAMPTZ,
  duration_ms     BIGINT,
  rows_in         BIGINT,
  rows_out        BIGINT,
  task_count      INT,             -- Citus EXPLAIN 的 Task Count
  repartition_hit BOOLEAN,         -- EXPLAIN 里出现 Repartition 吗
  worker_cpu_peak_pct INT,
  coord_cpu_peak_pct  INT,
  work_mem_peak_mb INT,
  temp_bytes      BIGINT,
  wal_bytes       BIGINT,
  explain_json    JSONB,           -- EXPLAIN(FORMAT JSON) 完整输出
  notes           TEXT,
  PRIMARY KEY (run_id, query_name, variant)
);

-- 备注 / 发现 / 疑问
CREATE TABLE bench.notes (
  id         SERIAL PRIMARY KEY,
  run_id     TEXT,
  topic      TEXT,
  severity   TEXT,    -- 'info' | 'warn' | 'suspect' | 'blocker'
  body       TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 最终报告(markdown 整份内容)
-- 为什么进 DB:上游是通过 MCP 连 Citus 跑 SELECT,看不到你本地文件系统。
-- 把报告本体放这里,上游 `SELECT body FROM bench.report ORDER BY created_at DESC LIMIT 1` 就能拿到。
CREATE TABLE bench.report (
  id           SERIAL PRIMARY KEY,
  report_name  TEXT,                       -- 'optinet_rebuild5_citus_benchmark_YYYYMMDD'
  body         TEXT,                       -- 完整 markdown
  meta         JSONB,                      -- {rows_scanned: ..., runs: ['r01_default','r02_recommended'], ...}
  created_at   TIMESTAMPTZ DEFAULT now()
);
```

所有洞察都**必须**落进这些表。终端 scroll / markdown 不算交付。

---

## 7. 样本数据导入

### 7.1 数据源(从旧 PG 直接抽样)

- **旧库 DSN**:`postgres://postgres:123456@192.168.200.217:5433/ip_loc2`
- **源表**:`rebuild5.raw_gps_full_backup`(2025-12-01 ~ 12-07 共 7 天)
- **源表总行数**:**25,442,069 行**(已经过 ETL 去重)
- **目标样本量**:150 万行左右(±10 万可接受)
- **网络**:旧库和新 Citus coordinator 在同一内网,`192.168.200.217:5433` 和 `:5488` 都可达

### 7.2 抽样 + 导入流程(你自选方案,下面是推荐做法)

**步骤 1 — 在新库建好空表结构**(从旧库拉表定义):

```bash
# 在新 Citus coordinator 上
pg_dump -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
        --schema-only --no-owner --no-acl \
        -t rebuild5.raw_gps_full_backup \
        | sed 's/rebuild5\./src./g; s/raw_gps_full_backup/raw_gps_sample/g' \
        | psql -h 127.0.0.1 -p 5488 -U postgres -d optinet_rebuild5_sandbox
```
(或者手工 `CREATE TABLE src.raw_gps_sample (...)`,自选)

**步骤 2 — 从旧库抽样,用 COPY 管道直接灌入新库**:

```bash
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -c "\\copy (SELECT * FROM rebuild5.raw_gps_full_backup \
             TABLESAMPLE BERNOULLI(6) REPEATABLE(42)) TO STDOUT" \
| psql -h 127.0.0.1 -p 5488 -U postgres -d optinet_rebuild5_sandbox \
  -c "\\copy src.raw_gps_sample FROM STDIN"
```
- `TABLESAMPLE BERNOULLI(6)` 大约抽到 **6% ≈ 153 万行**
- `REPEATABLE(42)` 让你多次重抽结果一致,便于调试
- 如果这个抽样方案在你环境有问题(比如网络带宽不够,或 BERNOULLI 太慢),**可选方案**:
  - 按 1 天过滤:`WHERE "ts"::date = '2025-12-04'` 大约 350 万行,再叠 `TABLESAMPLE` 降到 150 万
  - 按 did hash 过滤:`WHERE abs(hashtext("did")) % 17 = 0` 大约 6% 分布
  - 直接 pg_dump `-Fc` 落盘 + pg_restore(慢但最可靠)
  - **选什么写 `bench.notes` topic='sampling_method'** 记录下来

**步骤 3 — 校验行数 + 分布**:

```sql
-- 在 optinet_rebuild5_sandbox 里
SELECT COUNT(*) FROM src.raw_gps_sample;  -- 期望 140 万~ 160 万之间

-- 分布表化
SELECT create_distributed_table('src.raw_gps_sample', 'did');
-- 理由写 bench.notes topic='dist_key_choice'

-- shard 均匀度(偏差 ±5% 内 OK;> 5% 写 warn;> 10% 写 blocker)
WITH dist AS (
  SELECT nodename, COUNT(*) AS n_shards, SUM(shard_size) AS bytes
  FROM citus_shards
  WHERE table_name = 'src.raw_gps_sample'::regclass
  GROUP BY nodename
)
SELECT *, ROUND(100.0 * bytes / SUM(bytes) OVER (), 1) AS pct FROM dist;
```

### 7.3 注意事项

- 旧库 `rebuild5.raw_gps_full_backup` 是**只读数据**,不要对它 UPDATE/DELETE
- 抽样本身不要跑 > 10 分钟;跑久了写 notes 记录实测耗时和瓶颈
- 若网络不稳,用 pg_dump 落盘兜底

---

## 8. 基准测试(B1-B8)

每个 benchmark 给的是**测试意图**和**骨架样例**。你可以:

- 改 SQL 写法、用不同分布键、加/去掉 colocation
- 同一 benchmark 跑多个 variant 做对比(比如 "B4 自 JOIN" 跑 colocated vs repartition 两个写法)
- 骨架 SQL 太小跑不出差异就加大 / 多跑
- 加自己觉得有价值的观测点

**每个 benchmark 的指标最终要落 `bench.run_results`**,至少一个 variant = 'main'。额外 variant 名自取。

### B1 · Parse(jsonb 展开 + DISTINCT ON)

**对应业务**:`parse.py::_parse_cell_infos`
**测试什么**:大 JSON 对象展开,shard-local 能否避免 shuffle
**骨架**:参考 `rebuild5/backend/app/etl/parse.py` 第 210-320 行
**输出表**:`etl.b1_parsed`
**关键观察**:task_count、repartition_hit、per-worker 耗时均匀度

### B2 · Clean(大表 UPDATE)

**对应业务**:`clean.py::ODS_RULES` 里 `action='nullify'` 的那批规则(包括新的 ODS-023b)
**测试什么**:分布式 UPDATE,能否 shard-local 执行
**输入**:B1 输出(考虑 colocate)
**输出表**:`etl.b2_clean`(或 in-place UPDATE `etl.b1_parsed`,你选)
**关键观察**:UPDATE 分发 vs coordinator 中转、WAL 增量、是否锁抖动

### B3 · Profile(GROUP BY + percentile)

**对应业务**:`profile/logic.py` 的 cell 级 p50 / p90 聚合
**测试什么**:分布式聚合 + `percentile_cont`(Citus 必须 coordinator merge)
**输出表**:`pipe.b3_cell_stats`(按 `cell_id` 分布)
**关键观察**:coordinator 最终 merge 阶段的 CPU + work_mem 峰值 —— 这是未来生产的关键瓶颈点

### B4 · Spatial 多点距离(self-join)

**对应业务**:`maintenance/window.py` 的 cell 点对最大距离计算(模拟 DBSCAN 的距离矩阵)
**测试什么**:**self-join 在 Citus 上的代价** —— 如果输入按 `dev_id` 分布而聚合键是 `cell_id`,会强制 repartition
**骨架 SQL**:
```sql
-- 可能的最简写法(agent 可改)
SELECT a.cell_id,
       MAX( 6371000 * 2 * asin(sqrt(
              sin(radians(b.lat - a.lat)/2)^2
            + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(radians(b.lon - a.lon)/2)^2
       )) )::int AS max_spread_m
FROM etl.b2_clean a
JOIN etl.b2_clean b ON a.cell_id = b.cell_id AND a.dev_id < b.dev_id
WHERE a.lon IS NOT NULL AND b.lon IS NOT NULL
GROUP BY a.cell_id;
```
**输出表**:`pipe.b4_spread`
**建议 variant 对比**:
- `variant='by_devid'`(输入按 dev_id 分布,预期 repartition_hit=true)
- `variant='by_cellid'`(另建一份按 cell_id 分布,预期 repartition_hit=false)
- **两种写法的 duration_ms 差异是未来迁移决定 colocation 策略的关键证据**

### B5 · Label JOIN 风暴(多表 JOIN)

**对应业务**:`label_engine.py` 主查询(4+ LEFT JOIN 合并候选/特征/动态特征)
**测试什么**:多表 colocated JOIN 的分布式执行
**输入**:从 B3 输出衍生 2-3 张辅助小表(模拟 `_label_cell_kstats` / `_label_k2_features`)
**输出表**:`pipe.b5_label`
**关键观察**:所有表按 cell_id colocated 的话,repartition_hit 应为 false;如果出现 repartition 写 severity='blocker'

### B6 · 索引构建

**对应业务**:`pipeline.py` 里 CREATE INDEX
**测试什么**:Citus 分布式 CREATE INDEX 的并行度,`maintenance_work_mem` 效果
**做**:给 `etl.b2_clean` 建 2-3 个复合索引(建议包含 `(dev_id, cell_id)` 和 `(cell_id)`)
**关键观察**:索引构建总耗时,单索引平均

### B7 · Coordinator Merge(ORDER BY + LIMIT 跨 shard)

**对应业务**:UI 分页(`queries.py::paginate` + `ORDER BY p90 DESC LIMIT 50`)
**测试什么**:coordinator 从各 worker 拉 top N 再 merge 的延迟
**做**:针对 `pipe.b3_cell_stats` 跑几条 `ORDER BY ... LIMIT 50`(不同排序字段)
**关键观察**:期望 < 500ms;超过 2s 写 severity='warn'

### B8 · Bulk Insert(大批量 INSERT ... SELECT)

**对应业务**:`publish_cell.py` 把画像产物批量写入 trusted_cell_library
**测试什么**:跨 worker INSERT 性能,colocated 情况下的吞吐
**输出表**:`pipe.b8_published`(按 `cell_id` 分布,colocated with b3)
**关键观察**:WAL 增量 + 每 worker 本地吞吐

---

## 9. 调参迭代(最多 3 档配置)

两档对比 `r01_default` + `r02_recommended` 跑完后,如果有以下**任一**明显信号,加一轮 `r03_tuned`:

| 现象 | 调什么 |
|---|---|
| worker CPU < 70% 但 coordinator CPU 打满 | ↑ `citus.max_adaptive_executor_pool_size`(16 → 32) |
| worker CPU 打满仍慢 | 记录,别调 shard_count(重分片代价高) |
| `log_temp_files` 大量几百 MB | ↑ worker `work_mem`(128M → 256M) |
| B6 索引占比 > 50% | ↑ `maintenance_work_mem`(2G → 4G) |
| B3/B7 的 coordinator CPU > 85% | ↑ coordinator `work_mem`(32M → 128M) |
| checkpoint 抖动大 | ↑ `max_wal_size` / `checkpoint_timeout` |
| B4/B5 repartition_hit=true 且慢 | **不调**,写 `bench.notes` 让上游定 colocation |
| 盘 IO 打满 + CPU 空闲 | **硬件瓶颈**,写 notes |

**最多到 `r03_tuned`,不超过**。

---

## 10. 交付物(位置明确)

**上游和你之间唯一的桥梁是 `PG_Citus` MCP**。上游**看不到**你本地机器文件系统、shell log、终端 scroll。所以所有东西必须能从 `192.168.200.217:5488 → optinet_rebuild5_sandbox` 库 SELECT 出来。

### 10.1 主交付:数据库表(全部在 `optinet_rebuild5_sandbox` 库)

| 表 | 内容 | 上游怎么读 |
|---|---|---|
| `bench.machine_spec` | 5 台机器规格 | `SELECT * FROM bench.machine_spec` |
| `bench.pg_conf_recommended` | 每台推荐参数 | 同上 |
| `bench.pg_conf_applied` | 实际应用值 | 同上 |
| `bench.kernel_tuning` | 内核改动 | 同上 |
| `bench.run_results` | **所有 run × benchmark × variant 指标(核心数据)** | `SELECT * FROM bench.run_results ORDER BY query_name, variant, run_id` |
| `bench.notes` | 观察、疑问、异常、建议 | `SELECT * FROM bench.notes ORDER BY severity DESC, id` |
| **`bench.report`** | **完整 markdown 报告本体** | `SELECT body FROM bench.report ORDER BY created_at DESC LIMIT 1` |
| `src.raw_gps_sample` | 样本数据 | 保留,MCP 抽查用 |
| `etl.*` / `pipe.*` | 基准测试产物 | 保留,MCP 抽查用 |

**硬约束**:
- 所有表 **不得 DROP**
- 所有表 **不得从其他库/schema 访问**,必须在 `optinet_rebuild5_sandbox.bench.*`
- `bench.report` 里的 markdown 必须是**最终完整版**(不是草稿),插入时用 `INSERT INTO bench.report (report_name, body, meta) VALUES (...)`

### 10.2 辅助交付:markdown 文件(用户取走后转交 Claude)

除了写进 `bench.report` 表外,在你自己的工作目录(`./`)留一份 markdown 文件:

- 路径:`./optinet_rebuild5_citus_benchmark_YYYYMMDD.md`
- 内容与 `bench.report.body` 完全一致

> 你是独立 agent,工作结束后用户会从你的工作目录把这份 md 取走,转给 Claude 看。
> DB 里的 `bench.report` 是冗余副本,给 Claude 用 MCP 独立校验。两份**必须一致**。
> 如果对不上,以 DB 为准;同时在 `bench.notes` 留一条 severity='warn' 说明不一致原因。

### 10.3 报告内容(写进 `bench.report.body`)

1. **集群摘要**:Citus 版本 / PG 版本 / 5 台拓扑
2. **机器规格汇总**:贴 `SELECT * FROM bench.machine_spec` 的输出,不要手抄
3. **参数 diff**:每台 `postgresql.conf` 推荐 vs 应用(引用 `bench.pg_conf_recommended` / `bench.pg_conf_applied`)
4. **benchmark 结果对照表**:贴 `SELECT ... FROM bench.run_results` 的输出
5. **`pg_stat_statements` Top 20 耗时 SQL**(从基准运行中抓)
6. **未决问题 / 建议清单**:引用 `bench.notes` 里 severity='warn'|'blocker'|'suspect' 的条目
7. **给迁移阶段的建议**:你基于数据给的判断,比如"如果迁移用 dev_id 做 raw_gps_full_backup 分布键,B4 会触发 repartition,代价 X ms;改用 cell_id 或 pipe 层 colocate 可以避免"
8. **附:MCP 快速校验 SQL**(§10.4,一条条可粘贴复算)

### 10.4 MCP 快速校验 SQL(附在报告末尾)

让上游粘贴到 `PG_Citus` MCP 里一键验证:

```sql
-- 1. 三档配置下每个 benchmark 耗时对照
SELECT run_id, query_name, variant, duration_ms, task_count, repartition_hit
FROM bench.run_results
ORDER BY query_name, variant, run_id;

-- 2. shard 分布均匀度
SELECT nodename, COUNT(*) AS n_shards, SUM(shard_size)/1024/1024 AS mb
FROM citus_shards WHERE table_name = 'src.raw_gps_sample'::regclass
GROUP BY nodename;

-- 3. 所有 warn/blocker 备注
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

### 10.5 完工信号(必做最后一步)

所有其他工作完成后,插一条信号让上游知道"活干完了":

```sql
INSERT INTO bench.notes (topic, severity, body) VALUES (
  'DELIVERY_COMPLETE',
  'info',
  '所有 benchmark 跑完,报告已写入 bench.report。可开始 MCP 校验。'
);
```

**必须是最后一步**。没有这条,上游会认为你还在跑。

---

## 11. 完成 checklist

全部 ✅ 才算完成:

- [ ] §2 集群健康:4 worker active,版本一致
- [ ] §3 5 台机器规格落入 `bench.machine_spec`
- [ ] §4 参数推荐落入 `bench.pg_conf_recommended`,审核后应用 → `bench.pg_conf_applied`
- [ ] §5 内核参数应用 → `bench.kernel_tuning`
- [ ] §6 库 + 四层 schema + 控制面表(**含 `bench.report`**)建好
- [ ] §7 样本数据导入,行数校验 + 分布均匀度检查通过
- [ ] §8 8 个 benchmark × 2 档配置 = 至少 16 条 `bench.run_results`
- [ ] §9 若有 warn/blocker 信号,加第 3 档
- [ ] §10.1 所有数据表保留
- [ ] §10.2 markdown 文件副本写到 agent 自己工作目录 `./optinet_rebuild5_citus_benchmark_YYYYMMDD.md`
- [ ] §10.3 markdown 报告内容完整插入 `bench.report`(与 md 文件一致)
- [ ] §10.4 校验 SQL 贴在报告末尾
- [ ] §10.5 **`bench.notes` 里有 `topic='DELIVERY_COMPLETE'` 的一条**(最终信号)

---

## 12. 约束回顾

- **所有关键数字必须落 `bench.*` 表**,不能只写日志 / markdown
- **不导入业务数据**(除 150 万样本)
- **不决定生产分布策略**(只建议)
- **不改认证**
- **不关 fsync / sync_commit**
- **不 DROP bench / src / etl / pipe 的产物**
- **骨架 SQL 你可以改,但测试意图不能漂**(每个 benchmark 要真的测到对应 pipeline 阶段)
- **不确定就停下来写 `bench.notes` severity='suspect'**,不要硬推

报告 + `bench.*` 表交齐,标记完成。上游 Claude 会用 PG_Citus MCP 独立复算,然后基于你的成果规划正式迁移。
