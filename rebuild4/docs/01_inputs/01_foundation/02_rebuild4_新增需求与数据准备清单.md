# rebuild4 新增需求与数据准备清单

状态：任务书输入整理  
更新时间：2026-04-05

---

## 0. 本文档的目的

这份文档把 rebuild4 相对于 rebuild3 必须新增或必须写实的内容集中列出来，重点解决两个问题：

1. rebuild2 的数据清理细节如何正式纳入 rebuild4
2. rebuild4 如何保证系统完成后就有数据可用，而不是只交付页面壳子

---

## 1. 新增需求 A：把 rebuild2 数据清理细节变成正式可见能力

### 1.1 这项能力必须回答的问题

rebuild4 必须能让使用者直接看到以下信息：

- 原始字段哪些被保留、哪些被解析、哪些被丢弃
- ODS 清洗规则有哪些
- 每条规则影响了多少数据
- 这些影响来自哪些源、哪些解析通道、哪些制式
- trusted 过滤前后损耗多少
- 被过滤数据里仍有多少有效 GPS / 有效信号
- 最终治理结果与前面清洗/过滤动作之间如何串起来

### 1.2 当前已验证的数据来源

这部分在 rebuild2 中已经有基础，不需要从零设计：

- 字段审计：数据库表 `rebuild2_meta.field_audit`，本地说明副本见 `rebuild4/docs/01_inputs/04_reference/rebuild2_baseline/04_phase1_总结.md`
- ODS 规则定义：`rebuild2_meta.ods_clean_rule`
- ODS 执行统计：`rebuild2_meta.ods_clean_result`
- trusted LAC：`rebuild2.dim_lac_trusted`
- 标准化明细：`rebuild2.l0_gps`、`rebuild2.l0_lac`
- enriched 事实：`rebuild2.dwd_fact_enriched`

### 1.3 当前已验证的关键数字（2026-04-05 实时查询）

#### A. 字段审计

数据库真实结果：

- 总字段数：27
- `keep`：17
- `parse`：3
- `drop`：7

注意：

- `rebuild4/docs/01_inputs/04_reference/rebuild2_baseline/04_phase1_总结.md` 中写的是 `keep 19 / parse 3 / drop 5`
- 但 `rebuild2_meta.field_audit` 当前实表统计为 `17 / 3 / 7`
- rebuild4 正式任务书必须先解决这个口径差异，且默认以数据库元数据为优先真相源

当前数据库中的 `drop` 字段包括：

- `当前数据最终经度`
- `当前数据最终纬度`
- `android_ver`
- `基带版本信息`
- `arp_list`
- `imei`
- `gps定位北京来源ss1或daa`

#### B. ODS 清洗规则

数据库真实结果：

- `rebuild2_meta.ods_clean_rule` 定义了 26 条规则
- 组成如下：
  - `delete`：1
  - `nullify`：22
  - `convert`：3
- `rebuild2_meta.ods_clean_result` 当前仅记录了 24 条已执行统计

当前已发现的差异：

- 已定义但未出现在执行统计中的 2 条规则：
  - `NULL_WIFI_NAME_INVALID`
  - `NULL_WIFI_MAC_INVALID`

这意味着 rebuild4 不能只写“26 条规则”，还必须写清：

- 定义层有 26 条
- 当前执行统计层只有 24 条
- 缺失的是哪两条，原因是否是后续脚本未执行或统计未补录

#### C. ODS 清洗影响最大的规则（按执行统计）

`l0_lac`：

- `CONVERT_TS_STD`：43,771,306 行（100.00%）
- `CONVERT_GPS_TS`：42,361,870 行（96.78%）
- `NULL_OPERATOR_INVALID`：21,321,003 行（48.71%）
- `NULL_CELLID_ZERO`：9,817,904 行（22.43%）
- `NULL_CELLID_NR_PLACEHOLDER`：7,716,881 行（17.63%）
- `CONVERT_CELL_TS_SS1`：5,593,973 行（12.78%）
- `NULL_CELL_TS_CI_RELATIVE`：4,972,420 行（11.36%）
- `NULL_LAC_OVERFLOW_4G`：1,461,962 行（3.34%）

`l0_gps`：

- `CONVERT_TS_STD`：38,433,729 行（100.00%）
- `CONVERT_GPS_TS`：37,196,163 行（96.78%）
- `NULL_OPERATOR_INVALID`：18,721,069 行（48.71%）
- `NULL_CELLID_ZERO`：8,620,685 行（22.43%）
- `NULL_CELLID_NR_PLACEHOLDER`：6,775,866 行（17.63%）
- `CONVERT_CELL_TS_SS1`：4,911,831 行（12.78%）
- `NULL_CELL_TS_CI_RELATIVE`：4,366,072 行（11.36%）
- `NULL_LAC_OVERFLOW_4G`：1,283,687 行（3.34%）

#### D. trusted 过滤损耗

以 `rebuild2.l0_lac` 对 `rebuild2.dim_lac_trusted` 的结果为准：

- `l0_lac` 总行数：43,771,306
- trusted 命中：30,082,381
- 被过滤：13,688,925
- 被过滤比例：31.27%

这说明 rebuild4 任务书里必须有“trusted 过滤损耗说明”，不能只展示最终保留下来的结果。

#### E. 被 trusted 过滤掉的数据仍然包含有效信息

被过滤的 13,688,925 行中：

- 有 `RSRP`：12,017,352
- 有 GPS：11,350,552
- `2G`：233,772
- `3G`：92,937
- `4G`：10,004,716
- `5G`：3,357,500

这条事实很关键：

- 被过滤数据并不只是“明显无效垃圾”
- 其中大量仍是 4G/5G、且仍有 GPS / 信号的记录
- 所以 rebuild4 必须把“为什么这些数据仍被排除”解释出来

#### F. 被 trusted 过滤掉的数据来源分布

按 `数据来源 + 来源明细 + Cell来源` 聚合：

- `sdk / daa / cell_infos`：7,015,342
- `sdk / daa / ss1`：5,951,068
- `sdk / dna / cell_infos`：722,515

这意味着 rebuild4 的数据清理说明不能只按规则，还要按来源通道展示损耗。

### 1.4 rebuild4 必须新增的页面/模块能力

这部分至少要通过读模型或页面模块体现：

1. **字段审计视图**
   - 展示 keep / parse / drop
   - 能看到字段来源与决策说明
2. **ODS 清洗规则视图**
   - 展示规则定义、规则类型、影响行数、影响比例
3. **过滤损耗视图**
   - 展示 trusted 前后数量变化
   - 展示被过滤数据的来源构成、制式构成、GPS/信号保有量
4. **结果追溯视图**
   - 从最终治理结果反查其上游清洗和过滤链路

建议优先落在：

- `基础数据治理`
- `初始化数据`
- 必要时在 `流转总览` / `对象详情` 中提供跳转入口

---

## 2. 新增需求 B：把“先准备数据”写成正式任务，而不是隐含前提

### 2.1 rebuild4 必须改变的做法

rebuild3 的一个明显问题是：

- 系统结构与页面先做出来了
- 但很多主页面初期没有足够 real 数据可评估
- 后续只能靠 synthetic 评估模式补救

rebuild4 必须反过来：

- 先定义数据准备标准
- 再定义页面接数标准
- 最后才进入 UI / API 完整验收

### 2.2 rebuild4 最低可用数据集建议

正式任务书中至少应定义如下“最低可用数据集”：

#### A. 初始化数据

至少具备：

- 1 个 real `full_initialization` run
- 1 个对应的 real initialization batch
- 该 batch 可追溯到正式 `baseline_version`
- 初始化页面能展示真实上下文、真实对象数量、真实四分流摘要

#### B. 增量数据

至少具备：

- 1 条 real 增量 run 主链
- 该 run 下不止 1 个 completed batch
- `/flow/overview` 能以 real batch 为主语
- `/runs` 能展示真实批次序列与趋势

#### C. 快照数据

至少具备：

- 每个 completed batch 都写入 `batch_snapshot`
- 快照不是比例估算拼装值，而是批次完成后的真实写入结果
- `/flow/snapshot` 可以看到真实时间点，而不是只能靠 synthetic 场景

#### D. baseline 数据

至少具备：

- 当前 baseline version
- 如页面需要版本比较，则至少还有上一版 baseline version
- `/baseline` 页面不依赖 rebuild2 结果冒充“上一版”

#### E. 对照与治理数据

至少需要二选一：

- 要么本轮明确做 real compare / governance 数据链
- 要么在正式任务书中明确降级，并说明“不属于本轮完成标准”

### 2.3 当前 rebuild3 的现实提醒

2026-04-05 的现实状态是：

- `full_initialization`：有 1 个 real run
- `scenario_replay`：有 3 个 run，但仍是 synthetic 语义
- `batch_snapshot`：已有 142 个 batch 的 1,562 条快照指标
- `/compare`、`/governance`：仍有 fallback 历史包袱

rebuild4 不能复制这种“先有页面，后补数据语义”的路径。

---

## 3. 新增需求 C：把 real / synthetic / fallback 规则前置写进任务书

### 3.1 为什么必须前置

如果不在任务书阶段先冻结来源语义，后续极容易再次出现：

- synthetic 被当成真实时间点
- fallback 被当成正式主语
- 页面可以渲染，但用户无法判断自己看到的是哪类结果

### 3.2 rebuild4 建议继续沿用的来源合同

建议在任务书中直接冻结：

- `real`
- `synthetic`
- `fallback`

并要求每个核心读模型都返回：

- `data_origin`
- `origin_detail`
- `subject_scope`
- `subject_note`

### 3.3 页面验收规则

- 主流程页默认以 `real` 为目标主语
- `synthetic` 只能作为显式评估模式
- `fallback` 只能作为显式降级模式
- 没有真实数据且又不允许 synthetic/fallback 的页面，必须诚实空状态

---

## 4. rebuild4 正式任务书里建议新增的验收条目

### 4.1 数据清理解释层验收

必须能验：

- 字段 keep / parse / drop 数量与明细
- ODS 规则定义数量与执行数量
- 每条规则影响量与比例
- trusted 过滤损耗
- 来源通道损耗
- 最终治理结果可回溯到上游过滤动作

### 4.2 数据准备验收

必须能验：

- 是否存在 real initialization 数据
- 是否存在 real rolling batch 数据
- 是否存在 real batch_snapshot
- 是否存在 baseline 版本链
- compare / governance 是否已真实接数，若未接数是否已明示降级

### 4.3 页面与 API 一致性验收

必须能验：

- 页面主语是否与 API 主语一致
- API 的 `data_origin` 是否被前端消费
- 页面是否把来源状态清楚表达给用户
- 页面是否能用真实数据完成功能评估

---

## 5. 结论

rebuild4 相比 rebuild3，至少要把两件以前没有真正写进主任务书的事情补上：

1. **把 rebuild2 的数据清理与过滤细节正式纳入系统说明与页面能力**
2. **把“准备好可用数据”提升为与 schema / API / UI 同等级的正式交付项**

如果这两点不先写进正式任务书，rebuild4 仍然很容易重复 rebuild3 的偏移路径。
