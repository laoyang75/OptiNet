# UI-first 正式任务书（Gate B）

> 原则：先 UI 映射，再页面/API 落地，再验收，再归档。  
> 说明：每个任务均给出输入、输出、依赖、验收、风险、回归影响、复用/重写策略。

## 任务 1：重建运行入口与启动器

- 输入：`UI_v2/launcher/*`、`config/services.yaml`、当前 `backend/` 与 `frontend/` 目录
- 输出：启动器页面、状态接口、最简启动脚本、运行说明
- 依赖：无
- 验收标准：用户可按文档启动前后端；`/launcher` 能显示前端/后端/数据库状态与日志入口
- 风险：后台无法自举启动自身；需在文档中明确先用脚本起主进程
- 回归影响：影响 Gate C 和用户自助验证能力
- 是否复用当前实现：复用 `services.yaml` 与现有工具链，不复用 `launcher/README.md`
- 如重写，旧文件最终归档到哪里：`rebuild3/archive/20260404_ui_spike/launcher_placeholder/`

## 任务 2：重建前端壳层与三组侧边栏导航

- 输入：`UI_v2/index.html`、`design_notes.md`、页面文档全集
- 输出：正式 App Shell、三组导航、全局 `VersionContext`、共享状态徽标组件
- 依赖：任务 1
- 验收标准：全部正式页面路由可达；导航结构与 `UI_v2` 一致；顶部版本上下文跨页一致
- 风险：现有 Cell spike 组件命名与页面结构不兼容
- 回归影响：影响所有页面
- 是否复用当前实现：只复用构建工具和少量状态/格式函数思路
- 如重写，旧文件最终归档到哪里：`rebuild3/archive/20260404_ui_spike/frontend_spike/`

## 任务 3：补齐 Run/Batch 读模型 API

- 输入：`rebuild3_meta.run`、`batch`、`batch_snapshot`、`batch_flow_summary`、`batch_anomaly_summary`、`batch_baseline_refresh_log`
- 输出：`/api/v1/runs/current`、`/flow-overview`、`/flow-snapshots`、`/batches`、`/batch/{id}`、`/baseline-profile`、`/initialization`
- 依赖：任务 1
- 验收标准：流转总览、批次中心、基线页、初始化页全部有正式接口，不直接拼底表
- 风险：当前仅 1 个 full batch + 1 个 sample batch，时间趋势需要 fallback 视图表达
- 回归影响：影响首页、批次中心、基线页、初始化页
- 是否复用当前实现：重写 `run.py`
- 如重写，旧文件最终归档到哪里：无需归档，占位文件可直接演进

## 任务 4：补齐对象总览、详情、画像读模型 API

- 输入：`rebuild3.obj_*`、`stg_*_profile`、`fact_*`、`baseline_*`、`obj_state_history`、`obj_relation_history`、`r2_full_*`
- 输出：统一的 `/api/v1/objects/summary`、`/list`、`/detail`、`/profile-list`
- 依赖：任务 2、任务 3
- 验收标准：对象浏览、对象详情、LAC/BS/Cell 画像共用统一对象读模型域；Cell/BS/LAC 三种对象均可访问
- 风险：现有 `object.py` 强耦合 Cell；重构时要保留已验证的 compare 语义
- 回归影响：影响对象浏览、详情、画像三类页面
- 是否复用当前实现：部分复用 `object.py` 中的连接、序列化和 compare 逻辑
- 如重写，旧文件最终归档到哪里：如整体替换，则归档到 `rebuild3/archive/20260404_ui_spike/backend_spike/object_api_v1.py`

## 任务 5：实现首批页面（Gate D 目标）

- 输入：任务 2/3/4 的壳层与 API
- 输出：`/launcher`、`/flow/overview`、`/runs`、`/objects`、`/objects/:object_type/:object_id`、`/observation`、`/anomalies`
- 依赖：任务 1~4
- 验收标准：首批页面均可见、可交互、可通过 API 接数；与 `UI_v2` 主结构差异可说明
- 风险：观察工作台和异常工作台需要新增派生读模型
- 回归影响：直接决定 Gate D / Gate E
- 是否复用当前实现：不复用现有页面结构，只吸收局部 Cell 表达经验
- 如重写，旧文件最终归档到哪里：`rebuild3/archive/20260404_ui_spike/frontend_spike/`

## 任务 6：实现第二批页面（画像与基线）

- 输入：对象读模型、baseline 元数据、compare 侧状态表
- 输出：`/baseline`、`/profiles/lac`、`/profiles/bs`、`/profiles/cell`
- 依赖：任务 4、任务 5
- 验收标准：统一 health_state、资格表达与解释层降级全部落地
- 风险：LAC/BS/Cell 页面字段口径不同，需做共性/个性拆分
- 回归影响：影响画像视角层完整性
- 是否复用当前实现：Cell spike 只复用少量字段文案，不复用页面结构
- 如重写，旧文件最终归档到哪里：`rebuild3/archive/20260404_ui_spike/frontend_spike/`

## 任务 7：实现第三批页面（验证 / 初始化 / 基础数据治理）

- 输入：样本/全量报告、compare 结果、资产编目 fallback、sample meta 表
- 输出：`/compare`、`/initialization`、`/governance`
- 依赖：任务 3、任务 4、任务 6
- 验收标准：验证页可展示样本/全量差异；初始化页能对接 sample batch；治理页 4 Tab 可用
- 风险：`rebuild3_meta.asset_*` 尚未灌数，治理页需临时 fallback 编目
- 回归影响：影响支撑治理层完整性
- 是否复用当前实现：重写 `compare.py`、`governance.py`
- 如重写，旧文件最终归档到哪里：无需归档，占位文件直接演进

## 任务 8：建立共享状态表达与组件边界

- 输入：`UI_v2/design_notes.md`、页面文档、页面级状态规则
- 输出：统一 `LifecycleBadge`、`HealthBadge`、`QualificationPills`、`FlowRoutePills`、`CompareDeltaCard`
- 依赖：任务 2
- 验收标准：所有页面不再自行发明颜色/标签/缩写；四分流必须使用全称
- 风险：旧页面遗留缩写与状态文案不统一
- 回归影响：影响全站一致性与验收通过率
- 是否复用当前实现：局部复用现有 Badge 组件思想，但要重写成正式组件
- 如重写，旧文件最终归档到哪里：`rebuild3/archive/20260404_ui_spike/frontend_spike/components/`

## 任务 9：运行文档与最简启动脚本

- 输入：任务 1~7 的正式实现
- 输出：`rebuild3/docs/runtime_startup_guide.md`、更新后的 `rebuild3/README.md`、`scripts/dev/*.sh`
- 依赖：任务 1~7
- 验收标准：用户可根据文档独立启动系统；可检查前端/后端/数据库状态
- 风险：本地环境差异导致命令不一致
- 回归影响：影响最终交付可用性
- 是否复用当前实现：重写当前 README
- 如重写，旧文件最终归档到哪里：无需归档，直接演进

## 任务 10：页面级验收与差异说明

- 输入：所有正式页面、接口、运行入口
- 输出：`rebuild3/docs/ui_acceptance_report.md`
- 依赖：任务 5~9
- 验收标准：每页明确原型文件、路由、API、数据来源、是否真实接数、差异与可接受性
- 风险：若未明确写出 fallback，会造成“已实现/未实现”判断混乱
- 回归影响：决定 Gate F 是否成立
- 是否复用当前实现：新建文档
- 如重写，旧文件最终归档到哪里：不涉及

## 任务 11：数据复审与 read model 补口

- 输入：实际数据库、现有样本/全量报告、UI 页面映射矩阵
- 输出：`rebuild3/docs/data_reaudit_report.md` 与必要的 API fallback 说明
- 依赖：任务 3、任务 4
- 验收标准：明确哪些页面接真实表、哪些仍是 report/fallback；无隐式数据空洞
- 风险：误把报告数据当长期读模型
- 回归影响：影响验收可信度
- 是否复用当前实现：新建文档
- 如重写，旧文件最终归档到哪里：不涉及

## 任务 12：归档 2026-04-04 UI spike

- 输入：`archive_manifest_20260404_ui_spike.md`、新正式实现
- 输出：`rebuild3/archive/20260404_ui_spike/README.md`、`rebuild3/docs/archive_execution_report.md`
- 依赖：Gate F 通过
- 验收标准：归档清单可追踪；旧 spike 已移出正式实现路径；生成产物已清理说明
- 风险：过早归档会丢失对照参考；过晚归档会继续制造目录混乱
- 回归影响：影响目录治理与后续维护成本
- 是否复用当前实现：按 manifest 执行
- 如重写，旧文件最终归档到哪里：`rebuild3/archive/20260404_ui_spike/`

## 实施顺序

1. 运行入口与启动器
2. 前端壳层与共享状态组件
3. Run/Batch API
4. 对象/API 域重构
5. 首批页面
6. 第二批页面
7. 第三批页面
8. 运行说明
9. 页面级验收
10. 归档执行
