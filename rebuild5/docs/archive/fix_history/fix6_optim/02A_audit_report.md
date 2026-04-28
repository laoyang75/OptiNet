# fix6_optim / 02A 审计报告

## 0. TL;DR

- P0 隐患: 0 条未修复的 3/3 命中;fix5 D 的 `publish_bs_library` 属于已修复 P0 参考样本。
- P1 隐患: 7 条,主要是 2/3 命中:参数化 `execute(..., params)` 或 `INSERT...WITH` 落在 `rb5.*` 主结果表,但未同时满足全部三条件。
- P2 隐患: 6 条,主要是 helper 散落、session SET 散落、`ctid` 只读投影、旧脚本自有 wrapper。
- helper 散落: 5 套入口/脚本族: `core/database.py`, `core/parallel.py`, `publish_bs_lac.py` 局部 ClientCursor helper, `bench_parallel.py`, `fix4_claude_pipeline.py`/研究脚本直连 cursor。
- 测试覆盖: 21 个 `test_*.py`,72 个 `def test_`;当前环境 `python3 -m pytest --collect-only` 因缺 pytest 未能 collect;0 个 Citus 集成测试。
- fix5 4 根因现有回归覆盖: 0/4 完整覆盖。`get_step2_input_relation` 有偏好 daily scope 的单测,但没有 runner 级 scope materialization 回归。
- 给 02B 必做项: 6 条。
- 给 02C 必做项: 7 条。

审计范围量级: `rebuild5/backend/app` + `rebuild5/scripts` + `rebuild5/tests`,共 89 个 `.py/.sql`,23,863 行。backend app 有 9 个有效模块目录。

## 1. Citus 兼容隐患清单(按风险分级)

判定规则按用户 Prime: P0 需要三个条件同时成立:

1. 参数化: `execute(..., params)` 或 `cur.execute(..., params)`
2. `INSERT...SELECT` 含 CTE: `WITH ... AS ...`
3. 操作 distributed / colocated 表: 以 `rb5.*` 主结果表为主

### 1.1 P0(fix5 已验证模式)

| 文件:行号 | 模式 | 三条件命中数 | 上下文 | 风险说明 |
| --- | --- | ---: | --- | --- |
| `rebuild5/backend/app/maintenance/publish_bs_lac.py:940` | `ClientCursor` 已修复路径 | 3/3,已修 | `INSERT INTO rb5.trusted_bs_library ... WITH cell_agg AS (...)`,参数为 `batch_id` | 这是 fix5 D 已验证会炸的形态,但当前通过 `_execute_with_session_settings` 使用 `ClientCursor + mogrify`,不计未修复 P0。 |

未发现新的未修复 3/3 P0。

### 1.2 P1(同结构未触发)

| 文件:行号 | 模式 | 三条件命中数 | 上下文 | 风险说明 |
| --- | --- | ---: | --- | --- |
| `rebuild5/backend/app/core/database.py:219` | 通用 `execute(sql, params)` 默认 cursor | 2/3 | `with conn.cursor() as cur: cur.execute(sql, params)` | 所有业务模块共享默认 psycopg server-side 参数路径;只要 caller 传入 3/3 SQL,就会复现 fix5 D 风险。 |
| `rebuild5/backend/app/core/database.py:207` | CTAS 拆分 helper 转 `INSERT INTO ... SELECT` | 2/3 | `cur.execute(f"INSERT INTO {relation} {select_sql}", params)` | C 阶段 helper 统一了分布式 CTAS,但仍把 params 交给默认 cursor;若 caller 的 `select_sql` 带复杂 CTE/params,风险升级为 P0。 |
| `rebuild5/backend/app/maintenance/publish_cell.py:56` | `INSERT INTO rb5.trusted_cell_library ... WITH merged AS` + params | 2/3 | 参数在 `cw.batch_id`, `a.batch_id`,阈值和 insert values 中使用 | 目标是主结果表,参数多;当前只有一个主要 CTE,未满足 "多 CTE",所以降级 P1。 |
| `rebuild5/backend/app/maintenance/publish_bs_lac.py:1240` | `INSERT INTO rb5.trusted_lac_library ... WITH bs_agg AS` + params | 2/3 | LAC publish 仍走默认 `execute(...)` | `trusted_lac_library` 在 `_REFERENCE_TABLES`,不是 hash distributed 主表;但语法与已修 BS publish 相似,建议统一入口。 |
| `rebuild5/backend/app/profile/pipeline.py:1546` | `INSERT INTO rb5.candidate_seed_history ... SELECT` + params | 2/3 | `execute(..., (batch_id, run_id, DATASET_KEY, run_id))` | 分布式结果表 + 参数化 INSERT SELECT,但无 `WITH`;03 pipelined 放大后应纳入兼容层。 |
| `rebuild5/backend/app/enrichment/pipeline.py:413` | `INSERT INTO rb5.snapshot_seed_records ... SELECT` + params | 2/3 | `execute(..., (run_id, DATASET_KEY))` | 分布式结果表 + 参数化 INSERT SELECT,但无 `WITH`;建议和 candidate seed 一起统一。 |
| `rebuild5/backend/app/maintenance/label_engine.py:103` | `INSERT INTO rb5._label_input_points WITH source_meta AS` | 2/3 | `label_input_sql` 内联 batch_id,无 params | 有 INSERT+WITH 且目标为 `rb5.*` 临时表,但参数已内联;不是 fix5 D 同款,保留 P1 观察。 |

### 1.3 P2(风格 / 重复)

| 文件:行号 | 模式 | 三条件命中数 | 上下文 | 风险说明 |
| --- | --- | ---: | --- | --- |
| `rebuild5/backend/app/maintenance/window.py:148` | CTE + keyed DELETE | 1/3 | `delete_keys AS (...) DELETE FROM rb5.cell_sliding_window ...` | fix5 C 已从 `ctid` 改成主键删除,当前是验证过的 Citus-safe 方向;缺少回归测试。 |
| `rebuild5/backend/app/etl/fill.py:138` | `c.ctid::text` 投影 | 1/3 | 用于生成 source uid 字段 | 不是 distributed DELETE 的 `ctid WHERE`,不属于 fix5 C 的失败模式。 |
| `rebuild5/backend/app/maintenance/publish_bs_lac.py:270,941` | `SET enable_nestloop = off` | 1/3 | 局部 session setup | 当前 publish_bs 使用 helper 会 RESET;cell centroid 路径仍是普通 `execute` 周边逻辑,建议 02B 统一 session setup。 |
| `rebuild5/scripts/fix4_claude_pipeline.py:461` | `SET enable_nestloop = off` | 1/3 | 旧 fix4 研究脚本自有 execute wrapper | 旧脚本不在主 runner 路径,但自有 wrapper 与 session SET 增加维护成本。 |
| `rebuild5/scripts/bench_parallel.py:44` | 脚本内自有 `execute(sql, params=None)` | 1/3 | `cur.execute(sql, params)` | benchmark 脚本绕过 `core/database.py`,与生产 helper 行为不一致。 |
| `rebuild5/scripts/research_multicentroid_batch7.py:181` | 研究脚本直连 cursor + params | 1/3 | `cur.execute(sql, tuple(params))` | 研究脚本可保留,但不应作为 03 runner 依赖。 |

### 1.4 A-F grep 量化结果

| 类别 | 命令摘要 | 命中数 | 说明 |
| --- | --- | ---: | --- |
| A1 | `cur.execute([^)]*params` | 11 | 直接 cursor 参数化;包含 core helper、bench/fix4/研究脚本。 |
| A2 | `.execute([^)]*%s` | 3 | 主要是 `create_reference_table` / `create_distributed_table` 元数据调用。 |
| A3 | `\bexecute\(` wrapper 全扫 | 788 | 需人工分 direct cursor vs wrapper;多数为普通 DDL/CTAS/无 params。 |
| A4 | `execute(..., (` tuple params | 6 | 业务层显式 tuple params;是 P1 主要来源。 |
| B | `SET citus.` / `SET enable_` / `SET auto_explain` | 0 / 4 / 0 | 无 `SET citus.` 和 `SET auto_explain`;`enable_nestloop` 4 处。 |
| C | `ctid` | 1 | 仅 `etl/fill.py` 只读投影。 |
| D | `CREATE.*FUNCTION.*LANGUAGE.*SQL` | 0 | 符合预期;fix5 D 错误 hint 不是用户 SQL function。 |
| E | `INSERT INTO` 文件再筛 `WITH` | 12 个文件 | 未截断;全量列入审计范围。 |
| F | `EXPLAIN ANALYZE.*INSERT` | 0 | 符合 fix5 后运行约束。 |

## 2. helper 散落 / 重复

### 2.1 模块 × helper 矩阵

| 模块 | 用 `core/database.py` | 自有 helper | Citus-aware? |
| --- | --- | --- | --- |
| `core/` | `execute`, `fetchone`, `fetchall`, CTAS split helper | `_execute_ctas_as_distributed`, layout helpers | 部分。能建 distributed/reference table,但参数仍走默认 cursor。 |
| `etl/` | `execute`, `fetchone` | 无 | 间接部分 Citus-aware;大量 CTAS 依赖 core helper。 |
| `profile/` | `execute`, `fetchone` | `relation_exists`, Step2 scope fallback | 间接部分 Citus-aware;`candidate_seed_history` INSERT SELECT 带 params。 |
| `evaluation/` | `execute`, `fetchone` | 局部 table build helpers | 间接部分 Citus-aware;多 CTAS/INSERT 无 params。 |
| `enrichment/` | `execute`, `fetchone`, `parallel_execute` | `parallel_execute` 用于 shard insert | 部分;enriched_records 已内联 params,`snapshot_seed_records` 仍默认 params。 |
| `maintenance/` | `execute`, `fetchone`, `parallel_execute` | `publish_bs_lac._execute_with_session_settings` | 混合。BS publish 已 Citus-safe;cell/LAC/label/window 仍散落。 |
| `routers/` | 无直接 SQL helper | FastAPI router wrapper | 不适用。 |
| `service_query/` / `services/` | `fetchall` / `fetchone` | payload shaping | 查询层,低风险。 |
| `scripts/` | 部分 import `core.database.execute` | `bench_parallel.execute`, `fix4_claude_pipeline.execute`, direct psycopg cursor | 不统一;生产 runner 与研究/benchmark 脚本行为不同。 |

### 2.2 统一接口草案(给 02B)

```python
# rebuild5/backend/app/core/citus_compat.py(02B 落地)

def execute_distributed_insert(
    sql: str,
    *,
    params: tuple[Any, ...] | None = None,
    session_setup_sqls: list[str] | None = None,
    reset_session: bool = True,
) -> None:
    """统一 Citus-safe INSERT...SELECT 入口。

    预期语义:
    - 使用 psycopg ClientCursor
    - params 存在时用 cur.mogrify(sql, params) 客户端 inline
    - 执行 session_setup_sqls,完成后按 SET key RESET
    - 仅用于 INSERT...SELECT / DML,不替代普通 SELECT fetch helper
    """
    ...
```

可替换 caller:

- `maintenance/publish_bs_lac.py:940` 已修 helper,迁入统一入口。
- `maintenance/publish_cell.py:56` trusted_cell_library publish。
- `maintenance/publish_bs_lac.py:1240` trusted_lac_library publish。
- `profile/pipeline.py:1546` candidate_seed_history persist。
- `enrichment/pipeline.py:413` snapshot_seed_records insert。
- `core/database.py:207/209` CTAS split helper中 params DML 分支,或至少增加守护/显式分流。

不能统一或不建议 02B 统一:

- `fetchall` / `fetchone` 普通 SELECT 查询。
- `create_distributed_table(%s, %s)` / `create_reference_table(%s)` 元数据函数调用。
- benchmark、fix4、research 脚本,除非 02B 明确把它们纳入 runner 支撑面。

## 3. 测试覆盖现状

### 3.1 现有 tests

| 文件 | def test_ 数 | 测什么层 | collect-only 通过? |
| --- | ---: | --- | --- |
| `test_enrichment_queries.py` | 1 | enrichment query payload | 未验证;pytest 缺失 |
| `test_etl_*.py` + `test_source_prep.py` | 10 | ETL definitions/queries/router/source prep | 未验证;pytest 缺失 |
| `test_profile_logic.py` + `test_profile_router.py` | 12 | profile 逻辑和 router | 未验证;pytest 缺失 |
| `test_label_engine.py` | 1 | label_engine 调用顺序/输入 | 未验证;pytest 缺失 |
| `test_maintenance_*.py` + `test_publish_*.py` | 10 | maintenance query/router/publish SQL shape | 未验证;pytest 缺失 |
| `test_pipeline_version_guards.py` | 23 | 跨阶段 SQL shape/version guard | 未验证;pytest 缺失 |
| `test_service_*.py`, `test_system_service.py`, `test_health_api.py`, `test_settings.py`, `test_envelope.py`, `test_launcher_port_guard.py` | 16 | service/system/API/settings/tooling | 未验证;pytest 缺失 |

collect-only 命令结果:

```text
cd rebuild5 && python -m pytest tests/ --collect-only -q
zsh:1: command not found: python

cd rebuild5 && python3 -m pytest tests/ --collect-only -q
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named pytest
```

因此本环境 collect 通过数记为 0,失败原因是测试工具未安装,不是测试 import 失败。

### 3.2 fix5 4 根因 vs 现有 tests

| 根因 | 现有 test? | 推荐测试形态 |
| --- | --- | --- |
| scope materialization | 部分。`test_get_step2_input_relation_prefers_daily_scope` 只测函数偏好,不测 runner 每批物化 | integration/static hybrid: 验 serial runner 在 Step1 后调用 `materialize_step2_scope` 且 drop `_step2_cell_input`;小样本跑后 `step2_batch_input` 单日。 |
| sliding_window trim | 无完整回归 | unit/static: 输入含旧时间戳,断言 trim SQL 用 key delete 且保留 retention 条件;integration 验窗口日期跨度。 |
| `ctid` distributed DELETE 不支持 | 无守护 | static test: grep `DELETE ... ctid` 禁止;允许 `ctid::text` 只读投影。 |
| parameterized distributed plan | 无完整回归 | unit/static: 对 `execute_distributed_insert` 断言使用 `ClientCursor.mogrify`;对 publish_bs/cell/lac 高危 INSERT 禁止直接 `execute(..., params)`。 |

未发现 Citus integration test。现有测试多为 monkeypatch SQL shape/version guard,不连接 Citus。

## 4. 跨模块依赖 / 抽象空隙

- `etl/` 依赖 `core.database`, `core.settings`,自身 `source_prep`;没有反向依赖。
- `profile/` 依赖 `core.database`, `etl.source_prep`,自身 `logic`;是 Step2/3 的中心层。
- `evaluation/` 依赖 `core.database`, `etl.source_prep`, `profile.pipeline`, `profile.logic`;合理,但对 profile 内部 helper 的耦合较深。
- `enrichment/` 依赖 `core.database`, `core.parallel`, `etl.source_prep`, `profile.logic`, `profile.pipeline.relation_exists`;Step4 直接 import profile helper,属于跨层复用但未形成循环。
- `maintenance/` 依赖 `core.database`, `core.parallel`, `etl.source_prep`, `profile.logic`, `profile.pipeline.relation_exists`;Step5 也复用 profile helper。
- 未发现 profile 反向 import maintenance 的循环。主要异味是 `relation_exists` 定义在 `profile.pipeline`,却被 enrichment/maintenance 复用;02B 可考虑迁到 core/db helper,但不要扩大为架构重写。

## 5. 给 02B 的优先级建议

### 必做(P0/P1 优先)

1. 把 `publish_bs_lac._execute_with_session_settings` 迁入 `core/citus_compat.py`,作为统一 `ClientCursor + mogrify + RESET` 实现。
2. 用统一入口替换 `publish_cell.py:56` 的 `trusted_cell_library` 参数化 INSERT。
3. 用统一入口替换 `publish_bs_lac.py:1240` 的 `trusted_lac_library` 参数化 INSERT。
4. 用统一入口替换 `profile/pipeline.py:1546` 的 `candidate_seed_history` 参数化 INSERT。
5. 用统一入口替换 `enrichment/pipeline.py:413` 的 `snapshot_seed_records` 参数化 INSERT。
6. 给 `core/database.py` 的 CTAS split helper增加明确策略: params DML 分支要么走统一入口,要么在报告中列为禁止用于复杂 INSERT/CTE。

### 应做(P1)

1. 梳理 `label_engine.py:103` 的 `INSERT WITH` 是否需要走统一入口,即使当前 params 已内联。
2. 将 `relation_exists` 从 `profile.pipeline` 下沉到 core 级 helper,降低 enrichment/maintenance 对 profile.pipeline 的耦合。
3. 将 session setup/reset 统一到 helper,避免 `SET enable_nestloop` 分散。
4. 给 production runner 所依赖脚本和 research/benchmark 脚本划边界,02B 只改 production surface。
5. 为 `core/database.execute` 增加注释或 guard,说明它不应用于高危 distributed parameterized INSERT...SELECT。

### 不做(P2)

1. 不改 `etl/fill.py` 的 `ctid::text` 只读 source uid 生成。
2. 不重构全部 788 个 `execute(` 调用。
3. 不把 benchmark/fix4/research 脚本全部迁移到生产 helper。
4. 不改变分布键和表结构。
5. 不引入新依赖或新测试框架。

## 6. 给 02C 的优先级建议

### smoke test

- 最小 smoke: reduced sample 1 LAC x 1 天,目标约 5 分钟。fixture 需要可重建的 raw sample 或 mock runner SQL;验 runner 跑通 + `step2_batch_input` 单日 + `_step2_cell_input` 不存在 + Step5 统计存在。
- 静态 smoke: collect 阶段可先不连 DB,检查 production high-risk callers 都不再直接 `execute(..., params)`。

### regression(P0)

1. scope materialization: runner 调用顺序测试,断言 Step1 后 drop `_step2_cell_input` 并物化 `step2_batch_input`。
2. sliding_window trim: SQL shape 测试,禁止 `DELETE ... ctid`,要求 key delete `(batch_id, source_row_uid, cell_id)`。
3. parameterized distributed plan: monkeypatch `ClientCursor`,断言统一 helper params 分支调用 `mogrify`。
4. publish_bs/cell/lac caller guard: 对 3 个 publish 入口做静态/monkeypatch 测试,确保高危 INSERT 不走 `core.database.execute(..., params)`。
5. CTAS helper guard: 有 params 的 CTAS/INSERT split 应走统一策略或明确拒绝。

### nightly(可选)

- batch 1 full sample,目标约 13 分钟。fixture 需要 Citus DSN + reset SQL;验 TCL 总量与 PG17 ±5%,并验 drift pattern 不全为 0。
- batch 1-2 mini chain,目标约 20-30 分钟。验 `trusted_cell_library` 单调增长、`cell_sliding_window` 日期跨度从 1 天到 2 天、batch 2 enriched 单日。

## 7. 已知限制 / 未回答问题

- 当前环境没有 `pytest`,所以 collect-only 没有执行到 import 阶段;报告只能记录 21 个文件 / 72 个 test definitions。
- 本阶段按约束未连接 Citus,distributed/reference 表判断来自代码 `_REFERENCE_TABLES` 和 `rb5.*` 表名语义,不是实时 catalog 查询。
- P1 中 `label_engine.py:103` 使用内联 batch_id 而非 params;是否迁入统一入口取决于 02B 是否希望所有 `INSERT WITH` 一律集中。
- `fix4_claude_pipeline.py`、`bench_parallel.py`、research scripts 是历史/研究脚本;是否纳入 02B 需要上游确认。
- `01_finalize_report.md` 和 `02A_audit_prompt.md` 当前为本地未提交文件;本阶段只新增本报告,不处理 git。
