# Layer_3 Restart（从这里继续）

更新时间：2025-12-25

本文件用于“保存进度 + 一键恢复上下文”。由于会话窗口过长，重启后请直接从本文件开始对齐。

---

## 1) 当前状态（本期已完成）

### 主链路（已跑完）

已按 `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md` 跑完并交付：

- Step30：`public."Y_codex_Layer3_Step30_Master_BS_Library"`
- Step31：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`
- Step32：`public."Y_codex_Layer3_Step32_Compare"`
- Step33：`public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`
- Step34：`public."Y_codex_Layer3_Step34_Signal_Compare"`
- Step99：`lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`（Gate-0 COMMENT 闭环）

本期性能结论：Step30 已从“卡一周”收敛到“<30min 级别”（分片并发方案已稳定）。

### 最终交付表（后续任务的依赖项）

已生成并作为后续 cell 补数/画像的输入：

- BS 画像库：`public."Y_codex_Layer3_Final_BS_Profile"`
- cell → BS 映射：`public."Y_codex_Layer3_Final_Cell_BS_Map"`
- 交付清单说明：`lac_enbid_project/Layer_3/reports/Layer_3_Delivery_Final_Tables.md`

---

## 2) 重启后两条路线（明确优先级）

### A) 主线（主要方向，优先推进）

目标：尽快完成 **BS 画像任务** → 启动 **依赖 BS 的 cell 库补数** → **cell 库画像** → 完成“原始数据 → 新结构”的最终流程闭环；然后进入 Layer_4 构建 cell 相关内容。

依赖基线：

- 口径/流程手册：`lac_enbid_project/Layer_3/Layer_3_Technical_Manual.md`
- BS 画像库：`public."Y_codex_Layer3_Final_BS_Profile"`
- cell→BS 映射：`public."Y_codex_Layer3_Final_Cell_BS_Map"`

重启后主线要交付的“阶段性结果”（作为 Layer_4 前置）：

1) BS 画像字段清单与口径稳定（可依赖、可解释）
2) 以 BS 为依赖的 cell 补数机制落地（保留来源标记；不要求极致精度，但要求可解释/可复跑）
3) cell 画像库落地并可作为 Layer_4 输入
4) 全流程 RUNBOOK 化（从原始数据到新结构的端到端步骤与产物清单）

### B) 附加线（次要方向：异常数据进一步研究）

现状：本期“明确异常”只收敛到 **375 个 scoped cell**（你口径：异常桶命中后得到），且已经有明确方向（动态/移动 cell）。

结论：过滤动态 cell 后剩余异常不会很多，因此该方向不作为主线推进，仅作为“异常剥离 + 再评估”的附加处理。

---

## 3) 附加线材料（28 天数据验证已完成）

### 3.1 375 个异常 scoped cell 清单（已准备）

- `lac_enbid_project/Layer_3/reports/Step35_abnormal_cell_scoped_list_375.csv`

说明：scoped 粒度为 `(operator_id_raw, tech_norm, cell_id_dec)`；同一个 `cell_id_dec` 可能在不同 operator/tech 下重复出现是正常的。

### 3.2 28 天 Excel 验证 RUNBOOK（已准备）

- `lac_enbid_project/Layer_3/notes/Step35_动态Cell_28天数据验证_RUNBOOK.md`

你在服务器侧准备的数据要求：

- Excel 格式与示例 `lac_enbid_project/Layer_3/20251225_cellid_28.xlsx` 一致（原始明细，不走 Layer_3 清洗表）
- 至少包含：`ts, opt_id, cell_id, dynamic_network_type, lgt, ltt`

已完成验证（基于你提供的 28 天明细表 `public.cell_id_375_28d_data_20251225`）：

- 结果表：`public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"`
- 命中动态/移动 scoped cell：7
- 报告：`lac_enbid_project/Layer_3/reports/Step35_dynamic_cell_validation_28d_20251225.md`

（后续如需复跑，可直接执行：`lac_enbid_project/Layer_3/sql/35_step35_dynamic_cell_28d_validation.sql`）

原计划（保留）：

- 多质心检测 + “时间/质心相关性（周期/切换）”判定
- 命中则标记动态 cell / 动态 BS（用于把这类异常从混桶样本中剥离）
- 排除动态 cell 后，再看剩余异常是否需要引入其它参数继续治理

（可选）SQL 落点（用于库内剥离/对比，但 28 天验证不依赖它）：

- `lac_enbid_project/Layer_3/sql/35_step35_dynamic_cell_bs_detection.sql`

---

## 4) 可选：清理分片残留表（谨慎）

如果数据库中存在大量 Step30 分片残留表，且你确认后续不需要“仅 merge 重跑”，可考虑清理（先盘点再删，避免误删）。

盘点示例：

```sql
SELECT tablename
FROM pg_tables
WHERE schemaname='public' AND tablename LIKE 'Y_codex_Layer3_Step30_%__shard_%'
ORDER BY tablename;
```
