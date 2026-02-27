# Layer_2（北京明细 20251201_20251207）README（人类可读版）

本目录把 Layer_0 的北京明细输入整理成一套 **可解释、可验收、可复跑、可审计** 的 Step00~Step06 流水线：

- Step00：统一标准口径字段（不改原表）
- Step01：基线统计（数据“长什么样”）
- Step02：行级绝对合规标记（不合规则不进入后续）
- Step03：有效 LAC 汇总库（聚合主表，XL）
- Step04：可信 LAC（集合筛选）
- Step05：可信映射底座 + 异常监测清单（XL）
- Step06：反哺 LAC 路 + GPS vs LAC 对比（XL）

项目重启入口见：`lac_enbid_project/restart.md`。
服务器配置与会话级调优建议见：`lac_enbid_project/服务器配置与SQL调优建议.md`。

---

## 1) 快速开始（阅读顺序 + 执行入口）

1. 先读：`README_人类可读版.md`（本文件，理解整体流程）
2. 再读：`RUNBOOK_执行手册.md`（执行顺序/对象名/冒烟模板/交接机制）
3. 执行时逐步打开：`Step00~Step06` 的说明文档（每步按 Summary Queries + 验收标准验收）

SQL 文件在：`lac_enbid_project/Layer_2/sql/`。

---

## 2) 已对齐的约束（本轮评审必须遵守）

- 命名：所有输出对象统一 `public."Y_codex_Layer2_StepXX_*"`
- 字段：列名保持英文；用 `COMMENT ON TABLE/COLUMN` 写“中文标签 + English description”
- 策略：每步先冒烟（限定 `report_date` 或 `operator_id_raw`）再全量
- 性能：PostgreSQL 15；允许在评审里提出“分区 / 增量物化 / 拆分跑”方案
- 范围：不修改业务口径，不新增复杂指标（share/top1 等）
- 暂缓：Step04/05 基于 Layer_1 研究结论的异常过滤，本轮先不实现（留插槽，后续评审补齐）

---

## 3) 一页式总览（对象流向）

```text
Layer_0（已存在）
  ├─ public."Y_codex_Layer0_Gps_base"
  └─ public."Y_codex_Layer0_Lac"

Step00 标准化视图（不改原表）
  ├─ public."Y_codex_Layer2_Step00_Gps_Std"
  └─ public."Y_codex_Layer2_Step00_Lac_Std"

Step01 基线统计（落表）
  ├─ public."Y_codex_Layer2_Step01_BaseStats_Raw"
  └─ public."Y_codex_Layer2_Step01_BaseStats_ValidCell"

Step02 合规标记（视图 + 对比表）
  ├─ public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
  └─ public."Y_codex_Layer2_Step02_Compliance_Diff"

Step03~05 建库（含 XL 聚合）
  ├─ public."Y_codex_Layer2_Step03_Lac_Stats_DB"
  ├─ public."Y_codex_Layer2_Step04_Master_Lac_Lib"
  ├─ public."Y_codex_Layer2_Step05_CellId_Stats_DB"
  └─ public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"

Step06 反哺与对比
  ├─ public."Y_codex_Layer2_Step06_L0_Lac_Filtered"（TABLE）
  └─ public."Y_codex_Layer2_Step06_GpsVsLac_Compare"
```

---

## 4) 执行顺序（按文件名）

1. `sql/00_step0_std_views.sql`
2. `sql/01_step1_base_stats.sql`
3. `sql/02_step2_compliance_mark.sql`
4. `sql/03_step3_lac_stats_db.sql`（XL）
5. `sql/04_step4_master_lac_lib.sql`
6. `sql/05_step5_cellid_stats_and_anomalies.sql`（XL）
7. `sql/06_step6_apply_mapping_and_compare.sql`（XL）
8. （可选，仅接口预埋）`sql/90_future_interfaces_ddl.sql`

执行细节、耗时等级、回滚、冒烟模板与交接机制：`RUNBOOK_执行手册.md`。

---

## 5) 运行与审计模型（你执行 SQL；我用 MCP 自检）

- 默认：你在服务器/数据库执行 SQL（尤其 L/XL），我用 MCP 做验收并更新 `RUNLOG_YYYYMMDD.md`
- 每步必须自检：至少包含 `count(*)`、主键重复检查；并按 Step 文档的 Summary Queries 抽至少 5 条结果写入 RUNLOG
- 工具注意：部分控制台/MCP 执行器会按 `;` 拆分语句，`DO $$...$$` 可能失败；遇到这种情况优先用 `psql -f`

---

## 6) 文档导航（一步一文档）

- 执行手册：`RUNBOOK_执行手册.md`
- Step00：`Step00_标准化视图说明.md`
- Step01：`Step01_基础统计说明.md`
- Step02：`Step02_合规标记说明.md`
- Step03：`Step03_有效LAC汇总库说明.md`
- Step04：`Step04_可信LAC说明.md`
- Step05：`Step05_可信映射与异常说明.md`
- Step06：`Step06_L0_Lac反哺与对比说明.md`
- 字段字典：`Data_Dictionary.md`
- 变更记录：`CHANGELOG.md`
