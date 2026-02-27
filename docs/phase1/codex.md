# Phase1 可视化研究平台 下一步说明与开发文档（Codex执行版）

## 1. 文档目的
本文件把“第三方方案（无代码Agent输出）+ 当前真实基线（已审计DB/SQL）”合并为可执行开发计划。  
目标是：在当前仓库中分阶段落地一个可持续研究工具，而不是再产出静态报告。

## 2. 输入依据
1. 当前基线审计：`docs/phase1/Phase1_基础审计与工程化方案_2026-02-25.md`
2. 第三方方案（摘要）：`docs/phase1/codex.md` 历史内容（需求重述、分层框架、可视化蓝图）
3. 方案补充蓝图：`docs/phase1/visualization_research/03_可视化页面与数据模型蓝图.md`
4. 项目主口径：`lac_enbid_project/Phase_1/Phase_1_Engineering_Handoff.md`

## 3. 当前情况（必须先承认的基线）

### 3.1 已验证可用
1. Layer_0~Layer_5 主干对象存在且可用。
2. Layer_4 Final 与 Layer_5 三画像已成型，可用于构建研究看板。
3. 标签闭环在“碰撞/严重碰撞/动态”上基本成立。

### 3.2 已知阻塞（P0）
1. `Step40_Gps_Metrics_All` 与事实表存在口径差异；`Step43` 脚本与现有 schema 漂移。
2. Layer_5 缺关键风险契约字段：`is_bs_id_lt_256`、`is_multi_operator_shared/shared_operator_*`。

### 3.3 已知高优先（P1）
1. Layer_1 入口对象“文档 vs 实际”不一致（`v_lac_L1_stage1` 缺失，`v_cell_l1_stage1` 为旧链路）。
2. Step30 存在 `bs_id<=0` 桶，与主文档入口止血描述不一致。
3. Layer_4 RUNBOOK 与实际 severe 策略描述冲突。

### 3.4 S0 修复状态（2026-02-26）
1. S0-1 已修复：`43_step43_merge_metrics.sql` 已与 `Step40_Gps_Metrics` 列集合对齐，纳入 `gps_fill_from_bs_severe_collision_cnt` 与 `bs_id_lt_256_row_cnt`。
2. S0-2 已修复：`51_step51_bs_profile.sql`、`52_step52_cell_profile.sql` 已暴露 `is_bs_id_lt_256`、`is_multi_operator_shared`、`shared_operator_cnt`、`shared_operator_list`，并同步 EN 视图与 Step53 幂等改名映射。
3. S0-3 已修复：`Layer_4_执行计划_RUNBOOK_v1.md` 已与 SQL/Handoff 对齐为“严重碰撞回填+强标注”。

### 3.5 S1/S2/S3 已落地状态（2026-02-26）
1. S1 已落地：`sql/phase1_obs/01_obs_ddl.sql`、`02_obs_build.sql`、`03_obs_gate_checks.sql`；并补充运行脚本 `scripts/run_phase1_obs_pipeline.sh` 与一致性检查脚本 `scripts/check_phase1_obs_consistency.sh`。
2. S2 已落地：`docs/phase1/dev/phase1_api_spec.md` + `apps/phase1_api/server.py`，已包含统一错误体、分页、问题单与补丁单写接口。
3. S3 已落地：`apps/phase1_ui/dashboard.html` + `layer.html`/`reconciliation.html`/`exposure.html`/`issues.html`/`patches.html` + `glossary.html`（术语独立页）+ `dashboard_data.json`。
4. 启动与浏览入口已落地：`launcher.py`（start/stop/status/open）+ `scripts/phase1_env.sh`（默认数据库）。
5. Trace 已落地：`/api/phase1/trace/{trace_key}` 支持 `seq_id/记录id` 穿透查询，页面已提供 Trace 输入与结果面板。

### 3.6 S4 闭环固化状态（2026-02-26）
1. 问题状态机已在 API 实施（非法流转返回 `409`）。
2. 补丁日志已接入（`GET/POST /api/phase1/patches` + `patches.html`）。
3. Runbook 已落盘：`docs/phase1/dev/issue_patch_runbook.md`。

## 4. 第三方方案中应保留的核心思想
1. 以 Layer 为中心的“六件套”研究框架：目标/输入/处理/输出/变化/风险。
2. 可视化产品必须支持三层粒度：总览 -> 分层剖面 -> 样本穿透。
3. 闭环机制必须完整：发现 -> 定位 -> 修复 -> 验证 -> 记录 -> 固化。
4. 先做门禁可信度，再做页面丰富度。

## 5. 总体落地策略
采用“双轨推进”：
1. 轨道A（数据正确性修复）：先消除 P0 口径与契约阻塞，保证看板数据可信。
2. 轨道B（可视化平台建设）：并行建设最小观测数据层、API 层、页面层。

原则：
1. 先解决“看得准”，再解决“看得全”。
2. 全程保留可回滚路径，不对主业务明细做破坏性改动。

## 6. 目标架构（MVP）

### 6.1 数据层（Observability Mart）
新增独立 schema 或前缀表（建议：`public.Y_codex_obs_*`），不改原主链路表：
1. `Y_codex_obs_run_registry`
2. `Y_codex_obs_layer_snapshot`
3. `Y_codex_obs_rule_hit`
4. `Y_codex_obs_quality_metric`
5. `Y_codex_obs_anomaly_stats`
6. `Y_codex_obs_reconciliation`
7. `Y_codex_obs_exposure_matrix`
8. `Y_codex_obs_issue_log`
9. `Y_codex_obs_patch_log`
10. `Y_codex_obs_gate_result`

### 6.2 API 层（MVP）
1. `/api/phase1/overview`
2. `/api/phase1/layer/{layer_id}`
3. `/api/phase1/reconciliation`
4. `/api/phase1/exposure-matrix`
5. `/api/phase1/issues`
6. `/api/phase1/patches`
7. `/api/phase1/trace/{trace_key}`
8. `/api/phase1/dashboard-snapshot`

### 6.3 页面层（MVP）
1. 总览页：链路健康与门禁状态。
2. 分层页：每层输入输出变化与规则影响。
3. 对账页：指标表 vs 事实表差值追踪。
4. 异常可见性页：明细字段在画像层的暴露矩阵。
5. 问题闭环页：问题单创建/状态流转/责任归属。
6. 补丁日志页：补丁记录、验证标记与 issue 关联。
7. 术语缩写页：独立解释，不占首页主空间。

## 7. 分阶段实施计划（可执行）

### Phase S0：基线修复（必须先做，2-4天）
目标：修复看板数据可信性阻塞。

任务：
1. 修复 Step43 与 Step40 指标列不一致问题。
2. 重新生成并核对 `_All` 汇总表。
3. 在 Layer_5 暴露缺失异常字段（至少 EN 视图先补齐）。
4. 修正文档冲突（Layer_4 RUNBOOK severe 策略）。

交付：
1. 修复SQL脚本。
2. 修复前后对账报告。
3. 门禁SQL执行结果快照。

验收：
1. `gps_not_filled_cnt` 差值归零或明确可解释。
2. Layer_5 BS/CELL 字段存在性门禁通过。

### Phase S1：观测数据层（3-5天）
目标：沉淀可视化可消费的数据模型。

任务：
1. 建 `Y_codex_obs_*` 表DDL。
2. 写批处理SQL：从 Layer_* 主表汇总到 obs 表。
3. 建 `run_id` 机制（手工/脚本触发均可）。
4. 首次回填最近 N 次基线（至少 1 次当前基线）。

交付：
1. `obs_ddl.sql`
2. `obs_build.sql`
3. `obs_smoke_check.sql`

验收：
1. 总览页所需字段齐全。
2. 对账页与异常可见性页所需字段齐全。

### Phase S2：API 层（3-4天）
目标：提供稳定可消费接口，隔离页面与DB细节。

任务：
1. 定义接口 schema（请求/响应/错误码）。
2. 实现 6 个MVP接口。
3. 增加最小缓存/分页/过滤（按 layer、operator、tech、tag）。
4. 写接口合同测试。

交付：
1. `api_spec.md`
2. 接口实现代码。
3. `api_smoke.http` 或等价测试。

验收：
1. 接口稳定返回。
2. 与 obs 表数据一致。

### Phase S3：前端页面（4-6天）
目标：形成可用于研究与排障的可视化工作台。

任务：
1. 实现总览、分层、对账、异常可见性、问题闭环 5 页。
2. 实现统一筛选器（run_id/layer/operator/tech/time）。
3. 实现关键联动（点击异常 -> 自动过滤详情）。
4. 实现门禁状态高亮与证据跳转。

交付：
1. 页面代码。
2. 使用说明。
3. 关键截图与演示路径。

验收：
1. 满足“15分钟定位异常”的演示流程。

### Phase S4：闭环固化（2-3天）
目标：从“看板”升级为“治理流程”。

任务：
1. 问题单/补丁单模板接入系统。
2. 加入验证状态机（new/in_progress/verified/rejected/rolled_back）。
3. 固化回滚说明与触发条件。

交付：
1. `issue_patch_runbook.md`
2. 状态机字段与展示。

验收：
1. 至少完成 1 个真实问题的闭环演练。

## 8. 建议目录与文件落点

建议在仓库新增（示例）：
1. `docs/phase1/dev/phase1_visualization_mvp_plan.md`
2. `docs/phase1/dev/phase1_api_spec.md`
3. `docs/phase1/dev/phase1_gate_sql_catalog.md`
4. `sql/phase1_obs/01_obs_ddl.sql`
5. `sql/phase1_obs/02_obs_build.sql`
6. `sql/phase1_obs/03_obs_gate_checks.sql`
7. `sql/phase1_fix/01_fix_step43_metrics.sql`
8. `sql/phase1_fix/02_fix_layer5_exposure.sql`
9. `sql/phase1_fix/03_fix_docs_sync_checklist.md`

## 9. 门禁与验收（开发阶段）

### 9.1 开发门禁（必须自动化）
1. 对象存在门禁。
2. 行数守恒门禁（Step40=Final）。
3. 对账一致性门禁（汇总 vs 事实）。
4. 异常字段暴露门禁（明细->画像）。
5. 无效LAC泄漏门禁。

### 9.2 业务验收（上线前）
1. 可视化页面可完成“异常发现->定位->证据展示”。
2. 问题闭环页可记录并回看一次真实修复链路。
3. 连续 7 天（或 7 次）运行门禁全绿。

## 10. 风险与回滚策略

### 10.1 风险
1. 修复 Step43 时可能影响历史报表口径。
2. Layer_5 补字段可能引起下游依赖变化。
3. obs 汇总任务可能增加数据库负载。
4. 页面若直接查主表会导致性能抖动。

### 10.2 回滚
1. 所有修复脚本提供 `UP` 和 `DOWN`。
2. obs 层与主链路解耦，异常时可直接关闭 obs 任务，不影响主产出。
3. 页面层失败时可降级到静态报表。
4. 门禁失败时冻结发布，仅允许审计使用。

## 11. 角色与协作建议
1. 深度思考Agent负责：框架策略、规则优先级、页面与闭环设计优化。
2. Codex（当前）负责：SQL修复、obs建模、API与页面可执行落地。
3. 业务/分析师负责：验收口径确认、规则争议拍板、真实样本复核。

## 12. 当前下一步（收口阶段）
1. 把 `run_phase1_obs_pipeline.sh` 接入定时任务或 CI。
2. 每次产出后自动生成一致性报告并归档到 `docs/phase1/dev/run_logs/`。
3. 完成至少 1 个真实问题的“问题 -> 补丁 -> 验证 -> 回滚条件”演练记录。

---

## 附录A：本文件与第三方方案关系说明
1. 第三方方案提供了方向（分层、闭环、可视化蓝图）。
2. 本文件提供执行路径（先修什么、建什么、验什么、如何回滚）。
3. 后续开发全部以本文件为执行基线；若策略变更，先更新本文件版本。
