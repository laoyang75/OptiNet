# 统一 Gate 与校验清单

状态：统一稿
更新时间：2026-04-06
说明：每个 Gate 都是停机线；未通过则不得默认进入下一 Gate。

## Gate A：真相源与目录冻结

- 输入：`01_foundation`、`02_research`、`UI_v2`、`reference`
- 输出：唯一真相源清单、三线边界、docs 目录结构冻结
- 校验：
  - 文档：只允许 `rebuild4/docs` 作为执行引用主入口
  - 路径：不存在并行总 prompt
  - Playwright：N/A
- 未通过处理：停止进入 schema 与实现

## Gate B：rebuild2 继承真相冻结

- 输入：数据清洗线草案 + PG17 查询结果
- 输出：字段审计、目标字段、ODS 规则、trusted 损耗的正式基线
- 校验：
  - PG17：`field_audit 17/3/7`、`target_field 55`、`parse/compliance 0/0`、ODS `26 vs 24`、trusted 损耗数值
  - API：N/A
  - Playwright：N/A
- 未通过处理：不允许进入治理页和初始化页的正式设计

## Gate C：实体合同与映射矩阵冻结

- 输入：流转线草案 + UI 线草案
- 输出：`run/batch/baseline/snapshot/object/fact_layer` 合同，页面矩阵冻结
- 校验：
  - 文档：每个 P0/P1 页面都有主语、API、表、来源
  - API 设计：所有读模型要求返回 `data_origin`
  - Playwright：N/A
- 未通过处理：不允许开始页面实现

## Gate D：schema 与元数据底座落地

- 输入：前 3 个 Gate 冻结结果
- 输出：`rebuild4`、`rebuild4_meta` schema 与关键元数据表
- 校验：
  - PG17：表、索引、关键列存在
  - API：最小空返回结构已可用
  - Playwright：仅做基础路由 smoke（如有页面壳）
- 未通过处理：不允许接入正式 UI 页面

## Gate E：P0 继承真相入库并可读

- 输入：数据清洗线继承/补建实现
- 输出：治理真相表、差异台账、质量解释词典、trusted 损耗读模型
- 校验：
  - PG17：摘要数字与冻结文档一致
  - API：`/governance`、`/initialization` 可返回继承真相
  - Playwright：治理页显示字段审计、ODS 规则、trusted 损耗，且来源说明正确
- 未通过处理：初始化页不得宣称“数据已准备完成”

## Gate F：真实初始化数据跑通

- 输入：真实 initialization 数据准备与流程实现
- 输出：至少 1 个 `real run`、1 个 `real batch`、1 个 `baseline_version`、对象结果与四分流统计
- 校验：
  - PG17：run/batch/baseline/object/fact 均有真实记录
  - API：`/runs` `/flow/overview` `/baseline` `/objects` 返回 `real`
  - Playwright：P0 页面首屏可见真实上下文
- 未通过处理：不得把 `synthetic` 升格为默认正式主语

## Gate G：真实 snapshot 与增量链路跑通

- 输入：真实 timepoint 与 incremental 数据
- 输出：至少 1 套真实 snapshot 链、至少 1 个真实 incremental batch
- 校验：
  - PG17：snapshot 链与 baseline 承接完整
  - API：`/flow/snapshot` 和 overview delta 返回 `real`
  - Playwright：时间点切换、批次切换、baseline 承接可见
- 未通过处理：`/flow/snapshot` 只能保留 empty 或评估模式，不得正式通过

## Gate H：对象与画像链路验收

- 输入：对象详情、画像页、对象下钻链路
- 输出：`objects -> detail -> profile -> baseline` 闭环
- 校验：
  - PG17：对象主键、状态、聚合字段可追溯
  - API：对象列表/详情/画像接口字段口径一致
  - Playwright：下钻链路不断，字段标签符合冻结口径
- 未通过处理：不允许仅通过首页验收

## Gate I：支撑治理与对照模块验收

- 输入：`governance` 与 `compare`
- 输出：明确来源状态的支撑模块
- 校验：
  - PG17：输入事实或降级占位来源可追溯
  - API：`data_origin` 与 `origin_reason` 可见
  - Playwright：`fallback/synthetic/real` banner 与文案符合合同
- 未通过处理：不得宣称 compare/governance 为正式实时模块

## Gate J：全链路回归与归档

- 输入：全部 P0/P1/P2 页面与接口
- 输出：可归档的验收记录、差异清单、运行说明
- 校验：
  - PG17：关键摘要可回勾
  - API：抽样接口与 SQL 一致
  - Playwright：至少跑 1 条主流程链 + 1 条支撑治理链
- 未通过处理：不得冻结为最终任务完成
