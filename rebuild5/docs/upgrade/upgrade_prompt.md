# OptiNet rebuild5 / PG + Citus + 扩展 升级到最新版(agent 新实例对话)

## § 1 元目标

把 192.168.200.217 集群(1 coordinator + 4 worker)的:

1. **PostgreSQL 升级到当前最新稳定大版本**(用户 3 周前以为升到 17 实际可能装的不是最新,**第一步实测确认 `SELECT version()`**,然后定目标版本 = 当前实测发布的最新稳定大版本,通常是 PG 18.x)
2. **Citus 升级到与新 PG 兼容的最新版**(查 Citus 官方版本兼容矩阵)
3. **扩展全装齐**:PostGIS / pg_stat_statements / auto_explain,以及之前用到的任何扩展(`SELECT extname FROM pg_extension` 在升级前先抓清单)
4. **升级完成后调优**(`citus.max_intermediate_result_size = 16GB` / `max_parallel_workers_per_gather = 40` 等)

**user 已批准的退路**:in-place 升级失败 → 重开一套新版集群 + pg_dumpall 灌回数据。**不要在 in-place 上死磕超过 30 分钟**。

## § 2 上下文启动顺序

按序读完直接开干(自主推进,无开跑前 ack):

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/upgrade/README.md`
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— § 11/§ 12
4. `rebuild5/docs/fix6_optim/04_runbook.md` —— 升级后 runbook 命令必须仍能跑(验收用)
5. `rebuild5/docs/loop_optim/03_rerun_report.md` —— 当前数据基线(TCL b7=340,766 / 7 批 wall clock 8541s,升级后跑同样命令应能复现 ±5%)
6. 本 prompt

读完直接开干。

## § 3 环境硬信息

### 集群拓扑

5 台机器,**root / 111111 SSH**:
- **coordinator**:`192.168.200.217`(同时是跳板机,user 本机连不通其他 worker,**所有 SSH 都从 217 跳**)
- **worker 1**:`192.168.200.216`
- **worker 2**:`192.168.200.219`
- **worker 3**:`192.168.200.220`
- **worker 4**:`192.168.200.221`

每台规格:20 物理核 / 40 逻辑核 / 251GB 内存。

### NAS 共享盘

`/nas_vol8`(5 台机器都挂载,agent 不需要 mount 操作,直接用)

**用途**:
- 下载 PG / Citus / PostGIS rpm/deb 包到 `/nas_vol8/upgrade/packages/`
- 备份产物落 `/nas_vol8/upgrade/backups/`
- spike 阶段产生的临时数据可放 `/nas_vol8/upgrade/spike/`

### 网络

- **国内镜像源**(资源拉取走这些,不要 GitHub / postgresql.org 直连):
  - 阿里云:`https://mirrors.aliyun.com/postgresql/`(yum repo)
  - 清华:`https://mirrors.tuna.tsinghua.edu.cn/postgresql/`
  - 中科大:`https://mirrors.ustc.edu.cn/`
  - PostGIS:看实际 OS 用 `postgis_18`(对应 PG 18)
  - Citus:`https://mirrors.aliyun.com/repo/Citus/`(若有)/ 或从 Citus GitHub release 走 `https://ghproxy.com/` / 阿里云容器镜像 / 清华代理
- 如果 217 能直连国外,先试 `curl -I --max-time 5 https://github.com`,通则可以直接走原 repo

### 当前数据库连接(只读用)

- **当前主集群(可能 PG17 或 PG18)**:`postgres://postgres:123456@192.168.200.217:5488/yangca`,MCP `mcp__PG_Citus__execute_sql`
- **PG17 旧库基线**:`postgres://postgres:123456@192.168.200.217:5433/ip_loc2`,MCP `mcp__PG17__execute_sql`(只读,**不动**)

### 数据现状(loop_optim 03 已收档)

- `rb5.trusted_cell_library` 全 7 批数据存在,TCL b7 = 340,766
- `rb5_stage.step2_input_b<N>_<YYYYMMDD>` 7 张 artifact 表存在(可以扔)
- `rb5_meta.pipeline_artifacts` 7 行 status='consumed'
- 数据可以扔(reset 重跑只 ~140 分钟),但**升级前必须备份**作为兜底

### user 不参与

agent 撞 blocker 才停下报告。完工统一 commit + push + 写 note。

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `fix6_optim/04_runbook.md` | 阅读 | 验收用,升级后 runbook 命令必须仍能跑 |
| `loop_optim/03_rerun_report.md` | 阅读 | 数据基线 TCL b7=340,766 |
| 本阶段产出 `upgrade_report.md` | 新建 | § 7 结构 |

**不修改任何 .md / .py 业务代码**,只动数据库 + OS 包 + 配置文件。

## § 5 任务清单(7 子阶段)

### 阶段 0:现状探测(纯只读,~30 分钟)

#### 5.0.1 SSH 测试

```bash
# 从用户本地执行不通,但 agent 应该有 mcp__PG_Citus__execute_sql,先用它探集群
# 如果 agent 有 host shell 访问(claude code 沙箱):
ssh -o StrictHostKeyChecking=no root@192.168.200.217 'hostname && uname -a && cat /etc/os-release'

# 跳板模式登 worker:
ssh -o StrictHostKeyChecking=no -J root@192.168.200.217 root@192.168.200.216 'hostname && cat /etc/os-release'
# (循环 219/220/221)
```

如果跳板不通,改 `ssh root@217 "ssh root@216 'hostname'"`(嵌套 ssh)。

#### 5.0.2 当前 PG / Citus / 扩展实测

```sql
-- via mcp__PG_Citus__execute_sql
SELECT version();
SELECT extname, extversion FROM pg_extension ORDER BY extname;
SHOW server_version;
SHOW citus.max_intermediate_result_size;
```

**关键**:user 说"3 周前以为升到 17 实际可能不是最新"。这一步**实测**当前到底是 PG 几,然后定升级目标:
- 如果当前 < PG 18.x → 目标 = 当前最新稳定 PG(查 https://www.postgresql.org/support/versioning/)
- 如果当前 = PG 18 → 目标 = 检查是否有 18.x 的小版本更新或下一大版本

#### 5.0.3 集群 health + 已挂载 NAS

```bash
# 在 217 上:
df -h /nas_vol8                          # 确认 NAS 挂载 + 空间
ls /nas_vol8                             # 看现有内容(可能已有 upgrade dir)
free -h                                  # 内存
df -h                                    # 各分区空间(尤其 /var/lib/pgsql 等)
systemctl status postgresql*             # PG 服务状态
systemctl status patroni 2>/dev/null     # 是否走 patroni
ps aux | grep -E "postgres|citus" | grep -v grep | head
```

各 worker 同样跑一遍(via 跳板)。

#### 5.0.4 写"现状报告"小节

把 §0 探测结果整理到 `upgrade_report.md` §1,user 回看用。**包含 OS 版本 / PG 版本 / Citus 版本 / 扩展清单 / 磁盘 / NAS 状态**。

写 note `topic='upgrade_phase0_done'` info,body 含当前 PG 版本 + 升级目标版本。

### 阶段 1:资源准备(下载到 NAS,~30 分钟)

#### 5.1.1 在 NAS 建结构

```bash
ssh root@192.168.200.217 '
mkdir -p /nas_vol8/upgrade/packages/{pg,citus,postgis,deps}
mkdir -p /nas_vol8/upgrade/backups/{dumps,basebackup,configs}
mkdir -p /nas_vol8/upgrade/spike
mkdir -p /nas_vol8/upgrade/logs
'
```

#### 5.1.2 选源 + 下载 PG

根据 OS:
- **CentOS / RHEL / Rocky**:从 https://mirrors.aliyun.com/postgresql/repos/yum/<version>/redhat/rhel-<X>-x86_64/ 下载 rpm
- **Ubuntu / Debian**:从 https://mirrors.tuna.tsinghua.edu.cn/postgresql/repos/apt/ 下载 deb
- 包清单:`postgresql<N>-server`、`postgresql<N>-contrib`、`postgresql<N>-devel`(后两者 Citus 编译可能要)

#### 5.1.3 下载 Citus

Citus 不一定有阿里云镜像,要从 GitHub release 走代理:
- 试 `https://ghproxy.com/https://github.com/citusdata/citus/releases/download/v<X.Y.Z>/citus-<X.Y.Z>.tar.gz`
- 或:从 Citus 官方 yum repo `https://download.postgresql.org/pub/repos/yum/reporpms/EL-<X>-x86_64/` 转阿里云镜像
- 选 Citus 版本对照表:[https://docs.citusdata.com/en/latest/installation/multi_node.html](按 PG 版本选)

#### 5.1.4 下载 PostGIS + 其他扩展

- PostGIS:阿里云镜像或 https://download.osgeo.org/postgis/(需要时通过 ghproxy 或华为云代理)
- pg_stat_statements、auto_explain:PG contrib 包自带,不需要单独下

#### 5.1.5 校验

每个下载完的文件:
```bash
sha256sum /nas_vol8/upgrade/packages/<file>
# 对比官方 SHA256(yum metadata 或 GitHub release notes)
```

写 note `topic='upgrade_phase1_done'` info,body 列下载的包文件名 + 版本号。

### 阶段 2:单机 spike(在最不重要的 worker 比如 221 上,~1 小时)

**目的**:在 221 上单独装新版 PG + Citus + PostGIS,跑通基本测试,**不动 PG17 / 当前集群**。

#### 5.2.1 spike 安装

在 221 上:
- 装新版 PG 到独立目录(如 `/usr/pgsql-<N>` rpm 默认 / 或 `/opt/pgsql-<N>` 手动)
- initdb 一个独立 cluster 到 `/var/lib/pgsql/<N>/data_spike`(独立路径,不动现有 PG17 数据)
- 监听独立 port(如 5489,与现有 5488 区分)
- 装 Citus 新版 + PostGIS

#### 5.2.2 spike 验证

启动 spike 实例:
```bash
systemctl start postgresql-<N>-spike  # 或手动 pg_ctl
psql -p 5489 -c "SELECT version();"
psql -p 5489 -c "CREATE EXTENSION citus;"
psql -p 5489 -c "CREATE EXTENSION postgis;"
psql -p 5489 -c "CREATE TABLE t (id int, c text); SELECT create_distributed_table('t', 'id');"
psql -p 5489 -c "INSERT INTO t SELECT i, md5(i::text) FROM generate_series(1,1000) i;"
psql -p 5489 -c "SELECT count(*) FROM t;"
# 期待 1000
```

如果 spike 失败:
- diagnose 错误日志,改源 / 改版本组合 / 改装方式
- ≤ 2 小时 解决不了 → blocker note + 等用户决策(stretch:可以选 PG 17.x 最新小版本 + Citus 14.x 最新小版本组合,而不是大版本升级)

#### 5.2.3 spike 清理

成功后:
- 停 spike 实例
- 保留 spike 数据目录,用作"升级模板"(确认包 / 版本 / 配置 OK)
- 写 note `topic='upgrade_phase2_done'`

### 阶段 3:备份(spike 成功后,~30-60 分钟)

#### 5.3.1 pg_dumpall 全库逻辑备份

在 217 上跑(pg_dumpall 拉所有 worker 数据回 coordinator):
```bash
PGPASSWORD=123456 pg_dumpall -h 192.168.200.217 -p 5488 -U postgres \
  > /nas_vol8/upgrade/backups/dumps/yangca_full_$(date +%Y%m%d_%H%M%S).sql
```

**这是跨版本兜底**,即便 PG18 灌不回来,至少有 SQL 文本。

#### 5.3.2 配置文件备份

每台机器:
```bash
cp /var/lib/pgsql/<N>/data/postgresql.conf /nas_vol8/upgrade/backups/configs/<host>_postgresql.conf
cp /var/lib/pgsql/<N>/data/pg_hba.conf /nas_vol8/upgrade/backups/configs/<host>_pg_hba.conf
```

#### 5.3.3(可选)数据卷文件级备份

如果磁盘空间够 + 想要快速回滚 PG17:
```bash
# 各 worker 停 PG17 服务后(本地数据 ~50GB?查实际)
# rsync -av /var/lib/pgsql/17/data/ /nas_vol8/upgrade/backups/basebackup/<host>_pg17_data/
```

如果空间不够,跳过 §5.3.3,只靠 §5.3.1 的 dumpall。

#### 5.3.4 备份验证

`pg_dumpall` 文件大小检查 + grep 关键 schema:
```bash
ls -lh /nas_vol8/upgrade/backups/dumps/
grep -c "CREATE TABLE rb5\." /nas_vol8/upgrade/backups/dumps/yangca_full_*.sql
# 期待 ≥ 30(rb5.* 主表数量)
```

写 note `topic='upgrade_phase3_done'` + body 含 dump 大小。

### 阶段 4:正式升级(分两条路)

#### 路 A:in-place 升级(优先,最多 30 分钟)

**这条路有失败风险**,所以 30 分钟卡死。

```bash
# 5 台机器,顺序操作(coordinator 最后)
for host in 216 219 220 221 217; do
  ssh root@192.168.200.<host> '
    # 1. 停服务
    systemctl stop postgresql-<old>
    
    # 2. 装新版(如果包从 NAS 用 yum localinstall)
    yum localinstall /nas_vol8/upgrade/packages/pg/postgresql<N>-*.rpm
    
    # 3. initdb 新 cluster 或 pg_upgrade --link
    /usr/pgsql-<N>/bin/pg_upgrade \
      --old-bindir /usr/pgsql-<old>/bin \
      --new-bindir /usr/pgsql-<N>/bin \
      --old-datadir /var/lib/pgsql/<old>/data \
      --new-datadir /var/lib/pgsql/<N>/data \
      --link
    
    # 4. 启新版
    systemctl start postgresql-<N>
  '
done
```

完成后 coord 上跑:
```sql
ALTER EXTENSION citus UPDATE;
ALTER EXTENSION postgis UPDATE;
SELECT version();
SELECT count(*) FROM rb5.trusted_cell_library;  -- 期待 = loop_optim 03 状态
```

任意 worker 跑挂 / metadata 不一致 / count 对不上 → 立刻切路 B。**不要尝试 troubleshoot Citus distributed metadata in-place 升级,已知风险大**。

#### 路 B:重开一套(in-place 失败的 fallback)

```bash
# 1. 各机器装新版到独立目录(spike 阶段已验证)
# 2. initdb 全新 cluster 监听独立 port(比如 5490)
# 3. pg_isready 测试新 cluster
# 4. Citus + PostGIS extension 创建
# 5. 注册 worker:SELECT citus_add_node('192.168.200.216', 5490) 等
# 6. 灌数据:psql -p 5490 < /nas_vol8/upgrade/backups/dumps/yangca_full_*.sql
# 7. 验证 distributed table:
SELECT logicalrelid::regclass, partmethod, partkey FROM pg_dist_partition;
SELECT count(*) FROM rb5.trusted_cell_library;  -- 期待 = dump 时刻状态
# 8. 切流量:把新 cluster 起在 5488(替代旧的)+ 旧的 PG17 / 旧的当前版本停服或挪 port
```

**关键**:路 B 走完后,旧版数据保留(独立目录 + 独立 port),作为终极兜底。

写 note `topic='upgrade_phase4_done'`,body 含选了路 A 还是路 B + 实际花了多少时间。

### 阶段 5:验收(~15-30 分钟)

#### 5.5.1 基础健康

```sql
SELECT version();
SELECT extname, extversion FROM pg_extension ORDER BY 1;
SELECT count(*) FROM rb5.trusted_cell_library;     -- 期待 = loop_optim 03 状态(若 路 A)或 dump 时刻状态(路 B)
SELECT count(*) FROM rb5.cell_sliding_window;
SELECT batch_id, count(*) FROM rb5.trusted_cell_library GROUP BY 1 ORDER BY 1;
```

#### 5.5.2 Citus 集群健康

```sql
SELECT * FROM citus_get_active_worker_nodes();   -- 期待 4 worker
SELECT count(*) FROM pg_dist_partition;           -- 期待 ≥ 30 distributed table
SELECT * FROM citus_check_cluster_node_health() LIMIT 10;
```

#### 5.5.3 数据查询能跑

```sql
-- 跨 shard 简单查
SELECT count(distinct cell_id) FROM rb5.trusted_cell_library WHERE batch_id=7;

-- 跨 shard join(检查 colocation)
SELECT count(*) FROM rb5.trusted_cell_library t
JOIN rb5.cell_sliding_window w
  USING (operator_code, lac, cell_id, tech_norm)
WHERE t.batch_id=7 LIMIT 10;
```

#### 5.5.4 runbook 命令验证(关键)

跑 `rebuild5/scripts/runbook/sentinels.sh 7`:
```bash
PGPASSWORD=123456 PGGSSENCMODE=disable bash rebuild5/scripts/runbook/sentinels.sh 7
# 期待 4 哨兵全 PASS
```

跑 `rebuild5/scripts/runbook/endpoint_check.sh`:
```bash
PGPASSWORD=123456 PGGSSENCMODE=disable bash rebuild5/scripts/runbook/endpoint_check.sh
# 期待终点 3 验收 PASS
```

验收挂任何一项 → blocker note + 报告。

写 note `topic='upgrade_phase5_done'`。

### 阶段 6:调优参数(~15 分钟)

```sql
-- 全局调优(参考 fix5 / fix6_optim 已用值)
ALTER SYSTEM SET citus.max_intermediate_result_size = '16GB';
-- 不要再设 max_parallel_workers_per_gather 全局,Step1 SETUP 走 session 级

-- auto_explain 不再强制 log_analyze=on(避免 fix5 D 撞的 INSERT...SELECT 不支持)
ALTER SYSTEM SET auto_explain.log_analyze = off;  -- 如果原先是 on

-- reload
SELECT pg_reload_conf();

-- 验证
SHOW citus.max_intermediate_result_size;
SHOW auto_explain.log_analyze;
```

agent 自主决定是否需要其他调优(基于阶段 0 探测的 `pg_settings` 异常项),但**不要扩大改动范围**。

写 note `topic='upgrade_phase6_done'`。

### 阶段 7:完工 commit + push

`git add` 列改动:
- `rebuild5/docs/upgrade/upgrade_prompt.md`(本 prompt)
- `rebuild5/docs/upgrade/upgrade_report.md`(产出)
- `rebuild5/docs/upgrade/README.md`

(不改 .py / 业务 .md / 数据库 schema)

一个 commit:
```
chore(rebuild5): upgrade PG to <X> and Citus to <Y>

- PG <old> -> PG <X>; Citus <old> -> Citus <Y>; PostGIS <old> -> <Y>
- Path used: <A in-place / B fresh-rebuild>; total downtime <m> minutes
- Backup at /nas_vol8/upgrade/backups/dumps/yangca_full_<timestamp>.sql (<size>)
- Sentinels and endpoint_check pass on TCL b7=<n>
- Tunables: citus.max_intermediate_result_size=16GB, auto_explain.log_analyze=off
- References upgrade/upgrade_report.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push 撞 SSL 等 60s 重试一次,再失败标 push pending。

写 note `topic='upgrade_done'`,用 § 9 完工话术汇报。

### 不做(显式禁止)

- ❌ 不改 backend/app 任何代码
- ❌ 不改 fix5/fix6_optim/loop_optim 任何已交付产物
- ❌ 不删 PG17 旧库(`/var/lib/pgsql/17/data` 或对应路径,作为终极兜底,即便 in-place 升级走 --link 也保留备份)
- ❌ 不在 in-place 上死磕超过 30 分钟,挂了立刻切路 B
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不 commit /nas_vol8/upgrade 任何二进制(包 / dump 文件不进 git)
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc
- ❌ 不动 PG17 5433/ip_loc2 旧库(独立基线,只读)
- ❌ 不为加速跳过备份(没备份不能动主集群,blocker)
- ❌ 不擅自决定"删 PG17 数据腾空间",空间不够停 + blocker

## § 6 验证标准

任务 done 的硬标准:

1. **5 台机器都跑新版**:每台 SSH 进去 `psql --version` 显示新版本号
2. **Citus 集群 health**:`citus_get_active_worker_nodes()` 返回 4 worker,`pg_dist_partition` 行数与升级前一致(±5%,允许 distributed metadata 重建期间小波动)
3. **TCL b7 数据完好**:升级后 `SELECT count(*) FROM rb5.trusted_cell_library WHERE batch_id=7` = 340,766 ± 0(in-place 不应丢数据;路 B 重建后从 dump 恢复 = 340,766 ± 0)
4. **runbook sentinels.sh 7 全 PASS** + **endpoint_check.sh 全 PASS**
5. **扩展齐全**:`SELECT extname FROM pg_extension` 至少含 `citus`、`postgis`、`pg_stat_statements`、`auto_explain`(或 explained)
6. **备份在 NAS**:`/nas_vol8/upgrade/backups/dumps/yangca_full_*.sql` 存在 + size > 1GB(yangca 全库导出大约几 GB)
7. **commit + push**:`git rev-parse HEAD == git rev-parse origin/main`(允许标 push pending)
8. **note `upgrade_done` 写入**

## § 7 产出物 `upgrade_report.md`

```markdown
# upgrade — PG / Citus / 扩展 升级报告

## 0. TL;DR
- 升级前:PG <old>, Citus <old>, PostGIS <old>
- 升级后:PG <new>, Citus <new>, PostGIS <new>
- 路径:<A in-place / B 重开一套>;原因:<>
- 总 downtime:<m> 分钟
- 备份位置:/nas_vol8/upgrade/backups/dumps/<file>(<size>)
- 验收:基础 health + Citus health + sentinels + endpoint_check 全 PASS
- 调优:<列>
- commit SHA:<sha>;push 状态:<status>

## 1. 现状探测(阶段 0)
- 5 台机器 OS / 内核
- 升级前 PG / Citus / PostGIS / 扩展清单
- 磁盘空间 / NAS 状态

## 2. 资源准备(阶段 1)
- 选了哪个镜像源
- 下载的包文件清单 + 校验 SHA
- 总下载量 + 时长

## 3. 单机 spike(阶段 2)
- 选 worker 221
- 装新版的步骤(关键命令节选)
- spike SQL 测试结果
- 撞坑(如有)+ 解决方式

## 4. 备份(阶段 3)
- pg_dumpall 命令 + 大小 + 时长
- 配置文件备份路径
- 数据卷快照(若做)

## 5. 正式升级(阶段 4)
- 路径选择:A in-place / B 重开一套 / 混合
- 5 台机器各自步骤(关键命令)
- ALTER EXTENSION 输出
- 撞错 + 切换路径(如有)

## 6. 验收(阶段 5)
- 基础 health 输出
- Citus 集群 health 输出
- 数据查询输出
- runbook 命令输出(sentinels + endpoint_check)

## 7. 调优(阶段 6)
- ALTER SYSTEM 列表
- SHOW 验证输出

## 8. 已知限制 / 未做
- 数据卷快照(若没做)
- 任何 spike 期间发现的小问题 user 应该知道

## 9. fallback 路径(给未来再升级用)
- PG17 旧数据保留位置
- 怎么从 dump 恢复(如果将来某个时刻发现新版有 bug 想退回)
```

## § 8 notes 协议

- 阶段开始 / 完工每个写一条:
  - `upgrade_phase0_done` info,body 含当前 PG 版本 + 升级目标
  - `upgrade_phase1_done` info,body 含下载包清单
  - `upgrade_phase2_done` info,body 含 spike 是否成功
  - `upgrade_phase3_done` info,body 含 dump 大小
  - `upgrade_phase4_done` info,body 含路 A 还是路 B
  - `upgrade_phase5_done` info,body 含验收结果
  - `upgrade_phase6_done` info,body 含调优清单
- 完工:`upgrade_done` info,body 含 PG 版本 + Citus 版本 + 总 downtime + commit SHA
- 失败:`upgrade_failed` blocker,body 含失败阶段 + 完整 traceback + 当前集群状态(是否能用 PG17 / 是否要回滚)

**重要**:`rb5_bench.notes` 是反向通信,**升级期间数据库会停**,note 可能写不进。备用方案:
- 升级中产生的关键事件先写 `/nas_vol8/upgrade/logs/<timestamp>.log` 文件
- 升级完成后,把 log 摘要补写到 notes 表

## § 9 完工话术

成功:
> "PG / Citus 升级完成。upgrade_report.md 已写入。PG <old> → <new>,Citus <old> → <new>,PostGIS <old> → <new>。路径:<A/B>,downtime <m> 分钟。备份在 /nas_vol8/upgrade/backups/dumps/<file>(<size>)。基础 health + Citus health + sentinels + endpoint_check 全 PASS。TCL b7=<n> 与升级前一致。调优:<列>。commit=<SHA>(push <成功/pending>)。notes `topic='upgrade_done'` 已插入。"

失败:
> "PG 升级失败于阶段 <N>:<step>。blocker=<一句话>。当前集群状态:<回滚到 PG17 / 部分升级 / 完全停服>。备份位置:<dump 路径,如已做>。已写 notes `topic='upgrade_failed'`。等上游处置。"

## § 10 失败兜底

- **阶段 0 SSH 跳板不通**:试嵌套 `ssh root@217 'ssh root@216 ...'`;再不通让 user 在 217 本地直接跑命令(他能登 217)
- **阶段 1 包下载源都不通**:换源(阿里云 → 清华 → 中科大 → ghproxy);如果 PG 18 大版本所有源都没货,降级目标到 PG 17.x 最新小版本(stretch goal 妥协,不是 blocker)
- **阶段 2 spike 失败**:diagnose 错误日志 + 换版本组合;**预算 ≤ 2 小时**,超过 → blocker note,不动主集群
- **阶段 3 备份磁盘空间不够**:NAS 写不下(/nas_vol8 满)→ blocker(没备份不能动主集群)
- **阶段 4 in-place 升级失败**:**≤ 30 分钟立刻切路 B**,不要在 in-place 死磕。pg_upgrade 报 incompatibility 即切
- **阶段 4 路 B 灌数据失败**(dump SQL 撞 PG18 不兼容语法):agent 自主修 dump(sed 替换不兼容语法),如果 ≥ 50 处不兼容 → 考虑分阶段灌(先 schema 后 data,或 per-table 单独灌)
- **阶段 5 runbook 跑挂**:看具体哪个 SQL 挂,如果是 distributed table 元数据问题,可能是 路 B 灌数据时 colocation group 没还原 → 用 `update_distributed_table_colocation()` 修
- **阶段 6 调优:撞陌生 GUC**:GUC 名跨版本可能改了,用 `pg_settings` 查替代名
- **任何阶段:数据丢失嫌疑**:**立刻停**,不要继续写,在报告 §9 给 user 完整恢复路径(从 dump / 从 PG17 旧数据)
- **GitHub HTTPS SSL 抖动**(push 阶段):等 60s 重试,push pending 不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改

---

## § 11 关键技术 prime(让 agent 不踩明显坑)

### pg_upgrade --link vs --copy

- `--link`:hard link 旧数据,瞬时,但**升级失败旧数据也可能损坏**。**强烈建议 --copy**(慢一点但安全),除非有完整数据卷快照
- 如果选 --link,务必先 §5.3.3 数据卷文件级备份

### Citus 跨大版本升级

- Citus 主版本号通常跟着 PG 走(Citus 11 → PG 14 / Citus 12 → PG 15 / Citus 13 → PG 16 / Citus 14 → PG 17)
- **如果实际有 Citus 15 / 16 对应 PG 18,选最新**;如果还没出,可能要降目标到 PG 17.x
- `ALTER EXTENSION citus UPDATE` 一般要在 coordinator 跑,worker 自动同步;但跨大版本可能要重建 distributed metadata,这是路 B 触发条件之一

### auto_explain 启动参数(fix5 D 教训)

升级后**不要再加 `-c auto_explain.log_analyze=on` 命令行启动参数**(fix5 D 撞过,会让 INSERT...SELECT 报错)。如果原 systemd 配置里有,改掉。

### NAS /nas_vol8 写入并发

5 台机器同时写 /nas_vol8 可能撞 NFS lock,**备份阶段在 217 上单独跑 dump**,不要并行 5 台一起 rsync。
