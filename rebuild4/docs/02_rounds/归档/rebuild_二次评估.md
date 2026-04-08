
# 明确问题

## Issue 1

* 严重级别：Blocker
* 涉及文件：`00_最终冻结基线.md`、`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
* 证据：

  * `执行期只允许引用本六文件；包外文件只能用于历史追溯，不能解释当前冻结口径。` 
  * `` `parse_rule` / `compliance_rule` 的 raw source 只允许来自以下白名单：... `rebuild4/docs/01_inputs/02_research/01_rebuild2_字段质量调查.md` ... `rebuild4/docs/02_rounds/round2_detail/outputs/claude/...` `` 
  * `按 seed_source_manifest 白名单先生成单一 canonical seed 导出物，再一次性导入 parse_rule 与 compliance_rule。` 
* 问题说明：

  * 文档一边要求“执行期只读六文件”，一边又把 G1 的 seed 生成正式依赖放到了包外文档与脚本白名单上。这样一来，G1 实际执行时必须回到冻结包外找依据，冻结包就不再自包含。
  * 对多工程师 / 多子 agent 协作来说，这会直接导致不同人引用不同包外材料版本、不同章节解释 seed 字段与冲突裁平规则，最终生成不同 canonical seed，而主文档又没有给出一个比包外材料更高优先级的封装件来封死这个分歧。
* 建议我带回主 agent 的问题：

  * G1 seed 的正式输入到底是“六文件内冻结产物”还是“允许读包外白名单”；若后者成立，是否必须把这些原料升格进正式包，或先补一份独立冻结的 canonical seed artifact？

## Issue 2

* 严重级别：High
* 涉及文件：`05_本轮范围与降级说明.md`、`03_最终执行任务书.md`
* 证据：

  * `G1 内必须先完成双输入 raw 上报时间 预检。` 
  * `P1-G1-01 创建 bootstrap schema 与最小控制表`、`P1-G1-03 在表创建后写入 current contract_version 与 Gate 定义`、`P1-G1-04 ... 完成 raw 时间跨度预检`。
* 问题说明：

  * 范围说明把 raw 时间跨度预检写成 G1 的“先完成”动作，但任务书里它排在建 schema、建表、写 current contract / gate 之后。也就是同一冻结包内，对 G1 的实际起跑顺序给了两种解释。
  * 这会带来真实执行偏差：如果 precheck 失败，团队是应该认为 G1 尚未开始，还是已经开始且需要回滚前面写入的 schema / contract / gate 数据？文档没有定义失败后的回滚边界，执行时极容易出现“有人先建表，有人坚持先预检”的抢跑。
* 建议我带回主 agent 的问题：

  * raw 时间跨度预检是否必须上提为 G1 的第一个原子步骤；若失败，之前的 schema / contract / gate 写入是否一律禁止或必须回滚？

## Issue 3

* 严重级别：High
* 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
* 证据：

  * `后续标准化得到的 fact_standardized.event_time 不得把该覆盖范围缩减到 < 4 小时而不显式上抛异常。` 
  * `P2B-G3-01 ... 基于 fact_standardized.event_time ... 按 ... 2 小时窗口切分 rolling batch。` 
* 问题说明：

  * 文档明确提出了一个关键执行风险：标准化后的 `event_time` 可能把原始 7 天跨度压缩到无法支撑 rolling。但任务书没有为这件事设置一个独立、可执行、可留痕的 Gate 检查项，只写了 raw 时间预检，然后就直接在 G3 用 `fact_standardized.event_time` 切窗。
  * 这意味着“显式上抛异常”只停留在口头要求，没有明确的执行主体、校验 SQL、产出证据和停机点。不同工程师可能有人在 G2 末检查、有人在 G3 开头检查、有人根本不检查，导致 rolling 能否启动并不收敛。
* 建议我带回主 agent 的问题：

  * 是否需要新增一个 G2→G3 之间的强制检查项，专门验证 standardized `event_time` 的实际覆盖范围，并把 `<4h` 定义成明确的阻断条件？

## Issue 4

* 严重级别：Blocker
* 涉及文件：`03_最终执行任务书.md`
* 证据：

  * `Phase 5 为 Playwright 总体验收，专用锚点使用 P5-GPW-00 到 P5-GPW-11。` 
  * `gate_check_item 已覆盖任务书全部锚点。` 
  * `gate_definition` 的约束是 `固定只允许 G0 到 G7 8 条`，而 `gate_check_item` 以 `(gate_code, step_id)` 唯一。
* 问题说明：

  * 任务书要求 `gate_check_item` 覆盖“全部锚点”，但 Phase 5 锚点是 `P5-GPW-*`，而 gate 体系只有 `G0-G7`，没有 `GPW` 对应的 `gate_code`。这在数据模型上是闭不上的：Playwright 条目到底挂在哪个 gate 下，文档没有给出可执行答案。
  * 结果就是验收证据闭环会断：要么 Playwright 结果无法正规落到 `gate_check_item / gate_run_result`，要么执行人临时把它们塞进 `G7` 或别的 gate，形成文档外解释。对多 agent 协作，这会直接造成验收归档口径不一致。
* 建议我带回主 agent 的问题：

  * Playwright 锚点准备挂在哪个正式 `gate_code` 上；是新增 `GPW/G8`，还是明确声明它们不进入 `gate_run_result` 体系？

## Issue 5

* 严重级别：Blocker
* 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
* 证据：

  * `允许回灌到 rebuild4_meta 的快照` 包含 `field_audit_snapshot`、`target_field_snapshot`、`ods_rule_snapshot`、`ods_execution_snapshot`、`asset_table_catalog`、`asset_field_catalog`、`asset_usage_map`、`asset_migration_decision`。
  * `P1-G1-05` 要把这些治理快照写入 `rebuild4_meta`，`P1-G1-06` 要完成四张 asset 注册表。
  * 但 `P1-G1-02` 的建表清单只列了 `run`、`batch`、`batch_snapshot`、`baseline_*`、`fact_*`、`obj_*`、`trusted_loss_*`、`compare_*` 等，并未正式列出上述 governance snapshot / asset 表；附录 D 也没有给这些表的最小列集与约束。
* 问题说明：

  * governance 正式能力要依赖的核心底座表，在“要写入什么”和“要展示什么”两个层面都已明确，但在“正式 DDL 合同”层面没有落表。这样执行时很容易出现三种分叉：有人临时建表、有人改成 view、有人直接回查旧 schema，最后都能勉强做出页面，但验收并不在同一合同上。
  * 同时，`trusted_loss_summary / trusted_loss_breakdown` 的建表责任在 `P1-G1-02` 和 `P1-G1-06` 被重复声明，说明 G1 内部表结构职责边界也有漂移。这个漂移和 governance snapshot / asset 表的缺失叠加后，会让 G1 很难并行协作而不互相踩边界。
* 建议我带回主 agent 的问题：

  * 是否要把 governance snapshot / asset 相关表全部补进 `P1-G1-02` 和附录 D，并把 `trusted_loss` 的建表责任固定到唯一一个步骤？

## Issue 6

* 严重级别：High
* 涉及文件：`05_本轮范围与降级说明.md`、`03_最终执行任务书.md`、`04_最终校验清单.md`
* 证据：

  * `Phase 3 (G4 / G5 / G6)` 被定义为同一阶段。
  * 校验清单写的是：`G4 只验统一 envelope 与来源语义；G5 才验 governance 完整性；G6 才验 baseline/profile 完整性。` 
  * 任务书里 `P3-G4-03` 已经把 `governance / profiles / compare` 都纳入同一顶层合同；后面 `P3-G5-01` 又实现 governance 12 组 endpoint，`P3-G6-01/02` 又交付 baseline/profile 接口。
* 问题说明：

  * 文档想表达“G4 先冻结合同，G5/G6 再补完整性”，但没有把这个意图写成 Phase 3 内部的强制顺序、交接产物和职责拆分。结果是同一批 endpoint 会跨 G4/G5/G6 反复被不同人修改。
  * 对并行协作最危险的地方在于：G4/G5/G6 的执行主体都还是笼统的 `Python 脚本`，而不是“谁先交接口骨架、谁后补聚合逻辑、谁负责 contract test、谁负责业务 test”。这会让不同子 agent 对“某接口做到什么程度算 G4 完成”产生不同理解。
* 建议我带回主 agent 的问题：

  * Phase 3 内部是否要正式冻结为 `G4 -> G5 -> G6`，并分别定义每个 gate 的代码所有权、可交付物和禁止越界内容？

## Issue 7

* 严重级别：High
* 涉及文件：`01_最终技术栈与基础框架约束.md`、`03_最终执行任务书.md`
* 证据：

  * `具体页面/API 的 subject_scope、必填 context 键、空态规则统一以 03_最终执行任务书.md 的附录矩阵为准。` 
  * 但在同一份任务书里，`API-02` 的必填 `context` 是 `run_id、batch_id、contract_version`，而 `PF-02` 又写成 `run_id、batch_id、contract_version、rule_set_version`。
  * `API-04` 把对象列表的 `context` 写成 `object_type、筛选条件、baseline_version`，而 `PF-04` 又多了 `contract_version`；同时附录 B.1 只逐项冻结了 `batches` 与 `governance` 的 query/path 参数，没有冻结 `objects / profiles / observation-workspace / anomaly-workspace` 的正式 query 参数。
* 问题说明：

  * 文档已经把“附录矩阵”提升为唯一依据，但矩阵内部自己还存在必填 `context` 键不一致，以及“筛选条件”这种未枚举字段名的隐性自由度。这样前后端各自实现时，很容易出现一边把 `contract_version` 当必填、一边不回；一边叫 `object_type`、一边把筛选参数拆成别的名字。
  * 这类问题最难在后期收敛，因为页面可能能跑，Playwright 也可能只验证 DOM，但 contract 已经悄悄分叉。对于多 agent 并行实现，这是典型的“看似有合同，实际仍靠默认常识补空白”。
* 建议我带回主 agent 的问题：

  * 附录 B 和附录 C 谁是最终权威；未枚举的 `筛选条件` 是否要像 governance 一样逐项冻结成正式 query 参数表？

## Issue 8

* 严重级别：High
* 涉及文件：`04_最终校验清单.md`、`03_最终执行任务书.md`
* 证据：

  * `先做文档与 SQL 校验，再做 API 响应检查，最后做 Playwright 页面验收。` 
  * 但 `P3-G4-01`、`P3-G4-02`、`P3-G4-03`、`P3-G5-01`、`P3-G5-02`、`P3-G6-*`、`P4-G7-*` 在校验清单里的检查方式统一写成了 `目测`。
  * 同时附录 D 又给了 `gate_run_result.evidence_ref` 这种需要证据归档的结构。
* 问题说明：

  * API 合同层的 gate 被定义为先于 Playwright，但它们的验收方式却不是可重放的 contract test，而是“目测”。这会让 `evidence_ref` 失去统一承载物：有人贴截图、有人贴 curl 输出、有人只写结论，证据闭环天然不一致。
  * 对多工程师 / 多子 agent 协作，这个风险尤其大，因为“目测通过”没有统一基准。一个人看到 six-field envelope 就算过，另一个人会继续检查 `context` 键、空态、错误码和 banner。最终 G4-G7 会变成依赖 reviewer 主观经验，而不是依赖正式合同。
* 建议我带回主 agent 的问题：

  * G4-G7 是否必须补成可执行的 API 合同测试与固定证据格式，而不是继续允许 `目测` 作为正式 gate 通过条件？

# 待确认问题

## Issue 1

* 严重级别：Need Confirmation
* 涉及文件：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
* 证据：

  * `canonical seed 导出物` 被定义为正式执行唯一读取物。
  * 任务书对它的验收只要求 `parse_rule > 0`、`compliance_rule > 0`、`canonical seed 已有唯一来源说明`。
* 问题说明：

  * 我倾向认为 canonical seed 还缺少路径、文件格式、列级 schema、hash、版本号、导入行数和冲突裁平结果的冻结方式；否则即使大家都遵守同一白名单，也可能生成不同 seed。
  * 但文档没有明确说这些信息必须写在任务书里，所以我把它放在待确认而不是直接判定为 blocker。
* 建议我带回主 agent 的问题：

  * canonical seed 是否要补一份独立 manifest（路径 / hash / schema / row-count / producer / approval）来封死实现分歧？

## Issue 2

* 严重级别：Need Confirmation
* 涉及文件：`03_最终执行任务书.md`、`02_数据生成与回灌策略.md`
* 证据：

  * `GET /api/flow-overview` 的用途是 `当前 completed batch 概览`。
  * `GET /api/runs/current` + `GET /api/batches` 构成 run/batch 中心；rolling 又允许 `is_rerun=true` 与 `rerun_source_batch_id`。
* 问题说明：

  * 文档没有明说当 `full_initialization`、普通 rolling、rerun batch 同时存在时，“current”按什么规则选：最新 completed、最新 window_end、最新 created_at，还是优先 rolling 非 rerun。
  * 这会影响 `/flow-overview`、`/runs/current`、`/flow-snapshot/timepoints`、甚至页面 context bar 的一致性。
* 建议我带回主 agent 的问题：

  * `current run/current completed batch` 的唯一选取规则，以及 rerun batch 是否进入默认 timepoints / 默认总览，是否需要显式冻结？

## Issue 3

* 严重级别：Need Confirmation
* 涉及文件：`03_最终执行任务书.md`、`04_最终校验清单.md`
* 证据：

  * Phase 5 只写了 `打开 /flow-overview`、`打开 /runs`、`打开 /governance` 等页面动作。
  * 校验清单要求 Playwright 通过，但没有给 base URL、认证方式、测试账号、数据前置态、trace/screenshot 归档路径。
* 问题说明：

  * 我认为这会让 Playwright 的真实执行环境依赖默认常识，尤其是多 agent 并行跑验收时，很可能各自在不同 URL、不同数据态下执行。
  * 但文档也可能默认这些属于实施层，而不是冻结包层，所以先放待确认。
* 建议我带回主 agent 的问题：

  * Playwright 是否需要补一份最小执行 harness：base URL、auth 策略、数据前置态、产物归档目录与命名规则？

## Issue 4

* 严重级别：Need Confirmation
* 涉及文件：`03_最终执行任务书.md`、`05_本轮范围与降级说明.md`
* 证据：

  * `rebuild4_meta.run.run_type` 的约束仍包含 `scenario_replay`。
  * 但范围说明又写 `scenario_replay、mock 数据、手动拼装结果：禁止作为主链正式完成证据`。
* 问题说明：

  * 这不一定是矛盾，也可能只是为了给 compare 保留历史兼容 run_type。
  * 但如果不解释清楚，实施者会对“rebuild4 是否允许落 `scenario_replay` run，只是不计入正式完成”产生不同理解。
* 建议我带回主 agent 的问题：

  * `scenario_replay` 留在 `rebuild4_meta.run` 是为了 compare 辅助链路，还是应该从最终 DDL 枚举中移除以避免实现漂移？
