# 30b · Citus 调优 Round 2(自主模式)

> **更新日期**:2026-04-23
> **接续**:`rebuild5/prompts/30_citus_cluster_tuning.md` 第一轮已完工(DELIVERY_COMPLETE id=15)。
> **本轮定位**:你拿到**完整自主权**,目标是**证明这个 Citus 集群能承接 rebuild5 生产级 pipeline 重跑**。不再走"先给推荐值让用户审核"的流程——你直接做、直接试、直接改,做完写进 DB 让上游验收。

---

## 1. Round 1 回顾(上游结论)

- 基础配置、schema、8 条 benchmark 都跑完了,数据结构完整 ✅
- **但 r02_recommended 和 r01_default 差异不大**,原因:session-level SET 改不了 `shared_preload_libraries`、`shared_buffers`、`max_connections` 这些需重启的参数。所以 r02 其实是"没真正应用"的状态。
- B3 percentile 52s 明显瓶颈 → 生产规模(16.7×)外推 14 分钟,接受边缘
- B4 self-join by_cellid vs by_devid 差距 23%(不是数量级)
- `pg_stat_statements` 没启用 → 没有 Top SQL 数据,这是 Round 2 必须解决的
- `synchronous_commit=off` 是历史容器参数(你没动,OK)

---

## 2. 本轮目标

**一个核心目标**:完成后,上游直接决定"是否可以把旧库 `192.168.200.217:5433/ip_loc2` 的 2500 万行全量迁移 + 应用 pipeline 重跑到这个 Citus 集群"。

**验收标准**(必须**全部**达到):

1. `pg_stat_statements` + `auto_explain` 启用且有数据可 SELECT
2. **跑一次 350 万行真实规模(1 天)的 rebuild5 完整 pipeline 模拟**(见 §5),B3 percentile 在 5 分钟以内、整个 pipeline 在 30 分钟以内
3. 若任何 benchmark 在真实规模下超出预期,你**自主调优到合理水平**(改参数、改索引、改分布键、改查询形态都可以)
4. 产出 Round 2 报告 + 新 bench 数据,上游一眼能看到"集群是否 ready"

---

## 3. 你有的权限(扩大)

本轮**全部自主**,不需要上游审核:

### ✅ 允许做
- 改 `postgresql.conf` 任意参数
- 重启 PG 容器(含改 `shared_preload_libraries`)
- 装扩展(`pg_stat_statements`、`auto_explain`、`pg_trgm`、PostGIS 如果有需要)
- 改分布键、shard_count、colocation
- DROP 你自己建的 `etl.*` / `pipe.*` benchmark 产物表
- 建新的测试表
- 迭代多少轮都行,没有 r03 上限
- **把库改名**(见 §4)

### ❌ 不允许做
- 动旧库 `192.168.200.217:5433/ip_loc2`(只读数据源)
- 动上游本地应用代码
- DROP `src.raw_gps_sample` 或 `bench.*` schema(保留给 MCP 校验)
- 改 `fsync` / `synchronous_commit`(历史配置,不动)
- 改 `pg_hba.conf` 认证 / 新增 db user

---

## 4. 库结构(新方案:长期研究工作台)

上游已经建好新库 `yangca`,**所有 Round 2 产出都写到 `yangca` 库**。

设计思路:

- `yangca` 是用户的**长期研究工作台**,MCP 永久指向它,不再换 DSN
- 每个项目 / 阶段用 **schema 前缀**隔离,不用新库
- 本阶段用 `rb5_*` 前缀:`rb5_src / rb5_etl / rb5_pipe / rb5_bench`
- 未来 rebuild6 就是 `rb6_*`,并存不冲突
- 阶段结束后再整批搬到归档库,不影响当前工作

Round 1 的数据(在 `optinet_rebuild5_sandbox` 库)**不要动,静止保留**作为历史快照。Round 2 的一切从头在 `yangca` 里独立建,不跨库引用(PG 也不支持跨库 SELECT)。

### 在 yangca 库里建 schema + 控制面表

```sql
-- 连到 yangca 库(coordinator 上 psql -d yangca)
CREATE EXTENSION IF NOT EXISTS citus;

-- 四层 schema,前缀 rb5_
CREATE SCHEMA rb5_src;
CREATE SCHEMA rb5_etl;
CREATE SCHEMA rb5_pipe;
CREATE SCHEMA rb5_bench;

COMMENT ON SCHEMA rb5_src   IS 'rebuild5 Round 2 原始层';
COMMENT ON SCHEMA rb5_etl   IS 'rebuild5 Round 2 ETL 产物';
COMMENT ON SCHEMA rb5_pipe  IS 'rebuild5 Round 2 画像产物';
COMMENT ON SCHEMA rb5_bench IS 'rebuild5 Round 2 基准测试控制面';

-- 控制面表(结构和 Round 1 一致,放 rb5_bench 下)
-- 参考 prompt 30 §6.3,把 schema 全替换成 rb5_bench
CREATE TABLE rb5_bench.machine_spec (...);            -- 同 Round 1 结构
CREATE TABLE rb5_bench.pg_conf_recommended (...);     -- 同
CREATE TABLE rb5_bench.pg_conf_applied (...);         -- 同
CREATE TABLE rb5_bench.kernel_tuning (...);           -- 同
CREATE TABLE rb5_bench.run_results (...);             -- 同
CREATE TABLE rb5_bench.notes (...);                   -- 同
CREATE TABLE rb5_bench.report (...);                  -- 同
CREATE TABLE rb5_bench.pg_stat_top20 (...);           -- 新表,本轮必建
```

### worker 注册

yangca 是新库,Citus worker 还没在这个库里注册,你要做一遍:

```sql
-- 参考 pg_dist_node 里的 worker 列表,在 yangca 里重新 citus_add_node
-- 具体 SQL 你按 Citus 版本(14.0)文档来
```

### 插一条 note 记录库结构决策

```sql
INSERT INTO rb5_bench.notes (topic, severity, body) VALUES (
  'db_structure_yangca', 'info',
  'Round 2 起,所有数据写到 yangca 库,按 rb5_* schema 前缀隔离项目。Round 1 产物静止保留在 optinet_rebuild5_sandbox 作历史快照。'
);
```

---

## 5. 核心任务:350 万行真实规模试水

### 5.1 准备样本

Round 1 的 `src.raw_gps_sample` 在另一个库,不再复用。**本轮从旧库重抽一份新的 1 天样本到 yangca**:

- 目标表:`rb5_src.raw_gps_day`
- 目标行数:**350 万行左右**(生产规模的 1/7,约为 Round 1 样本的 2.3 倍)

推荐做法 — 从旧库抽 1 整天:

```bash
# 1. 先在 yangca 里按旧库的列定义建表
# (方法:pg_dump --schema-only 旧库的 rebuild5.raw_gps_full_backup,改 schema 后应用到 yangca)

# 2. 抽 1 天数据(优先数据密度中位,如 2025-12-04 周四)
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -c "\copy (SELECT * FROM rebuild5.raw_gps_full_backup WHERE ts::date = '2025-12-04') TO STDOUT" \
| psql -h 127.0.0.1 -p 5488 -U postgres -d yangca \
  -c "\copy rb5_src.raw_gps_day FROM STDIN"

# 3. 分布
psql -h 127.0.0.1 -p 5488 -U postgres -d yangca \
  -c "SELECT create_distributed_table('rb5_src.raw_gps_day','did');"
```

如果 12-04 抽出来 < 300 万或 > 400 万,换一天或抽部分。目标区间宽松 300-400 万。

具体实现随你,选了哪天 / 多少行,写 `rb5_bench.notes topic='round2_sampling'`。

### 5.2 跑完整 pipeline 模拟(B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8)

和 Round 1 的 8 个 benchmark 语义相同,但:

- 输入改为 `rb5_src.raw_gps_day`
- 产物表:`rb5_etl.b1_parsed` / `rb5_etl.b2_clean` / `rb5_pipe.b3_cell_stats` / `rb5_pipe.b4_spread_*` / `rb5_pipe.b5_*` / `rb5_pipe.b8_published`(schema 都换成 rb5_*,不加 `_r3` 后缀)
- run_id 用 `r1_day`(本库里就是第一轮,不再叫 r03)
- **新增指标**:explain_json 要**真的**存 EXPLAIN(ANALYZE,FORMAT JSON) 的完整输出(Round 1 多数没存)
- **CPU / 内存采集**:Round 1 里 `worker_cpu_peak_pct / coord_cpu_peak_pct / work_mem_peak_mb / temp_bytes / wal_bytes` 字段大多是 NULL——**这一轮必须填上**,哪怕粗采样(每秒一次 sar / ps,取峰值)

### 5.3 如果有 benchmark 跑得差

自主决策:

| 现象 | 你可以做的 |
|---|---|
| B3 percentile > 5 min | 改查询形态(分片本地先 p50/p90 再合 coordinator?);建辅助索引;调 `work_mem` |
| B4 self-join 某 variant > 10 min | 再试 shard_count = 64 / 16;加 composite index;改 Haversine 写法 |
| 某条涉及 CPU 打满但 worker CPU < 60% | 调 `citus.max_adaptive_executor_pool_size` |
| 盘 IO 成瓶颈 | 记录,不硬调 |

每次调整前后**各跑一次**写进 `rb5_bench.run_results`,`run_id` 用 `r1_day_v1`, `r1_day_v2` 等语义化命名。

---

## 6. 可观测配置(必做)

进容器的 postgresql.conf(或你用的 docker mount):

```ini
shared_preload_libraries = 'citus,pg_stat_statements,auto_explain'
pg_stat_statements.max   = 10000
pg_stat_statements.track = all

auto_explain.log_min_duration = 10s
auto_explain.log_analyze     = on
auto_explain.log_buffers     = on
auto_explain.log_verbose     = on

log_checkpoints              = on
log_lock_waits               = on
log_temp_files               = 0
log_min_duration_statement   = 5000
```

改完 `systemctl restart` 或 `docker restart <container>`,然后:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SELECT pg_stat_statements_reset();
-- 然后跑 §5 的 pipeline,跑完:
SELECT query, calls, total_exec_time, mean_exec_time, rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC LIMIT 20;
-- 把 Top 20 结果保存到 rb5_bench.pg_stat_top20(§4 已建好的表)
```

---

## 7. Round 2 交付物

全部落 `yangca` 库:

| 新产出 | 内容 |
|---|---|
| `rb5_src.raw_gps_day` | 1 天样本,350 万行左右,distributed on did |
| `rb5_etl.b1_parsed` / `rb5_etl.b2_clean` | ETL 层产物 |
| `rb5_pipe.b3_cell_stats` / `rb5_pipe.b4_spread_*` / `rb5_pipe.b5_*` / `rb5_pipe.b8_published` | 画像层产物 |
| **`rb5_bench.run_results` 新增 rows**(run_id 以 `r1_day` 开头) | 完整指标,CPU/内存/temp/WAL 字段**不能留 NULL** |
| **`rb5_bench.pg_stat_top20`** | Round 2 后的 Top 20 耗时 SQL |
| `rb5_bench.notes` 新增 | 试水结论、自主调优过程、库结构决策 |
| **`rb5_bench.report` 新增一行**,报告名 `optinet_rebuild5_citus_round2_YYYYMMDD` | 本轮总结 |

### 报告必须回答的 5 个问题(上游要看这 5 条)

1. **在 350 万行(1 天)数据规模下,完整 pipeline(B1→B8)总耗时是多少?** 线性外推到 2500 万行是多少?
2. **哪条 benchmark 是决定性瓶颈?** 你做了什么优化?优化前后多少秒?
3. **你认为这个集群能不能承接全量 2500 万行重跑?** yes / no + 理由
4. **迁移阶段你推荐的 `create_distributed_table` 分布键策略?** 对每张核心表(raw_gps_sample、etl 产物、pipe 产物、trusted_cell_library)都给建议
5. **pg_stat_statements Top 20 里有哪些**意外慢的 SQL**?** 原因和建议修法

最后插:
```sql
INSERT INTO rb5_bench.notes (topic, severity, body) VALUES (
  'ROUND2_COMPLETE', 'info',
  '自主调优完成,全量迁移评估见 rb5_bench.report 最新一行第 3 问。'
);
```

---

## 8. 时间预算

没有硬上限,但建议:

- yangca 库 schema + 控制面表建好 + worker 注册 + 配置应用 + 重启:**< 40 min**
- 样本准备:**< 30 min**
- pipeline 试水 + 调优 1-3 轮:**< 4 小时**
- 写报告:**< 30 min**

如果超过 6 小时仍未有结论,在 `rb5_bench.notes` 写 `severity='blocker'` 说明卡在哪,上游介入。

---

## 9. 边界提醒

- **`optinet_rebuild5_sandbox` 库不动**(Round 1 产物静止保留,做历史对比用)
- 本轮一切新产出都在 **`yangca` 库**,schema `rb5_*`
- 本轮**不做全量 2500 万**,那是迁移阶段的事,不在 Round 2 范围
- MCP 上游只看 `yangca` 库里 `rb5_*` schema 的数据,不看你本地文件系统——重要结论务必写 DB

---

## 10. 完成后

按往常:

1. `rb5_bench.report` 新增一行完整 markdown
2. 自己工作目录下留一份 md 副本
3. `rb5_bench.notes` 插 `ROUND2_COMPLETE` 信号
4. 等上游 MCP 验收(上游 MCP 已改连 yangca)

验收通过后,上游会开 prompt 31 启动真正的 2500 万行迁移 + 应用代码 Citus 适配。
