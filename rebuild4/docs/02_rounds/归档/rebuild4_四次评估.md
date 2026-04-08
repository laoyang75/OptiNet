# rebuild4 第四次独立评审（只看任务执行流程闭环）

## 1. 明确问题

### 1.1 G0 的正式通过状态，在进入 G1 之前没有按同一套 Gate 机制闭合
- 严重级别：阻断级
- 涉及文件：`03_最终执行任务书.md`、`04_最终校验清单.md`、`05_本轮范围与降级说明.md`
- 证据原文：
  > `G0 只负责冻结包只读校验；G1 的第一个原子动作必须是 raw 时间跨度预检；只有 P1-G1-01 通过后才允许首个数据库写入落到 P1-G1-02。`

  > `在 P1-G1-01 通过后，创建 rebuild4、rebuild4_meta 两个 schema，并建立最小控制表：contract_version、rule_set_version、source_adapter、gate_definition、gate_check_item、gate_run_result。`

  > `gate_run_result.evidence_ref 必须固定指向 rebuild4/runtime_artifacts/gate/{package_id}/{gate_code}/index.json；各 step 的原始证据由同目录下的 {step_id}.* 提供，且必须被 index.json 收录。`
- 会导致什么执行偏差：
  G0 被定义成“必须先过、且不写库”，但正式 Gate 状态表 `gate_run_result` 要到 G1 才存在。结果就是：G1 能否启动只能靠口头确认、临时文件或事后回填；这会把“先过 Gate 再进下一阶段”变成“先执行再补 passed 记录”，Gate 链路起点不是真闭环。
- 建议我带回主 agent 核查的一句话问题：
  `G0 的 passed 到底是独立于 DB 的正式状态，还是允许在 G1 建表后回填；如果允许回填，G1 启动前靠什么唯一机制判定 G0 已通过？`

### 1.2 SQL-only 步骤与证据归档规则互相打架，很多步骤没有可执行的落证主体
- 严重级别：阻断级
- 涉及文件：`03_最终执行任务书.md`、`04_最终校验清单.md`
- 证据原文：
  > `SQL 只负责产出查询结果，不直接写文件；凡步骤主体包含 SQL 且要求证据落盘，必须由同一步的 Python 脚本把 SQL 结果序列化落盘，再在确认文件存在后更新 gate_run_result。`

  > `### P1-G1-01 先执行双输入 raw 时间跨度预检`
  >
  > `- 执行主体：SQL`

  > `### P1-G1-02 创建 bootstrap schema 与最小控制表`
  >
  > `- 执行主体：SQL`

  > `gate_run_result.evidence_ref 必须固定指向 .../index.json；各 step 的原始证据由同目录下的 {step_id}.* 提供，且必须被 index.json 收录。`
- 会导致什么执行偏差：
  大量步骤在任务书里只指定 `SQL`，但总规则又要求“同一步的 Python 脚本”负责把 SQL 结果落成 step 证据文件。也就是说，步骤主体、落证主体、谁写 `index.json` 其实没闭合。真实执行时一定会出现三种分叉：有人只留 SQL 控制台输出，有人额外写临时导出，有人把落证动作塞进别的步骤。最后 Gate 是否能签 passed 会变成执行习惯问题，而不是合同问题。
- 建议我带回主 agent 核查的一句话问题：
  `所有 SQL-only 步骤是否都要补一个显式的 Python evidence-writer 子步骤/子主体，否则谁负责生成 step 文件并写入 index.json？`

### 1.3 “单 Gate 单 owner 签发”只写在文字里，没有数据结构可以真正约束
- 严重级别：高
- 涉及文件：`00_最终冻结基线.md`、`03_最终执行任务书.md`
- 证据原文：
  > `每个 Gate 只能有 1 名 gate owner 写 gate_run_result.status；多工程师或多 sub-agent 可以协作，但只有 gate owner 能签发 passed/failed 与汇总清单。`

  > `六文件任一内容发生实质变化，都必须生成新的 package_id 与新的 per-file version。`

  > `rebuild4_meta.gate_check_item | gate_code、step_id、check_method、pass_criteria、is_blocking`

  > `rebuild4_meta.gate_run_result | gate_code、package_id、status、executed_at、evidence_ref`
- 会导致什么执行偏差：
  现在表结构里没有 `gate_owner`、`attempt_id`、`superseded_by`、`contract_version_id` 一类字段，也没有把 `gate_check_item` 跟某个 `package_id` 绑定。多工程师 / 多子 agent 并行时，系统无法技术上区分“谁有权签发”“这是第几次尝试”“这个结果对应哪版 gate criteria”。结果就是可以口头说“只有 1 个 owner”，但数据库层无法防止覆盖、串版、串证据。
- 建议我带回主 agent 核查的一句话问题：
  `是否要把 gate_owner / attempt_id / package_id(或 contract_version_id) 明确落到 gate_definition / gate_check_item / gate_run_result，否则单签与升版如何被技术上约束？`

### 1.4 canonical seed artifact 到 parse/compliance 正式表的映射没有锁死，G1 仍会分叉
- 严重级别：阻断级
- 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
- 证据原文：
  > `必填列 | rule_family、rule_code、source_field、target_field、rule_logic、fail_action、severity、source_reference、conflict_resolution_note、is_active | 缺任一列都不得导入`

  > `row 粒度 | 1 行 = 1 条待导入规则 | 通过 rule_family 区分 parse_rule / compliance_rule`

  > `rebuild4_meta.parse_rule | rule_id、source_field、target_fields、parse_logic、source_reference、is_active、created_at`

  > `rebuild4_meta.compliance_rule | rule_id、rule_code、check_field、check_condition、fail_action、severity、source_reference、is_active、created_at`

  > `生成 canonical seed、登记 seed manifest 并导入 parse/compliance`
- 会导致什么执行偏差：
  这里缺的不是“有没有 seed”，而是“同一行 canonical seed 究竟怎么落到两张目标表”。现在至少有四个未锁死点：`target_field -> target_fields`、`rule_logic -> parse_logic/check_condition`、`source_field -> check_field`、以及 parse 家族里的 `rule_code/fail_action/severity` 到底保留还是丢弃。结果是两个工程师都能“成功导入”，但导入后的规则语义并不一定一致；而现有验收只卡 `row_count > 0`，挡不住这种分叉。
- 建议我带回主 agent 核查的一句话问题：
  `请主 agent 直接给出 canonical_seed.csv → parse_rule / compliance_rule 的逐列映射与 family 分流规则，否则 G1 seed 仍不是唯一实现。`

### 1.5 G3 current 切换规则前后冲突，API 很容易提前暴露 rolling
- 严重级别：阻断级
- 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
- 证据原文：
  > `current run | 若存在 completed real rolling run，则取最新一条；否则回落到唯一 completed real full_initialization run`

  > `切换触发 | 只有当第一个 rolling batch 已 completed，且对应 batch_snapshot、batch_flow_summary、baseline_refresh_log、timepoints 都已经落库后，才允许 current 从 initialization 切到 rolling`

  > `GET /api/flow-overview | 默认读取当前 non-rerun completed batch：若存在 completed real rolling run，则取其最新 non-rerun completed batch；否则回落到唯一 completed real full_initialization batch。`

  > `只有该记录为 passed 后才允许进入 P3-G4-01。`
- 会导致什么执行偏差：
  一套文字在说“只要存在 completed real rolling run，就取 rolling”；另一套文字在说“必须等 G3 handoff 完成且原子切换后，才允许 current 从 initialization 切到 rolling”。如果后端只按附录 B.1 实现 current 选取，就会在 G3 未正式交接前提前把 `/flow-overview`、`/runs/current` 指到 rolling，直接破坏你想要的“统一切换”与“G3 -> G4 阻断线”。
- 建议我带回主 agent 核查的一句话问题：
  `current run/current batch 的最终判定，到底是“数据上存在 completed rolling 就切换”，还是“必须受 G3 handoff/显式 current 标记控制”？`

### 1.6 任务书要求必建的多张表，在校验清单与 DDL 最小合同里没有同步成为“必验对象”
- 严重级别：高
- 涉及文件：`03_最终执行任务书.md`、`04_最终校验清单.md`
- 证据原文：
  > `建立正式业务层与控制层其余关键表：... baseline_version、baseline_refresh_log、baseline_diff_summary、baseline_diff_object、fact_standardized、四分流事实表、obj_cell / obj_bs / obj_lac、obj_state_history、obj_relation_history、... trusted_loss_summary、trusted_loss_breakdown、compare_job、compare_result。`

  > `P1-G1-03 ... fact_standardized、四分流、obj_*、batch_snapshot、baseline_version、trusted_loss_*、batch_anomaly_*、field_audit_snapshot、target_field_snapshot、ods_*_snapshot、seed_artifact_manifest、四张 asset 表全部存在，且关键唯一约束已生效。`
- 会导致什么执行偏差：
  任务书把 `baseline_refresh_log / baseline_diff_* / obj_state_history / obj_relation_history / compare_job / compare_result` 明确写成要建的正式表，但对应校验项没把它们列成 G1 必验对象，附录 D 也没给最小列集和关键约束。这样一来，实施方会把这些表理解成“最好有”而不是“必须有”；后面 G3/G6/G7 再来接 baseline、对象历史、compare 时，就只能临时补 schema 或各自发明结构。
- 建议我带回主 agent 核查的一句话问题：
  `这些在任务书里必建、但在校验清单/DDL 最小合同里缺席的表，哪些是正式必选，是否需要一次性补齐最小列集与验收项？`

### 1.7 观察工作台只冻结了页面字段，没有冻结正式数据落点，G2→G4 的链路没闭合
- 严重级别：高
- 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
- 证据原文：
  > `页面/接口必须出现的核心字段`
  >
  > `Stage 1 | existence_eligible | existence_progress、missing_detail`
  >
  > `Stage 2 | anchorable | anchorable_progress、missing_detail、trend_direction`
  >
  > `Stage 3 | baseline_eligible | baseline_progress、suggested_action、stall_batches`

  > `第三阶段的输出结果桶固定为：promoted_this_batch / converted_to_issue_this_batch`

  > `P2A-G2-03 ... 同步生成 obj_cell / obj_bs / obj_lac、batch_snapshot、batch_flow_summary、batch_transition_summary、batch_anomaly_object_summary、batch_anomaly_record_summary、batch_anomaly_impact_summary。`
- 会导致什么执行偏差：
  观察工作台的页面字段和验收口径写得很细，但 G2 产物里没有对应的正式 read model / summary 表，附录 D 也没有 observation 相关数据落点。于是 `/api/observation-workspace` 只能临时从 `obj_*`、`batch_*`、异常表里现场拼。不同实现者会给出不同的 `missing_detail / stall_batches / promoted_this_batch` 计算逻辑，页面看起来都能跑，但口径并不唯一。
- 建议我带回主 agent 核查的一句话问题：
  `观察工作台到底要不要补一张正式 read model / summary 表；如果不要，是否必须把运行时派生公式逐项冻结？`

### 1.8 附录 B / B.1 / C 的 query→context 归一化没有真正闭合，objects / profiles 最容易跑偏
- 严重级别：高
- 涉及文件：`01_最终技术栈与基础框架约束.md`、`03_最终执行任务书.md`
- 证据原文：
  > `API-04 | GET /api/objects + GET /api/objects/summary | ... | object_type、filter_lifecycle、filter_health、filter_qualification、baseline_version、contract_version`

  > `请求参数与 context 键允许不同名，但映射必须固定如下： lifecycle -> filter_lifecycle；missing_qual -> filter_missing_qual；sort -> sort_key；view -> view_mode；type -> filter_type；severity -> filter_severity ...`

  > `GET /api/objects | type、lifecycle、health、qualification、q、page、size | type 固定 cell / bs / lac`

  > `API-09 | GET /api/profiles/lac + GET /api/profiles/bs + GET /api/profiles/cell | ... | profile_type、filter_operator、filter_rat、filter_lac、filter_bs、filter_health_state、filter_qualification、baseline_version、contract_version`

  > `PF-08 | /profiles/lac | ... | profile_type=lac、filter_operator、filter_rat、filter_lifecycle_state、filter_health_state、filter_qualification、baseline_version、contract_version`
- 会导致什么执行偏差：
  这里至少有三处没锁死：  
  1) `/api/objects` 的 `type` 在参数表里被全局映射成 `filter_type`，但 API-04 要的是 `object_type`；  
  2) `health -> filter_health`、`qualification -> filter_qualification` 没写进统一映射表；  
  3) `profiles/lac` 在附录 C 需要 `filter_lifecycle_state`，但 API-09 的家族级 context 键里没列。  
  结果就是，后端、前端、合同测试三方很容易各自“都按文档理解”，但生成的 `context` 不同名。
- 建议我带回主 agent 核查的一句话问题：
  `是否把附录 B/B.1/C 改成 endpoint-scoped 的逐条映射，而不是现在这种家族级 + 全局映射混写？`

### 1.9 空态合同写在“API 家族”层，不在“endpoint”层，多个列表接口的数据形状仍然含糊
- 严重级别：高
- 涉及文件：`01_最终技术栈与基础框架约束.md`、`03_最终执行任务书.md`
- 证据原文：
  > `列表型空态 | /api/objects、/api/profiles/*、/api/observation-workspace、/api/anomaly-workspace 的列表响应 | data 形状 []`

  > `汇总/概览型空态 | /api/flow-overview、/api/flow-snapshot、/api/runs/current、/api/baseline/current、/api/initialization/latest、/api/governance/* | data 形状 {}`

  > `API-02 | GET /api/flow-snapshot/timepoints + GET /api/flow-snapshot | ... | data={} + subject_note=暂无快照数据`

  > `API-03 | GET /api/runs/current + GET /api/batches + GET /api/batches/:id/detail | ... | data={} + subject_note=暂无运行记录`

  > `API-11 | GET /api/governance/overview + fields + tables + ... + trusted_loss | ... | data={} + subject_note=元数据快照尚未初始化`
- 会导致什么执行偏差：
  你现在把 `timepoints`、`batches`、`governance/fields`、`governance/tables` 这类明显带列表语义的 endpoint，跟汇总 endpoint 放在同一个家族空态规则里统一写成 `data={}`。前后端一联调就会分叉：有人按列表接口返回 `[]`，有人按家族规则返回 `{}`；两边都能找到文档依据，G4/G8 的验收就会来回拉扯。
- 建议我带回主 agent 核查的一句话问题：
  `是否必须把 empty-state 规则下沉到每个 endpoint，而不是继续按 API 家族共用一个 data 形状？`

### 1.10 compare 的“是否阻断总通过”前后不一致，最终验收会失真
- 严重级别：高
- 涉及文件：`03_最终执行任务书.md`、`05_本轮范围与降级说明.md`
- 证据原文：
  > `compare 只用于重构验证与修复后的定向核对，不计入 12 个正式页面与正式完成标准。`

  > `M5 compare 降级链路 | compare 的辅助验证身份、banner 与空 fallback | G7`

  > `M6 前端工作台 | 12 个正式页面通过 Playwright 验收；compare 另作辅助验证页验收 | G8（P5-GPW-00 到 P5-GPW-11）`

  > `G8 只有在 P5-GPW-00 到 P5-GPW-11 全部 passed 且 index.json 汇总完成后才允许写成 passed。`
- 会导致什么执行偏差：
  一处说 compare “不计入正式完成标准”，另一处又把 compare 作为正式模块 M5，并且让 `P5-GPW-11` 进入 `G8 all passed` 的阻断条件。真实执行时就会出现两种完全不同的 release 判定：一组人认为 compare 失败不阻断总通过，另一组人认为 P11 失败则 G8 必定 failed。
- 建议我带回主 agent 核查的一句话问题：
  `compare 到底是“非正式完成标准”还是“正式模块但不计 12 页”；如果 P11 失败，是否阻断总通过，请主 agent 明确只保留一种解释。`

## 2. 待确认问题

### 2.1 rerun 到底是“增量补入”还是“整窗重算”，与全局事件幂等约束还没完全说死
- 严重级别：高（待确认）
- 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
- 证据原文：
  > `late data 策略 | 迟到数据进入 rerun batch；原批不改写，rerun 通过 is_rerun=true + rerun_source_batch_id 追溯`

  > `幂等键 | 事件级幂等键写入标准事实层；批次级幂等由 run_id + batch_seq + window_start + window_end 共同约束`

  > `rebuild4.fact_standardized | standardized_event_id、event_idempotency_key ... | event_idempotency_key 在正式主链内必须唯一`
- 会导致什么执行偏差：
  如果 rerun 是“整窗重算”，那 `event_idempotency_key` 全局唯一会跟重算写入冲突；如果 rerun 只是“补 late data 增量”，那 rerun batch 的口径又不是完整窗口快照。当前文本两种理解都能自洽，但实现结果完全不同。
- 建议我带回主 agent 核查的一句话问题：
  `请明确 rerun batch 存的是“整窗重算结果”还是“仅 late data 增量”，并据此回写 fact_standardized 的幂等约束。`

### 2.2 current `rule_set_version` 在 seed_manifest 回填前就被设为 current，是否允许对外可见需要再锁死
- 严重级别：中（待确认）
- 涉及文件：`03_最终执行任务书.md`
- 证据原文：
  > `P1-G1-04 ... 初始化 current rule_set_version 与双输入 source_adapter`

  > `rule_set_version.is_current=true 恰好 1 行`

  > `rule_set_version.seed_manifest_id 在 P1-G1-04 可以先为空，待 P1-G1-06 current seed manifest 生成后再回填。`
- 会导致什么执行偏差：
  现在存在一个窗口期：`rule_set_version` 已经是 current，但还没绑定 current seed manifest。有人会把它当“已可执行 current”，有人会认为“只是占位 current、G1 未完成前不可读”。如果这点不锁死，G1 末尾与 G2 起步之间会出现不同实现。
- 建议我带回主 agent 核查的一句话问题：
  `rule_set_version 在 seed_manifest_id 为空时，是否允许被任何 run / API 视为可执行 current？`

### 2.3 `approval_note` 被要求存在，但谁有资格写“已裁平并批准”没有明示
- 严重级别：中（待确认）
- 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
- 证据原文：
  > `approval_note | 必须写明冲突已在 artifact 内裁平`

  > `current canonical seed 只允许由 1 个 python:seed_builder 进程或 1 名指定 Seed Builder 生成`

  > `P1-G1-06 ... 由唯一 gate owner 指定 1 个 Seed Builder`
- 会导致什么执行偏差：
  现在能看出“谁生成 seed”，但看不出“谁批准 seed”。如果 `approval_note` 既能由 Seed Builder 自写，又能被 gate owner 代写，那冲突裁平其实仍可能是自审自批；多工程师场景下这会削弱 seed 的唯一性和可追责性。
- 建议我带回主 agent 核查的一句话问题：
  `approval_note 的签署责任到底归 Seed Builder、gate owner，还是需要独立审批人？`

## 3. 总体判断

这 6 份文件已经把**阶段顺序、主链来源、页面主语、降级边界**压得比较死，大方向不是问题；真正的问题出在“执行闭环最后一公里”还没有全部锁住。

当前最危险的不是方向分歧，而是**实施层会出现多种“都像符合文档”的做法**：  
- Gate 起点（G0）与证据写入机制没有完全同构；  
- SQL 步骤的落证主体没写实；  
- canonical seed 的导入映射没写死；  
- current 切换既像“数据存在即切换”，又像“必须等 G3 handoff”；  
- 附录参数表、校验清单、DDL 最小合同对若干正式对象没有完全闭合。

我的判断是：**主骨架已接近可执行，但还不能算“多工程师 / 多子 agent 并行下的无分叉闭环”**。  
如果不先修上面的明确问题，开发可以启动，但很大概率会在 **G1 seed、G3 切 current、G4 合同测试、G8 最终放行** 四个点出现实现分叉或验收失真。
