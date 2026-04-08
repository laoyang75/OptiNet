# rebuild4 第五次评估（仅聚焦任务执行流程闭环、落地性、可验收性）

> 评审范围：仅检查六文件在“执行顺序、前置条件、执行主体、产出、停机条件、跨 Gate 衔接、任务书/清单/DDL/范围说明对齐、多工程师/多 sub-agent 并行执行闭环”上的真实风险。
>
> 评审原则：不评价方向对不对，只指出**会导致开发偏差、实现分叉、验收失真**的问题；同时识别确实存在的**过度工程化**点，并优先建议收敛。

---

## 1. 明确问题

### 1.1 Gate 证据归档没有按 attempt 隔离，重试后证据会互相覆盖或污染
- **严重级别**：严重 / P0
- **涉及文件**：`00_最终冻结基线.md`、`03_最终执行任务书.md`、`04_最终校验清单.md`
- **证据原文**：
  - `00_最终冻结基线.md`：
    > “Gate 证据一律写入工作区相对路径 `rebuild4/runtime_artifacts/gate/{package_id}/{gate_code}/`；数据库只登记 repo-relative `evidence_ref`……”
  - `03_最终执行任务书.md`：
    > “`gate_run_result.evidence_ref` 只登记 repo-relative 路径，默认指向该 Gate 的 `index.json` 汇总清单；原始 step 证据固定落在同目录下的 `{step_id}.*`。”
  - `03_最终执行任务书.md` 附录 D：
    > “`gate_run_result` | `contract_version_id`、`gate_code`、`package_id`、`attempt_id`、`gate_owner`、`status_source`、`status`、`executed_at`、`superseded_by_attempt_id`、`evidence_ref`”
- **会导致什么执行偏差**：
  1. 文档允许 `gate_run_result` 存在多次 `attempt_id`，但证据路径只到 `gate_code`，没有 `attempt_id` 维度；一旦 Gate 重试，旧证据只能被覆盖、混放，或靠人工改文件名兜底。
  2. `evidence_ref` 永远指向同一个 `index.json`，自动验收无法判断“当前 passed 对应的是哪一次 attempt 的证据”。
  3. 多工程师/多 sub-agent 并行补证时，会把不同尝试轮次的 step 证据写进同一路径，最后形成“状态可通过，但证据不可追溯”的假闭环。
- **建议我带回主 agent 核查的一句话问题**：
  - **是否必须把 Gate 证据路径升级为 `.../{gate_code}/{attempt_id}/...`，并让 `evidence_ref` 指向 attempt 级 `index.json`，否则 `attempt_id` 只是表字段、不是可验收合同？**

### 1.2 canonical seed 的正式 artifact 路径只绑定 package，不绑定 manifest/attempt，seed 重跑会破坏可追溯性
- **严重级别**：高 / P1
- **涉及文件**：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`、`04_最终校验清单.md`
- **证据原文**：
  - `02_数据生成与回灌策略.md`：
    > “artifact 路径 | `rebuild4/runtime_artifacts/canonical_seed/{package_id}/canonical_seed.csv` | 只允许这一条正式 artifact 路径模式”
  - `02_数据生成与回灌策略.md`：
    > “`seed_artifact_manifest` 的 current 约束：`artifact_uri` 必须指向唯一 current canonical seed artifact……”
  - `03_最终执行任务书.md`：
    > “生成单一 `canonical_seed.csv` 与 `canonical_seed.build.json`……确认 `artifact_hash` 一致后，把 `artifact_uri / artifact_hash / schema_version / row_count / producer / approved_by / approval_note` 登记到 `seed_artifact_manifest`……”
- **会导致什么执行偏差**：
  1. 只要 `G1` 因冲突裁平、审批意见、导入失败而重跑，新的 `canonical_seed.csv/build.json` 就会落到同一路径。
  2. 旧的 `seed_artifact_manifest` 行即使保留下来，也会指向一个已被新内容覆盖的同路径文件，历史 manifest 无法再还原“当时真正导入的 seed”。
  3. 一旦出现“先导入、后补 artifact”或“并行重建 seed”的情况，`artifact_hash` 与文件当前内容可能短暂一致、长期不一致，验收会出现假阳性。
- **建议我带回主 agent 核查的一句话问题**：
  - **是否要把 canonical seed 的正式 URI 冻结为 `seed_manifest_id`/`attempt_id`/`artifact_hash` 级唯一路径，而不是仅按 `package_id` 固定，否则 seed 历史不可追溯？**

### 1.3 `observation_workspace_snapshot` 的 read model 合同、API 合同与 DDL 最小合同没有闭合
- **严重级别**：高 / P1
- **涉及文件**：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`、`04_最终校验清单.md`
- **证据原文**：
  - `02_数据生成与回灌策略.md`：
    > “`/api/observation-workspace` 不允许临时拼接 `obj_*`、`batch_*` 与异常表后再即席推导口径；正式执行必须先产出 `rebuild4_meta.observation_workspace_snapshot`，再由 API 直接读取。”
  - `02_数据生成与回灌策略.md`：
    > “字段要求：`run_id / batch_id`……`lifecycle_state`……`current_stage`……”
  - `03_最终执行任务书.md` 附录 B.1：
    > “`GET /api/observation-workspace` | `lifecycle`、`missing_qual`、`sort`、`page`、`size` | ……正式数据源固定为 `observation_workspace_snapshot`，不得临场拼底表。”
  - `03_最终执行任务书.md` 附录 D：
    > “`rebuild4_meta.observation_workspace_snapshot` | `batch_id`、`object_key`、`object_type`、`current_stage`、`existence_progress`、`anchorable_progress`、`baseline_progress`、`missing_detail`、`trend_direction`、`suggested_action`、`stall_batches`、`created_at`”
- **会导致什么执行偏差**：
  1. 数据策略要求 snapshot 自带 `run_id`、`lifecycle_state`，API 又要求支持 `lifecycle` 过滤，还禁止临时拼底表；但 DDL 最小列集没有这两个字段。
  2. 实现者只剩 3 条路：
     - 私自给表加列，偏离 DDL 最小合同；
     - 运行时 join `obj_*`，违反“只读 read model、不拼底表”；
     - 砍掉过滤能力，偏离 API 合同。
  3. 这会直接造成后端实现分叉、前端筛选语义不一致、Playwright 验收无法稳定复现。
- **建议我带回主 agent 核查的一句话问题**：
  - **是否要把 `observation_workspace_snapshot` 的最小列集补齐到 `run_id + lifecycle_state`，并明确 API 只读该表即可完成全部筛选？**

### 1.4 多工程师 / 多 sub-agent 的签发责任没有冻结成角色矩阵，`gate_owner` 规则会变成“自己写、自己验”
- **严重级别**：高 / P1
- **涉及文件**：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`、`04_最终校验清单.md`
- **证据原文**：
  - `03_最终执行任务书.md`：
    > “每个 Gate 只能有 1 名 gate owner 写 `gate_run_result.status`；多工程师或多 sub-agent 可以协作，但只有 gate owner 能签发 `passed/failed`……”
  - `03_最终执行任务书.md`：
    > “`gate_definition` 恰好包含 `G0` 到 `G8` 共 9 条且每条都显式绑定 `gate_owner`……”
  - `02_数据生成与回灌策略.md`：
    > “`approved_by` | 必须记录执行批准导入的 `G1` gate owner，且不得与 `producer` 为同一主体”
  - `02_数据生成与回灌策略.md`：
    > “批准职责分离……`approved_by != producer`”
- **会导致什么执行偏差**：
  1. 文档要求“唯一签发人”“审批人与产出人分离”，但六文件没有冻结一张 `G0-G8` 的 owner / backup / handoff 矩阵。
  2. 结果会变成：谁先执行 `P1-G1-04`，谁就把 `gate_definition.gate_owner` 写成自己想要的值，再要求后续 `gate_run_result.gate_owner` 与之相等；这不是外部约束，而是运行时自定义。
  3. 单人执行时，`approved_by != producer` 会天然冲突；多人执行时，又没有规定谁是 Seed Builder、谁是 G1 owner、谁能替补，最后只能靠口头协调，验收无法机器化验证。
- **建议我带回主 agent 核查的一句话问题**：
  - **是否要在冻结包内补一张 `G0-G8` owner / backup / handoff 角色矩阵，并补一个单人执行时的降级签发合同，否则多 agent 并行一定会撞责？**

### 1.5 当前页/API 的验收目标会随 rolling 推进漂移，G4-G8 没有冻结验收批次
- **严重级别**：高 / P1
- **涉及文件**：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`、`04_最终校验清单.md`
- **证据原文**：
  - `02_数据生成与回灌策略.md`：
    > “rolling 阶段只允许指向当前 run 下最新 non-rerun completed batch”
  - `02_数据生成与回灌策略.md`：
    > “`/api/flow-overview`、`/api/runs/current`、`/api/flow-snapshot/timepoints` 必须在同一次 `current_pointer` 更新中原子切换……”
  - `03_最终执行任务书.md`：
    > “`/api/flow-overview`、`/api/runs/current`、`/api/flow-snapshot/timepoints` 已统一读取该指针；……只有该记录为 `passed` 后才允许进入 `P3-G4-01`。”
- **会导致什么执行偏差**：
  1. 现在 current 语义默认跟随“最新 non-rerun completed batch”。如果 G3 之后 rolling 继续推进，G4 的 HTTP 测试与 G8 的 Playwright 用例读到的 `batch_id` 可能不是同一批。
  2. 这会导致页面截图、API 对账、基线 diff、trusted loss 数字在同一轮验收里自发漂移，表现为“代码没变，验收结果变了”。
  3. 多工程师环境下尤其明显：一组人继续跑 rolling，一组人做前端/API 验收，最终产生假失败或假通过。
- **建议我带回主 agent 核查的一句话问题**：
  - **进入 `G4-G8` 后，是否要冻结一个 `acceptance_current_batch_id`（或暂停 rolling 推进），否则所有 current 页验收对象都会漂移？**

---

## 2. 待确认问题

### 2.1 `G1` 把“seed 可执行化”和“asset 语义注册”捆成一个 blocking 大步骤，过度工程化风险很高
- **严重级别**：中 / P2
- **涉及文件**：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`、`05_本轮范围与降级说明.md`
- **证据原文**：
  - `03_最终执行任务书.md`：
    > “`P1-G1-06`……登记 seed manifest……导入 `parse_rule` 与 `compliance_rule`；同步完成 `asset_table_catalog`、`asset_field_catalog`、`asset_usage_map`、`asset_migration_decision`。”
  - `02_数据生成与回灌策略.md`：
    > “`asset_usage_map / asset_migration_decision` | 在真实基数上人工补语义……人工只能补语义”
  - `05_本轮范围与降级说明.md`：
    > “`M2` 解释层与治理底座 | 快照、规则 seed、seed manifest、asset 注册、trusted loss | `G1` + `G5`”
- **会导致什么执行偏差**：
  1. `seed` 可执行 current 是主链起跑前置；但 `asset_usage_map / asset_migration_decision` 明显带人工语义判定，节奏比 seed 慢。
  2. 现在两者被绑成同一个 blocking step，容易出现两种坏结果：
     - 为了不阻塞 G2，团队仓促填充 asset 语义；
     - 为了追求 asset 完整，seed 可执行 current 被无谓拖住。
  3. 这不是“缺思考”，而是**把非同一节奏的任务强捆绑**，会拖慢收敛。
- **建议我带回主 agent 核查的一句话问题**：
  - **是否把 `G1` 至少拆成“seed executable current 放行”与“asset 语义完善”两个检查项，避免非关键语义工作拖死主链起跑？**

### 2.2 记录级异常的 `handling_note` 出现在策略合同里，却没有被 DDL/API/清单完整承接
- **严重级别**：中 / P2
- **涉及文件**：`02_数据生成与回灌策略.md`、`03_最终执行任务书.md`
- **证据原文**：
  - `02_数据生成与回灌策略.md`：
    > “记录级异常最小字段……`handling_note` | 处理说明”
  - `03_最终执行任务书.md` 附录 D：
    > “`rebuild4_meta.batch_anomaly_record_summary` | `batch_id`、`anomaly_type`、`affected_rows`、`new_rows_current_batch`、`fact_destination`、`anchor_impact`、`baseline_impact`”
- **会导致什么执行偏差**：
  1. 策略说它是记录级异常“最小字段”，但 DDL 最小合同没有它。
  2. 后端实现可能出现两派：一派补字段，一派删展示，一派临时把说明塞进别的字段。
  3. 虽然这不是主链阻断级问题，但它会让异常页/API 的字段口径逐步漂移。
- **建议我带回主 agent 核查的一句话问题**：
  - **`handling_note` 到底是正式最小字段还是可删减字段？若是正式字段，就应同步补到 DDL/API/清单；若不是，就应从策略合同删掉。**

---

## 3. 总体判断

### 3.1 总体结论
这套六文件的**Gate / Phase 大顺序基本是闭合的**：`G0 -> G1 -> G2 -> G3 -> G4 -> G5 -> G6 -> G7 -> G8` 的主链没有明显回环，`G1 seed`、`G2->G3 rolling_ready`、`G3->G4 current handoff`、`G4/G5/G6/G7/G8` 的阶段边界也都已经比前几轮清楚很多。

但它**还没有达到“可直接多人并行落地且可稳定验收”的程度**。现在真正卡住闭环的，不是“方向没定”，而是下面 3 类执行元合同还没冻结到位：

1. **证据元合同没闭合**：Gate 与 seed 都支持重试/重建，但 artifact 路径没有 attempt/manifest 级隔离，证据会被覆盖，历史不可还原。
2. **责任元合同没闭合**：文档要求唯一签发人与职责分离，但没有冻结 owner 矩阵，导致多 agent 并行时会出现“自己定义自己是谁”的签发问题。
3. **读模型元合同没闭合**：少数字段在策略/API/DDL 之间没有完全对齐，最典型的是 observation workspace，直接会把实现逼成多版本。

### 3.2 关于你担心的“是不是过度思考 / 过度工程化”
你的担心是对的，但问题不在于“检查太细”，而在于**有些地方规定得太细，却没规定到真正影响闭环的地方**。

我判断目前最该收敛的不是再补更多解释，而是做两类收敛：

- **删掉非关键捆绑**：例如把 `G1` 里 seed executable current 与 asset 语义完善拆开，不要让非关键人工语义阻塞主链起跑。
- **补上关键元合同**：只补 3 个最值钱的东西——
  1. attempt/manifest 级 artifact 路径；
  2. Gate owner / backup / handoff 角色矩阵；
  3. observation/anomaly 这类 read model 的最小列集对齐。

### 3.3 最终判断
**结论：当前版本不是方向性失控，而是“主流程骨架已成，但执行元合同仍有 5 个会导致实现分叉或验收失真的缺口”。**

如果你只打算带最重要的问题回主 agent，我建议优先只带这 3 个：

1. **Gate/seed 证据路径必须做 attempt/manifest 级隔离。**
2. **`G0-G8` 的 owner / backup / handoff 角色矩阵必须写死。**
3. **`observation_workspace_snapshot` 的最小列集必须与 API/DDL 一次对齐。**

这 3 个不补，后面即使继续细化文案，也还是会在真正执行时分叉；这 3 个补上，再收掉 `G1` 过捆绑，整体就会明显更可落地，不会无限评审下去。
