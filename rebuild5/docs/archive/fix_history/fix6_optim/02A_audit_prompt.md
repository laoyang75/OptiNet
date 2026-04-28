# OptiNet rebuild5 / fix6_optim / 02A 审计(只读 · agent 新实例对话)

## § 1 元目标

**纯只读地**扫一遍 `rebuild5/backend/` + `rebuild5/scripts/` + `rebuild5/tests/`,产出**全景审计报告**,定位 03 pipelined 加速之前必须解决的:
1. **Citus 兼容隐患**(类似 fix5 D 撞的 publish_bs_library 那种,batch 4 才炸的隐性 bug)
2. **helper 散落 / 重复**(现在每个模块自己写 INSERT...SELECT,没统一 Citus 兼容层)
3. **测试覆盖空白**(现有 `tests/` 跑得通什么、没 cover 什么)

**不动代码、不动数据库、不动文档。** 只产出 1 份报告,02B/02C 基于这份报告决定具体重构和测试范围。

## § 2 上下文启动顺序

按序读完再动手:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/fix6_optim/README.md` —— 全局阶段表
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— prompt 模板,核对本 prompt 完整性
4. `rebuild5/docs/fix6_optim/01_finalize_report.md` —— 01 阶段交付,知道 head SHA
5. `rebuild5/docs/fix5/01_quality_diagnosis.md` —— fix5 根因诊断
6. `rebuild5/docs/fix5/04_code_fix_report.md` —— C 阶段代码改动
7. `rebuild5/docs/fix5/06_rerun_validation.md` §5 附录 —— D 阶段 publish_bs Citus 错误的 traceback + hotfix 实施细节(本次审计的核心参考)
8. `rebuild5/backend/app/maintenance/publish_bs_lac.py` L890-L915 —— 当前唯一已修的 ClientCursor 实例,作为 "Citus-safe" 模式参考
9. 本 prompt(你正在读的)

读完不立刻动手。先在对话里报告:
- 你计划用什么 grep / 工具扫(给具体命令)
- 你预期需要审计的代码量级(行数 / 模块数)
- 你打算怎么分类风险等级(P0/P1/P2 之类)

等用户 ack 再开扫。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`(读权限即可,本阶段不写任何代码 / 数据库)
- **当前 git 头**:`4b23cd013f2cc96c18fcb1731b2a57737d7d1fa5`
- **审计目标目录**:
  - `rebuild5/backend/app/`(主要)
  - `rebuild5/backend/app/core/database.py`(execute helper 起点)
  - `rebuild5/scripts/`(runner 层 helper)
  - `rebuild5/tests/`(现有测试覆盖)
- **已知现状**(survey 结果):
  - `tests/` 有 ~10+ 个 `test_*.py`,覆盖 etl/profile/label_engine/service 各层
  - **`ClientCursor` / `mogrify` 当前只在 `publish_bs_lac.py:894` 一处使用** —— 这是 fix5 D 阶段的 hotfix 起点
  - 其他模块仍然走 `with conn.cursor() as cur: cur.execute(sql, params)` 默认路径,**潜在风险面**

**本阶段不需要数据库连接**,所有审计来自代码静态分析 + 文档阅读。**禁止跑 pipeline / 改 schema**。

## § 4 关联文档清单(只读不改)

| 路径 | 用途 |
|---|---|
| `rebuild5/docs/fix5/01_quality_diagnosis.md` | fix5 根因诊断,知道 scope materialization 等 root cause 是怎么找到的 |
| `rebuild5/docs/fix5/04_code_fix_report.md` | C 阶段 3 处改动,知道当前 Citus 兼容的最小集 |
| `rebuild5/docs/fix5/06_rerun_validation.md` | D 阶段 publish_bs hotfix + auto_explain 兼容,知道 ClientCursor 是怎么救场的 |
| `rebuild5/docs/01b_数据源接入_处理规则.md` | ETL 清洗规则,审计 etl/* 时对照 |
| `rebuild5/docs/03_流式质量评估.md` | profile/* 的业务规则 |
| `rebuild5/docs/05_画像维护.md` | maintenance/* 的业务规则 |

## § 5 任务清单

### 必做

#### 5.1 Citus 兼容隐患全扫

对 `rebuild5/backend/` + `rebuild5/scripts/` 跑下面这些 grep,把每个命中点分类报告:

```bash
# A. 默认 cursor + 参数化 execute(可能撞 distributed plan 限制,publish_bs 那种)
grep -rn "cur\.execute([^)]*params" rebuild5/backend rebuild5/scripts
grep -rn "\.execute([^)]*%s" rebuild5/backend rebuild5/scripts

# B. session-level SET citus.* 散落(应该集中到统一入口)
grep -rn "SET citus\." rebuild5/backend rebuild5/scripts
grep -rn "SET enable_" rebuild5/backend rebuild5/scripts
grep -rn "SET auto_explain" rebuild5/backend rebuild5/scripts

# C. ctid 用法(Citus distributed DELETE 不支持 ctid WHERE,fix5 已踩过)
grep -rn "ctid" rebuild5/backend rebuild5/scripts

# D. SQL function 创建(SQL 语言 + 参数,Citus 限制)
grep -rn "CREATE.*FUNCTION.*LANGUAGE.*[sS][qQ][lL]" rebuild5/backend rebuild5/scripts

# E. INSERT...SELECT 含多 CTE(Citus generic plan 撞参数化的高危模式)
grep -rln "INSERT INTO" rebuild5/backend | xargs grep -l "WITH" | head

# F. EXPLAIN ANALYZE 在 INSERT 上(Citus coordinator 不支持)
grep -rn "EXPLAIN ANALYZE.*INSERT" rebuild5/backend rebuild5/scripts
```

每个命中点按以下风险分级(P0 = fix5 已验证会炸的模式;P1 = 同结构但还没触发的潜在炸点;P2 = 一般 code smell 不影响 Citus):

- **P0** 已知 Citus 不兼容,batch 量级到了一定就会炸(参考 fix5 D publish_bs)
- **P1** 类似模式但目前批量级未到 / 走过 fast-path,不能保证未来稳
- **P2** 风格 / 重复 / 未来迁移问题,不紧急

每个命中点报告:文件 + 行号 + ~3 行上下文 + 风险等级 + 一句话说明"为什么是这个等级"。

#### 5.2 helper 散落 / 重复审计

backend 各模块的 SQL 执行模式有几套?各自 helper 在哪定义?互相重复多少?

特别关注:
- `core/database.py::execute / fetchone / fetchall` —— 默认路径
- `core/database.py::CTAS_PATTERN` / Citus distributed_table 创建 helper —— C 阶段加的
- `maintenance/publish_bs_lac.py::_execute_with_session_settings` —— D 阶段 hotfix 局部
- 各模块自定义的 `_run_sql` / `_insert_*` 等 ad-hoc 工具

输出一张**模块 × helper 矩阵**:每个模块用了哪个 helper、自己有没有写一份、是否 Citus-aware。

最后给出**统一接口建议**(02B 要落地的 `core/citus_compat.py` 应该长什么样):
- 接口签名草案(参数、返回、副作用)
- 该接口替换掉现有哪些 caller
- 不能统一的 corner case(如果有)

#### 5.3 测试覆盖现状审计

```bash
ls -la rebuild5/tests/
grep -rn "^def test_" rebuild5/tests/ | wc -l
```

报告:
- 现有 tests 数量、覆盖哪些层(etl / profile / label / maintenance / publish / runner)
- **能不能跑通?** 试 `cd rebuild5 && python -m pytest tests/ --collect-only -q`(只 collect,不执行,看有无 import error)
- 有没有针对 Citus 跑的 integration test(几乎肯定没有,但要 confirm)
- **核心空白**:fix5 期间发现的 4 个根因(scope materialization / sliding_window trim / ctid / parameterized distributed plan)有没有任何对应回归测试 → 答案肯定是没有,但要给出"如果要补,每个根因对应什么测试"的草案

#### 5.4 跨模块依赖 / 抽象空隙

backend/app 各包之间的依赖关系(grep import 即可,不深挖):
- `etl/` → 谁?
- `enrichment/` → 谁?
- `profile/` → 谁?
- `maintenance/` → 谁?

哪些是合理依赖,哪些是循环 / 反向依赖?有没有"profile 直接 import maintenance 的 helper"这种异味?

#### 5.5 给 02B(重构)的优先级建议

基于 5.1 的 P0/P1 清单,给 02B 排个优先级:
- **必做(P0)**:这些不修,03 pipelined 一上就会炸
- **应做(P1)**:这些可以推迟到 03 之后,但 02B 顺手做掉成本低
- **不做(P2)**:留给未来重构,02B 不碰

#### 5.6 给 02C(测试)的优先级建议

基于 5.3 的空白 + 5.1 的 P0,给 02C 排个优先级:
- **smoke test**(最小):reduced sample 1 LAC × 1 天,~5 分钟,验"runner 跑通 + 4 哨兵"
- **regression test**(P0 对应):每个 fix5 根因配一个 unit / integration test
- **nightly**(可选):full sample batch 1,~13 分钟,验"PG17 ±5%"

每个测试给出:测什么、需要什么 fixture、预期 ~ 多长

### 不做(显式禁止)

- ❌ 不改任何代码、不 git add / commit / push
- ❌ 不动数据库(连读 SQL 都不用,本阶段纯静态分析)
- ❌ 不修 .md 文档(只写本阶段产出报告)
- ❌ 不跑 pipeline / runner
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc
- ❌ 不引入新依赖
- ❌ 不下载工具(用仓库已有的 grep / find / git)
- ❌ 不预判"应该这么改" —— 02A 是审计,不是设计;具体改法 02B 再决定
- ❌ 不开新分支

## § 6 验证标准

任务 done 的硬标准:

1. **5 类 grep 全部跑过** —— 每类至少 1 行结果(可能为 0 但报告写"未命中")
2. **风险分级有量化** —— P0 / P1 / P2 各类条目数有具体数字,不允许"看起来没几个"这种表述
3. **统一 helper 接口草案有具体签名** —— 不允许"建议抽个 helper"这种空话,要有 `def execute_distributed_xxx(...) -> ...:` 级别的具体形状
4. **现有 tests 能 collect** —— 报告里贴 `pytest --collect-only -q` 的输出(只要数字 + import 是否过)
5. **fix5 4 根因 → 测试草案 4 条** —— 一对一覆盖
6. **02B / 02C 优先级清单 ≥ 5 条** 各 —— 不允许只列 1-2 条

## § 7 产出物

`rebuild5/docs/fix6_optim/02A_audit_report.md`,结构:

```markdown
# fix6_optim / 02A 审计报告

## 0. TL;DR
- P0 隐患:N 条
- P1 隐患:N 条
- P2 隐患:N 条
- helper 散落:N 个模块各自一套
- 测试覆盖:M 个 test_*,K 个能 collect 通过,0 个 Citus 集成测试
- 给 02B 必做项:N 条
- 给 02C 必做项:N 条

## 1. Citus 兼容隐患清单(按风险分级)
### 1.1 P0(fix5 已验证模式)
| 文件:行号 | 模式 | 上下文 | 风险说明 |
| --- | --- | --- | --- |
...
### 1.2 P1(同结构未触发)
...
### 1.3 P2(风格 / 重复)
...

## 2. helper 散落 / 重复
### 2.1 模块 × helper 矩阵
| 模块 | 用 core/database.py | 自有 helper | Citus-aware? |
| --- | --- | --- | --- |
| etl/ | execute, fetchone | _run_etl_step | 否 |
| ... | ... | ... | ... |

### 2.2 统一接口草案(给 02B)
```python
# rebuild5/backend/app/core/citus_compat.py(02B 落地)

def execute_distributed_insert(
    sql: str,
    *,
    params: tuple[Any, ...] | None = None,
    session_setup_sqls: list[str] | None = None,
) -> None:
    """统一 Citus-safe INSERT...SELECT 入口。
    强制 ClientCursor + 客户端 inline params + 自动 RESET session-level SET。
    """
    ...
```
- 替换掉的 caller(列):`maintenance/publish_bs_lac.py:894`、...
- 不能统一的 corner case(如果有):...

## 3. 测试覆盖现状
### 3.1 现有 tests
| 文件 | def test_ 数 | 测什么层 | collect-only 通过? |
| --- | --- | --- | --- |
...

### 3.2 fix5 4 根因 vs 现有 tests
| 根因 | 现有 test? | 推荐测试形态 |
| --- | --- | --- |
| scope materialization | 无 | integration: 验 batch N 后 step2_batch_input 单日 |
| sliding_window trim | 无 | unit: 喂带 2023 时间戳的 input,验 trim 输出 |
| ctid 不支持 | 无 | static: grep 守护 |
| parameterized distributed plan | 无 | unit: ClientCursor 模式守护 |

## 4. 跨模块依赖 / 抽象空隙
- 反向依赖:...
- 循环依赖:...
- 异味:...

## 5. 给 02B 的优先级建议
### 必做(P0)
1. ...
2. ...
### 应做(P1)
...
### 不做(P2)
...

## 6. 给 02C 的优先级建议
### smoke test
- 测什么、fixture、预期时长
### regression(P0)
- 4 个根因测试草案
### nightly(可选)
- batch 1 full sample 对账 PG17

## 7. 已知限制 / 未回答问题
(如果你扫的过程中发现"这块需要业务 owner 确认"或"语义模糊不能下判断",列在这里给上游)
```

## § 8 notes 协议

`rb5_bench.notes` schema:`(id, run_id, topic, severity, body, created_at)`,字段是 **body** 不是 message。

- 开跑前(读完所有 §2 文件,给出 grep 计划):
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_02A_started', 'info',
    'audit start, scope=backend+scripts+tests, plan=<grep classes A-F>, no code changes');
  ```
- 完工:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_02A_done', 'info',
    'audit complete, P0=<n>, P1=<n>, P2=<n>, tests_collectable=<k>, recs_for_02B=<n>, recs_for_02C=<n>');
  ```
- 失败:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_02A_failed', 'blocker', 'failed at <step>: <one-line reason>');
  ```

## § 9 完工话术

成功:
> "fix6_optim 02A 完成。02A_audit_report.md 已写入。关键发现:P0=<n>(列表见报告 §1.1)、helper 矩阵显示 <m> 个模块各自一套、测试覆盖 fix5 4 根因 = 0/4。给 02B 必做 <k> 条、给 02C 必做 <j> 条。notes `topic='fix6_02A_done'` 已插入。请上游 review,然后写 02B 重构 prompt。"

失败:
> "fix6_optim 02A 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='fix6_02A_failed'`。等上游处置。"

## § 10 失败兜底

- **grep / find 命令撞性能问题**(repo 内有 `.venv_research/` 等大量第三方包)→ 排除路径:`--exclude-dir=.venv_research --exclude-dir=__pycache__ --exclude-dir=node_modules`,或者直接用 `git ls-files | xargs grep ...` 只扫 tracked 文件
- **pytest collect 失败**(import error 等)→ 不要尝试修复,把错误信息原样贴到报告 §3.1,标 "collect failed"
- **撞陌生模式不会判断 P0/P1/P2** → 标 "P?" + 说明,在报告 §7 列给上游
- **报告写到一半发现需要改代码才能确认隐患** → 不要改,在报告 §7 列 "需要 02B 验证" 的待确认项
- **5 类 grep 任意一类命中超过 50 行** → 在报告里只贴 top 20 + 给完整数字,不要把几百行 grep 输出全塞 .md
- **任何挂** → `severity='blocker'` note,不硬扛
