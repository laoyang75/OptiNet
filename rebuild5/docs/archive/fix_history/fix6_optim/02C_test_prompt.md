# OptiNet rebuild5 / fix6_optim / 02C 测试 — fix5 4 根因回归 + Citus caller 守护(agent 新实例对话)

## § 1 元目标

为 fix5 已修复的 **4 个根因**(scope materialization / sliding_window trim / ctid distributed DELETE / parameterized distributed plan)各加一个**回归 / 静态守护**测试,**防止未来重构悄悄破坏 Citus 兼容**。本阶段是 03 pipelined 加速前的最后一道保险:有了这层守护,03 改 runner / 04 改 helper 都不会再触发 fix5 同款 bug。

不做 integration / nightly(连库的全链路对账留给 03 之后或 04 runbook 阶段)。

## § 2 上下文启动顺序

按序读完直接开工(按 _prompt_template.md § 11 不再要求开跑前 ack):

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/fix6_optim/README.md` —— 全局 + 协作约定
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— **§ 11(自动 commit/push)+ § 12(对上游互审)必读**
4. `rebuild5/docs/fix6_optim/02A_audit_report.md` —— §3.2 fix5 4 根因 vs 现有 tests + §6 推荐测试形态
5. `rebuild5/docs/fix6_optim/02B_refactor_report.md` —— §5 给 02C 的输入(具体 grep 守护目标)
6. `rebuild5/backend/app/core/citus_compat.py` —— 新建的统一入口,02C 第一个测试就测它
7. `rebuild5/tests/` 现有 21 个 `test_*.py` 一瞥(不必逐个读,看 pytest 配置 + import 模式即可)
8. 本 prompt

如果发现 02A/02B 报告里有不可行的测试设计(如 `test_runner_scope_order` 没法在不连库的情况下静态验证调用顺序),**在 02C 报告 §0 写"对上游报告的修订",然后采用替代方案**;不要悄悄绕过。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`(完整读写)
- **当前 git 头**:`bb090de`(02B 交付)
- **Git remote**:`https://github.com/laoyang75/OptiNet.git`
- **本阶段不连数据库**,纯单元 + 静态守护
- **pytest 状态**:02A 报告记录 `python3 -m pytest` 撞 `No module named pytest`。先 `python3 -m pytest --version` 探一遍:
  - **可用** → 跑全套测试,报告里贴每个测试的 pass/fail
  - **不可用** → 不要装系统 pytest(避免污染用户 env)。只做 `python3 -m py_compile` + `python3 -c "import ..."` 的静态导入检查;在报告里明确"测试已写但未在本环境验证运行,需要后续在已配 pytest 的 venv 里跑"
- **现有 tests 风格**(02A §3.1):多为 monkeypatch SQL shape / version guard,不连 Citus。新加的 5 个测试沿用同款风格

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `02A_audit_report.md` §3.2 / §6 | 阅读 | fix5 4 根因 + 推荐测试形态(设计输入) |
| `02B_refactor_report.md` §5 | 阅读 | 静态 grep 守护目标 |
| 现有 `rebuild5/tests/test_*.py` | 阅读(1-2 个样本) | 沿用风格(import / monkeypatch / fixtures) |
| 本阶段产出 `02C_test_report.md` | 新建 | § 7 结构 |

**本阶段不修改任何已有 .md / .py 业务代码**,只新建测试文件 + 本阶段报告。

## § 5 任务清单

### 必做(5 个测试文件,1:1 对应 fix5 4 根因 + 1 个 caller guard)

#### 5.1 `rebuild5/tests/test_citus_compat.py`(根因 #4 + 02B 入口验证)

测 `core/citus_compat.execute_distributed_insert` 本身,monkeypatch psycopg。

至少 3 个 test:

1. `test_uses_client_cursor_for_params`
   - monkeypatch `psycopg.ClientCursor`(或 `core.citus_compat.ClientCursor`)替换为 spy
   - 调 `execute_distributed_insert("INSERT ... %s", params=(1,))`
   - 断言 ClientCursor 被实例化
   - 断言 `cur.mogrify("INSERT ... %s", (1,))` 被调用
   - 断言 `cur.execute(<mogrified result>)` 被调用,**不是** `cur.execute(sql, params)`(关键!这正是 fix5 D 撞的限制)

2. `test_no_params_skips_mogrify`
   - 调 `execute_distributed_insert("INSERT ... values (1)")`(无 params)
   - 断言 mogrify **未被调用**
   - 断言 `cur.execute("INSERT ... values (1)")` 直接调用

3. `test_session_setup_executed_and_reset_in_reverse`
   - 调 `execute_distributed_insert("INSERT ...", session_setup_sqls=["SET enable_nestloop = off", "SET work_mem = '1GB'"])`
   - 断言 cur.execute 调用顺序:
     - `SET enable_nestloop = off`
     - `SET work_mem = '1GB'`
     - `INSERT ...`(主 SQL)
     - `RESET work_mem`(逆序)
     - `RESET enable_nestloop`
   - 断言非 `SET ` 开头的 setup SQL 不会触发 RESET(可加一条 `["SELECT 1", ...]` 验证)

#### 5.2 `rebuild5/tests/test_citus_caller_guard.py`(根因 #4 静态守护)

不连库,纯文本 grep 守护。防止未来某个 caller 又走回 `execute(..., params)` 老路。

至少 4 个 test:

1. `test_no_legacy_execute_with_session_settings`
   - 在 `rebuild5/backend/` 全仓 grep `_execute_with_session_settings`
   - 断言无命中(02B 已删,守护它不被复活)

2. `test_high_risk_callers_use_unified_entry`
   - 对 02B 迁移的 7 个 caller 文件(`publish_bs_lac.py` / `publish_cell.py` / `profile/pipeline.py` / `enrichment/pipeline.py` / `core/database.py`)各 grep:
     - `execute_distributed_insert` 出现次数 ≥ 1(已 import + 已用)
     - **其他自定义 ClientCursor 实例**(`with ClientCursor(` pattern)出现次数 = 0(只在 citus_compat.py 里有)

3. `test_no_top_level_circular_import_for_citus_compat`
   - 读 `core/database.py`,断言文件顶部 `import` / `from` 区段(前 50 行)无 `from .citus_compat`
   - 但允许函数体内 local import(grep `from .citus_compat` 在文件内任何位置 ≥ 0)

4. `test_publish_helpers_no_raw_params_execute`
   - 对 publish_cell.py / publish_bs_lac.py 的每个 publish_* 函数,grep 函数体内不存在 `execute([^)]*params` 形式(允许 `execute_distributed_insert([^)]*params=` 形式)
   - 实现:用 `ast` 模块解析,找 `Call(func=Name("execute"))` 节点,断言它们的 `params` arg 都是 None / 不存在

#### 5.3 `rebuild5/tests/test_runner_scope_materialization.py`(根因 #1)

不连库,静态 + 函数调用顺序断言。

至少 2 个 test:

1. `test_serial_runner_calls_materialize_step2_scope_after_step1`
   - 用 `ast` 解析 `rebuild5/scripts/run_citus_serial_batches.py`,找 main loop 函数体
   - 在 loop body 里定位 `run_step1_pipeline()` / `materialize_step2_scope(...)` / `run_profile_pipeline()` 三个调用的相对顺序
   - 断言:`materialize_step2_scope` 出现在 `run_step1_pipeline` 之后、`run_profile_pipeline` 之前
   - 断言:同一 loop iteration 里有 `DROP TABLE IF EXISTS rb5._step2_cell_input`(grep 字符串即可)

2. `test_materialize_step2_scope_imported_from_daily_loop`
   - 静态读 `run_citus_serial_batches.py` import 区
   - 断言 `materialize_step2_scope` 从 `run_daily_increment_batch_loop`(任一相对/绝对路径)import

#### 5.4 `rebuild5/tests/test_sliding_window_trim_shape.py`(根因 #2 + #3)

不连库,SQL 字符串 shape 静态分析。

至少 3 个 test:

1. `test_trim_uses_pk_delete_not_ctid`
   - 读 `rebuild5/backend/app/maintenance/window.py` 源文件
   - 找 `refresh_sliding_window` 函数(或 trim 部分对应的 execute 调用)的 SQL 字符串
   - 断言 SQL 含 `DELETE FROM rb5.cell_sliding_window`
   - 断言 **同一 SQL 不含** `WHERE ... ctid` / `ctid =` / `ctid IN` 形式(关键!fix5 C 已修)
   - 断言 SQL 含 `(batch_id, source_row_uid, cell_id)` PK 三元组(任一形式:`USING delete_keys d WHERE w.batch_id = d.batch_id ...`)

2. `test_trim_retention_window_clause_present`
   - 同 SQL 字符串
   - 断言含 `WINDOW_RETENTION_DAYS` 或 `INTERVAL '14 days'`(允许 f-string 注入,grep `RETENTION_DAYS` 文字也接受)
   - 断言含 `obs_rank` / `WINDOW_MIN_OBS` 或 `1000`(per-cell latest N 保护)

3. `test_no_skip_sliding_window_trim_env_var`
   - grep `rebuild5/backend/` + `rebuild5/scripts/` 全仓
   - 断言无 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM` 任何形式的赋值 / setdefault(fix5 B 阶段已删,守护它不复活)

#### 5.5 `rebuild5/tests/test_ctid_static_guard.py`(根因 #3 全仓守护)

不连库,纯 grep。

至少 2 个 test:

1. `test_no_distributed_delete_with_ctid_where`
   - grep `rebuild5/backend/` + `rebuild5/scripts/` 中所有 `.py` 文件
   - 找出所有含 `ctid` 字符串的行
   - 对每行,断言**所在 SQL 块**(可粗略:同一 triple-quoted f-string 内)不含 `DELETE FROM` 任意大小写(精确点用 ast 解析 f-string,简化用：人为允许 list,白名单)
   - **白名单**:`etl/fill.py:138` 的 `ctid::text` 只读投影是允许的,因为不在 DELETE 上下文

2. `test_publish_bs_does_not_use_ctid_anywhere`
   - 读 `maintenance/publish_bs_lac.py`
   - 断言文件全文无 `ctid` 字符串(publish 路径任何 ctid 用法都是危险)

### 其他必做

#### 5.6 验证现有 21 个 tests 没被打破(如果 pytest 可用)

```bash
python3 -m pytest --version  # 探测
# 如果可用:
cd rebuild5 && python3 -m pytest tests/ -x --tb=short 2>&1 | tail -30
# 如果不可用:
python3 -m py_compile rebuild5/tests/*.py 2>&1 | head
python3 -c "import sys; sys.path.insert(0, 'rebuild5'); from tests import test_etl_definitions; print('import ok')" 2>&1 | head
```

把输出贴进 02C 报告 §3。**任何已有 test 被新加测试影响 → 不要修旧 test,在报告 §0 修订并报告原因**(可能是测试间共享 fixture 冲突)。

#### 5.7 完工后流程(按 _prompt_template.md § 11)

1. `git add` 显式列:
   - `rebuild5/tests/test_citus_compat.py`(新)
   - `rebuild5/tests/test_citus_caller_guard.py`(新)
   - `rebuild5/tests/test_runner_scope_materialization.py`(新)
   - `rebuild5/tests/test_sliding_window_trim_shape.py`(新)
   - `rebuild5/tests/test_ctid_static_guard.py`(新)
   - `rebuild5/docs/fix6_optim/02B_refactor_prompt.md`(02B 写但未提交,本阶段一并 commit)
   - `rebuild5/docs/fix6_optim/02C_test_prompt.md`(本 prompt)
   - `rebuild5/docs/fix6_optim/02C_test_report.md`(产出)
   - `rebuild5/docs/fix6_optim/README.md`(更新阶段状态)

2. 一个 commit:
   ```
   test(rebuild5): fix6_optim 02C add fix5 4 root cause regression guards

   - test_citus_compat: ClientCursor + mogrify + RESET-in-reverse on
     execute_distributed_insert (root cause #4 parameterized distributed plan)
   - test_citus_caller_guard: static grep + AST guard on 7 high-risk callers
     using unified entry; no _execute_with_session_settings revival
   - test_runner_scope_materialization: serial runner calls materialize_step2_scope
     between Step1 and Step2-3 (root cause #1)
   - test_sliding_window_trim_shape: trim uses (batch_id, source_row_uid, cell_id)
     PK delete, retention window present, no SKIP_SLIDING_WINDOW_TRIM env var
     (root cause #2)
   - test_ctid_static_guard: no DELETE FROM rb5.* WHERE ctid pattern anywhere;
     etl/fill.py ctid::text projection whitelisted (root cause #3)
   - References fix6_optim/02A_audit_report.md §3.2/§6 and 02B_refactor_report.md §5

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   ```

3. `git push origin main`(如果 push 撞瞬时 SSL/HTTP2 错误,**等 30s 重试 1 次**;再失败才 blocker)

4. 写 note `topic='fix6_02C_done'`

5. 用 § 9 完工话术汇报

### 不做(显式禁止)

- ❌ 不写 integration test(连库的全链路对账,留给 03 / 04)
- ❌ 不写 nightly fixture(留给 04 runbook)
- ❌ 不修改任何业务代码 / 文档(02A 02B 已定稿)
- ❌ 不安装 pytest 到系统 / 用户 site-packages(只用 venv 里的,如果没 venv 就静态检查)
- ❌ 不修改现有 21 个 test_*.py(可读不可改)
- ❌ 不引入新依赖(假设标准库 + 已有 psycopg / pytest 即可,如缺就用纯标准库 ast/re/pathlib 写)
- ❌ 不开 PR / 不开分支
- ❌ 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc

## § 6 验证标准

任务 done 的硬标准:

1. **5 个测试文件存在**:`ls rebuild5/tests/test_{citus_compat,citus_caller_guard,runner_scope_materialization,sliding_window_trim_shape,ctid_static_guard}.py` 全部 hit
2. **每个测试文件至少有最少 test_ 数量**:5.1=3 / 5.2=4 / 5.3=2 / 5.4=3 / 5.5=2 = 共 ≥ 14 个 `def test_`
3. **py_compile 全过**:5 个新文件全部 0 退出码
4. **pytest 可用时**:5 个新文件全部 pass(贴 `pytest -v` 输出)
5. **pytest 不可用时**:每个测试文件能 import(`python3 -c "import sys; sys.path... ; from tests import <module>"` 0 退出),并在报告 §3 明确标 "未在本环境运行,需要 pytest 配置后跑"
6. **commit 内容**:`git show --stat HEAD` 显示 ≥ 8 个文件改动(5 测试 + 报告 + README + 本 prompt + 02B 遗留 prompt)
7. **push 远端同步**:`git rev-parse HEAD == git rev-parse origin/main`
8. **note 已写**:`SELECT body FROM rb5_bench.notes WHERE topic='fix6_02C_done'` 返回非空,body 含 14+ 测试数 + pytest 是否 pass

## § 7 产出物 `02C_test_report.md`

```markdown
# fix6_optim / 02C 测试报告

## 0. TL;DR + 对上游报告的修订
- 5 个新测试文件,N 个 test_ 函数
- pytest 可用?<是 / 否>;若是,M/M pass
- fix5 4 根因覆盖:#1=test_runner_scope_*;#2=test_sliding_window_trim_*;#3=test_ctid_*;#4=test_citus_compat + test_citus_caller_guard
- 对 02A 修订:<无 / 列出>
- 对 02B 修订:<无 / 列出>
- commit SHA:<sha>;push 状态:<status>

## 1. 测试设计(逐文件)
### 1.1 test_citus_compat.py
- 文件路径、test_ 数、覆盖根因 #4
- 每个 test 一行说明
- 关键 monkeypatch 对象 + 断言对象

### 1.2 test_citus_caller_guard.py
... 同结构

### 1.3 ~ 1.5 ...

## 2. 静态分析方式
- 用 ast / re / pathlib 而非 pytest 内建(因 pytest 可能不可用)
- 关键解析点的实现策略

## 3. 运行结果
### 3.1 pytest 探测
- python3 -m pytest --version 输出
- 若可用:全部 21+5 = 26 个 test 文件的 pytest -v 末尾 30 行
- 若不可用:`python3 -m py_compile` + `python3 -c "import ..."` 输出

### 3.2 守护命中(grep / ast 输出节选)
- _execute_with_session_settings 残留:无
- DELETE ... ctid 命中:无(白名单 etl/fill.py:138)
- REBUILD5_SKIP_SLIDING_WINDOW_TRIM 残留:无

## 4. 已知限制 / 未做
- integration / nightly:本阶段未做,留给 03 / 04
- 新依赖:无引入
- pytest 配置(若不可用):需要后续在 venv 跑

## 5. 给 03 pipelined 的输入
- 03 改 runner 时,以下守护必须保持绿色,任何一条挂红立刻停下来排查:
  1. test_runner_scope_materialization.test_serial_runner_calls_materialize_step2_scope_after_step1
     —— 03 如果加 pipelined runner,新 runner 也要满足同等约束
  2. test_citus_caller_guard.test_high_risk_callers_use_unified_entry
     —— 03 如果新加 publish 入口,必须用 execute_distributed_insert
  3. test_sliding_window_trim_shape.* + test_ctid_static_guard.*
     —— window.py 任何改动都要保持 PK delete shape
- 03 在新 runner 文件里如果用类似的"step1 → scope → step2-5"结构,02C 应当扩展守护到新 runner(本阶段先不扩展)
```

## § 8 notes 协议

- 完工:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_02C_done', 'info',
    'fix5 4 root cause regression guards added, files=5, test_=<n>, pytest=<available|absent>, pytest_pass=<m/n|n/a>, head=<sha>, no upstream revisions OR <list>');
  ```
- 失败:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_02C_failed', 'blocker', 'failed at <step>: <reason>');
  ```

## § 9 完工话术

成功:
> "fix6_optim 02C 完成。02C_test_report.md 已写入。新增 5 个测试文件,<N> 个 test_,fix5 4 根因 1:1 覆盖。pytest <可用/不可用>:<M/N pass / 仅静态导入检查>。对 02A/02B 修订:<无 / 列表>。commit=<SHA>,GitHub:<url>。notes `topic='fix6_02C_done'` 已插入。"

失败:
> "fix6_optim 02C 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='fix6_02C_failed'`。等上游处置。"

## § 10 失败兜底

- **pytest 不可用 + 不能装**:不要尝试 `pip install` 系统级污染;5 个测试**仍要写完**,只是不在本环境跑,在报告 §3 明确标"未运行验证"。这不算 blocker,02C 仍可完工
- **ast 解析撞 SyntaxError**(被分析文件有 lazy import 等):报告里说明,改用纯 re grep 替代,降级但不放弃断言
- **测试本身假设错误**(比如以为 publish_bs 用了 ClientCursor 但 02B 改的方式不一样):**先读源文件再写测试**,不要凭 prompt 想象;报告 §0 修订 02B 描述
- **现有 21 个 test 中有某个被打破**:不修旧 test,在报告 §0 修订 + 标 blocker(因为说明 02B 改动有侧面影响)
- **push 撞瞬时网络**:等 30s 重试 1 次再 blocker
- **任何挂** → blocker note + 对话报告 + 等上游
