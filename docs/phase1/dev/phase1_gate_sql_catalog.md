# Phase1 门禁 SQL 目录（MVP）

版本：`v0.1`  
更新时间：`2026-02-26`

## 1. 入口脚本
1. 主脚本：`sql/phase1_obs/03_obs_gate_checks.sql`
2. 观测构建：`sql/phase1_obs/02_obs_build.sql`（会把门禁结果写入 `Y_codex_obs_gate_result`）

## 2. 门禁清单

### G01 行数守恒
- 目标：Step40 与 Final 行数一致。
- SQL：`03_obs_gate_checks.sql` 的 `B) Row conservation`。
- 通过条件：`diff_cnt = 0`。

### G02 指标对账：Not_Filled
- 目标：`Step40_Gps_Metrics_All.gps_not_filled_cnt` 与事实一致。
- SQL：`03_obs_gate_checks.sql` 的 `C) Reconciliation`。
- 通过条件：`diff_not_filled = 0`。

### G03 指标对账：Severe Fill
- 目标：`gps_fill_from_bs_severe_collision_cnt` 与事实一致。
- SQL：`03_obs_gate_checks.sql` 的 `C) Reconciliation`。
- 通过条件：`diff_severe_fill = 0`。

### G04 指标对账：bs_id_lt_256
- 目标：`bs_id_lt_256_row_cnt` 与事实一致。
- SQL：`03_obs_gate_checks.sql` 的 `C) Reconciliation`。
- 通过条件：`diff_bs_id_lt_256 = 0`。

### G05 字段存在性（Layer5 中文底表）
- 目标：BS/CELL 都存在四个异常契约字段。
- SQL：`03_obs_gate_checks.sql` 的 `D) Layer5 contract field existence`。
- 通过条件：返回 8 行（2 表 x 4 字段）。

### G06 无效 LAC 泄漏
- 目标：L5 三张画像无 sentinel/无效 LAC。
- SQL：`03_obs_gate_checks.sql` 的 `E) Invalid LAC leakage`。
- 通过条件：`l5_lac_invalid = l5_bs_invalid = l5_cell_invalid = 0`。

### G07 标签闭环（碰撞/严重/动态）
- 目标：Layer4 -> Layer5 对象级闭环一致。
- SQL：`03_obs_gate_checks.sql` 的 `F) Label closure`。
- 通过条件：
  1. `l4_collision_bs = l5_collision_bs`
  2. `l4_severe_cell = l5_severe_cell`
  3. `l4_dynamic_cell_filtered = l5_dynamic_cell`

## 3. 口径说明
1. `dynamic` 门禁采用 `Step52` 同口径过滤（运营商、制式、有效键），避免全量口径误差引发误报。
2. 对账门禁以 `shard_id=-1` 的 `_All` 行作为最终汇总口径。

## 4. 自动化建议
1. 每次完成 Layer4/Layer5 关键脚本后执行：
  `01_obs_ddl.sql`（首次） -> `02_obs_build.sql` -> `03_obs_gate_checks.sql`。
2. 推荐直接使用脚本：
  `scripts/run_phase1_obs_pipeline.sh`（自动落日志与汇总报告）。
3. 若需二次复核，使用：
  `scripts/check_phase1_obs_consistency.sh [run_id]`（输出一致性报告）。
4. CI 或定时任务读取 `Y_codex_obs_gate_result.pass_flag`，出现 `false` 即阻断发布。
