# OptiNet rebuild5 / 内核升级后综合收尾 — IO 适配 + 宿主机 profile + 网络 backlog(agent 新实例对话)

## § 1 元目标

kernel-ml 6.6.12 已全节点升完(commit `a3a1ae9`,5 节点都 `uname -r` = `6.6.12-1.el7.elrepo.x86_64`),**现在做 06 文档 § 9 综合收尾的 3 个子项**:

1. **PG18 IO 适配**(06 § 3.3):新内核启用 worker AIO,配 `io_method='worker' / io_workers=10 / effective_io_concurrency=64 / maintenance_io_concurrency=64`(之前 PG18 在老内核上跑不动这套,所以用 mmap 模式应付,现在内核升级后可以改回 posix shm + 调 worker AIO)
2. **宿主机性能 profile**(06 § 9 项 4):tuned-adm 切到适合数据库吞吐的 profile(如 `throughput-performance`),不再用 balanced
3. **网络 backlog**(06 § 9 项 5):提高 `net.core.somaxconn` / `net.ipv4.tcp_max_syn_backlog` 等 sysctl,避免连接高峰排队溢出

**不做**:
- ❌ **不动 RAID 写入参数**(06 § 9 项 6,user 明确推迟)
- ❌ 不改 PG 业务参数(WAL / checkpoint / parallel / cache 已在 upgrade v2 finalize 阶段调过)
- ❌ 不改容器 docker run 参数(已在 upgrade v2 finalize 加 `--shm-size=16g` 等)
- ❌ 不动 backend 业务代码

## § 2 上下文启动顺序

按序读完直接开干(自主推进,无开跑前 ack):

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/CLUSTER_USAGE.md` — 集群当前调优参数全景(§ 9 列了已生效的)
3. `rebuild5/docs/fix6_optim/_prompt_template.md` § 11/§ 12
4. `/Users/yangcongan/cursor/DataBase/Docs/05_当前PG设置优化要求.md` § 3.3 / § 4 — IO 参数依据
5. `/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md` § 9 — 综合收尾清单(项 4 / 5 是本阶段范围,项 6 不做)
6. `rebuild5/docs/upgrade/upgrade_v2_finalize_and_tuning_report.md` — PG18 已生效参数清单
7. `rebuild5/docs/upgrade/kernel_upgrade_all_210_report.md` — 内核升级最终状态
8. `rb5_bench.notes` topic LIKE `'upgrade_%' OR 'kernel_%'` — 升级 trail
9. 本 prompt

读完直接开干。

## § 3 环境硬信息

### 集群拓扑

5 节点(同 06 文档,不重复列):
- 控制台:**192.168.200.210**(已是内核升级控制台)
- coordinator:192.168.200.217(端口 5488 PG18 / 5487 PG17 fallback)
- workers:216 / 219 / 220 / 221(同样 5488 + 5487)
- root / 111111
- NAS `/nas_vol8`(5+1 都挂)

### 关键现状(2026-04-28)

- 全 5 节点内核 = `6.6.12-1.el7.elrepo.x86_64`
- 全 5 节点 PG = 18.3 + Citus 14.0-1 + PostGIS 3.6.3
- 容器 `--shm-size=16g` 已生效
- `dynamic_shared_memory_type = posix`(在 upgrade v2 finalize 已设)
- 当前 `io_method` = ?(agent 第一步 SHOW 实测;06 § 3.3 期望改 'worker')
- 当前 host tuned profile = ?(`tuned-adm active`,可能是 'balanced' 或 'virtual-guest')
- 当前 `net.core.somaxconn` = ?(默认 128 太小)

### 数据基线

TCL b7 = 340,766 / sliding = 24,017,207 / 4 worker active(详见 PROJECT_STATUS.md)

### 控制台

210:`/data/upgrade/kernel-ml-6.6.12/`(脚本归档)+ `/data/upgrade/post_kernel_tuning/`(本阶段产物建议落这里)

## § 4 关联文档清单

| 路径 | 阅读 / 修改 |
|---|---|
| `Docs/05_当前PG设置优化要求.md` § 3.3 | 阅读 — IO 参数依据 |
| `Docs/06_kernel_ml_6.6.12升级计划.md` § 9 | 阅读 — 收尾项目分类 |
| `rebuild5/docs/CLUSTER_USAGE.md` § 9 | **修改** — 把本阶段新参数加进"PG 参数 / 内核 / 容器"清单 |
| 本阶段产出 `post_kernel_io_and_host_tuning_report.md` | 新建 |

**不动 backend/app 业务代码**。

## § 5 任务清单(按风险递增顺序,每子项 reload 后跑哨兵确认未挂)

### 阶段 0:状态实测(~5 分钟)

```sql
-- via Citus MCP 5488,5 节点都跑(coord + workers)
SHOW io_method;
SHOW io_workers;
SHOW effective_io_concurrency;
SHOW maintenance_io_concurrency;
SHOW dynamic_shared_memory_type;
SHOW shared_buffers;
```

```bash
# 在 210 上,via SSH 跳板每节点跑:
ssh -J root@192.168.200.210 root@<host> '
tuned-adm active
tuned-adm list 2>&1 | head -10
sysctl net.core.somaxconn net.ipv4.tcp_max_syn_backlog net.core.netdev_max_backlog
'
```

把全部输出整理到报告 §1。

写 note `topic='post_kernel_phase0_done'`。

### 阶段 1:PG18 IO 适配(reload 级,~10 分钟)

按 06 § 3.3:

```sql
-- 在 5488 coord 跑(ALTER SYSTEM 自动同步到 worker 通过 Citus,不需要每节点跑;
-- 但实际 worker 也要确认参数生效,因为 ALTER SYSTEM 改 postgresql.auto.conf 是单机的
-- Citus distributed table 的 worker 需要分别 ALTER SYSTEM)

-- 第一步:coord 设
ALTER SYSTEM SET io_method = 'worker';
ALTER SYSTEM SET io_workers = 10;
ALTER SYSTEM SET effective_io_concurrency = 64;
ALTER SYSTEM SET maintenance_io_concurrency = 64;
SELECT pg_reload_conf();
SHOW io_method;  -- 验证

-- 注:io_method 是 PG18 的新 GUC,可能在某些 reload 不生效场景需要重启容器
-- 如果 reload 后 SHOW 没变,标 "需要容器重启",但不要本阶段重启(留给 user 决定时机)
```

每个 worker 也要 ALTER SYSTEM(因为每个 worker 是独立 PG instance):

```bash
# 在每个 worker 上(via 210 跳板)psql 直连本机 5488:
for w in 216 219 220 221; do
  PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.${w} -p 5488 -U postgres -d yangca -c "
ALTER SYSTEM SET io_method = 'worker';
ALTER SYSTEM SET io_workers = 10;
ALTER SYSTEM SET effective_io_concurrency = 64;
ALTER SYSTEM SET maintenance_io_concurrency = 64;
SELECT pg_reload_conf();
SHOW io_method;
"
done
```

#### 1.1 验证 + 哨兵

```sql
-- 跑一个简单 SELECT 验未挂
SELECT count(*) FROM rb5.trusted_cell_library WHERE batch_id = 7;
-- 期待 340766
```

如果某个参数 SHOW 没变(说明需要重启才生效),记录到报告 §3 标"pending restart"。**不要本阶段重启**。

写 note `topic='post_kernel_phase1_done'`,body 含 5 节点 SHOW 结果 + pending restart 列表。

### 阶段 2:宿主机性能 profile(~10 分钟)

```bash
# 在每节点(via 210 跳板):
ssh -J root@192.168.200.210 root@<host> '
# 1. 看现 profile
tuned-adm active

# 2. 看候选 profile(看哪个适合 DB 吞吐)
tuned-adm list

# 3. 切到 throughput-performance(主流推荐)
tuned-adm profile throughput-performance

# 4. 验证
tuned-adm active
sysctl vm.swappiness vm.dirty_ratio vm.dirty_background_ratio
'
```

**注意**:5 节点逐个切,每切一个等 30 秒,看 PG18 容器是否健康(`docker ps | grep 5488`)。

某个 profile 在某节点切了之后 PG 异常 → 立刻切回原 profile(`tuned-adm profile <原>`),写 blocker。

写 note `topic='post_kernel_phase2_done'`。

### 阶段 3:网络 backlog(sysctl,需要持久化)(~10 分钟)

按 06 § 9 项 5:

```bash
# 在每节点:
ssh -J root@192.168.200.210 root@<host> '
# 1. 写 sysctl drop-in(持久化,reboot 后仍生效)
cat > /etc/sysctl.d/99-citus-network.conf << "EOF"
# 提高连接排队上限,避免数据库连接高峰时系统队列太小
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 4096
net.core.netdev_max_backlog = 30000
EOF

# 2. 立即生效
sysctl -p /etc/sysctl.d/99-citus-network.conf

# 3. 验证
sysctl net.core.somaxconn net.ipv4.tcp_max_syn_backlog net.core.netdev_max_backlog
'
```

**注**:这些值是常用偏保守的推荐(参考 PG / Citus 社区 + Linux performance tuning 文档)。如果机器有特殊瓶颈再调。

#### 3.1 验证 PG18 监听 backlog 也跟上

PG18 自身的 listener backlog 由 `listen_addresses` 和内核 `somaxconn` 共同决定。改完 `somaxconn` 后,**PG18 容器需要重启**才能让 listen socket 用新的 backlog(reload 不行)。

**本阶段不重启容器**(避免 UNLOGGED 表丢历史 batch),记录"PG18 listen backlog 等下次容器重启自然生效"。

写 note `topic='post_kernel_phase3_done'`。

### 阶段 4:综合验证(~10 分钟)

#### 4.1 集群健康

```sql
SELECT * FROM citus_check_cluster_node_health() LIMIT 5;
SELECT * FROM citus_get_active_worker_nodes();
SELECT count(*) FROM rb5.trusted_cell_library WHERE batch_id = 7;  -- 期待 340766
```

#### 4.2 跑 sentinels.sh 7 + endpoint_check.sh

```bash
bash rebuild5/scripts/runbook/sentinels.sh 7
bash rebuild5/scripts/runbook/endpoint_check.sh
# 期待全 PASS
```

#### 4.3 跑一次 batch 1 single-batch smoke(可选)

```bash
# 大约 13 分钟,验证 IO 调优后 Step1 是否更快
PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca' \
bash rebuild5/scripts/runbook/run_single_batch.sh 2025-12-01 1
```

如果不跑(保守)就标"smoke 留给 user 自行触发"。

写 note `topic='post_kernel_phase4_done'`,body 含 sentinels / endpoint_check 状态 + smoke 时长(若跑)。

### 阶段 5:更新 CLUSTER_USAGE.md + 完工 commit

#### 5.1 修改 `rebuild5/docs/CLUSTER_USAGE.md` § 9

把"待办"列表里的 IO / profile / backlog 三项移到"已生效"列表,加上具体数值。

#### 5.2 完工 commit + push

`git add`:
- `rebuild5/docs/upgrade/post_kernel_io_and_host_tuning_prompt.md`(本)
- `rebuild5/docs/upgrade/post_kernel_io_and_host_tuning_report.md`(产出)
- `rebuild5/docs/CLUSTER_USAGE.md`(更新 § 9)

一个 commit:
```
chore(rebuild5): post-kernel-upgrade IO/host/network tuning

- PG18 IO: io_method=worker, io_workers=10,
  effective_io_concurrency=64, maintenance_io_concurrency=64
  (applied to coord + 4 workers; some params pending container restart)
- Host tuned profile: <balanced -> throughput-performance> on 5 nodes
- Network sysctl: somaxconn=4096, tcp_max_syn_backlog=4096,
  netdev_max_backlog=30000 via /etc/sysctl.d/99-citus-network.conf (5 nodes)
- RAID tuning intentionally deferred per user instruction
- Cluster health post-tune: 4 workers active, TCL b7=340766 unchanged
- Update CLUSTER_USAGE.md §9 with new tunables

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push 撞 SSL 等 60s 重试,再失败标 push pending。

写 note `topic='post_kernel_io_host_done'`(同时是综合收尾这一轮的 done 信号)。

### 不做(显式禁止)

- ❌ 不动 RAID 写入参数(06 § 9 项 6,user 明确推迟)
- ❌ 不改业务 PG 参数(WAL / checkpoint / parallel / cache 已 finalize 调过)
- ❌ 不改容器 docker run 参数(--shm-size 已 16g)
- ❌ 不重启 PG18 容器(避免 UNLOGGED 表丢历史 batch)
- ❌ 不动 backend/app 业务代码
- ❌ 不动 fix5/fix6/loop 已交付产物
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 任何参数 ALTER 后 reload 撞错立刻 RESET 那个参数,不硬推
- ❌ 不持久化 sysctl 到 `/etc/sysctl.conf`(用 drop-in `/etc/sysctl.d/99-*.conf`,清晰可回滚)
- ❌ 不改 PG17 5487 fallback(它仍在观察期)
- ❌ tuned-adm 切了之后 PG 异常立刻切回原 profile

## § 6 验证标准

1. **5 节点 IO 参数 SHOW**:io_method=worker / io_workers=10 / effective_io_concurrency=64 / maintenance_io_concurrency=64(部分可能 pending restart,允许标注)
2. **5 节点 tuned profile**:不再是 balanced(具体值由 agent 选,通常 throughput-performance)
3. **5 节点 sysctl**:somaxconn ≥ 4096,sysctl drop-in 文件存在
4. **集群健康** + **数据基线**:`citus_check_cluster_node_health` 全 healthy / TCL b7 = 340766(无变化)
5. **sentinels.sh 7** + **endpoint_check.sh**:全 PASS
6. **CLUSTER_USAGE.md § 9 更新**:IO / profile / backlog 三项移到已生效
7. **commit + push**(允许 push pending)
8. **note `post_kernel_io_host_done`** 写入

## § 7 产出物 `post_kernel_io_and_host_tuning_report.md`

```markdown
# 内核升级后综合收尾 — IO / Profile / 网络 报告

## 0. TL;DR
- IO: io_method=worker / io_workers=10 / eff_io_conc=64 / maint_io_conc=64,5 节点 ALTER SYSTEM
  pending restart 项:<列>
- Host profile: <balanced -> throughput-performance>(5 节点)
- 网络 backlog: somaxconn=4096 / tcp_max_syn_backlog=4096 / netdev=30000(5 节点)
- 集群健康 + TCL b7=340766 无变化
- RAID 项推迟(per user)
- commit SHA / push 状态

## 1. 阶段 0 状态实测
- 5 节点 IO / profile / sysctl 输出节选

## 2. 阶段 1 PG18 IO 适配
- ALTER SYSTEM 命令 + 5 节点 SHOW 结果
- pending restart 项

## 3. 阶段 2 Host profile
- tuned-adm active 切换前后
- 5 节点状态

## 4. 阶段 3 网络 backlog
- /etc/sysctl.d/99-citus-network.conf 内容
- 5 节点 sysctl 切换前后

## 5. 阶段 4 综合验证
- citus_check_cluster_node_health 输出
- TCL 基线对账(无变化)
- sentinels.sh 7 输出
- endpoint_check.sh 输出
- single-batch smoke 时长(若跑)

## 6. CLUSTER_USAGE.md §9 更新点
- diff 节选

## 7. 已知限制 / 后续维护建议
- io_method 等 pending restart 的容器重启时机
- RAID 调优(06 §9 项 6)推迟时机
- tuned profile 在 specific workload 上是否还需要 fine-tune
```

## § 8 notes 协议

- 每阶段:`post_kernel_phase<N>_done` info
- 完工:`post_kernel_io_host_done` info
- 失败:`post_kernel_io_host_failed` blocker

## § 9 完工话术

成功:
> "内核升级后综合收尾完成。post_kernel_io_and_host_tuning_report.md 已写入。
> IO 适配:io_method=worker / 等 4 项 ALTER SYSTEM(5 节点);pending restart=<list>。
> Host profile:<old> → throughput-performance(5 节点)。
> 网络 backlog:somaxconn=4096 / etc(5 节点 sysctl drop-in)。
> 集群健康 + TCL b7=340766 无变化,sentinels + endpoint_check 全 PASS。
> RAID 项按 user 指令推迟。
> CLUSTER_USAGE.md §9 已更新。
> commit=<SHA>(push <成功/pending>)。
> notes `topic='post_kernel_io_host_done'` 已插入。"

失败:
> "内核升级后综合收尾失败于阶段 <N>:<step>。blocker=<一句话>。当前已生效 / 已回滚 状态:<>。已写 notes,等上游处置。"

## § 10 失败兜底

- **某个 ALTER SYSTEM 撞错**:RESET 那个参数,跑下一个;5 步分隔目的就是隔离风险
- **io_method='worker' 报"参数不支持"**:可能是 PG 18 minor 版本差异,看 `pg_settings` 找替代名
- **tuned-adm 切到新 profile 后 PG 容器异常**(rare,但可能切换瞬间 IO scheduler 变化引入抖动):立刻 `tuned-adm profile <原>` 切回,blocker
- **sysctl drop-in 写入后 sysctl -p 报错**:看具体哪个参数不被内核支持(6.6.12 比 3.10 GUC 名可能有差异),逐项二分
- **集群基线偏差**(TCL b7 不再 = 340766):**这不应该发生**(本阶段只改 OS / PG 启动参数,不改数据)。立刻 blocker,可能是某个调优撞 query plan 变化
- **GitHub HTTPS SSL 抖动**:等 60s 重试,push pending 不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不擅自大改
