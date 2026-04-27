# OptiNet rebuild5 / kernel-ml 6.6.12 全集群升级(210 控制台)(agent 新实例对话)

## § 1 元目标

把 rebuild5 PG18/Citus 生产集群 5 台机器按顺序升级到 `kernel-ml 6.6.12-1.el7.elrepo.x86_64`，控制台改用 **192.168.200.210**，因为本轮包含 coordinator `192.168.200.217` 重启。升级方式继续沿用 `/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md` §3.1.1: 暂停写入、不 drain、不 remove、不 rebalance，保留原 IP/端口/数据目录/容器配置。

本 prompt 已吸收 216 单机试验结论: `6.6.12` 可启动，RAID/网络/Docker/PG18 能起来；新内核下出现的 XFS AGFL warning **按 user 指令忽略，不因它阻断、不自动回退**，后续由 user 自行安排 `xfs_repair` 维护窗口。

## § 2 上下文启动顺序

按序读完直接开干，不要开跑前 ack:

1. 仓库根目录 `AGENTS.md` —— 协作规约
2. `/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md` §3-§8 —— 只作为原始执行手册；其中旧内核 `.119.1` 已修正为 `.71.1`
3. `rebuild5/docs/fix6_optim/_prompt_template.md` §11/§12 —— 完工 commit/push/note 流程
4. `rebuild5/docs/upgrade/upgrade_v2_finalize_and_tuning_report.md` —— PG18 已切到 5488 生产
5. `rebuild5/docs/upgrade/kernel_upgrade_216_report.md` —— 216 试验 trail；重点看 XFS warning 和回退后 PG17 archived 容器抢 5488 的教训
6. `rb5_bench.notes` topic LIKE `'kernel_216%' OR topic LIKE 'upgrade_%'` —— 升级 trail
7. 本 prompt

## § 3 环境硬信息

### 控制台 / 登录

- **控制台**: `192.168.200.210`
- **所有机器登录**: `root / 111111`
- user 已确认有键盘 / IPMI / KVM / 物理控制台能力，遇到机器完全起不来可独立进 GRUB 选旧内核；**agent 不再二次询问这件事**
- 控制台所有下载、脚本、日志、报告镜像都放:
  - `210:/data/upgrade/kernel-ml-6.6.12/`
  - 如果 210 没有 `/data`，用 `210:/root/upgrade/kernel-ml-6.6.12/`，但必须把最终路径写入 report 和 notes

### 集群拓扑

| 节点 | IP | 角色 | port |
|---|---|---|---|
| worker | 192.168.200.216 | worker | 5488 PG18 生产 + 5487 PG17 fallback |
| worker | 192.168.200.219 | worker | 5488 PG18 生产 + 5487 PG17 fallback |
| worker | 192.168.200.220 | worker | 5488 PG18 生产 + 5487 PG17 fallback |
| worker | 192.168.200.221 | worker | 5488 PG18 生产 + 5487 PG17 fallback |
| coordinator | 192.168.200.217 | coordinator | 5488 PG18 生产 + 5487 PG17 fallback |

`5491` 只是历史临时端口/兼容 alias。Citus 元数据、生产 SQL、健康检查都用 `5488`。

### 固定版本和源

- 固定目标: `kernel-ml-6.6.12-1.el7.elrepo.x86_64`
- 主源: `https://mirrors.coreix.net/elrepo-archive-archive/kernel/el7/x86_64/RPMS/`
- 备用: `https://dtops.co/elrepo/elrepo-archive-archive/kernel/el7/x86_64/RPMS/`
- 不用清华/阿里当前 elrepo kernel 目录作为主源，它们可能没有旧版 6.6.12
- 210 上必须缓存:
  - 必装: `kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm`
  - 备用但不安装: `kernel-ml-devel-6.6.12-1.el7.elrepo.x86_64.rpm`, `kernel-ml-doc-6.6.12-1.el7.elrepo.noarch.rpm`, `kernel-ml-headers-6.6.12-1.el7.elrepo.x86_64.rpm`, `kernel-ml-tools-6.6.12-1.el7.elrepo.x86_64.rpm`, `kernel-ml-tools-libs-6.6.12-1.el7.elrepo.x86_64.rpm`, `kernel-ml-tools-libs-devel-6.6.12-1.el7.elrepo.x86_64.rpm`
  - `RPM-GPG-KEY-elrepo.org`
  - `elrepo-release-7.el7.elrepo.noarch.rpm`
  - `SHA256SUMS`, `RPM_VERIFY.txt`, `KERNEL_ML_SHA256.txt`

### 数据库

- Citus 主集群: `postgres://postgres:123456@192.168.200.217:5488/yangca`
- psql 兜底:
  ```bash
  PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca
  ```
- notes 表: `rb5_bench.notes(run_id, topic, severity, body, created_at)`
- 217 coordinator 重启期间 DB 不可用；notes 写不进时先写 `210:$BASE/logs/notes_pending.log`，217 恢复后补写摘要

### 216 试验结论

- 216 当前旧内核 fallback: `3.10.0-1160.71.1.el7.x86_64`
- 216 已安装过 `6.6.12-1.el7.elrepo.x86_64`，但当前默认回到旧内核；再次升级 216 时可跳过 yum install，只需验证 RPM/GRUB 后设默认
- 216 新内核启动后出现 XFS AGFL warning；user 指令: **忽略 XFS，不因它阻断**
- 216 回退时 `citus-worker-5488-pg17-archived-20260427_180341` 曾抢占 5488；本轮每台机器重启前必须处理 `*-pg17-archived-*` 抢 5488 风险

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md` | 阅读 | 原始 runbook；XFS 阻断策略被本 prompt 覆盖 |
| `rebuild5/docs/upgrade/kernel_upgrade_216_report.md` | 阅读 | 216 试验事实 |
| `rebuild5/docs/upgrade/kernel_upgrade_all_210_report.md` | 新建 | 本轮最终报告 |
| `rebuild5/docs/upgrade/README.md` | 修改 | 状态新增全集群内核升级结果 |

## § 5 任务清单

### 阶段 0:210 控制台准备 + 全局硬门槛

1. 在 210 建目录，验证空间:
   ```bash
   sshpass -p 111111 ssh -o StrictHostKeyChecking=no root@192.168.200.210 '
   set -euo pipefail
   BASE=/data/upgrade/kernel-ml-6.6.12
   if ! mkdir -p "$BASE"/{rpms,scripts,logs,backups,docs}; then
     BASE=/root/upgrade/kernel-ml-6.6.12
     mkdir -p "$BASE"/{rpms,scripts,logs,backups,docs}
   fi
   echo "$BASE" > /tmp/kernel_ml_base_path
   df -h "$BASE" /nas_vol8 2>/dev/null || df -h "$BASE"
   '
   ```

2. 在 210 验证源 URL 精确可达。若 210 CA 旧，允许 `curl -k -fI` / `wget --no-check-certificate`，因为后面必须做 `sha256sum` + `rpm -K`:
   ```bash
   curl -k -fI --max-time 20 https://mirrors.coreix.net/elrepo-archive-archive/kernel/el7/x86_64/RPMS/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
   curl -k -fI --max-time 20 https://www.elrepo.org/RPM-GPG-KEY-elrepo.org
   curl -k -fI --max-time 20 https://www.elrepo.org/elrepo-release-7.el7.elrepo.noarch.rpm
   ```

3. 全节点回退入口检查，不再问 user 是否有键盘:
   ```bash
   for n in 216 219 220 221 217; do
     sshpass -p 111111 ssh -o StrictHostKeyChecking=no root@192.168.200.$n '
       set -euo pipefail
       echo "=== node $(hostname) ==="
       uname -r
       grubby --default-kernel
       grubby --info=ALL | grep -E "^index=|^kernel="
       test -e /boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
       grep -E "^GRUB_TIMEOUT=" /etc/default/grub || true
     '
   done
   ```
   如果某节点没有旧内核文件或 GRUB 旧条目，blocker，不升级该节点。

4. 全节点快照归档到 210:
   - `uname -a`
   - `grubby --info=ALL`
   - `/proc/mdstat`
   - `mdadm --detail /dev/md126`
   - `lsblk`
   - `df -hT`
   - `mount | grep -E "nas_vol8|/data"`
   - `ip -br addr`
   - `ip route`
   - `docker ps -a`
   - `docker inspect citus-*-5488 / citus-*-5487-pg17-fallback`
   - `systemctl --failed`
   - `journalctl -p warning..alert -b`

5. 写 note `kernel_all_phase0_done`，body 含 210 BASE 路径、5 节点旧内核存在、user 已确认控制台能力。

### 阶段 1:Citus 健康基线 + 暂停写入证据

执行并保存到 `210:$BASE/backups/citus_baseline_pre.txt`:

```sql
SELECT * FROM citus_check_cluster_node_health();
SELECT * FROM citus_get_active_worker_nodes();
SELECT nodeid, nodename, nodeport, noderole, isactive, shouldhaveshards
FROM pg_dist_node
ORDER BY nodeid;

SELECT pid, usename, application_name, state, query_start, LEFT(query, 100)
FROM pg_stat_activity
WHERE datname='yangca'
  AND state IN ('active','idle in transaction')
  AND pid != pg_backend_pid()
ORDER BY query_start;

SELECT pid, usename, application_name, client_addr, state, wait_event_type, wait_event,
       now() - COALESCE(xact_start, query_start) AS age,
       LEFT(query, 160) AS query
FROM pg_stat_activity
WHERE datname='yangca'
  AND pid != pg_backend_pid()
  AND (
    state <> 'idle'
    OR application_name ILIKE '%runner%'
    OR application_name ILIKE '%psql%'
  )
ORDER BY age DESC NULLS LAST;

SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
SELECT COUNT(*) FROM rb5.cell_sliding_window;
```

预期:
- 4 worker active
- `citus_check_cluster_node_health` 全 true
- 无 active/idle in transaction 业务 SQL
- 无 runner/写入线索
- TCL b7=`340766`
- `cell_sliding_window`=`24017207`

有明显写入/长事务则 blocker，不升级。

### 阶段 2:210 离线包缓存 + 签名校验

优先从 217 已缓存目录复制到 210；如果 217 不可用或文件不全，再从 Coreix 下载:

```bash
BASE=$(sshpass -p 111111 ssh root@192.168.200.210 'cat /tmp/kernel_ml_base_path')
sshpass -p 111111 ssh root@192.168.200.210 "
set -euo pipefail
cd '$BASE/rpms'
SOURCE=https://mirrors.coreix.net/elrepo-archive-archive/kernel/el7/x86_64/RPMS
for rpm in \
  kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-devel-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-doc-6.6.12-1.el7.elrepo.noarch.rpm \
  kernel-ml-headers-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-tools-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-tools-libs-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-tools-libs-devel-6.6.12-1.el7.elrepo.x86_64.rpm
do
  test -s \"\$rpm\" || wget --no-check-certificate -O \"\$rpm\" --progress=dot:giga \"\$SOURCE/\$rpm\"
done
wget --no-check-certificate -O RPM-GPG-KEY-elrepo.org --progress=dot:giga https://www.elrepo.org/RPM-GPG-KEY-elrepo.org
wget --no-check-certificate -O elrepo-release-7.el7.elrepo.noarch.rpm --progress=dot:giga https://www.elrepo.org/elrepo-release-7.el7.elrepo.noarch.rpm
sha256sum *.rpm RPM-GPG-KEY-elrepo.org > SHA256SUMS
rpm --import RPM-GPG-KEY-elrepo.org || true
rpm -K *.rpm | tee RPM_VERIFY.txt
expected=\$(ls -1 *.rpm | wc -l)
ok=\$(grep -Ec 'gpg OK|digests signatures OK' RPM_VERIFY.txt || true)
test \"\$ok\" -eq \"\$expected\"
sha256sum kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm | tee KERNEL_ML_SHA256.txt
"
```

写 note `kernel_all_phase2_done`，body 含 7 个 RPM + key + sha256 + rpm 签名全 OK。

### 阶段 3:逐台 worker 升级(216 -> 219 -> 220 -> 221)

顺序必须一次一台，不并行:

```text
216, 219, 220, 221
```

每台节点 `<NODE>` 的步骤:

1. 重启前处理 archived PG17 抢 5488 风险。只处理名字含 `pg17-archived` 且端口含 `5488` 的归档容器，不改 PG18 生产容器、不改 5487 fallback:
   ```bash
   ssh root@<NODE> '
   set -euo pipefail
   docker ps -a --format "{{.Names}} {{.Ports}}" | awk "/pg17-archived/ && /5488/ {print \$1}" | while read c; do
     docker update --restart=no "$c" || true
     docker stop "$c" || true
   done
   '
   ```

2. 从 210 同步必装 RPM/key 到节点，安装或确认已安装:
   ```bash
   scp "$BASE/rpms/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm" "$BASE/rpms/RPM-GPG-KEY-elrepo.org" root@<NODE>:/tmp/
   ssh root@<NODE> '
   set -euo pipefail
   df -h /boot
   test -e /boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
   rpm --import /tmp/RPM-GPG-KEY-elrepo.org || true
   rpm -K /tmp/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm | tee /tmp/kernel_rpm_verify.txt
   grep -Eq "gpg OK|digests signatures OK" /tmp/kernel_rpm_verify.txt
   if ! rpm -q kernel-ml-6.6.12-1.el7.elrepo.x86_64 >/dev/null 2>&1; then
     yum -y --disablerepo="*" localinstall /tmp/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
   fi
   test -e /boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64
   grubby --set-default=/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64
   test "$(grubby --default-kernel)" = "/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64"
   '
   ```

3. reboot 并等待 SSH。10 分钟 SSH 不回来，写 blocker；user 自行键盘/GRUB 选旧内核:
   ```bash
   ssh root@<NODE> 'sync; sync; reboot' || true
   # 210 上每 15s ssh 检查 uname -r，最多 10 分钟
   ```

4. post-boot 系统验证:
   - `uname -r` 必须是 `6.6.12-1.el7.elrepo.x86_64`
   - `/proc/mdstat` RAID 6/6 active
   - `/`, `/boot`, `/data` 正常挂载
   - `p1p1` 10Gb link yes，或实际生产网卡 link yes
   - `docker info` OK
   - `citus-worker-5488` Up；若没起来，`docker start citus-worker-5488`
   - `citus-worker-5487-pg17-fallback` Up 或保持原本状态
   - `systemctl --failed`
   - `journalctl -p warning..alert -b`

5. **XFS 忽略规则(本 prompt 覆盖 06 文档):**
   - 忽略 `XFS ... Reset corrupted AGFL ... xfs_repair`、timestamp 2038、AGFL/leaked block 等 XFS warning
   - 不因 XFS warning 阻断、不自动回退、不在线执行 `xfs_repair`
   - 仅把 XFS warning 记录到 report 的 known issues

6. 仍然必须回退/阻断的严重异常:
   - RAID degraded / failed devices > 0
   - 根分区、`/boot`、`/data` 挂载失败或只读
   - 生产网卡无 link / IP 丢失 / 路由不通
   - Docker daemon 失败
   - PG18 `citus-worker-5488` 起不来或日志显示数据目录错误
   - Citus 从 coordinator 看该 worker 不 active，等待 5 分钟仍失败
   - 数据基线偏差

7. 每台 worker 完成后，从 coordinator 验证:
   ```sql
   SELECT * FROM citus_check_cluster_node_health();
   SELECT * FROM citus_get_active_worker_nodes();
   SELECT nodeid, nodename, nodeport, noderole, isactive, shouldhaveshards
   FROM pg_dist_node ORDER BY nodeid;
   SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
   SELECT COUNT(*) FROM rb5.cell_sliding_window;
   SELECT run_command_on_workers($$SELECT version();$$);
   ```

8. 每台写 note:
   - `kernel_all_worker_<NODE>_done` info
   - body 含 `uname`、SSH 恢复耗时、Citus active、数据一致、XFS warning 是否出现

### 阶段 4:升级 coordinator 217(最后执行)

前置条件:
- 216/219/220/221 全部 `uname -r = 6.6.12-1.el7.elrepo.x86_64`
- 4 worker Citus active
- 数据基线一致
- 210 上已有完整 RPM/key/scripts/logs

217 升级步骤:

1. 因 217 是 coordinator，重启期间 5488 DB 不可用。先写 210 本地 log:
   ```bash
   echo "217 coordinator upgrade start $(date)" >> "$BASE/logs/217_upgrade.log"
   ```

2. 同样处理 217 上 `pg17-archived` 抢 5488 风险，只处理 archived 容器。

3. 从 210 同步 RPM/key 到 217，`yum --disablerepo="*" localinstall`，设置 6.6.12 默认。

4. reboot 217，从 210 等待 SSH 最多 10 分钟。

5. 217 post-boot:
   - `uname -r = 6.6.12-1.el7.elrepo.x86_64`
   - RAID/mount/network/docker OK
   - `citus-coordinator-5488` Up；如未起，`docker start citus-coordinator-5488`
   - `citus-coordinator-5487-pg17-fallback` Up 或保持原本状态
   - XFS warning 按本 prompt 忽略并记录

6. coordinator 恢复后做全集群最终验证:
   ```sql
   SELECT version();
   SELECT run_command_on_workers($$SELECT version();$$);
   SELECT * FROM citus_check_cluster_node_health();
   SELECT * FROM citus_get_active_worker_nodes();
   SELECT nodeid, nodename, nodeport, noderole, isactive, shouldhaveshards
   FROM pg_dist_node ORDER BY nodeid;
   SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
   SELECT COUNT(*) FROM rb5.cell_sliding_window;
   ```

7. 写 note `kernel_all_coordinator_217_done`，并补写 217 离线期间 `notes_pending.log` 摘要。

### 阶段 5:最终归档

在 210 归档脚本:

- `scripts/install_kernel_on_node.sh`
- `scripts/post_boot_validation.sh`
- `scripts/rollback_to_old_kernel.sh`
- `docs/REUSE_GUIDE.md`

`rollback_to_old_kernel.sh` 必须使用:

```bash
OLD=/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
grubby --set-default="$OLD"
```

生成 `rebuild5/docs/upgrade/kernel_upgrade_all_210_report.md`，结构:

```markdown
# kernel-ml 6.6.12 全集群升级报告(210 控制台)

## 0. TL;DR
## 1. 210 控制台与离线包
## 2. 升级前 Citus / 数据基线
## 3. 各节点升级记录
## 4. XFS warning 记录(忽略项)
## 5. coordinator 217 重启记录
## 6. 最终 Citus / 数据对账
## 7. 210 归档脚本
## 8. 已知限制 / 后续 xfs_repair 维护建议
```

修改 `rebuild5/docs/upgrade/README.md` 加全集群升级状态。

### 阶段 6:commit + push + done note

只 add 本阶段文档产物:

- `rebuild5/docs/upgrade/kernel_upgrade_all_210_prompt.md`
- `rebuild5/docs/upgrade/kernel_upgrade_all_210_report.md`
- `rebuild5/docs/upgrade/README.md`

不要 add 其他用户未提交改动。

commit message:

```text
chore(rebuild5): kernel-ml 6.6.12 upgrade all nodes via 210 console

- Upgrade 216/219/220/221/217 to kernel-ml 6.6.12 using 210 as control console
- Preserve old 3.10.0-1160.71.1 kernel as GRUB fallback
- Keep Citus topology unchanged: no drain/remove/rebalance
- Treat XFS AGFL warning as recorded known issue per user decision, not a blocker
- Final Citus health and data baselines match

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push:

```bash
git push origin main
```

写 note `kernel_all_done` info，body 含 5 台 `uname`、4 worker active、数据一致、217 downtime、commit SHA。

## § 6 验证标准

1. 210 上有 7 个 RPM + GPG key + elrepo-release + SHA256SUMS + RPM_VERIFY
2. 5 台机器 `uname -r = 6.6.12-1.el7.elrepo.x86_64`
3. 5 台机器 `/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64` 仍在，GRUB 旧内核条目仍在
4. RAID active，failed devices = 0
5. 生产网卡 link yes
6. Docker daemon OK
7. PG18 5488 容器全部 Up
8. PG17 fallback 5487 不抢 5488
9. `citus_check_cluster_node_health()` 全 true
10. 4 worker active
11. TCL b7=`340766`，`cell_sliding_window`=`24017207`
12. XFS warning 可存在但只记录，不阻断
13. report / README 写入
14. commit + push 完成或明确 push pending
15. note `kernel_all_done` 写入

## § 7 不做 / 禁止项

- 不 drain / 不 remove / 不 rebalance Citus
- 不改 PG18 参数
- 不改 PG18 生产容器配置
- 不动任何 `/data/pgsql/...` 数据卷
- 不删除旧 3.10 内核
- 不删除新 6.6.12 内核
- 不在线运行 `xfs_repair`
- 不因 XFS AGFL warning 自动回退
- 不使用清华/阿里作为 6.6.12 主源
- 不在节点临时联网下载 RPM，必须从 210 缓存同步
- 不并行重启 worker
- 不 add/commit 用户其他未提交改动

## § 8 失败兜底

- SSH 10 分钟不回来: 写 blocker，user 通过键盘/IPMI/KVM 进 GRUB 选旧内核
- SSH 能通但严重异常: `bash rollback_to_old_kernel.sh <node_ip> --reboot`
- RAID degraded / mount 失败 / Docker daemon 失败 / PG18 5488 起不来: 自动回退该节点
- Citus 不 healthy: 等 5 分钟；仍不健康则回退最后升级节点
- 数据基线偏差: blocker，停止，不继续下一台
- 217 coordinator 重启失败: user 控制台选旧内核；210 保留日志
- XFS warning: 只记录，不回退，不阻断

## § 9 完工话术

成功:

> "kernel-ml 6.6.12 全集群升级完成。控制台 210 已缓存 7 个 RPM + GPG key + sha256/RPM_VERIFY。5 台当前 uname 均为 `6.6.12-1.el7.elrepo.x86_64`;旧 `3.10.0-1160.71.1` 均保留为 GRUB fallback。Citus 4 worker active，`citus_check_cluster_node_health()` 全 true，数据基线 TCL b7=340766 / sliding=24017207 完全一致。XFS AGFL warning 已按 user 指令记录为 known issue，不阻断。报告 `kernel_upgrade_all_210_report.md` 已写入。commit=<SHA>(push <成功/pending>)。notes `kernel_all_done` 已插入。"

失败:

> "kernel-ml 6.6.12 全集群升级失败于 <节点>/<阶段>。blocker=<一句话>。当前状态:<已回退旧内核 / 等 user 控制台 / Citus 不健康 / 数据偏差>。已写 notes。210 日志在 `<BASE>/logs/`。未继续后续节点。"
