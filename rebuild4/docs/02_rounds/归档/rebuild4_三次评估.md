# rebuild4 第三次独立评审报告

> 评审范围：`rebuild4/docs/03_final/00_最终冻结基线.md` 至 `05_本轮范围与降级说明.md` 共 6 份冻结文件  
> 评审时间：2026-04-06  
> 评审视角：任务执行流程是否真正闭合、可落地、可验收  
> 评审方法：逐条比对 Gate 顺序、前置条件、执行主体、预期产出、停机条件；交叉比对附录 B / B.1 / C / D 与任务书正文；识别会导致实际偏差的结构性歧义

---

## 1. 明确问题（确认存在执行偏差风险的条目）

---

### 问题 1：canonical_seed 生成主体与来源 **完全未定义**，G1 必然挂起

**严重级别：🔴 阻断级**

**涉及文件：**
- `03_最终执行任务书.md` P1-G1-06
- `02_数据生成与回灌策略.md` §3.3 / §3.3.1

**证据原文：**
```
执行主体：SQL + Python 脚本
执行动作：按 02_数据生成与回灌策略.md 第 3.3 节 canonical_seed_contract 生成单一 canonical_seed.csv
```
```
parse_rule 与 compliance_rule 的每条正式记录都必须带 source_reference，用于追溯其 canonical seed 来源
```
```
一旦历史来源之间发生冲突，必须先在 canonical seed artifact 中裁平；不得把冲突留给开发时临场判断
```

**问题核心：** 六文件任何地方都没有定义：
1. canonical_seed.csv 的内容从哪里来？合并哪些源表？用什么规则生成哪些 row？
2. 谁负责执行 seed_builder python 脚本？ 人工还是自动化？
3. 历史来源冲突的"裁平"由谁决策、写在哪里？

现在的状态是：`parse_rule / compliance_rule` 在 PG17 均为 0（`00_最终冻结基线.md` 第3.2节确认），`rebuild2_meta.parse_rule / compliance_rule` 也为 0/0。这意味着 canonical_seed.csv 不是从现有数据库数据导出的，而是要被人工创建。但人工创建的规范（字段含义、rule_logic 格式、来源约束）在六文件内完全缺失。

**会导致什么执行偏差：**
- 执行者无法生成 canonical_seed.csv，将自行发明内容，导致"能跑通但规则语义失控"
- 多执行者情况下每人可能生成不同版本，出现多份互相竞争的 current manifest
- G1-06 的停机条件（规则 seed 为空）无法区分"真正没规则"与"等待主 agent 告知规则内容"

**建议带回主 agent 核查的一句话问题：**
> canonical_seed.csv 的 N 条规则从何而来？是否有离线预生成文件或对应的 round2 决策文档，需要在六文件中补一个"seed_builder 构建指南"或"seed 预生成步骤"？

---

### 问题 2：G2 到 G3 的衔接节点 P2A-G2-06 证据归档路径与执行主体存在逻辑矛盾

**严重级别：🔴 阻断级**

**涉及文件：**
- `03_最终执行任务书.md` P2A-G2-06
- `02_数据生成与回灌策略.md` §5.1.2
- `04_最终校验清单.md` [P2A-G2-06]

**证据原文：**
```
执行主体：SQL + Python 脚本
执行动作：以当前 completed full_initialization batch 为对象，检查 fact_standardized.event_time 的最早/最晚时间...
gate_run_result.evidence_ref 固定指向 artifacts/gate/{package_id}/G2/P2A-G2-06.json
```

**问题核心：** 
1. `artifacts/gate/{package_id}/` 这个路径是文件系统路径还是数据库字段路径？六文件从未定义 `artifacts/` 目录在何处落地（服务器本地文件系统？S3？数据库内的 JSON 字段？）
2. `gate_run_result.evidence_ref` 是一个数据库表字段，但它存储的是文件路径字符串。那么文件本身存在哪里？谁负责写这个文件？
3. SQL 步骤能往文件系统写 JSON 文件吗？如果不能，谁来写？

校验清单 P2A-G2-06 的通过标准是：
```
gate_run_result.evidence_ref 已生成 P2A-G2-06 的固定 JSON 证据
```
但怎么验证这个 evidence_ref 指向的文件真实存在且内容正确，校验清单没有说。

**会导致什么执行偏差：**
- 实现者直接往 `gate_run_result.evidence_ref` 字段写路径字符串，但文件实际不存在，G2 表面"通过"
- 多工程师并行时，evidence 文件写在不同机器上，导致归档不共享，后续回溯无法找到文件
- G8 Playwright 的证据也用同一套规则，如果文件系统没有共识，G8 证据将是事实上的幽灵

**建议带回主 agent 核查的一句话问题：**
> `artifacts/gate/...` 文件的落地介质是什么（本地文件系统 / 共享存储 / DB JSON字段）？谁负责写文件、谁负责读文件校验？

---

### 问题 3：Phase 3 内部 G4→G5→G6 虽声明串行，但 **没有明确单 agent 还是多 agent 执行**，职责边界会被撕裂

**严重级别：🟠 高风险**

**涉及文件：**
- `03_最终执行任务书.md` §"Phase 3 内部顺序与职责冻结" (第172-179行)
- `04_最终校验清单.md` G4/G5/G6 条目

**证据原文：**
```
Phase 3 必须严格按 G4 -> G5 -> G6 推进，禁止不同执行者并行改写同一组 endpoint 的顶层合同
G5 只负责 /api/governance/*...不得回头重命名 G4 已冻结的主流程接口
G6 只负责 /api/baseline* 与 /api/profiles/*；不得在 G6 修改 governance 路由
```

**问题核心：**
1. "不同执行者"是指不同人工程师还是不同 sub-agent？文档用了两种措辞混用，但没有定义判定机制。
2. G4 完成后 G5 开始前，没有任何"交接验证"步骤——G5 执行者怎么知道 G4 确实通过了？只看 `gate_run_result` 数据库表吗？谁可以写 G4 的 `status=passed`？
3. G4 的停机条件是"暂停所有前端接数"，但如果多个 sub-agent 并行，哪个 agent 有权暂停其他 agent？
4. G5 endpoint 列表列了 12 组，G4 也说"G4 只冻结顶层来源语义"——但 `/api/governance/*` 在 G4 阶段 **已经需要**有顶层 six-field envelope，意味着 G4 必须部分实现 governance 接口骨架。谁来决定 G4 实现到什么深度？

**会导致什么执行偏差：**
- G4 工程师过度实现 governance（为了让 G4 合同测试通过），导致 G5 工程师被迫在已有实现上修改而非在骨架上构建，出现代码路径冲突
- G5 工程师发现 G4 骨架与自己的理解不一致，但 G4 已经 passed，无权重跑 G4，被迫在 G5 步骤内修改，导致 G4 的 passed 证据失效
- 并行 sub-agent 情况下，G5 agent 可能误读 G4 的 passed 状态，提前展开实现

**建议带回主 agent 核查的一句话问题：**
> G4 对 governance / profiles / compare 的"骨架实现深度"是否有明确的最小可通过定义，防止 G4 与 G5 工程师各自对同一 endpoint 做出不兼容的实现？

---

### 问题 4：`obj_cell / obj_bs / obj_lac` 的"对象晋升"逻辑 **完全缺失于执行步骤**，是 G2 的隐藏黑洞

**严重级别：🟠 高风险**

**涉及文件：**
- `03_最终执行任务书.md` P2A-G2-03
- `02_数据生成与回灌策略.md` §4.2（11步初始化语义 §5-7步）
- `附录 D`（DDL 最小合同 `obj_cell / obj_bs / obj_lac`）

**证据原文（初始化 11 步）：**
```
5. Cell 候选累计与晋升
6. 由 active Cell 派生 BS
7. 由 active BS 派生 LAC
```

```
执行动作：按冻结的 11 步初始化语义落库 initialization_step_log，并同步生成 obj_cell / obj_bs / obj_lac...
```

**DDL 最小合同：**
```
obj_cell / obj_bs / obj_lac：主键、lifecycle_state、health_state、anchorable、baseline_eligible、current_baseline_version、last_active_batch
```

**问题核心：**
11 步语义描述了"晋升"，但没有任何地方定义：
1. 什么条件触发 Cell 候选晋升为 active Cell？（进入 `obj_cell` 的门槛）
2. `anchorable`、`baseline_eligible`、`health_state` 的计算规则是什么？
3. `obj_bs` 由 `active Cell` 派生的算法是什么？BS 的 LAC 归属怎么决定？

这些是核心业务逻辑，任务书只是说"按初始化语义"，但初始化语义的具体实现规则不在六文件范围内。六文件是治理文档，不是需求规格书。但问题是：**六文件要求 P2A-G2-03 通过才能进 G3，而 G2-03 的通过标准只验表是否存在，不验对象派生逻辑是否正确。**

**会导致什么执行偏差：**
- 执行者自行实现晋升算法，表存在、数字守恒，但业务语义错误
- 验收清单只检查"异常读模型具备三种正式输出"，不检查对象晋升的业务准确性
- 因为 G2 Gates 没有对象晋升的验收项，错误会静默流入 G3/G4/G8，只在最终页面验收时才被发现

**建议带回主 agent 核查的一句话问题：**
> 对象晋升的业务规则（Cell 候选 → active Cell 的条件，以及三层对象的派生算法）是否已经在 round1-round3 的某个 merged 文档中定义？如果是，需要在执行任务书中给出引用指引或将核心规则内嵌。

---

### 问题 5：附录 B.1 的 context 键名称与附录 C 的 context 键名称存在**不一致**

**严重级别：🟠 高风险**

**涉及文件：**
- `03_最终执行任务书.md` 附录 B（第373-387行）
- `03_最终执行任务书.md` 附录 B.1（第388-429行）
- `03_最终执行任务书.md` 附录 C（第431-449行）

**证据原文：**

附录 B（API-06，observation-workspace）的必填 context 键：
```
run_id、batch_id、contract_version、rule_set_version、filter_lifecycle、filter_missing_qual、sort_key
```

附录 C（PF-05）的必填 context 键：
```
run_id、batch_id、contract_version、rule_set_version、filter_lifecycle、filter_missing_qual、sort_key
```
（此处一致）

但附录 B.1 对 `/api/observation-workspace` 参数描述：
```
lifecycle、missing_qual、sort、page、size
```
注意 `filter_lifecycle` vs `lifecycle`，`filter_missing_qual` vs `missing_qual`，`sort_key` vs `sort`

同样，附录 B（API-07，anomaly-workspace）的必填 context 键：
```
view_mode、filter_type、filter_severity
```

附录 B.1 的参数写法：
```
view、type、severity、trend、page、size
```
`view_mode` vs `view`，`filter_type` vs `type`，`filter_severity` vs `severity`

附录 C（PF-06）：
```
view_mode、filter_type、filter_severity
```
（与附录 B 一致，但与附录 B.1 不一致）

**会导致什么执行偏差：**
- 后端工程师参考附录 B.1 实现 query param 名（`view`、`type`、`severity`）
- 前端工程师参考附录 C 发送 context 键（`view_mode`、`filter_type`、`filter_severity`）
- 联调时参数对不上，双方均认为自己依据了正式合同，但两套合同本身冲突

文档声明"附录 B.1 只是参数补充，附录 C 只能逐项镜像，不允许另起口径"，但实际上附录 B.1 与附录 C 确实用了不同名字。

**建议带回主 agent 核查的一句话问题：**
> 附录 B.1 的 query param 命名（`view`、`lifecycle`、`sort`）与附录 C 的 context 键（`view_mode`、`filter_lifecycle`、`sort_key`）哪个是 API 实际的 query string 参数名称？context 键是 API 响应 envelope 里的字段还是请求参数？这两套名字是否本来就指不同层次？

---

### 问题 6：`batch_anomaly_object_summary` 中 `downstream_impact` 字段在 DDL 最小合同里**缺失**，但任务书和校验清单都要求它存在

**严重级别：🟡 中风险**

**涉及文件：**
- `02_数据生成与回灌策略.md` §6.2（对象级异常最小字段）
- `03_最终执行任务书.md` 附录 D（DDL 最小合同）
- `04_最终校验清单.md` [P5-GPW-06]

**证据原文（§6.2 对象级异常最小字段）：**
```
downstream_impact | 受影响对象列表或其聚合摘要
suggested_action  | 系统推荐动作
```

**附录 D 的 `batch_anomaly_object_summary` 最小列集：**
```
batch_id、object_key、object_type、anomaly_type、severity、forbid_anchor、forbid_baseline、discovered_batch、evidence_trend
```

`downstream_impact` 与 `suggested_action` 在 DDL 最小合同中**完全缺失**。

**校验清单 P5-GPW-06：**
```
页面可切换 object / record 两类异常，并能看到...downstream_impact / 影响链
```

**会导致什么执行偏差：**
- DDL 执行者建表时不加 `downstream_impact`，因为附录 D 没有要求
- API 实现者被 §6.2 要求返回这个字段，但表里没有，被迫在 API 层临时拼装
- G8 验收时如果有 `downstream_impact`，是拼装的；如果没有，就验收失败
- `suggested_action` 同理

**建议带回主 agent 核查的一句话问题：**
> 附录 D 的 `batch_anomaly_object_summary` 是否需要补充 `downstream_impact` 和 `suggested_action` 两列，还是这两个字段应该来自 `batch_anomaly_impact_summary` 的聚合，不需要在主表里存储？

---

### 问题 7：G1 建表顺序与外键约束存在循环依赖风险

**严重级别：🟡 中风险**

**涉及文件：**
- `03_最终执行任务书.md` P1-G1-02 / P1-G1-03 / P1-G1-04
- `03_最终执行任务书.md` 附录 D

**证据原文（附录 D）：**
```
rebuild4_meta.rule_set_version：seed_manifest_id（FK 指向 seed_artifact_manifest）
rebuild4_meta.seed_artifact_manifest：先创建，后被 rule_set_version 引用
```

但执行顺序：
- P1-G1-02：建 `contract_version`、`rule_set_version`、`source_adapter`、`gate_definition`...
- P1-G1-03：建 `seed_artifact_manifest`...
- P1-G1-04：写入 current `rule_set_version`

问题：`rule_set_version` 在 P1-G1-02 建表时声明了 `seed_manifest_id` 外键，但 `seed_artifact_manifest` 表在 P1-G1-03 才创建。如果 DDL 带外键约束，P1-G1-02 的建表 SQL 会因引用不存在的表而失败。

类似的问题：
```
rebuild4.fact_governed 的 standardized_event_id FK 指向 fact_standardized
```
两者都在 P1-G1-03 创建，但谁先谁后不确定，可能触发外键建立失败。

**会导致什么执行偏差：**
- 执行者遇到外键报错，选择去掉所有外键约束 → 约束形同虚设
- 或者重新排列建表顺序，但与任务书步骤不一致，导致 gate_check_item 的 step_id 记录与实际执行不对应

**建议带回主 agent 核查的一句话问题：**
> `P1-G1-02` 和 `P1-G1-03` 的建表 DDL 是否保证了外键声明的被引用表在引用表之前创建，或者附录 D 应明确哪些外键需要 DEFERRABLE 或分步建立？

---

### 问题 8：G3 完成后何时启动 Phase 3 (G4) **没有显式触发条件**，衔接完全依赖隐式理解

**严重级别：🟡 中风险**

**涉及文件：**
- `03_最终执行任务书.md` P2B-G3-04（最后一个 G3 步骤）
- `03_最终执行任务书.md` P3-G4-01（第一个 G4 步骤）
- `05_本轮范围与降级说明.md` §4.1

**证据原文（P2B-G3-04 停机条件）：**
```
若 timepoints 混入 scenario_replay、synthetic、fallback 或 rerun 记录，则暂停 /flow-snapshot 与 /runs 页面联调
```

**P3-G4-01 前置条件（缺失）：** P3-G4-01 没有任何显式的"进入前提"描述。任务书的 G4 章节直接开始执行动作，没有写"在 G3 全部步骤 passed 后方可进入"。

**05 文件 §4.1：**
```
Phase 2B (G3) -> Phase 3 (G4 -> G5 -> G6)
不允许跳过前置 Gate 提前展开后续阶段
```

但这是一个原则声明。具体执行步骤中没有 G3→G4 的显式交接节点（而 G0→G1 有"P0-G0-03 停机条件"作为隐式交接，G2→G3 有"P2A-G2-06"作为显式 blocking 检查）。

**会导致什么执行偏差：**
- 多 sub-agent 并行时，G4 agent 可能在 G3 尚未完成时提前启动，认为只要有 at least 1 completed rolling batch 就可以联调 API
- G3 的 P2B-G3-04 步骤（timepoints 纯洁性）失败，但 G4 已经开始，造成验收证据污染

**建议带回主 agent 核查的一句话问题：**
> 是否需要在 P3-G4-01 之前增加一个显式的"G3 全部步骤 gate_run_result 均为 passed"的前置检查步骤，类似 G2 的 P2A-G2-06 做法？

---

### 问题 9：`compliance_rule.severity` 枚举与 `batch_anomaly_object_summary.severity` 枚举**不一致**

**严重级别：🟡 中风险**

**涉及文件：**
- `03_最终执行任务书.md` 附录 D
- `02_数据生成与回灌策略.md` §6.2（对象级异常最小字段）

**证据原文：**

附录 D 的 `compliance_rule`：
```
severity 固定 critical/high/medium/low
```

§6.2 对象级异常：
```
severity | 固定为 high / medium / low
```

一个有 `critical`，一个没有。这两个 severity 虽然属于不同域（合规规则 vs 异常对象），但如果合规规则触发的异常对象继承了 `critical` severity，而异常表只允许 `high/medium/low`，写入就会失败或被截断。

**会导致什么执行偏差：**
- 合规规则发现 `critical` 级别违规，路由到 `fact_pending_issue` 时需要给对象打 severity，但对象表只有 `high/medium/low`，实现者需要自行映射（`critical` → `high`？），这个映射逻辑没有被冻结

**建议带回主 agent 核查的一句话问题：**
> compliance_rule 的 `critical` severity 触发的异常，在写入 `batch_anomaly_object_summary` 时应该映射为什么值，这个映射规则需要显式冻结。

---

### 问题 10：G8 Playwright 的 12 个页面验收**只规定了 Playwright 工具，没有规定任意单一页面验收失败时整个 G8 的处置策略**

**严重级别：🟡 中风险**

**涉及文件：**
- `03_最终执行任务书.md` Phase 5 / Gate G8（P5-GPW-00 至 P5-GPW-11）
- `04_最终校验清单.md` G8 条目

**证据原文（每个 GPW 步骤的停机条件都是）：**
```
则暂停 [某个] 页面上线
```

但没有统一的：
1. 如果 P5-GPW-01 失败，是否暂停 P5-GPW-02 至 P5-GPW-11？
2. 如果 P5-GPW-10 (governance) 失败，是否影响已通过的 P5-GPW-01 的 passed 状态？
3. 12 个页面验收全部 passed 的汇总条件是什么？谁来宣布 G8 整体通过？

直接风险：
- 执行者可能解读为"12 个并行跑，哪个失败就暂停那个，其余继续"
- 也可能解读为"必须全部串行、任一失败则暂停后续全部"
- 两种解读都有道理，但结果截然不同

**会导致什么执行偏差：**
- 多 Playwright 测试员并行执行时，各自认为自己只负责自己的页面，最终有 10 个通过、2 个失败，但 G8 是否通过无人能判定
- `gate_run_result` 对 G8 只有一行还是 12 行？attachments 在哪里汇总？

**建议带回主 agent 核查的一句话问题：**
> G8 的整体通过条件是"全部 12 个 GPW 步骤均 passed"，还是允许指定步骤豁免？以及 `gate_run_result` 是否需要为 G8 的每个 GPW 步骤各写一行，还是只写一行汇总？

---

## 2. 待确认问题（可能导致分叉，但有多种合理解读）

---

### 待确认问题 A：`current run / current batch` 选取规则在 `/api/flow-overview` 与 `/api/runs/current` 声明一致，但 **G2 阶段无 rolling 时的 current run 是 full_initialization，rolling 开始后 current run 切换——切换瞬间的处置未定义**

**涉及文件：** `02_数据生成与回灌策略.md` §5.1.3 / `03_最终执行任务书.md` 附录 B.1

**问题说明：** 当第一个 rolling batch completed 时，current run 从 full_initialization 切换为 rolling run。在这个切换瞬间，`/api/flow-overview` 的数据会突然从 initialization 数据跳变为第一个 rolling batch 数据。文档没有定义：这个切换是原子的吗？切换过程中 API 应该返回什么？前端是否需要特殊处理？

---

### 待确认问题 B：G5 的 12 组 governance endpoint 与附录 B（API-11）的扩展路径之间，`governance/overview` 被列为 API-11 家族，但 P3-G5-01 的 12 组能力列表没有 `overview`，有 `tables`

**涉及文件：** `03_最终执行任务书.md` P3-G5-01 / 附录 B API-11 / 附录 C PF-12

**证据原文（P3-G5-01 的 12 组）：**
```
overview、fields、tables、usage、migration、field_audit、target_fields、ods_rules、ods_executions、parse_rules、compliance_rules、trusted_loss
```
（共12个，含 overview）

附录 B API-11：
```
GET /api/governance/overview + fields + tables + usage + migration + field_audit + target_fields + ods_rules + ods_executions + parse_rules + compliance_rules + trusted_loss
```
（也是12个）

这里实际上是一致的，不是冲突。但 `governance/usage` 在附录 B.1 中写作：
```
GET /api/governance/usage/:table_name（path table_name）
```
带路径参数，而附录 B API-11 里把 `usage` 列为平铺的 12 组之一，没有说是 path 参数路由。待确认是否 `usage` 只有一个 endpoint `/api/governance/usage/:table_name` 而不是平铺的 `/api/governance/usage`。

---

### 待确认问题 C：`rerun batch` 的来源是 **late data**，但执行任务书和校验清单都没有说明 rerun batch 什么时候触发、由什么机制决定

**涉及文件：** `02_数据生成与回灌策略.md` §5.2 / `03_最终执行任务书.md` P2B-G3-01

**证据原文：**
```
late data 策略：迟到数据进入 rerun batch；原批不改写，rerun 通过 is_rerun=true + rerun_source_batch_id 追溯
```

**问题说明：** 在 `full_initialization` 模式下不存在 late data 问题，所以 G2 不需要 rerun。但 G3 里 late data 触发 rerun 的条件没有定义：
- 什么是"迟到"？相对于 window_end 多久以后到达的数据算迟到？
- 迟到数据的检测是实时的还是到下一个 rolling batch 时才检查？
- 如果是手动触发 rerun，谁来触发？

这个不确定性不影响 G3 的通过条件（G3 只要求"存在 completed real rolling run 且 completed batch > 1"），但会影响实现质量和后续 profile/observation 的正确性。

---

### 待确认问题 D：`initialization_step_log` 的 11 步是否每一步都必须对应一条独立的数据库记录，还是 11 步可以合并为单个状态字段

**涉及文件：** `03_最终执行任务书.md` P2A-G2-03 / 附录 D

**问题说明：** 附录 D 没有为 `initialization_step_log` 给出最小列集（出现在 P1-G1-03 的建表列表中，但 DDL 最小合同表里没有该表）。执行者可能合理地将 11 步合并为一个 JSONB 字段，或者每步一行。G2-03 的验收条件是"恰好 11 步"，但"11 步"是 11 行还是 11 个 key 不确定。

---

## 3. 总体判断

### 执行流程的整体闭合性评估

```
Phase 0 (G0) → Phase 1 (G1) → Phase 2A (G2) → Phase 2B (G3) → Phase 3 (G4→G5→G6) → Phase 4 (G7) → Phase 5 (G8)
```

| Gate | 前置条件 | 执行主体 | 预期产出 | 停机条件 | 闭合状态 |
|------|---------|---------|---------|---------|---------|
| G0 | 无（启动点） | Python脚本 | 六文件校验通过 | 文件缺失/版本不符 | ✅ 闭合 |
| G1 | G0通过 | SQL + Python | Schema建立、seed导入 | **canonical_seed来源未定义（问题1）、DDL建表顺序有循环依赖风险（问题7）** | 🔴 **有阻断风险** |
| G2 | G1通过 | SQL + Python | full_initialization完成 | **对象晋升逻辑缺失（问题4）、证据归档路径未定义（问题2）** | 🟠 有高风险 |
| G3 | G2的P2A-G2-06通过 | SQL + Python | rolling批次生成 | **G3→G4无显式交接（问题8）** | 🟡 有中等风险 |
| G4 | G3通过（隐式） | Python+HTTP合同测试 | 12个API家族骨架 | **参数命名不一致（问题5）、G4/G5边界模糊（问题3）** | 🟠 有高风险 |
| G5 | G4通过 | Python+HTTP合同测试 | governance 12组endpoint | 依赖G4正确，G4问题会传导 | 🟡 有中等风险 |
| G6 | G4通过 | Python+HTTP合同测试 | baseline/profile接口 | 依赖G4正确 | 🟡 有中等风险 |
| G7 | G6通过（隐式） | Python+HTTP合同测试 | compare降级验收 | 相对最干净 | ✅ 基本闭合 |
| G8 | 全部前置通过 | Playwright | 12页面验收 | **缺汇总通过判定（问题10）、证据归档路径未定义（问题2）** | 🟡 有中等风险 |

### 核心判断

**六文件在结构设计和边界冻结上完成度很高**，特别是：
- Gate 串行顺序清晰且有停机条件
- 数字基线冻结精确（PG17数字全部锁定）
- API合同骨架和附录矩阵覆盖完整
- compare降级语义和legacy_ref降级边界清晰

**但在"让人或agent真正可以拿着文件开始写代码"这一层面，仍有 2 个阻断级、3 个高风险问题未解决：**

1. **最高优先级（必须解决才能启动 G1）：** canonical_seed.csv 的构建指南 (问题1)
2. **次高优先级（必须解决才能安全通过 G2）：** 证据归档介质定义 (问题2)、对象晋升规则引用 (问题4)
3. **并行执行安全（多工程师/多agent时）：** G4/G5边界 (问题3)、G3→G4交接 (问题8)、G8汇总通过判定 (问题10)
4. **接口合同一致性（前后端联调时）：** 附录B.1 vs 附录C参数命名 (问题5)、DDL vs §6.2字段缺失 (问题6)、severity枚举不一致 (问题9)

**在问题1未解决前，建议不要开始 G1 执行；在问题2、3未解决前，建议不要进行多工程师/多agent并行执行。**

---

*本评审为纯文档分析，未修改任何冻结文件，未产生任何数据库写入操作。*
