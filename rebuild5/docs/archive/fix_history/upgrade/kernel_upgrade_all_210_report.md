# kernel-ml 6.6.12 全集群升级报告(210 控制台)

## 0. TL;DR

- 结果: **完成**。
- 控制台: `192.168.200.210`
- 归档目录: `210:/data/upgrade/kernel-ml-6.6.12/`
- 升级节点顺序: `216 -> 219 -> 220 -> 221 -> 217`
- 当前 5 台 `uname -r` 均为 `6.6.12-1.el7.elrepo.x86_64`。
- 5 台均保留 `/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64` 作为 GRUB fallback。
- Citus 拓扑未变: 不 drain、不 remove、不 rebalance，生产仍是 `192.168.200.217:5488/yangca`。
- 最终 Citus health: 25/25 true，4 workers active。
- 数据基线一致: TCL b7=`340766`，`cell_sliding_window`=`24017207`。
- 217 coordinator 重启到 PG ready 耗时 `162s`。
- 本轮未观察到 `Reset corrupted AGFL`；各节点均有新内核 XFS timestamp 2038 warning，按 user 指令记录并忽略。

## 1. 210 控制台与离线包

210 归档目录:

```text
/data/upgrade/kernel-ml-6.6.12/
```

已缓存并校验:

- 7 个 `kernel-ml 6.6.12` RPM
- `elrepo-release-7.el7.elrepo.noarch.rpm`
- `RPM-GPG-KEY-elrepo.org`
- `SHA256SUMS`
- `RPM_VERIFY.txt`
- `KERNEL_ML_SHA256.txt`

主 kernel RPM sha256:

```text
83dfe226203fe096796a96360a7195e5cc9b527b71792fcf70064839f4cfe2be  kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
```

`rpm -K` 在 210 上 8 个 RPM 均为 `gpg OK`。

## 2. 升级前 Citus / 数据基线

升级前基线保存于:

```text
210:/data/upgrade/kernel-ml-6.6.12/backups/citus_baseline_pre.txt
```

基线结果:

- `citus_check_cluster_node_health()`: 25/25 true
- active workers: `216/219/220/221` on `5488`
- `pg_dist_node`: coordinator `217` shouldhaveshards=false，4 workers shouldhaveshards=true
- active / idle-in-transaction 业务 SQL: 0
- runner / 写入线索: 0
- TCL b7: `340766`
- `cell_sliding_window`: `24017207`

## 3. 各节点升级记录

| 节点 | 角色 | SSH 恢复耗时 | 结果 |
|---|---|---:|---|
| 192.168.200.216 | worker | 146s | PASS |
| 192.168.200.219 | worker | 92s | PASS |
| 192.168.200.220 | worker | 92s | PASS |
| 192.168.200.221 | worker | 93s | PASS |
| 192.168.200.217 | coordinator | 162s, PG ready 162s | PASS |

每台升级前均停止了仅名字含 `pg17-archived` 且端口含 `5488` 的归档 PG17 容器 restart/运行风险。PG18 生产容器和 PG17 `5487` fallback 配置未改。

最终节点核验:

- 216/219/220/221: RAID `6/6`, failed devices `0`
- 217: RAID `5/5`, failed devices `0`
- 5 台 `p1p1` link detected yes, 10Gb
- 5 台 Docker daemon OK
- PG18 `5488` 容器全部 Up
- PG17 fallback 仅暴露 `5487`，未抢占 `5488`

## 4. XFS warning 记录(忽略项)

本轮 5 台新内核 boot journal 均记录了类似:

```text
xfs filesystem being mounted/remounted ... supports timestamps until 2038-01-19
```

本轮未观察到 216 单机试验中的:

```text
Reset corrupted AGFL ... blocks leaked ... run xfs_repair
```

按 user 指令，XFS AGFL / timestamp / leaked block 类 warning 仅记录为 known issue，不阻断、不回退、不在线执行 `xfs_repair`。

额外记录: 217 本次 boot journal 有一次 `ata6` `BadCRC` / link reset warning；pre 快照中已有 `ata6` exception / SError 历史，且本次 reset 后 `mdadm` 为 clean/active、failed devices `0`，Citus 和数据对账均通过。建议后续在硬件维护窗口检查 217 对应 SATA 链路/线缆/盘健康。

## 5. coordinator 217 重启记录

217 重启期间 5488 短暂不可用:

```text
reboot start: 2026-04-27 20:08:01 CST
SSH ready:    2026-04-27 20:10:43 CST, elapsed=162s
PG ready:     2026-04-27 20:10:43 CST, elapsed=162s
```

恢复后:

- `citus-coordinator-5488` Up
- `citus-coordinator-5487-pg17-fallback` Up healthy
- PG17 archived coordinator container Exited，不暴露 5488

## 6. 最终 Citus / 数据对账

最终验证保存于:

```text
210:/data/upgrade/kernel-ml-6.6.12/logs/final_citus_after_217.log
```

结果:

- coordinator: PostgreSQL 18.3
- all workers: PostgreSQL 18.3
- `citus_check_cluster_node_health()`: 25/25 true
- active workers: 4
- `pg_dist_node`: 217 coordinator + 216/219/220/221 workers, all `5488`, all active
- TCL counts:
  - b1=`79452`
  - b2=`158068`
  - b3=`211324`
  - b4=`252687`
  - b5=`286290`
  - b6=`314489`
  - b7=`340766`
- `cell_sliding_window`: `24017207`

## 7. 210 归档脚本

210 已归档:

```text
/data/upgrade/kernel-ml-6.6.12/scripts/install_kernel_on_node.sh
/data/upgrade/kernel-ml-6.6.12/scripts/post_boot_validation.sh
/data/upgrade/kernel-ml-6.6.12/scripts/rollback_to_old_kernel.sh
/data/upgrade/kernel-ml-6.6.12/docs/REUSE_GUIDE.md
```

`rollback_to_old_kernel.sh` 固定使用:

```bash
OLD=/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
grubby --set-default="$OLD"
```

关键日志:

```text
logs/install_<node>.log
logs/<node>_reboot.log
logs/<node>_post_boot_validation.log
logs/<node>_citus_after.log
logs/final_node_validation_summary.txt
logs/final_citus_after_217.log
```

## 8. 已知限制 / 后续 xfs_repair 维护建议

1. 旧 `3.10.0-1160.71.1` 内核已保留，但当前默认启动项是 `6.6.12-1.el7.elrepo.x86_64`。
2. PG17 fallback `5487` 仍保留；归档 PG17 容器对象仍保留但不应暴露 `5488`。
3. XFS warning 按本次 user 决策只记录不阻断。若后续再出现 AGFL/leaked block warning，建议安排离线维护窗口执行 `xfs_repair`，不要在线执行。
4. 217 有历史和本次均出现过 `ata6` 链路/SError 记录；当前 RAID clean/active、failed=0，但建议后续硬件巡检。
5. 本轮没有改 PG 参数、Docker 配置、数据卷、Citus 元数据或 shard 分布。
