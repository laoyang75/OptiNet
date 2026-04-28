# Rebuild5 顶层操作手册

本文是顶层导航。**详细操作手册**在 [`archive/fix_history/fix6_optim/04_runbook.md`](./archive/fix_history/fix6_optim/04_runbook.md)(已含 PG18 升级后基线)。

> 想了解项目当前状态 → [`PROJECT_STATUS.md`](./PROJECT_STATUS.md)
> 想了解业务逻辑 → [`README.md`](./README.md)
> 想了解历史 trail → [`archive/fix_history/`](./archive/fix_history/)

---

## 1. 当前生产环境

| 项 | 值 |
|---|---|
| 生产入口 | `postgres://postgres:123456@192.168.200.217:5488/yangca` |
| PG17 fallback(1-2 周观察期) | `postgres://postgres:123456@192.168.200.217:5487/yangca` |
| MCP 名 | `mcp__PG_Citus__execute_sql`(指 5488) |
| Runner env | `REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'` |
| auto_explain 兼容(必须前缀) | `PGOPTIONS='-c auto_explain.log_analyze=off'` |

## 2. 日常操作命令(常用)

详见 [`archive/fix_history/fix6_optim/04_runbook.md` § 1](./archive/fix_history/fix6_optim/04_runbook.md#1-快速参考命令清单)。常用 7 条:

```bash
# 1. reset 全 7 批基线
bash rebuild5/scripts/runbook/reset_full_baseline.sh

# 2. 单批快速验证(改代码后 ~13 min)
bash rebuild5/scripts/runbook/run_single_batch.sh 2025-12-01 1

# 3. 全 7 批跑(默认推荐:artifact pipelined,~128 min)
bash rebuild5/scripts/runbook/run_full_artifact_pipelined.sh

# 4. 全 7 批跑(串行 fallback,~150 min,稳但慢)
bash rebuild5/scripts/runbook/run_full_serial.sh

# 5. 每批跑完打 4 哨兵
bash rebuild5/scripts/runbook/sentinels.sh <batch_id>

# 6. 全 7 批跑完打终点验收
bash rebuild5/scripts/runbook/endpoint_check.sh

# 7. fix6 03 pipelined runner(老式 barrier,留作 fallback)
bash rebuild5/scripts/runbook/run_full_pipelined.sh
```

## 3. "改 → 跑 → 验" 工作流

```
1. 改代码(backend/app/* 或 scripts/*)
2. 决定重跑范围:
   - 改 Step1 ETL → 必须从 batch 1 重跑 7 批(全 reset,~128 min)
   - 改 Step2-3 profile → reset_step2 + run from batch 2(~省 30 min)
   - 改 Step5 maintenance → keep step1-4 输出,只 rebuild step5
   - 改 publish_bs/cell/lac SQL → 单批 quick verify(~13 min)
3. 跑(选上面 § 2 对应命令)
4. 哨兵 + 终点验收
5. commit + push(独立 commit,跨阶段不攒)
```

## 4. 常见故障决策树

详见 [`archive/fix_history/fix6_optim/04_runbook.md` § 2](./archive/fix_history/fix6_optim/04_runbook.md#2-决策树遇到问题怎么办)。摘要:

| 现象 | 根因方向 |
|---|---|
| 哨兵 #1 enriched 跨日 | scope materialization 失效,检查 runner 调用顺序 |
| sliding_window 含 2023/2024 | trim 关 / Step2 scope 放大;不允许 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM` |
| TCL batch N 行数 ≤ batch N-1 | input 冻结 / publish 失败,reset 重跑 |
| publish_bs/cell/lac 撞 "could not create distributed plan" | caller 走回 `core.database.execute(..., params)`,改回 `execute_distributed_insert` |
| pipelined 跑挂 | 切串行 `--start-batch-id N --skip-reset` 接 |
| GitHub HTTPS SSL_ERROR_SYSCALL | 等 60s 重试,本地 commit 不丢 |
| 单 worker 挂 | 26% shard 不可访问,重启容器恢复;无 HA(`shard_replication_factor=1`) |

## 5. 升级 / 维护操作

### 5.1 PG / Citus 版本升级

参考已落地 trail:[`archive/fix_history/upgrade/upgrade_v2_finalize_and_tuning_report.md`](./archive/fix_history/upgrade/upgrade_v2_finalize_and_tuning_report.md)

**关键经验**(给未来再升级用):
- ❌ **不要** `pg_dumpall` 全库 + 后置 `create_distributed_table`(v1 死因,部分大表 shard 不可见)
- ✅ **正确路径**:per-table CREATE TABLE 空建 + create_distributed_table → 后 COPY 数据 → Citus 自动路由
- ✅ 老集群保留(挪 port 5487)1-2 周观察期再删
- ✅ 调优分 5 步走(WAL → cache → io → parallel → memory),不一次改完
- ✅ 容器重建必须 `docker inspect` 当前配置作底稿,漏 env/volume 启不来
- ✅ 端口切换 downtime ≤ 2 分钟(用 docker stop + rename + run 串起来)

### 5.2 内核升级

参考 prompt:[`archive/fix_history/upgrade/kernel_upgrade_216_prompt.md`](./archive/fix_history/upgrade/kernel_upgrade_216_prompt.md)
依据文档:`/Users/yangcongan/cursor/DataBase/Docs/06_kernel_ml_6.6.12升级计划.md`

**当前进度**:216 单机试验阶段,prompt 已落地,等 agent 执行。

**关键约束**:
- 走 § 3.1.1 不 drain 路径(暂停写入 + 不从 Citus 摘除)
- 重启**前** 必须确认有 IPMI / KVM / 物理控制台之一(回退入口硬门槛)
- 所有 RPM/key 重启前缓存到 217:`/data/upgrade/kernel-ml-6.6.12/`,不允许 216 临时联网下载
- 主源 ELRepo archive(coreix.net),**不要清华/阿里**(它们的 elrepo 目录是滚动镜像,可能没 6.6.12 旧版)
- 不删旧 3.10 内核(GRUB 回退)

**复用脚本**(216 试验成功后,219/220/221/217 后续升级用):
```
217:/data/upgrade/kernel-ml-6.6.12/scripts/install_kernel_on_worker.sh <node_ip>
217:/data/upgrade/kernel-ml-6.6.12/scripts/post_boot_validation.sh <node_ip>
217:/data/upgrade/kernel-ml-6.6.12/scripts/rollback_to_old_kernel.sh <node_ip> [--reboot]
```

### 5.3 端口切换 / 集群停机维护

通用模板见 [`archive/fix_history/upgrade/upgrade_v2_finalize_and_tuning_prompt.md` § 5.7](./archive/fix_history/upgrade/upgrade_v2_finalize_and_tuning_prompt.md)。

## 6. 数据可信度对账标尺

详见 [`PROJECT_STATUS.md` § 5](./PROJECT_STATUS.md#5-可信回归基线数据可信度对账标尺)。

| 基线 | TCL b7 |
|---|---:|
| PG17 黄金 | 341,460 |
| 当前 PG18 tuned | **340,766**(-0.20% vs PG17) |

**验收阈值**:
- 同环境同代码 ±0.5%
- 跨环境(PG 升级 / 调优)±1%
- 跨大变化(集群重建 / 内核升级)±5%

## 7. 监控指标

详见 [`archive/fix_history/fix6_optim/04_runbook.md` § 3](./archive/fix_history/fix6_optim/04_runbook.md#3-监控指标)。

## 8. 联系点

- 代码:`rebuild5/backend/app/`
- 脚本:`rebuild5/scripts/`(主 runner 在 `run_citus_artifact_pipelined.py`)
- 测试守护:`rebuild5/tests/test_*.py`(15 个 test,覆盖 fix5 4 根因 + caller guard)
- 文档:本目录 `rebuild5/docs/`
- 运维 trail:`rb5_bench.notes` 表(reference table,跨集群可见)
