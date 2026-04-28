# fix5 — Citus 迁移可行性 + 4 根因修复(已收档)

> ⚠️ **已收档,这是历史 trail**。当前项目状态见上层 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)。
> 这个目录里的 prompt / report 不再 active 维护,但保留作历史决策依据。

## 元目标(当时)

把 rebuild5 业务从单机 PG17 迁到 Citus 14 + PG17 集群,跑通全 7 批数据。

## 阶段交付(A → D)

| 阶段 | 产出 | 角色 |
|---|---|---|
| A 诊断 | [`01_quality_diagnosis.md`](./01_quality_diagnosis.md) | Claude 诊断 4 根因 |
| B 审计 | [`02_agent_change_audit.md`](./02_agent_change_audit.md) | agent 审计 working tree,回滚 B 类 |
| C 修复 | [`04_code_fix_report.md`](./04_code_fix_report.md) + [`03_fix_and_optimize_prompt.md`](./03_fix_and_optimize_prompt.md) | agent 改代码 + ALTER SYSTEM |
| D 重跑 | [`06_rerun_validation.md`](./06_rerun_validation.md) + [`05_rerun_prompt.md`](./05_rerun_prompt.md) | agent 跑全 7 批 + 验收 |

## 4 根因修复(给未来人:这些根因如果再次出现,看这里)

| 根因 | 现象 | 修复 |
|---|---|---|
| **scope materialization 失效** | 跨日数据混入 enriched_records | runner 在 Step1 后调 `materialize_step2_scope(day)`,materialize_step2_scope 严格按 `event_time_std::date` 切片 |
| **sliding_window trim 关闭** | sliding_window 出现 2023/2024 时间戳 | 删除 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM=1` env;trim 严格 `WHERE event_time_std < latest_day - WINDOW_RETENTION_DAYS` |
| **distributed DELETE 用 ctid 不支持** | publish_bs/cell/lac 撞 Citus error | trim DELETE 改用 PK `(batch_id, source_row_uid, cell_id)`;不再用 `WHERE ctid IN ...` |
| **parameterized distributed plan 不支持** | INSERT...SELECT 含 CTE + params 撞 "could not create distributed plan" | publish_bs_lac.py 用 `psycopg.ClientCursor` 客户端 binding;后续 fix6_optim 抽出 `core/citus_compat.execute_distributed_insert` 统一入口 |

## 数据基线(fix5 D 时刻)

- TCL b7 = 348,921(vs PG17 黄金 341,460,+2.19%)— Citus DBSCAN 非确定性正常波动
- 全 7 批串行 wall clock ≈ 9,000s ≈ 150 min

## 后续阶段

- fix5 收档 → [`../fix6_optim/`](../fix6_optim/) 加速 + 守护
- fix6_optim 收档 → [`../loop_optim/`](../loop_optim/) 流水线 + 索引
- loop_optim 收档 → [`../upgrade/`](../upgrade/) PG18 升级
