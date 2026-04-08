# rebuild3 面向 AI 的技术骨架与待确认事项

## 0. 第三方阅读说明

本文虽然面向 AI / 工程实现者，但仍按“业务职责先于代码细节”的方式组织。即使读者不能访问当前仓库，也可以按下面的约定理解：

- 文中的表名大多是“建议名称”，用于表达职责边界，不要求当前数据库已经存在同名表。
- `legacy` 表示更早一轮静态研究结果与原始输入。
- `rebuild2` 表示上一轮本地验证结果，已经验证过静态规则，但还不是动态治理系统。
- `Layer/Step` 是历史阶段名。本文引用它们只是为了说明继承来源，不建议在 rebuild3 中继续把它们当成系统主语。
- `fact_governed` 可以直接理解为“系统正式接受的治理后事实”。
- `candidate / observation / issue` 可以直接理解为“等待池 / 观察池 / 异常分流池”。

## 1. 设计总原则

rebuild3 的技术骨架应遵守以下原则：

1. 先保留现有解析契约和静态规则，不先重写业务哲学。
2. 初始化与增量共享同一条治理主骨架，只在输入窗口和状态起点上不同。
3. 主语从 `Layer/Step` 切换为 `object + decision + fact + baseline + version`。
4. 旧 `legacy` / `rebuild2` 表族保留为初始化输入、回归参照和规则对照。
5. 首轮实现优先“状态清楚、准入清楚、版本清楚”，不优先做重平台。
6. 冷启动仍可沿用 `LAC -> Cell -> BS` 的建库顺序，但动态增量以 `Cell` 为最小治理单元。
7. 北京 7 天样本上的严格 GPS/LAC 过滤属于研究策略，不应直接固化为全国化长期规则。

## 2. 核心对象族与建议表族 / 模块族

建议按“稳定对象 + 决策对象 + 证据对象 + 版本对象”组织。

| 对象族 | 建议表/模块族 | 作用 |
| --- | --- | --- |
| 源与批次 | `meta_source_registry`、`meta_batch_registry`、`meta_contract_registry` | 描述源表、批次、契约版本与回放窗口 |
| 标准事件 | `ods_std_event`、`ods_parse_error` | 统一承接 `cell_infos / ss1` 解析结果与错误留痕 |
| LAC 对象 | `obj_lac_registry`、`obj_lac_state_history` | LAC 当前状态、历史状态与版本归属 |
| BS 对象 | `obj_bs_registry`、`obj_bs_state_history`、`obj_bs_relation_history` | BS 当前主档、状态和关系历史 |
| Cell 对象 | `obj_cell_registry`、`obj_cell_state_history`、`obj_cell_relation_history` | Cell 当前主档、状态和关系历史 |
| 等待/观察对象 | `obj_candidate_pool`、`obj_observation_pool` | 未正式注册对象的累计与晋升容器 |
| 治理后事实 | `fact_governed` | 系统接受的事件事实底盘 |
| 待判定事实 | `fact_pending_observation`、`fact_pending_issue` | 等待/观察或异常待判定事实 |
| 拒收事实 | `fact_rejected` | 不合规或明确拒收的事件 |
| 画像与基线 | `profile_lac_baseline`、`profile_bs_baseline`、`profile_cell_baseline`、`baseline_registry` | 三级画像、可信度与基线版本 |
| 异常与问题 | `issue_event`、`issue_object_snapshot`、`issue_rule_case` | 异常分流、研究样本、规则试验 |
| 决策与转移 | `decision_event_result`、`decision_object_transition` | 每批次每条事件、每个对象的处理结果 |
| 运行版本 | `run_registry`、`version_binding` | run/batch/contract/rule/baseline 绑定关系 |

首轮实现时不要求一次把所有表都做满，但对象注册、待判定事实、治理后事实、画像基线、运行版本五类必须先有。

补充说明：如果第三方读者看不到代码，可以把本节理解为“rebuild3 最少要把哪些信息长期存下来”。表名只是这些信息容器的建议命名。

这里再加一条优先级判断：

- `obj_cell_registry` 是动态治理第一主语；
- `obj_bs_registry` 是空间锚点和影响传播主语；
- `obj_lac_registry` 是边界与区域级健康主语。

## 3. 初始化与增量共用的技术骨架

建议统一成 7 步：

### 步骤 1：批次注册

输入：

- 源表；
- 时间窗口；
- 契约版本；
- 运行类型。

输出：

- `run_id`
- `batch_id`
- `contract_version`

### 步骤 2：标准化事件生成

复用：

- `cell_infos` / `ss1` 解析；
- LAC / Cell / BS 派生；
- 合规规则。

输出：

- `ods_std_event`

### 步骤 3：对象与基线查找

对每条标准事件查找：

- 当前是否已有 LAC / BS / Cell 注册对象；
- 当前对象处于何种生命周期状态；
- 当前对象健康状态与基线版本。

### 步骤 4：决策分流

输出到：

- `fact_governed`
- `fact_pending_observation`
- `fact_pending_issue`
- `fact_rejected`

### 步骤 5：对象证据累计与状态转移

按对象键累计：

- 批次证据；
- 观察窗口证据；
- 异常证据；
- 晋升 / 降级 / 退役证据。

### 步骤 6：画像与可信度刷新

对正式对象刷新：

- LAC / BS / Cell 画像；
- GPS / signal 可信度；
- 基线版本。

### 步骤 7：回归与重算钩子

根据变更类型决定：

- 只更新对象局部；
- 局部重算对象；
- 全局完整回归。

初始化和增量唯一的区别：

- 初始化默认对象注册表为空，输入窗口长；
- 增量默认对象注册表和基线已存在，输入窗口短。

建议再补一个本地验证运行类型：

- `bootstrap_3d_then_roll_to_7d`

用于当前阶段把“3 天起跑 -> 增量滚到 7 天 -> 对比直接 7 天结果”变成显式验证模式。

## 4. 各对象的最小状态机

### 4.1 推荐的状态表达方式

不建议把所有情况压成一个超大状态枚举。

建议拆成两轴：

1. `lifecycle_state`
2. `health_state`

这样可以避免 `trusted_dynamic_migration_pending` 这种难维护的组合状态。

### 4.2 生命周期状态

所有对象族通用：

| 状态 | 含义 |
| --- | --- |
| `candidate_waiting` | 首次出现，样本不足 |
| `candidate_observing` | 已进入观察，等待稳定性判断 |
| `trusted_active` | 正式对象，可参与准入和画像 |
| `trusted_watch` | 正式对象，但近期需要观察 |
| `retiring` | 长期不再活跃或被新关系替代 |
| `retired` | 已退役，只保留历史 |
| `rejected` | 明确拒收，不进入正式对象 |

### 4.3 健康状态

所有对象族可复用：

| 状态 | 含义 |
| --- | --- |
| `healthy` | 当前健康，可作锚点 |
| `insufficient` | 当前证据不足 |
| `gps_bias` | 主要是 GPS 偏差问题 |
| `collision_suspect` | 疑似碰撞 |
| `dynamic_suspect` | 疑似动态对象 |
| `migration_suspect` | 疑似迁移或关系切换 |
| `split_pending` | 可能需要拆分重算 |
| `manual_review` | 需要人工复核 |

### 4.4 LAC / BS / Cell 的最小差异

#### LAC

- 更强调合法性、区域边界和长期稳定性；
- 通常不会走 `split_pending`，更常见的是 `rejected`、`trusted_active`、`trusted_watch`、`retired`。

#### BS

- 最需要关注 `collision_suspect`、`dynamic_suspect`、`split_pending`；
- 当健康状态异常时，不应再继续作为 GPS 修正锚点。

#### Cell

- 最需要关注 `migration_suspect`、`dynamic_suspect`；
- 需要保留历史绑定关系，避免把“迁移”误写成“新对象”或“错误覆盖旧对象”。
- 是动态治理里的最小注册对象，应承接最低注册门槛、锚点门槛、画像成熟门槛三层判断。

## 5. 准入 / 等待 / 观察 / 晋升 / 降级 / 拒收 / 分裂 / 迁移 / 退役 判定矩阵

建议首轮先冻结以下矩阵：

| 场景 | 事实动作 | 对象动作 | 后续 |
| --- | --- | --- | --- |
| 对象已知，健康，事件在基线内 | 写入 `fact_governed` | 维持 `trusted_active + healthy` | 可参与画像刷新 |
| 对象已知，轻微漂移但未破坏主档 | 写入 `fact_governed`，加 drift 标签 | `trusted_watch` | 多批累计后决定是否刷新基线 |
| 对象已知，GPS 偏差，且对象仍健康 | 写入 `fact_governed`，按对象锚点修正 | `trusted_watch` 或维持健康 | 记录修正来源 |
| 对象已知，但疑似碰撞 / 动态 / 迁移 | 写入 `fact_pending_issue` 或“带标签治理事实” | 健康状态切到 `collision_suspect / dynamic_suspect / migration_suspect` | 暂停其作为补齐锚点 |
| 对象未知，样本不足 | 写入 `fact_pending_observation` | 建立 `candidate_waiting` | 继续累计 |
| 对象未知，样本已够但稳定性未够 | 写入 `fact_pending_observation` | 转 `candidate_observing` | 继续累计 |
| 观察对象满足晋升门槛 | 后续批次可写入 `fact_governed` | 升为 `trusted_active` | 刷新初始画像 |
| 观察对象长期不稳定或结构不合规 | 不写治理事实 | `rejected` | 留痕备查 |
| 正式对象被证实一分为二 | 暂停更新原对象 | 原对象 `split_pending`，新建候选对象 | 局部重算 |
| 正式对象被证实迁移 | 暂停直接覆盖现主档 | 原对象 `migration_suspect`，更新关系历史 | 需要迁移决议 |
| 正式对象长期不再出现 | 不影响历史事实 | `retiring -> retired` | 保留历史画像 |
| 记录本身绝对不合规 | 写入 `fact_rejected` | 对象无状态变化或记录异常命中 | 不参与后续画像 |

首轮实现不需要把“分裂”“迁移”的全部自动处理做完，但必须先为其留出状态和关系历史位置。

## 6. 已验证规则迁移清单

### 6.1 直接复用

| 类别 | 内容 | 来源 |
| --- | --- | --- |
| 输入解析 | `cell_infos` / `ss1` 解析规则 | `rebuild2/docs/01_字段契约_Layer0.md`、`05_ss1解析规则.md` |
| 派生规则 | 4G `/256`、5G `/4096` 派生 `bs_id` | `docs/data_warehouse/00_业务逻辑与设计原则.md` |
| 合规规则 | PLMN 白名单、LAC / CellID 合法范围、信号范围 | `rebuild2/docs/03_字段治理规则.md` |
| 可信对象主键 | LAC / BS / Cell 主键口径 | `docs/data_warehouse/02_项目现状与逻辑梳理_外部评审版.md` |
| 异常标签字典 | `normal_spread` 等 6 类 BS 标签 | `rebuild2/prompts/phase3_anomaly_bs_research_result.md` |
| 画像口径 | 三级画像、可信度、异常标记传递 | `rebuild2/prompts/phase4_profile_baseline.md` |

### 6.2 需调整后复用

| 类别 | 现状 | rebuild3 调整方向 |
| --- | --- | --- |
| 可信 LAC 阈值 | 当前多以北京 7 天窗口、严格 GPS 区域过滤和固定门槛表述 | 改为“研究期严格过滤”和“长期运行轻量过滤”两套口径；全国运行不再以严格 GPS 边界框为主规则 |
| GPS 修正阈值 | 当前主要是静态城市阈值 | 保留首轮阈值，但与对象健康状态和区域标签绑定 |
| 信号补齐 | 当前仅是后置补齐 | rebuild3 中补齐必须受对象状态和 donor 可信度门控 |
| 画像刷新 | 当前更多是静态汇总结果 | 改成“只有 `baseline_eligible` 事实参与刷新” |
| 异常分类 | 当前更多是研究表和样本页 | 改成正式异常事件和对象健康状态输入 |
| 完整回归 | 当前仍偏 Step 式表驱动 | 改成版本驱动的全局/局部重算机制 |
| Cell 样本门槛 | 当前多以固定活跃天数和样本量近似处理 | 改成“最低注册门槛 / 锚点门槛 / 画像成熟门槛”三层门槛，并允许高流量对象快注册、低流量对象长观察 |

### 6.3 暂不进入首轮实现

| 类别 | 原因 |
| --- | --- |
| 碰撞 BS 第二轮自动拆分重算 | 首轮先保证“能标记、能暂停锚点、能分流”，再做自动拆分 |
| 2G / 3G 完整支持 | 当前优先 4G / 5G |
| 外部真值源深度融合 | 属于后续增强项 |
| 云端物理分层与调度实现 | 本轮先本地冻结逻辑骨架 |

## 7. 补齐、画像、可信度、异常分类之间的依赖关系

建议按以下依赖顺序理解：

```text
标准事件
  ↓
对象查找 / 对象状态
  ↓
是否允许补齐
  ↓
治理后事实
  ↓
画像与可信度
  ↓
异常分类与状态转移
  ↓
反过来影响下一批准入与补齐
```

关键原则：

1. 画像不是只读汇总，它直接参与下一批准入。
2. 可信度不是展示字段，它决定对象能否继续当锚点。
3. 异常分类不是研究附属物，它要反向改变对象状态。
4. 补齐后的事实并非全部都能进入基线刷新，需要 `baseline_eligible`。

## 8. Cell 的三层门槛

这是本轮应补进 rebuild3 的关键技术点。

### 8.1 最低注册门槛

目标：

- 承认一个 `Cell` 已经可以被系统正式建档。

特点：

- 高流量对象可以很快通过；
- 低流量对象允许长时间累计；
- 当前先做参数化，不先写死固定天数。

### 8.2 锚点门槛

目标：

- 判断该对象是否已经可靠到可以参与 GPS 修正、信号补齐或影响上游准入。

说明：

- 这通常比最低注册门槛更严格；
- 已注册对象不一定自动获得锚点资格。

### 8.3 画像成熟门槛

目标：

- 判断该对象是否已经成熟到能稳定影响正式基线。

说明：

- 这通常又比锚点门槛更高；
- rebuild3 需要允许“已注册但尚未成熟”的对象长期存在。

## 9. 数据保留策略建议

既然 `Cell` 是最小治理单元，就要区分热数据和长期数据。

### 9.1 热明细

建议表族：

- `fact_cell_recent_detail`
- `fact_bs_recent_detail`

用途：

- 等待池；
- 观察池；
- 迁移判断；
- 近期异常复核；
- 增量回放。

策略：

- 只保留最近窗口；
- 观察中对象保留更细；
- 超大且稳定对象不必长期保留全部热明细。

### 9.2 长期汇总

建议表族：

- `agg_cell_daily_activity`
- `agg_bs_daily_activity`

用途：

- 活跃节奏；
- 基线成熟度；
- 缺失/暂停辅助判断；
- 长期趋势。

### 9.3 归档事实

建议表族：

- `fact_governed_archive`

用途：

- 审计；
- 回放；
- 完整回归。

## 10. run / version / batch / event_time / idempotency 的最小建议口径

### 10.1 run

建议 `run_registry` 至少包含：

- `run_id`
- `run_type`
- `source_name`
- `window_start`
- `window_end`
- `status`
- `triggered_by`

`run_type` 建议最小枚举：

- `init_bootstrap`
- `increment_2h`
- `historical_replay`
- `partial_recalc`
- `full_regression`

### 10.2 version

全局最小版本体系保持 4 个：

- `contract_version`
- `rule_set_version`
- `baseline_version`
- `run_id`

所有对象、事实、判定结果、画像都应能追溯到这 4 个标识。

### 10.3 batch

建议：

- `batch_id` 与 `run_id` 分离；
- 一个 `run_id` 可含一个或多个 `batch_id`；
- 2 小时批次由 `source_name + window_start + window_end` 唯一确定。

### 10.4 event_time

这是当前必须确认但尚未最终冻结的口径。

首轮最小建议：

1. 先把 `report_time = ts_std` 作为系统事件时间；
2. 另存 `source_cell_time`、`source_gps_time` 等原始时间；
3. 待确认 `cell_infos.timeStamp` 的绝对时间可用性后，再决定是否升级口径。

原因：

- 现有文档已指出 `cell_infos.timeStamp` 有相对时间特征；
- `ss1` 中又存在独立时间与 GPS 时间；
- 若不先拆成“系统事件时间 + 原始时间证据”，增量幂等会失稳。

### 10.5 idempotency

建议标准事件级幂等键至少由以下信息组成：

- `source_name`
- `source_record_id`
- `parsed_from`
- `source_group_seq`
- `source_cell_seq`
- `contract_version`

说明：

- 一条原始记录会拆成多条标准事件；
- 不能只用 `record_id`；
- 需要源适配层显式补齐 `source_group_seq / source_cell_seq` 这类展开序号。

## 11. 需要预留但暂不展开的接口边界

以下接口必须留口子，但首轮不必做全：

| 接口边界 | 说明 |
| --- | --- |
| 源表适配接口 | 兼容单表、双表、未来新源表 |
| 批次回放接口 | 用历史数据模拟 2 小时增量，包含“3天起跑后滚到7天”的验证模式 |
| 画像刷新接口 | 支持全量刷新和对象局部刷新 |
| 局部重算接口 | 面向对象、异常桶、规则命中范围 |
| 全量回归接口 | 契约或主口径变化时触发 |
| UI 读模型接口 | 面向对象状态、等待池、决策结果而不是只面向 Step |
| 规则实验接口 | 让异常研究不再只能写散乱中间表 |

## 12. 当前仍缺失、必须确认的信息清单

以下信息未确认前，不建议直接进入实现细节：

1. `event_time` 的最终口径。
2. 2 小时批次切分和迟到数据处理规则。
3. 当前首轮输入到底采用单张 `lac` 表、双表回放，还是两者都要兼容。
4. 未知对象从等待池晋升到观察池、再晋升正式对象的最小阈值。
5. 轻微漂移事件是否直接进入 `fact_governed`，以及是否允许参与基线刷新。
6. Cell / BS 发生 LAC 切换时，是视为迁移、映射异常，还是新对象。
7. `collision_confirmed / dynamic_bs / migration_suspect` 对 GPS 补齐是否一律禁用锚点。
8. 基线刷新周期是“每批微刷”还是“每日 / 每 N 批刷新”。
9. 谁负责拍板 `rule_set_version` 的升级和回归触发。
10. 当前 UI 一期是否新增对象状态页，还是先把状态信息并入现有页面。

补充说明：

- “对象多久算消失/退役”当前不应作为主阻塞，只需先保留参数位；
- 本轮重点是先跑通 3 天起跑、滚到 7 天、再和直接 7 天对比的验证闭环。

## 13. 当前已有 UI / 后端 API / 数据库结构的承接建议

### 13.1 可以原样承接

| 资产 | 原因 |
| --- | --- |
| `raw / audit / ods` 页面与 API | 仍然适合作为源适配与字段契约入口 |
| `anomaly / profile` 页面与 API | 适合作为异常研究和画像验证视图 |
| 历史研究结果表族（当前库名为 `legacy.*` 与 `rebuild2.*`） | 适合作为初始化输入与历史对照 |
| 当前契约与规则元数据表（当前库名为 `rebuild2_meta.*`） | 可继续承接元数据和版本绑定起点 |

### 13.2 只需轻量调整

| 资产 | 调整方向 |
| --- | --- |
| `trusted` API / 页面 | 从“只构建静态可信库”扩成“初始化对象注册结果 + 等待池入口” |
| `enrich` API / 页面 | 从“单次 Step 执行”扩成“批次治理执行 + 状态决策展示” |
| `profile` API / 页面 | 增加基线版本、对象状态、是否可作锚点等信息 |
| 前端导航 | 先补对象/批次读模型入口，不急着改整体框架 |

### 13.3 暂时不该优先动

| 资产 | 原因 |
| --- | --- |
| 全量 UI 信息架构重写 | 当前先要冻结状态和批次骨架 |
| 云端物理建模与调度 | 会分散本轮主任务 |
| 复杂 Agent 编排系统 | 当前协作方式已经够用 |

## 14. 风险点、优先级建议、进入实现前的阻塞项

### 14.1 最高优先级风险

1. 如果继续以 `Layer/Step` 为长期主语，增量治理会始终缺少对象生命周期。
2. 如果不先冻结 `event_time + batch_id + idempotency`，2 小时增量无法稳定重放。
3. 如果异常对象仍可继续充当 GPS / signal 锚点，会持续污染治理后事实。
4. 如果没有版本绑定，后续 UI、回归、比较和审计都会失去共同语言。
5. 如果把北京研究期的严格 GPS/LAC 过滤直接固化为全国长期规则，后续会出现明显过拟合。

### 14.2 建议优先级

1. 先冻结对象注册与状态机。
2. 再冻结批次、版本和幂等键。
3. 再冻结 `Cell` 三层门槛和数据保留策略方向。
4. 再把现有静态表映射成初始化输入。
5. 再做“3天起跑 -> 滚到7天 -> 对比直接7天”的回放验证。
6. 最后才进入具体 API / SQL / 页面补齐。

### 14.3 进入实现前的阻塞项

当前最少有 4 个阻塞项需要先确认：

1. `event_time` 最终口径。
2. 源表适配边界。
3. 等待/观察/晋升阈值。
4. 异常对象是否允许继续作为补齐锚点。

## 15. 本文结论

对后续 AI / 工程实现而言，rebuild3 的正确切入点不是“继续扩一个 Step”，而是先建立：

1. 对象注册表；
2. 批次与版本绑定；
3. 治理后事实与待判定事实分层；
4. 画像与异常反向驱动准入的闭环。

再加两点：

5. `Cell` 作为动态治理的最小主语；
6. “研究期严格过滤”和“长期运行轻量过滤”的边界拆分。

这几条一旦冻结，后续实现才能真正从静态研究迁移到持续运行型治理系统。
