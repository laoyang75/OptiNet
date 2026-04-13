# Prompt: rebuild5 总复核、字段评估与 Step5 方案讨论

你在 `/Users/yangcongan/cursor/WangYou_Data` 继续 `rebuild5`。

## 0. 当前任务目标

本轮目标**不是**继续盲目跑批，也**不是**立刻开始新一轮大改，而是做一次面向可交付的总复核，分三部分：

1. **runbook 对照设计总检查**
   - 逐段对照开发文档检查当前生产 runbook 是否与设计一致
   - 发现问题可以**直接修改**
   - 同时检查多次修订后，代码路径是否已经出现不合理、临时性、难以维护的问题

2. **数据库输出字段评估**
   - 评估当前数据库中最终产物的表/字段/口径是否与设计一致
   - 这部分先**给出反馈**
   - 暂时不要求因此立刻改代码
   - 目标是支撑下一阶段 UI 修订与显示评估

3. **Step 5 评估与方案**
   - 对 Step 5 的结构、性能、并发、可维护性给出评估和方案
   - 重点覆盖：
     - 多质心计算
     - 退出逻辑
     - 异常感染 / 防毒化
     - 全局表
     - Cell → BS → LAC 的全量维护链路
     - 并发策略
     - 是否应考虑分表
   - **这一部分先不要改代码**
   - 先给出评估与方案，等用户确认后再进入改造

## 1. 本轮执行边界

### 1.1 这轮要做的

- 完成 runbook vs 设计文档总检查
- 如发现 runbook、脚本、相关支撑代码存在明确问题，可以直接修正
- 完成数据库输出字段评估并给出反馈
- 完成 Step 5 的评估与重构方案建议

### 1.2 这轮不要做的

- 不要在本轮直接开始 Step 5 大规模重构
- 不要在本轮直接再发起从 Step 1 开始的全量重跑
- 不要在没有完成前三部分复核前，就继续扩数据或迁移到生产语义新环境

### 1.3 后续明确计划（只作为下一阶段计划）

在本轮复核、修正、方案确认全部完成之后，下一阶段应按这个顺序执行：

1. 先用本次已经准备好的 `10 个 LAC` 样例数据完整跑通
2. 然后清空数据库中 Step 0-5 相关结果
3. 再从 **Step 1 开始**，按更贴近真实环境的方式完整重跑：
   - 每次从基础数据库中提取**一天原始数据**
   - 跑当天 ETL
   - 跑当天 Step 2 → Step 5
   - 严格按产品语义逐日推进

注意：这一步是**下一阶段**，本 prompt 里先不要执行。

## 2. 先阅读这些文件

这些文件是当前事实基线，必须先读：

- `rebuild5/docs/human_guide/00_系统全貌.md`
- `rebuild5/docs/human_guide/06_核心约束与设计原则.md`
- `rebuild5/docs/00_全局约定.md`
- `rebuild5/docs/02_基础画像.md`
- `rebuild5/docs/03_流式质量评估.md`
- `rebuild5/docs/04_知识补数.md`
- `rebuild5/docs/05_画像维护.md`
- `rebuild5/docs/09_控制操作_初始化重算与回归.md`
- `rebuild5/scripts/runbook_beijing_7d_daily_standard.md`
- `rebuild5/scripts/runbook_beijing_7d_standard.md`

同时还要读当前关键实现：

- `rebuild5/backend/app/profile/pipeline.py`
- `rebuild5/backend/app/evaluation/pipeline.py`
- `rebuild5/backend/app/enrichment/pipeline.py`
- `rebuild5/backend/app/maintenance/pipeline.py`
- `rebuild5/backend/app/maintenance/window.py`
- `rebuild5/backend/app/maintenance/cell_maintain.py`
- `rebuild5/backend/app/maintenance/collision.py`
- `rebuild5/backend/app/maintenance/publish_cell.py`
- `rebuild5/backend/app/maintenance/publish_bs_lac.py`
- `rebuild5/scripts/run_daily_increment_batch_loop.py`
- `rebuild5/scripts/build_daily_sample_etl_input.py`

## 3. 当前已知事实

### 3.1 产品语义

已经确认当前正确语义是：

- `Step 1` 首次全量初始化 / 后续每日 ETL
- `Step 2 ~ Step 5` 每次只处理“当天新增数据”
- 当前批只能读取上一版已发布正式库 / 冻结快照

### 3.2 当前全量按天重基线结果

当前库里已经按 `event_time_std` 的 7 个日桶完成了 `batch1..7` 的正式重基线：

- `2025-12-01` → `batch1`
- `2025-12-02` → `batch2`
- `2025-12-03` → `batch3`
- `2025-12-04` → `batch4`
- `2025-12-05` → `batch5`
- `2025-12-06` → `batch6`
- `2025-12-07` → `batch7`

当前最终正式产物（`batch_id = 7`）：

- `trusted_cell_library = 314698`
- `trusted_bs_library = 164316`
- `trusted_lac_library = 10152`
- `collision_id_list = 8383`

### 3.3 当前样例测试表

当前已经准备好的样例数据表：

- `rebuild5.etl_cleaned_top10_lac_sample`

它是从 `etl_cleaned` 中抽取 `10 个高体量 LAC` 的完整 7 天样例，后续下一阶段应优先用它重跑完整流程。

### 3.4 本轮已经修过的重要实现

不要回滚以下修复：

- Step 2 已支持从 `rebuild5.step2_batch_input` 读取当前日 scope
- `run_daily_increment_batch_loop.py` 支持 `--input-relation`
- `run_daily_increment_batch_loop.py` 支持 `--start-batch-id` 和 `--resume-phase`
- Step 2 donor 已透传到 `path_a_records`
- Step 2 / Step 3 读取 `collision_id_list` 已按上一版 batch 收紧
- Step 5 `snapshot_version_prev` 已按 `< 当前 batch` 读取
- 候选池累计逻辑已经修到可跨天累计，`batch2` 起会出现真实晋升
- `candidate_cell_pool` 的重复 upsert 冲突已经修过
- Step 4 那条纯统计性质的重查询已经降级，避免拖慢正式跑
- `publish_bs_library` 已通过 session 级 `enable_nestloop=off` 修正坏执行计划
- `cell_sliding_window` 写入并发已从 12 降到 4
- `enriched_records` 遇到 `ENOSPC` 时会自动降并发重试

### 3.5 当前新增索引

当前已经补上的关键索引包括：

- `idx_etl_cleaned_event_time_std`
- `idx_rebuild5_raw_gps_ts`
- `idx_tcl_batch_cell_id`
- `idx_tcl_abs_collision`
- `idx_enriched_batch`
- `idx_enriched_batch_cell`
- `idx_gps_anomaly_batch_cell`

但这次总复核里仍然必须重新评估：

- 还有哪些中间表 / 发布表 / 样例表应该加索引
- 哪些索引只是补丁式的，哪些应制度化进入正式流程

### 3.6 当前性能事实

当前正式全量跑里，已确认：

- `collision` 的主要热点已经被显著压下
- 当前 Step 5 新的主要瓶颈更偏向：
  - `daily_centroids`
  - `cell_metrics`
  - `drift_metrics`
  - `publish_cell`

这正是第三部分 Step 5 评估时要重点讨论的对象。

## 4. 本轮具体任务

### Part A: runbook 对照开发文档总检查

你需要逐段核对：

- 当前 `runbook_beijing_7d_daily_standard.md`
- `docs/09_控制操作_初始化重算与回归.md`
- `human_guide/00_系统全貌.md`
- `human_guide/06_核心约束与设计原则.md`
- `docs/03_流式质量评估.md`
- `docs/04_知识补数.md`
- `docs/05_画像维护.md`

必须回答：

1. 当前生产 runbook 是否与设计语义完全一致
2. 哪些段落仍然遗漏、模糊或与实现口径不一致
3. 哪些地方虽然文档没错，但代码路径已经不合理
4. 需要直接修哪些文档或支撑脚本

发现问题可以直接改。

### Part B: 数据库输出字段评估

必须检查当前数据库中这些正式产物：

- `trusted_snapshot_cell`
- `trusted_snapshot_bs`
- `trusted_snapshot_lac`
- `trusted_cell_library`
- `trusted_bs_library`
- `trusted_lac_library`
- `collision_id_list`
- `enriched_records`
- `gps_anomaly_log`

任务目标：

1. 逐表检查字段是否与设计文档一致
2. 逐表检查当前库里是否缺少设计要求字段
3. 识别哪些字段语义漂移了
4. 给出 UI 修订阶段需要注意的字段口径风险

这部分先给反馈，不强制立刻修改。

### Part C: Step 5 评估与方案

你需要从以下角度给出结构化评估：

1. 当前 Step 5 的模块拆分是否合理
2. 多质心、退出逻辑、异常感染、防毒化、全局表是否应进一步拆开
3. Cell 全量维护、再上卷 BS / LAC 的执行模型是否合理
4. 当前并发策略是否合理
5. 是否应考虑分表、分批、分层物化、或局部增量维护
6. 哪些部分适合继续保留 SQL 主导
7. 哪些部分应该改为更清晰的阶段化中间表

这部分先出方案，不要直接改代码。

## 5. 输出要求

在开始改任何 runbook / 文档前，先输出：

1. runbook 总检查的主要风险点
2. 数据库字段评估的检查范围
3. Step 5 方案讨论的边界

完成后，最终输出必须分成三部分：

### 5.1 runbook / 设计一致性结论

- 哪些地方一致
- 哪些地方有问题
- 哪些已经直接修正

### 5.2 数据库字段评估结论

- 逐表给出高价值反馈
- 标出 UI 会依赖但当前需要注意的字段
- 标出与设计不一致处

### 5.3 Step 5 评估与方案

- 给出清晰、可讨论的结构方案
- 明确哪些部分建议拆分
- 明确并发/分表/阶段化的建议
- 明确哪些建议只是讨论，不要在本轮执行

## 6. 当前禁止事项

- 不要在本轮直接开始新的 Step 5 大规模重构
- 不要在本轮直接再次清库并从 Step 1 发起完整全量重跑
- 不要跳过文档对照，直接凭印象评估 runbook

## 7. 补充说明

下一阶段一旦用户确认：

1. 先用 `rebuild5.etl_cleaned_top10_lac_sample` 从 Step 1 对应流程完整跑通
2. 再清空数据库
3. 再从基础数据库逐日抽原始数据
4. 从 Step 1 开始完成一次完整产品语义重跑

本 prompt 先做到“复核、反馈、方案”，不要提前进入下一阶段。
