# rebuild5 三轮模块优化审计记录

> 本文件用于记录 `10b_模块优化审计.md` 第三轮的进度与结论。
> 新会话开始时先读 `audit_log_round2_module.md` 了解前两轮记录，再读本文件确认第三轮进度。

## 审计进度

- M1 Step 1 数据接入：confirmed
- M2 Step 2 基础画像：confirmed
- M3 Step 3 流式评估：confirmed
- M4 Step 4 知识补数：confirmed
- M5 Step 5 画像维护：confirmed
- M6 服务层：in_progress
- M7 运行控制：pending
- M8 通用基础层：pending

## 二轮结论速查（开始前参考，不要重复展开）

| 模块 | 二轮优先级 | 二轮核心问题（摘要） | 是否已改代码 |
|------|-----------|---------------------|-------------|
| M1 Step 1 | P1 | 伪多源壳层未清干净；同报文补齐漏补（单 donor）；清洗路径存储足迹过重 | 否 |
| M2 Step 2 | P0 | Layer 3 ID 碰撞只取一行候选；`bs_id` 混入 Cell 主键 | 否 |
| M3 Step 3 | P0 | 无独立候选池，snapshot 与候选状态混叠；waiting/observing 对象无法跨批连续升级 | 否 |
| M4 Step 4 | P0 | donor 版本未冻结到上一轮（读最新库）；`tech_norm` 阻断 donor 命中 | 否 |
| M5 Step 5 | P0 | 滑动窗口只装本批数据，非真正滑动；真碰撞判定缺 `tech_norm`；多质心为占位实现 | 否 |
| M6 服务层 | pending | — | — |
| M7 运行控制 | pending | — | — |
| M8 通用基础层 | pending | — | — |

## 详细记录

> 所有模块初始状态为 pending，按 M1 → M8 顺序推进，每次只审一个模块。
> 每完成一个模块，在下方对应章节填写本轮增量评估结论。

## M1 Step 1 数据接入

- 状态：confirmed
- 前两轮结论回顾：见上方速查表
- 需求文档：
  - `rebuild5/docs/00_全局约定.md`
  - `rebuild5/docs/01a_数据源接入_功能要求.md`
  - `rebuild5/docs/01b_数据源接入_处理规则.md`
  - `rebuild5/docs/human_guide/01_Step1_数据源接入.md`
  - `rebuild5/ui/03_ETL数据接入页面.md`
- 代码范围：
  - `rebuild5/backend/app/etl/source_prep.py`
  - `rebuild5/backend/app/etl/definitions.py`
  - `rebuild5/backend/app/etl/parse.py`
  - `rebuild5/backend/app/etl/clean.py`
  - `rebuild5/backend/app/etl/fill.py`
  - `rebuild5/backend/app/etl/pipeline.py`
  - `rebuild5/backend/app/etl/queries.py`
  - `rebuild5/backend/app/routers/etl.py`
  - `rebuild5/frontend/design/src/api/etl.ts`
  - `rebuild5/frontend/design/src/views/etl/DataSource.vue`
  - `rebuild5/frontend/design/src/views/etl/FieldAudit.vue`
  - `rebuild5/frontend/design/src/views/etl/Parse.vue`
  - `rebuild5/frontend/design/src/views/etl/Clean.vue`
  - `rebuild5/frontend/design/src/views/etl/Fill.vue`
- 对齐汇总：已实现 4 / 偏差 6 / 未实现 2 / 超出文档 0
- 已落地的改进：
  - 已把 Step 1 文档中的 `dataset_key`、`source_table` 补回字段清单，不再视为“超出字段”
  - 已把 UI 文档中的清洗规则口径修正为 `19` 条
  - 已新增第一阶段修复建议：`rebuild5/docs/fix1/01_step1_UI小修复建议.md`
- 本轮新增发现：
  - ETL 主流程（解析 / 清洗 / 同报文补齐）基本成立
  - 主要差异集中在统计口径、页面文案和阶段语义表达
  - `test_source_prep.py` 仍依赖旧接口，测试与现状漂移
- 优先级结论：
  - P1
  - 当前不阻塞 Step 1 主流程，优先做 UI 小修复与文档口径收口
- 决策动作：
  - 多数据源注册/切换及数据源管理交互暂不开发
  - 第一阶段仅处理 Step 1 UI 小修复，不改 ETL 主流程
  - 细粒度字段审计与解析阶段独立统计后置
- 偏差列表：
  - 数据源页仍使用“注册/管理”语义，但当前实现是单活只读展示
  - 字段审计页当前展示冻结字段定义，不是真实源表字段审计
  - 解析页覆盖率展示为 Step 1 汇总口径，非纯解析阶段口径
  - 清洗页/文档的规则数口径此前存在不一致
  - 补齐页边界说明未完整表达 `cell_infos` / `ss1<=60s` / `ss1>60s`
  - Step 1 统计能力仍是简化版
- 用户确认：是
- 写入 fix 文件：是
- 是否已改代码：
- 是否仅更新文档：是
- 下一步：进入 M2 Step 2 基础画像审计

## M2 Step 2 基础画像

- 状态：confirmed
- 前两轮结论回顾：见上方速查表
- 需求文档：
  - `rebuild5/docs/00_全局约定.md`
  - `rebuild5/docs/02_基础画像.md`
  - `rebuild5/docs/human_guide/02_Step2_基础画像与分流.md`
  - `rebuild5/ui/04_基础画像与分流页面.md`
- 代码范围：
  - `rebuild5/backend/app/profile/pipeline.py`
  - `rebuild5/backend/app/profile/queries.py`
  - `rebuild5/backend/app/profile/logic.py`
  - `rebuild5/backend/app/routers/profile.py`
  - `rebuild5/frontend/design/src/views/profile/Routing.vue`
  - `rebuild5/frontend/design/src/api/profile.ts`
  - `rebuild5/tests/test_profile_logic.py`
  - `rebuild5/tests/test_profile_router.py`
  - `rebuild5/tests/test_pipeline_version_guards.py`
- 对齐汇总：已实现 6 / 偏差 5 / 未实现 1 / 超出文档 0
- 已落地的改进：
  - 已按当前实现把 Step 2 文档中的 Cell 识别口径修正为 `operator_code + tech_norm + lac + cell_id`
  - 已对 Step 2 页面做第一阶段 UI 小修复，补充动态 Path A 文案、Path C 口径说明、只读规则口径区、支持/待开发区
  - 已新增修复建议：`rebuild5/docs/fix1/02_step2_UI小修复建议.md`
- 本轮新增发现：
  - Path A / Path B / Path C 主链路与分钟级去重、中位数质心、P50/P90 半径主算法已落地
  - Layer 2 宽松匹配当前比文档更宽
  - Path C 当前展示为剩余丢弃总量，而非纯“无 GPS 丢弃”
  - 页面功能目前是轻量总览页，复杂筛选/样本/跳转仍未实现
- 优先级结论：
  - P1
  - 当前优先处理文档与 UI 语义收口；复杂页面交互后置
- 决策动作：
  - `tech_norm` 相关差异认定为文档口径错误，已修正文档
  - Path C 统计不再扩展拆分统计，本阶段只在 UI 中明确口径
  - 页面复杂筛选、样本和跳转能力改为待开发
- 偏差列表：
  - Layer 2 宽松匹配当前放宽范围大于文档描述
  - Path C 页面统计当前为汇总剩余丢弃量
  - Step 2 页面的筛选、样本、跳转等能力尚未实现
  - 原页面将“冷启动 Path A=0”写死，现已修正文案
- 用户确认：是
- 写入 fix 文件：是
- 是否已改代码：是
- 是否仅更新文档：否
- 下一步：进入 M3 Step 3 流式评估审计

## M3 Step 3 流式评估

- 状态：confirmed
- 前两轮结论回顾：见上方速查表
- 需求文档：
  - `rebuild5/docs/03_流式质量评估.md`
  - `rebuild5/docs/human_guide/03_Step3_流式质量评估.md`
  - `rebuild5/ui/05_流转评估页面.md`
  - `rebuild5/docs/00_全局约定.md`
- 代码范围：
  - `rebuild5/backend/app/evaluation/pipeline.py`
  - `rebuild5/backend/app/evaluation/queries.py`
  - `rebuild5/backend/app/routers/evaluation.py`
  - `rebuild5/frontend/design/src/api/evaluation.ts`
  - `rebuild5/frontend/design/src/views/evaluation/FlowOverview.vue`
  - `rebuild5/frontend/design/src/views/evaluation/CellEval.vue`
  - `rebuild5/frontend/design/src/views/evaluation/BSEval.vue`
  - `rebuild5/frontend/design/src/views/evaluation/LACEval.vue`
  - `rebuild5/tests/test_pipeline_version_guards.py`
  - `rebuild5/tests/test_profile_router.py`
- 对齐汇总：已实现 8 / 偏差 1 / 未实现 2 / 超出文档 0
- 已落地的改进：
  - 已将 `tech_norm` 纳入 Step 3 的候选池合并键、候选池唯一约束、快照 carry-forward 匹配键和 Cell diff 识别键
  - 已增加简化版候选池清理：`waiting / observing` 对象连续 `45` 批未晋级即删除
  - 已将 `waiting_pruned_cell_count` 透出到 Step 3 总流转页，并把未启用的 `dormant` 统计标注为待开发
  - 已修正文档中把“分钟级观察点去重”误读成“分钟级评估调度”的表达
- 本轮新增发现：
  - Step 3 的候选池模型、carry-forward 边界和三层 snapshot 主链已经成立
  - “分钟级”是批内观察点去重口径，不是调度频率
  - 详情展开和部分过滤统计仍然未完全接线
- 优先级结论：
  - P1
  - 当前主链已可继续使用，剩余问题主要是统计补齐和 UI 细化
- 决策动作：
  - `tech_norm` 相关问题按代码修复处理
  - 候选池清理先采用 `45` 批简化规则
  - `dormant` 完整链路与更复杂详情钻取暂标待开发
  - “分钟级”问题认定为文档表达问题，不作为代码缺陷
- 偏差列表：
  - `mode_filtered_count / region_filtered_count / gps_filtered_count` 当前仍未实现，统计位保留为 0
  - `dormant_marked_count` 统计位已保留，但实际逻辑暂未启用
  - Cell / BS / LAC 详情展开接口已存在，前端尚未接入完整钻取交互
- 用户确认：是
- 写入 fix 文件：是
- 是否已改代码：是
- 是否仅更新文档：否
- 下一步：等待用户指令，不自动进入 M4

## M4 Step 4 知识补数

- 状态：confirmed
- 前两轮结论回顾：见上方速查表
- 需求文档：
  - `rebuild5/docs/04_知识补数.md`
  - `rebuild5/docs/human_guide/04_Step4_知识补数.md`
  - `rebuild5/ui/06_知识补数与治理页面.md`
- 代码范围：
  - `rebuild5/backend/app/enrichment/pipeline.py`
  - `rebuild5/backend/app/enrichment/schema.py`
  - `rebuild5/backend/app/enrichment/queries.py`
  - `rebuild5/backend/app/routers/enrichment.py`
  - `rebuild5/frontend/design/src/api/enrichment.ts`
  - `rebuild5/frontend/design/src/views/governance/KnowledgeFill.vue`
  - `rebuild5/tests/test_pipeline_version_guards.py`
  - `rebuild5/tests/test_maintenance_router.py`
  - `rebuild5/tests/test_enrichment_queries.py`
- 对齐汇总：已实现 7 / 偏差 1 / 未实现 1 / 超出文档 0
- 已落地的改进：
  - 已将 GPS 异常检测收口为“仅对原始且有效的 GPS 证据做 donor 质心比对”
  - 已直接使用 Step 2 记录上的碰撞标记跳过异常检测，不再回头查碰撞表
  - 已实现 `collision_skip_anomaly_count` 真实统计
  - 已将异常样本接口收口为“默认只看最新批次”
  - 已修正前端异常样本接口参数契约为 `page_size`
  - 已新增修复建议：`rebuild5/docs/fix1/04_step4_UI小修复建议.md`
- 本轮新增发现：
  - Step 4 的 donor/version 边界总体正确，核心链路已经收口
  - 当前 Step 4 页面仍是轻量概览页，复杂筛选能力尚未实现
  - `tech_final / tech_fill_source_final` 当前作为补数审计字段保留
- 优先级结论：
  - P1
  - 当前主流程可用，剩余问题主要是页面能力和统计细化
- 决策动作：
  - 简单边界问题直接修代码并对齐文档
  - 页面复杂筛选能力继续标注待开发
- 偏差列表：
  - 知识补数页的运营商 / LAC / donor 质量 / 异常状态筛选仍未实现
  - `tech_final` 仍作为 Step 4 审计补数字段保留，文档已按当前实现收口
- 用户确认：是
- 写入 fix 文件：是
- 是否已改代码：是
- 是否仅更新文档：否
- 下一步：进入 M5 Step 5 画像维护审计

## M5 Step 5 画像维护

- 状态：confirmed
- 前两轮结论回顾：见上方速查表
- 已落地的改进：
  - 已将 `tech_norm` 贯穿到 Step 5 的核心 Cell 维护链路：`trusted_cell_library`、`cell_sliding_window`、`cell_daily_centroid`、`cell_metrics_window`、`cell_centroid_detail` 及其查询/发布 join
  - 已修正 BS / LAC 发布阈值到文档口径：BS `>=1 excellent` 或 `>=3 qualified+`；LAC `qualified BS >= 3` 或占比 `>=10%`
  - 已将滑动窗口建议口径更新为“最近 `14` 天，或至少 `1000` 条观测，取较大范围”，并在窗口实现层落地
  - 已修正文档中 A 类碰撞扫描对象的 `tech_norm` 歧义
  - 已新增第一阶段 UI 修复建议：`rebuild5/docs/fix1/05_step5_UI小修复建议.md`
  - 已新增全局 UI 收口说明：`rebuild5/docs/fix1/00_全局UI收口说明.md`
  - 已修正 Step 5 页面中的 `active` 旧术语，并使 `dormant / retired` 过滤在 Cell 页真实可用
- 本轮新增发现：
  - 滑动窗口仍是固定时间窗，不是文档中的“数量优先窗口”
  - `step5_run_stats` 仍是精简统计，不是文档中 `step5_maintenance_log` 的完整指标集
  - 归档表 `cell_window_archive / retired_profile_archive` 仍未实现
- 优先级结论：
  - P0
  - Step 5 是治理与正式发布核心节点，当前已先修关键识别键和阈值问题
- 决策动作：
  - 先修 `tech_norm` 和发布阈值，保证主链正确
  - 滑动窗口口径先上调为“最近 `14` 天或至少 `1000` 条观测，取较大范围”
  - 质心相关先保持“可用但不过度设计”，为后续 `09_多质心算法调研.md` 准备真实数据底座
  - 更重的窗口策略、归档表和完整维护统计后续再收口
- 偏差列表：
  - `step5_run_stats` 仍是精简统计，不是文档中 `step5_maintenance_log` 的完整指标集
  - `cell_window_archive / retired_profile_archive` 仍未实现
  - 多质心细表当前是轻量版，字段集未完全达到文档目标
- 用户确认：是
- 写入 fix 文件：是
- 是否已改代码：是
- 是否仅更新文档：否
- 下一步：进入 M6 服务层审计

## M6 服务层

- 状态：in_progress
- 前两轮结论回顾：二轮未审（pending）
- 已落地的改进：
  - 已修复服务层搜索结果点击详情时的上下文丢失问题：Cell 详情携带 `operator_code + lac + tech_norm`，BS 详情携带 `operator_code + lac`，LAC 详情携带 `operator_code`
  - 已修复 Cell 详情中的独立设备数字段映射，前端不再错误读取 `unique_devices`
  - 已将服务层页面标题与文档统一收口为 `站点查询`
  - 已把未实现能力（运营商筛选、坐标范围查询、覆盖分析深层图表、统计报表趋势图）统一标注为待开发
  - 已新增第一阶段 UI 修复建议：`rebuild5/docs/fix1/06_step6_UI小修复建议.md`
- 本轮新增发现：
  - 服务层后端主查询基本都直接读取最新正式库，主链简单清晰
  - 当前页面仍保留部分治理字段作为过渡展示，尚未完全收口为纯业务友好表达
  - 覆盖分析与统计报表页功能明显轻于文档初稿
- 优先级结论：
  - P1
  - 当前主风险是“串详情”和“文档/页面能力强于实际实现”，已先修最关键的上下文问题
- 决策动作：
  - 先保留轻量服务层，不扩展复杂筛选和区域分析能力
  - 对未实现能力统一降级为待开发
- 是否已改代码：是
- 是否仅更新文档：否
- 下一步：输出修订后的 M6 审计结论供用户确认

## M7 运行控制

- 状态：pending
- 前两轮结论回顾：二轮未审（pending）
- 已落地的改进：
- 本轮新增发现：
- 优先级结论：
- 决策动作：
- 是否已改代码：
- 是否仅更新文档：
- 下一步：

## M8 通用基础层

- 状态：pending
- 前两轮结论回顾：二轮未审（pending）
- 已落地的改进：
- 本轮新增发现：
- 优先级结论：
- 决策动作：
- 是否已改代码：
- 是否仅更新文档：
- 下一步：
