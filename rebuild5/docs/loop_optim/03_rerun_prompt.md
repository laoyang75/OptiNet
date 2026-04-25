# OptiNet rebuild5 / loop_optim / 03 全 7 批重跑验证(agent 新实例对话)

## § 1 元目标

跑 **`run_citus_artifact_pipelined.py` 全 7 批**(2025-12-01 ~ 2025-12-07)+ 终点验收,验证 02 阶段的 artifact 流水线 + Step1 40 核能否达到 **~90 分钟 / 加速比 ~1.67×** 目标。

数据一致性是硬约束(±5% vs fix6_optim 03 串行/pipelined 同 batch),加速是 nice-to-have。

**类似 fix5 D 模式**:本阶段不动业务代码,只跑 + 验证 + 写报告。但**允许小修 bug**(如果撞 02 实施期没暴露的细节问题,可以小修 + 立刻重跑某批,不需要回到 02 重新 prompt)。

## § 2 上下文启动顺序

按序读完直接开干:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/loop_optim/README.md`
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— § 11 自动 commit/push + § 12 上下游互审
4. `rebuild5/docs/loop_optim/02_artifact_pipelined_report.md` —— **核心**,02 实施细节 + §5 给 03 的启动命令
5. `rebuild5/docs/loop_optim/01_index_additions_report.md` —— 索引现状(预期跑得更快的依据)
6. `rebuild5/docs/fix6_optim/03_pipelined_report.md` §3 —— fix6 03 batch 时长基线(对比靶子)
7. `rebuild5/docs/fix5/06_rerun_validation.md` §6 —— 串行 batch 时长基线(150 min 目标对比)
8. `rebuild5/scripts/run_citus_artifact_pipelined.py` —— 02 实施的新 runner
9. 本 prompt

读完直接开干。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`
- **当前 git 头**:`36fcaa5`(loop_optim 02 已 push 远端)
- **Git remote**:`https://github.com/laoyang75/OptiNet.git`(SSL 抖动严重,push 失败等 60s 重试一次)

### 数据库

- **Citus**:`postgres://postgres:123456@192.168.200.217:5488/yangca`,MCP `mcp__PG_Citus__execute_sql`
- **PG17**(只读基线):`mcp__PG17__execute_sql`,batch 7 TCL = 341,460
- **runner env**:`REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'`
- **auto_explain workaround**:启动 runner 必须 `PGOPTIONS='-c auto_explain.log_analyze=off'`
- **Citus 配置**:`citus.max_intermediate_result_size=16GB`(已 ALTER SYSTEM)

### 沙箱

已解除长跑限制。预期 ~90 分钟,直接 nohup 后台跑 + 定期 tail。

### 时长基线(对比靶子)

| Run | 全 7 批总时长 | speedup vs serial |
|---|---:|---:|
| fix5 D 串行 | ~9000s ≈ 150 min | 1.0× |
| fix6_optim 03 pipelined | 7,947s ≈ 132 min | 1.13× |
| **loop_optim 03 artifact pipelined**(目标) | **~5,400s ≈ 90 min** | **~1.67×** |

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `02_artifact_pipelined_report.md` | 阅读 | 启动命令 + 验收口径 |
| `06_rerun_validation.md` §3-6 | 阅读 | fix5 D 哨兵 SQL + 终点验收 SQL |
| `fix6_optim/03_pipelined_report.md` §3 | 阅读 | batch 时长对比基线 |
| 本阶段产出 `03_rerun_report.md` | 新建 | § 7 结构 |
| `rebuild5/docs/fix6_optim/04_runbook.md` | 修改(终点更新) | 加 artifact pipelined 命令 + 实测 90min/1.67× 数据 |

**本阶段不动业务代码**(02 已稳定),只在以下情况允许微调:
- runner 撞 producer/consumer 死锁 → 加 timeout / lock 等小修
- 哨兵 SQL 因 02 改了 input 表而需要适配
- artifact 索引建漏了某个 critical join key

任何代码改动 ≤ 30 行,且必须在 03 报告 §0 显式记录"03 阶段微调"。**超过 30 行就停 + blocker note + 退到 02 重做**。

## § 5 任务清单

### 必做(按顺序)

#### 5.1 reset 全量(开干前)

走 02 阶段已扩展的 reset SQL(包含 rb5_stage drop + state truncate):

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca \
  -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

验证:
```sql
SELECT count(*) FROM rb5.trusted_cell_library;            -- 期待 0
SELECT count(*) FROM rb5.cell_sliding_window;             -- 期待 0
SELECT count(*) FROM rb5.enriched_records;                -- 期待 0
SELECT count(*) FROM rb5_meta.pipeline_artifacts;         -- 期待 0
SELECT count(*) FROM information_schema.tables
 WHERE table_schema='rb5_stage';                          -- 期待 0
```

#### 5.2 启动全 7 批 artifact pipelined

```bash
cd /Users/yangcongan/cursor/WangYou_Data
PGPASSWORD=123456 \
PGGSSENCMODE=disable \
PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca' \
nohup python3 rebuild5/scripts/run_citus_artifact_pipelined.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  > /tmp/loop_optim_03_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > /tmp/loop_optim_03.pid
```

启动前 + 启动 ~30 秒后:
- `ps -p $(cat /tmp/loop_optim_03.pid)`:确认进程存活
- `tail -20 /tmp/loop_optim_03_*.log`:确认 plan 事件 + producer 启动事件
- 写 `topic='loop_optim_03_started'` note

#### 5.3 进度监控(每 5-15 分钟)

```bash
# 整体进度
tail -50 /tmp/loop_optim_03_*.log | grep -E "step1_done|step2_scope|batch_validation|step5_done|sentinels"

# state 表
mcp__PG_Citus__execute_sql:
SELECT batch_id, day, status, row_count,
       finished_at - created_at AS duration,
       LEFT(COALESCE(error,''), 100) AS error
FROM rb5_meta.pipeline_artifacts
ORDER BY batch_id;

# producer/consumer 进度差(artifact pipelined 的关键观察点)
SELECT
  (SELECT max(batch_id) FROM rb5_meta.pipeline_artifacts WHERE status IN ('ready', 'consumed')) AS max_produced,
  (SELECT max(batch_id) FROM rb5_meta.pipeline_artifacts WHERE status='consumed') AS max_consumed;
-- 期望 producer 一直领先 consumer ≥ 1
```

#### 5.4 每批跑完打 4 哨兵(grep batch_validation 触发)

每检测到 `batch_validation` for batch N(从 log)立刻打 fix5 D 同款 4 哨兵 SQL,bid 替换为 N:

```sql
-- #1 enriched 严格单日(允许 batch 1 Path-A 空批,沿用 fix6 03 修订)
SELECT batch_id, MIN(event_time_std)::date AS mind, MAX(event_time_std)::date AS maxd, COUNT(*) AS rows
FROM rb5.enriched_records WHERE batch_id = :bid GROUP BY batch_id;

-- #2 sliding 跨度 ≤ 14 天 + 无 2023/2024
SELECT MIN(event_time_std)::date AS mind, MAX(event_time_std)::date AS maxd,
       MAX(event_time_std) - MIN(event_time_std) AS span,
       COUNT(*) AS rows
FROM rb5.cell_sliding_window;

-- #3 当批 artifact 状态(替代 fix5 D 的 _step2_cell_input 哨兵,artifact 流水线下查 state 表更精准)
SELECT batch_id, status, row_count, day, finished_at - created_at AS duration
FROM rb5_meta.pipeline_artifacts WHERE batch_id = :bid;
-- 期望 status='consumed',row_count > 0

-- #4 TCL 单调
SELECT batch_id, COUNT(*) AS rows FROM rb5.trusted_cell_library
GROUP BY batch_id ORDER BY batch_id;
-- 期望 batch N rows > batch N-1 rows
```

**任意哨兵挂红立刻停**(`kill $(cat /tmp/loop_optim_03.pid)` + 写 blocker note),不要硬推。

#### 5.5 batch 7 终点 3 验收

```sql
-- (A) TCL b7 vs fix6 03 串行/pipelined ±5%
SELECT COUNT(*) AS citus_b7 FROM rb5.trusted_cell_library WHERE batch_id=7;
-- 期望 in [323,728, 357,805] (340,767 ± 5%)

-- (B) sliding 日期范围
SELECT MIN(event_time_std)::date AS mind, MAX(event_time_std)::date AS maxd
FROM rb5.cell_sliding_window;
-- 期望 mind in [2025-11-24, 2025-12-01], maxd = 2025-12-07,无 2023/2024

-- (C) enriched 7 批严格单日(batch 1 Path-A 空属预期)
SELECT batch_id, MIN(event_time_std)::date, MAX(event_time_std)::date, COUNT(*)
FROM rb5.enriched_records GROUP BY batch_id ORDER BY batch_id;
-- 期望 batch_id 2..7 共 6 行(或 1..7 共 7 行,看 batch 1 是否产 enriched 行)

-- 与 PG17 黄金对账(允许 ±20%)
mcp__PG17__execute_sql:
SELECT COUNT(*) FROM rebuild5.trusted_cell_library WHERE batch_id=7;
-- PG17 = 341,460,Citus pipelined 应 in [273,168, 409,752]
```

#### 5.6 时长对账

从 log + state 表收集:

| batch | producer T(s) | consumer T(s) | end-to-end T(s) | vs fix6 03 |
|---:|---:|---:|---:|---:|
| 1 | <n> | <n> | <n> | <%> |
| ... | | | | |
| 7 | <n> | <n> | <n> | <%> |
| **全 7 批 wall clock** | **<T_total>s** | | | speedup vs serial = <x>× |

**关键观察**:
- 总 wall clock = max(producer 总, consumer 总),不是 sum(因为流水线)
- 如果 max ≈ Step1 总耗时,说明 Step2-5 跑得快;如果 max ≈ Step2-5 总耗时,说明 Step1 跑得快(预期是后者,Step5 是瓶颈)
- speedup 目标 ≥ 1.5×(150 min → 100 min);**1.67× = stretch goal,>1.3× = 已经比 fix6 03 显著好**

#### 5.7 fix6_optim/04_runbook.md 更新

把 `04_runbook.md` 的关键基线表更新:

```markdown
## 4. 已验证的基线指标

| 指标 | PG17 黄金 | Citus 串行(fix5 D) | Citus pipelined(fix6 03) | Citus artifact pipelined(loop_optim 03) |
|---|---:|---:|---:|---:|
| TCL b7 总量 | 341,460 | 348,921(+2.19%) | 340,767(-0.20%) | <n>(<x>%) |
| 7 批总时长 | n/a | ~150 min | ~132 min | **<T> min** |
| speedup | 1.0× | 1.0× | 1.13× | **<x>×** |
```

并在 §1 命令清单中添加:

```bash
# 1.7 跑全 7 批(loop_optim artifact pipelined,默认推荐)
bash rebuild5/scripts/runbook/run_full_artifact_pipelined.sh
```

新建 `rebuild5/scripts/runbook/run_full_artifact_pipelined.sh`(参照 `run_full_pipelined.sh` 模板,只改 runner 文件名)。

#### 5.8 完工流程

`git add` 列:
- `rebuild5/docs/loop_optim/03_rerun_prompt.md`(本 prompt)
- `rebuild5/docs/loop_optim/03_rerun_report.md`(产出)
- `rebuild5/docs/loop_optim/README.md`(状态更新)
- `rebuild5/docs/fix6_optim/04_runbook.md`(基线更新)
- `rebuild5/scripts/runbook/run_full_artifact_pipelined.sh`(新)

如果 §4 允许范围内有 ≤ 30 行的 03 微调,**也在这个 commit 一起进**(报告 §0 显式列)。

一个 commit:
```
test(rebuild5): loop_optim 03 artifact pipelined full 7-batch validation

- Run all 7 batches end-to-end through run_citus_artifact_pipelined.py
- Wall clock T=<n>s vs fix6_03 7947s, speedup=<x>x;
  TCL b7=<n> within ±<x>% of fix6_03 340,767 and ±<x>% of PG17 341,460
- Per-batch sentinels (4 each) and endpoint 3-checks all PASS
- 03 micro-fixes (if any): <list or "无">
- Update fix6_optim/04_runbook.md baseline table and command list
- Add scripts/runbook/run_full_artifact_pipelined.sh

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push 撞 SSL 等 60s 重试一次,再失败标 push pending 不算 blocker。

写 note `topic='loop_optim_03_done'`,用 § 9 完工话术汇报。

### 不做(显式禁止)

- ❌ 不动业务代码(02 已稳定;允许 ≤ 30 行 03 微调,超过停 + blocker)
- ❌ 不动其他 4 个 02C test 文件 + fix6 02C 已扩展的 test
- ❌ 不删 03 fix6 pipelined / 串行 runner / artifact runner(都保留作 fallback)
- ❌ 不改分布键 / colocation / schema
- ❌ 不引入新依赖
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc
- ❌ 哨兵挂不"再跑一遍碰运气",立刻停 + blocker
- ❌ 数据一致性 ±5% 挂红 = 实质 blocker,不为加速妥协

## § 6 验证标准

任务 done 的硬标准:

1. **全 7 批跑完**:
   - `SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY 1` 返回 7 行
   - state 表 7 行,全 status='consumed'
2. **每批 4 哨兵 PASS**(报告 §3 完整列每批结果)
3. **终点 3 验收 PASS**:
   - TCL b7 in [323,728, 357,805](±5% vs fix6 03 340,767)
   - sliding maxd = 2025-12-07,mind ≥ 2025-11-24,无 2023/2024
   - enriched 各 batch 严格单日
4. **时长 wall clock ≤ 7,500s**(目标 5,400s,允许 +40% 偏差容错;>7,500s 算 stretch goal 未达但仍可完工)
5. **04_runbook.md 基线表更新** + 新 runbook script 落地
6. **commit + push**:`git rev-parse HEAD == git rev-parse origin/main`(允许标 push pending)
7. **note 写入**:`SELECT body FROM rb5_bench.notes WHERE topic='loop_optim_03_done'` 含 wall clock + speedup + TCL b7

## § 7 产出物 `03_rerun_report.md`

```markdown
# loop_optim / 03 全 7 批重跑验证报告

## 0. TL;DR + 03 微调清单
- 全 7 批 artifact pipelined wall clock = <n>s = <m> min
- speedup vs fix5 D serial(150 min):<x>×;vs fix6 03(132 min):<y>×
- TCL b7:<n>,vs fix6 03 340,767 偏差 <X.XX>%,vs PG17 341,460 偏差 <X.XX>%
- 4 哨兵 × 7 批 = 28 项 PASS,终点 3 验收 PASS
- 03 微调:<无 / 列出 ≤ 30 行的具体改动>
- 对 02 报告修订:<无 / 列表>
- commit SHA:<sha>;push 状态:<status>
- loop_optim 收档?<是/否>

## 1. 启动信息
- reset 命令 + 验证结果
- runner 启动命令 + PID + 日志路径
- 启动时间

## 2. 批次时长 + state 表
| batch | day | producer T(s) | consumer T(s) | end-to-end T(s) | TCL rows | vs fix6 03 |
| ---:| --- | ---:| ---:| ---:| ---:| ---:|
| 1 | 2025-12-01 | ... | ... | ... | ... | ... |
| ... |
| 7 | 2025-12-07 | ... | ... | ... | ... | ... |
| **wall clock 总** | | producer 总=<n>s | consumer 总=<n>s | **max=<n>s** | total=<n> | speedup=<x>× |

producer/consumer 进度差曲线(每 5 分钟采样一次的 max_produced - max_consumed):
- 起步 ~5 分钟:差距 0(producer 比 consumer 快但还没积压)
- 中段 ~30-60 分钟:差距 ≥ 1(producer 领先,流水线生效)
- 收尾:producer 跑完 day 7 后 stop,consumer 继续消费
- ASCII 简图

## 3. 每批 4 哨兵
### batch 1
- #1 enriched: ...
- #2 sliding: ...
- #3 artifact state: status=consumed, rows=<n>, duration=<s>
- #4 TCL 单调: rows=<n>
(batch 2~7 同结构)

## 4. 终点 3 验收
- (A) TCL b7 = <n>,vs fix6 03 340,767 偏差 <X.XX>%,**PASS/FAIL**
- (B) sliding mind=<d>, maxd=<d>,**PASS/FAIL**
- (C) enriched 7 批严格单日,**PASS/FAIL**
- PG17 对比:Citus <n> vs PG17 341,460 偏差 <X.XX>%(±20% 范围)

## 5. 时长分析
- 全 7 批 wall clock = max(producer T 总, consumer T 总) = <max>s
- producer 总 = <n>s(Step1 实际耗时,40 核 SETUP 后估计 ~15-20 min)
- consumer 总 = <n>s(Step2-5 顺序总耗时,~80-90 min)
- speedup 来自:Step1 与 Step2-5 完全重叠;Step1 ~20 min 被 consumer ~90 min 完全掩盖
- 与 fix6 03 对比(132 min vs 90 min):压缩了约 30%,主因是 03 用 barrier 而 loop_optim 用 immutable artifact 解锁了 producer 持续推进

## 6. 04_runbook.md + 新 runbook script 更新点

## 7. 已知限制 / 03 微调
- producer/consumer 资源压力(CPU / connection / lock)实测
- artifact 物理空间(7 张表 ~5M rows × 7 = ~35M rows × LIKE etl_cleaned schema 开销)
- 03 微调清单(每条 ≤ 30 行,在 02 报告 §4 / §5 范围内允许的 micro 调整)

## 8. loop_optim 总账
- 01 索引补全:25 条 live + 5 deferred templates
- 02 artifact pipelined + Step1 40 核:rb5_stage + state 表 + 新 runner
- 03 全 7 批重跑:T=<n>s,speedup=<x>×,TCL b7 ±<x>% vs fix6 03
- (04 UI 留下个阶段)
```

## § 8 notes 协议

- 开跑前:`topic='loop_optim_03_started'` info
- 关键事件(可选):`topic='loop_optim_03_batch_<N>'` info(每批跑完时)
- 哨兵挂:`topic='loop_optim_03_blocker_batch_<N>_sentinel_<#>'` blocker
- 完工:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('loop_optim_03_done', 'info',
    'artifact pipelined full 7-batch validated: wall_clock=<n>s, speedup vs serial=<x>x, vs fix6_03=<y>x, TCL b7=<n> +-<x>% vs fix6_03 340767 / +-<x>% vs PG17 341460, all sentinels pass, head=<sha>');
  ```
- 失败:`topic='loop_optim_03_failed'` blocker

## § 9 完工话术(loop_optim 主线收档,UI 留 04 阶段)

成功:
> "loop_optim 03 完成。03_rerun_report.md 已写入。artifact pipelined 全 7 批 wall clock=<n>s=<m>min,speedup=<x>× vs serial / <y>× vs fix6 03。TCL b7=<n>,vs fix6 03=<x>%,vs PG17=<y>%。28 项哨兵 + 3 终点验收全过。03 微调:<无 / 列表>。04_runbook.md 已更新基线 + 新增 artifact pipelined 命令。commit=<SHA>,GitHub:<url>(push <成功/pending>)。loop_optim 主线收档,UI 04 阶段独立支线。notes `topic='loop_optim_03_done'` 已插入。"

失败:
> "loop_optim 03 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='loop_optim_03_failed'`。等上游处置。working tree 未回滚保留给 review。"

## § 10 失败兜底

- **producer 撞 Step1 SQL 错误**(40 核 SETUP 副作用):降级 SETUP(去掉 `parallel_tuple_cost` / `parallel_setup_cost`,只保留 `max_parallel_workers_per_gather=40`);若仍挂,回退到无 SETUP 跑(性能差但功能 OK)。**这属于 ≤ 30 行 03 微调允许范围**
- **artifact 表 colocate 失败**(distribution key 类型不一致):02 应已处理,若再撞,在报告 §7 列出实际形态(distributed without colocate / reference / local),**功能优先**
- **consumer 撞 Citus distributed plan 错误**:复制完整 traceback,**先尝试单独跑 fix6 03 pipelined / 串行 runner**(都还在),如果它们也撞同错,blocker;如果只 artifact runner 撞,看是不是 input_relation 路径在 Step2 内某处没 propagate
- **producer/consumer 死锁**(consumer wait queue,producer 推进卡住):看 `pg_locks` + log,如果是 advisory lock 撞,加 `--max-pipeline-depth 1` 降级跑(producer 等 consumer 完成才推进下一 day);时长会差一些但功能 OK
- **TCL b7 vs fix6 03 偏差 > 5%**:**根本性数据问题**,立刻停 + blocker note + 完整对账 + 完整 8 类 drift_pattern 分布对比(可能是 artifact 切分不对造成 batch 1 数据污染)
- **wall clock > 7,500s**(超 +40% 容错):标 stretch goal 未达,记录 producer/consumer 总耗时分解 + 瓶颈分析,**仍算完工**
- **GitHub HTTPS SSL 抖动**:等 60s 重试,push pending 不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
