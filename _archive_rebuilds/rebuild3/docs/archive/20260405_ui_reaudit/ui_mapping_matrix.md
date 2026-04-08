# UI 页面映射矩阵（Gate A1）

> 说明：本矩阵以 `UI_v2` 为正式页面基线；“当前实现状态”描述的是审计时点状态，“正式路由/API”描述的是本轮 UI-first 实现目标。

| UI_v2 原型 | 正式路由 | 页面目标 | 必要读模型 / API | 依赖数据表 / 汇总表 | 当前实现状态 | 验收标准 | 首批优先 |
|---|---|---|---|---|---|---|---|
| `launcher/launcher.html` | `/launcher` | 启动、停止、状态检查、日志查看的独立入口 | `GET /api/v1/launcher/services`、`GET /api/v1/launcher/logs/{service}`、`POST /api/v1/launcher/services/{name}/{action}` | `config/services.yaml`、本地进程 / 端口状态、运行日志 | 未开始（仅 `launcher/README.md`） | 能查看前端/后端/数据库状态；能执行最简启动动作；能查看日志 | 是 |
| `pages/01_flow_overview.html` + `01_flow_overview_timeline.html` | `/flow/overview` | 展示当前 run/batch/baseline 上下文、四分流、delta、问题入口与快照视图 | `GET /api/v1/runs/current`、`GET /api/v1/runs/flow-overview`、`GET /api/v1/runs/flow-snapshots` | `rebuild3_meta.run`、`batch`、`batch_snapshot`、`batch_flow_summary`、`batch_anomaly_summary`、`batch_baseline_refresh_log` | 未实现 | 顶部版本上下文完整；四分流与 `batch_snapshot` 一致；问题入口可下钻 | 是 |
| `pages/02_run_batch_center.html` | `/runs` | 批次列表、趋势、选中批次详情与 delta 诊断 | `GET /api/v1/runs/batches`、`GET /api/v1/runs/batch/{batch_id}` | `rebuild3_meta.batch`、`batch_snapshot`、`batch_flow_summary`、`batch_decision_summary`、`batch_anomaly_summary` | 未实现 | 批次列表、趋势、详情联动可见；可跳对象/异常/基线页 | 是 |
| `pages/03_objects.html` | `/objects` | 统一浏览 Cell / BS / LAC 的治理状态与资格 | `GET /api/v1/objects/summary`、`GET /api/v1/objects/list` | `rebuild3.obj_cell`、`obj_bs`、`obj_lac`，及 `stg_*_profile`、`r2_full_*` 对比表 | 仅有 Cell spike | 支持对象类型切换；统一 lifecycle/health/资格徽标；可下钻详情 | 是 |
| `pages/04_object_detail.html` | `/objects/:object_type/:object_id` | 展示单对象状态、画像摘要、事实分布、历史、资格原因、异常和下游影响 | `GET /api/v1/objects/detail` | `rebuild3.obj_*`、`obj_state_history`、`obj_relation_history`、`fact_*`、`baseline_*`、`r2_full_*` | 仅 Cell 局部可用 | 支持 Cell/BS/LAC；具备版本上下文与下游影响；能跳异常/批次/画像 | 是 |
| `pages/05_observation_workspace.html` | `/observation` | 三层资格推进（存在 / 锚点 / 基线）与堆积分析 | `GET /api/v1/runs/observation-workspace` | `rebuild3.obj_cell`、`fact_pending_observation`、`rebuild3_meta.batch_snapshot` | 未实现 | 候选卡按三层资格显示；能解释停滞/推进/转问题建议 | 是 |
| `pages/06_anomaly_workspace.html` | `/anomalies` | 对象级异常与记录级异常双视角工作台 | `GET /api/v1/runs/anomaly-workspace` | `rebuild3.obj_cell`、`obj_bs`、`fact_pending_issue`、`fact_rejected`、`rebuild3_meta.batch_anomaly_summary` | 未实现 | 双 Tab 完整；对象级/记录级分开展示；建议动作可见 | 是 |
| `pages/07_baseline_profile.html` | `/baseline` | 基线版本、刷新原因、覆盖质量、版本差异、风险与历史 | `GET /api/v1/runs/baseline-profile` | `rebuild3_meta.baseline_version`、`batch_baseline_refresh_log`、`baseline_*`、`r2_full_*` | 未实现 | 明确“当前批次只读上一版 baseline”；对象差异与风险评估可见 | 否 |
| `pages/08_validation_compare.html` | `/compare` | 样本/全量对照、差异对象与解释 | `GET /api/v1/compare/overview`、`GET /api/v1/compare/diffs` | `rebuild3_meta.compare_result`（当前为空，需 fallback） + `sample_compare_report.md` + `full_compare_report.md` + `r2_full_*` | 占位骨架 | 至少展示样本/全量两组结果、关键偏差、差异样例与解释 | 否 |
| `pages/09_lac_profile.html` | `/profiles/lac` | LAC 区域画像、统一 health_state、区域质量标签 | `GET /api/v1/objects/profile-list?object_type=lac` | `rebuild3.obj_lac`、`stg_lac_profile`、`r2_full_lac_state`、`r2_full_profile_lac` | 未实现 | 主状态使用 lifecycle/health/anchorable；旧标签只做解释层 | 否 |
| `pages/10_bs_profile.html` | `/profiles/bs` | BS 锚点画像、P50/P90、旧分类降级展示 | `GET /api/v1/objects/profile-list?object_type=bs` | `rebuild3.obj_bs`、`stg_bs_profile`、`stg_bs_classification_ref`、`r2_full_bs_state`、`r2_full_profile_bs` | 未实现 | 主状态统一；旧 `classification_v2/gps_confidence/signal_confidence` 仅做灰色解释层 | 否 |
| `pages/11_cell_profile.html` | `/profiles/cell` | Cell 最小治理单元画像与事实去向 | `GET /api/v1/objects/profile-list?object_type=cell`、`GET /api/v1/objects/detail` | `rebuild3.obj_cell`、`stg_cell_profile`、`fact_*`、`r2_full_cell_state`、`r2_full_profile_cell` | 仅有 Cell spike | 表格页与详情口径统一；四分流用全称；解释层降级显示 | 否 |
| `pages/12_initialization.html` | `/initialization` | 冷启动流程、结果汇总、研究期策略说明 | `GET /api/v1/runs/initialization` | `rebuild3_sample_meta.run`、`batch`、`batch_snapshot`、`sample_run_report.md` | 未实现 | 11 步流程、汇总卡、四分流分布与研究期说明完整可见 | 否 |
| `pages/13_data_governance.html` | `/governance` | 字段目录、表目录、实际使用、迁移状态 | `GET /api/v1/governance/overview`、`/fields`、`/tables`、`/usage/{table}`、`/migration` | `rebuild3_meta.asset_*`（当前未灌数） + 当前目录/SQL/API 映射 fallback | 占位骨架 | 4 Tab 完整可用；明确哪些是真实元数据、哪些是 fallback 编目 | 否 |

## 共享组件与上下文映射

| 组件 / 上下文 | 服务页面 | 说明 |
|---|---|---|
| `VersionContext` | 全部正式页面 | 固定显示 `run_id / batch_id / contract_version / rule_set_version / baseline_version` |
| `LifecycleBadge` | 对象浏览、详情、画像、观察、异常 | 统一 `waiting / observing / active / dormant / retired / rejected` |
| `HealthBadge` | 对象浏览、详情、画像、异常 | 统一 `healthy / insufficient / gps_bias / collision_suspect / collision_confirmed / dynamic / migration_suspect` |
| `QualificationPills` | 对象浏览、详情、画像、观察、异常 | 显示 `existence / anchorable / baseline_eligible` |
| `FlowRoutePills` | 流转总览、批次中心、详情、画像、异常 | 统一四分流全称 |
| `CompareDeltaCard` | 流转总览、批次中心、基线、验证/对照 | 展示 `rebuild2 vs rebuild3` 差异 |
| `ObservationProgressCard` | 等待/观察工作台 | 三层资格推进卡 |
| `AnomalyTabs` | 异常工作台 | 对象级 / 记录级双视角切换 |

## 当前门禁判断

- Gate A1 通过条件所需的页面-路由-API-数据映射已明确。
- 当前最大差距不是数据表不存在，而是：**前端页面体系与 API 读模型尚未对齐到这张矩阵。**
