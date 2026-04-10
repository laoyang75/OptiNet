# 前端问题集中处理清单

> 目的：集中记录 `rebuild5` 前端的已确认问题，等问题梳理完整后再统一处理。

## 写入规则

- 只记录已经和用户讨论并确认的问题。
- 未确认的问题可以在对话里讨论，但不要写入本文件。
- 本文件用于集中处理，不代表发现后立刻修改代码。
- 每条问题尽量写清楚现象、影响、关联文件和建议处理方向。

## 条目模板

```md
### W-xxx 问题标题

- 状态：confirmed / ready / done
- 现象：
- 影响：
- 相关文件：
- 建议处理：
- 确认结论：
```

## 已确认问题

### W-001 ETL 接口类型层未完全和后端返回对齐

- 状态：confirmed
- 现象：
  - ETL 页面已经在对接真实后端接口
  - 但共享 API 类型定义仍有旧结构残留，和当前后端返回不完全一致
- 影响：
  - 前端类型检查和构建不稳定
  - 后续继续改 ETL 页面时容易误判接口结构
- 相关文件：
  - `rebuild5/frontend/design/src/api/etl.ts`
  - `rebuild5/frontend/design/src/views/etl/Fill.vue`
  - `rebuild5/frontend/design/src/views/etl/FieldAudit.vue`
- 建议处理：
  - 统一 ETL API 类型定义
  - 让共享类型层和当前后端单源返回保持一致
- 确认结论：
  - 已确认属于前端/UI 对齐问题，不是 Step 1 单源主流程错误

### W-002 数据集重建页面仍保留旧双源语义和展示口径

- 状态：confirmed
- 现象：
  - 当前数据准备已经改成单源入口
  - 但页面文案、接口命名和部分返回类型仍保留旧双源口径
- 影响：
  - UI 会继续传达“当前仍是双源准备”的旧心智
  - 页面展示和当前单源流程不完全一致
- 相关文件：
  - `rebuild5/frontend/design/src/api/system.ts`
  - `rebuild5/frontend/design/src/views/global/DatasetSelect.vue`
- 建议处理：
  - 将页面文案、命名和返回结构统一成单源口径
- 确认结论：
  - 已确认属于前端/UI 和接口展示未完全收口的问题

### W-003 配置页默认配置对象未和系统配置类型保持一致

- 状态：confirmed
- 现象：
  - 配置页使用的默认 `config` 对象没有和最新系统配置类型完全对齐
  - 当前至少缺少必填字段，导致 TypeScript 检查报错
- 影响：
  - 配置相关页面无法稳定通过前端构建
  - 页面初始化兜底状态和真实接口契约不一致
- 相关文件：
  - `rebuild5/frontend/design/src/views/config/AntitoxinRules.vue`
  - `rebuild5/frontend/design/src/views/config/PromotionRules.vue`
  - `rebuild5/frontend/design/src/views/config/RetentionPolicy.vue`
  - `rebuild5/frontend/design/src/api/system.ts`
- 建议处理：
  - 统一系统配置默认对象
  - 保证默认值结构和 `SystemConfigPayload` 完整一致
- 确认结论：
  - 已确认属于前端类型和默认态未同步的问题

### W-004 治理页面存在 TypeScript 收尾问题，当前不能稳定构建

- 状态：confirmed
- 现象：
  - 治理页面仍有未使用变量、未使用导入、空值类型未处理干净等问题
  - 这些问题会直接导致前端 build 报错
- 影响：
  - 治理页面相关代码还没有收尾到可稳定构建的状态
  - 后续继续迭代治理页面时会被这些工程噪音持续干扰
- 相关文件：
  - `rebuild5/frontend/design/src/views/governance/CellMaintain.vue`
  - `rebuild5/frontend/design/src/views/governance/GovernanceOverview.vue`
- 建议处理：
  - 清理未使用代码
  - 补齐空值类型处理
  - 先把治理页恢复到可稳定构建状态
- 确认结论：
  - 已确认属于前端工程收尾未完成的问题
