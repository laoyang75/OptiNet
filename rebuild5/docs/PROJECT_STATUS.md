# Rebuild5 当前状态总览(2026-04-27)

本文是 **fix5 / fix6_optim / loop_optim / upgrade 系列收档之后**的项目状态导航。

> 想入门系统业务逻辑 → 看 [`README.md`](./README.md)(云端接手入门)
> 想跑数据 / 跑批 / 操作集群 → 看 [`runbook.md`](./runbook.md)(顶层操作手册)
> 想看历史改动决策 trail → 看 [`archive/fix_history/`](./archive/fix_history/)

---

## 0. TL;DR

| 维度 | 当前状态 |
|---|---|
| **PostgreSQL** | **18.3**(2026-04-27 升级,从 17.6 → 18.3) |
| **Citus** | 14.0-1 |
| **PostGIS** | 3.6.3 |
| **集群拓扑** | 1 coord(217)+ 4 worker(216/219/220/221),所有节点 5488 |
| **生产入口** | `postgres://postgres:123456@192.168.200.217:5488/yangca` |
| **PG17 fallback** | `5487` 端口保留 ~1-2 周观察期(coordinator 217 同时跑) |
| **数据基线** | TCL b7 = 340,766 / sliding_window 24,017,207 行 / 7 天全(2025-12-01..2025-12-07) |
| **8 类 drift_pattern** | 全有(stable / dual_cluster / uncertain / large_coverage / migration / oversize_single / insufficient / collision) |
| **跑全 7 批最新时长** | ~7,691s ≈ 128 min(loop_optim 03 8541s 后,upgrade 调优重跑加速 ~9.9%) |
| **改 1 行单批快验** | ~13 min(`bash scripts/runbook/run_single_batch.sh`) |
| **关键调优参数** | shared_buffers=64GB / max_wal_size=64GB / effective_cache_size=180GB / max_parallel_workers=24 / shm-size=16g / citus.max_intermediate_result_size=64GB / dynamic_shared_memory_type=posix |

---

## 1. 历史阶段总览

按时间顺序,孤立子目录 + 一句话定位:

| 阶段 | 目录 | 周期 | 主要交付 |
|---|---|---|---|
| **fix5** | [`archive/fix_history/fix5/`](./archive/fix_history/fix5/) | 早期 | Citus 迁移可行性 + 4 根因修复(scope materialization / sliding_window trim / ctid distributed DELETE 不支持 / parameterized distributed plan)+ 全 7 批跑通 |
| **fix6_optim** | [`archive/fix_history/fix6_optim/`](./archive/fix_history/fix6_optim/) | 中期 | 02A 审计 + 02B 抽统一 helper(`core/citus_compat.execute_distributed_insert`)+ 02C 16 个守护测试 + 03 pipelined 加速 1.13× + 04_runbook + 6 个 bash 脚本 |
| **loop_optim** | [`archive/fix_history/loop_optim/`](./archive/fix_history/loop_optim/) | 后期 | 01 索引补全(25+条)+ 02 artifact-driven pipelined runner + 02b 分布键 hotfix + 03 全 7 批 wall clock 8541s |
| **upgrade** | [`archive/fix_history/upgrade/`](./archive/fix_history/upgrade/) | 最近 | v1 dumpall 路径失败 → v2 fresh rebuild + per-table COPY → finalize + tuning + port cutover + 内核 6.6.12 试验(216) |

**收档原则**:每个子目录都是"历史 trail",**已不再 active**。新工作不要再加进这些目录。

## 2. 当前 active 的事(2026-04-28 起)

| 事项 | 状态 |
|---|---|
| gps1 研究重启 | active,见 [`gps1/README.md`](./gps1/README.md) |
| UI 修复(8 块累积清洗规则前端落地) | 部分 Claude 直接做 + 部分独立 agent prompt 待写 |
| 文档收尾(本批) | 顶层 authority docs 对齐 + archive 收口中 |
| 数仓搭建 | 推迟,稳定期后单独立项 |

## 3. 关键技术决策记录(给未来人/AI 看的)

### 3.1 为什么数据库层选 Citus

- 单机 PG 装不下(数据 ~1 亿+ 行级别)
- Citus 14 + PG 18 是当前主流稳定组合,避开 Citus 15+ 的不成熟
- **教训**:`shard_replication_factor=1` 是研究环境配置,不是生产 HA。如果未来做数仓,这是关键决策点

### 3.2 为什么 enriched_records / candidate_seed_history / snapshot_seed_records 是 UNLOGGED

- 中间产物,Step 4 / Step 2 内部消费,不需要 WAL
- **代价**:容器重启会清空这些表的历史 batch(只剩当前 batch)
- **收益**:WAL 压力小,checkpoint 不爆
- **影响 endpoint_check.sh**:必须按"UNLOGGED 表只验当前 batch"口径写,不是"全 batch 历史完整"

### 3.3 为什么不走 pg_dumpall + 后置 create_distributed_table 跨集群迁移

- v1 失败教训:Citus 把 distributed 表的数据通过 dumpall 搬到新集群再 distribute,部分大表会出现"部分 shard 不可见"现象,根因是 distributed metadata 重建后 colocation 错位
- v2 正确做法:per-table CREATE TABLE 空建 + create_distributed_table → 后 COPY 数据 → Citus 自动路由到 shard
- **以后任何 Citus 跨集群迁移都按 v2 路径,不要走 dumpall**

### 3.4 为什么 artifact pipelined runner 优于 fix6 03 barrier pipelined

- fix6 03 用"barrier" 确保 Step1 day N+1 与 Step2-5 day N 重叠 depth=2,加速 1.13×
- loop_optim 02 用 immutable artifact `rb5_stage.step2_input_b<N>_<YYYYMMDD>` 切断隐式依赖,理论 producer 完全自由
- **实际**:1.05× 加速,因为 Step5 是真瓶颈,artifact 救不了。**架构方向对,但 Step5 内部并行才是下一步**

### 3.5 为什么 Step1 用 `PARALLEL_40_SETUP`

- 利用 `core/citus_compat.execute_distributed_insert` 的 `session_setup_sqls` 注入
- Step1 ETL 是 SQL-bound + per-record 独立,天然多 CPU 友好
- 只在 Step1 阶段开,Step2-5 不开(过度并行可能反慢)

### 3.6 为什么 PG18 升级 + 内核 6.6.12 升级

- PG18 是当前最新稳定版,后续构建数仓需要新版内核能力
- 老内核 3.10 是 CentOS 7 默认,某些 PG18 / Docker 新功能受限
- 内核升级先在 216 做单机试验;试验阶段曾因 root XFS warning 回退旧内核,随后按保留旧内核的策略完成全集群 6.6.12 升级
- **绝不删旧内核 / 旧数据**,旧 3.10 始终保留为 GRUB 回退入口

## 4. 当前关键架构图(2026-04-27 状态)

```
                       ┌─────────────────────────┐
                       │ Coordinator + 跳板 + 控制台 │
                       │ 192.168.200.217          │
                       │  - PG18 5488 (生产)       │
                       │  - PG17 5487 (fallback)  │
                       │  - /data/upgrade/...     │
                       └─────────────────────────┘
                                   │
                  ┌────────┬───────┼───────┬────────┐
                  │        │               │        │
              ┌───▼──┐ ┌───▼──┐ ┌────▼──┐ ┌▼─────┐
              │ 216  │ │ 219  │ │ 220   │ │ 221  │
              │worker│ │worker│ │worker │ │worker│
              │ 5488 │ │ 5488 │ │ 5488  │ │ 5488 │
              │ 5487 │ │ 5487 │ │ 5487  │ │ 5487 │
              │      │ │      │ │       │ │      │
              │ 266 placement (each worker) │
              │ ~26GB shard data            │
              └──────┘ └──────┘ └───────┘ └──────┘

Reference tables(在 5 节点都有副本):
  - rb5_meta.pipeline_artifacts
  - rb5_bench.notes
  - rb5.trusted_lac_library
  - 等 10 个

Hash distributed tables(按 cell_id 或 dev_id 分布):
  - rb5.trusted_cell_library (cell_id)
  - rb5.cell_sliding_window (cell_id)
  - rb5.enriched_records (cell_id)
  - rb5.raw_gps_full_backup (dev_id)
  - rb5.etl_cleaned (dev_id)
  - 等 32 个 distributed table × 32 shard = 1024 placement

NAS 共享:
  /nas_vol8 (5 节点都挂载,放包/dump/镜像/备份)
```

## 5. 可信回归基线(数据可信度对账标尺)

升级 / 改代码后跑出的 TCL b7 必须落在以下范围内:

| 基线 | TCL b7 | 备注 |
|---|---:|---|
| **PG17 黄金**(5433/ip_loc2 旧库) | 341,460 | 不动,只读 |
| **fix5 D 串行**(初次 7 批跑通) | 348,921(+2.19% vs PG17) | Citus DBSCAN 非确定性正常波动 |
| **fix6 03 pipelined** | 340,767(-0.20% vs PG17) | |
| **loop_optim 03 artifact** | 340,766(-0.20% vs PG17) | 与 fix6_03 差 1 行 |
| **upgrade v2 finalize 重跑** | 340,766(-0.20% vs PG17) | 与 loop_optim 03 完全一致 |

**一般验收阈值**:
- 严格(同环境同代码):±0.5%
- 跨环境(PG17 → PG18 / 调优变化):±1%
- 跨大变化(全集群重建 / 内核升级):±5%(数据可信度参考线)

## 6. 当前已知技术债 / 后续可优化方向

### 6.1 Step5 是真瓶颈

`metrics_radius` / `collision` / `daily_centroids` 这几个 SQL 跨 24M sliding_window 行算,batch 7 单批 ~1500s+,占总时长 ~70%。

**潜在优化方向**(都是新课题,1-2 周工程,不在当前任何阶段范围):
- 表分区(`cell_sliding_window` partition by event_time_std::date)
- 增量 daily_centroid(只算当天 + merge)
- per-cell 内部并行

### 6.2 集群无 HA(`shard_replication_factor=1`)

任何一台 worker 挂 → 26% shard 不可访问。
任何一台 worker 硬盘坏 → 26% 数据永久丢失(unique 副本)。

**适合数仓时再决策**:
- A:`shard_replication_factor=2`(简单,磁盘 ×2,写入慢 10-30%)
- B:Streaming replication / Patroni(标准 PG HA,加机器)
- C:灾难恢复 playbook(定期 dump,挂了几小时 downtime 可接受)

### 6.3 `endpoint_check.sh` / `sentinels.sh` 对 UNLOGGED 表的口径

已修(upgrade v2 finalize 阶段),只验当前 batch。如果未来重写脚本,**保持这个口径**。

### 6.4 GitHub HTTPS push 不稳

近期多次 SSL_ERROR_SYSCALL,等 60s 重试一般能成。**不是 fix5/fix6/loop/upgrade 的问题**,是网络问题。push pending 不算 blocker。

## 7. 推荐入门顺序(给新人 / 新 AI)

```
1. 读 README.md(本目录)— 业务逻辑 + 状态机
2. 读 PROJECT_STATUS.md(本文)— 当前状态 + 历史 trail 索引
3. 读 runbook.md(本目录)— 怎么操作集群 / 跑批 / 验证
4. 按需读 [`archive/fix_history/`](./archive/fix_history/) 下各 trail 子目录 — 历史决策依据
5. 实操:cd WangYou_Data && bash rebuild5/scripts/runbook/sentinels.sh 7
   验证集群 + 数据健康
```
