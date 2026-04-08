# Codex 审计报告

> 审计人：Codex Agent
> 审计日期：2026-03-23
> 审计文档数：11

## 审计结果

### 维度 A：完整性
**评定：** 部分通过

1. 5 份缺口文档与 Q01~Q04 均已存在，且正文内容明显不是占位符；Q01~Q04 也都给出了可落地的回答。
2. `04_指标注册表.md` 未覆盖全部已声明步骤。当前只注册了 Step0/1/2/3/4/5/6/30/31/33/40/41/50/51/52（`rebuild/docs/04_指标注册表.md:34-183`），缺少 `wb_step_registry` 中已登记的 Step32/34/35/36/37/42（`rebuild/docs/05_工作台元数据DDL.md:538-547`），也缺少 `03_步骤SQL参数映射.md` 详细段落中仍然存在的 Step43/44（`rebuild/docs/03_步骤SQL参数映射.md:451-471`）。
3. 项目上下文材料尚未收敛到最终状态。`00_重构上下文与范围.md` 仍写着“27 张表完整字段定义”“待决策项”（`rebuild/docs/00_重构上下文与范围.md:285-324`），`context.md` 也仍写“27张表的完整字段定义”（`rebuild/prompts/context.md:85-92`），但最终 DDL 文档实际只定义了 22 张表（`rebuild/docs/05_工作台元数据DDL.md:10-32`）。

### 维度 B：一致性
**评定：** 未通过

1. 完整回归口径冲突。Doc01 明确要求“从 Layer0 完整起点开始”，并且“完整回归必须回到 Layer0 全量数据重新处理”（`rebuild/docs/01_数据起点与表体系决策.md:10-19,23-39`）；但 Doc03 的 Step40 详细定义只输入 `Y_codex_Layer0_Lac`，未包含 `Y_codex_Layer0_Gps_base`（`rebuild/docs/03_步骤SQL参数映射.md:400-404`）；而 Doc04 的 Step40 指标又按 `raw_records` 口径描述（`rebuild/docs/04_指标注册表.md:150-155`）。
2. `operator_id_raw` 的语义前后不一致。Step0 把 `46000/46015/46020` 映射为 `CMCC`、`46001` 映射为 `CUCC`、`46011` 映射为 `CTCC`（`rebuild/docs/03_步骤SQL参数映射.md:63-70`）；但 Step1、指标维度和默认参数集都把 `operator_id_raw` 当作原始 PLMN 码使用（`rebuild/docs/03_步骤SQL参数映射.md:90-92`，`rebuild/docs/04_指标注册表.md:85,230-248`，`rebuild/docs/05_工作台元数据DDL.md:559-560`）。同时文档里还单独存在 `operator_group_hint` 字段（`rebuild/docs/03_步骤SQL参数映射.md:63`），导致两者职责边界不清。
3. 工作台元数据模型前后不一致。Doc00/`context.md` 仍以 27 张表为准，包含 `wb_step_dependency`、`wb_dataset_registry`、`wb_metric_snapshot`、`wb_rerun_scope` 等（`rebuild/docs/00_重构上下文与范围.md:287-303`，`rebuild/prompts/context.md:87-92`）；Doc05 改成了另一套 22 张表模型，且这些表不再出现（`rebuild/docs/05_工作台元数据DDL.md:10-32`）。
4. 参数注册表前后不一致。示例包括：
   - 全局 `rsrp_invalid_values` 在 Doc03 写为 `-110 / -1 / >=0 -> NULL`（`rebuild/docs/03_步骤SQL参数映射.md:561`），在默认参数集里只保留了 `[-110,-1]`（`rebuild/docs/05_工作台元数据DDL.md:562-564`）。
   - Step30 详细参数含 `center_bin_scale`（`rebuild/docs/03_步骤SQL参数映射.md:220-223`），默认参数集也有（`rebuild/docs/05_工作台元数据DDL.md:566`），但 Doc03 汇总参数表缺失该参数（`rebuild/docs/03_步骤SQL参数映射.md:565-573`）。
   - Step35 详细参数含 `grid_round_decimals`、`min_day_major_share`、`min_half_major_day_share`（`rebuild/docs/03_步骤SQL参数映射.md:324-327`），默认参数集也有（`rebuild/docs/05_工作台元数据DDL.md:568`），但 Doc03 汇总参数表只保留了 3 个参数（`rebuild/docs/03_步骤SQL参数映射.md:574-576`）。
   - Step50/51/52 在 Doc03 汇总里分别命名为 `min_rows_lac` / `min_rows_bs` / `min_rows_cell`（`rebuild/docs/03_步骤SQL参数映射.md:579-581`），在默认参数集里统一命名为 `min_rows`（`rebuild/docs/05_工作台元数据DDL.md:570-572`）。
5. 步骤编号/注册不完全对齐。Doc03 详细部分仍保留 Step43 与 Step44（`rebuild/docs/03_步骤SQL参数映射.md:451-471`），但其“重构后步骤映射总表”已不再列出这两步（`rebuild/docs/03_步骤SQL参数映射.md:620-626`），`wb_step_registry` 初始数据也未登记（`rebuild/docs/05_工作台元数据DDL.md:545-550`）；与此同时，`fact_final.is_bs_id_lt_256` 和相关异常指标仍然保留（`rebuild/docs/02_新旧表体系映射.md:469`，`rebuild/docs/04_指标注册表.md:195`）。
6. Doc02 内部列数统计不一致。总览表写 `fact_filtered` 为 50 列、`fact_final` 为 70 列（`rebuild/docs/02_新旧表体系映射.md:28,32`），但逐表映射分别写成 56 列和 74 列（`rebuild/docs/02_新旧表体系映射.md:248-307,423-500`）。

### 维度 C：可执行性
**评定：** 未通过

1. 步骤执行合同仍需猜测。`wb_step_registry` 中存在 `(intermediate)`、`(compliant_records)`、`(step40_output)` 这类占位输入/输出（`rebuild/docs/05_工作台元数据DDL.md:531-546`），这意味着后端 Worker 和 FastAPI API 在实现物化策略、临时表命名和步骤依赖时必须自行补假设。
2. Step36 的输入定义无法直接执行。Doc03 详细定义中，Step36 输入是 `Y_codex_Layer3_Final_BS_Profile`，并依赖 `bs_id_hex` 长度规则（`rebuild/docs/03_步骤SQL参数映射.md:338-349`）；但 `wb_step_registry` 把它登记为从 `dim_bs_trusted` 读取（`rebuild/docs/05_工作台元数据DDL.md:542`），而 `dim_bs_trusted` 字段清单里并没有 `bs_id_hex`（`rebuild/docs/02_新旧表体系映射.md:316-337`）。
3. Step5/Step30 之间仍有未落地的中间依赖。Step5 会输出 `Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac`（`rebuild/docs/03_步骤SQL参数映射.md:160-163`），Step30 明确把它作为输入之一（`rebuild/docs/03_步骤SQL参数映射.md:210-214`）；但新表映射里没有对应 pipeline 表，`dim_cell_stats` 也没有承接该异常结果的字段（`rebuild/docs/02_新旧表体系映射.md:225-241`）。
4. 仅凭现有文档无法直接写完 pipeline schema 的生产级 DDL。Doc02 给了字段级映射（`rebuild/docs/02_新旧表体系映射.md:143-707`），但没有任何主键、唯一约束、索引、分区、聚簇、保留周期说明；对 2.5 亿级与 3000 万级大表来说，这些不是可选项。
5. 仅凭现有文档不能直接完成运行 API/前端工作台的运行模式实现。`wb_run` 只有 `run_mode` 枚举（`rebuild/docs/05_工作台元数据DDL.md:49-79`），却没有 `sample_set_id`、`rerun_from_step`、`rerun_to_step`、`pseudo_daily_anchor` 一类关键字段；`wb_sample_set` 虽存在（`rebuild/docs/05_工作台元数据DDL.md:365-388`），但与 `wb_run` 没有关系；上下文里原本提出的 `wb_step_dependency` 与 `wb_rerun_scope` 也未在最终 DDL 中落地（`rebuild/docs/00_重构上下文与范围.md:287-300`）。

### 维度 D：业务正确性
**评定：** 部分通过

1. 大方向上，文档确实贯彻了“有效 cell_id = 有效上报”“修正优于丢弃”“层层收敛、互相印证”“基线驱动”四条原则（`rebuild/docs/00_重构上下文与范围.md:35-63`），且 Step30/31/33/50~52 的阈值基本落在合理区间，明显继承了旧 SQL 资产。
2. 但完整回归若只重放 `Y_codex_Layer0_Lac` 而不纳入 `Y_codex_Layer0_Gps_base`（`rebuild/docs/03_步骤SQL参数映射.md:400-404`），就会偏离“从 Layer0 全量数据重新处理”的业务定义（`rebuild/docs/01_数据起点与表体系决策.md:37-39`）。
3. `operator_id_raw` / `operator_group_hint` 的职责不清，会直接影响运营商维度上的白名单、画像聚合和指标切片，属于业务语义层面的高风险问题（见 `rebuild/docs/03_步骤SQL参数映射.md:63-70,90-92`；`rebuild/docs/04_指标注册表.md:85,230-248`）。
4. `is_bs_id_lt_256` 异常逻辑仍被最终表与指标消费（`rebuild/docs/02_新旧表体系映射.md:469`，`rebuild/docs/04_指标注册表.md:195`），但执行层没有明确保留 Step44 或等价替代步骤（`rebuild/docs/03_步骤SQL参数映射.md:463-471,620-626`；`rebuild/docs/05_工作台元数据DDL.md:545-550`），导致异常来源链条不闭合。

### 维度 E：遗漏检测
**评定：** 未通过

1. 缺少 pipeline 表的索引/分区策略。Doc02 只定义字段映射，没有定义任何 pipeline 侧索引；而现有索引只覆盖了一部分 workbench/meta 表（见 `rebuild/docs/05_工作台元数据DDL.md:78-79,213-234,250,269-270,288,328,416-417,451,486,503`）。
2. 错误处理与重试机制没有定义。`wb_step_execution` 只有 `status` 和 `error_message`（`rebuild/docs/05_工作台元数据DDL.md:200-214`），没有 `attempt_no`、`retry_count`、`next_retry_at`、`retry_policy`、`backoff_seconds` 等字段，全文也没有重试策略说明。
3. 4 种运行模式只有命名，没有完整落地设计。上下文里有“全链路重跑 / 局部重跑 / 样本重跑 / 伪日更运行”（`rebuild/docs/00_重构上下文与范围.md:166-171`），但最终 DDL 只保留了 `run_mode` 字段（`rebuild/docs/05_工作台元数据DDL.md:51`）；局部重跑、样本重跑、伪日更所需的额外状态均未定义。
4. 步骤依赖与重跑范围模型被遗漏。早期上下文中存在 `wb_step_dependency`、`wb_rerun_scope`（`rebuild/docs/00_重构上下文与范围.md:288,300`），最终 DDL 没有替代设计；对存在报表步、附加步和主链路分支的系统，这会让调度与 UI 都依赖硬编码。
5. 指标覆盖矩阵缺失。既没有明确说明哪些步骤只产出 `wb_step_metric`、哪些只产出 `wb_gate_result` / `wb_reconciliation`，也没有给出 Step32/34/35/36/37/42/43/44 的指标去向，导致开发时仍需反推。

## 总体评估

**结论：** 需修改后可开发

### 必须修改项（如有）
1. 统一完整回归口径，明确 Step40 到底是回放 `raw_records`、两张 Layer0 原表，还是仅 `Layer0_Lac`；并同步修正文档、步骤注册和指标口径。
2. 统一 `operator_id_raw` 与 `operator_group_hint` 的字段语义，固定一个跨表一致的命名/取值方案。
3. 补齐步骤执行合同：明确 Step2/3/5/40 的物化策略，明确 Step43/44 是保留、合并还是废弃，并把 Step36/Step44 的真实输入输出对齐到最终表设计。
4. 整理一份唯一可信的参数规范，同时同步修正 `03_步骤SQL参数映射.md` 与 `wb_parameter_set` 的 JSON 结构。
5. 在最终版本中冻结一套唯一可信的工作台元数据模型，消除“27 张表方案”和“22 张表方案”的并存状态。
6. 补充 pipeline 大表的主键/唯一键/索引/分区策略，以及运行模式、依赖关系、错误重试的元数据设计。

### 建议改进项（如有）
1. 增加一张“步骤 -> 输入表 -> 输出表 -> 指标表 -> 门控表”的总矩阵，避免开发时跨文档反查。
2. 为 FastAPI/Worker 增加最小可执行契约示例，例如创建 run、从某步局部重跑、样本重跑、伪日更运行的请求体与状态流转。
3. 在 Doc02 中把每张 pipeline 表的推荐主键、查询主索引和大表分区键直接写出来，降低实现歧义。
