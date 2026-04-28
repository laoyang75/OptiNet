# 内核升级后综合收尾 — IO / Profile / 网络 报告

## 0. TL;DR

- 结果:完成。
- PG18 IO:5 节点均已 `ALTER SYSTEM` 到 `io_method=worker` / `io_workers=10` / `effective_io_concurrency=64` / `maintenance_io_concurrency=64`。
- Pending restart:IO 四项 `pending_restart=none`;网络 backlog 对 PG18 listen socket 的完整拾取需等下次容器重启,本阶段按约束未重启。
- Host profile:5 节点从 `balanced` 切到 `throughput-performance`。
- 网络 backlog:5 节点通过 `/etc/sysctl.d/99-citus-network.conf` 持久化 `somaxconn=4096` / `tcp_max_syn_backlog=4096` / `netdev_max_backlog=30000`。
- 集群健康: `citus_check_cluster_node_health()` 25/25 true,4 workers active。
- 数据基线:TCL b7=`340766`, `cell_sliding_window=24017207`,无变化。
- `sentinels.sh 7` PASS; `endpoint_check.sh` PASS。
- RAID 写入参数按 user 指令推迟。

## 1. 阶段 0 状态实测

PG18 5 节点实测在本阶段开始前已经是目标 IO 值:

| 节点 | io_method | io_workers | effective_io_concurrency | maintenance_io_concurrency | dynamic_shared_memory_type | shared_buffers |
|---|---|---:|---:|---:|---|---:|
| 192.168.200.217 | worker | 10 | 64 | 64 | posix | 64GB |
| 192.168.200.216 | worker | 10 | 64 | 64 | posix | 64GB |
| 192.168.200.219 | worker | 10 | 64 | 64 | posix | 64GB |
| 192.168.200.220 | worker | 10 | 64 | 64 | posix | 64GB |
| 192.168.200.221 | worker | 10 | 64 | 64 | posix | 64GB |

Host 实测:

| 节点 | tuned profile before | somaxconn | tcp_max_syn_backlog | netdev_max_backlog | drop-in |
|---|---|---:|---:|---:|---|
| 192.168.200.217 | balanced | 4096 | 4096 | 1000 | missing |
| 192.168.200.216 | balanced | 4096 | 4096 | 1000 | missing |
| 192.168.200.219 | balanced | 4096 | 4096 | 1000 | missing |
| 192.168.200.220 | balanced | 4096 | 4096 | 1000 | missing |
| 192.168.200.221 | balanced | 4096 | 4096 | 1000 | missing |

Note: `post_kernel_phase0_done`.

## 2. 阶段 1 PG18 IO 适配

对 217/216/219/220/221 逐节点执行:

```sql
ALTER SYSTEM SET io_method = 'worker';
ALTER SYSTEM SET io_workers = 10;
ALTER SYSTEM SET effective_io_concurrency = 64;
ALTER SYSTEM SET maintenance_io_concurrency = 64;
SELECT pg_reload_conf();
```

最终 5 节点 `SHOW` 结果均为:

```text
effective_io_concurrency   = 64
io_method                  = worker
io_workers                 = 10
maintenance_io_concurrency = 64
```

`TCL b7=340766`。IO 四项 reload 后生效,无 pending restart。

执行记录:第一次把多条 `ALTER SYSTEM` 放在同一个 `psql -c` 内,PostgreSQL 返回 `ALTER SYSTEM cannot run inside a transaction block`;该语句未修改任何参数。随后按每条 `ALTER SYSTEM` 单独执行完成。

Note: `post_kernel_phase1_done`.

## 3. 阶段 2 Host profile

5 节点原 profile 均为 `balanced`,逐节点切换:

```bash
tuned-adm profile throughput-performance
tuned-adm active
sysctl vm.swappiness vm.dirty_ratio vm.dirty_background_ratio
```

每个节点切换后等待 30 秒,并验证:

- `docker ps` 中对应 `citus-*5488` 容器仍为 `Up`
- `pg_isready -h <node> -p 5488` 接受连接

最终:

| 节点 | before | after | vm.swappiness | vm.dirty_ratio | vm.dirty_background_ratio |
|---|---|---|---:|---:|---:|
| 192.168.200.217 | balanced | throughput-performance | 10 | 20 | 5 |
| 192.168.200.216 | balanced | throughput-performance | 10 | 20 | 5 |
| 192.168.200.219 | balanced | throughput-performance | 10 | 20 | 5 |
| 192.168.200.220 | balanced | throughput-performance | 10 | 20 | 5 |
| 192.168.200.221 | balanced | throughput-performance | 10 | 20 | 5 |

`TCL b7=340766`。未触发回滚。

Note: `post_kernel_phase2_done`.

## 4. 阶段 3 网络 backlog

5 节点写入并加载:

```text
# 提高连接排队上限,避免数据库连接高峰时系统队列太小
net.core.somaxconn = 4096
net.ipv4.tcp_max_syn_backlog = 4096
net.core.netdev_max_backlog = 30000
```

路径:

```text
/etc/sysctl.d/99-citus-network.conf
```

最终 5 节点 `sysctl`:

| 节点 | somaxconn | tcp_max_syn_backlog | netdev_max_backlog | drop-in |
|---|---:|---:|---:|---|
| 192.168.200.217 | 4096 | 4096 | 30000 | present |
| 192.168.200.216 | 4096 | 4096 | 30000 | present |
| 192.168.200.219 | 4096 | 4096 | 30000 | present |
| 192.168.200.220 | 4096 | 4096 | 30000 | present |
| 192.168.200.221 | 4096 | 4096 | 30000 | present |

`TCL b7=340766`。PG18 容器未重启;PG listen socket backlog 会在下次容器重启后自然拾取新的 `somaxconn`。

Note: `post_kernel_phase3_done`.

## 5. 阶段 4 综合验证

Citus health:

```text
citus_check_cluster_node_health(): 25/25 result=true
citus_get_active_worker_nodes(): 192.168.200.216/219/220/221:5488
```

数据基线:

```text
TCL b7 = 340766
cell_sliding_window = 24017207
```

`sentinels.sh 7`:

```text
enriched_current_batch_single_day PASS
sliding_span_no_old_future        PASS
step2_scope_clean_or_today        PASS
tcl_monotonic                     PASS
fail_count = 0
sentinel_ok = true
```

`endpoint_check.sh`:

```text
tcl_b7_vs_fix5_serial_pm5 PASS
tcl_b7_vs_pg17_pm20       PASS
sliding_endpoint_range    PASS
enriched_latest_batch     PASS
```

Single-batch smoke 未跑。本阶段是 OS / PG 启动参数收尾,为避免改写 batch 数据,保守留给后续维护窗口触发。

Note: `post_kernel_phase4_done`.

## 6. CLUSTER_USAGE.md §9 更新点

已将以下项目移到已生效清单:

- PG IO: `io_method=worker`, `io_workers=10`, `effective_io_concurrency=64`, `maintenance_io_concurrency=64`
- Host profile: `tuned-adm active=throughput-performance`
- Network sysctl: `/etc/sysctl.d/99-citus-network.conf` 中三项 backlog

待办仅保留 RAID 写入参数,按 user 指令推迟。

## 7. 已知限制 / 后续维护建议

1. PG18 容器本阶段未重启,因此 listen socket backlog 对新 `somaxconn` 的完整拾取留到下次容器重启。
2. RAID 写入参数属于 06 §9 项 6,本阶段按 user 指令不做。
3. `throughput-performance` 已稳定切换并通过健康检查;后续如果有完整 workload 基准,可再评估是否需要更细的 tuned profile。
4. 本阶段没有修改 WAL/checkpoint/parallel/cache 等业务 PG 参数,也没有修改 backend/app 代码。
