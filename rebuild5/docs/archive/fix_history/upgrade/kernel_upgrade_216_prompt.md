# OptiNet rebuild5 / kernel-ml 6.6.12 升级试验(216 单机)(agent 新实例对话)

## § 1 元目标

按 `/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md` § 3.1.1 **首选方式**(暂停写入 + 不从 Citus 元数据摘除),在 **192.168.200.216** 单台 worker 上试装 `kernel-ml 6.6.12`,**为后续其他 4 台机器升级铺路**。

**关键约束**(user 拍板):

- 这是**单机试验**,**仅 216**,217/219/220/221 不动
- **217 作控制台**:所有下载文件、安装包、回退脚本都先存在 217 的 NAS 共享路径或本地路径,为未来 217/219/220/221 升级**直接复用**
- 不删除旧内核 `3.10.0-1160.71.1.el7.x86_64`(回退入口)
- 注:216 阶段 0 实测当前可启动旧内核为 `3.10.0-1160.71.1.el7.x86_64`;原文档/早期 prompt 写成 `.119.1` 是版本误记,已按 user 确认修正
- 不从 Citus 元数据摘除 216(走 § 3.1.1 不走 § 3.1.2 drain)
- 试验期间业务暂停写入(user 自行控制)
- **数据不会丢失**:即使新内核启动失败,GRUB 选老内核能恢复
- **稳妥优先,不追最新**:本轮固定 `kernel-ml 6.6.12`,不要改成当前最新 kernel-ml
- **尽量自动化**:除"机器完全起不来必须进物理/IPMI/KVM 选旧内核"外,其余步骤都由 agent 自动推进
- **不要临用临下**:所有安装包、备用包、GPG key、安装脚本、回退脚本必须在重启前完整下载/归档到 217
- 安全不是本地老机器升级的首要目标,但 sha256 / rpm 签名校验仍要做,目的主要是避免包损坏或下载错包

## § 2 上下文启动顺序

按序读完直接开干:

1. 仓库根目录 `AGENTS.md`
2. `/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md` —— **本阶段执行手册**,§ 3-§ 8 全读
3. `rebuild5/docs/fix6_optim/_prompt_template.md` § 11/§ 12
4. `rebuild5/docs/upgrade/upgrade_v2_finalize_and_tuning_report.md` —— PG18 集群已切到 5488 生产
5. `rb5_bench.notes` topic LIKE `'upgrade_%'` —— 升级 trail
6. 本 prompt

读完直接开干。

## § 3 环境硬信息

### 集群拓扑(关键:文档里写 5491 是历史 port,实际生产是 5488)

| 节点 | IP | 角色 | port |
|---|---|---|---|
| coordinator + 跳板 + 控制台 | 192.168.200.217 | coordinator | **5488 生产** + 5487 PG17 fallback |
| worker(本次试验目标) | **192.168.200.216** | worker | **5488 生产** + 5487 PG17 fallback |
| worker | 192.168.200.219 | worker | 5488 + 5487 |
| worker | 192.168.200.220 | worker | 5488 + 5487 |
| worker | 192.168.200.221 | worker | 5488 + 5487 |

**注意**:06 文档里 § 3.1 提到 "5491" 是 v2 升级期间的临时 port,**实际生产已切到 5488**。所有 SQL / 容器名都用 5488 (`citus-worker-5488` 而非 `citus-worker-5491-fresh`)。每台机器还有 `citus-coordinator-5487-pg17-fallback` 或 `citus-worker-5487-pg17-fallback`(老 PG17 集群,内核重启时也会自动 restart)。

### 服务器登录

- **所有机器**:root / 111111
- **跳板**:user 本地 → 217 → 其他 worker

### NAS 共享 + 217 本地路径

- **NAS**:`/nas_vol8`(5 台都挂载,生产稳定)
- **217 本地**(本次新建):`/data/upgrade/kernel-ml-6.6.12/`(后续其他机器复用,**所有下载/安装/回退脚本都放这里**)

### 下载策略(关键)

- 固定目标版本:`kernel-ml-6.6.12-1.el7.elrepo.x86_64`
- 主下载源用 ELRepo archive mirror,不要用当前 elrepo kernel 目录赌旧包还在:
  - 主:`https://mirrors.coreix.net/elrepo-archive-archive/kernel/el7/x86_64/RPMS/`
  - 备用:`https://dtops.co/elrepo/elrepo-archive-archive/kernel/el7/x86_64/RPMS/`
- 已验证清华 / 阿里当前目录可能只保留 `elrepo-release`,精确旧包 URL 会 404,**不能作为 kernel-ml 6.6.12 主源**
- 重启前必须下载到 217:
  - 必装:`kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm`
  - 备用但本轮不安装:`kernel-ml-devel-6.6.12-1.el7.elrepo.x86_64.rpm`,`kernel-ml-doc-6.6.12-1.el7.elrepo.noarch.rpm`,`kernel-ml-headers-6.6.12-1.el7.elrepo.x86_64.rpm`,`kernel-ml-tools-6.6.12-1.el7.elrepo.x86_64.rpm`,`kernel-ml-tools-libs-6.6.12-1.el7.elrepo.x86_64.rpm`,`kernel-ml-tools-libs-devel-6.6.12-1.el7.elrepo.x86_64.rpm`
  - 校验辅助:`RPM-GPG-KEY-elrepo.org`,`elrepo-release-7.el7.elrepo.noarch.rpm`
- 安装阶段必须使用 217 本地已缓存 RPM,不允许到 216 上临时联网下载

### 数据库连接(只读用)

- Citus 主集群:`postgres://postgres:123456@192.168.200.217:5488/yangca`,MCP `mcp__PG_Citus__execute_sql`
- 5487 老 PG17 fallback:psql 直连 `-p 5487`(本阶段不用)

### 当前数据

- 4 worker 各 266 placement,216 上有 ~26GB shard data(unique 副本,丢了不能恢复)
- 升级期间 216 离线 = 集群 26% shard 不可访问,**所以 user 已要求暂停写入**

## § 4 关联文档清单

| 路径 | 阅读 / 修改 |
|---|---|
| `/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md` | 阅读(执行手册)|
| 本阶段产出 `kernel_upgrade_216_report.md` | 新建 |
| `rebuild5/docs/upgrade/README.md` | 修改(状态新增内核升级条目)|

**不动业务代码 / 不改 PG18 配置 / 不改 Docker 容器配置**(本阶段只改宿主机内核)。

## § 5 任务清单

### 阶段 0:试验前快照(在 217 上,~10 分钟)

#### 5.0.1 217 准备控制台目录 + 下载源验证

```bash
ssh root@192.168.200.217 '
set -euo pipefail
mkdir -p /data/upgrade/kernel-ml-6.6.12/{rpms,scripts,logs,backups,docs}
df -h /data /nas_vol8

# 验证精确旧包 URL,必须 200;当前清华/阿里目录可能没有 6.6.12,不能只测目录可达
curl -fI --max-time 15 https://mirrors.coreix.net/elrepo-archive-archive/kernel/el7/x86_64/RPMS/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
curl -fI --max-time 15 https://www.elrepo.org/RPM-GPG-KEY-elrepo.org
curl -fI --max-time 15 https://www.elrepo.org/elrepo-release-7.el7.elrepo.noarch.rpm

cat > /data/upgrade/kernel-ml-6.6.12/scripts/source.txt << "EOF"
PRIMARY_KERNEL_ARCHIVE=https://mirrors.coreix.net/elrepo-archive-archive/kernel/el7/x86_64/RPMS
FALLBACK_KERNEL_ARCHIVE=https://dtops.co/elrepo/elrepo-archive-archive/kernel/el7/x86_64/RPMS
ELREPO_GPG_KEY=https://www.elrepo.org/RPM-GPG-KEY-elrepo.org
ELREPO_RELEASE=https://www.elrepo.org/elrepo-release-7.el7.elrepo.noarch.rpm
NOTE=Do not use current TUNA/Aliyun elrepo kernel directory as primary source for 6.6.12; exact old RPM can 404 there.
EOF
'
```

如果 Coreix 不可达,换备用 archive 源,但必须验证精确 RPM URL 返回 200,并把最终源写进 `/data/upgrade/kernel-ml-6.6.12/scripts/source.txt`。

#### 5.0.2 回退入口硬门槛(重启前必须过)

```bash
ssh -J root@192.168.200.217 root@192.168.200.216 '
set -euo pipefail
echo "=== current kernel ==="
uname -r

echo "=== grub default ==="
grubby --default-kernel

echo "=== grub entries ==="
grubby --info=ALL | grep -E "^index=|^kernel="

echo "=== grub timeout ==="
grep -E "^GRUB_TIMEOUT=" /etc/default/grub || true

echo "=== old kernel exists ==="
test -e /boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
'
```

**硬门槛**:
- `/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64` 必须存在
- `grubby --info=ALL` 必须能看到旧 3.10 条目
- 必须有物理控制台 / IPMI / 远程 KVM / 本地显示器键盘中的一种方式能进 GRUB 选旧内核
- 如果无法确认控制台回退能力,**不要 reboot**,写 `kernel_216_failed` blocker;这是本阶段唯一允许停下来让 user 处理的前置风险

#### 5.0.3 216 试验前快照(都存到 217 上)

```bash
ssh -J root@192.168.200.217 root@192.168.200.216 '
set -euo pipefail
hostname
uname -a
grubby --default-kernel
{
  echo "=== hostname ==="; hostname
  echo "=== uname ==="; uname -a
  echo "=== grub default ==="; grubby --default-kernel
  echo "=== grubby all ==="; grubby --info=ALL
  echo "=== mdstat ==="; cat /proc/mdstat
  echo "=== lsblk ==="; lsblk
  echo "=== df ==="; df -hT
  echo "=== mounts ==="; mount | grep -E "nas_vol8|/data" || true
  echo "=== ip addr ==="; ip -br addr
  echo "=== route ==="; ip route
  echo "=== docker ps ==="; docker ps -a
  echo "=== systemctl failed ==="; systemctl --failed
} > /tmp/system_pre.txt
grubby --info=ALL > /tmp/grubby_pre.txt
cat /proc/mdstat
lsblk
df -hT
mount | grep -E "nas_vol8|/data"
ip -br addr
ip route
docker ps -a
docker inspect citus-worker-5488 > /tmp/docker_inspect_5488_pre.json
docker inspect citus-worker-5487-pg17-fallback > /tmp/docker_inspect_5487_pre.json 2>/dev/null || true
systemctl --failed
journalctl -p warning..alert -b > /tmp/journal_pre.txt
'

# 把快照拉到 217 控制台保存
ssh root@192.168.200.217 '
mkdir -p /data/upgrade/kernel-ml-6.6.12/backups/216-pre/
scp root@192.168.200.216:/tmp/grubby_pre.txt \
    root@192.168.200.216:/tmp/system_pre.txt \
    root@192.168.200.216:/tmp/docker_inspect_5488_pre.json \
    root@192.168.200.216:/tmp/docker_inspect_5487_pre.json \
    root@192.168.200.216:/tmp/journal_pre.txt \
    /data/upgrade/kernel-ml-6.6.12/backups/216-pre/
'
```

写 note `topic='kernel_216_phase0_done'`,body 含 216 当前内核 + 现有 docker 容器名。

### 阶段 1:Citus 健康基线 + 暂停写入确认(~5 分钟)

#### 5.1.1 Coordinator 健康检查(via 5488 MCP)

```sql
SELECT * FROM citus_check_cluster_node_health();
SELECT * FROM citus_get_active_worker_nodes();
SELECT nodeid, nodename, nodeport, noderole, isactive, shouldhaveshards
FROM pg_dist_node
ORDER BY nodeid;

-- 当前活跃业务 SQL 检查
SELECT pid, usename, application_name, state, query_start, LEFT(query, 100)
FROM pg_stat_activity
WHERE datname='yangca'
  AND state IN ('active','idle in transaction')
  AND pid != pg_backend_pid()
ORDER BY query_start;

-- 后台写入 / 跑数进程线索(应为空或只剩当前检查连接)
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
```

**预期**:4 worker 全 active / shouldhaveshards=true / 无长事务、无跑数进程、无业务写入。业务暂停由 user 控制,但 agent 必须用上面 SQL 做证据快照;如果仍有明显写入/长事务,写 blocker,不要 reboot。

#### 5.1.2 数据基线(快照)

```sql
SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY 1 ORDER BY 1;
-- 期待 7 batch 全有,batch 7 = 340766
SELECT COUNT(*) FROM rb5.cell_sliding_window;
-- 期待 24,017,207
```

把这两个数字记进 `/data/upgrade/kernel-ml-6.6.12/backups/216-pre/citus_baseline.txt`,升级后对账用。

写 note `topic='kernel_216_phase1_done'` info,body 含 4 worker 全 active + 数据基线。

### 阶段 2:下载 kernel-ml 6.6.12 离线包到 217(~10-20 分钟)

```bash
ssh root@192.168.200.217 '
set -euo pipefail
cd /data/upgrade/kernel-ml-6.6.12/rpms

SOURCE="https://mirrors.coreix.net/elrepo-archive-archive/kernel/el7/x86_64/RPMS"

# 必装包 + 备用包全部提前下载到 217,避免升级时临用临下
for rpm in \
  kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-devel-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-doc-6.6.12-1.el7.elrepo.noarch.rpm \
  kernel-ml-headers-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-tools-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-tools-libs-6.6.12-1.el7.elrepo.x86_64.rpm \
  kernel-ml-tools-libs-devel-6.6.12-1.el7.elrepo.x86_64.rpm
do
  test -s "$rpm" || wget -O "$rpm" --progress=dot:giga "${SOURCE}/${rpm}"
done

# 校验辅助文件也提前缓存;安全不是首要,但能避免包损坏/拿错包
wget -O RPM-GPG-KEY-elrepo.org --progress=dot:giga https://www.elrepo.org/RPM-GPG-KEY-elrepo.org
wget -O elrepo-release-7.el7.elrepo.noarch.rpm --progress=dot:giga https://www.elrepo.org/elrepo-release-7.el7.elrepo.noarch.rpm

sha256sum *.rpm RPM-GPG-KEY-elrepo.org > SHA256SUMS

# rpm 签名校验:如果缺 key 先 import;校验输出归档,失败就停
rpm --import RPM-GPG-KEY-elrepo.org || true
rpm -K *.rpm | tee RPM_VERIFY.txt
grep -v "digests signatures OK" RPM_VERIFY.txt && exit 1 || true

ls -lh
'
```

如果 Coreix 慢或不可达,换 § 3 `FALLBACK_KERNEL_ARCHIVE`,但仍要把 7 个 RPM + key + elrepo-release 全部下载完并校验后再继续。**不要把清华/阿里当前目录当主源**,它们的精确 6.6.12 RPM 可能 404。

写 note `topic='kernel_216_phase2_done'`,body 含最终 SOURCE、7 个 RPM 文件名、`kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm` sha256、`RPM_VERIFY.txt` 结果。

### 阶段 3:在 216 上安装 kernel-ml(不重启)(~5 分钟)

#### 5.3.1 同步 rpm 到 216

```bash
ssh root@192.168.200.217 '
set -euo pipefail
scp /data/upgrade/kernel-ml-6.6.12/rpms/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm \
    /data/upgrade/kernel-ml-6.6.12/rpms/RPM-GPG-KEY-elrepo.org \
    root@192.168.200.216:/tmp/
'
```

#### 5.3.2 在 216 上 yum localinstall

```bash
ssh -J root@192.168.200.217 root@192.168.200.216 '
set -euo pipefail
# 先确认 /boot 空间
df -h /boot

# 安装前校验本地 RPM;只 install,不 update,不删旧内核,不联网拉依赖
rpm --import /tmp/RPM-GPG-KEY-elrepo.org || true
rpm -K /tmp/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm | tee /tmp/kernel_rpm_verify.txt
grep -q "digests signatures OK" /tmp/kernel_rpm_verify.txt
yum -y --disablerepo="*" localinstall /tmp/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm

# 验证装成功 + 旧内核仍在
grubby --info=ALL
ls /boot/vmlinuz-*
'
```

**预期**:`/boot` 出现 `vmlinuz-6.6.12-1.el7.elrepo.x86_64` 同时旧 `vmlinuz-3.10.0-1160.71.1.el7.x86_64` 仍在。

#### 5.3.3 把新内核设为默认启动(为自动化明确允许)

```bash
ssh -J root@192.168.200.217 root@192.168.200.216 '
set -euo pipefail
# 看新内核的 GRUB index
grubby --info=ALL | grep -E "^index|^kernel"

# 注意:grubby --set-default 是持久默认,不是一次性软设置。
# 本轮为尽量自动化,明确允许先把 6.6.12 设为默认;旧 3.10 仍保留为 GRUB 回退入口。
grubby --set-default=/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64

# 验证
grubby --default-kernel
test "$(grubby --default-kernel)" = "/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64"
'
```

**预期**:`grubby --default-kernel` 返回 6.6.12 路径。**旧 3.10 内核仍可在 GRUB 菜单选择**(回退入口)。如果成功后 user 想改回旧内核默认,使用阶段 6 归档的 rollback 脚本。

写 note `topic='kernel_216_phase3_done'`,body 含 grubby 状态。

### 阶段 4:重启 216 + 启动验证(~10-15 分钟)

#### 5.4.1 重启前最后确认

```bash
# 在 217 上确认监控已就位
ssh root@192.168.200.217 'echo "Pre-reboot timestamp: $(date)" >> /data/upgrade/kernel-ml-6.6.12/logs/216_reboot.log'
ssh -J root@192.168.200.217 root@192.168.200.216 'sync; sync; sync'
```

#### 5.4.2 重启 216

```bash
ssh -J root@192.168.200.217 root@192.168.200.216 'reboot' &
# 然后等待 ~3-5 分钟
```

#### 5.4.3 重启后等待 + ping 检查

```bash
# 在 217 上每 30 秒 ping 一次,直到 216 回来或 10 分钟超时
ssh root@192.168.200.217 '
set -euo pipefail
for i in $(seq 1 20); do
  if ping -c 1 -W 2 192.168.200.216 > /dev/null 2>&1; then
    echo "216 alive at $(date)"
    exit 0
  fi
  echo "Waiting for 216... ($i/20)"
  sleep 30
done
echo "216 did not return within 10 minutes at $(date)" >&2
exit 1
'
```

**如果 10 分钟没回来**:**216 启动失败**,需要 user / 数据中心人员通过 IPMI / 物理控制台进入 GRUB 选老内核。**Agent 不能自己解决**,写 blocker note + 报告。

#### 5.4.4 验证新内核已启动 + 系统层

按 06 文档 § 5 跑全套验证:

```bash
ssh root@192.168.200.217 '
set -euo pipefail
ssh root@192.168.200.216 '"'"'
set -euo pipefail
echo "=== uname ==="
uname -r        # 期待 6.6.12-1.el7.elrepo.x86_64

echo "=== mdstat ==="
cat /proc/mdstat

echo "=== lsblk ==="
lsblk

echo "=== mounts ==="
df -hT
mount | grep -E "nas_vol8|/data"

echo "=== network ==="
ip -br addr
ip route
ethtool p1p1 2>/dev/null | head -20 || ethtool $(ip -o link | awk -F\: "{print \$2}" | grep -v lo | head -1) | head -20

echo "=== docker ==="
docker info > /dev/null 2>&1 && echo "docker info OK" || echo "DOCKER FAIL"
docker ps

echo "=== systemd ==="
systemctl --failed

echo "=== journal ==="
journalctl -p warning..alert -b | tail -20
'"'"' > /data/upgrade/kernel-ml-6.6.12/logs/216_post_boot_validation.log 2>&1
'
```

**判断**:
- `uname -r` = 6.6.12 → 新内核启动成功
- mdstat / lsblk / df / 网络 / docker / journal 无关键错误 → 系统层 PASS
- 任意一项异常 → 立刻 blocker,**走 06 文档 § 7 失败分层判断**(不要硬继续)

写 note `topic='kernel_216_phase4_done'` info,body 含 uname 输出 + 系统层 PASS/FAIL 各项。

### 阶段 5:PG18 容器 + Citus 验证(~10 分钟)

#### 5.5.1 检查容器自启动情况

```bash
ssh -J root@192.168.200.217 root@192.168.200.216 '
docker ps -a
# 期待 citus-worker-5488 状态 Up
# 期待 citus-worker-5487-pg17-fallback 状态 Up(若之前在跑)
'
```

如果 5488 worker 容器没自动起来(`--restart unless-stopped` 应该会启动,但如果没有):
```bash
ssh -J root@192.168.200.217 root@192.168.200.216 '
set -euo pipefail
docker start citus-worker-5488
docker logs --tail 100 citus-worker-5488
'
```

#### 5.5.2 PG18 worker 健康检查

```bash
# 从 217 直接 psql 216 worker(用 5488 worker 的 internal port,通过 docker port mapping)
ssh root@192.168.200.217 '
PGPASSWORD=123456 psql -h 192.168.200.216 -p 5488 -U postgres -d yangca \
  -c "SELECT version(); SELECT count(*) FROM pg_class WHERE relkind = chr(114);" 2>&1
'
```

#### 5.5.3 Citus coordinator 视角验证

按 06 文档 § 3.1.1 末尾:

```sql
-- via 5488 MCP coordinator
SELECT * FROM citus_check_cluster_node_health();
SELECT * FROM citus_get_active_worker_nodes();
SELECT nodeid, nodename, nodeport, noderole, isactive, shouldhaveshards
FROM pg_dist_node ORDER BY nodeid;

-- 数据基线对账(应与阶段 1.2 完全一致)
SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY 1 ORDER BY 1;
SELECT COUNT(*) FROM rb5.cell_sliding_window;
```

**验收**:
- citus_check_cluster_node_health 全 'healthy'
- 4 worker 全 active(包括 216)
- 数据基线 100% 一致(数据没动,任何偏差都是异常)

#### 5.5.4 (可选)单批 smoke 跑

默认不另行询问。若 agent 判断脚本只读且业务仍暂停,可以跑一个最小验证;如果脚本会写入或会触发重跑,标 `skipped`:

```bash
# 不在本阶段强制,标"skipped"也接受。如果跑:
bash rebuild5/scripts/runbook/sentinels.sh 7
bash rebuild5/scripts/runbook/endpoint_check.sh
# 期待和阶段 1.2 一样全 PASS
```

写 note `topic='kernel_216_phase5_done'`,body 含 citus_check_cluster_node_health 状态 + 4 worker active + 数据一致性确认。

### 阶段 6:把成功配置 + 脚本归档到 217(给 217/219/220/221 复用)(~5 分钟)

```bash
ssh root@192.168.200.217 '
set -euo pipefail
cd /data/upgrade/kernel-ml-6.6.12/

# 1. 整理脚本(从本次 216 升级抽出步骤,做成 reusable)
cat > scripts/install_kernel_on_worker.sh << "EOF"
#!/usr/bin/env bash
# Usage: bash install_kernel_on_worker.sh <node_ip>
# Run from 217. Pre-req: all RPMs already downloaded to /data/upgrade/kernel-ml-6.6.12/rpms/

set -euo pipefail
NODE=${1:?node_ip required}
RPM=/data/upgrade/kernel-ml-6.6.12/rpms/kernel-ml-6.6.12-1.el7.elrepo.x86_64.rpm
KEY=/data/upgrade/kernel-ml-6.6.12/rpms/RPM-GPG-KEY-elrepo.org
BASE=$(basename "$RPM")

if [[ "$NODE" == "192.168.200.217" ]]; then
  cp "$RPM" "$KEY" /tmp/
  REMOTE=(bash -lc)
else
  scp "$RPM" "$KEY" "root@${NODE}:/tmp/"
  REMOTE=(ssh "root@${NODE}")
fi

"${REMOTE[@]}" "
set -euo pipefail
df -h /boot
test -e /boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64
rpm --import /tmp/RPM-GPG-KEY-elrepo.org || true
rpm -K /tmp/${BASE} | tee /tmp/kernel_rpm_verify.txt
grep -q \"digests signatures OK\" /tmp/kernel_rpm_verify.txt
yum -y --disablerepo=\"*\" localinstall /tmp/${BASE}
test -e /boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64
grubby --set-default=/boot/vmlinuz-6.6.12-1.el7.elrepo.x86_64
grubby --default-kernel
"
echo "Now reboot ${NODE}: ssh root@${NODE} reboot (run from 217; for 217 reboot in maintenance window)"
EOF
chmod +x scripts/install_kernel_on_worker.sh

cat > scripts/post_boot_validation.sh << "EOF"
#!/usr/bin/env bash
# Usage: bash post_boot_validation.sh <node_ip>
# Run from 217 after node reboot

set -euo pipefail
NODE=${1:?node_ip required}

if [[ "$NODE" == "192.168.200.217" ]]; then
  REMOTE=(bash -lc)
else
  REMOTE=(ssh "root@${NODE}")
fi

"${REMOTE[@]}" "
set -euo pipefail
uname -r
test \"\$(uname -r)\" = \"6.6.12-1.el7.elrepo.x86_64\"
cat /proc/mdstat
lsblk | head
df -hT | grep -E \"nas_vol8|data\"
ip -br addr
docker info > /dev/null 2>&1 && echo docker_ok || echo docker_FAIL
docker ps | grep 5488
systemctl --failed
"
EOF
chmod +x scripts/post_boot_validation.sh

cat > scripts/rollback_to_old_kernel.sh << "EOF"
#!/usr/bin/env bash
# Usage: bash rollback_to_old_kernel.sh <node_ip> [--reboot]
# Run from 217 when the node is reachable. If the node cannot boot, use physical/IPMI/KVM GRUB selection.

set -euo pipefail
NODE=${1:?node_ip required}
DO_REBOOT=${2:-}
OLD=/boot/vmlinuz-3.10.0-1160.71.1.el7.x86_64

if [[ "$NODE" == "192.168.200.217" ]]; then
  REMOTE=(bash -lc)
else
  REMOTE=(ssh "root@${NODE}")
fi

"${REMOTE[@]}" "
set -euo pipefail
test -e ${OLD}
grubby --set-default=${OLD}
grubby --default-kernel
"

if [[ "$DO_REBOOT" == "--reboot" ]]; then
  "${REMOTE[@]}" "sync; sync; reboot" || true
fi
EOF
chmod +x scripts/rollback_to_old_kernel.sh

# 2. 同步说明文档
cat > docs/REUSE_GUIDE.md << "EOF"
# 内核升级复用指南(216 已成功后,219/220/221/217 复用此流程)

## 原则
- 固定 kernel-ml 6.6.12,不追最新
- 所有 RPM/key 已提前缓存到 217:/data/upgrade/kernel-ml-6.6.12/rpms/
- install 脚本只安装 kernel-ml 本体,不安装 devel/headers/tools/doc
- 失败且机器还能 SSH: bash rollback_to_old_kernel.sh <node_ip> --reboot
- 失败且机器不能 SSH:通过物理/IPMI/KVM 在 GRUB 选择旧 3.10 内核

## 顺序建议
1. 先升 219 / 220 / 221 三个 worker(三选一,一次一个)
2. 最后升 217(coordinator)

## 单台升级步骤
1. user 暂停业务写入
2. bash /data/upgrade/kernel-ml-6.6.12/scripts/install_kernel_on_worker.sh <worker_ip>
3. ssh root@<worker_ip> reboot
4. 等 5 分钟,跑 bash post_boot_validation.sh <worker_ip>
5. coordinator 跑 SELECT * FROM citus_check_cluster_node_health();
6. 若失败:
   - 能 SSH: bash rollback_to_old_kernel.sh <worker_ip> --reboot
   - 不能 SSH:GRUB 选老内核 3.10 重启

## 217 coordinator 升级注意事项
- coord 升级期间整个集群不可用
- 完成前要确保所有 worker 已升完
- 217 本机运行脚本不需要 ssh 跳板;reboot 前必须确认所有 worker healthy
EOF

ls -la scripts/ docs/
'
```

### 阶段 7:完工 commit + push

`git add` 列:
- `rebuild5/docs/upgrade/kernel_upgrade_216_prompt.md`(本 prompt)
- `rebuild5/docs/upgrade/kernel_upgrade_216_report.md`(产出)
- `rebuild5/docs/upgrade/README.md`(状态加内核升级条目)

**注意**:`/data/upgrade/kernel-ml-6.6.12/` 在 217 服务器上,**不在 git 仓库**,不需要 commit。

一个 commit:
```
chore(rebuild5): kernel-ml 6.6.12 upgrade trial on worker 216

- Single-machine kernel trial on 192.168.200.216, following
  /Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md §3.1.1
- Citus topology preserved (no drain, no rebalance, no remove); 216 came
  back to coordinator with same identity after reboot
- Old 3.10 kernel preserved as GRUB fallback
- Reusable scripts staged at 217:/data/upgrade/kernel-ml-6.6.12/ for future
  219/220/221/217 upgrades
- Cluster health post-upgrade: 4 workers active, data baseline matches
  (TCL b7=340,766 unchanged, sliding rows=24,017,207 unchanged)
- References /Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push 撞 SSL 等 60s 重试,再失败标 push pending。

写 note `topic='kernel_216_done'` info,用 § 9 完工话术汇报。

### 不做(显式禁止)

- ❌ 不动其他 4 台机器(217/219/220/221),仅 216 试验
- ❌ 不 `citus_drain_node` / `citus_remove_node`(走 § 3.1.1 不走 § 3.1.2)
- ❌ 不删旧 3.10 内核(GRUB 回退入口)
- ❌ 不改 PG18 容器配置 / 不改 Docker 配置
- ❌ 不改 PG 参数(本阶段是内核试验,不是综合调优)
- ❌ 不动数据卷 `/data/pgsql/...`(任何情况下都不能动数据)
- ❌ 不升级到当前最新 kernel-ml;固定 `6.6.12-1.el7.elrepo`
- ❌ 不在 216 上临时联网下载 RPM;所有包必须先缓存在 217
- ❌ 不安装 `kernel-ml-headers` / `kernel-ml-tools` / `kernel-ml-devel` / `kernel-ml-doc`(本轮按 06 文档 § 4 只装内核本体;这些包只提前缓存备用)
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 启动失败超过 10 分钟立刻 blocker,等 user 通过 IPMI 介入,**不自己尝试 fix**(物理控制台权限不在 agent)
- ❌ 不动 5487 老 PG17 fallback 容器(它会随机器重启自动恢复)

## § 6 验证标准

1. **离线包完整**:217 上 `/data/upgrade/kernel-ml-6.6.12/rpms/` 含 7 个 6.6.12 RPM + `RPM-GPG-KEY-elrepo.org` + `elrepo-release-7.el7.elrepo.noarch.rpm` + `SHA256SUMS` + `RPM_VERIFY.txt`
2. **回退入口确认**:旧内核文件存在,`grubby --info=ALL` 含 3.10 条目,且报告记录物理/IPMI/KVM/本地控制台回退方式
3. **216 内核**:`ssh ... 'uname -r'` = `6.6.12-1.el7.elrepo.x86_64`
4. **旧内核仍在**:`grubby --info=ALL` 含 3.10 条目
5. **系统层**:RAID / XFS / NAS / 10G 网卡 / Docker 全部 OK,journal 无关键错误
6. **216 上 PG18 容器自启**:`docker ps | grep citus-worker-5488` 状态 Up
7. **Citus 健康**:`citus_check_cluster_node_health()` 全 healthy + 4 worker active(216 在内)
8. **数据基线**:TCL b7=340,766 不变,sliding 24,017,207 不变(完全无差)
9. **217 控制台脚本归档**:`/data/upgrade/kernel-ml-6.6.12/scripts/{install_kernel_on_worker,post_boot_validation,rollback_to_old_kernel}.sh` + `docs/REUSE_GUIDE.md` 存在
10. **commit + push**(允许标 push pending)
11. **note `kernel_216_done`** 写入;如果 216 离线期间 notes 写入受阻,先写 217 本地 log,恢复后补 note

## § 7 产出物 `kernel_upgrade_216_report.md`

```markdown
# kernel-ml 6.6.12 升级试验报告(216 单机)

## 0. TL;DR
- 试验机:192.168.200.216(worker)
- 老内核:3.10.0-1160.71.1.el7.x86_64(保留作 GRUB fallback)
- 新内核:6.6.12-1.el7.elrepo.x86_64
- 试验结果:成功 / 失败(具体失败层)
- 下载策略:固定 6.6.12 / archive 源 / 离线包已完整缓存
- 回退入口:旧 3.10 内核存在 + 控制台/IPMI/KVM 回退方式已确认
- 系统层验证:RAID / XFS / NAS / 网络 / Docker 全 OK
- PG18 + Citus:216 自动加入集群,数据基线 100% 一致
- 重启总耗时:<m> 分钟
- 217 控制台脚本归档:/data/upgrade/kernel-ml-6.6.12/scripts/(给 219/220/221/217 复用)
- commit SHA:<sha>;push 状态:<status>

## 1. 试验前快照(216)
- uname:3.10.0-1160.71.1.el7.x86_64
- grubby --info=ALL 输出节选
- /proc/mdstat / lsblk / df 节选
- docker inspect citus-worker-5488 + 5487 节选

## 2. Citus 健康基线(集群视角)
- citus_check_cluster_node_health 输出
- 4 worker 全 active
- TCL b7=340,766 / sliding=24,017,207

## 3. kernel-ml 6.6.12 下载 + 安装
- 镜像源选择(Coreix archive / 备用 archive)
- 7 个 RPM 离线缓存清单
- rpm sha256 / RPM_VERIFY
- yum localinstall 输出
- grubby --set-default 输出

## 4. 重启 + 系统层验证
- reboot 时间戳
- 等待 ping 时长
- uname -r、mdstat、lsblk、df、网络、docker、systemctl --failed、journal warn 输出

## 5. PG18 + Citus 验证
- 216 上 docker ps(5488 + 5487 都 Up)
- citus_check_cluster_node_health 输出(全 healthy)
- 4 worker active 验证
- 数据基线对账(完全一致)

## 6. 217 控制台归档
- /data/upgrade/kernel-ml-6.6.12/ 目录结构
- install_kernel_on_worker.sh 内容
- post_boot_validation.sh 内容
- rollback_to_old_kernel.sh 内容
- REUSE_GUIDE.md 内容

## 7. 已知限制 / 给后续升级的输入
- 219/220/221 复用顺序建议
- 217 coordinator 升级特殊性(需要全集群停服窗口)
- 任何 216 升级期间发现的小问题(driver 警告 / Docker 慢启动 / 等)
```

## § 8 notes 协议

- 每阶段 1 条 info note:`kernel_216_phase<N>_done`
- 完工:`kernel_216_done` info,body 含 uname + 4 worker active + 数据基线一致性
- 失败:`kernel_216_failed` blocker,body 含失败阶段 + 当前 216 状态(已回退 / 卡 GRUB / 数据是否动过)

`rb5_bench.notes` 是 reference table,placement 可能包含 216。升级期间如果因为 216 离线导致 note 写不进,不要硬等;先把同样内容写到 217:

```bash
ssh root@192.168.200.217 'printf "%s\n" "<topic>|<severity>|<body>" >> /data/upgrade/kernel-ml-6.6.12/logs/notes_pending.log'
```

216 和 Citus 恢复 healthy 后,再把 pending log 摘要补写进 `rb5_bench.notes`。

## § 9 完工话术

成功:
> "kernel-ml 6.6.12 在 216 试验完成。kernel_upgrade_216_report.md 已写入。217 已完整缓存 7 个 6.6.12 RPM + GPG key + sha256/RPM_VERIFY,后续不需要临用临下。新内核 6.6.12-1.el7.elrepo.x86_64 启动成功;旧 3.10 内核保留为 GRUB fallback;系统层(RAID/XFS/NAS/网络/Docker)全 PASS;PG18 容器自动恢复;Citus 4 worker 全 active;数据基线 TCL b7=340,766 / sliding=24,017,207 完全一致。重启总耗时 <m> 分钟。217 上已归档 install/post_boot/rollback 脚本 + 复用指南给 219/220/221/217 后续升级。commit=<SHA>(push <成功/pending>)。notes `topic='kernel_216_done'` 已插入。下一步:user 决定是否升 219/220/221。"

失败:
> "kernel-ml 6.6.12 在 216 试验失败于阶段 <N>:<step>。blocker=<一句话>。当前 216 状态:<跑老 3.10 内核回退中 / 卡 GRUB 物理介入需要 / 系统层异常 / Citus 不健康>。已写 notes `topic='kernel_216_failed'`。等上游处置。其他 4 worker 不受影响。"

## § 10 失败兜底

按 06 文档 § 7 失败分层执行:

- **216 重启不回来超 10 分钟**:blocker note,**user 必须通过 IPMI / 远程 KVM / 物理控制台进入 GRUB 选老 3.10 内核**(agent 没物理权限)
- **能启动但 mdstat / lsblk 异常**(RAID/磁盘):立刻 reboot 选老内核 → 再启 3.10 验证 → blocker 让 user 决定
- **能启动但网络异常**(ip -br addr 异常):同上,看是 ixgbe / igb 驱动问题
- **能启动但 docker 不工作**(docker info 失败):看 `journalctl -u docker` + `systemctl status docker`,可能是 cgroupv1 vs v2 问题。**先回退到 3.10 内核**,blocker 让 user 决策
- **能启动但 PG18 容器起不来**:不动数据目录,先回退老内核;问题在新内核兼容层
- **Citus coordinator 看 216 不 healthy**:几分钟自然 reconnect 一般会好;等 5 分钟再标 blocker
- **数据基线对账偏差**:**这是数据完整性事件**,极不应该(本阶段不动数据)。立刻停 + blocker + 让 user 决定是否回退 + 检查 5487 fallback 是否能用
- **GitHub HTTPS SSL 抖动**:等 60s 重试,push pending 不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
- **绝不**`citus_drain_node` / `citus_remove_node`(走 § 3.1.1,user 已拍板)
- `grubby --set-default` 是持久默认。本 prompt 为了自动化明确允许在阶段 3 设置 6.6.12 为默认;回退时用 `/data/upgrade/kernel-ml-6.6.12/scripts/rollback_to_old_kernel.sh <node_ip> --reboot`,或机器不可 SSH 时通过 GRUB 手动选旧 3.10。
