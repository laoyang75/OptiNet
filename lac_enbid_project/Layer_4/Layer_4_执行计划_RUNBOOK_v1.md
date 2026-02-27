# Layer_4 执行计划 RUNBOOK v1（2025-12-25）

目标：在 `public."Y_codex_Layer0_Lac"` 上构建“补齐后的 cell_id 明细库”，并输出分步补齐比例与最终对比结果。

依赖输入（必须存在）：

- 原始明细库：`public."Y_codex_Layer0_Lac"`
- BS 画像库（Layer_3 产物）：`public."Y_codex_Layer3_Step30_Master_BS_Library"`

输出对象（固定命名）：

- Step40：`public."Y_codex_Layer4_Step40_Cell_Gps_Filter_Fill"`（GPS 过滤+按 BS 回填后的明细）
- Step40 指标：`public."Y_codex_Layer4_Step40_Gps_Metrics"`
- Step41（最终库）：`public."Y_codex_Layer4_Final_Cell_Library"`（信号补齐后的最终明细库）
- Step41 指标：`public."Y_codex_Layer4_Step41_Signal_Metrics"`
- Step42：`public."Y_codex_Layer4_Step42_Compare_Summary"`（最终库 vs 原始库对比汇总）
- Step43（可选）：`public."Y_codex_Layer4_Step40_Gps_Metrics_All"` / `public."Y_codex_Layer4_Step41_Signal_Metrics_All"`（汇总 shard 指标 + rollup）

说明（重要）：

- 本层按 **BS（bs_shard_key=tech_norm|bs_id_final）** 进行处理与 sharding（效率优先）；`wuli_fentong_bs_key` 仍用于与 Layer_3 BS 库精确关联（含 lac 维度）。
- 严重碰撞桶：回填 GPS（`Augmented_from_BS_SevereCollision`），并保留严重碰撞判定与原因用于强标注。
- 城市阈值（当前默认）：
  - 4G：`dist_threshold_m = 1000`
  - 5G：`dist_threshold_m = 500`
- 未来扩展：阈值应由 `lac` 决定（非城市 lac 允许更大阈值）；本轮只做参数预留与文档标注，不改业务口径。

---

## 0) 会话参数（可选）

脚本内均读取以下 session setting（不设置则用默认值）：

- `SET codex.is_smoke = 'false'|'true'`（冒烟切片）
- `SET codex.smoke_date = 'YYYY-MM-DD'`（冒烟日期）
- `SET codex.smoke_operator_id_raw = '46000'`（冒烟运营商）
- `SET codex.shard_count = 'N'`（按 BS 桶分片；默认 1）
- `SET codex.shard_id = 'k'`（当前分片 id；默认 0）

> 当 `shard_count>1` 时，每个 Step 会输出到 shard 表（表名带 `__shard_XX` 后缀）；需要你在所有 shard 跑完后，再执行一次合并（见各 Step SQL 文件末尾说明）。
>
> 备注：Step42 已支持在 `shard_count>1` 场景下自动 `UNION ALL` 汇总 Final shard 表，因此“不合并也能出对比汇总”。如果你确实需要一张物理合并表，可后续再补充 merge 脚本。

---

## 1) 执行顺序（必须）

1. `lac_enbid_project/Layer_4/sql/40_step40_cell_gps_filter_fill.sql`
2. `lac_enbid_project/Layer_4/sql/41_step41_cell_signal_fill.sql`
3. `lac_enbid_project/Layer_4/sql/42_step42_compare.sql`
4. （可选）`lac_enbid_project/Layer_4/sql/43_step43_merge_metrics.sql`
5. （可选）`lac_enbid_project/Layer_4/sql/99_layer4_comments.sql`

推荐执行方式（全量按 shard 并行）：

- `lac_enbid_project/Layer_4/sql/run_layer4_sharded_32.sh`

MCP 冒烟（可选）：

- 若你用的是 DBHub MCP 的 `execute_sql`，可能无法执行包含 `DO $$...$$` 的脚本；可改用 `lac_enbid_project/Layer_4/sql/mcp_smoke/40_step40_cell_gps_filter_fill__mcp_smoke.sql` 等无 DO 版本（输出到 `__MCP_SMOKE` 表）做快速验证。

---

## 2) 验收要点（建议每次跑完检查）

1) 产物表存在：Step40/Final/Step42 均已生成  
2) 行数（同一过滤口径下）一致：Final 与 Step40 行数一致  
3) GPS：过滤命中与回填比例合理（查看 Step40 指标表）  
4) 信号：cell-nearest 与 bs-donor 的补齐比例可解释（查看 Step41 指标表；`need_fill_row_cnt` 表示“至少 1 个信号字段为空”的行数，通常会很接近总行数，建议结合 `filled_field_sum/missing_field_before_sum` 看补齐效果）  
5) 对比：Step42 汇总表能回答“条数/GPS/信号”三类指标的 before/after 差异  
