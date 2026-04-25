# OptiNet rebuild5 / fix6_optim / 03 pipelined 加速 + Runbook(终点 · agent 新实例对话)

## § 1 元目标

**fix6_optim 终点阶段,一次跑完不分手**。两件事捆绑做:

1. **加速兑现**:新建 `rebuild5/scripts/run_citus_pipelined_batches.py`,Step 1 (day N+1) 与 Step 2-5 (day N) 跨日并行,跑全 7 批(2025-12-01 ~ 2025-12-07),目标 ≤ 90 分钟(串行 ~150 分钟,加速比 ≥ 1.3×)。
2. **Runbook 沉淀**:本 agent 跑全 7 批的过程就是 runbook 的素材源 —— 把"reset / 启动 / 监控 / 哨兵 / 验收 / 故障切串行"全套标准化成 `rebuild5/docs/fix6_optim/04_runbook.md` + `rebuild5/scripts/runbook/*.sh` 可复用脚本。

数据一致性是硬约束(±5% vs fix5 D 同 batch 基线),加速是 nice-to-have。

**用户不参与本阶段**(沙箱已解除长跑限制,完整自主跑到 fix6_optim 完工)。

## § 2 上下文启动顺序

按序读完直接开工:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/fix6_optim/README.md` —— 全局 + 协作约定
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— **§ 11 自动 commit/push** 和 **§ 12 上下游互审**
4. `rebuild5/docs/fix6_optim/02C_test_report.md` §5 给 03 的守护清单
5. `rebuild5/docs/fix6_optim/02B_refactor_report.md` —— Citus 兼容统一入口
6. `rebuild5/docs/fix5/06_rerun_validation.md` —— 串行 runner 7 批基线 + 终点验收方法 + 故障 checklist 素材
7. `rebuild5/docs/fix5/01_quality_diagnosis.md` §2-3 —— scope 物化根因(pipelined 必须保)+ 哨兵 SQL
8. `rebuild5/scripts/run_citus_serial_batches.py` —— 串行 runner 完整实现
9. `rebuild5/scripts/run_step1_step25_pipelined_temp.py` —— PG17 上已有 pipelined 实现的本地参考
10. `rebuild5/scripts/run_daily_increment_batch_loop.py::materialize_step2_scope` —— scope 物化函数
11. `rebuild5/backend/app/core/citus_compat.py` —— 02B 抽的统一入口(线程 / 进程安全考虑)
12. 本 prompt

读完**直接开工**,不需要在对话报告设计选型等用户 ack。**所有设计决策记录在 03_pipelined_report.md §1**,跑完后由用户回看。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`
- **当前 git 头**:`38ad774`(02C 本地交付)
- **GitHub 远端可能落后** 02B/02C(SSL 抖动 push 失败的遗留)。开干前先 `git push origin main` 一次,撞 SSL 等 60s 重试 1 次,再失败 §4 标 "push pending" 不算 blocker
- **Git remote**:`https://github.com/laoyang75/OptiNet.git`(private + 局域网)

### 数据库连接

- **Citus**:`postgres://postgres:123456@192.168.200.217:5488/yangca`,MCP `mcp__PG_Citus__execute_sql`
- **PG17(只读基线)**:`postgres://postgres:123456@192.168.200.217:5433/ip_loc2`,MCP `mcp__PG17__execute_sql`
- **runner env**:`REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'`
- **auto_explain**:`PGOPTIONS='-c auto_explain.log_analyze=off'`(必须前缀)
- **Citus 配置**:`citus.max_intermediate_result_size = 16GB`(已 ALTER SYSTEM)

### 集群规格

- 1 coord + 4 worker / 每台 20 物理 / 40 逻辑 / 251GB 内存
- pipelined 在这台机器上完全可承载并发

### 沙箱状态

**沙箱已解除长跑限制**(用户已确认)。可以完整跑全 7 批 ~90 分钟,不需要拆 batch 1-3 / batch 4-7。建议仍用 `nohup ... &` + 日志重定向 + PID 文件作好习惯,但 SIGKILL 风险已消除。

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `02C_test_report.md` §5 | 阅读 | 必须保的守护 |
| `06_rerun_validation.md` §3-4 | 阅读 | 串行 7 批基线时长 + 终点验收 |
| `01_quality_diagnosis.md` §2-3 | 阅读 | 4 哨兵 SQL + 根因 |
| `rebuild5/tests/test_runner_scope_materialization.py` | 修改 | 扩展 1 个 test 覆盖 pipelined runner |
| 本阶段产出 `03_pipelined_report.md` | 新建 | § 7 结构 |
| 本阶段产出 `04_runbook.md` | 新建 | § 5.7 结构(原计划 04 阶段并入此次) |
| 本阶段产出 `rebuild5/scripts/runbook/*.sh` | 新建 | reset / serial / pipelined / sentinels / endpoint |

## § 5 任务清单

### 必做(按顺序,自主推进)

#### 5.1 设计选型自主决策 + 记录

读完 §2 后,你自主拍板以下 6 项,**直接在 `03_pipelined_report.md §1` 记录**(不在对话里要 ack):

1. **并发模型**:threading / multiprocessing / asyncio(提示:Step 1 是 SQL-bound,threading 在 GIL release 期间有效并行;multiprocessing 重 IPC 但完全隔离 connection;asyncio 需要 async psycopg)
2. **数据隔离**(同一 day Step 1 写 `rb5.etl_cleaned`,Step 2-5 同时读,**怎么防 day N+1 Step 1 破坏 day N Step 2-5 工作集**):
   - A:per-day step2_batch_input(`rb5.step2_batch_input_<day>` 后缀)
   - B:Step 1 day N+1 必须等 Step 2 day N 的 materialize_step2_scope 完成才启动(barrier)
   - C:per-day staging schema
   - 自创方案也允许,但要在报告里详述
3. **connection 池**:每个 thread / process 独立 `get_conn()`(psycopg connection **不是线程安全**,这是硬约束)
4. **Race / 死锁防护**:Citus inter-shard advisory lock 撞死锁怎么应对
5. **错误处理**:某一 day Step 1 / Step 2-5 挂了 → fail-fast / partial commit / 跳过
6. **fallback 策略**:pipelined 撞错时,自动切串行 / 停 / 重试

#### 5.2 实现 `run_citus_pipelined_batches.py`

新文件,**不修改 `run_citus_serial_batches.py`**(保留作 fallback)。

CLI 与串行兼容:
```
python rebuild5/scripts/run_citus_pipelined_batches.py \
  --start-day 2025-12-01 \
  --end-day 2025-12-07 \
  --start-batch-id 1 \
  [--skip-reset] \
  [--max-pipeline-depth 2] \
  [--fallback-on-error]
```

复用既有模块(直接 import,不重写):
- `run_daily_increment_batch_loop.materialize_step2_scope`
- `run_citus_serial_batches._load_raw_day` / `_log` / step 调用
- `backend.app.core.citus_compat.execute_distributed_insert`

每 day 完成时 emit 与串行 runner 等价的 `_log` 事件(`raw_day_loaded` / `step1_done` / `step2_scope_materialized` / `batch_validation` / `step5_done` 等),保证 02C 守护通过。

#### 5.3 扩展 02C 守护到 pipelined runner

修改 `rebuild5/tests/test_runner_scope_materialization.py`,新增 1 个 test:

```python
def test_pipelined_runner_calls_materialize_step2_scope_after_step1():
    """守护 pipelined runner 也满足 step1 → scope → step2-5 顺序约束。
    
    pipelined 中 step1 thread 可能比 step2-5 thread 抢跑,所以约束是
    "对同一 day,materialize_step2_scope(day=N) 在 step1 day N 完成后、
    step2-5 day N 启动前"。
    """
    # AST 解析 run_citus_pipelined_batches.py
    ...
```

不动其他 4 个 02C test 文件。

#### 5.4 reset + 全 7 批 pipelined 跑

reset(避免 fix5 D 残留干扰):
```bash
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca \
  -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

后台跑全 7 批:
```bash
PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca' \
nohup python3 rebuild5/scripts/run_citus_pipelined_batches.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  > /tmp/fix6_03_pipelined_b1_7_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > /tmp/fix6_03.pid
```

每 5-15 分钟 `tail` 日志一次,grep `batch_validation` 监听完成事件。每完成一 batch 立刻打 4 条哨兵(05_rerun_prompt §5,bid 替换为当前 N):

1. `enriched_records` 当批严格单日
2. `cell_sliding_window` 跨度 ≤ 14 天 + 无 2023/2024 时间戳
3. `_step2_cell_input` NULL 或 max(event_time_std) = 当日
4. TCL batch N 行数 > batch N-1(单调增长)

任意一条挂红立刻停 + blocker note,**不要硬推到下一批**。

#### 5.5 终点验收(batch 7 完成后)

参考 fix5 D `06_rerun_validation.md` §6 三条软验收:

1. **TCL 总量 vs PG17 ±20%**:`pg17.rebuild5.trusted_cell_library batch_id=7` ≈ 341,460,Citus pipelined 应在 273,168 ~ 409,752
2. **sliding_window 日期范围**:min ≥ 2025-11-24,max = 2025-12-07,无未来 / 2023
3. **enriched 7 批全覆盖**:7 行,各严格单日

数据一致性硬约束(vs fix5 D 串行同 batch ±5%):
- TCL b7:fix5 D = 348,921,pipelined 应在 331,475 ~ 366,367
- TCL 各 batch 子分布(stable / dual_cluster 等)允许 ±5%

#### 5.6 时长对比

| batch | pipelined T(s) | serial T(fix5 D) | speedup |
|---|---:|---:|---:|
| 1 | <n> | 800 | <x> |
| 2 | <n> | 932 | <x> |
| 3 | <n> | 1171 | <x> |
| 4-7 总 | <n> | ~6000(D 阶段累计 hotfix 后) | <x> |
| **全 7 批总** | <T_pipe> | **~9000s ≈ 150 min** | **<目标 ≥ 1.3×>** |

speedup < 1.0 仍算"完成"(数据一致性达标即可),但报告 §0 详细分析瓶颈(planning 时间 / lock 等待 / 网络往返),由 user 回看时决定是否切回串行。

#### 5.7 写 Runbook(原计划 04 阶段并入)

新建以下文件,**基于本次实战经验**沉淀:

##### `rebuild5/docs/fix6_optim/04_runbook.md`(主文档)

```markdown
# OptiNet rebuild5 Citus 集群 — 标准操作 Runbook

> 适用范围:rebuild5 Citus 集群(192.168.200.217:5488/yangca)的"改 → 跑 → 验"研究循环。
> 撰写时间:2026-04-25(fix6_optim 终点阶段)。
> 撰写依据:fix5 五阶段诊断 + fix6_optim 三阶段加速,实战通过。

## 1. 快速参考(命令清单)

### 1.1 reset 全 7 批基线
```
bash rebuild5/scripts/runbook/reset_full_baseline.sh
```

### 1.2 跑 1 day 单批(快速验证代码改动)
```
bash rebuild5/scripts/runbook/run_single_batch.sh 2025-12-01 1
```

### 1.3 跑全 7 批(pipelined 加速)
```
bash rebuild5/scripts/runbook/run_full_pipelined.sh
```

### 1.4 跑全 7 批(串行 fallback,稳但慢)
```
bash rebuild5/scripts/runbook/run_full_serial.sh
```

### 1.5 每批跑完打 4 哨兵
```
bash rebuild5/scripts/runbook/sentinels.sh <batch_id>
```

### 1.6 终点验收(batch 7 完成后)
```
bash rebuild5/scripts/runbook/endpoint_check.sh
```

## 2. 决策树:遇到问题怎么办

### 2.1 哨兵 #1 enriched 跨日
原因:scope materialization 失效。
处理:见 fix5/01 §2.1。检查 runner 在 Step1 后是否调用了 materialize_step2_scope。

### 2.2 sliding_window 含 2023/2024
原因:trim 被关或 SKIP env var 复活。
处理:见 fix5/01 §2.2。grep `REBUILD5_SKIP_SLIDING_WINDOW_TRIM` 确认无残留。

### 2.3 TCL batch N 行数 = batch N-1
原因:input 冻结(stale `_step2_cell_input`)。
处理:reset + 重跑该批起。

### 2.4 publish_bs/cell/lac 撞 "could not create distributed plan"
原因:某 caller 走回 `core.database.execute(..., params)` 老路。
处理:确认 02C 守护 `test_high_risk_callers_use_unified_entry` 是绿的。如果不绿,grep `execute([^)]*params=` 找漏迁的 caller,改用 `execute_distributed_insert`。

### 2.5 pipelined 跑挂
原因:race / 死锁 / connection 不安全。
处理:切 `run_citus_serial_batches.py` 跑剩余批次(`--start-batch-id N --skip-reset`)。

### 2.6 GitHub HTTPS push 撞 SSL_ERROR_SYSCALL
原因:网络瞬时抖动。
处理:等 60s 重试。本地 commit 不会丢失。

## 3. 监控指标

### 3.1 进程层
- `tail -f /tmp/fix6_*.log`:runner 当前 step
- `ps -p $(cat /tmp/fix6_*.pid)`:进程存活
- pipelined 还可看 thread 当前 day(在日志的 `_log` 事件 `event` 字段)

### 3.2 数据库层
- `pg_stat_activity` where datname='yangca':识别 stuck SQL
- `rb5_meta.step1_run_stats`(以及 step2/3/4/5):每 step 完成情况
- `rb5_bench.notes` ORDER BY created_at DESC:跨阶段决策 trail

### 3.3 业务层
- TCL by batch 单调增长:`SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY 1 ORDER BY 1`
- sliding_window 跨度 = batch_id(从 1 增到 7):`SELECT MAX(event_time_std) - MIN(event_time_std), COUNT(*) FROM rb5.cell_sliding_window`

## 4. 已验证的基线指标(2026-04-25)

| 指标 | PG17 黄金 | Citus 串行(fix5 D) | Citus pipelined(fix6 03) |
|---|---:|---:|---:|
| TCL b7 总量 | 341,460 | 348,921(+2.19%) | <n>(<X.XX%>) |
| stable | 337,480 | 344,339 | <n> |
| dual_cluster | 442 | 445 | <n> |
| 7 批总时长 | n/a | ~150 min | <T> min |

## 5. 历史诊断 trail

- fix5 A 诊断:`rebuild5/docs/fix5/01_quality_diagnosis.md`
- fix5 B 审计:`rebuild5/docs/fix5/02_agent_change_audit.md`
- fix5 C 修复:`rebuild5/docs/fix5/04_code_fix_report.md`
- fix5 D 重跑:`rebuild5/docs/fix5/06_rerun_validation.md`
- fix6_optim 02A 审计:`rebuild5/docs/fix6_optim/02A_audit_report.md`
- fix6_optim 02B 重构:`rebuild5/docs/fix6_optim/02B_refactor_report.md`
- fix6_optim 02C 测试:`rebuild5/docs/fix6_optim/02C_test_report.md`
- fix6_optim 03 加速:`rebuild5/docs/fix6_optim/03_pipelined_report.md`(本批)

## 6. 关键代码出口

| 关注点 | 文件 |
|---|---|
| Citus 兼容 INSERT 入口 | `rebuild5/backend/app/core/citus_compat.py::execute_distributed_insert` |
| 串行 runner | `rebuild5/scripts/run_citus_serial_batches.py` |
| pipelined runner | `rebuild5/scripts/run_citus_pipelined_batches.py` |
| reset SQL | `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql` |
| scope 物化 | `rebuild5/scripts/run_daily_increment_batch_loop.py::materialize_step2_scope` |
```

##### `rebuild5/scripts/runbook/*.sh`(可执行脚本)

至少 6 个 bash 脚本(`#!/usr/bin/env bash` + `set -euo pipefail` + 必要 PG env vars):

1. `reset_full_baseline.sh` —— 跑 reset SQL + 验证空表
2. `run_single_batch.sh <day> <batch_id>` —— 串行单批(代码 quick check 用)
3. `run_full_pipelined.sh` —— pipelined 全 7 批 + nohup + 日志
4. `run_full_serial.sh` —— 串行全 7 批 fallback
5. `sentinels.sh <batch_id>` —— 4 条哨兵 SQL via psql
6. `endpoint_check.sh` —— batch 7 终点 3 验收 + PG17 对账

每个脚本顶部加注释:用途 / 输入参数 / 期望输出 / 失败处理建议。

#### 5.8 完工后流程(按 _prompt_template.md § 11)

`git add` 显式列:
- `rebuild5/scripts/run_citus_pipelined_batches.py`(新)
- `rebuild5/scripts/runbook/*.sh`(新)
- `rebuild5/tests/test_runner_scope_materialization.py`(扩展)
- `rebuild5/docs/fix6_optim/02C_test_prompt.md`(02C 漏 commit)
- `rebuild5/docs/fix6_optim/03_pipelined_prompt.md`(本 prompt)
- `rebuild5/docs/fix6_optim/03_pipelined_report.md`(产出)
- `rebuild5/docs/fix6_optim/04_runbook.md`(产出)
- `rebuild5/docs/fix6_optim/README.md`(更新阶段状态:终点)

一个 commit:
```
feat(rebuild5): fix6_optim 03 pipelined runner + runbook (终点)

- Add run_citus_pipelined_batches.py with <并发模型> Step1//Step2-5 pipeline
- Per-day isolation via <选项 A/B/C>; reuse materialize_step2_scope and
  citus_compat.execute_distributed_insert; no business code change
- Extend test_runner_scope_materialization to guard pipelined runner
- Run full 7-batch pipelined: T_pipe=<n>s vs T_serial=~9000s, speedup=<x>×;
  TCL_b7=<n> within ±<x>% of fix5 D serial baseline (348,921)
- Add 04_runbook.md + scripts/runbook/{reset,run_single,run_full_pipelined,
  run_full_serial,sentinels,endpoint_check}.sh standardized ops surface
- References fix6_optim/02C_test_report.md §5 and fix5/06_rerun_validation.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

`git push origin main`(撞瞬时 SSL 等 60s 重试 1 次,再失败标 "push pending" 不算 blocker)

写 note `topic='fix6_03_done'`(同时也是整个 fix6_optim 完工信号)。

用 § 9 完工话术汇报。

### 不做(显式禁止)

- ❌ 不修改 `run_citus_serial_batches.py`(保留作 fallback)
- ❌ 不修改 `backend/app/` 任何代码(02B 已稳定)
- ❌ 不修改其他 4 个 02C test_*.py
- ❌ 不改分布键 / colocation / 表结构 / SQL 业务语义
- ❌ 不引入新依赖
- ❌ 不开 PR / 不开分支
- ❌ 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc
- ❌ pipelined 跑挂不"再跑一遍碰运气",立刻停 + blocker note
- ❌ 不为加速牺牲数据一致性 → ±5% 对账挂红就 blocker
- ❌ runbook 别写"未来如果..." 等空话,只记本次实战通过的步骤

## § 6 验证标准

任务 done 的硬标准:

1. **新 runner 文件存在**:`rebuild5/scripts/run_citus_pipelined_batches.py`
2. **CLI 兼容**:`python3 rebuild5/scripts/run_citus_pipelined_batches.py --help` 显示串行同款 + 新增 pipeline 参数
3. **02C 守护扩展通过**:`test_runner_scope_materialization.py` 新加 1 个 test 后,手工 invoke / pytest 全过
4. **全 7 批跑通**:
   - `SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY 1 ORDER BY 1` 显示 7 行,行数严格单调增长
   - `SELECT MIN(event_time_std)::date, MAX(event_time_std)::date FROM rb5.cell_sliding_window` = `2025-11-24..` ~ `2025-12-07`(具体 min 由 14 天 retention 决定)
   - 每批 4 哨兵均 pass
5. **终点对账**:TCL b7 总量在 fix5 D 串行(348,921)±5% 内 → 331,475 ~ 366,367
6. **加速比报告**:T_pipe / T_serial / speedup 三个数字记录
7. **6 个 runbook 脚本可执行**:`bash -n` 语法检查 0 退出 + chmod +x
8. **commit + push**:`git rev-parse HEAD == git rev-parse origin/main`(允许标 "push pending due to network")
9. **note 写入**:`SELECT body FROM rb5_bench.notes WHERE topic='fix6_03_done'`,body 含全 7 批时长 + speedup + TCL b7 + 一致性偏差

## § 7 产出物 `03_pipelined_report.md`

```markdown
# fix6_optim / 03 pipelined 加速 + Runbook 报告(终点)

## 0. TL;DR + 对上游修订
- 并发模型:<threading / multiprocessing / asyncio>
- 数据隔离:<A / B / C / 自创>
- 全 7 批时长:T_pipe=<n>s,T_serial=~9000s,speedup=<x.x>×
- TCL b7:<n>(vs fix5 D 348,921,±<x>%)
- 数据一致性:7 批哨兵全过;终点 3 验收<状态>
- 4 个 runbook 脚本 + 04_runbook.md 已落地
- 对 02A/02B/02C 修订:<无 / 列表>
- commit SHA:<sha>;push 状态:<status>
- fix6_optim 收档,无后续阶段

## 1. 设计选型决策
1. 并发模型:<选 + 理由>
2. 数据隔离:<选 + 理由>
3. connection 池:<策略>
4. race/死锁防护:<机制>
5. 错误处理:<策略>
6. fallback:<策略>

## 2. 实现要点(伪代码 + 关键 diff)
- 主循环结构(Step1 thread / Step2-5 thread / queue / barrier)
- materialize_step2_scope 调用时机
- enqueue / dequeue 协议
- 异常 propagation 路径

## 3. 验证结果
### 3.1 7 批哨兵
| batch | enriched 单日 | sliding span | TCL | vs fix5 D |
| ... |

### 3.2 时长对账
表(同 §5.6)

### 3.3 终点 3 验收
- TCL b7 vs PG17 ±20%:<结果>
- sliding 日期范围:<min..max>
- enriched 7 批全覆盖:<结果>

### 3.4 02C 守护扩展
- test_pipelined_runner_calls_materialize_step2_scope_after_step1 结果
- 全 14+1 = 15 个守护对新 runner / 新代码的扫描结果

## 4. Runbook 落地
- 04_runbook.md 主文档:6 章
- scripts/runbook/*.sh 6 个脚本,每个一句话用途 + 输入参数

## 5. 已知限制 / 未做
- pipelined 跑挂?切串行的实战路径(若本次未触发,只在 04 §2.5 描述)
- push 状态(若网络抖动未 push)
- 任何 corner case 在本次未触发但未来可能的(给 user 留 trail)

## 6. fix6_optim 总账
- 01 收尾:commit head=4b23cd0
- 02A 审计:P0=0/P1=7/P2=6
- 02B 重构:7 caller 迁移,新 helper
- 02C 测试:5 文件 14 test_,1:1 覆盖 fix5 4 根因
- 03 加速 + runbook:speedup=<x>×,7 批 TCL b7 ±<x>%
```

## § 8 notes 协议

- 完工(整个 fix6_optim 收档):
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_03_done', 'info',
    'fix6_optim 收档:pipelined 全 7 批 T=<n>s vs serial ~9000s, speedup=<x>x, TCL b7=<n> +-<x>% vs fix5 D, runbook 04 + 6 sh scripts, head=<sha>');
  ```
- 失败:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_03_failed', 'blocker', 'failed at <step>: <reason>, no rollback');
  ```

## § 9 完工话术(用户回来时一眼看到)

成功:
> "fix6_optim 收档。03_pipelined_report.md + 04_runbook.md + 6 个 runbook bash 脚本已落地。
> pipelined 全 7 批跑通,T=<n>s,加速比 <x>×。TCL b7=<n>,vs fix5 D 串行偏差 <x>%。
> 02C 守护扩展为 15 个 test。对 02A/02B/02C 修订:<无 / 列表>。
> commit=<SHA>,GitHub:<url>(push <成功/pending>)。
> notes `topic='fix6_03_done'` 已插入,fix6_optim 全部完成。"

失败:
> "fix6_optim 03 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='fix6_03_failed'`。
> 当前 fix6_optim 进度:01 02A 02B 02C 完成,03 部分完成。
> working tree 未回滚保留给 user review。"

## § 10 失败兜底

- **pipelined 跑挂某 batch**:不要再跑一遍碰运气(fix5 D 教训);**自动切串行**(`run_citus_serial_batches.py --start-batch-id <挂的批> --skip-reset`)继续剩余批次,在报告 §0 标"pipelined 撞错切串行,加速比失效但终点数据交付"
- **psycopg connection 多线程不安全**:每 thread 独立 `get_conn()`,不共享。撞"连接已关闭"是根因
- **Citus inter-shard advisory lock 死锁**:`pg_locks` + `pg_stat_activity` 看 wait chain;最简单解法是 sync barrier(选项 B)
- **数据一致性 vs serial 偏差 > 5%**:**根本性问题**,意味着隔离方案漏 race。stop + blocker note,**不要硬推**,fix5 D 教训
- **batch 4-5 跑到一半某条 SQL 撞 Citus 错误**:复制完整 traceback 到报告 §0,**先尝试自动切串行**(用 fallback flag);如果串行也撞同错,blocker
- **GitHub HTTPS SSL 抖动**:等 60s 重试 1 次;再失败 §4 标 "push pending",**不算 blocker**,fix6_optim 仍可完工
- **runbook 写到一半 03 跑挂**:先停 03,blocker note;runbook 至少把 reset / serial / sentinels 三个写完(独立于 pipelined 成功),pipelined 部分留 placeholder
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
