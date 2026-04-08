# Layer_5（LAC / BS / CELL 汇总画像库：一行一对象）

本层目标：基于 Layer_4 最终明细库 `public."Y_codex_Layer4_Final_Cell_Library"`，分别构建：

- LAC 汇总表（LAC Profile）
- BS 汇总表（BS Profile）
- CELL 汇总表（CELL Profile）

每个对象压缩成“一行”，输出其关键属性（规模、时间覆盖、GPS 范围、信号覆盖/统计、质量标记等），作为后续“新进入数据的初步筛选逻辑”的依据与底座。

本轮约束：

- 信号暂不做质量评分（需要独立加权公式）；仅输出 `sig_*_final` 覆盖统计 + “原生 vs 补齐来源”统计（补齐来源=同 Cell 时间最近 / 同 BS 下 top cell 时间最近）。

入口（按顺序）：

1) `lac_enbid_project/Layer_5/Layer_5_执行计划_RUNBOOK_v1.md`
2) `lac_enbid_project/Layer_5/Layer_5_Technical_Manual.md`

SQL（按顺序执行）：

- `lac_enbid_project/Layer_5/sql/50_step50_lac_profile.sql`
- `lac_enbid_project/Layer_5/sql/51_step51_bs_profile.sql`
- `lac_enbid_project/Layer_5/sql/52_step52_cell_profile.sql`
- `lac_enbid_project/Layer_5/sql/99_layer5_comments.sql`（可选）

字段说明（独立文件，便于逐个修改）：

- `lac_enbid_project/Layer_5/tables/Y_codex_Layer5_Lac_Profile_字段说明.md`
- `lac_enbid_project/Layer_5/tables/Y_codex_Layer5_BS_Profile_字段说明.md`
- `lac_enbid_project/Layer_5/tables/Y_codex_Layer5_Cell_Profile_字段说明.md`

本层当前默认口径（可在 SQL 顶部 params 调整）：

- 仅 `tech IN ('4G','5G')`
- 仅 `{46000,46001,46011,46015,46020}`
- GPS 使用 `lon_final/lat_final`（Layer_4 已按 BS 回填/止损）
