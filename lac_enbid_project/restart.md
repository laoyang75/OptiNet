# Restart 记录（`lac_enbid_project`）

最后更新：2025-12-15

这份文件是“回到现场”的入口：记录当前进度、必须遵守的协作方式、以及下次从哪里开始继续。

---

## 1. 重启时我（assistant）该怎么做（强制流程）

当你说“读 restart 并从 Step00 开始”，我必须按以下顺序推进：

1) 我先读文档（不直接改 SQL）
- 项目根：`lac_enbid_project/README.md`
- 重启入口：`lac_enbid_project/restart.md`
- Layer_2：`lac_enbid_project/Layer_2/README_人类可读版.md` → `lac_enbid_project/Layer_2/RUNBOOK_执行手册.md` → Step00~Step06 说明

2) 每个 Step 的“解释 + 问答确认”（你确认后才动手）
- 我先解释：目的/意图、输入输出对象、核心口径、关键实现、性能与可重跑、自检与验收点
- 我再提问：你确认口径/依赖/命名/索引/拆分跑策略是否满足设计
- 你明确回复“通过 / 按修改通过”后，我才会修改该 Step SQL，并用 MCP 做自检与写 RUNLOG

3) 对 L/XL SQL 的“人工执行交接机制”
- 真正执行前，我必须给“交接卡片”（为什么慢/拆分方案/前置索引/你需要回传的最小结果）
- 你回传最小结果后，我才进入下一步

---

## 1.2 本轮重启的“成功/失败”判定（你下次回来怎么推进）

你下次说“继续/重跑”，默认分两种情况：

1) **重跑顺利（无 SQL 报错，产出表齐全）**
- 我只做“验收与解释”：检查 Gate/一致性/关键汇总与 TopN 样本，更新 `RUNLOG`，并把报告写清楚（你只需要看结论和少量抽样）。

2) **重跑不顺利（中间 SQL 报错/锁/产出缺失）**
- 我只做“定位与修复”：明确哪一步报错、是否锁等待、是哪类口径/字段/性能问题；修复对应 SQL 后给你最小重跑建议（避免全量反复浪费时间）。

说明：Layer_3 的 `lac_enbid_project/Layer_3/sql/00_layer3_placeholders.sql` 是**纯占位 no-op**，不在执行链路中，不影响重跑与验收。

---

## 1.1 服务器配置与会话级调优（执行 SQL 前必读）

性能相关的“机器上限 + 推荐会话级 SET 参数”已固定记录在：

- `lac_enbid_project/服务器配置与SQL调优建议.md`

原则：

- 每次跑 L/XL SQL 前，建议先执行文档里的推荐 `SET`（或使用已内嵌 `SET` 的新版 SQL 文件）。
- 对“产出超大明细表”的 CTAS，脚本可能会覆盖部分推荐值（例如关闭并行、关闭 merge join）来避免 `temp_bytes` 爆炸或 `MessageQueueSend` 堵塞。

---

## 2. Layer_2（北京明细 20251201_20251207）当前状态

### 2.1 已完成事项（checkpoint）

- PostgreSQL：15
- 执行策略：你选 **B（人工执行 SQL）**；我用 MCP 做自检与审计记录
- 已完成：旧命名对象迁移为新命名 + 清理 smoke 临时对象（已通过 MCP 验收）
- 本轮不做：Step04/05 基于 Layer_1 的异常过滤（待后续评审迭代再落地）

### 2.2 Layer_2 输出对象命名规范（已就位）

schema 固定为 `public`；输出对象统一为 `Y_codex_Layer2_StepXX_*`：

- Step00：`public."Y_codex_Layer2_Step00_Gps_Std"`（VIEW）、`public."Y_codex_Layer2_Step00_Lac_Std"`（VIEW）
- Step01：`public."Y_codex_Layer2_Step01_BaseStats_Raw"`（TABLE）、`public."Y_codex_Layer2_Step01_BaseStats_ValidCell"`（TABLE）
- Step02：`public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（VIEW）、`public."Y_codex_Layer2_Step02_Compliance_Diff"`（TABLE）
- Step03：`public."Y_codex_Layer2_Step03_Lac_Stats_DB"`（TABLE）
- Step04：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（TABLE）
- Step05：`public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（TABLE）、`public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`（VIEW）
- Step06：`public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE）、`public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`（TABLE）

可审计运行记录：
- `lac_enbid_project/Layer_2/RUNLOG_20251215.md`

补充：给工程人员的“实施手册”（推荐从这里理解整体）
- `lac_enbid_project/Layer_2/Layer_2_Technical_Manual.md`

### 2.3 工具注意事项（必须记住）

- 一些 SQL 控制台/工具（含部分 MCP 执行器）会按 `;` 拆分语句，导致 `DO $$ ... $$` 块执行失败。
  - 推荐：用 `psql -f` 执行整文件
  - 或：改为“先列清单，再逐条 `DROP/ALTER`/`CREATE`”执行

### 2.4 Layer_2 快速验收（重启时先跑一遍）

```sql
-- smoke/旧命名应为 0，新命名应存在
select count(*) as smoke_objects
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relname ilike '%smoke%';

select count(*) as legacy_objects
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public'
  and (c.relname ilike 'v_layer2_%' or c.relname ilike 'd_step%' or c.relname ilike 'rpt_step%' or c.relname='anomaly_cell_multi_lac');

select c.relkind, c.relname
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relname ilike 'y_codex_layer2_step%'
order by c.relname;
```

---

## 3. Layer_2 下一轮：从 Step00 开始逐步修订

### 3.1 必读顺序

1) `lac_enbid_project/Layer_2/README_人类可读版.md`  
2) `lac_enbid_project/Layer_2/RUNBOOK_执行手册.md`  
3) `lac_enbid_project/Layer_2/Layer_2_Technical_Manual.md`（工程实施手册：目的/口径/每步做什么）
3) Step00~Step06 说明（每步都按 Summary Queries 做验收）

### 3.2 执行顺序（按 RUNBOOK）

1) Step00：`lac_enbid_project/Layer_2/sql/00_step0_std_views.sql`  
2) Step01：`lac_enbid_project/Layer_2/sql/01_step1_base_stats.sql`  
3) Step02：`lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql`  
4) Step03（XL）：`lac_enbid_project/Layer_2/sql/03_step3_lac_stats_db.sql`  
5) Step04：`lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql`  
6) Step05（XL）：`lac_enbid_project/Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql`  
7) Step06（XL）：`lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`  

### 3.3 本轮已确认的修订约束（不再争议）

- 命名：所有输出对象保持 `public."Y_codex_Layer2_StepXX_*"`
- 字段：不强制中文列名；用 `COMMENT ON TABLE/COLUMN` 做“中文标签 + English description”
- 重跑：每个 Step SQL 内嵌必要索引（`CREATE INDEX IF NOT EXISTS`），避免分散到新文件导致遗漏
- 性能：允许在评审中提出“分区 / 增量物化 / 拆分跑”方案（不默认一次性实现）
- 口径：不修改业务口径，不新增复杂指标（share/top1 等）

---

## 4. Layer_0（北京明细）checkpoint（供 Layer_2 输入复核）

### 4.1 源表（北京明细 20251201_20251207）

- GPS 源：`public."网优项目_gps定位北京明细数据_20251201_20251207"`
- LAC 源：`public."网优项目_lac定位北京明细数据_20251201_20251207"`

### 4.2 Layer_0 最终输入表（Layer_2 依赖）

- `public."Y_codex_Layer0_Gps_base"`
- `public."Y_codex_Layer0_Lac"`

### 4.3 解析口径与实现落地（参考文档）

解析规则与统计口径以以下文件为准（restart 只保留“导航 + 要点”）：

- `lac_enbid_project/Layer_0/Beijing_Source_Parse_Rules_v1.md`
- `lac_enbid_project/Layer_0/Y_codex_Layer0_build_20251201_20251207.sql`

### 4.4 下次回来的最低复核项（建议先做）

- 两张 Layer_0 表是否存在、行数是否合理
- 关键派生字段是否齐：`ts_std`、`cell_id_dec`、`lac_dec`、`tech`、`"运营商id"`、`parsed_from`
