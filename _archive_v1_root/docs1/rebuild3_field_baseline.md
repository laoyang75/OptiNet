# rebuild3 第二轮字段与边界基线

审计时间：2026-04-05

## 1. 采用的真相源

- Tier 0：`rebuild3/docs/01_rebuild3_说明_最终冻结版.md`、`rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`、`rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`
- Tier 1：`rebuild3/docs/UI_v2/design_notes.md`、`rebuild3/docs/UI_v2/index.html`、`rebuild3/docs/UI_v2/pages/*_doc.md`
- Tier 2（按需）：`rebuild3/docs/api_models.md`、`rebuild3/docs/param_matrix.md`、`docs1/rebuild3_snapshot_rerun_plan.md`
- 实现核对：`rebuild3/backend/app/api/*.py`、`rebuild3/backend/sql/govern/*.sql`、PostgreSQL live schema / live rows、Playwright live page verification

## 2. live schema 结论

- `lifecycle_state`、`health_state`、`existence_eligible`、`anchorable`、`baseline_eligible` 在 `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac` 中均存在。
- `region_quality_label` 仅在 `rebuild3.obj_lac` 中存在。
- `classification_v2` 不在正式对象主表中，当前只出现在参考/画像相关表：`rebuild3.stg_bs_classification_ref`、`rebuild3_meta.r2_full_bs_classification_ref`、`rebuild3_meta.r2_full_profile_bs`。
- `gps_confidence`、`signal_confidence` 在当前 `rebuild3` / `rebuild3_meta` 业务表中不存在。
- 当前实现实际暴露的是 `gps_quality`，来源于 `rebuild3.stg_bs_profile` 或 `rebuild3.stg_cell_profile` 的衍生画像字段，不等于 UI_v2 文档中的 `gps_confidence`。

## 3. 资格阈值基线（来自 `rebuild3/docs/param_matrix.md`）

| 资格层 | 阈值 |
|---|---|
| `existence_eligible` | `min_records=5`、`min_devices=1`、`min_active_days=1` |
| `anchorable` | `min_gps_points=10`、`min_devices=2`、`min_active_days=1`、`max_p90_m=1500` |
| `baseline_eligible` | `min_gps_points=20`、`min_devices=2`、`min_active_days=3`、`min_signal_original_ratio=0.50` |

## 4. 字段与边界确认表

| 字段 | 文档定义 | 层级 | 允许页面 | 不允许升格为 | API 字段 / 端点 | 表/视图来源 | 空值 / fallback | 当前实现一致性 |
|---|---|---|---|---|---|---|---|---|
| `lifecycle_state` | 对象处于哪个存在阶段；与健康状态分离 | 主状态 | `/objects`、`/objects/:type/:id`、`/profiles/lac`、`/profiles/bs`、`/profiles/cell`、`/observation` | `health_state`、资格字段 | `lifecycle_state`；`/api/v1/objects/list`、`/api/v1/objects/profile-list`、`/api/v1/objects/detail` | `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac` | 不应为空；无 fallback | 一致 |
| `health_state` | 对象当前是否可被信任；不能与生命周期混写 | 主状态 | `/objects`、`/objects/:type/:id`、`/profiles/*`、`/anomalies` | `lifecycle_state`、`anchorable`、`baseline_eligible` | `health_state`；对象类 API、异常页 API | `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac` | 不应为空；无 fallback | 一致 |
| `existence_eligible` | 三层资格中的第一层，只代表“存在资格达标” | 资格 | `/observation`、对象详情、对象浏览/筛选 | 主状态、健康状态 | `existence_eligible`；对象类 API | `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac` | 应为布尔；无 fallback | 基本一致；UI 主展示主要集中在观察页 |
| `anchorable` | 锚点资格；与生命周期/健康状态独立 | 资格 | `/objects`、`/profiles/lac`、`/profiles/bs`、`/profiles/cell`、`/observation`、`/baseline` | 主状态、`health_state` 替代品 | `anchorable`；对象类 API | `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac` | 应为布尔；无 fallback | 基本一致；LAC 只展示该资格，符合 UI_v2 |
| `baseline_eligible` | baseline 资格；只回答“能否进入 baseline” | 资格 | `/objects`、`/profiles/bs`、`/profiles/cell`、`/baseline`、对象详情 | 主状态、`compare_membership` 替代品 | `baseline_eligible`；对象类 API | `rebuild3.obj_cell`、`rebuild3.obj_bs`、`rebuild3.obj_lac` | 应为布尔；无 fallback | 部分一致；字段本身正确，但 `/baseline` 页没有按“上一版 baseline”语义使用 |
| `region_quality_label` | LAC 独立解释标签；例如“覆盖不足”等；不属于 `health_state` | 解释层 | `/profiles/lac`、`/objects/:type/:id`（LAC） | LAC 主健康状态 | `region_quality_label`；`/api/v1/objects/profile-list?object_type=lac`、`/api/v1/objects/detail` | `rebuild3.obj_lac` | 允许空；无 fallback | 不一致；当前页面直接显示 `issue_present` / `coverage_insufficient` 原始代码，未做人类标签映射 |
| `classification_v2` | rebuild2 遗留分类，只能做灰色参考信息 | 参考层 | `/profiles/bs`、`/profiles/cell`、必要时对象详情参考区 | 主状态、异常主判断 | `classification_v2`；`/api/v1/objects/profile-list` | BS：`rebuild3_meta.r2_full_profile_bs`；Cell：`rebuild3.stg_bs_classification_ref` | 允许空；无 fallback | 部分一致；位置正确是参考层，但源头并不统一为同一张参考表 |
| `gps_confidence` | rebuild2 遗留 GPS 可信度，只能做灰色参考 | 参考层 | `/profiles/bs`、`/profiles/cell` | `anchorable` 或 `baseline_eligible` 的替代品 | 设计期应为 `gps_confidence`；当前 API 未返回该字段 | live schema 中不存在当前业务列 | 允许空；不应伪造 fallback | 不一致；实现用 `gps_quality` 代替，语义已漂移 |
| `signal_confidence` | rebuild2 遗留信号可信度，只能做灰色参考 | 参考层 | `/profiles/bs` | `baseline_eligible` 的替代品 | 设计期应为 `signal_confidence`；当前前端列存在但 API 未提供值 | live schema 中不存在当前业务列 | 允许空；不应伪造 fallback | 不一致；当前页面整列基本为 `—` |
| `compare_membership` | 对比成员关系；属于验证/参考语义，不属于主治理语义 | 参考层 / 派生字段 | `/objects`、`/objects/:type/:id`、`/compare`、必要时 baseline 参考区 | baseline 版本差异本体 | `compare_membership` / `membership` | 对象 API 中由 `baseline_eligible` + `rebuild3_meta.r2_full_*`.`baseline_eligible` 派生；`run_workspaces.py` baseline 页存在硬编码 | 不应为空；无隐式 fallback | 部分一致；对象页可用，但 `/baseline` 页把它误当“版本差异 membership” |
| `fact_governed` | 已知且健康，或仅存在可治理记录级异常的事实去向 | 四分流主字段 | `/flow/overview`、`/flow/snapshot`、`/runs`、`/compare`、对象详情分布 | 对象主状态 | API 指标名 `fact_governed` | 正式事实表 `rebuild3.fact_governed`；元数据聚合 `rebuild3_meta.batch_flow_summary`、`rebuild3_meta.batch_snapshot` | 不为空；不应 fallback 成 sample/full 对照 | 部分一致；正式全量链路可用，但 scenario snapshot 里是合成结果 |
| `fact_pending_observation` | 等待更多证据/资格推进的事实去向 | 四分流主字段 | `/flow/*`、`/runs`、`/observation`、`/compare`、对象详情分布 | 对象主状态 | API 指标名 `fact_pending_observation` | `rebuild3.fact_pending_observation`；`rebuild3_meta.batch_flow_summary`、`rebuild3_meta.batch_snapshot` | 不为空；不应 fallback | 部分一致；`/observation` 页面主体正确，但趋势仍用 sample/full 衍生 |
| `fact_pending_issue` | 存在对象级问题或需复核问题的事实去向 | 四分流主字段 | `/flow/*`、`/runs`、`/anomalies`、`/compare`、对象详情分布 | 对象主状态 | API 指标名 `fact_pending_issue` | `rebuild3.fact_pending_issue`；`rebuild3_meta.batch_flow_summary`、`rebuild3_meta.batch_snapshot` | 不为空；不应 fallback | 部分一致；`/flow/overview` 与 `/runs` 的 delta/趋势口径错误 |
| `fact_rejected` | 结构不合规或直接拒收的事实去向 | 四分流主字段 | `/flow/*`、`/runs`、`/anomalies`、对象详情分布 | 对象主状态 | API 指标名 `fact_rejected` | `rebuild3.fact_rejected`；`rebuild3_meta.batch_flow_summary`、`rebuild3_meta.batch_snapshot` | 不为空；不应 fallback | 部分一致；正式事实表存在，但 scenario replay 中仍为合成值 |

## 5. 结论摘要

- 主状态层：`lifecycle_state`、`health_state` 的语义边界在对象主表和大部分对象页里是稳定的。
- 资格层：`existence_eligible`、`anchorable`、`baseline_eligible` 的阈值和字段存在性明确，但页面和对比逻辑仍有把资格差异误当版本差异的情况。
- 解释/参考层：`region_quality_label`、`classification_v2`、`gps_confidence`、`signal_confidence` 是本轮最容易继续跑偏的区域。
- live implementation 当前最明显的字段漂移是：
  - 把 `gps_quality` 当成 `gps_confidence` 使用；
  - `signal_confidence` 列保留但没有真实来源；
  - LAC `region_quality_label` 直接暴露技术值；
  - `compare_membership` 被拿去代替“baseline 版本差异”。
