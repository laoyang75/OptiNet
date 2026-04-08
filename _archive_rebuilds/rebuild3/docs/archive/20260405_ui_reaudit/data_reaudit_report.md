# 数据资产复审报告

> 复审时间：2026-04-05  
> 复审范围：`rebuild3*` / `rebuild3_meta*` 实际数据库、现有 SQL、样本/全量报告、页面读模型需求。

## 1. 现有数据链路哪些部分已经满足正式实现输入要求

### 1.1 已满足 UI 输入要求的正式表

以下表已在正式库存在，且可直接服务页面/API：

- 对象层：
  - `rebuild3.obj_cell`（573,561）
  - `rebuild3.obj_bs`（193,036）
  - `rebuild3.obj_lac`（50,153）
- 事实层：
  - `rebuild3.fact_standardized`（43,765,636）
  - `rebuild3.fact_governed`（24,855,060）
  - `rebuild3.fact_pending_observation`（10,591,977）
  - `rebuild3.fact_pending_issue`（3,825,789）
  - `rebuild3.fact_rejected`（4,499,191）
- 基线层：
  - `rebuild3.baseline_cell`（194,952）
  - `rebuild3.baseline_bs`（93,110）
  - `rebuild3.baseline_lac`（866）
- 画像/阶段层：
  - `rebuild3.stg_cell_profile`
  - `rebuild3.stg_bs_profile`
  - `rebuild3.stg_lac_profile`
  - `rebuild3.stg_bs_classification_ref`
- 元数据层：
  - `rebuild3_meta.run`（1）
  - `rebuild3_meta.batch`（1）
  - `rebuild3_meta.baseline_version`（1）
  - `rebuild3_meta.batch_snapshot`（11）
  - `rebuild3_meta.batch_flow_summary`（4）
  - `rebuild3_meta.batch_anomaly_summary`（有数据）
  - `rebuild3_meta.batch_baseline_refresh_log`（1）
- 对比参考层：
  - `rebuild3_meta.r2_full_cell_state`
  - `rebuild3_meta.r2_full_bs_state`
  - `rebuild3_meta.r2_full_lac_state`
  - `rebuild3_meta.r2_full_profile_cell`
  - `rebuild3_meta.r2_full_profile_bs`
  - `rebuild3_meta.r2_full_profile_lac`

结论：**对象浏览、对象详情、画像页、流转总览、批次中心、基线页的核心数据基础已经存在。**

## 2. 哪些部分仍只覆盖样本/全量对比，不足以独立支撑正式 UI

### 2.1 仍依赖报告而非正式表的域

- 验证 / 对照页：
  - `rebuild3_meta.compare_result` 当前为空
  - 目前主要信息沉淀在 `sample_compare_report.md` 与 `full_compare_report.md`
- 初始化页：
  - 正式库没有独立 `initialization_step` 明细表
  - 当前可用输入主要来自 `rebuild3_sample_meta.run / batch / batch_snapshot` 与 `sample_run_report.md`
- 基础数据治理页：
  - `rebuild3_meta.asset_table_catalog`、`asset_field_catalog`、`asset_usage_map`、`asset_migration_decision` 已建表但未灌数
  - 需使用当前目录 / SQL / API 实际扫描结果做 fallback 编目

### 2.2 仍缺多批次时间序列的域

- `rebuild3_meta.run` 和 `batch` 只有 1 组正式 full 数据、1 组 sample 数据
- 因此运行 / 批次中心可以展示结构化 batch 详情，但“近 N 批趋势”只能以 sample/full 双点或 fallback 说明展示

### 2.3 观察工作台仍需专用派生读模型

- `obj_cell` 与 `fact_pending_observation` 已存在
- 但 `UI_v2` 需要的：
  - 三层资格百分比
  - 停滞批次数
  - 推进趋势
  - 建议动作
- 这些字段目前不在底表中，需由 API 层派生

### 2.4 异常工作台仍需对象级 / 记录级双视角组合

- 对象级异常：可由 `obj_cell` / `obj_bs` + `health_state` 派生
- 记录级异常：可由 `fact_pending_issue` / `fact_rejected` / `anomaly_tags` + 研究表/规则映射派生
- 但目前没有现成工作台级 summary 表，需 API 聚合

## 3. 是否存在除 UI 之外的 P0 / P1 缺口

### P0

- `launcher` 未落地：用户无法按正式入口独立运行系统
- `run.py`、`compare.py`、`governance.py` 未完成：首批页面无法形成完整读模型闭环

### P1

- `compare_result` 未落表：验证页需 fallback
- `asset_*` 元数据表未灌数：治理页需 fallback
- 当前仅 1 个正式 batch：批次趋势视图表达能力有限
- 观察工作台 / 异常工作台缺少专用派生指标，需要 API 计算层补口

结论：**除 UI 外仍存在 P0/P1 缺口，但都集中在“读模型/API/启动交付”层，而不是底层主数据链路失效。**

## 4. 是否需要补充 read model / summary table

需要，但优先级分两层：

### 4.1 可以先用 API 聚合 / fallback 补齐的域

- 观察工作台三层资格进度
- 异常工作台双视角 summary
- 验证 / 对照页总览与差异样例
- 基础数据治理页编目

### 4.2 后续建议正式沉淀为表的域

- `compare_result` 正式灌数
- `initialization_step_summary`（若初始化页长期保留）
- `observation_progress_summary`（若进入多批增量）
- `anomaly_workspace_summary`（若进入高频日常使用）

## 5. 复审结论

- 数据主链路已经足够支撑本轮 UI-first 正式实现，不需要重写 SQL 主链路。
- 需要补的是页面导向的读模型 API 与少量派生层，而不是推倒已有对象/事实/baseline 表。
- 因此本轮正确策略是：**复用现有 `rebuild3*` 正式表，优先补 API 与页面实现；对于 compare / governance / initialization 等暂未表化的域，先明确 fallback，再在验收报告中写清真实接数状态。**
