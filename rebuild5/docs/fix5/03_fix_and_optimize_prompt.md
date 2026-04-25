# OptiNet rebuild5 Citus 迁移 · fix5 / C 阶段 bugfix + 战术优化(agent 新实例对话)

> 你是 OptiNet-main / rebuild5 fix5 C 阶段的 agent 新实例。
> A 阶段(Claude)已产出 `rebuild5/docs/fix5/01_quality_diagnosis.md`,定位了根因。
> B 阶段(agent)已产出 `rebuild5/docs/fix5/02_agent_change_audit.md`,回滚了 B/C 类改动,保留了 Citus 兼容(A 类)的所有必要改动。
> **本轮你做:精准修 bug + 1 条全局参数调整 + 小样本(1~2 批)验证。不跑 7 批全量(那是 D 阶段)。**

---

## 1. 上下文启动顺序(必须按顺序读完再动手)

1. 仓库根目录 `AGENTS.md`(写死的协作规约)
2. `rebuild5/docs/fix5/README.md`(本目录全局,看 C 阶段边界与"不做"清单)
3. `rebuild5/docs/fix5/01_quality_diagnosis.md`(根因定位 + 修复清单 §3 + 重跑策略 §4,**这是你要执行的设计书**)
4. `rebuild5/docs/fix5/02_agent_change_audit.md`(B agent 已经做过的回滚/清理,避免你把已经删掉的 B/C 类改动又加回来)

**读完之后不要立刻动手**。先在对话中列出你识别到的:
- A 阶段要求你改的 2~3 处代码(按 01 §3)
- B 阶段已经删掉/清理过的东西(避免重复撤回)
- 你决定在 C 阶段是否采纳修复 C(`get_step2_input_relation` 过期保护,01 §3 "推荐")

得到我(上游 Claude 或用户)确认后再改代码。

---

## 2. 定位与边界

**你要做**(严格)

1. **修 bug**(必做,精确改动):
   - `rebuild5/scripts/run_citus_serial_batches.py`:在主循环里,每批 `run_step1_pipeline()` 完成之后、`run_profile_pipeline()` 之前,调用 `materialize_step2_scope(day=day, input_relation='rb5.etl_cleaned')`;该函数已在 `rebuild5/scripts/run_daily_increment_batch_loop.py:148` 定义,直接 import 复用。
   - 在每批开始处显式 `DROP TABLE IF EXISTS rb5._step2_cell_input`(兜底,防止 fallback 分支被 stale 表触达)。
   - 01 §3 "修复 C"(`backend/app/profile/pipeline.py::get_step2_input_relation` 的 fallback 过期保护)**列为可选**;除非你在第 6 步单批验证中发现 fallback 还被触达,否则**不要加**。

2. **全局调大 citus 中间结果限制**(必做,1 条 SQL):
   ```sql
   ALTER SYSTEM SET citus.max_intermediate_result_size = '16GB';
   SELECT pg_reload_conf();
   ```
   走 coordinator 节点。验证用 `SHOW citus.max_intermediate_result_size;` 得到 `16GB`。
   不要在业务代码里散落 session SET(B 阶段已经清掉了,不要加回来)。

3. **Pipelined 并行(Step 1 / Step 2-5)**(必做,单独一次改动):
   - 参考本地已有的 `rebuild5/scripts/run_step1_step25_pipelined_temp.py` 的模式,把 Step 1(day N+1)和 Step 2-5(day N)做成 pipelined —— Step 1 一跑完 day N 就让 Step 2-5 day N 并发启动,Step 1 继续推进 day N+1。
   - 目标:在 Citus runner 上实现同样的 pipelined 行为。实现方式:
     - **方案 A**(首选):改 `run_citus_serial_batches.py`,把 Step 1 和 Step 2-5 拆成两个 asyncio task / 两个线程,用一个 `asyncio.Queue` / `queue.Queue` 做 day 级流水。
     - **方案 B**(如果方案 A 复杂度爆炸):新写一个 `run_citus_pipelined_batches.py`,保留 `run_citus_serial_batches.py` 作为 fallback;但**必须**把 §2.1 的 bug 修复同步落到 pipelined runner 里。
   - **关键规则**:Pipelined 不要和 §2.1 bugfix 同一轮提交做验证。先只开 §2.1 + §2.2,在单批串行跑通拿到正确 metric,**再**开 §2.3 pipelined 再跑一次单批对齐。

4. **小样本(1~2 批)验证**(必做):
   - `SELECT * FROM rb5_bench.notes WHERE topic='fix5_audit_complete' ORDER BY created_at DESC LIMIT 1;` 先确认 B 阶段已完工。
   - 执行 `psql ... -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql` 做 full reset(01 §4 明确要求,污染是从 batch 1 开始的,不能接跑)。
   - 跑 **batch 1**(day=2025-12-01)单批,打 §5 的回归哨兵指标,和 PG17 基线对齐(允许 ±5%)。
   - 跑 **batch 2**(day=2025-12-02)单批,再打一次哨兵指标,确认 `enriched_records` 严格单日、`cell_sliding_window` 跨度 ≤ 14 天、`_step2_cell_input` 的 `event_time_source='report_ts'` 行范围推进到 batch 2 的 day。
   - 如果 1~2 批都过,停(不跑 7 批)。7 批全量由 D 阶段做。

5. **产出物**:
   - `rebuild5/docs/fix5/04_code_fix_report.md`(下面 §6 的结构)
   - `rb5_bench.notes` 完工信号(`topic='fix5_C_done'`,含 batch 1/2 单批哨兵指标 summary)

**你不做**(严格)

- ❌ 不 `git commit / push`(上游 review 后统一做)
- ❌ 不跑 batch 3~7,不碰 D 阶段的工作
- ❌ 不改分布键、不改 colocation group、不动 sliding_window 表结构、不重构 label_engine 候选池(README §6 "不做"清单)
- ❌ 不改 `etl/fill.py`(cell_ts 回退是产品设计,不是 bug;01 §2.4 已澄清)
- ❌ 不恢复 B 阶段删掉的任何东西(02 §2 清单内的 4 段 B 类 + 4 段 C 类)
- ❌ 不 DROP `rb5_bench.*` / `claude_diag.*` 里的任何表(诊断/对照要用)
- ❌ 不动旧库 PG17(5433/ip_loc2)
- ❌ 不在业务代码里加 `SET citus.max_intermediate_result_size`、`SET auto_explain`(全局 ALTER SYSTEM 是唯一入口)
- ❌ 不 `git reset --hard`、不 `git checkout -- <file>`、不 `git stash`
- ❌ 不开 subagent、不用 `python3 - <<'PY'` stdin heredoc

上下文纪律:
- 大文件 diff 截关键节选进 04,不要把几百行 diff 全塞对话
- 长跑任务走后台 + 日志轮询,不要同步阻塞等待

---

## 3. 环境(硬信息)

仓库:`/Users/yangcongan/cursor/WangYou_Data`(完整读写权)

**旧库(PG17,只读基线,对齐目标)**
- DSN:`postgres://postgres:123456@192.168.200.217:5433/ip_loc2`
- MCP:`mcp__PG17__execute_sql`
- psql 兜底:`PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2`(密码 `123456`)

**新集群(Citus,主目标)**
- DSN:`postgres://postgres:123456@192.168.200.217:5488/yangca`
- MCP:`mcp__PG_Citus__execute_sql`
- psql 兜底:`PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca`
- Python runner 用 env `REBUILD5_PG_DSN=postgres://postgres:123456@192.168.200.217:5488/yangca`

**集群规格**(1 coordinator + 4 worker,每台 20 物理 / 40 逻辑 / 251GB 内存)
- Citus 14.0-1 / PostGIS 3.6.3 / pg_stat_statements / auto_explain 已加载

**不需要**:Web/UI 登录、SSH。`ALTER SYSTEM` 走 coordinator 即可(MCP 或 psql 都行)。

---

## 4. 具体修复步骤(带文件行号,边改边验)

### 4.1 修复 A(必做):runner 每批物化 step2_batch_input

**目标文件**:`rebuild5/scripts/run_citus_serial_batches.py`

**改动 1**(顶部 import,大约 L14~L20 附近):
```python
from run_daily_increment_batch_loop import materialize_step2_scope
```
(注意相对 import 路径;如果 `run_citus_serial_batches.py` 作为 `python -m` 入口跑的,要用 `from rebuild5.scripts.run_daily_increment_batch_loop import materialize_step2_scope` 的绝对路径,按当前脚本的实际运行方式对齐。)

**改动 2**(主循环 batch 内,约 L813~L877):在 `step1 = run_step1_pipeline(...)` / `_log({"event": "step1_done", ...})` 之后、`run_profile_pipeline()` 之前插入:
```python
execute("DROP TABLE IF EXISTS rb5._step2_cell_input")
scope_rows = materialize_step2_scope(day=day, input_relation='rb5.etl_cleaned')
_log({"event": "step2_scope_materialized", "day": day.isoformat(), "rows": scope_rows})
```

**验证(batch 1 跑完后)**:
```sql
-- 期待严格单日,2025-12-01 一整天
SELECT MIN(event_time_std), MAX(event_time_std), COUNT(*)
FROM rb5.step2_batch_input;

-- 期待:只有 batch 1 对应的一天
SELECT MIN(event_time_std)::date, MAX(event_time_std)::date, COUNT(*)
FROM rb5.enriched_records WHERE batch_id = 1;

-- _step2_cell_input 要么不存在,要么每批跑完后被 drop
SELECT to_regclass('rb5._step2_cell_input');
```

### 4.2 修复 B(B 阶段已完成,仅验证)

`rebuild5/scripts/run_citus_serial_batches.py` 里的
`os.environ.setdefault("REBUILD5_SKIP_SLIDING_WINDOW_TRIM", "1")` 应该已被 B 阶段删除。
**不要加回来**。只做一次 grep 验证:
```bash
grep -n "REBUILD5_SKIP_SLIDING_WINDOW_TRIM" rebuild5/scripts/run_citus_serial_batches.py
```
期待无命中。

### 4.3 Citus 全局中间结果限制调大

```sql
-- 在 coordinator 执行
ALTER SYSTEM SET citus.max_intermediate_result_size = '16GB';
SELECT pg_reload_conf();
SHOW citus.max_intermediate_result_size;  -- 期待 '16GB'
```

说明:服务器 251GB 内存,1GB 默认值太保守;sliding_window trim 大 DELETE + label_engine 的 DBSCAN partition 在 Citus 都会触达这个阈值。`16GB` 是保守起点,单个 repartition 不会一次性把 coordinator 内存吃爆。

### 4.4 Pipelined 并行

只有在 §4.1~§4.3 的 batch 1/2 单批指标全部对齐 PG17 黄金基线后再做。分两步:

**Step A**:读 `rebuild5/scripts/run_step1_step25_pipelined_temp.py`,理解它在 PG17 上的 pipelined 结构。
**Step B**:在 `run_citus_serial_batches.py`(方案 A)或新脚本(方案 B)上实现同样的 pipelined 行为。
**Step C**:在开启 pipelined 后再跑一次 batch 1(reset 后),打同样的 §5 哨兵。pipelined 后的 `trusted_cell_library` 分布必须和 §4.1~§4.3 阶段对齐。

如果 pipelined 实现复杂度远超预期,C 阶段可以**只完成 §4.1~§4.3**,把 pipelined 作为 `TODO` 记在 04,交给 D 阶段或后续迭代。**这件事不值得压垮整个 C 阶段**。

---

## 5. 单批回归哨兵(batch 1 / batch 2 必须全部过)

按 01 §4 "回归哨兵" 抄,每批跑完立刻执行,任意一条挂掉就停 run 并在 04 记录 blocker。

```sql
-- (1) 当前 batch 的 enriched_records 严格单日
SELECT batch_id, MIN(event_time_std)::date, MAX(event_time_std)::date, COUNT(*)
FROM rb5.enriched_records WHERE batch_id = :bid GROUP BY batch_id;

-- (2) sliding_window 跨度 ≤ 14 天(batch 1 允许更短;batch 2 起要能看到 2 天推进)
SELECT MAX(event_time_std) - MIN(event_time_std) AS span,
       MIN(event_time_std)::date, MAX(event_time_std)::date
FROM rb5.cell_sliding_window;

-- (3) 多质心类别至少其一 > 0(batch 1 允许都 0 —— 候选池还没累积;batch 2 起至少 large_coverage > 0)
SELECT drift_pattern, COUNT(*)
FROM rb5.trusted_cell_library WHERE batch_id = :bid
GROUP BY drift_pattern ORDER BY 2 DESC;

-- (4) _step2_cell_input 不含 stale 数据(如果还存在)
SELECT MIN(event_time_std), MAX(event_time_std), COUNT(*)
FROM rb5._step2_cell_input;  -- 理想情况是 DROP 掉了,to_regclass 为 NULL
```

和 PG17 同批(batch 1 = 2025-11-30 对应的 batch 1 产出)用 `mcp__PG17__execute_sql` 对比:
- `trusted_cell_library` batch 1 行数 ±5%
- `drift_pattern='stable'` 行数 ±5%
- `label_results` k_eff 分布 ±20%(k_eff=0 量大,占比稳;k_eff≥3 数量小,允许更大相对偏差)
- `cell_sliding_window` 跨度必须 ≤ PG17 同批跨度 + 1 天

---

## 6. 产出物 `04_code_fix_report.md` 结构

```markdown
# fix5 / 04 代码修复 + 战术优化报告

## 0. TL;DR
- 三件事做了几件,哪件 skip / 为什么
- batch 1/2 哨兵是否全过,关键偏差

## 1. 改动清单
| 文件 | 动作 | 对应 01 §x | diff 行数 |
| --- | --- | --- | --- |
| `rebuild5/scripts/run_citus_serial_batches.py` | import + 每批 materialize_step2_scope | 01 §3 修复 A | +X / -Y |
| ... | ... | ... | ... |

## 2. 逐段 diff(截关键行,不贴大段)

### 2.1 修复 A:runner materialize_step2_scope
```diff
...
```

### 2.2 citus.max_intermediate_result_size 全局调大
- 执行了 `ALTER SYSTEM ...` + `pg_reload_conf()`
- `SHOW` 验证结果:`16GB`

### 2.3 Pipelined 并行
- 方案 A / 方案 B / 推迟 —— 哪个,为什么
- 如做了,加了哪些文件 / 改了哪里
- batch 1 串行 vs pipelined 指标对比

## 3. 单批验证
### batch 1(day=2025-12-01)
- 哨兵 1/2/3/4 结果,逐项贴 SQL 输出
- PG17 对比结果
- Pass / Fail

### batch 2(day=2025-12-02)
- 同上

## 4. 已知问题 / 交接 D 阶段
- D 阶段在开始前要不要再次 reset(我建议:一次性 reset + 直接跑 7 批)
- Pipelined 有没有 TODO 留给 D
- 任何 `severity='suspect'` 的 notes 清单

## 5. 附录
- 关键 SQL 完整输出(batch 1/2 哨兵 4 条 × 2 批 = 8 块)
- 运行日志关键片段(step2_scope_materialized 的 rows 数值)
```

**notes 完工信号**:
```sql
INSERT INTO rb5_bench.notes (topic, severity, message, created_at)
VALUES ('fix5_C_done', 'info',
        'batch1 sentinels: enriched=<n> tcl=<n> sw_span=<d>; batch2: ... ; ready for D rerun',
        now());
```

---

## 7. 核心原则(fix5 通用)

- **严格串行**:C → D,D 必须等 C 的 04 + 上游 review 通过
- **不 commit / push**:working tree 保留给上游统一做
- **不跑全量 7 批**:batch 1~2 验证后立即停
- **不改旧库**:5433/ip_loc2 只读
- **不 DROP rb5_bench / claude_diag**:诊断要用
- **`rb5_bench.notes` 是 C 和 D 之间唯一异步通信通道**,不要在代码里加其他同步点
- **有疑问先写 `severity='suspect'` note 再推进**,不要硬扛

---

## 8. 你最后一句话

完成后在本对话回一句:
> "C 阶段完成。04 在 `rebuild5/docs/fix5/04_code_fix_report.md`。notes `topic='fix5_C_done'` 已插入。batch 1/2 哨兵 [pass / 具体哪条 fail]。pipelined [已实现 / 已推迟 / 未做]。请上游 review 后开启 D。"

**不要**在未验证情况下写 "已完成"。验证失败就写 "卡在哪一步,blocker 是什么,建议上游下一步"。
