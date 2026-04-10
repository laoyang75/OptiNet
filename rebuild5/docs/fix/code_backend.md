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
