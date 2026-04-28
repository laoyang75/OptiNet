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

### W-005 Step 1 五页的页面语义仍强于当前实现，第一阶段需做小修复收口

- 状态：confirmed
- 现象：
  - Step 1 当前核心 ETL 流程有效
  - 但五个页面里仍存在“注册/管理/实时审计/纯解析统计”等过强表述
  - 这些表述会误导用户以为当前已支持多数据源管理、实时字段审计或纯阶段化统计
- 影响：
  - 页面表达和当前单活只读实现不一致
  - 用户会把尚未开发的能力当成已具备能力
  - 也会误读部分统计图表的实际口径
- 相关文件：
  - `rebuild5/frontend/design/src/views/etl/DataSource.vue`
  - `rebuild5/frontend/design/src/views/etl/FieldAudit.vue`
  - `rebuild5/frontend/design/src/views/etl/Parse.vue`
  - `rebuild5/frontend/design/src/views/etl/Clean.vue`
  - `rebuild5/frontend/design/src/views/etl/Fill.vue`
  - `rebuild5/docs/fix1/01_step1_UI小修复建议.md`
- 建议处理：
  - 第一阶段只做 UI 小修复
  - 统一把页面文案、空状态和边界说明收口到当前实现
  - 不在这一阶段扩展多数据源管理或复杂交互
- 确认结论：
  - 已确认 Step 1 当前优先级是“页面语义收口”，不是“补齐管理能力”

### W-006 Step 2 路由页需按当前实现做轻量 UI 收口

- 状态：confirmed
- 现象：
  - Step 2 页面当前只支持路由总览、碰撞摘要和 Path B 基础画像摘要
  - 文案曾把 `Path A=0` 写死，并且没有解释 Path C 的实际汇总口径
  - 文档中的筛选、样本、跳转、在线调参能力当前并未实现
- 影响：
  - 页面会误导用户对当前支持能力和统计口径的理解
  - 非冷启动场景下，固定文案会直接失真
- 相关文件：
  - `rebuild5/frontend/design/src/views/profile/Routing.vue`
  - `rebuild5/frontend/design/src/api/profile.ts`
  - `rebuild5/ui/04_基础画像与分流页面.md`
  - `rebuild5/docs/fix1/02_step2_UI小修复建议.md`
- 建议处理：
  - 保留轻量总览页
  - 增加动态 Path A 文案、Path C 口径说明、只读规则口径区
  - 把未实现能力明确标成待开发
- 确认结论：
  - 已确认 Step 2 当前优先级是“页面语义与支持边界收口”

### W-007 Step 3 评估页面已补候选池清理摘要，并将未启用统计标为待开发

- 状态：done
- 现象：
  - Step 3 页面原先没有展示候选池清理结果
  - 同时容易把“分钟级”误解成调度频率
  - 未启用的 `dormant` 统计也没有明确说明
- 影响：
  - 用户难以判断本批候选池有没有被清理
  - 页面表达会误导对 Step 3 运行节奏和能力边界的理解
- 相关文件：
  - `rebuild5/frontend/design/src/views/evaluation/FlowOverview.vue`
  - `rebuild5/frontend/design/src/views/evaluation/CellEval.vue`
  - `rebuild5/frontend/design/src/api/evaluation.ts`
  - `rebuild5/docs/fix1/03_step3_UI小修复建议.md`
- 建议处理：
  - 总流转页展示 `waiting_pruned_cell_count`
  - 将未启用的 `dormant` 统计标注为待开发
  - 统一把“分钟级”收口为“批内观察点去重”
- 确认结论：
  - 已按第一阶段 UI 小修复完成收口

### W-008 Step 4 知识补数页已收口为轻量概览，复杂筛选继续标为待开发

- 状态：done
- 现象：
  - Step 4 页面当前已能展示补数概览、字段级补数、donor 质量分布和最新批次异常样本
  - 但文档原本提到的运营商 / LAC / donor 质量 / 是否异常筛选仍未实现
- 影响：
  - 如果不收口文案，页面会继续传达“当前已支持复杂筛选”的错误心智
- 相关文件：
  - `rebuild5/frontend/design/src/views/governance/KnowledgeFill.vue`
  - `rebuild5/frontend/design/src/api/enrichment.ts`
  - `rebuild5/ui/06_知识补数与治理页面.md`
  - `rebuild5/docs/fix1/04_step4_UI小修复建议.md`
- 建议处理：
  - 保留轻量概览页
  - 明确异常样本仅展示最新批次
  - 将筛选能力统一标记为待开发
- 确认结论：
  - 已按第一阶段 UI 小修复完成收口

### W-009 Step 5 治理页已完成第一阶段 UI 收口

- 状态：done
- 现象：
  - Step 5 页面当前具备摘要卡片、异常筛选、列表展开和关键字段查看
  - 但部分文案仍混有旧术语，且文档对深度钻取能力表达过强
- 影响：
  - 会误导用户对当前治理页面能力边界的理解
- 相关文件：
  - `rebuild5/frontend/design/src/views/governance/CellMaintain.vue`
  - `rebuild5/frontend/design/src/views/governance/BSMaintain.vue`
  - `rebuild5/frontend/design/src/views/governance/LACMaintain.vue`
  - `rebuild5/ui/06_知识补数与治理页面.md`
  - `rebuild5/docs/fix1/05_step5_UI小修复建议.md`
  - `rebuild5/docs/fix1/00_全局UI收口说明.md`
- 建议处理：
  - 统一状态名到当前正式术语
  - 将 `dormant / retired` 过滤做成真实能力
  - 对未实现的深度治理工作台能力明确标注待开发
- 确认结论：
  - 已按第一阶段 UI 小修复完成收口
