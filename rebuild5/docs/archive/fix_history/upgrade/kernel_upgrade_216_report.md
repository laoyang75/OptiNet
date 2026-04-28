# kernel-ml 6.6.12 升级试验报告(216 单机)

## 0. TL;DR

- 试验机: `192.168.200.216` worker
- 结果: **失败 / 已自动回退**
- 旧内核 fallback: `3.10.0-1160.71.1.el7.x86_64`，已保留且当前正在运行
- 新内核: `6.6.12-1.el7.elrepo.x86_64`，已安装到 `/boot`，但已取消默认启动
- 失败层: 阶段 4 系统层验证
- 触发原因: 新内核启动后 journal 出现新的 XFS warning:
  `XFS (md126p3): WARNING: Reset corrupted AGFL on AG 0. 6 blocks leaked. Please unmount and run xfs_repair.`
- 回退动作: `grubby --set-default=/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64` 后重启
- 最终状态: 旧内核启动成功，RAID 6/6 active，p1p1 10Gb link yes，Docker OK，PG18 `citus-worker-5488` 恢复
- Citus: 4 worker active，all workers PG18.3，health 全 true
- 数据基线: TCL b7=`340,766`，`cell_sliding_window`=`24,017,207`，与升级前完全一致
- 重启耗时: 新内核 SSH 恢复约 140s；回退旧内核 SSH 恢复约 143s
- notes: `kernel_216_phase1_done` / `kernel_216_phase2_done` / `kernel_216_phase3_done` / `kernel_216_failed` / `kernel_216_rollback_done`

## 1. 试验前快照(216)

采集时间: `2026-04-27 19:09:04 CST`

```text
uname:
Linux localhost.localdomain 3.10.0-1160.71.1.el7.x86_64 #1 SMP Tue Jun 28 15:37:28 UTC 2022 x86_64 x86_64 x86_64 GNU/Linux

grubby --default-kernel:
/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64

GRUB entries:
index=0 kernel=/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
index=1 kernel=/boot/vmlinuz-0-rescue-b9fb2af7904e414392b94158ec59c738
index=2 non linux entry
```

旧内核 fallback 文档已按 216 实测从原误记的 `.119.1` 修正为 `.71.1`。用户随后确认 216 有 IPMI/KVM/物理控制台可进入 GRUB。

完整快照已保存:

- `217:/data/upgrade/kernel-ml-6.6.12/backups/216-pre/system_pre.txt`
- `217:/data/upgrade/kernel-ml-6.6.12/backups/216-pre/grubby_pre.txt`
- `217:/data/upgrade/kernel-ml-6.6.12/backups/216-pre/docker_inspect_5488_pre.json`
- `217:/data/upgrade/kernel-ml-6.6.12/backups/216-pre/docker_inspect_5487_pre.json`
- `217:/data/upgrade/kernel-ml-6.6.12/backups/216-pre/journal_pre.txt`

## 2. Citus 健康基线(集群视角)

升级前基线:

```text
citus_check_cluster_node_health: 25/25 true
citus_get_active_worker_nodes: 216 / 219 / 220 / 221 on 5488
pg_dist_node: coordinator 217 shouldhaveshards=false; 4 workers shouldhaveshards=true
active / idle in transaction SQL: 0 rows
runner / psql clues: 0 rows
```

数据基线:

```text
trusted_cell_library:
b1=79,452
b2=158,068
b3=211,324
b4=252,687
b5=286,290
b6=314,489
b7=340,766

cell_sliding_window=24,017,207
```

归档: `217:/data/upgrade/kernel-ml-6.6.12/backups/216-pre/citus_baseline.txt`

## 3. kernel-ml 6.6.12 下载 + 安装

217 离线包目录: `217:/data/upgrade/kernel-ml-6.6.12/rpms/`

已缓存:

```text
kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
kernel-ml-devel-6.6.12-1.el7.elrepo.x86_64.rpm
kernel-ml-doc-6.6.12-1.el7.elrepo.noarch.rpm
kernel-ml-headers-6.6.12-1.el7.elrepo.x86_64.rpm
kernel-ml-tools-6.6.12-1.el7.elrepo.x86_64.rpm
kernel-ml-tools-libs-6.6.12-1.el7.elrepo.x86_64.rpm
kernel-ml-tools-libs-devel-6.6.12-1.el7.elrepo.x86_64.rpm
RPM-GPG-KEY-elrepo.org
elrepo-release-7.el7.elrepo.noarch.rpm
SHA256SUMS
RPM_VERIFY.txt
```

主 kernel RPM sha256:

```text
83dfe226203fe096796a96360a7195e5cc9b527b71792fcf70064839f4cfe2be  kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
```

`rpm -K` 在 EL7 输出格式为 `(sha1) dsa sha1 md5 gpg OK`，8 个 RPM 全部 `gpg OK`。

216 安装结果:

```text
yum -y --disablerepo="*" localinstall /tmp/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
Installed:
  kernel-ml.x86_64 0:6.6.12-1.el7.elrepo

GRUB after install:
index=0 kernel=/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64
index=1 kernel=/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64

default after install:
/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64
```

安装日志: `217:/data/upgrade/kernel-ml-6.6.12/logs/kernel_install_216.log`

## 4. 重启 + 系统层验证

新内核启动:

```text
reboot issued: 2026-04-27 19:23:35 CST
SSH ready: 2026-04-27 19:25:55 CST
uname: 6.6.12-1.el7.elrepo.x86_64
boot time: 2026-04-27 19:25:34 CST
```

系统层通过项:

```text
md126 RAID5: active, 6/6 devices
/ and /boot mounted as XFS
p1p1: 10000Mb/s, full duplex, link detected yes
docker info: OK
citus-worker-5488: Up
citus-worker-5487-pg17-fallback: Up
```

系统层失败项:

```text
XFS (md126p3): WARNING: Reset corrupted AGFL on AG 0. 6 blocks leaked. Please unmount and run xfs_repair.
```

pre-journal 中未发现同类 XFS warning。按 06 文档 §7 “能启动但磁盘或 RAID 异常 / 文件系统关键错误先回退旧内核”处理，没有继续 PG 写入或业务测试。

post-boot 日志:

- `217:/data/upgrade/kernel-ml-6.6.12/logs/216_post_boot_validation.log`
- `217:/data/upgrade/kernel-ml-6.6.12/logs/216_reboot.log`

## 5. 回退 + PG18 / Citus 恢复验证

回退动作:

```text
grubby --set-default=/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
rollback reboot start: 2026-04-27 19:26:52 CST
rollback SSH ready: 2026-04-27 19:29:15 CST
uname: 3.10.0-1160.71.1.el7.x86_64
boot time: 2026-04-27 19:28:51 CST
```

回退后系统层:

```text
GRUB default: /boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
/boot also still contains /boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64
md126 RAID5 active, 6/6 devices, failed devices 0
p1p1 10000Mb/s full duplex link yes
docker info OK
systemctl --failed: 0 loaded units
rollback boot journal: no XFS/kdump warning lines in sampled grep
```

回退后容器状态曾出现一个恢复问题: `citus-worker-5488` PG18 未自动占回 5488，旧归档 PG17 容器 `citus-worker-5488-pg17-archived-20260427_180341` 短暂占用了 host port 5488，导致一次 TCL 查询在 216 shard 上报缺表。已停止该归档容器并启动原 PG18 `citus-worker-5488`，未改 Docker 配置、未动数据卷。

最终容器状态:

```text
citus-worker-5487-pg17-fallback: Up healthy, 5487
citus-worker-5488: Up, 5488/5491
citus-worker-5488-pg17-archived-20260427_180341: Exited
```

最终 Citus 验证:

```text
coordinator version: PostgreSQL 18.3
all 4 workers version: PostgreSQL 18.3
citus_check_cluster_node_health: 25/25 true
citus_get_active_worker_nodes: 216 / 219 / 220 / 221 on 5488
pg_dist_node: all 4 workers active, shouldhaveshards=true
```

最终数据对账:

```text
trusted_cell_library:
b1=79,452
b2=158,068
b3=211,324
b4=252,687
b5=286,290
b6=314,489
b7=340,766

cell_sliding_window=24,017,207
```

数据基线与升级前完全一致。

## 6. 217 控制台归档

已创建并保留:

```text
/data/upgrade/kernel-ml-6.6.12/backups/216-pre/
/data/upgrade/kernel-ml-6.6.12/logs/
/data/upgrade/kernel-ml-6.6.12/rpms/
/data/upgrade/kernel-ml-6.6.12/scripts/source.txt
```

关键日志:

```text
logs/phase0_source_verify.log
logs/kernel_install_216.log
logs/216_reboot.log
logs/216_post_boot_validation.log
logs/216_rollback_validation.log
logs/kernel216_container_recovery.log
```

未生成成功复用脚本和 `REUSE_GUIDE.md`，因为本次 216 试验失败并已回退；后续不应把该流程作为成功模板直接复用。

## 7. 已知限制 / 给后续升级的输入

1. `kernel-ml 6.6.12` 可以启动到 SSH，但新内核下 root XFS 出现新的 AGFL warning。后续继续内核方向前，应先由人工判断是否需要在维护窗口做离线 `xfs_repair`，或改测别的 kernel-ml 版本。
2. 新内核已安装但不是默认启动；当前默认回到旧内核。若再次测试，必须重新 `grubby --set-default=/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64`。
3. 旧归档 PG17 容器 `citus-worker-5488-pg17-archived-20260427_180341` 在回退重启后曾自动占用 5488。后续重启前应处理其 restart policy 或确认不会抢占生产端口；本次按“不改 Docker 配置”约束只停止了该容器，没有修改配置。
4. 本次没有删除旧 3.10 内核，没有删除新 6.6.12 内核，没有动 PG/Docker 配置，没有动任何数据卷，没有对 Citus 做 drain/remove/rebalance。
