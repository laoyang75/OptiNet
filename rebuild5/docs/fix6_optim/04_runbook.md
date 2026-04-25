# OptiNet rebuild5 Citus 集群 — 标准操作 Runbook

> 适用范围:rebuild5 Citus 集群(192.168.200.217:5488/yangca)的"改 -> 跑 -> 验"研究循环。
> 撰写时间:2026-04-25(fix6_optim 终点阶段)。
> 撰写依据:fix5 五阶段诊断 + fix6_optim 三阶段加速,实战通过。

## 1. 快速参考(命令清单)

### 1.1 reset 全 7 批基线

```bash
bash rebuild5/scripts/runbook/reset_full_baseline.sh
```

### 1.2 跑 1 day 单批(快速验证代码改动)

```bash
bash rebuild5/scripts/runbook/run_single_batch.sh 2025-12-01 1
```

### 1.3 跑全 7 批(pipelined 加速)

```bash
bash rebuild5/scripts/runbook/run_full_pipelined.sh
```

### 1.4 跑全 7 批(串行 fallback,稳但慢)

```bash
bash rebuild5/scripts/runbook/run_full_serial.sh
```

### 1.5 每批跑完打 4 哨兵

```bash
bash rebuild5/scripts/runbook/sentinels.sh <batch_id>
```

### 1.6 终点验收(batch 7 完成后)

```bash
bash rebuild5/scripts/runbook/endpoint_check.sh
```

## 2. 决策树:遇到问题怎么办

### 2.1 哨兵 #1 enriched 跨日

原因:scope materialization 失效。处理:检查 runner 是否在同一 day 内严格执行 `run_step1_pipeline -> materialize_step2_scope -> run_profile_pipeline`。

### 2.2 sliding_window 含 2023/2024

原因:trim 被关或 Step2 scope 放大。处理:确认没有 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM`;检查 `cell_sliding_window` 的 min/max 和 `rb5.step2_batch_input` max day。

### 2.3 TCL batch N 行数 <= batch N-1

原因:input 冻结或 publish 未写入。处理:停止当前 run,reset 后从 batch 1 重跑;不要在 donor 链污染后继续推进。

### 2.4 publish_bs/cell/lac 撞 "could not create distributed plan"

原因:高风险 caller 走回 `core.database.execute(..., params)`。处理:跑 02C 守护 `test_high_risk_callers_use_unified_entry`,漏迁 caller 改回 `execute_distributed_insert`。

### 2.5 pipelined 跑挂

原因:runner race、Citus lock、connection 或代码错误。处理:若挂点没有 partial 输出,用串行 `--start-batch-id N --skip-reset` 接;若已有 partial 输出,先 reset 全量状态再跑。

### 2.6 GitHub HTTPS push 撞 SSL_ERROR_SYSCALL

原因:网络瞬时抖动。处理:等 60s 重试一次。本地 commit 不会丢失;再失败标 `push pending`。

## 3. 监控指标

### 3.1 进程层

- `tail -f /tmp/fix6_*.log`:runner 当前 step。
- `ps -p $(cat /tmp/fix6_03.pid)`:进程存活。
- pipelined 关注 JSON 事件:`step2_scope_materialized`,`batch_validation`,`batch_sentinels`,`pipelined_complete`。

### 3.2 数据库层

- `pg_stat_activity WHERE datname='yangca'`:定位 stuck SQL。
- `rb5_meta.step1_run_stats` / `step2_run_stats` / `step3_run_stats` / `step4_run_stats` / `step5_run_stats`:确认 step 完成情况。
- `rb5_bench.notes ORDER BY created_at DESC`:跨阶段决策 trail。

### 3.3 业务层

- TCL 单调增长:
  ```sql
  SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library GROUP BY 1 ORDER BY 1;
  ```
- sliding 范围:
  ```sql
  SELECT MIN(event_time_std)::date, MAX(event_time_std)::date FROM rb5.cell_sliding_window;
  ```
- enriched 单日:
  ```sql
  SELECT batch_id, MIN(event_time_std)::date, MAX(event_time_std)::date, COUNT(*)
  FROM rb5.enriched_records GROUP BY 1 ORDER BY 1;
  ```

## 4. 已验证的基线指标(2026-04-25)

| 指标 | PG17 黄金 | Citus 串行(fix5 D) | Citus pipelined(fix6 03) |
|---|---:|---:|---:|
| TCL b7 总量 | 341,460 | 348,921(+2.19%) | 340,767(-0.20% vs PG17;-2.34% vs serial) |
| stable | 337,480 | 344,339 | 336,804 |
| dual_cluster | 442 | 445 | 465 |
| 7 批总时长 | n/a | ~150 min | 132.45 min |

## 5. 历史诊断 trail

- fix5 A 诊断:`rebuild5/docs/fix5/01_quality_diagnosis.md`
- fix5 B 审计:`rebuild5/docs/fix5/02_agent_change_audit.md`
- fix5 C 修复:`rebuild5/docs/fix5/04_code_fix_report.md`
- fix5 D 重跑:`rebuild5/docs/fix5/06_rerun_validation.md`
- fix6_optim 02A 审计:`rebuild5/docs/fix6_optim/02A_audit_report.md`
- fix6_optim 02B 重构:`rebuild5/docs/fix6_optim/02B_refactor_report.md`
- fix6_optim 02C 测试:`rebuild5/docs/fix6_optim/02C_test_report.md`
- fix6_optim 03 加速:`rebuild5/docs/fix6_optim/03_pipelined_report.md`

## 6. 关键代码出口

| 关注点 | 文件 |
|---|---|
| Citus 兼容 INSERT 入口 | `rebuild5/backend/app/core/citus_compat.py::execute_distributed_insert` |
| 串行 runner | `rebuild5/scripts/run_citus_serial_batches.py` |
| pipelined runner | `rebuild5/scripts/run_citus_pipelined_batches.py` |
| reset SQL | `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql` |
| scope 物化 | `rebuild5/scripts/run_daily_increment_batch_loop.py::materialize_step2_scope` |
| runbook scripts | `rebuild5/scripts/runbook/*.sh` |
