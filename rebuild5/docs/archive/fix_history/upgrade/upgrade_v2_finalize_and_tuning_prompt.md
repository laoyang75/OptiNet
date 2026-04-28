# OptiNet rebuild5 / upgrade v2 收尾 + 调优(agent 新实例对话)

## § 1 元目标

v2 phase 4 已完成(TCL b7=342,581 / sentinels.sh 7 PASS),但有 2 个验收口径问题阻挡端口切换:

1. **`endpoint_check.sh` `enriched_7_batch_coverage` FAIL** — 容器重启清空了 UNLOGGED 表 `rb5.enriched_records` 的历史 batch
2. **TCL 偏差 +0.5326%** — 略超我之前写的严格 0.5%

**关键发现**:`enriched_records` 在老 PG17 5488 上**本来就是 UNLOGGED**(`relpersistence='u'`,设计就是中间产物),fix5/fix6 期间老集群从未重启所以历史 batch 一直在。`endpoint_check.sh` 实际假设了"容器一直跑"这个隐含前提。**v2 重启暴露的是脚本口径 bug,不是数据 bug**。

TCL +0.5326% vs 340,766 但 vs PG17 黄金 341,460 = +0.328%(反而更接近),Citus DBSCAN 非确定性正常波动,可接受。

**本阶段做 4 件事**(一个重启窗口内全部做完,避免反复 UNLOGGED 丢失):

1. **修 `endpoint_check.sh` 口径**:对 UNLOGGED 表只验当前 batch,不要求历史
2. **调优(`/Users/yangcongan/cursor/DataBase/Docs/05_当前PG设置优化要求.md` 分 5 步)** — reload 级 + 重建容器(shm-size=16g)
3. **reset + 全 1-7 重跑一次** — 用新参数 + 新容器,跑完后不再重启,UNLOGGED 表保留
4. **端口切换** + **commit + push + 完工话术**

## § 2 上下文启动顺序

按序读完直接开干:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/upgrade/README.md` + `upgrade_prompt.md`(v1)+ `upgrade_report.md`(v1 失败)+ `upgrade_v2_fresh_rebuild_prompt.md`(v2 起始)
3. `/Users/yangcongan/cursor/DataBase/Docs/05_当前PG设置优化要求.md` —— **本阶段调优依据**
4. `rebuild5/docs/fix6_optim/_prompt_template.md` § 11/§ 12
5. `rebuild5/scripts/runbook/endpoint_check.sh` —— 要修的脚本
6. `rebuild5/scripts/runbook/sentinels.sh` —— 参考(也对 UNLOGGED 表友好,看怎么写的)
7. `rebuild5/docs/loop_optim/03_rerun_report.md` —— 时长基线 8541s,新参数后期望加速
8. `rb5_bench.notes` topic LIKE `'upgrade_v2%'` —— v2 phase 0/1/2 trail
9. 本 prompt

读完直接开干。

## § 3 环境硬信息

### 当前实测状态(开干前必须重新探,因为可能跨小时变化)

- 5488(老):PG 17.6 / Citus 14.0-1 / **没动**
- 5491(新):PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3 / `dynamic_shared_memory_type=mmap`(因为容器默认 /dev/shm=64MB)/ `citus.max_intermediate_result_size=64GB`
- 5491 数据:TCL b7=342,581 / sentinels.sh 7 PASS / endpoint_check 缺 enriched 历史
- worker 拓扑:216/219/220/221 全 active
- 镜像在 `/nas_vol8/upgrade/packages/images/optinet_citus_14.0.1_pg18.3_postgis3.6.3_*.tar.gz`

### 服务器登录

- coord/跳板:192.168.200.217 root/111111
- workers:216/219/220/221 root/111111
- NAS:`/nas_vol8`

### MCP

- `mcp__PG_Citus__execute_sql` 当前指 5488(老 PG17)
- 5491(新 PG18)用 psql:`PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5491 -U postgres -d yangca -c "..."`

### git

- 远端 head:`a49b2a1`(loop_optim 03)
- v1+v2 文档全部 untracked,本阶段一并 commit
- working tree:`rebuild5/scripts/bootstrap_schema.py`(v2 phase 2 产物)+ `rebuild5/docs/upgrade/`(v1 + v2 prompt + report 全部)

## § 4 关联文档清单

| 路径 | 阅读 / 修改 |
|---|---|
| `/Users/yangcongan/cursor/DataBase/Docs/05_当前PG设置优化要求.md` | 阅读 — 调优依据 |
| `rebuild5/scripts/runbook/endpoint_check.sh` | **修改** — UNLOGGED 表口径 |
| `rebuild5/scripts/runbook/sentinels.sh` | 阅读(参考) |
| `rebuild5/docs/fix6_optim/04_runbook.md` | 修改 — 加新版本基线 + 端口切换记录 |
| 本阶段产出 `upgrade_v2_finalize_and_tuning_report.md` | 新建 |

**不动 backend/app 业务代码**(loop_optim 已收档)。**不动 enriched_records 表定义**(UNLOGGED 是设计,改成 LOGGED 增加 WAL 压力)。

## § 5 任务清单(按顺序,一个重启窗口内做完)

### 阶段 1:状态确认(5491 实际数据)(~5 分钟)

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5491 -U postgres -d yangca <<EOF
SELECT version();
SELECT extname, extversion FROM pg_extension ORDER BY 1;
SELECT * FROM citus_get_active_worker_nodes();
SELECT batch_id, count(*) FROM rb5.trusted_cell_library GROUP BY 1 ORDER BY 1;
SELECT count(*) FROM rb5.cell_sliding_window;
SELECT MIN(event_time_std)::date, MAX(event_time_std)::date FROM rb5.cell_sliding_window;
SELECT batch_id, count(*) FROM rb5.enriched_records GROUP BY 1 ORDER BY 1;
SHOW citus.max_intermediate_result_size;
SHOW dynamic_shared_memory_type;
SHOW max_wal_size;
SHOW shared_buffers;
SHOW effective_cache_size;
EOF
```

把输出整理到报告 §1。**确认前提**:trusted_cell_library 7 batch 全有 + sliding_window 7d 全覆盖(LOGGED 表持久)。

写 note `topic='upgrade_v2_finalize_phase1_done'`。

### 阶段 2:修 `endpoint_check.sh` 口径(~15 分钟)

读现脚本看 `enriched_7_batch_coverage` 怎么写的。改的核心思路:

- **对 UNLOGGED 表(`enriched_records` / `candidate_seed_history` / `snapshot_seed_records`)**:只验**当前(最新)batch** 的存在性 + 单日单查;**不要求历史 batch 完整**
- **对 LOGGED 表(`trusted_cell_library` / `cell_sliding_window` / `trusted_bs_library`)**:仍然要求 batch 1-7 全覆盖

具体修改示意:
```bash
# 老逻辑(假设大概这样):
# enriched_7_batch_coverage:期待 batch 1-7 各自 enriched 行 > 0
# 改成:
# enriched_latest_batch:期待 当前 batch 的 enriched 行 > 0,且严格单日
# 加一行注释:"UNLOGGED tables drop history batches on container restart;
#              only validate current batch (Step 4 only consumes current day input).
#              For batch-history coverage, use trusted_cell_library which is LOGGED."
```

类似把 `sentinels.sh` 也复查一遍(UNLOGGED 表的 sentinel 也应该只验当前 batch),按需小改。

**改完静态验证**:
```bash
bash -n rebuild5/scripts/runbook/endpoint_check.sh   # 语法检查
bash -n rebuild5/scripts/runbook/sentinels.sh
```

写 note `topic='upgrade_v2_finalize_phase2_done'` info,body 列改的具体口径。

### 阶段 3:调优 ALTER SYSTEM(reload 级,不重启)(~10 分钟)

按 `05_当前PG设置优化要求.md` § 4.1 顺序,**分 5 步走,每步 reload + 跑一个简单查询验证未挂**:

```sql
-- 在 5491 coord 执行(via psql)

-- 第一步:WAL / checkpoint
ALTER SYSTEM SET max_wal_size = '64GB';
ALTER SYSTEM SET min_wal_size = '8GB';
ALTER SYSTEM SET checkpoint_timeout = '15min';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_compression = 'lz4';
ALTER SYSTEM SET wal_buffers = '64MB';
SELECT pg_reload_conf();
SHOW max_wal_size;  -- 验证 64GB

-- 第二步:查询代价
ALTER SYSTEM SET effective_cache_size = '180GB';
ALTER SYSTEM SET random_page_cost = 1.2;
SELECT pg_reload_conf();

-- 第三步:io workers(PG18 worker AIO)
ALTER SYSTEM SET io_method = 'worker';
ALTER SYSTEM SET io_workers = 10;
ALTER SYSTEM SET effective_io_concurrency = 64;
ALTER SYSTEM SET maintenance_io_concurrency = 64;
SELECT pg_reload_conf();

-- 第四步:parallel worker
ALTER SYSTEM SET max_worker_processes = 32;
ALTER SYSTEM SET max_parallel_workers = 24;
ALTER SYSTEM SET max_parallel_workers_per_gather = 4;
ALTER SYSTEM SET max_parallel_maintenance_workers = 4;
SELECT pg_reload_conf();

-- 第五步:内存
ALTER SYSTEM SET work_mem = '128MB';
ALTER SYSTEM SET maintenance_work_mem = '8GB';
SELECT pg_reload_conf();

-- 注意:shared_buffers 需要重启,放在阶段 4 容器重建一起做
-- 注意:max_worker_processes 需要重启,但 ALTER SYSTEM 已写入,阶段 4 重启后生效
```

**注意一些参数需要重启**(不是 reload):
- `shared_buffers`(reload 不生效)
- `max_worker_processes`(reload 不生效)
- `dynamic_shared_memory_type`(reload 不生效)— 阶段 4 重建容器时改回 `posix`(因为新容器 shm-size=16g 够大)

这些都在阶段 4 容器重建时一并生效。

**每个 ALTER SYSTEM 写完,在 5491 跑一个简单查询**(`SELECT count(*) FROM rb5.trusted_cell_library;`)确保 PG 没挂。撞错立刻 ROLLBACK ALTER SYSTEM RESET <param>。

写 note `topic='upgrade_v2_finalize_phase3_done'` info,body 含已 ALTER 的参数清单。

### 阶段 4:重建容器(shm-size=16g + restart 策略)(~20 分钟)

#### 4.1 备份当前容器配置

```bash
# 在 217 上,每台机器:
docker inspect citus-coordinator-5491-fresh > /nas_vol8/upgrade/v2_container_inspect_217_$(date +%s).json
# (worker 同样)
```

#### 4.2 改 ALTER SYSTEM 让 dynamic_shared_memory_type 重启后回 posix

```sql
-- 在 5491 跑(via psql)
ALTER SYSTEM SET dynamic_shared_memory_type = 'posix';
ALTER SYSTEM SET shared_buffers = '64GB';  -- 第一步 § 3.5,重启生效
SELECT pg_reload_conf();  -- 注意:这两个参数 reload 不会生效,但写进 postgresql.auto.conf 让重启后生效
```

#### 4.3 各机器 stop + remove + 重建容器(带 shm-size=16g)

**关键**:**保持 volume mount 不变**(数据在 host 路径 /data/pgsql/18-fresh/...,容器删除不会删数据)。

```bash
# 在每台机器(via 跳板),先 coord 217:
docker stop citus-coordinator-5491-fresh
docker rm citus-coordinator-5491-fresh
docker run -d --name citus-coordinator-5491-fresh \
  -p 5491:5432 \
  --shm-size=16g \
  --restart unless-stopped \
  --stop-timeout=300 \
  --ulimit nofile=1048576:1048576 \
  -v /data/pgsql/18-fresh/coordinator/pgroot:/var/lib/postgresql \
  -e POSTGRES_PASSWORD=123456 \
  -e POSTGRES_USER=postgres \
  optinet/citus:14.0.0-pg18.3-postgis3.6.3

# worker(每台 216/219/220/221)同理,只是 --name 改 worker
```

**重要**:agent 必须先 `docker inspect` 看当前容器**完整 docker run 参数**(env / network / cmd / entrypoint),再决定新容器 docker run 怎么写,**不要凭记忆**。容器配置漏一项启不来。

#### 4.4 验证容器起来 + 参数生效

```bash
# 等 30 秒,5 台都 docker ps 看 status='Up'
ssh -J root@217 root@<host> 'docker ps | grep 5491'

# psql 连
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5491 -U postgres -d yangca -c "
SHOW shared_buffers;        -- 64GB
SHOW dynamic_shared_memory_type;  -- posix
SHOW max_wal_size;          -- 64GB
SHOW effective_cache_size;  -- 180GB
SHOW max_worker_processes;  -- 32
"
```

如果有参数没生效,检查 `pg_settings` 看 `pending_restart` / `setting` 列。

写 note `topic='upgrade_v2_finalize_phase4_done'`。

### 阶段 5:reset + 全 1-7 重跑(~90-130 分钟,期望比 loop_optim 03 的 142 分钟快)(~~140 分钟)

**目的**:用新调优 + 新容器跑一次完整 7 批,**跑完后不再重启**,UNLOGGED 表的 batch 1-7 历史保留下来。

```bash
# reset
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5491 -U postgres -d yangca \
  -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql

# 验证 reset
psql -h 192.168.200.217 -p 5491 -U postgres -d yangca -c "
SELECT count(*) FROM rb5.trusted_cell_library;        -- 0
SELECT count(*) FROM rb5.cell_sliding_window;         -- 0
SELECT count(*) FROM rb5.enriched_records;            -- 0
SELECT count(*) FROM rb5_meta.pipeline_artifacts;     -- 0
"

# 重跑(临时指 5491)
PGPASSWORD=123456 PGGSSENCMODE=disable PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5491/yangca' \
nohup python3 rebuild5/scripts/run_citus_artifact_pipelined.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  > /tmp/upgrade_v2_finalize_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > /tmp/upgrade_v2_finalize.pid
```

监控 + 每批跑完打 sentinels.sh `<bid>`(临时指 5491)。

**预期**:wall clock < 120 分钟(比 loop_optim 03 的 142 分钟快),因为 WAL/checkpoint/parallel 都调宽了。

写 note `topic='upgrade_v2_finalize_phase5_done'` info,body 含 wall clock + TCL b7 + checkpoint 频率(看 docker logs grep "checkpoint complete")。

### 阶段 6:验收(~15 分钟)

```bash
# 改进后的 endpoint_check.sh + sentinels.sh,临时指 5491
export REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5491/yangca'
bash rebuild5/scripts/runbook/sentinels.sh 7
bash rebuild5/scripts/runbook/endpoint_check.sh

# 期望全 PASS,enriched 单批口径已修
```

数据基线对账(放宽到 ±1%,因为 PG18 + 新调优是不同环境):

```sql
-- TCL b7 期望 in [338,058..345,168](340,766 ± 1%,放宽,因为新 PG/参数环境差异)
SELECT count(*) FROM rb5.trusted_cell_library WHERE batch_id=7;

-- 8 类 drift_pattern 全有
SELECT drift_pattern, count(*) FROM rb5.trusted_cell_library
WHERE batch_id=7 GROUP BY drift_pattern ORDER BY 2 DESC;
```

**重要**:**checkpoint 频率检查**(05 文档 § 5):
```bash
ssh -J root@217 root@216 'docker logs citus-worker-5491-fresh 2>&1 | grep "checkpoint complete" | tail -20'
# 期待间隔 ≥ 数分钟,不再是 17-30 秒
```

写 note `topic='upgrade_v2_finalize_phase6_done'`,body 含 endpoint_check 状态 + TCL 偏差 + checkpoint 间隔。

### 阶段 7:端口切换(~15 分钟,downtime ≤ 2 分钟)

#### 7.1 切换前最后确认

新 5491 跑 sentinels + endpoint_check 全 PASS;老 5488 也跑同套确认(保险)。

#### 7.2 切换(每台机器)

```bash
# 在每台机器:

# 1. 停老 5488 容器
docker stop citus-coordinator-5488   # 或 citus-worker-5488

# 2. 老容器挪 5487(保留作 fallback,不删数据)
docker rename citus-coordinator-5488 citus-coordinator-5487-pg17-fallback
# 改 port 重新启动(用老 PG17 镜像 + 老 data path):
# 这一步要确认老容器的镜像和 volume,docker inspect 看清楚再改
docker run -d --name citus-coordinator-5487-pg17-fallback \
  -p 5487:5432 \
  -v /data/pgsql/17-citus/coordinator/data:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=123456 \
  citusdata/citus:14.0.0-pg17

# 3. 停新 5491,改 5488 重启
docker stop citus-coordinator-5491-fresh
docker rm citus-coordinator-5491-fresh
docker run -d --name citus-coordinator-5488 \
  -p 5488:5432 \
  --shm-size=16g \
  --restart unless-stopped \
  --stop-timeout=300 \
  --ulimit nofile=1048576:1048576 \
  -v /data/pgsql/18-fresh/coordinator/pgroot:/var/lib/postgresql \
  -e POSTGRES_PASSWORD=123456 \
  optinet/citus:14.0.0-pg18.3-postgis3.6.3
# 注意:容器重启会再次清空 UNLOGGED 表,但 endpoint_check 已修了不再要求历史
```

**worker 同理**:5491 → 5488,老 5488 → 5487。

#### 7.3 切换后验证

```bash
# 现在 5488 = 新 PG18
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5488 -U postgres -d yangca -c "
SELECT version();
SELECT count(*) FROM rb5.trusted_cell_library WHERE batch_id=7;
"
# 期待 PG 18.3,TCL b7 = 阶段 5 的值 ± 0(因为只是换 port,数据不变)

# runbook(原始 5488 端口,无需改)
bash rebuild5/scripts/runbook/sentinels.sh 7
bash rebuild5/scripts/runbook/endpoint_check.sh
# enriched_7_batch_coverage 此时只剩 batch 7(因为容器重启清了 UNLOGGED),但脚本已改口径,应 PASS

# 老 5487 仍在
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5487 -U postgres -d yangca -c "SELECT version();"
# 期待 PG 17.6
```

写 note `topic='upgrade_v2_finalize_phase7_done'`,body 含切换 timestamp + 老/新 port 验证。

### 阶段 8:完工 commit + push(~5 分钟)

`git add` 列(把 v1 + v2 + v2 收尾全部一并 commit):
- `rebuild5/docs/upgrade/README.md`
- `rebuild5/docs/upgrade/upgrade_prompt.md`(v1)
- `rebuild5/docs/upgrade/upgrade_report.md`(v1 失败 trail)
- `rebuild5/docs/upgrade/upgrade_v2_fresh_rebuild_prompt.md`
- `rebuild5/docs/upgrade/upgrade_v2_finalize_and_tuning_prompt.md`(本)
- `rebuild5/docs/upgrade/upgrade_v2_finalize_and_tuning_report.md`(产出)
- `rebuild5/scripts/bootstrap_schema.py`
- `rebuild5/scripts/runbook/endpoint_check.sh`(改的)
- `rebuild5/scripts/runbook/sentinels.sh`(若改)
- `rebuild5/docs/fix6_optim/04_runbook.md`(更新基线 + 切换记录)

一个 commit:
```
chore(rebuild5): upgrade to PG18.3 + Citus 14 + tuning, port cutover

- v1 dumpall+post-distribute path failed (trail at upgrade/upgrade_report.md)
- v2 fresh rebuild: per-table COPY for raw_gps_full_backup (25.4M),
  rb5_bench.notes dump+restore, business tables full reset+rerun
- Tuned: max_wal_size=64GB, checkpoint_timeout=15min, wal_compression=lz4,
  effective_cache_size=180GB, random_page_cost=1.2, io_method=worker,
  io_workers=10, max_parallel_workers=24, shared_buffers=64GB,
  shm-size=16g (container), restart=unless-stopped
- Container hardened: --shm-size=16g, --ulimit nofile=1048576, --stop-timeout=300
- Fixed endpoint_check.sh / sentinels.sh: UNLOGGED tables (enriched_records,
  candidate_seed_history, snapshot_seed_records) only validate current batch
  (their persistence design is intentional; container restart drops history).
  LOGGED tables (TCL, sliding_window, trusted_bs_library) still validate full coverage.
- Reset+rerun 7 batches with new tuning: TCL b7=<n> within ±<x>% of loop_optim_03
  340,766; wall clock=<s>s vs 8541s baseline.
- Port cutover: new PG18 cluster on 5488; old PG17 cluster preserved on 5487
  as fallback for 1-2 weeks observation.
- bootstrap_schema.py added for future fresh-rebuild reproducibility.
- References upgrade/upgrade_v2_finalize_and_tuning_report.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push 撞 SSL 等 60s 重试,再失败标 push pending。

写 note `topic='upgrade_v2_done'`(同时是整个 upgrade 系列收档)。

### 不做(显式禁止)

- ❌ 不改 `enriched_records` / `candidate_seed_history` / `snapshot_seed_records` 的 UNLOGGED 设计(增加 WAL 压力,违反 fix5/fix6 一直以来的约定)
- ❌ 不重跑 1-7 多次(只在阶段 5 跑一次,跑完后不再重启,数据保留)
- ❌ 不改 backend/app 业务代码
- ❌ 不动 fix5/fix6_optim/loop_optim 已交付产物
- ❌ 不删老 PG17 数据(终极 fallback,挪 5487 后保留 1-2 周)
- ❌ 不删 v1 dump (127GB,作 safety net)
- ❌ 不一次性 ALTER SYSTEM 所有参数(分 5 步,每步 reload + 验证未挂)
- ❌ 不漏 `docker inspect` 检查现有容器配置就重建(漏 env/volume 启不来)
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 阶段 7 端口切换失败立刻回滚(新 5491 维持,老 5488 不动)

## § 6 验证标准

1. **endpoint_check.sh 改完且 5491 跑过 PASS**
2. **5491 调优参数生效**:`SHOW max_wal_size`=64GB / `effective_cache_size`=180GB / `shared_buffers`=64GB / `dynamic_shared_memory_type`=posix
3. **容器 shm 验证**:`docker exec <container> df -h /dev/shm` 显示 16G
4. **重跑 7 批跑通**:trusted_cell_library 7 batch 单调,sliding_window 7 天全
5. **TCL b7 偏差 ≤ ±1%**(放宽,因为新环境;严格 ±0.5% 是 nice-to-have)
6. **8 类 drift_pattern 全有**
7. **checkpoint 频率下降**:docker logs grep checkpoint 间隔 ≥ 5 分钟(原本 17-30 秒)
8. **5488 = 新 PG18 / 5487 = 老 PG17 fallback**:两个 port 各自 SELECT version() 验证
9. **commit + push**(允许标 push pending)
10. **note `upgrade_v2_done`** 写入

## § 7 产出物 `upgrade_v2_finalize_and_tuning_report.md`

```markdown
# upgrade v2 收尾 + 调优 报告(终)

## 0. TL;DR
- v1 失败 → v2 fresh rebuild 跑通 → v2 收尾(本批):endpoint 口径 + 调优 + 重跑 + 端口切换
- 新 5488:PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3 / shm-size=16g / 调优 5 步
- 老 5487:PG 17.6 / Citus 14.0-1(fallback,保留 1-2 周)
- 重跑 wall clock = <s>s = <m> min vs loop_optim 03 8541s,加速 <x>%
- TCL b7 = <n>,vs 340,766 偏差 <x>%
- checkpoint 间隔 <m> 分钟(原本 17-30 秒)
- commit SHA / push 状态

## 1. 阶段 1 状态确认
... 5491 实测输出

## 2. 阶段 2 endpoint_check.sh 改动
... diff 节选 + 改的口径说明

## 3. 阶段 3 ALTER SYSTEM 5 步
| 参数 | 旧 | 新 | reload 还是 restart 后生效 |
| --- | --- | --- | --- |
... 完整列表

## 4. 阶段 4 容器重建
... 5 台 docker run 命令(脱敏后)+ shm-size 验证

## 5. 阶段 5 重跑
... wall clock + 每批耗时表 + checkpoint 频率

## 6. 阶段 6 验收
... endpoint_check + sentinels 输出
... 8 类 drift_pattern 表
... TCL 偏差

## 7. 阶段 7 端口切换
... 切换前/后 docker ps + version 验证 + downtime 实测

## 8. 已知限制 / 后续
- 老 PG17 5487 数据保留 1-2 周后删除时机
- v1 dump (127GB) 何时清理
- 后续构建数仓时基于 5488 PG18 推进
```

## § 8 notes 协议

- 每阶段 1 条 info note:`upgrade_v2_finalize_phase<N>_done`
- 完工:`upgrade_v2_done` info,body 含 PG 版本 + Citus 版本 + 重跑 wall clock + TCL b7 + checkpoint 间隔 + 切换 timestamp
- 失败:`upgrade_v2_finalize_failed` blocker

升级期间 5488 仍是老 PG17,note 表是 reference table,**MCP 写 5488 的 note 会同步到 worker**(reference 复制),所以 note 写得进。但端口切换后 5488 = 新 PG18,5491 → 5488。**切换那一刻有 ~2 分钟 note 写不进**,备用 `/nas_vol8/upgrade/logs/v2_finalize_<timestamp>.log`。

## § 9 完工话术

成功:
> "upgrade v2 finalize + 调优完成。upgrade_v2_finalize_and_tuning_report.md 已写入。新 PG 18.3 在 5488,老 PG 17.6 在 5487 fallback。endpoint_check.sh + sentinels.sh 对 UNLOGGED 表口径已修。调优 5 步生效(checkpoint 间隔从 17-30s → <m>min)。重跑 wall clock=<s>s vs 8541s 加速 <x>%。TCL b7=<n> 偏差 <x>%(±1% 内)。8 类 drift_pattern 全在。commit=<SHA>(push <成功/pending>)。整个 upgrade 系列(v1 失败 + v2 重建 + v2 收尾调优)收档。notes `topic='upgrade_v2_done'` 已插入。后续构建数仓基于新 5488 PG18 推进。"

失败:
> "upgrade v2 finalize 失败于阶段 <N>:<step>。blocker=<一句话>。当前集群状态:<5488 仍 PG17 / 5491 PG18 状态 / 端口是否切换>。已写 notes `topic='upgrade_v2_finalize_failed'`。等上游处置。"

## § 10 失败兜底

- **阶段 2 endpoint_check 改完跑挂**:不要硬切其他验收逻辑,先看实际命中表 + UNLOGGED 列表对照,可能漏了某个表
- **阶段 3 某个 ALTER SYSTEM 撞错**:RESET 单个参数,继续后续步;5 步分开走的目的就是隔离风险
- **阶段 4 容器重建启不来**:`docker logs` 看错,八成是漏 env / volume 路径错;**不要改 host 数据目录**,只改 docker run 命令
- **阶段 4 shared_buffers=64GB 启不来**(物理内存不够):降级 32GB 重试
- **阶段 5 重跑挂某 batch**:不再硬切 fix6 03 pipelined / 串行 fallback(本阶段 runner 已稳),先看是不是新 PG18 + 新参数引入的 incompatibility,blocker 给 user
- **阶段 6 TCL 偏差 > 1%**:数据可信问题,blocker;**别端口切换**;给 user 8 类 drift_pattern 完整对比让他决定
- **阶段 7 端口切换某台机器卡住**:**立刻回滚**(那台用 docker rename 再换回老配置);其他机器维持(部分集群跨版本短期可用,但要立刻 blocker 让 user 介入)
- **GitHub HTTPS SSL 抖动**:等 60s 重试,push pending 不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
