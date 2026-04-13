# Fix4 最终整合评估 Prompt

你在 `/Users/yangcongan/cursor/WangYou_Data` 中执行一轮 **Fix4 最终整合评估**。

这不是第三条独立研究线，也不是让你直接跑正式全量数据。

你的任务是：

1. 对 `fix4/codex/` 与 `fix4/claude/` 两边的已有结果做**独立审计**
2. 对比两边在 `batch1-3` 范围内的结果偏差
3. 如果偏差存在，定位具体原因
4. 对照当前开发文档与设计文档，判断哪一边更合理
5. 对多质心/位置计算/覆盖面积方案做重点评估
6. 最终形成一版**唯一的、可执行的最终 runbook**
7. 最终 runbook 必须先在样例数据上分阶段验证，再允许回到主流程

你的输出将作为后续真正修代码、测试、跑全量的依据。

## 一、先读这些内容

### 1. Fix4 总说明与共享样例约束

- `rebuild5/docs/fix4/00_fix4_任务说明.md`
- `rebuild5/docs/fix4/03_shared_dataset_contract.md`
- `rebuild5/docs/fix4/04_shared_dataset_spec.md`

### 2. 当前问题背景

- `rebuild5/docs/fix3/04_数据链路完整审计报告.md`
- `rebuild5/docs/fix3/多质心问题分析.md`
- `rebuild5/docs/fix3/postgis_multicentroid_batch7_report.md`
- `rebuild5/docs/03_流式质量评估.md`
- `rebuild5/docs/05_画像维护.md`

### 3. 两边研究产物

#### Codex

- `rebuild5/docs/fix4/codex/report.md`
- `rebuild5/docs/fix4/codex/runbook.md`
- `rebuild5/docs/fix4/codex/dataset_plan.md`
- `rebuild5/docs/fix4/codex/metrics_summary.json`
- `rebuild5/docs/fix4/codex/batch1_3_integrated_validation.md`
- `rebuild5/docs/fix4/codex/engineering_fix_batch1_2.md`
- `rebuild5/docs/fix4/codex/step5_postgis_perf_round1.md`

#### Claude

- `rebuild5/docs/fix4/claude/report.md`
- `rebuild5/docs/fix4/claude/runbook.md`
- `rebuild5/docs/fix4/claude/dataset_plan.md`
- `rebuild5/docs/fix4/claude/metrics_summary.json`

## 二、你当前的核心任务

### 1. 不要直接相信任何一方

你必须以“独立审计”的姿态做事。

这意味着：

- 不把 Codex 产物当默认正确
- 不把 Claude 产物当默认正确
- 不把谁跑得更快直接当更好
- 不把谁跑得更多轮直接当更合理

### 2. 先审计前 3 轮

当前两边完成度不一致：

- 一边声称已经完成 `7` 轮
- 另一边只完成到 `3` 轮

所以**第一步不是比谁跑得更远**，而是先把双方在 `batch1-3` 这个共同区间内严格对齐比较。

你必须先完成：

1. `batch1`
2. `batch2`
3. `batch3`

这三轮的结果偏差审计。

### 3. 对偏差做原因追踪

如果双方在 `batch1-3` 上存在结果偏差，你必须追查原因。

至少覆盖：

- Step1 / ETL 行数差异
- Step2 的 `Path A / Path B / Path C`
- Step3 的 `waiting / observing / qualified / excellent`
- Step4 的 `donor_matched / gps_filled / gps_anomaly`
- Step5 的：
  - 发布量
  - 多质心数量
  - moving / migration / dual_cluster / multi_cluster
  - 面积相关指标

不能只写“结果不同”，必须定位：

- 是因为共享数据使用不一致
- 是因为代码改动不同
- 是因为其中一方过度修改了底层设计逻辑
- 还是因为性能折中导致行为变化

### 4. 对照开发文档评估合理性

你必须把偏差和当前文档约束一一对照。

重点看：

1. 谁偏离了已有架构设计
2. 谁修改了不该修改的底层逻辑
3. 谁虽然跑得快，但牺牲了设计边界或业务语义
4. 谁虽然跑得慢，但逻辑上更符合 Fix4 目标

你的目标不是“折中”，而是选出**更合理的最终方案**。

## 三、重点审计方向

### 1. 位置计算问题

这是最高优先级。

你必须重点判断：

- 谁更有效过滤了无效 GPS / 偏差最大点
- 谁更合理处理了 Step3 与 Step5 的位置计算分工
- 是否应在 Step3 先做强过滤，还是 Step5 做主过滤，还是两层协同
- 是否引入了过度裁剪或过度平滑

### 2. 覆盖面积过大问题

必须重点评估：

- Cell 面积是否明显收敛
- BS 面积是否随之收敛
- 这种收敛是否合理，是否有解释
- 是否只是通过“硬裁剪”把面积压小

### 3. 多质心计算

你必须重点比较：

- 哪一方的多质心计算方案更合理
- 双簇 / 多簇 / moving / migration 的边界是否清楚
- `migration` 是否真的只建立在双簇基础上
- `moving` 是否可以合理继承到 BS
- `LAC 不做多簇` 是否被严格遵守

### 4. 速度优化

只有在前面逻辑问题评估清楚后，才允许比较速度优化。

你必须分开判断：

1. 逻辑是否正确
2. 速度是否更优

不要因为速度更快就忽略设计偏差。

## 四、必须采用的共享样例数据

你必须使用 Fix4 已经冻结好的共享样例数据：

- `rebuild5_fix4.raw_gps_shared_sample`
- `rebuild5_fix4.etl_cleaned_shared_sample`
- `rebuild5_fix4.focus_cells_shared`

固定时间范围：

- `2025-12-01 ~ 2025-12-07`

如果你认为共享样例数据不足：

- 只能提出补样建议
- 不能直接改共享原始样例集

## 五、最终 runbook 的验证顺序

你最终交付的 runbook **必须严格按下面顺序验证**：

### 阶段 A：前三轮前置验证

1. 先只跑第 `1` 轮
2. 再跑第 `2` 轮
3. 再做第 `3` 轮前置测试

验证目标：

- 第 `2` 轮必须已经出现有效的等待、分流、补数
- 第 `3` 轮必须确认代码运行逻辑正常
- 第 `3` 轮的核心指标必须和预期一致

### 阶段 B：7 轮样例验证

只有前三轮前置验证通过后，才允许扩展到：

- 完整 `7` 轮样例数据测试

### 阶段 C：形成最终 runbook

你最后要形成的是：

- 一版**可用于后续全量运行前的最终样例 runbook**

注意：

- 此 runbook 仍然先用于样例验证
- 不是让你现在直接跑正式全量

## 六、你必须输出什么

输出目录建议放到：

- `rebuild5/docs/fix4/final/`

至少包括：

1. `final_audit_report.md`
   - 双方结果对比
   - 偏差列表
   - 偏差原因
   - 合理性裁决
   - 最终推荐方案
2. `batch1_3_diff_audit.md`
   - 专门审计前三轮差异
3. `multicentroid_judgement.md`
   - 专门审计多质心 / moving / migration / dual_cluster / multi_cluster
4. `final_runbook.md`
   - 最终执行 runbook
   - 严格包含“第1轮 -> 第2轮 -> 第3轮前置测试 -> 第7轮样例验证”的顺序
5. `final_metrics_summary.json`
   - 最终方案的核心指标
6. `code_change_decision.md`
   - 说明当前主流程后续应改哪些代码
   - 哪些改动应保留
   - 哪些改动应回退

## 七、关键要求

### 1. 不要直接进入正式全量

你当前的任务不是跑正式全量，而是形成一版足够稳的最终方案。

### 2. 不要只看“谁跑得更多轮”

轮次多不代表更合理。

你必须先在共同区间 `batch1-3` 上做公平审计。

### 3. 不要只看“谁更快”

速度快不代表逻辑对。

### 4. 如果某一方改了不该改的底层设计

必须明确指出：

- 改了什么
- 为什么不合理
- 是否应回退

### 5. 最终目标

你要交付的不是“建议清单”，而是：

- 一版经比较后确认的最终方案
- 一版可执行的样例 runbook
- 一版回到主流程后该如何改代码、测试、再跑全量的明确方案
