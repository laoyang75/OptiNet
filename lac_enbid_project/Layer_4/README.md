# Layer_4（按 BS 纠偏 GPS → 补齐 cell 信号 → 产出最终 cell_id 明细库 + 对比评估）

本目录为 Layer_4 的工作区（中文为主，必要时括号补充英文）。

入口（按顺序读，v1）：

1) `lac_enbid_project/Layer_4/Layer_4_执行计划_RUNBOOK_v1.md`（含执行顺序、指标汇总与对比口径）
2) `lac_enbid_project/Layer_4/Layer_4_Technical_Manual.md`（工程实施手册：流程图 + 每步目的 + 阈值口径）

SQL 入口（按顺序执行）：

- `lac_enbid_project/Layer_4/sql/40_step40_cell_gps_filter_fill.sql`
- `lac_enbid_project/Layer_4/sql/41_step41_cell_signal_fill.sql`
- `lac_enbid_project/Layer_4/sql/42_step42_compare.sql`
- `lac_enbid_project/Layer_4/sql/43_step43_merge_metrics.sql`（可选：汇总 shard 指标 + rollup）
- `lac_enbid_project/Layer_4/sql/99_layer4_comments.sql`（可选：COMMENT 闭环）

推荐：全量按 shard 并行执行（含 Step42/43）：

- `lac_enbid_project/Layer_4/sql/run_layer4_sharded_32.sh`

MCP/DBHub 冒烟（说明）：

- DBHub 的 `execute_sql` 可能不支持 `DO $$ ... $$` 这类 dollar-quote 块；如需用 MCP 做快速验证，请使用 `lac_enbid_project/Layer_4/sql/mcp_smoke/40_step40_cell_gps_filter_fill__mcp_smoke.sql` 等无 DO 版本（固定输出到 `__MCP_SMOKE` 表）。

本层的目标：

1) 基于 Layer_3 的 **可信 BS 库**，对 `public."Y_codex_Layer0_Lac"` 的 GPS 做“按 BS 过滤 + 按 BS 回填”（严重碰撞桶不回填）。
2) 对信号字段做二阶段补齐：
   - 优先：同 cell_id 时间最近记录
   - 退化：同 BS 下数据量最多的 cell_id（donor）时间最近记录
3) 输出最终 **补齐后的 cell_id 明细库**，并与原始库做条数/GPS/信号的对比评估（含每步补齐比例）。

补充说明：

- Step41 输出 `sig_*_final`（不覆盖原始 `sig_*`），并记录 `signal_fill_source/signal_donor_seq_id` 便于追溯。
- 当 `codex.shard_count>1` 时，Step42 会自动对 Final shard 表做 `UNION ALL` 汇总，无需先手工合并。
