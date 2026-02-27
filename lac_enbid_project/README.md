# `lac_enbid_project`（LAC / Cell / ENBID 分层数据工程）

本项目把“原始明细 → 合规子集 → 可信库/对比报表”拆成可复跑、可审计、可迭代的 3 层流程：

- Layer_0：原始数据解析与字段标准化（产出统一输入表）
- Layer_1：合规规则（定义“什么叫合规”，产出合规视图/子集）
- Layer_2：只在合规数据上建库与对比（可信库、异常监测清单、GPS vs LAC 对比）

本仓库的“回到现场入口”是：`lac_enbid_project/restart.md`。
服务器配置与会话级调优建议见：`lac_enbid_project/服务器配置与SQL调优建议.md`。

---

## 1) 从哪里开始（推荐阅读顺序）

1. `lac_enbid_project/restart.md`（当前进度 + 必须遵守的协作方式）
2. Layer_2（当前主线）：`lac_enbid_project/Layer_2/README_人类可读版.md`
3. Layer_2 执行手册：`lac_enbid_project/Layer_2/RUNBOOK_执行手册.md`
4. Layer_1 规则参考：`lac_enbid_project/restart_v1/L1_LAC_Compliance.md`、`lac_enbid_project/restart_v1/L1_CELL_Compliance.md`

---

## 2) 命名与口径（必须对齐）

### 2.1 数据库对象命名

- Layer_0 输入表：
  - `public."Y_codex_Layer0_Gps_base"`
  - `public."Y_codex_Layer0_Lac"`
- Layer_2 输出对象（统一）：`public."Y_codex_Layer2_StepXX_*"`
  - 例如：`public."Y_codex_Layer2_Step00_Gps_Std"`、`public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`

### 2.2 字段语言策略

- 列名保持英文（沿用 Layer_0 的列名与派生列名）
- 用 `COMMENT ON TABLE/COLUMN` 写“中文标签 + English description”的双语说明

---

## 3) 执行方式与审计（Layer_2 必须遵守）

### 3.1 默认执行模型

- 你（人类）在服务器/数据库里执行 SQL（尤其是 L/XL 步骤）
- 我（assistant）用 MCP 做自检，产出可审计运行记录（`RUNLOG_YYYYMMDD.md`）

### 3.2 迭代原则（为了本地多轮重跑）

- 每个 Step SQL 都必须：幂等可重跑（drop/replace 处理）、并内嵌必要索引（`CREATE INDEX IF NOT EXISTS`）
- 每步先冒烟再全量：优先限定 `report_date` 或 `operator_id_raw` 做可跑性验证
- PostgreSQL 15：允许在评审中提出“分区 / 增量物化 / 拆分跑”作为加速方案

---

## 4) 目录结构（你要去哪儿找东西）

- `lac_enbid_project/Layer_0/`：原始解析与建表 SQL（产出 Layer_0 输入表）
- `lac_enbid_project/Layer_1/`：合规规则与研究（LAC / Cell / Enbid）
- `lac_enbid_project/Layer_2/`：Step00~Step06 流水线、RUNBOOK、RUNLOG、字段字典
- `lac_enbid_project/Agent_Workspace/`：临时脚本与实验（不沉淀长期规则）

---

## 5) 关键历史参考（可选）

- `lac_enbid_project/Analysis_Summary_20251209.md`：历史分析总结（只作参考，不作为当前口径准绳）
