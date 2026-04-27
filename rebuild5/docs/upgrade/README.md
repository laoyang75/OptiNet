# upgrade — PG / Citus / 扩展 升级到最新稳定版

独立任务,不属于 fix5/fix6_optim/loop_optim 任何一个。

## 元目标

升级 192.168.200.217 集群(1 coord + 4 worker)的:

1. **PostgreSQL** 升级到当前最新稳定大版本(预期 PG 18.x,agent 第一步实测当前版本再定具体目标)
2. **Citus** 升级到与新 PG 兼容的最新版
3. **扩展齐全**:PostGIS、pg_stat_statements、auto_explain,以及任何 fix5/fix6 历史用过的扩展
4. **升级后调优参数**(citus.max_intermediate_result_size / max_parallel_workers_per_gather 等)

## 边界

- ❌ 不动 backend/app 任何代码(loop_optim 已收档)
- ❌ 不动 fix5/fix6_optim/loop_optim 已交付的产物 / 报告
- ❌ 不动业务数据(rb5.* 表数据可以扔重跑,但要确保有备份)
- ✅ 升级失败可回滚到 PG17(底线)
- ✅ "实在不行重开一套"是被批准的退路(user 明确拍板)

## 协作模式(继承 fix6_optim §11/§12)

- agent 自主推进,无开跑前 ack
- 完工自动 commit + push + 写 note
- 撞 blocker 才停下来报告
- 上下游互审(本任务上游是 loop_optim 收档状态,无 prompt 互审目标)

## 当前状态

完成。生产端口 `5488` 已切到 PG18.3 / Citus 14.0-1 / PostGIS 3.6.3；老 PG17.6 集群保留在 `5487` 作 fallback。

- 最终报告:`upgrade_v2_finalize_and_tuning_report.md`
- v1 失败 trail:`upgrade_report.md`
- v2 fresh rebuild prompt:`upgrade_v2_fresh_rebuild_prompt.md`
- v2 收尾 + 调优 prompt:`upgrade_v2_finalize_and_tuning_prompt.md`
- v1 dump safety net:`/nas_vol8/upgrade/backups/dumps/yangca_full_20260426_105359.sql`

## 阶段表

| 阶段 | Prompt | 产出 | 估时 |
|---|---|---|---|
| **upgrade 主任务**(7 子阶段) | `upgrade_prompt.md` | `upgrade_report.md` + 集群升级完成 + 备份在 NAS | ~半天 ~ 1 天 |
| **upgrade v2 fresh rebuild** | `upgrade_v2_fresh_rebuild_prompt.md` | new PG18 cluster on 5491 + reset rerun trail | ~半天 |
| **upgrade v2 finalize + tuning** | `upgrade_v2_finalize_and_tuning_prompt.md` | `upgrade_v2_finalize_and_tuning_report.md` + port cutover | ~3 小时 |

v1 失败后没有删除 PG17 数据或 v1 dump。v2 使用 fresh schema + minimal data migration + reset rerun,避开 dumpall 后置 distribute 陷阱。

## 引用文档

- `rebuild5/docs/fix6_optim/04_runbook.md` —— 升级后要保证 runbook 命令仍能跑
- `rebuild5/docs/loop_optim/03_rerun_report.md` —— loop_optim 收档基线
- `rb5_bench.notes` topic LIKE `'upgrade_%'` —— 升级 trail
