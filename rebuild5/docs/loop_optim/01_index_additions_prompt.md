# OptiNet rebuild5 / loop_optim / 01 索引补全(agent 新实例对话)

## § 1 元目标

普查 7 张大表(`rb5.raw_gps` / `etl_parsed` / `etl_cleaned` / `etl_filled` / `step2_batch_input` / `cell_sliding_window` / `trusted_cell_library`)的 reader SQL,**WHERE / JOIN / GROUP BY 列没索引就建**。直接落到对应 schema/pipeline Python 文件里(用 `CREATE INDEX IF NOT EXISTS`,幂等)。

**用户决议**:**索引加多了无害**,**不删除现有索引**(占用不在乎)。这一阶段不做"哪些索引没用过"的精细审计,只做正向补全。

## § 2 上下文启动顺序

按序读完直接开工(按 `_prompt_template.md` § 11 / § 12 自主推进):

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/loop_optim/README.md` —— 全局阶段表
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— 模板复用,**§ 11 自动 commit/push** 必读
4. `rebuild5/docs/fix6_optim/02A_audit_report.md` §2.1 helper 矩阵 —— 知道哪些表是 distributed / reference
5. `rebuild5/backend/app/etl/source_prep.py` / `etl/pipeline.py` / `etl/fill.py` —— 已有 CREATE INDEX 的样本(参考风格)
6. `rebuild5/backend/app/maintenance/schema.py` —— 已有 CREATE TABLE + 部分索引
7. `rebuild5/backend/app/enrichment/schema.py` —— 同上
8. 本 prompt

读完直接开工,**不需要在对话报告设计选型**。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`
- **当前 git 头**:`914eb1f`(fix6_optim 03 收档,本地)
- **远端 origin/main**:`914eb1f`(fix6_optim 03 已 push 成功)
- **Git remote**:`https://github.com/laoyang75/OptiNet.git`(private + 局域网,不脱敏)

### 数据库连接

- **Citus**(主目标,可读可写):`postgres://postgres:123456@192.168.200.217:5488/yangca`
  - MCP:`mcp__PG_Citus__execute_sql`
  - psql:`PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca`
- **PG17**(只读基线,本阶段不需要)
- **runner env**(本阶段不跑 runner,但留作参考):`REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'`

### Citus 索引规则(关键背景)

- distributed table 上 CREATE INDEX → Citus 自动在每个 shard 上独立建
- reference table 上 CREATE INDEX → 在每个 worker 副本上建
- distribution column 已是隐式 hash 索引,**不需要再 CREATE INDEX (column)** 但 colocated join 的 join key 通常需要复合索引
- 大表(>1M rows)上 CREATE INDEX 需要时间,但是 IF NOT EXISTS + 幂等,跑多次不出错

### 沙箱状态

已解除长跑限制。CREATE INDEX 在 ~30M rows 表上可能需要几分钟,可以前台跑或 nohup 都行。

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `rebuild5/docs/fix6_optim/02A_audit_report.md` §2.1 | 阅读 | distributed / reference / colocated 分类参考 |
| 本阶段产出 `01_index_additions_report.md` | 新建 | § 7 结构 |
| `rebuild5/backend/app/etl/source_prep.py` | 修改 | 加 raw_gps 索引(如缺) |
| `rebuild5/backend/app/etl/pipeline.py` | 修改 | 加 etl_parsed / etl_cleaned / etl_filled 索引(如缺) |
| `rebuild5/backend/app/etl/fill.py` | 修改 | 已有 fill 期间临时索引,看是否要持久化 |
| `rebuild5/backend/app/profile/pipeline.py` | 修改 | step2_batch_input 索引(已有 idx_step2_batch_input_*,确认) |
| `rebuild5/backend/app/maintenance/schema.py` | 修改 | cell_sliding_window / cell_metrics_base / 等 maintenance 大表 |
| `rebuild5/backend/app/maintenance/window.py` | 修改 | sliding_window insert/trim 路径上的索引 |
| `rebuild5/backend/app/enrichment/schema.py` | 修改 | enrichment 表(snapshot_seed_records / candidate_seed_history) |

**本阶段不修改文档(*.md)**,只改 Python 文件 + 写本阶段产出报告。

## § 5 任务清单

### 必做(按顺序)

#### 5.1 列出现有索引(via Citus MCP / psql)

对每张大表跑:

```sql
-- 通过 PG_Citus MCP 执行
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'rb5'
  AND tablename IN (
    'raw_gps', 'etl_parsed', 'etl_cleaned', 'etl_filled',
    'step2_batch_input', 'cell_sliding_window', 'trusted_cell_library',
    'snapshot_seed_records', 'candidate_seed_history',
    'enriched_records', 'cell_metrics_base', 'cell_radius_stats',
    'cell_drift_stats', 'cell_daily_centroid', 'gps_anomaly_log',
    'cell_core_gps_day_dedup', 'trusted_bs_library', 'trusted_lac_library'
  )
ORDER BY tablename, indexname;
```

把输出整理成"现有索引矩阵"贴进报告 §1.1。

#### 5.2 grep 各 step 的 SQL,识别这些表的 WHERE / JOIN / GROUP BY 列

对每张大表,grep `from rb5.<table>` / `JOIN rb5.<table>` 在 backend 全仓:

```bash
# 例:cell_sliding_window
grep -rn "rb5\.cell_sliding_window\|rb5\.cell_sliding_window\b" rebuild5/backend rebuild5/scripts \
  --include="*.py" --include="*.sql" \
  | grep -v "tests/" | head -50
```

对每个命中的 SQL 上下文,识别:
- WHERE 子句的列(equality / range)
- JOIN ON 子句的列(等于 join key)
- GROUP BY 子句的列
- ORDER BY 的列(如果是 ORDER BY ... LIMIT,可能需要索引覆盖)

整理成"SQL access pattern × 列" 矩阵,贴进报告 §1.2。

#### 5.3 列出"该有但没有"的索引

把 §5.1 现有索引 与 §5.2 access pattern 对比,生成"待加索引清单":

| 表 | 列(组合) | 当前是否有索引 | 推荐索引名 | 优先级 |
|---|---|---|---|---|
| `cell_sliding_window` | `(operator_code, lac, cell_id, tech_norm, event_time_std)` | 否 | `idx_cell_sliding_window_dim_time` | P0(maintenance.window 反复用) |
| ... | ... | ... | ... | ... |

优先级判断标准(简单粗暴,不要过度分析):
- **P0**:critical join / 高频 WHERE + 表行数 > 10M
- **P1**:中频 WHERE + 表行数 1M-10M
- **P2**:罕见 WHERE 或 GROUP BY only

**P0 + P1 全部加,P2 也加**(用户说"加多了无害")。

#### 5.4 在对应 Python 文件里加 CREATE INDEX

参考 `etl/source_prep.py:153` / `etl/pipeline.py:25` 的现有风格:

```python
# 在 schema 创建函数 / pipeline 入口之后:
execute("""
    CREATE INDEX IF NOT EXISTS idx_<table>_<col_short>
    ON rb5.<table> (<columns>)
""")
```

注意:
- 用 `IF NOT EXISTS` 幂等
- 索引命名:`idx_<table_short>_<col_short>`,不要太长
- 复合索引列顺序按"selectivity 高的在前"(等值 > 范围)
- distributed table 不要把 distribution column 单独建索引(已有隐式 hash)

把这些 CREATE INDEX 加在哪个文件,**遵循现有约定**:
- raw_gps → `etl/source_prep.py`
- etl_parsed / etl_cleaned / etl_filled → `etl/pipeline.py`(在 step1 入口)
- step2_batch_input → `scripts/run_daily_increment_batch_loop.py::materialize_step2_scope`(已有)+ 同 logic 复用
- cell_sliding_window 及 maintenance 表 → `maintenance/schema.py` 或 `maintenance/window.py`
- enrichment 表 → `enrichment/schema.py`
- TCL 主结果表 → `maintenance/schema.py`

#### 5.5 在数据库里实际执行新索引(本次会话)

**这是关键**:不只改 Python 文件,**当场把新索引建出来**(下次跑 step1 才会触发的话验证延迟)。

通过 MCP 跑 CREATE INDEX(可能耗时几分钟,因为表大):

```sql
-- 例
CREATE INDEX IF NOT EXISTS idx_cell_sliding_window_dim_time
ON rb5.cell_sliding_window (operator_code, lac, cell_id, tech_norm, event_time_std);
```

每条建完后:
```sql
-- 确认建出来
SELECT indexname FROM pg_indexes
WHERE schemaname='rb5' AND indexname='idx_cell_sliding_window_dim_time';

-- 跑 ANALYZE 让 planner 看到
ANALYZE rb5.cell_sliding_window;
```

如果某张表行数太大,CREATE INDEX 可能耗时 ≥ 5 分钟,**不要跑超过 10 分钟的索引**(可能堵塞其他 query)。如果撞超时,先 kill query,在报告 §3 标 "需要 maintenance window 期间手动跑"(留给用户)。

#### 5.6 静态验证

```bash
python3 -m py_compile rebuild5/backend/app/etl/*.py rebuild5/backend/app/maintenance/*.py rebuild5/backend/app/enrichment/*.py
# 全 0 退出
```

#### 5.7 完工流程(按 _prompt_template.md § 11)

- `git add` 显式列改动的 .py 文件 + 本阶段 prompt + report + README
- 一个 commit:
  ```
  perf(rebuild5): loop_optim 01 add missing indexes on big tables

  - Survey existing indexes on 18 rb5.* tables via pg_indexes
  - Identify access patterns from backend SQL (WHERE/JOIN/GROUP BY)
  - Add <N> CREATE INDEX IF NOT EXISTS to schema/pipeline modules
    covering: <table summary>
  - Apply indexes live to current Citus database via MCP
  - References loop_optim/01_index_additions_report.md

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- `git push origin main`(撞瞬时 SSL 等 60s 重试 1 次)
- 写 note `topic='loop_optim_01_done'`
- 用 § 9 完工话术汇报

### 不做(显式禁止)

- ❌ 不删除现有索引(用户决议:加多了无害,不做精细审计)
- ❌ 不分析"哪些索引从未被用过"(留给未来 vacuum 时手动看)
- ❌ 不修改业务 SQL(只在 Python 里加 CREATE INDEX)
- ❌ 不动 fix6_optim 已稳定的代码(citus_compat.py / 02C 守护 / runner)
- ❌ 不连 PG17 旧库
- ❌ 不跑 pipeline runner(只 in-place CREATE INDEX,不重跑数据)
- ❌ 不引入新依赖
- ❌ 不开 PR / 不开分支
- ❌ 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc
- ❌ 单条 CREATE INDEX 不要跑超过 10 分钟(撞超时停下,在报告标"需要维护窗口")

## § 6 验证标准

任务 done 的硬标准:

1. **现有索引矩阵完整**:18 张 rb5.* 大表全列出 indexname / indexdef
2. **access pattern 矩阵**:每张大表至少 1 个 SQL 访问模式被识别
3. **新索引清单 ≥ 5 条**:不允许"现有都够了"这种结论(实际几乎肯定有缺,如果真没缺要附完整查证 trail)
4. **新索引在数据库里实际可见**:`SELECT indexname FROM pg_indexes WHERE schemaname='rb5' AND indexname IN (<新建索引名列表>)` 全部返回
5. **schema/pipeline 文件里 CREATE INDEX 与数据库一致**:每条数据库新索引都对应一处 Python 代码 CREATE INDEX IF NOT EXISTS
6. **py_compile 全过**
7. **commit + push**:`git rev-parse HEAD == git rev-parse origin/main`(允许标 "push pending due to network")
8. **note 写入**:`SELECT body FROM rb5_bench.notes WHERE topic='loop_optim_01_done'` 包含新索引数量

## § 7 产出物 `01_index_additions_report.md`

```markdown
# loop_optim / 01 索引补全报告

## 0. TL;DR
- 18 张 rb5.* 大表现有索引矩阵已盘点
- 新增索引:N 条(P0=<n>, P1=<n>, P2=<n>)
- 数据库实际建索引耗时:总 <m> 分钟,最长一条 <s> 秒
- schema/pipeline 文件改动:M 处 CREATE INDEX IF NOT EXISTS
- 对 fix6_optim 02A/02B 修订:<无 / 列表>
- commit SHA:<sha>;push 状态:<status>

## 1. 现有索引矩阵
### 1.1 18 张大表的 pg_indexes 输出
| schema.table | indexname | indexdef | 推测用途 |
| --- | --- | --- | --- |
... 完整列表

### 1.2 SQL access pattern × 列
| 表 | 文件:行号 | SQL access(WHERE/JOIN/GROUP BY) | 列 |
| --- | --- | --- | --- |
... 完整列表

## 2. 新增索引清单
| 表 | 列(组合) | 索引名 | 优先级 | 加在哪个文件 | 数据库实际建立耗时 |
| --- | --- | --- | --- | --- | ---: |
... 至少 5 条

## 3. 已知限制 / 未做
- 单条 CREATE INDEX 超时跳过的(若有)
- "存在但从未被用过"的索引(本阶段不删,留给未来)
- partial index / covering index 没用的(本阶段不引入新概念)
- pg_stat_user_indexes 的使用率数据(只在报告里贴一份当前快照,不做决策)

## 4. 给 02 artifact pipelined 的输入
- 02 阶段的 rb5_stage.step2_input_b<N>_<YYYYMMDD> 系列也要建索引,本阶段把建索引模板写进 §4(让 02 agent 直接抄)
- 如:`(cell_id)`,`(operator_filled, lac_filled, cell_id)`,`(record_id)`(参考 materialize_step2_scope 现有 3 索引)
```

## § 8 notes 协议

- 完工:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('loop_optim_01_done', 'info',
    'index additions complete, added=<n> (P0=<n>/P1=<n>/P2=<n>), all visible in pg_indexes, head=<sha>, max_create_time=<s>s');
  ```
- 失败:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('loop_optim_01_failed', 'blocker', 'failed at <step>: <reason>');
  ```

## § 9 完工话术

成功:
> "loop_optim 01 完成。01_index_additions_report.md 已写入。新增 <N> 条 CREATE INDEX(P0=<n>/P1=<n>/P2=<n>),全部 pg_indexes 可见,schema/pipeline 文件同步更新。对 fix6_optim 02A 修订:<无 / 列表>。commit=<SHA>,GitHub:<url>(push <成功/pending>)。notes `topic='loop_optim_01_done'` 已插入。"

失败:
> "loop_optim 01 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='loop_optim_01_failed'`。等上游处置。"

## § 10 失败兜底

- **CREATE INDEX 超时**(>10 分钟):取消 query(`SELECT pg_cancel_backend(<pid>)`),在报告 §3 标"需要维护窗口手动跑",不算 blocker,01 仍可完工
- **撞死锁 / lock wait**:看 `pg_locks`,如果是 ANALYZE / VACUUM 撞,等 5 分钟再试;如果是业务 query,推迟到无业务时段
- **现有索引矩阵巨大**(18 表 × ~5 索引 = ~90 行):报告 §1.1 完整列出,不要截断
- **某张表实际不存在**(还没创建过):标记"未创建" + 跳过该表索引,不算 blocker
- **GitHub HTTPS SSL 抖动**:等 60s 重试 1 次;再失败标 "push pending",不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
