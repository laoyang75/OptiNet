# Rebuild5 Citus 集群使用说明(原则性)

本文是开发 / 分析时**必读**的集群工作原则。开始任何研究或开发前,先读完这一页,避免反复踩 fix5/fix6/loop/upgrade 期间已经踩过的坑。

> 详细操作命令见 [`runbook.md`](./runbook.md)
> 详细历史 trail 见 [`PROJECT_STATUS.md`](./PROJECT_STATUS.md)

---

## 1. 集群拓扑(2026-04-28 状态)

```
   192.168.200.210    (控制台,非 Citus 节点。NAS 共享、升级包、操作脚本归档地)
   192.168.200.217    coordinator(同时承载 5487 PG17 fallback)
   192.168.200.216    worker
   192.168.200.219    worker
   192.168.200.220    worker
   192.168.200.221    worker
```

| 端口 | 用途 | 版本 |
|---|---|---|
| **5488** | **生产入口**(所有研究 / 业务都走这个) | PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3 |
| **5487** | PG17 fallback(观察期保留,**不要写入**) | PG 17.6 / Citus 14.0-1(只读使用) |
| 5433 | PG17 旧基线 ip_loc2(独立机,只读) | PG 17.x |

**生产 DSN**:`postgres://postgres:123456@192.168.200.217:5488/yangca`
**MCP 名**:`mcp__PG_Citus__execute_sql`

## 2. 数据库分层(关键!写代码前必须知道)

### 2.1 表的物理形态

Citus 把表分成 3 类,**写 SQL / 写代码必须知道目标表是哪类**,否则会撞 "could not create distributed plan":

| 类型 | 数据分布 | 适合 |
|---|---|---|
| **distributed table**(hash) | 按某列(`distribution_column`)hash 分到 4 个 worker | 大业务表 |
| **reference table** | 每个 worker 有完整副本 | 小维度表 / 共享元数据 |
| **local table**(只在 coordinator) | 不分布 | 不应该出现在生产路径 |

查某表是哪类:
```sql
SELECT logicalrelid::regclass::text AS rel,
       partmethod  -- 'h'=hash distributed, 'n'=reference
FROM pg_dist_partition WHERE logicalrelid::regclass::text = 'rb5.<table_name>';
```

### 2.2 关键表的分布(记下来)

**Distributed by `cell_id`**(cell colocation group,**这是主结果链**):
- `rb5.trusted_cell_library` / `cell_sliding_window` / `enriched_records` / `candidate_seed_history` / `step2_batch_input` / `cell_metrics_base` 等

**Distributed by `dev_id`**(device colocation group):
- `rb5.raw_gps_full_backup` / `etl_cleaned` / `etl_parsed` / `etl_filled`(Step1 输入输出层)

**Reference tables**(每个 worker 副本):
- `rb5_meta.pipeline_artifacts`(state 表)
- `rb5_bench.notes`(决策 trail)
- `rb5.trusted_lac_library` 和其他 _lac / 维度表

**Distributed by `bs_id`**:
- `rb5.trusted_bs_library` / `bs_centroid_detail`(BS colocation group)

### 2.3 colocation 原则(写 JOIN 时必须遵守)

**Citus 的 distributed JOIN 只支持 colocated tables 在 distribution column 上 join**。

✅ 正确:`trusted_cell_library JOIN cell_sliding_window ON cell_id = cell_id`(都按 cell_id 分布,colocated)
❌ 错误:`raw_gps_full_backup JOIN trusted_cell_library ON cell_id = cell_id`(raw 按 dev_id,TCL 按 cell_id,不同 colocation group → "complex joins not supported")

**写新代码 + 新表时**:看下游要 JOIN 谁,新表的 distribution_column 必须和下游 colocation 一致。

## 3. UNLOGGED 表清单(容器重启会清空!)

以下是 UNLOGGED 表(中间产物,不需要 WAL):

- `rb5.enriched_records`(Step 4 enrichment 输出)
- `rb5.candidate_seed_history`(Step 2 候选种子历史)
- `rb5.snapshot_seed_records`(Step 2 snapshot)

**重要**:容器 / Postgres 重启后,这些表的**历史 batch 全部清空**(只有当前 batch 数据)。

- `trusted_cell_library` / `cell_sliding_window` / `trusted_bs_library` 等是 LOGGED,持久。
- `endpoint_check.sh` 已经改了口径,对 UNLOGGED 表只验当前 batch。

**写代码 / 写 SQL 时不要假设 UNLOGGED 表有历史 batch 完整数据**。如果需要全 batch 视图,从 LOGGED 表拉。

## 4. 写代码必须遵守的 Citus 兼容规则

### 4.1 参数化 INSERT...SELECT 含 CTE 必须走统一 helper

```python
# ❌ 错误(fix5 D 撞过 "could not create distributed plan"):
execute(
    "INSERT INTO rb5.trusted_cell_library (...) WITH merged AS (...) SELECT ... FROM ...",
    (batch_id, ...)
)

# ✅ 正确:
from rebuild5.backend.app.core.citus_compat import execute_distributed_insert
execute_distributed_insert(
    "INSERT INTO rb5.trusted_cell_library (...) WITH merged AS (...) SELECT ... FROM ...",
    params=(batch_id, ...),
    session_setup_sqls=['SET enable_nestloop = off'],  # 可选
)
```

`execute_distributed_insert` 内部用 `psycopg.ClientCursor` 客户端 binding 把 params inline,绕开 Citus distributed planner 对参数化 INSERT...SELECT 含 CTE 的限制。

### 4.2 不能用的 SQL 模式

| 模式 | 替代 |
|---|---|
| `DELETE FROM <distributed_table> WHERE ctid = ...` | 用 PK `(batch_id, source_row_uid, cell_id)` 三元组 DELETE USING |
| `EXPLAIN ANALYZE INSERT INTO <distributed_table> ...` | 不用(Citus 不支持) — 启动时 `PGOPTIONS='-c auto_explain.log_analyze=off'` |
| `pg_dumpall + 后置 create_distributed_table` | per-table CREATE TABLE 空建 + create_distributed_table → 后 COPY 数据 |
| 跨 colocation group JOIN | 中间表落到目标 colocation group 后 JOIN |

### 4.3 02C 守护(测试时跑)

```bash
cd rebuild5 && python3 -m pytest tests/test_citus_compat.py tests/test_citus_caller_guard.py \
  tests/test_runner_scope_materialization.py tests/test_sliding_window_trim_shape.py \
  tests/test_ctid_static_guard.py
```

15+ 个测试守护 fix5 4 根因不复现。任何代码改动后都跑一次。

## 5. 跑批(改代码后验证流程)

详见 [`runbook.md`](./runbook.md) 和 [`archive/fix_history/fix6_optim/04_runbook.md`](./archive/fix_history/fix6_optim/04_runbook.md)。

| 改动范围 | 推荐验证方式 | 时长 |
|---|---|---|
| 改 1 行业务 SQL | `bash scripts/runbook/run_single_batch.sh 2025-12-01 1` | ~13 min |
| 改 Step1 ETL 规则 | reset + `run_full_artifact_pipelined.sh`(全 7 批) | ~128 min |
| 改 Step5 maintenance | reset + 7 批(同上) | ~128 min |
| 改 publish_bs/cell/lac | 单批 quick verify | ~13 min |

每批 / 终点都有自动哨兵 + endpoint check。**任何 sentinel 挂红都不要硬继续**(fix5 D 教训)。

## 6. 数据基线(对账标尺)

任何升级 / 改代码后跑出的 TCL b7 必须落在范围内:

| 基线 | TCL b7 |
|---|---:|
| PG17 黄金(5433/ip_loc2) | 341,460 |
| 当前 PG18 调优后 | **340,766**(-0.20% vs PG17) |

阈值:同环境 ±0.5% / 跨环境 ±1% / 大变化 ±5%。

## 7. 容错 / 高可用现状(必须知道)

⚠️ **当前是研究环境,无 HA**:

- `shard_replication_factor=1`(每个 shard 只有 1 份)
- 任何 1 个 worker 挂 → 26% shard 不可访问 → 业务接近瘫痪
- 任何 1 个 worker 硬盘坏 → 那 26% 数据**永久丢失**
- coordinator 挂 → 整个集群不可用

**研究环境可接受**(挂了重启容器就行,数据卷在),**但数仓上线前必须改**(`shard_replication_factor=2` / Patroni / 或定期 dump 备份)。

## 8. 控制台 / NAS 约定

- **210** 是非 Citus 控制台节点,所有运维操作的执行起点
- `/nas_vol8`(5+1 节点都挂载)放:升级包 / 镜像 tar / dump 备份 / 操作脚本归档
- `/data/upgrade/kernel-ml-6.6.12/`(在 210 上)有 reusable 脚本(`install_kernel_on_node.sh` / `post_boot_validation.sh` / `rollback_to_old_kernel.sh`)

## 9. 内核 + Postgres 调优现状(2026-04-28)

```
内核:    6.6.12-1.el7.elrepo.x86_64(全 5 节点已升)
旧内核:   3.10.0-1160.71.1.el7.x86_64(GRUB fallback,保留)
PG:      18.3
Citus:   14.0-1
PostGIS: 3.6.3

PG 参数(已 ALTER SYSTEM):
  shared_buffers = 64GB
  max_wal_size = 64GB / min_wal_size = 8GB
  checkpoint_timeout = 15min / completion_target = 0.9
  wal_compression = lz4
  effective_cache_size = 180GB
  random_page_cost = 1.2
  io_method = io_uring / io_workers = 10
  effective_io_concurrency = 64 / maintenance_io_concurrency = 64
  max_parallel_workers = 24 / max_parallel_workers_per_gather = 4
  shared_preload_libraries = citus, pg_stat_statements, auto_explain

Citus 参数:
  citus.max_intermediate_result_size = 64GB
  citus.shard_count = 32
  citus.shard_replication_factor = 1

Docker:
  --shm-size=16g
  --restart unless-stopped
  --stop-timeout=300
  --ulimit nofile=1048576:1048576
  --security-opt seccomp=unconfined(io_uring_setup 需要;全 5 节点 PG18 容器已重建)

Host profile:
  tuned-adm active = throughput-performance(全 5 节点)

Linux sysctl(/etc/sysctl.d/99-citus-network.conf,全 5 节点):
  net.core.somaxconn = 4096
  net.ipv4.tcp_max_syn_backlog = 4096
  net.core.netdev_max_backlog = 30000
  注:PG18 容器已在 io_uring 切换时滚动重建,listener backlog 已拾取新 somaxconn。

待办(后续优化):
  RAID 写入参数(按 user 指令推迟,不盲目永久修改)
```

## 10. 一些必须知道的"绝对不要做"

- ❌ 不要在生产 5488 上跑 `pg_dumpall + 后置 create_distributed_table`(v1 失败模式)
- ❌ 不要 `DELETE FROM rb5.* WHERE ctid IN ...`(Citus 不支持)
- ❌ 不要在业务代码里散落 `SET citus.* / SET enable_*`(用 `execute_distributed_insert.session_setup_sqls`)
- ❌ 不要假设 UNLOGGED 表有历史 batch(容器重启会丢)
- ❌ 不要直接 `cur.execute(参数化 INSERT...SELECT 含 CTE)`(用 `execute_distributed_insert`)
- ❌ 不要删 PG17 fallback `5487`(观察期内是终极回退)
- ❌ 不要删 `/boot/vmlinuz-3.10.0-...`(GRUB 内核回退)
- ❌ 不要 `citus_drain_node` / `citus_remove_node` 除非有明确理由(单 worker 维护用 § 3.1.1 的 pause 模式)
- ❌ 不要在 batch 跑挂时硬继续("再跑一遍碰运气" 不行 — fix5 D 教训)

## 11. 环境变量速查

```bash
# Runner / 任何 Python 脚本连数据库:
export REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'

# 必须前缀(否则 Citus 在 INSERT...SELECT 上撞 EXPLAIN ANALYZE 错):
export PGOPTIONS='-c auto_explain.log_analyze=off'

# psql 直连(跨防火墙):
export PGPASSWORD=123456
export PGGSSENCMODE=disable
psql -h 192.168.200.217 -p 5488 -U postgres -d yangca
```

## 12. 遇到不确定的事就读

按这个顺序,大部分问题都能找到答案:

1. 本文(原则)
2. [`runbook.md`](./runbook.md)(操作命令)
3. [`PROJECT_STATUS.md`](./PROJECT_STATUS.md)(当前状态)
4. [`README.md`](./README.md)(业务架构)
5. fix5 / fix6_optim / loop_optim / upgrade 子目录(历史 trail,只在排查具体问题时翻)
