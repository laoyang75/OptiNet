# fix6_optim / 02C 测试报告

## 0. TL;DR + 对上游报告的修订

- 5 个新测试文件,14 个 `test_` 函数;`rebuild5/tests/` 现有 21 个测试文件未修改,总文件数 26。
- pytest 可用?否;当前环境 `python3 -m pytest --version` 返回 `No module named pytest`。已完成 `py_compile`、静态导入检查和新增测试手工执行。
- fix5 4 根因覆盖:#1=`test_runner_scope_materialization.py`;#2=`test_sliding_window_trim_shape.py`;#3=`test_ctid_static_guard.py`;#4=`test_citus_compat.py` + `test_citus_caller_guard.py`。
- 对 02A 修订:无。
- 对 02B 修订:无。
- commit SHA:本报告随 02C commit 提交;最终 SHA 以 `git rev-parse HEAD` / 完工话术为准。push 状态:待 commit 后执行。

## 1. 测试设计(逐文件)

### 1.1 test_citus_compat.py

- 路径:`rebuild5/tests/test_citus_compat.py`;3 个 `test_`;覆盖根因 #4 parameterized distributed plan。
- `test_uses_client_cursor_for_params`:monkeypatch `citus_compat.ClientCursor` 和 `get_conn`,断言 params 分支实例化 client cursor、调用 `mogrify(sql, params)`,再执行 mogrified SQL。
- `test_no_params_skips_mogrify`:断言无 params 时不调用 `mogrify`,直接 `execute(sql)`。
- `test_session_setup_executed_and_reset_in_reverse`:断言 setup SQL 顺序执行,主 SQL 后按逆序 RESET;非 `SET ` 语句不触发 RESET。

### 1.2 test_citus_caller_guard.py

- 路径:`rebuild5/tests/test_citus_caller_guard.py`;4 个 `test_`;覆盖根因 #4 caller 防回退。
- `test_no_legacy_execute_with_session_settings`:backend 全仓禁止 `_execute_with_session_settings` 复活。
- `test_high_risk_callers_use_unified_entry`:守护 02B 迁移的 5 个文件均包含 `execute_distributed_insert`,且不在 caller 内自建 `ClientCursor` context。
- `test_no_top_level_circular_import_for_citus_compat`:守护 `core/database.py` 前 50 行无 `from .citus_compat`,保留函数体 local import 方案。
- `test_publish_helpers_no_raw_params_execute`:用 AST 遍历 publish helper 函数,禁止 `execute(..., params=...)` 形态回归;允许 `execute_distributed_insert(params=...)`。

### 1.3 test_runner_scope_materialization.py

- 路径:`rebuild5/tests/test_runner_scope_materialization.py`;2 个 `test_`;覆盖根因 #1 scope materialization。
- `test_serial_runner_calls_materialize_step2_scope_after_step1`:AST 定位 serial runner 主循环,断言 `run_step1_pipeline()` < `materialize_step2_scope(...)` < `run_profile_pipeline()`,并守护同文件含 `DROP TABLE IF EXISTS rb5._step2_cell_input`。
- `test_materialize_step2_scope_imported_from_daily_loop`:断言 runner 从 `run_daily_increment_batch_loop` import `materialize_step2_scope`。

### 1.4 test_sliding_window_trim_shape.py

- 路径:`rebuild5/tests/test_sliding_window_trim_shape.py`;3 个 `test_`;覆盖根因 #2 sliding_window trim 和 #3 ctid delete。
- `test_trim_uses_pk_delete_not_ctid`:AST 提取 `refresh_sliding_window` trim SQL,断言 `DELETE FROM rb5.cell_sliding_window` 使用 `delete_keys` 和 `(batch_id, source_row_uid, cell_id)` join,不含 `ctid`。
- `test_trim_retention_window_clause_present`:断言 trim SQL 保留 `WINDOW_RETENTION_DAYS` 和 `obs_rank` / `WINDOW_MIN_OBS`。
- `test_no_skip_sliding_window_trim_env_var`:backend + scripts 全仓禁止 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM` 复活。

### 1.5 test_ctid_static_guard.py

- 路径:`rebuild5/tests/test_ctid_static_guard.py`;2 个 `test_`;覆盖根因 #3 distributed DELETE with ctid。
- `test_no_distributed_delete_with_ctid_where`:AST 提取 backend + scripts Python 字符串,禁止同一 SQL 字符串同时含 `DELETE FROM` 与 `ctid`;白名单 `etl/fill.py` 的 `ctid::text` 只读投影。
- `test_publish_bs_does_not_use_ctid_anywhere`:守护 `maintenance/publish_bs_lac.py` 全文不含 `ctid`。

## 2. 静态分析方式

- 使用 `ast` / `pathlib` / 字符串 grep,不依赖 pytest 特性或数据库连接。
- SQL shape 通过 AST 提取 `Constant(str)` 与 `JoinedStr` 内容,避免只按相邻源码行误判。
- runner 调用顺序通过 AST call lineno 比较,不执行 runner。
- caller guard 对 publish 函数体做 AST Call 检查,避免普通注释或文档字符串影响结论。

## 3. 运行结果

### 3.1 pytest 探测

```text
$ python3 -m pytest --version
/opt/homebrew/opt/python@3.14/bin/python3.14: No module named pytest
```

pytest 不可用,按 02C prompt 兜底流程未安装新依赖,未在本环境运行 pytest。

```text
$ python3 -m py_compile rebuild5/tests/*.py
# exit 0, no output

$ python3 -c "import sys; sys.path.insert(0, 'rebuild5/tests'); import test_citus_compat, test_citus_caller_guard, test_runner_scope_materialization, test_sliding_window_trim_shape, test_ctid_static_guard; print('new test imports ok')"
new test imports ok

$ python3 -c "import sys; sys.path.insert(0, 'rebuild5/tests'); import test_etl_definitions; print('existing import ok')"
existing import ok

$ python3 -c "<manual invocation of all 14 new test functions>"
manual new tests ok
```

### 3.2 守护命中(grep / ast 输出节选)

```text
$ rg -n "_execute_with_session_settings" rebuild5/backend || true
# no output

$ rg -n "REBUILD5_SKIP_SLIDING_WINDOW_TRIM" rebuild5/backend rebuild5/scripts || true
# no output

$ rg -n "ctid" rebuild5/backend rebuild5/scripts || true
rebuild5/backend/app/etl/fill.py:138:                c.ctid::text,
```

`etl/fill.py:138` 是只读 `ctid::text` 投影,已在 `test_ctid_static_guard.py` 白名单中保留。

## 4. 已知限制 / 未做

- integration / nightly:本阶段未做,留给 03 / 04。
- 新依赖:无引入。
- pytest 配置:当前环境缺 pytest;需要后续在已配置 pytest 的 venv 中运行 `cd rebuild5 && python3 -m pytest tests/ -x --tb=short`。
- 现有 21 个测试文件未修改;因 pytest 缺失,本环境只做 `py_compile` 与单个既有测试模块静态导入验证。

## 5. 给 03 pipelined 的输入

- 03 改 runner 时,以下守护必须保持绿色,任何一条挂红立刻停下来排查:
  1. `test_runner_scope_materialization.test_serial_runner_calls_materialize_step2_scope_after_step1` —— 03 如果加 pipelined runner,新 runner 也要满足同等约束。
  2. `test_citus_caller_guard.test_high_risk_callers_use_unified_entry` —— 03 如果新加 publish 入口,必须用 `execute_distributed_insert`。
  3. `test_sliding_window_trim_shape.*` + `test_ctid_static_guard.*` —— `window.py` 任何改动都要保持 PK delete shape。
- 03 在新 runner 文件里如果用类似的 "step1 -> scope -> step2-5" 结构,02C 应当扩展守护到新 runner;本阶段先不扩展。
