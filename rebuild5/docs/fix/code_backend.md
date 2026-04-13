# 后端问题集中处理清单

> 目的：集中记录 `rebuild5` 后端、流程、数据库、索引和接口契约的已确认问题，待统一评审后再集中处理。

## 写入规则

- 只记录已经和用户讨论并确认的问题。
- 未确认的问题可以在对话里讨论，但不要写入本文件。
- 本文件用于集中处理，不代表发现后立刻修改代码。
- 每条问题尽量写清楚现象、影响、关联模块和建议处理方向。

## 条目模板

```md
### B-xxx 问题标题

- 状态：confirmed / ready / done
- 现象：
- 影响：
- 相关模块/文件：
- 建议处理：
- 确认结论：
```

## 已确认问题

### B-001 Step 4 应简化为“按 Step 2 已确认补数源执行补数”，不再自己二次匹配

- 状态：confirmed
- 现象：
  - Step 4 当前仍自己去 `trusted_cell_library` 重新做 donor/source cell 匹配，并独立选择 donor 版本
  - 这让一个本应很简单的补数步骤承担了额外的匹配和版本决策复杂度
- 影响：
  - 容易破坏冻结快照边界
  - 容易在重跑 Step 4 时读到错误版本
  - 也让 Step 4 变成“重新匹配 + 补数”，而不是单纯补数
- 相关模块/文件：
  - `rebuild5/backend/app/enrichment/pipeline.py`
  - `rebuild5/docs/04_知识补数.md`
  - `rebuild5/docs/human_guide/04_Step4_知识补数.md`
- 建议处理：
  - 将“命中哪个可信 Cell / 使用哪个版本”这件事前移到 Step 2
  - `path_a_records` 应携带已确认的 source cell 身份和 source version
  - Step 4 只按已确认 source cell 读取值并补数，同时基于同一 source 做 GPS 异常初筛
- 确认结论：
  - 已确认 Step 4 的合理模型就是“简单补数器”，不应再拥有 donor 重新匹配和版本选择权

### B-002 Step 1 统计与审计接口当前仍是简化版，页面需按现状降级表达

- 状态：confirmed
- 现象：
  - Step 1 主流程已经可运行，但统计与审计接口仍偏简化
  - `field-audit` 当前返回的是冻结字段定义，不是真实源表字段审计
  - 解析页所用覆盖率口径也是 Step 1 汇总结果，并非纯解析阶段独立统计
- 影响：
  - 页面如果继续按“注册页 / 审计页 / 解析页”的强语义展示，会产生理解偏差
  - 后续若要补齐细粒度统计，还需要单独扩展后端统计口径
- 相关模块/文件：
  - `rebuild5/backend/app/etl/queries.py`
  - `rebuild5/backend/app/etl/pipeline.py`
  - `rebuild5/backend/app/etl/source_prep.py`
  - `rebuild5/docs/fix1/01_step1_UI小修复建议.md`
- 建议处理：
  - 当前阶段不扩展 Step 1 后端统计能力
  - 先通过 UI 与文档文案把口径降到与现状一致
  - 后续若要做真实字段审计和解析阶段独立统计，再单独补后台能力
- 确认结论：
  - 已确认本阶段不做 Step 1 统计能力扩展，先做语义收口

### B-003 Step 2 Layer 2 宽松匹配当前放宽范围大于文档描述

- 状态：confirmed
- 现象：
  - Step 2 的 Layer 2 当前只要 `cell_id` 为非碰撞且未命中 Layer 1，就会按 `cell_id` 放宽命中
  - 文档原描述限定为“`operator_code` 或 `lac` 缺失”时才放宽
- 影响：
  - 当前实现与文档约束不完全一致
  - 但这部分暂不在本阶段改动逻辑，只作为已确认差异保留
- 相关模块/文件：
  - `rebuild5/backend/app/profile/pipeline.py`
  - `rebuild5/docs/02_基础画像.md`
- 建议处理：
  - 先保持代码逻辑不动
  - 后续再决定是收紧代码，还是继续调整文档对齐当前实现
- 确认结论：
  - 已确认当前不修改该逻辑，先继续推进后续模块审计

### B-004 Step 3 已将 tech_norm 纳入候选池与快照识别，并增加简化版 45 批清理

- 状态：done
- 现象：
  - Step 3 原先的候选池、快照 carry-forward 和 diff 仍按 `(operator_code, lac, cell_id)` 合并
  - 这会把不同 `tech_norm` 的对象混在一起
  - 同时候选池缺少明确的超时清理机制
- 影响：
  - 会产生跨制式混证风险
  - 候选池会持续膨胀，难以解释“长期不晋级对象”的去向
- 相关模块/文件：
  - `rebuild5/backend/app/evaluation/pipeline.py`
  - `rebuild5/backend/app/evaluation/queries.py`
  - `rebuild5/tests/test_pipeline_version_guards.py`
  - `rebuild5/docs/03_流式质量评估.md`
  - `rebuild5/docs/human_guide/03_Step3_流式质量评估.md`
- 建议处理：
  - 将 `tech_norm` 纳入 Step 3 候选池与快照识别键
  - 增加简化版候选池清理规则：连续 `45` 批未晋级即删除
  - 对未启用的 `dormant` 统计保留统计位并标注待开发
- 确认结论：
  - 已完成代码与文档对齐，测试已覆盖关键 SQL 约束

### B-005 Step 4 已修正 GPS 异常检测边界并补齐碰撞跳过统计

- 状态：done
- 现象：
  - Step 4 原先异常检测只看 `lon_raw/lat_raw`，未要求 `gps_valid=true`
  - 同时还会回头查 `collision_id_list` 做跳过判断，`collision_skip_anomaly_count` 也未真正计算
- 影响：
  - 可能把无效原始坐标当成异常
  - Step 4 继续承担了不必要的碰撞表依赖
  - 页面上的碰撞跳过统计没有真实值
- 相关模块/文件：
  - `rebuild5/backend/app/enrichment/pipeline.py`
  - `rebuild5/backend/app/enrichment/queries.py`
  - `rebuild5/backend/app/enrichment/schema.py`
  - `rebuild5/tests/test_pipeline_version_guards.py`
  - `rebuild5/tests/test_enrichment_queries.py`
- 建议处理：
  - 仅对 `gps_valid=true` 的原始 GPS 做异常检测
  - 直接复用 Step 2 已写入的碰撞标记，不再回查碰撞表
  - 为 `collision_skip_anomaly_count` 提供真实统计
  - 异常样本默认收口到最新批次
- 确认结论：
  - 已完成代码修复、文档对齐和测试补充

### B-006 Step 5 已修正 tech_norm 维护键和 BS/LAC 发布阈值

- 状态：done
- 现象：
  - Step 5 原先的 Cell 维护链路没有把 `tech_norm` 作为维护识别键贯穿到底
  - BS / LAC 发布阈值也与文档不一致
- 影响：
  - 不同制式的同号 Cell 会在维护链路中混证
  - BS / LAC 更容易被错误发布为 `qualified`
- 相关模块/文件：
  - `rebuild5/backend/app/maintenance/schema.py`
  - `rebuild5/backend/app/maintenance/window.py`
  - `rebuild5/backend/app/maintenance/cell_maintain.py`
  - `rebuild5/backend/app/maintenance/publish_cell.py`
  - `rebuild5/backend/app/maintenance/publish_bs_lac.py`
  - `rebuild5/backend/app/maintenance/queries.py`
  - `rebuild5/tests/test_publish_bs_lac.py`
  - `rebuild5/tests/test_pipeline_version_guards.py`
- 建议处理：
  - 将 `tech_norm` 纳入 Step 5 的核心 Cell 维护链路和查询映射
  - 将 BS / LAC 发布阈值严格改回文档口径
  - 文档同步修正 A 类碰撞扫描对象的 `tech_norm` 表达
- 确认结论：
  - 已完成代码修复、文档对齐和测试补充
