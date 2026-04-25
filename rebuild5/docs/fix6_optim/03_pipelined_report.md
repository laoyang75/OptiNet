# fix6_optim / 03 pipelined 加速 + Runbook 报告(终点)

## 0. TL;DR + 对上游修订

- 并发模型:threading,Step1 producer + Step2-5 consumer。
- 数据隔离:barrier 方案。Step1(day N+1) 可与 Step2-5(day N) 重叠,但 Step2 scope(day N+1) 必须等 batch N 的 `batch_validation` + 4 哨兵通过后才物化。
- 全 7 批时长:T_pipe=7,946.83s,T_serial=~9,000s,speedup=1.13x。未达 1.3x 目标,但数据一致性达标。
- TCL b7:340,767(vs fix5 D 348,921,-2.34%;vs PG17 341,460,-0.20%)。
- 数据一致性:7 批内置 4 哨兵全过;终点 3 验收通过。batch 1 Path-A 为空,沿用 fix5 D 口径,`enriched_records` 只要求 batch 2-7 严格单日。
- runbook:04_runbook.md + 6 个 `scripts/runbook/*.sh` 已落地并 `bash -n` 通过;`endpoint_check.sh` 与 `sentinels.sh 7` 实测通过。
- 对 02A/02B/02C 修订:无。对 03 prompt 的验收口径修订:enriched 覆盖按 fix5 D 基线允许 batch 1 空批,否则会错误判红。
- commit SHA:本报告所在 commit,以 `git rev-parse HEAD` / 完工话术为准;push 状态:同完工话术。
- fix6_optim 收档,无后续主线阶段。

## 1. 设计选型决策

1. 并发模型:选 threading。Step1 和 Step2-5 都是 SQL-bound,Python 线程主要负责调度和等待数据库,不需要 multiprocessing 的 IPC 成本。
2. 数据隔离:选 barrier。共享表 `rb5.raw_gps` / `rb5.etl_cleaned` 可被下一天 Step1 改写,但 Step2-5 只允许读取已经冻结的 `rb5.step2_batch_input`。为保证外部/内置哨兵 #3 可审计,下一天 scope 物化延后到上一批 `batch_sentinels` 通过之后。
3. connection 池:不共享连接。runner 只复用现有 `core.database` helper;每次 SQL 调用进入 `get_conn()` 都新建独立 autocommit connection,满足 psycopg connection 不跨线程共享。
4. race/死锁防护:只允许一个 Step2-5 consumer 串行执行;Step1 producer 最多提前一批。barrier 防止 `DROP/CREATE rb5.step2_batch_input` 与 profile 阶段并发;失败时 `stop_event` fail-fast。
5. 错误处理:任一线程异常记录 first error、写 blocker/fallback note、停止队列;不会继续推进后续 scope。
6. fallback:CLI 支持 `--fallback-on-error` 调串行 runner `--start-batch-id <failed> --skip-reset`。实战最终成功 run 未触发 fallback;早期代码 bug 触发过一次,已停止并 reset 后重跑,不计数据失败。

## 2. 实现要点

- 主结构:`_run_step1_producer` 顺序 `_load_raw_day -> run_step1_pipeline -> materialize_step2_scope -> enqueue`;`_run_step25_consumer` 顺序 `run_profile_pipeline -> run_enrichment_pipeline -> run_maintenance_pipeline -> validation -> sentinels`。
- 同日顺序:AST 守护确保 `run_step1_pipeline()` < `materialize_step2_scope()` < queue `put()`。
- 跨日协议:producer 可以在 consumer 跑 batch N 时执行 day N+1 Step1;但 producer 在物化 day N+1 scope 前等待 batch N 的 `sentinels_done`。
- 内置哨兵:每批 `batch_validation` 后执行 enriched 单日、sliding span、step2 scope、TCL 单调四项,失败即 raise。
- 失败传播:线程共享 `PipelineState`;第一个异常写入 `first_error` 和 traceback,主线程 join 后决定 raise 或 fallback。

## 3. 验证结果

### 3.1 7 批哨兵

| batch | enriched 单日 | sliding span | step2 scope | TCL 单调 | TCL rows | vs fix5 D |
|---:|---|---|---|---|---:|---:|
| 1 | PASS(Path-A 空批) | 2025-12-01..2025-12-01 PASS | max=2025-12-01 PASS | PASS | 79,452 | -0.00% |
| 2 | PASS | 2025-12-01..2025-12-02 PASS | max=2025-12-02 PASS | PASS | 158,068 | 0.00% |
| 3 | PASS | 2025-12-01..2025-12-03 PASS | max=2025-12-03 PASS | PASS | 211,324 | +0.00% |
| 4 | PASS | 2025-12-01..2025-12-04 PASS | max=2025-12-04 PASS | PASS | 252,688 | +0.75% |
| 5 | PASS | 2025-12-01..2025-12-05 PASS | max=2025-12-05 PASS | PASS | 286,292 | -0.17% |
| 6 | PASS | 2025-12-01..2025-12-06 PASS | max=2025-12-06 PASS | PASS | 314,490 | -1.51% |
| 7 | PASS | 2025-12-01..2025-12-07 PASS | max=2025-12-07 PASS | PASS | 340,767 | -2.34% |

### 3.2 时长对账

| batch | pipelined effective T(s) | serial T(fix5 D) | speedup |
|---:|---:|---:|---:|
| 1 | 1,005.78 | 799.73 | 0.80x |
| 2 | 1,170.56 | 931.67 | 0.80x |
| 3 | 1,449.12 | 1,171.11 | 0.81x |
| 4-7 总 | 5,517.36 | 6,006.04 | 1.09x |
| 全 7 批总 | 7,946.83 | ~9,000 | 1.13x |

全局 speedup 未达 1.3x。主要原因是为了守住 `step2_batch_input` 可审计性,scope 物化被放到上一批哨兵之后;实际重叠只覆盖下一批 Step1 与上一批 Step2-5,而 Step5 后半程仍是主耗时。

### 3.3 终点 3 验收

- TCL b7 vs PG17 ±20%:340,767 在 273,168..409,752 内,PASS。
- TCL b7 vs fix5 D ±5%:340,767 在 331,475..366,367 内,PASS。
- sliding 日期范围:min=2025-12-01,max=2025-12-07,old_rows=0,future_rows=0,PASS。
- enriched 覆盖:batch 2-7 均严格单日,off_day_rows=0;batch 1 Path-A 空批沿用 fix5 D 验收口径,PASS。

### 3.4 02C 守护扩展

- 新增 `test_pipelined_runner_calls_materialize_step2_scope_after_step1`。
- `python3 -m py_compile rebuild5/tests/*.py rebuild5/scripts/run_citus_pipelined_batches.py` exit 0。
- `python3 -m pytest --version` 仍失败:`No module named pytest`。
- 用本地 monkeypatch shim 手工执行 02C 新增测试:15 个 `test_` 全过。

## 4. Runbook 落地

- `04_runbook.md`:快速命令、问题决策树、监控指标、已验证指标、历史 trail、关键代码出口。
- `reset_full_baseline.sh`:reset 全量状态并检查核心表。
- `run_single_batch.sh`:串行单批快速验证。
- `run_full_pipelined.sh`:全 7 批 pipelined 后台启动,默认带 fallback。
- `run_full_serial.sh`:全 7 批串行 fallback。
- `sentinels.sh`:按 batch_id 跑 4 哨兵;batch 7 实测 PASS。
- `endpoint_check.sh`:终点 4 项检查;实测 PASS。

## 5. 已知限制 / 未做

- speedup=1.13x,低于 1.3x 目标。为守住数据一致性,未采用 per-day `step2_batch_input` 替换 `rb5.step2_batch_input` 的侵入式方案。
- `sentinels.sh <batch_id>` 在 pipelined 运行中应由 runner 内置 gate 或紧贴 batch 完成时运行;若 pipeline 已推进到下一天 scope,旧 batch 的 step2 scope 检查不再有意义。
- `pytest` 未安装,未运行真实 pytest;已用 `py_compile` 和手工调用覆盖新增 15 个静态测试。
- 后台 `nohup` 在当前 Codex exec 环境两次无日志退出;最终使用持久 exec 会话完成长跑。runbook 仍保留 `nohup`,适合用户 shell。

## 6. fix6_optim 总账

- 01 收尾:head=4b23cd0。
- 02A 审计:P0=0/P1=7/P2=6。
- 02B 重构:7 caller 迁移,新增 Citus-safe helper。
- 02C 测试:5 文件 14 test_,覆盖 fix5 4 根因。
- 03 加速 + runbook:新增 pipelined runner + 1 个守护测试,全 7 批 T=7,946.83s,speedup=1.13x,TCL b7 -2.34% vs fix5 D。
