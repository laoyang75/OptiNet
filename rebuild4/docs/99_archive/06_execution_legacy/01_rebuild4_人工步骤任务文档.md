# rebuild4 人工步骤任务文档

状态：执行稿
更新时间：2026-04-06
说明：这是 rebuild4 的唯一人工执行总任务书。所有实现、校验、归档都以本文件为准。

## 总执行规则

1. 任何步骤开始前，先确认其对应 Gate 已满足前置条件。
2. 每一步都必须记录：输入、输出、PG17 校验、API 校验、Playwright 校验、失败处理。
3. 若本步骤尚未涉及页面，Playwright 项必须明确写 `N/A`，不能留空。
4. 任一步骤校验失败，不得默认进入下一步。

## Step 1：冻结文档入口与真相源

- 输入：`rebuild4/docs/README.md`、`01_foundation/`、`02_research/`、`UI_v2/`、`reference/`
- 输出：冻结后的 docs 结构、引用清单、唯一任务书入口
- PG17 校验：N/A
- API 校验：N/A
- Playwright 校验：N/A
- 通过标准：所有实现说明只再引用 `rebuild4/docs`
- 失败处理：先修文档与路径，再继续

## Step 2：用 PG17 固化 rebuild2 继承真相

- 输入：`02_research/01_rebuild2_字段质量调查.md`
- 输出：`rebuild4` 的字段质量与损耗正式基线
- PG17 校验：
  - `field_audit = 17/3/7`
  - `target_field = 55`
  - `parse_rule/compliance_rule = 0/0`
  - ODS `定义 26 / 执行 24 / 缺口 2`
  - trusted 损耗与来源前三
- API 校验：N/A
- Playwright 校验：N/A
- 通过标准：所有数字写入正式基线文档且可复查
- 失败处理：停止进入 schema 设计

## Step 3：冻结实体合同与 data_origin 合同

- 输入：`05_unified/01_统一重构基线.md`
- 输出：实体合同、来源合同、compare/governance 定位裁决
- PG17 校验：N/A
- API 校验：设计文档要求所有读模型返回 `data_origin`
- Playwright 校验：N/A
- 通过标准：`run/batch/baseline/snapshot/object/fact_layer` 与 `real/synthetic/fallback/empty` 全部冻结
- 失败处理：不进入接口设计

## Step 4：冻结页面/API/表/data_origin 映射矩阵

- 输入：`05_unified/02_统一映射矩阵.md`
- 输出：P0/P1/P2 页面矩阵
- PG17 校验：核对每个页面依赖的逻辑表确实存在或已列为待建
- API 校验：每个页面都已定义关键读模型
- Playwright 校验：N/A
- 通过标准：P0 页面没有空行，没有“待定主语”
- 失败处理：不进入 UI 实施

## Step 5：建立 rebuild4 / rebuild4_meta schema 与元数据底座

- 输入：实体合同、数据清洗补建清单
- 输出：基础 schema、关键元数据表、索引、读模型视图
- PG17 校验：
  - schema 存在
  - 元数据表存在
  - 关键索引存在
- API 校验：基础空返回接口可访问
- Playwright 校验：若已有页面壳，仅做 smoke；否则 `N/A`
- 通过标准：DDL 落地且最小读接口可用
- 失败处理：不接下一步数据导入

## Step 6：导入并固化继承真相能力

- 输入：rebuild2 字段审计、目标字段、ODS 规则、损耗统计
- 输出：`rebuild4_meta` 中的治理真相表与差异台账
- PG17 校验：摘要数字与 Step 2 完全一致
- API 校验：`/governance`、`/initialization` 已可出继承真相数据
- Playwright 校验：
  - 打开治理页
  - 检查字段审计模块、ODS 规则模块、trusted 损耗模块存在
  - 检查 `data_origin` 与 `origin_reason` 可见
- 通过标准：治理页已不是空壳
- 失败处理：回退到 schema/导入逻辑修正

## Step 7：准备真实 initialization 数据并跑通主链路最小集

- 输入：正式初始化输入数据、规则版本、合同版本
- 输出：至少 1 个 `real run`、1 个 `real initialization batch`、1 个 `baseline_version_out`、对象聚合与四分流统计
- PG17 校验：run/batch/baseline/object/fact 五类实体均有真实记录
- API 校验：`/runs` `/flow/overview` `/baseline` `/objects` 返回 `real`
- Playwright 校验：
  - `/runs` 首屏有数据
  - `/flow/overview` 展示真实 batch 上下文
  - `/baseline` 显示真实 baseline_version
- 通过标准：P0 主链路不再依赖 synthetic 才能看数
- 失败处理：不得默认切回 synthetic 展示正式页

## Step 8：实现并验证 P0 主流程页面

- 输入：P0 页面矩阵与真实 initialization 数据
- 输出：`/runs` `/flow/overview` `/objects` `/baseline` `/initialization` 页面与读模型接口
- PG17 校验：抽样核对页面对应摘要值
- API 校验：主语、`data_origin`、关键摘要值一致
- Playwright 校验：
  - 每页首屏可打开
  - 主语可见
  - `data_origin` 可见
  - 关键 CTA 可点击
- 通过标准：P0 页面通过首屏验收
- 失败处理：返回矩阵与接口合同修正

## Step 9：实现真实 snapshot 与 incremental 链路

- 输入：真实 timepoint 生成逻辑、baseline 承接逻辑、增量数据准备
- 输出：真实 snapshot 链、真实 incremental batch、delta 读模型
- PG17 校验：snapshot 与 incremental 记录能回勾到 run/batch/baseline
- API 校验：`/flow/snapshot` 和 overview delta 返回 `real`
- Playwright 校验：
  - `/flow/snapshot` 可切时间点
  - overview 与 snapshot 能互相对齐当前 batch
  - baseline 承接信息可见
- 通过标准：不再需要 synthetic 才能评估 snapshot/增量
- 失败处理：页面保留 empty，禁止 silent synthetic

## Step 10：实现 observation / anomaly / object detail / profiles 下钻链路

- 输入：对象聚合、四分流数据、画像字段合同
- 输出：工作台页、对象详情页、LAC/BS/Cell 画像页
- PG17 校验：对象详情、资格状态、画像字段可追溯
- API 校验：对象列表/详情/画像接口字段一致
- Playwright 校验：
  - `/objects -> 详情 -> profiles` 链路不断
  - 字段标签符合冻结口径
  - 关键筛选与切换能驱动数据变化
- 通过标准：对象闭环可跑通
- 失败处理：不允许只验首页通过

## Step 11：实现 governance / compare 的支撑模块交付

- 输入：治理真相、对照语义与输入条件
- 输出：支撑治理模块与对照模块
- PG17 校验：治理事实可回勾；compare 的真实输入或降级原因可回勾
- API 校验：`data_origin`、`origin_reason` 与降级说明正确
- Playwright 校验：
  - `/governance` banner 与模块齐全
  - `/compare` 不抢占主流程入口
  - `fallback/synthetic` 提示清晰
- 通过标准：支撑模块表达真实，不冒充正式实时能力
- 失败处理：模块降级，不得虚报完成

## Step 12：执行 Gate 级全链路验收

- 输入：全部已实现页面、API、表
- 输出：验收报告、差异清单、归档记录
- PG17 校验：关键摘要、实体数量、来源状态抽样回勾
- API 校验：抽样接口与 PG17 一致
- Playwright 校验：
  - 主流程链：`/runs -> /flow/overview -> /flow/snapshot -> /objects -> detail -> /baseline`
  - 支撑治理链：`/initialization -> /governance -> /compare`
- 通过标准：Gate A-J 全通过
- 失败处理：回到对应 Gate，不得直接宣布重构完成

## Step 13：归档与冻结

- 输入：通过的验收记录
- 输出：冻结版文档、查询脚本、Playwright 脚本、差异台账
- PG17 校验：关键真相查询脚本可重跑
- API 校验：关键接口示例可重放
- Playwright 校验：关键用例脚本可重跑
- 通过标准：后续重构不再依赖口头记忆
- 失败处理：继续补归档，不得结束项目
