# OptiNet rebuild5 / loop_optim / 02 artifact pipelined + Step1 40 核(agent 新实例对话)

## § 1 元目标

实施用户拍板的 **immutable artifact 流水线**架构,切断 Step1/Step2-5 的虚假依赖:

- **Step1 producer 顺序跑 7 天**(不并行 7 天 Step1),每完成 1 天立刻冻结 `rb5_stage.step2_input_b<N>_<YYYYMMDD>` 不可变 artifact
- **Step2-5 consumer 顺序消费 artifact**(因 cumulative TCL 依赖必须串行)
- 总耗时 ≈ max(Step1 全 7 天 ~20min, Step2-5 全 7 批 ~90min) ≈ **~90 分钟**(目标加速比 ~1.67×)

附加优化:**Step1 SQL 加 PG parallel hint 拉到 40 核**(`max_parallel_workers_per_gather` 等),进一步压 Step1 单天耗时。

**本阶段只实施 + 静态验证,不实际跑全 7 批**(留给 03 阶段,fix5 C/D 模式)。

## § 2 上下文启动顺序

按序读完直接开工(自主推进,无开跑前 ack):

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/loop_optim/README.md`
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— **§ 11 自动 commit/push** + **§ 12 上下游互审**
4. `rebuild5/docs/loop_optim/01_index_additions_report.md` —— 索引现状 + §4 给 02 的 artifact 表索引模板(直接抄)
5. `rebuild5/docs/fix6_optim/03_pipelined_report.md` —— 03 pipelined 设计 + 1.13× 局限分析
6. `rebuild5/docs/fix6_optim/02B_refactor_report.md` —— `core/citus_compat.execute_distributed_insert` 接口(本阶段 Step1 40 核 SET 走它的 session_setup_sqls)
7. `rebuild5/scripts/run_citus_pipelined_batches.py` —— 03 已实现的 producer/consumer 框架,可借鉴
8. `rebuild5/scripts/run_daily_increment_batch_loop.py::materialize_step2_scope` —— 当前 scope 物化函数,要在它基础上做 artifact 化
9. `rebuild5/backend/app/profile/pipeline.py::get_step2_input_relation` (L542-L568)—— Step2 input 隐式查找,要改显式参数
10. `rebuild5/backend/app/profile/pipeline.py::run_profile_pipeline` —— Step2-3 入口,要加 input_relation 参数
11. 本 prompt

读完直接开工。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`
- **当前 git 头**:`0b6d902`(loop_optim 01 收档,已 push)
- **Git remote**:`https://github.com/laoyang75/OptiNet.git`(private + 局域网)

### 数据库

- **Citus**:`postgres://postgres:123456@192.168.200.217:5488/yangca`,MCP `mcp__PG_Citus__execute_sql`
- **PG17**(只读基线,本阶段不需要)
- **runner env**:`REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'`
- **auto_explain**:`PGOPTIONS='-c auto_explain.log_analyze=off'`(本阶段不实际跑 runner,但写 runner 时要设)
- **Citus 参数**:`citus.max_intermediate_result_size=16GB`(已 ALTER SYSTEM)

### 沙箱

已解除长跑限制(03 阶段已用过)。本阶段不需要 nohup,只静态实施 + 单批 dry-run 验证 < 5 分钟。

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `loop_optim/01_index_additions_report.md` §4 | 阅读 | artifact 表索引模板(直接抄) |
| `fix6_optim/02B_refactor_report.md` | 阅读 | `execute_distributed_insert` 接口 + session_setup_sqls 用法 |
| `fix6_optim/03_pipelined_report.md` | 阅读 | producer/consumer 框架 + 1.13× 限制原因 |
| `rebuild5/backend/app/profile/pipeline.py` | 修改 | `get_step2_input_relation` + `run_profile_pipeline(input_relation=)` |
| `rebuild5/backend/app/etl/pipeline.py` | 修改 | Step1 入口加 40 核 session SET(via citus_compat) |
| `rebuild5/scripts/run_daily_increment_batch_loop.py` | 修改 | `materialize_step2_scope` 加 artifact 化变体或新建 `freeze_step2_input_artifact` |
| `rebuild5/backend/app/maintenance/schema.py` | 修改 | 加 `rb5_meta.pipeline_artifacts` reference table |
| `rebuild5/scripts/run_citus_artifact_pipelined.py` | **新建** | producer + consumer + state 表 |
| `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql` | 修改 | 加 drop `rb5_stage.*` + truncate `rb5_meta.pipeline_artifacts` |
| `rebuild5/tests/test_runner_scope_materialization.py` | 修改 | 加 1 个 test 守护 artifact 流水线 |
| 本阶段产出 `02_artifact_pipelined_report.md` | 新建 | § 7 结构 |

**本阶段不修改其他 .md 文档**(runbook 留给 03 阶段更新)。

## § 5 任务清单

### 必做(按顺序)

#### 5.1 创建 `rb5_stage` schema + `rb5_meta.pipeline_artifacts` 状态表

via Citus MCP 跑(也写进 `maintenance/schema.py` 持久化):

```sql
CREATE SCHEMA IF NOT EXISTS rb5_stage;

CREATE TABLE IF NOT EXISTS rb5_meta.pipeline_artifacts (
    batch_id INTEGER PRIMARY KEY,
    day DATE NOT NULL,
    artifact_relation TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'ready', 'consumed', 'failed')),
    row_count BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    error TEXT
);

-- 把它注册成 reference table(全 worker 复制,consumer 本地查询)
SELECT create_reference_table('rb5_meta.pipeline_artifacts');
```

#### 5.2 实现 `freeze_step2_input_artifact(*, batch_id, day, source_relation='rb5.etl_cleaned')`

新函数,加在 `rebuild5/scripts/run_daily_increment_batch_loop.py`(与 `materialize_step2_scope` 同文件)。

```python
def freeze_step2_input_artifact(
    *,
    batch_id: int,
    day: date,
    source_relation: str = 'rb5.etl_cleaned',
) -> tuple[str, int]:
    """Freeze当 day 的 etl_cleaned 切片到 immutable artifact 表。
    
    Returns:
        (artifact_relation, row_count)
    """
    artifact = f"rb5_stage.step2_input_b{batch_id}_{day.strftime('%Y%m%d')}"
    start_ts = _day_start_ts(day)
    end_ts = _day_start_ts(day + timedelta(days=1))
    
    # State: running
    execute("""
        INSERT INTO rb5_meta.pipeline_artifacts
            (batch_id, day, artifact_relation, status, created_at)
        VALUES (%s, %s, %s, 'running', NOW())
        ON CONFLICT (batch_id) DO UPDATE
            SET day=EXCLUDED.day, artifact_relation=EXCLUDED.artifact_relation,
                status='running', created_at=NOW(),
                finished_at=NULL, row_count=NULL, error=NULL
    """, (batch_id, day, artifact))
    
    try:
        # Drop if exists, then UNLOGGED distributed CTAS-WITH-NO-DATA + INSERT
        execute(f'DROP TABLE IF EXISTS {artifact}')
        execute(f"""
            CREATE UNLOGGED TABLE {artifact} (LIKE {source_relation} INCLUDING DEFAULTS)
        """)
        # 与 etl_cleaned colocate(假设 etl_cleaned 已 distributed by 某 column)
        # 用 core/database.py 现有 helper(02B citus_compat 间接)
        # ...或者 SELECT create_distributed_table(artifact, '<dist_col>', colocate_with=source_relation)
        execute(f"""
            SELECT create_distributed_table('{artifact}', '<distribution_column>',
                                             colocate_with => '{source_relation}')
        """)
        # populate
        execute(f"""
            INSERT INTO {artifact}
            SELECT * FROM {source_relation}
            WHERE event_time_std >= %s AND event_time_std < %s
        """, (start_ts.isoformat(), end_ts.isoformat()))
        
        # 抄 01 报告 §4 给的索引模板(参考 step2_batch_input 现有索引)
        execute(f'CREATE INDEX idx_{artifact_short}_cell ON {artifact} (cell_id)')
        execute(f'CREATE INDEX idx_{artifact_short}_op_lac_cell ON {artifact} (operator_filled, lac_filled, cell_id)')
        execute(f'CREATE INDEX idx_{artifact_short}_record ON {artifact} (record_id)')
        execute(f'ANALYZE {artifact}')
        
        row = fetchone(f'SELECT COUNT(*) AS cnt FROM {artifact}')
        row_count = int(row['cnt']) if row else 0
        
        # State: ready
        execute("""
            UPDATE rb5_meta.pipeline_artifacts
            SET status='ready', row_count=%s, finished_at=NOW()
            WHERE batch_id=%s
        """, (row_count, batch_id))
        
        return artifact, row_count
    except Exception as e:
        # State: failed
        execute("""
            UPDATE rb5_meta.pipeline_artifacts
            SET status='failed', error=%s, finished_at=NOW()
            WHERE batch_id=%s
        """, (str(e)[:500], batch_id))
        raise
```

**注意**:
- `<distribution_column>` 要查 `etl_cleaned` 实际分布键(`SELECT logicalrelid, partkey FROM pg_dist_partition WHERE logicalrelid='rb5.etl_cleaned'::regclass`)— **agent 第一步先查实际分布键**,不要硬编码
- 如果 `etl_cleaned` 是 reference table 而不是 distributed,artifact 就建 reference table(`create_reference_table`)
- 索引按 01 §4 模板建,artifact 名太长就用 hash 后缀(避免 PG 63 字符限制)

#### 5.3 改 Step2 入口支持显式 `input_relation` 参数

修改 `rebuild5/backend/app/profile/pipeline.py`:

```python
# 当前(不改):
def get_step2_input_relation() -> str:
    if relation_exists(STEP2_INPUT_SCOPE_RELATION):
        return STEP2_INPUT_SCOPE_RELATION
    if relation_exists(STEP2_FALLBACK_CELL_RELATION):
        return STEP2_FALLBACK_CELL_RELATION
    if relation_exists('rb5.etl_cleaned'):
        # ... fallback create
    raise RuntimeError("no step2 input")

# 改成:
def get_step2_input_relation(*, override: str | None = None) -> str:
    """Step2 input 入口。override 优先,否则保留隐式查找(向后兼容)。"""
    if override:
        if not relation_exists(override):
            raise RuntimeError(f"input_relation '{override}' does not exist")
        return override
    # ... 原有 fallback 链
```

`run_profile_pipeline` 改签名:

```python
def run_profile_pipeline(
    *,
    input_relation: str | None = None,  # 新增,显式优先
    ...
) -> dict:
    step2_input = get_step2_input_relation(override=input_relation)
    # ...
```

`run_enrichment_pipeline` / `run_maintenance_pipeline` 一般不直接读 etl_cleaned,但要 grep 一遍确认。如果有 reader,同样加 override 参数。

**向后兼容**:不改的 caller 走原 fallback 链,行为不变(03 pipelined 仍可用)。

#### 5.4 Step1 加 PG parallel hint 拉到 40 核

修改 `rebuild5/backend/app/etl/pipeline.py`(Step1 主入口),把每条大 INSERT...SELECT 走 02B 的 `execute_distributed_insert` + `session_setup_sqls`:

```python
from ..core.citus_compat import execute_distributed_insert

PARALLEL_40_SETUP = [
    "SET max_parallel_workers_per_gather = 40",
    "SET max_parallel_workers = 40",
    "SET max_parallel_maintenance_workers = 16",
    "SET parallel_tuple_cost = 0.01",
    "SET parallel_setup_cost = 100",
]

# Step1 内部的 INSERT...SELECT 都改用:
execute_distributed_insert(
    "INSERT INTO rb5.etl_cleaned ... SELECT ... FROM rb5.etl_parsed ...",
    session_setup_sqls=PARALLEL_40_SETUP,
)
```

**只在 Step1 阶段(parse / clean / fill)用这个高并行 SETUP**,Step2-5 不用(它们已经有自己的 query 形态,过度并行可能反而慢)。

如果 Step1 现有 SQL 是 raw `execute(sql)`(无 params),也可以走 `execute_distributed_insert(sql, session_setup_sqls=PARALLEL_40_SETUP)`,02B helper 兼容 params=None 路径。

#### 5.5 新 runner `run_citus_artifact_pipelined.py`

完整 producer + consumer + state 持久化。骨架:

```python
"""artifact-driven pipelined runner.

Producer 顺序跑 7 天 step1 + freeze artifact;Consumer 串行消费 artifact 跑 step2-5。
state 持久化在 rb5_meta.pipeline_artifacts。
"""

import argparse, threading
from datetime import date, timedelta
from queue import Queue, Empty
# ... import step1/step2-5 + freeze_step2_input_artifact + execute/fetchone

def producer(days: list[date], start_batch_id: int, q: Queue, stop_event: threading.Event):
    for i, day in enumerate(days):
        if stop_event.is_set():
            break
        bid = start_batch_id + i
        try:
            _load_raw_day(day, expected_batch_id=bid)
            run_step1_pipeline()  # 内部已经走了 PARALLEL_40_SETUP
            artifact, row_count = freeze_step2_input_artifact(batch_id=bid, day=day)
            q.put({'batch_id': bid, 'day': day, 'artifact': artifact, 'row_count': row_count})
        except Exception as e:
            _log({'event': 'producer_failed', 'batch_id': bid, 'error': str(e)})
            stop_event.set()
            raise

def consumer(q: Queue, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            job = q.get(timeout=5)
        except Empty:
            # 若 producer 已退出且 q 空,consumer 也退出
            if not producer_alive():  # 自定义检查
                break
            continue
        try:
            run_profile_pipeline(input_relation=job['artifact'])
            run_enrichment_pipeline()
            run_maintenance_pipeline()
            # 4 哨兵
            sentinels(job['batch_id'])
            execute("""UPDATE rb5_meta.pipeline_artifacts SET status='consumed' WHERE batch_id=%s""", (job['batch_id'],))
        except Exception as e:
            _log({'event': 'consumer_failed', 'batch_id': job['batch_id'], 'error': str(e)})
            execute("""UPDATE rb5_meta.pipeline_artifacts SET status='failed', error=%s WHERE batch_id=%s""", (str(e)[:500], job['batch_id']))
            stop_event.set()
            raise

def main():
    args = _parse_args()  # --start-day / --end-day / --start-batch-id / --skip-reset
    days = _iter_days(args.start_day, args.end_day)
    q = Queue(maxsize=10)  # 允许 producer 提前 10 day,实际不会到
    stop_event = threading.Event()
    
    p = threading.Thread(target=producer, args=(days, args.start_batch_id, q, stop_event), name='producer')
    c = threading.Thread(target=consumer, args=(q, stop_event), name='consumer')
    p.start(); c.start()
    p.join(); c.join()
    
    # 终点报告
```

**失败哲学**(用户拍板):
- consumer 哨兵失败 → consumer 停 + 写 failed state
- **producer 默认继续到当前 running day 结束**(因 producer 已经在跑 SQL,中断成本高;让它写完当 day artifact 再退出)
- 加 CLI flag `--producer-fail-fast`(默认 false)允许 user 选择"producer 立刻停"

#### 5.6 reset SQL 适配

修改 `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql`,在结尾加:

```sql
-- artifact 流水线产物清理
DROP SCHEMA IF EXISTS rb5_stage CASCADE;
CREATE SCHEMA rb5_stage;
TRUNCATE rb5_meta.pipeline_artifacts;
```

#### 5.7 02C 守护扩展

修改 `rebuild5/tests/test_runner_scope_materialization.py`,新增 1 个 test:

```python
def test_artifact_pipelined_runner_freezes_before_consumer():
    """守护 run_citus_artifact_pipelined.py:
    - producer 完成 step1 后必须调 freeze_step2_input_artifact
    - consumer 必须从 rb5_meta.pipeline_artifacts ready 状态拿 input_relation
    - consumer 调用 run_profile_pipeline 必须传 input_relation= 参数(不是空调用)
    """
    # AST 解析新 runner
    ...
```

不动其他 4 个 02C test。

#### 5.8 静态验证(本阶段不实际跑全 7 批)

```bash
python3 -m py_compile rebuild5/scripts/run_citus_artifact_pipelined.py
python3 -m py_compile rebuild5/scripts/run_daily_increment_batch_loop.py
python3 -m py_compile rebuild5/backend/app/profile/pipeline.py
python3 -m py_compile rebuild5/backend/app/etl/pipeline.py
python3 -m py_compile rebuild5/backend/app/maintenance/schema.py
python3 -m py_compile rebuild5/tests/test_runner_scope_materialization.py
# 全 0 退出

# Smoke check:跑 1 day artifact freeze 不实际跑 step2-5
python3 -c "
from rebuild5.scripts.run_daily_increment_batch_loop import freeze_step2_input_artifact
from datetime import date
# 假设当前 etl_cleaned 是 batch 7 的(2025-12-07),做一次 dry freeze
artifact, n = freeze_step2_input_artifact(batch_id=99, day=date(2025,12,7), source_relation='rb5.etl_cleaned')
print(f'smoke artifact={artifact} rows={n}')
"
# 期待 artifact='rb5_stage.step2_input_b99_20251207' rows>0

# 然后 cleanup smoke artifact:
DROP TABLE IF EXISTS rb5_stage.step2_input_b99_20251207;
DELETE FROM rb5_meta.pipeline_artifacts WHERE batch_id=99;
```

#### 5.9 完工流程(按 _prompt_template.md § 11)

`git add` 显式列改动 + 新文件 + 报告 + README:
```
rebuild5/backend/app/profile/pipeline.py
rebuild5/backend/app/etl/pipeline.py
rebuild5/backend/app/maintenance/schema.py
rebuild5/scripts/run_daily_increment_batch_loop.py
rebuild5/scripts/run_citus_artifact_pipelined.py  # 新
rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
rebuild5/tests/test_runner_scope_materialization.py
rebuild5/docs/loop_optim/02_artifact_pipelined_prompt.md
rebuild5/docs/loop_optim/02_artifact_pipelined_report.md
rebuild5/docs/loop_optim/README.md
```

一个 commit:
```
feat(rebuild5): loop_optim 02 artifact-driven pipelined runner + Step1 40-core parallelism

- Add rb5_stage schema + rb5_meta.pipeline_artifacts reference state table
- New freeze_step2_input_artifact(batch_id, day) creates immutable
  rb5_stage.step2_input_b<N>_<YYYYMMDD> per-batch artifact (UNLOGGED
  distributed, colocated with etl_cleaned, indexed per loop_optim/01 §4)
- run_profile_pipeline gains explicit input_relation parameter; legacy
  implicit get_step2_input_relation fallback preserved for backward compat
- Step1 ETL queries now run with PARALLEL_40_SETUP via citus_compat
  execute_distributed_insert (max_parallel_workers_per_gather=40 etc)
- New run_citus_artifact_pipelined.py producer/consumer with state-table
  persistence; producer fail-soft, consumer fail-fast
- Reset SQL drops rb5_stage and truncates rb5_meta.pipeline_artifacts
- Extend test_runner_scope_materialization with artifact pipeline guard
- Smoke verification: freeze on batch 7 etl_cleaned snapshot succeeded
- References loop_optim/01_index_additions_report.md §4

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

`git push origin main`(撞瞬时 SSL 等 60s 重试 1 次)

写 note `topic='loop_optim_02_done'`,用 § 9 完工话术汇报。

### 不做(显式禁止)

- ❌ 不跑全 7 批(留给 03 阶段)— 只跑 1 batch artifact freeze 做 smoke
- ❌ 不动 etl_cleaned 表(继续作 staging,artifact 只是 SELECT 出来的副本)
- ❌ 不删 03 已实现的 `run_citus_pipelined_batches.py`(保留作 fallback)
- ❌ 不删串行 `run_citus_serial_batches.py`(保留作底线 fallback)
- ❌ 不动 fix6_optim 已稳定的 citus_compat / 02C 14 个原 test
- ❌ 不引入新依赖(threading / queue 都是标准库)
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc

## § 6 验证标准

任务 done 的硬标准:

1. **rb5_stage schema + rb5_meta.pipeline_artifacts** 在 Citus 实际存在(via `\dn` 和 `SELECT * FROM rb5_meta.pipeline_artifacts LIMIT 0` 检查)
2. **`freeze_step2_input_artifact` 可调用** + smoke run on batch 7 etl_cleaned 成功(artifact 表存在,row_count > 0,state='ready')
3. **`run_profile_pipeline(input_relation=...)` 显式参数生效**:smoke 不跑全程,但 grep 确认签名改了 + caller 都传参或保留 None(向后兼容)
4. **Step1 PARALLEL_40_SETUP 注入**:grep `max_parallel_workers_per_gather = 40` 在 etl/pipeline.py 命中 + Step1 SQL 走 execute_distributed_insert
5. **新 runner 文件存在** + `python3 rebuild5/scripts/run_citus_artifact_pipelined.py --help` 显示 CLI
6. **02C 守护扩展通过**:test_runner_scope_materialization.py 新加 1 个 test,手工 invoke 通过
7. **py_compile 全过**
8. **commit + push**:`git rev-parse HEAD == git rev-parse origin/main`(允许标 push pending)
9. **note 写入**:`SELECT body FROM rb5_bench.notes WHERE topic='loop_optim_02_done'`

## § 7 产出物 `02_artifact_pipelined_report.md`

```markdown
# loop_optim / 02 artifact pipelined + Step1 40 核报告

## 0. TL;DR + 对上游修订
- rb5_stage schema + rb5_meta.pipeline_artifacts 已建
- freeze_step2_input_artifact 已实施,smoke on batch 7 成功(rows=<n>)
- run_profile_pipeline 加 input_relation 显式参数,向后兼容
- Step1 PARALLEL_40_SETUP 注入到 N 处 INSERT...SELECT
- 新 runner run_citus_artifact_pipelined.py 已实施
- 02C 守护扩展 1 个 test 通过
- 对 fix6_optim 02A/02B/02C 修订:<无 / 列表>
- commit SHA:<sha>;push 状态:<status>
- 03 阶段可以接入(完整 7 批 reset + run + verify)

## 1. 设计实施细节
### 1.1 etl_cleaned 实际分布键(查询结果)
SELECT logicalrelid, ... FROM pg_dist_partition WHERE logicalrelid='rb5.etl_cleaned'::regclass
=> 分布键 = '<col>'

artifact 表 colocate 实施方式:create_distributed_table(..., colocate_with='rb5.etl_cleaned')

### 1.2 freeze_step2_input_artifact 关键 diff
代码节选 + state 表写入路径

### 1.3 run_profile_pipeline 显式参数
diff 节选

### 1.4 Step1 40 核 SETUP
PARALLEL_40_SETUP 内容 + 注入到 N 处 caller

### 1.5 producer/consumer 流程
ASCII 图或 mermaid

### 1.6 reset SQL 改动
diff 节选

## 2. Smoke 验证
- batch 7 freeze:artifact='rb5_stage.step2_input_b99_20251207', rows=<n>, build_time=<s>
- state 表写入路径:running -> ready -> (cleanup)
- artifact cleanup 后 pipeline_artifacts 行数

## 3. 02C 守护扩展
- 新 test 名 + 手工 invoke 输出
- 现有 14 个 test 不被打破:py_compile 输出

## 4. 已知限制 / 未做
- 全 7 批 run + 终点验收:留给 03 阶段
- producer/consumer 死锁 / 资源压力测:留给 03 实战
- artifact 物理空间监控(每批 ~5M rows × 7 = ~35M rows):03 跑完后看 pg_database_size

## 5. 给 03 重跑阶段的输入
- 启动命令完整 host shell 块
- 4 哨兵 SQL(等价 fix5/05_rerun_prompt §5)
- 终点验收 SQL(TCL b7 ±5% vs fix6 03 的 340,767 / ±20% vs PG17 的 341,460)
- 预期时长:~90 分钟(目标加速比 1.67×)
```

## § 8 notes 协议

- 完工:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('loop_optim_02_done', 'info',
    'artifact pipelined implemented, rb5_stage schema + pipeline_artifacts ref table, freeze_step2_input_artifact smoke=pass (batch7 rows=<n>), run_profile_pipeline gains input_relation, Step1 40-core SETUP injected to <n> callers, new runner=run_citus_artifact_pipelined.py, 02C guard extended, head=<sha>');
  ```
- 失败:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('loop_optim_02_failed', 'blocker', 'failed at <step>: <reason>');
  ```

## § 9 完工话术

成功:
> "loop_optim 02 完成。02_artifact_pipelined_report.md 已写入。rb5_stage schema + pipeline_artifacts 已建,freeze smoke 通过(batch 7 rows=<n>),run_profile_pipeline 加显式 input_relation,Step1 40 核 SETUP 注入,新 runner run_citus_artifact_pipelined.py,02C 守护扩展。对 fix6_optim 修订:<无 / 列表>。commit=<SHA>,GitHub:<url>(push <成功/pending>)。03 阶段可以接入。notes `topic='loop_optim_02_done'` 已插入。"

失败:
> "loop_optim 02 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='loop_optim_02_failed'`。等上游处置。"

## § 10 失败兜底

- **etl_cleaned 不是 distributed table**(可能是 reference 或 local):查 `pg_dist_partition` 后选对应 create 路径(distributed / reference / local),报告 §1.1 记录实际形态
- **artifact 表名超过 PG 63 字符限制**:用 hash 后缀(如 `rb5_stage.s2i_b<N>_<YYYYMMDD>`,缩写)
- **colocate_with 失败**(因为 distribution key 类型不一致):降级为非 colocated distributed table(slower join),在报告 §4 标注
- **producer/consumer 多线程撞 connection 共享**:psycopg connection 不线程安全,每 thread 独立 `get_conn()`,如果撞"connection closed",这是根因
- **smoke run 失败**(freeze 报错):立刻停 + blocker note + 完整 traceback,不要继续写 runner
- **02C 守护新 test 撞 AST 解析问题**:fall back 到 string grep 守护(降级但有用)
- **GitHub HTTPS SSL 抖动**:等 60s 重试 1 次;再失败标 "push pending"
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
