# OptiNet rebuild5 / upgrade v2 — 重开 PG18 集群 + reset 重跑(选项 C)(agent 新实例对话)

## § 1 元目标

**v1 失败教训**:`pg_dumpall` 整库 + 后置 `create_distributed_table` 在 PG17→PG18 + Citus 跨集群是已知陷阱(部分 distributed 表数据不可见),v2 **不走 dumpall 路径**。

**v2 路径**(用户拍板的"完整重建"):

1. 5 台机器部署 PG18 + Citus 14 + PostGIS 全新集群(独立 port 5491,与 5488 共存)
2. 跑 backend schema.py **空建** rb5/rb5_meta/rb5_stage 全部表 + Citus distributed metadata
3. 只迁移 **2 个最小必需** dataset:`rb5.raw_gps_full_backup`(Step1 源,25.4M 行)+ `rb5_bench.notes`(历史 trail,145 行)
4. reset 跑全 7 批 `run_citus_artifact_pipelined.py`,验数据基线 TCL b7 ≈ 340,766 ± 0.5%
5. 调优 + 端口切换(老 5488 挪 5487 保留 / 新 5491 升 5488)
6. 验收 + 老集群保留 1-2 周观察期再删

**user 长期目标**:升级后要在新集群上**构建数仓**,所以版本 / 配置 / runbook 要做对。

## § 2 上下文启动顺序

按序读完直接开干:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/upgrade/README.md` + `upgrade_prompt.md`(v1)+ `upgrade_report.md`(v1 失败 trail)
3. `rebuild5/docs/fix6_optim/_prompt_template.md` § 11/§ 12
4. `rebuild5/docs/loop_optim/03_rerun_report.md` —— 数据基线(TCL b7=340,766 / 7 批 wall clock 8541s)
5. `rebuild5/docs/fix6_optim/04_runbook.md` —— 验收命令
6. `rebuild5/scripts/run_citus_artifact_pipelined.py` —— 主 runner
7. `rebuild5/backend/app/etl/schema.py` / `enrichment/schema.py` / `maintenance/schema.py` —— 空建用
8. v1 已交付的 spike 镜像清单(见 `rb5_bench.notes` topic='upgrade_phase1_done' / 'phase2_done')
9. 本 prompt

读完直接开干。

## § 3 环境硬信息

### 集群拓扑

5 台机器,**root / 111111 SSH**:
- coordinator + 跳板:`192.168.200.217`
- workers:`192.168.200.216` / `219` / `220` / `221`
- 每台:20 物理 / 40 逻辑核 / 251GB / Docker 跑 PG

### NAS 共享盘

`/nas_vol8`(5 台都挂载,~65T 可用)

**v1 已落地的资源**(直接复用):
- 镜像:`/nas_vol8/upgrade/packages/images/optinet_citus_14.0.1_pg18.3_postgis3.6.3_20260426_105314.tar.gz`(~已 spike 验证 PG 18.3 + Citus 14.0-1 + PostGIS 3.6.3 + pg_stat_statements)
- v1 dump(127GB)在 `/nas_vol8/upgrade/backups/dumps/yangca_full_20260426_105359.sql` —— **不用,v2 不走 dumpall**,但保留作 safety net
- v1 PG18 残留数据 `/data/pgsql/18-citus/*` —— **删掉腾空间**(v1 失败的旧数据)

### v2 新集群目标

- **5491 port**(临时,与生产 5488 共存,验收后切到 5488)
- 装在 `/data/pgsql/18-fresh/coordinator/pgroot`(coord)/ `/data/pgsql/18-fresh/worker/pgroot`(worker)的独立路径,与 v1 残留隔离
- 容器命名:`citus-coordinator-5491-fresh` / `citus-worker-5491-fresh`(与现有 `-5488` 隔离)

### 当前生产连接(只读用,不动)

- **生产 PG17**:`postgres://postgres:123456@192.168.200.217:5488/yangca` MCP `mcp__PG_Citus__execute_sql`
- **PG17 5433 旧基线**:不动
- v2 新集群将临时在 5491 跑,验收后切 5488

### 数据基线(loop_optim 03 后)

- `rb5.raw_gps_full_backup`:25,442,069 行,dist=did,Step1 装载源
- `rb5_bench.notes`:145 行 / 112KB / reference table / 历史决策 trail
- `rb5.trusted_cell_library` batch 7 = 340,766(reset 重跑后期望复现 ±0.5%)
- 其他 rb5.* 业务表全部可扔(reset 重跑能复现)

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `upgrade/upgrade_report.md` | 阅读 | v1 失败原因 + 镜像清单 |
| `loop_optim/03_rerun_report.md` | 阅读 | 数据基线 |
| `fix6_optim/04_runbook.md` | 修改(收尾)| 加新集群命令(如 port 切换前先指向 5491) |
| `rebuild5/scripts/runbook/run_full_artifact_pipelined.sh` | 可能修改(端口切换前)| 临时指 5491,切换后改回 5488 |
| 本阶段产出 `upgrade_v2_report.md` | 新建 | § 7 结构 |

**不动 backend/app 任何业务代码**(loop_optim 已收档)。

## § 5 任务清单(8 子阶段)

### 阶段 0:确认就绪 + 清理 v1 残留(~15 分钟)

```bash
# 在 217 上(via SSH 跳板,每台都执行)
# 1. 验证 v1 spike 镜像存在
ls -lh /nas_vol8/upgrade/packages/images/

# 2. 删 v1 PG18 残留(v1 失败的旧数据,占 ~127GB+,腾空间)
ssh root@192.168.200.<host> '
  # 先确认没 PG18 容器在跑
  docker ps -a | grep -E "pg18|fresh"
  # 然后删数据
  rm -rf /data/pgsql/18-citus/coordinator/pgroot
  rm -rf /data/pgsql/18-citus/worker/pgroot
'

# 3. 各机器磁盘空间检查
ssh root@192.168.200.<host> 'df -h /data /nas_vol8'

# 4. 确认 /nas_vol8/upgrade/backups/dumps/yangca_full_20260426_105359.sql 仍在(v1 dump 作 safety net)
```

写 note `topic='upgrade_v2_phase0_done'` info,body 含磁盘可用空间。

### 阶段 1:5 台部署 PG18 + Citus 集群(独立 port 5491)(~30 分钟)

```bash
# 在每台机器(via 跳板):
# 1. load 镜像
docker load -i /nas_vol8/upgrade/packages/images/optinet_citus_14.0.1_pg18.3_postgis3.6.3_*.tar.gz

# 2. 起容器(coord 在 217,worker 在 216/219/220/221)
# coordinator 217:
docker run -d --name citus-coordinator-5491-fresh \
  -p 5491:5432 \
  -v /data/pgsql/18-fresh/coordinator/pgroot:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=123456 \
  -e POSTGRES_USER=postgres \
  optinet/citus:14.0.0-pg18.3-postgis3.6.3

# worker(每台):
docker run -d --name citus-worker-5491-fresh \
  -p 5491:5432 \
  -v /data/pgsql/18-fresh/worker/pgroot:/var/lib/postgresql/data \
  -e POSTGRES_PASSWORD=123456 \
  -e POSTGRES_USER=postgres \
  optinet/citus:14.0.0-pg18.3-postgis3.6.3

# 3. 等所有 5 台启动完毕(pg_isready),然后初始化 Citus 拓扑
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5491 -U postgres -d postgres <<EOF
CREATE DATABASE yangca;
\c yangca
CREATE EXTENSION citus;
CREATE EXTENSION postgis;
CREATE EXTENSION pg_stat_statements;
SELECT * FROM citus_set_coordinator_host('192.168.200.217', 5491);
SELECT citus_add_node('192.168.200.216', 5491);
SELECT citus_add_node('192.168.200.219', 5491);
SELECT citus_add_node('192.168.200.220', 5491);
SELECT citus_add_node('192.168.200.221', 5491);
SELECT * FROM citus_get_active_worker_nodes();  -- 期待 4 worker
EOF
```

写 note `topic='upgrade_v2_phase1_done'`。

### 阶段 2:schema 空建(~15 分钟)

跑 backend schema 模块,在新集群空建所有 rb5.* / rb5_meta.* / rb5_stage 表 + Citus distributed metadata。

```bash
# 设环境指向 5491
export REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5491/yangca'
export PGOPTIONS='-c auto_explain.log_analyze=off'

# 调用 schema 创建函数。注意:agent 要 grep backend 找到 schema 入口,
# 通常是各 schema.py 的模块级函数(create_etl_schema / create_enrichment_schema / create_maintenance_schema)
# 或者 main 入口里有统一调用
python3 -c "
from rebuild5.backend.app.etl import schema as etl_schema
from rebuild5.backend.app.enrichment import schema as enr_schema
from rebuild5.backend.app.maintenance import schema as mnt_schema
etl_schema.create_etl_schema()
enr_schema.create_enrichment_schema()
mnt_schema.create_maintenance_schema()
"

# 验证
psql ... -c "SELECT count(*) FROM pg_dist_partition;"   -- 期待与生产一致 (~59 但允许差异,因为 rb5_stage 表是 runner 时建)
psql ... -c "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('rb5','rb5_meta');"
```

如果 schema.py 没有"全部一键建"的入口函数,agent 自己写一个 `bootstrap_schema.py` script(放 `rebuild5/scripts/`),里面把各模块的 create 函数串起来调一遍,**这个 script 会进 commit**(对未来 reset 重建有用)。

写 note `topic='upgrade_v2_phase2_done'`,body 含 distributed/reference table 数。

### 阶段 3:关键数据迁移(~30-60 分钟)

#### 5.3.1 raw_gps_full_backup(25.4M 行)

**不用 dumpall**,用 per-table COPY:

```bash
# 老 5488 → NAS(在 217 容器内执行,-z gzip 压缩):
docker exec citus-coordinator-5488 \
  psql -U postgres -d yangca -c \
  "\\COPY (SELECT * FROM rb5.raw_gps_full_backup) TO PROGRAM 'gzip > /var/lib/postgresql/data/pgdata_share/raw_gps_full_backup.csv.gz' WITH CSV"

# 或者 pipe 到 NAS(挂载需要):
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5488 -U postgres -d yangca \
  -c "\\COPY (SELECT * FROM rb5.raw_gps_full_backup) TO STDOUT WITH CSV" \
  | gzip > /nas_vol8/upgrade/migrate/raw_gps_full_backup.csv.gz

# 新 5491 → restore(先 CREATE TABLE + create_distributed_table 在 phase 2 已做):
gunzip -c /nas_vol8/upgrade/migrate/raw_gps_full_backup.csv.gz | \
  PGPASSWORD=123456 psql -h 192.168.200.217 -p 5491 -U postgres -d yangca \
  -c "\\COPY rb5.raw_gps_full_backup FROM STDIN WITH CSV"

# 验证:
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5491 -U postgres -d yangca \
  -c "SELECT count(*) FROM rb5.raw_gps_full_backup;"
# 期待 25,442,069
```

#### 5.3.2 rb5_bench.notes(145 行)

```bash
# 老 5488 dump:
PGPASSWORD=123456 pg_dump -h 192.168.200.217 -p 5488 -U postgres -d yangca \
  --table=rb5_bench.notes --data-only --column-inserts \
  > /nas_vol8/upgrade/migrate/notes.sql

# 新 5491 灌(先确认 phase 2 已建 rb5_bench.notes 作 reference table):
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5491 -U postgres -d yangca \
  -f /nas_vol8/upgrade/migrate/notes.sql

# 验证:
psql ... -c "SELECT count(*) FROM rb5_bench.notes;"  -- 期待 145+
```

写 note `topic='upgrade_v2_phase3_done'`,body 含两表迁移行数。

### 阶段 4:reset + 全 7 批重跑(~140 分钟)

新集群 reset(虽然空,但 reset SQL 会幂等地清空 + 准备 schema):

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5491 -U postgres -d yangca \
  -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

启动 artifact pipelined runner(临时指向 5491):

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5491/yangca' \
nohup python3 rebuild5/scripts/run_citus_artifact_pipelined.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  > /tmp/upgrade_v2_rerun_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > /tmp/upgrade_v2_rerun.pid
```

监控 + 每批哨兵,**沿用 loop_optim 03 同套验收逻辑**(reset_step1_to_step5_for_full_rerun_v3.sql + run_citus_artifact_pipelined + sentinels.sh + endpoint_check.sh,但临时改 -p 5491)。

写 note `topic='upgrade_v2_phase4_done'`,body 含 wall_clock + TCL b7。

### 阶段 5:验收(~30 分钟)

```sql
-- 基础
SELECT version();
SELECT extname, extversion FROM pg_extension ORDER BY 1;
SELECT * FROM citus_get_active_worker_nodes();

-- 数据基线对账(关键):
SELECT count(*) FROM rb5.trusted_cell_library WHERE batch_id=7;
-- 期待 in [338,062 .. 343,470](340,766 ± 0.5%)

SELECT count(*) FROM rb5.cell_sliding_window;
SELECT MIN(event_time_std)::date, MAX(event_time_std)::date FROM rb5.cell_sliding_window;

-- 8 类 drift_pattern 全在
SELECT drift_pattern, count(*) FROM rb5.trusted_cell_library
WHERE batch_id=7 GROUP BY drift_pattern;
```

跑 runbook(临时指 5491):
```bash
# 改环境:
export REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5491/yangca'
bash rebuild5/scripts/runbook/sentinels.sh 7
bash rebuild5/scripts/runbook/endpoint_check.sh
# 期待全 PASS
```

任意挂红 → blocker 退到 spike 阶段重排查;**不要硬切端口**。

写 note `topic='upgrade_v2_phase5_done'`,body 含 TCL b7 偏差。

### 阶段 6:调优(~10 分钟)

```sql
-- 在新 5491 上(coord)
ALTER SYSTEM SET citus.max_intermediate_result_size = '16GB';
ALTER SYSTEM SET auto_explain.log_analyze = off;  -- 防 fix5 D 撞过的 INSERT...SELECT 问题
SELECT pg_reload_conf();

-- 验证
SHOW citus.max_intermediate_result_size;
SHOW auto_explain.log_analyze;
```

agent 自主决定其他 PG18-specific 调优(如果 spike 期间发现差异),但**不要扩大改动**。

### 阶段 7:端口切换 + 旧集群保留观察(~15 分钟)

#### 5.7.1 切换前最后确认

```bash
# 新 5491 跑 sentinels + endpoint_check 全 PASS
# 老 5488 跑同一套也全 PASS(保险)
```

#### 5.7.2 端口切换(短 downtime ~2 分钟)

```bash
# 在每台机器:
# 1. 停老 5488 容器
docker stop citus-coordinator-5488  # 或 citus-worker-5488

# 2. 把老容器 port 改成 5487(保留作 fallback,不删数据)
docker rename citus-coordinator-5488 citus-coordinator-5487-pg17-fallback
docker run -d --name citus-coordinator-5487-pg17-fallback \
  -p 5487:5432 ... (用老 PG17 镜像 + 老 data path)

# 3. 把新 5491 容器停掉,改成 5488 重启
docker stop citus-coordinator-5491-fresh
docker rm citus-coordinator-5491-fresh
docker run -d --name citus-coordinator-5488 \
  -p 5488:5432 \
  -v /data/pgsql/18-fresh/coordinator/pgroot:/var/lib/postgresql/data \
  ...

# (worker 同理:5491 ↔ 5488 / 老的挪 5487)
```

#### 5.7.3 切换后验证

```bash
# 现在 5488 = 新 PG18 集群
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5488 -U postgres -d yangca -c "SELECT version();"
# 期待 PG 18.3

# runbook(原始 5488 端口,无需改)
bash rebuild5/scripts/runbook/sentinels.sh 7
bash rebuild5/scripts/runbook/endpoint_check.sh

# 老集群 5487 仍在(fallback)
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5487 -U postgres -d yangca -c "SELECT version();"
# 期待 PG 17.6
```

写 note `topic='upgrade_v2_phase7_done'`,body 含切换时间戳 + 老集群挪到 5487 的 trail。

### 阶段 8:完工 commit + push

`git add` 列:
- `rebuild5/docs/upgrade/upgrade_v2_fresh_rebuild_prompt.md`(本 prompt)
- `rebuild5/docs/upgrade/upgrade_v2_report.md`(产出)
- `rebuild5/docs/upgrade/README.md`(状态更新:v2 完成)
- `rebuild5/docs/upgrade/upgrade_report.md`(v1 失败 trail,如果阶段 0 时 commit)
- `rebuild5/scripts/bootstrap_schema.py`(若新建)
- `rebuild5/docs/fix6_optim/04_runbook.md`(更新基线表 + 新版本号)

一个 commit:
```
chore(rebuild5): upgrade v2 fresh rebuild PG18.3 + Citus 14.0-1 + PostGIS 3.6.3

- v1 dumpall+post-distribute path failed; v2 uses fresh schema bootstrap +
  per-table COPY for raw_gps_full_backup (25.4M rows) + dump+restore for
  rb5_bench.notes (145 rows); business tables fully reset+rerun via
  run_citus_artifact_pipelined
- New cluster on port 5488 (PG18.3); old PG17 cluster moved to 5487 as fallback
- Reset+rerun 7 batches: TCL b7=<n> within ±<x>% of pre-upgrade 340,766
- Tunables applied: citus.max_intermediate_result_size=16GB,
  auto_explain.log_analyze=off
- References upgrade/upgrade_v2_report.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push 撞 SSL 等 60s 重试,再失败标 push pending。

写 note `topic='upgrade_v2_done'`,用 § 9 完工话术汇报。

## § 6 验证标准

任务 done 的硬标准:

1. **新集群 5 台**:每台 SSH 进去 `docker ps | grep 5488` 显示新 PG18 容器
2. **PG 版本**:`SELECT version()` = PG 18.x
3. **Citus 健康**:`citus_get_active_worker_nodes()` 返回 4 worker
4. **扩展齐全**:citus / postgis / pg_stat_statements / auto_explain
5. **数据基线**:`rb5.trusted_cell_library WHERE batch_id=7` 在 340,766 ± 0.5% = [338,062..343,470]
6. **8 类 drift_pattern 全有**(stable / dual_cluster / uncertain / large_coverage / migration / oversize_single / insufficient / collision)
7. **runbook sentinels.sh 7 + endpoint_check.sh 全 PASS**
8. **老 PG17 集群 5487 仍可用**(fallback,跑 `SELECT version()` 显示 17.6)
9. **commit + push**(允许标 push pending)
10. **note `upgrade_v2_done`** 写入,body 含 PG 版本 + Citus 版本 + TCL b7 + 切换 timestamp

## § 7 产出物 `upgrade_v2_report.md`

```markdown
# upgrade v2 — 重开 PG18 集群 + reset 重跑报告

## 0. TL;DR
- 升级前/老:PG 17.6 / Citus 14.0-1 / PostGIS 3.6.3(已挪到 5487 fallback)
- 升级后/新:PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3(在 5488)
- 路径:v2 fresh rebuild(避开 v1 dumpall 陷阱)
- 数据基线:TCL b7 = <n>(vs upgrade 前 340,766 偏差 <x>%)
- runbook sentinels + endpoint_check 全 PASS
- 端口切换时间:<timestamp>;切换 downtime:<m> 分钟
- 老集群保留:port 5487 + data path /data/pgsql/17-citus-pg17-fallback/(暂留 1-2 周)
- commit SHA:<sha>;push 状态:<status>

## 1. v1 失败 trail(回顾)
- v1 用 pg_dumpall 整库 + 后置 create_distributed_table,Citus 跨大版本踩 distributed metadata 重建陷阱
- v1 残留已清(/data/pgsql/18-citus/* 删除)+ v1 dump (127GB) 仍在 NAS 作 safety net

## 2. 新集群部署(阶段 1)
- 镜像:optinet/citus:14.0.0-pg18.3-postgis3.6.3(v1 spike 镜像复用)
- 5 台机器 docker run + 拓扑注册
- citus_add_node 4 worker 输出

## 3. schema 空建(阶段 2)
- bootstrap_schema.py 调用链
- distributed table 数 + reference table 数

## 4. 数据迁移(阶段 3)
- raw_gps_full_backup:25.4M 行 / per-table COPY / 耗时 <m> 分钟
- rb5_bench.notes:145 行 / dump+restore

## 5. 重跑(阶段 4)
- artifact pipelined wall clock = <s>s = <m> min
- 与 loop_optim 03 (8541s) 对比:<快/慢> <x>%
- 每批 4 哨兵全 PASS,trail 列表

## 6. 验收(阶段 5)
- 8 类 drift_pattern 分布表
- TCL b7 偏差 <x>% vs 升级前 340,766
- sentinels.sh 7 输出
- endpoint_check.sh 输出

## 7. 调优(阶段 6)
- ALTER SYSTEM 列表 + SHOW 验证

## 8. 端口切换(阶段 7)
- 切换前/后 docker ps 节选
- 5488 验证 PG18 / 5487 验证 PG17
- 切换 downtime 实测

## 9. 已知限制 / 给后续构建数仓的建议
- 老 PG17 集群保留 1-2 周后删除时机
- v1 dump (127GB) 何时清理
- 后续构建数仓时,新集群 schema/tablespace 规划建议(基于本次 fresh rebuild 经验)
```

## § 8 notes 协议

每阶段一条 info note:`upgrade_v2_phase<N>_done`,body 含关键数字。
完工:`upgrade_v2_done` info,body 含 PG/Citus 版本 + TCL b7 + 端口切换时间戳。
失败:`upgrade_v2_failed` blocker,body 含失败阶段 + 当前集群状态(新集群是否能用 / 老集群是否仍 5488)。

**重要**:阶段 7 端口切换期间数据库会短暂停服,note 写不进。备用:写 `/nas_vol8/upgrade/logs/v2_<timestamp>.log` 文件,事后补 notes。

## § 9 完工话术

成功:
> "upgrade v2 完成。upgrade_v2_report.md 已写入。新集群 PG 18.3 + Citus 14.0-1 + PostGIS 3.6.3 在 5488。reset 重跑全 7 批 TCL b7=<n>,vs 升级前 340,766 偏差 <x>%。runbook 全 PASS。老 PG17 集群挪到 5487 作 fallback,/data/pgsql/17-* 数据保留 1-2 周观察期。端口切换 downtime <m> 分钟。commit=<SHA>(push <成功/pending>)。notes `topic='upgrade_v2_done'` 已插入。后续构建数仓可基于新集群推进。"

失败:
> "upgrade v2 失败于阶段 <N>:<step>。blocker=<一句话>。当前集群状态:<新集群 5491 部分跑通 / 端口未切换 / 老 PG17 5488 仍承生产>。已写 notes `topic='upgrade_v2_failed'`。等上游处置。"

## § 10 失败兜底

- **阶段 1 部署失败**:diagnose docker / network / port 冲突,如果 5491 已被占用换 5492 等
- **阶段 2 schema 空建失败**:可能 backend schema.py 没"全部一键建"入口 → agent 自己写 bootstrap_schema.py(进 commit)
- **阶段 3 raw_gps_full_backup COPY 失败**:中途断 → 用 `\COPY ... WHERE event_time_std BETWEEN day..day+1` 分天导出,逐天灌
- **阶段 4 重跑撞 PG18-specific bug**(GUC 名变 / 函数语义变):agent 修 ≤ 30 行(本质是兼容补丁),超过停 + blocker
- **阶段 5 数据基线偏差 > 0.5%**:**这是数据可信度危机**,blocker 立刻停,完整 8 类 drift_pattern 对比给 user 决定是否接受更宽松阈值
- **阶段 7 端口切换失败**:**立刻回滚**(新 5491 维持,老 5488 不动),业务 0 影响;blocker note + 让 user 决定下一步
- **GitHub HTTPS SSL 抖动**(push):等 60s 重试,push pending 不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
- **绝不**走 dumpall + 后置 distribute(v1 失败模式)
- **绝不**删除老 PG17 数据(终极 fallback)

---

## § 11 关键技术 prime(避免再踩坑)

### Citus 跨集群迁移的正确姿势

- ✅ **先在新集群 create_distributed_table(空表)再 COPY 数据进来** —— Citus 自动路由到 shard
- ❌ **不要 dumpall 灌进去再 create_distributed_table** —— v1 失败模式

### per-table COPY 的 chunk 策略

raw_gps_full_backup 25M 行,直接一次 COPY 可能内存爆 / 超时。如果撞:
- 按 day 切:`\COPY (SELECT * FROM rb5.raw_gps_full_backup WHERE event_time_std::date = '2025-12-01') TO ...`
- 按 dev_id 哈希切(不太实用)

### Citus 14 + PG 18 兼容性已知约束

- v1 spike 已验证:Citus 14.0-1 在 PG 18.3 跑得通(基本 SQL + create_distributed_table + insert/count)
- 但**复杂 query**(distributed JOIN + advisory lock)不一定 0 风险,阶段 4 重跑是真正验证

### 端口切换 atomic 操作

不要"老停先,新停后,启新"留窗口。理想:
- 新集群在 5491 完全跑通
- 老停 5488 → 立刻新启 5488(同时老挪 5487 启动)
- 用 docker stop + docker rename + docker run 串起来,downtime ≤ 2 分钟
