# Layer_5 执行计划 RUNBOOK v1（2025-12-26）

目标：把 Layer_4 的超大明细库压缩成 LAC/BS/CELL 三套“一行一对象”的画像表，用于后续新数据的初步筛选与质量控制。

输入（必须存在）：

- `public."Y_codex_Layer4_Final_Cell_Library"`

输出（固定命名）：

- Step50：`public."Y_codex_Layer5_Lac_Profile"`
- Step51：`public."Y_codex_Layer5_BS_Profile"`
- Step52：`public."Y_codex_Layer5_Cell_Profile"`
- Step99（可选）：DB COMMENT

字段说明（独立文件）：

- `lac_enbid_project/Layer_5/tables/Y_codex_Layer5_Lac_Profile_字段说明.md`
- `lac_enbid_project/Layer_5/tables/Y_codex_Layer5_BS_Profile_字段说明.md`
- `lac_enbid_project/Layer_5/tables/Y_codex_Layer5_Cell_Profile_字段说明.md`

执行顺序（必须）：

1. `lac_enbid_project/Layer_5/sql/50_step50_lac_profile.sql`
2. `lac_enbid_project/Layer_5/sql/51_step51_bs_profile.sql`
3. `lac_enbid_project/Layer_5/sql/52_step52_cell_profile.sql`
4. （可选）`lac_enbid_project/Layer_5/sql/99_layer5_comments.sql`

验收要点（建议每次跑完检查）：

1) 三张画像表均生成且主键无重复  
2) 三张画像表的统计口径一致（tech/operator/cell_id>0 等）  
3) GPS 范围字段可解释：点数足够时 p50/p90/max 呈合理分布；点数不足时降级标记明确  
4) 可用于筛选的标记字段（例如 `is_low_sample/is_gps_unstable`）口径清晰且可追溯  
5) 信号来源统计可解释：`native_*`、`need_fill_row_cnt`、`filled_row_cnt`、`filled_by_*` 与 `filled_field_sum` 数值关系自洽（不做质量评分）  
