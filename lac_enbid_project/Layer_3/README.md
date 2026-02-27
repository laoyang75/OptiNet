# Layer_3（规划）：基站（ENBID）库 → 基站 GPS → 按基站修正与补齐

本目录为 Layer_3 的工作区（中文为主，必要时括号补充英文）。

入口（按顺序读，v3）：

1) `lac_enbid_project/Layer_3/Layer_3_任务理解与口径对齐_v3.md`  
2) `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md`（含 Gate-0：COMMENT 双语覆盖硬验收）  
3) `lac_enbid_project/Layer_3/Layer_3_Data_Dictionary_v3.md`（口径一致性修订版，逐字段仍以 v2 为底稿）  
4) `lac_enbid_project/Layer_3/Layer_3_验收报告模板_v3.md`（修复 Step32 不吞 WARN；Step34 口径统一）
5) `lac_enbid_project/Layer_3/Layer_3_Technical_Manual.md`（工程实施手册：目的/口径/每步做什么）

历史版本（保留，便于对照）：

- `lac_enbid_project/Layer_3/archive/Layer_3_任务理解与口径对齐_v2.md`
- `lac_enbid_project/Layer_3/archive/Layer_3_执行计划_RUNBOOK_v2.md`
- `lac_enbid_project/Layer_3/archive/Layer_3_Data_Dictionary_v2.md`
- `lac_enbid_project/Layer_3/archive/Layer_3_验收报告模板_v2.md`

补充：
- `lac_enbid_project/Layer_3/notes/`：性能评估、任务单、草案等非主流程文件
- `lac_enbid_project/Layer_3/archive/`：v1/v2 历史版本归档

Layer_3 的目标不是再做“统计建库”，而是把 Layer_2 已经得到的**严格过滤后的可信集合**，进一步提升到“可用于画像/建模”的数据资产：

1) **构建基站（ENBID / gNB）库（基站主库）**：把 `cell_id_dec` 归并到 `bs_id`（基站）维度，产出站级索引与质量字段，并标记是否存在“多运营商共建/共用”。  
2) **为基站计算可信 GPS**：从 Layer_2 的可信样本中聚合得到基站中心点（可用中位数/鲁棒统计），并计算离散度（用于判断 GPS 是否可信）。  
3) **按基站修正与补齐**：对所有 `cell_id` 有值但 GPS 缺失/漂移（不准）的记录，优先使用基站 GPS 进行修正；并在必要时对“单样本 cell（只有一条数据）”进行降权/标记。  
4) **补齐信号参数（若源数据存在）**：对缺少信号强度等字段的记录，按“同 cell 最近时间”补齐；若同 cell 无可用值，再回退到“同基站最近时间/基站统计值”补齐，并记录补齐来源。

说明：`lac_enbid_project/Layer_2/未来三大步骤_接口与字段说明.md` 中的“基站主库（Master_BS_Library）/最终主库（Final_Master_DB）”与本层方向一致；但本项目当前阶段已在 Layer_2 完成严格过滤（你明确“最严格过滤已实现”），因此 Layer_3 将以“基站库 + GPS 修正/补齐 + 信号补齐”为主线推进。

SQL 入口（按顺序执行）：

- `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`
- `lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql`
- `lac_enbid_project/Layer_3/sql/32_step32_compare.sql`
- `lac_enbid_project/Layer_3/sql/33_step33_signal_fill_simple.sql`
- `lac_enbid_project/Layer_3/sql/34_step34_signal_compare.sql`
- `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`
