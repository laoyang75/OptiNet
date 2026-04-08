# 实体字段接口与Gate细化 (Gemini)

## 1. 实际阅读的输入文件
- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/round2_detail/00_round_goal.md`
- `rebuild4/docs/02_rounds/round2_detail/prompts/00_共享约束.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/01_统一计划.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/02_统一风险与缺口.md`
- `rebuild4/docs/02_rounds/round1_plan/decisions/01_待裁决问题清单.md`
- PG17 MCP 数据库查证事实：ODS 规则定义 26 行，ODS 规则结果统计只含 24 唯一 rule_code 等。

## 2. 关键表与字段矩阵
### 结论
构建的 `rebuild4` 事实及对象表和 `rebuild4_meta` 表必须强绑定来源及元数据约束：
- **`rebuild4.fact_standardized` 等事实表**：必需字段 `id` (UUID), `data_origin` (VARCHAR, 限制域), `run_id` (UUID, 外键), `batch_id` (UUID, 外键), `source_type` (VARCHAR), `record_state` (VARCHAR)。
- **`rebuild4_meta.ods_clean_rule` (ODS 规则定义表)**：必需字段 `rule_code` (VARCHAR, 主键), `rule_desc` (TEXT), `status` (VARCHAR)。
- **`rebuild4_meta.ods_clean_result` (ODS 规则执行表)**：必需字段 `id` (UUID), `run_id` (UUID), `rule_code` (VARCHAR), `hit_count` (BIGINT), `execution_time` (TIMESTAMP)。
- **`rebuild4_meta.parse_rule` / `compliance_rule`**：新建表，必须具有 `rule_code`, `target_field`, `logic_desc`, `is_active`。

### 依据
`rebuild4/docs/02_rounds/round1_plan/decisions/01_待裁决问题清单.md` D-003 裁决结果要求：将 ODS 规则定义层与执行层物理分离；`02_统一风险与缺口.md` R-04 要求补齐 `parse_rule` 和 `compliance_rule` 缺失表结构，以满足元数据主线。

### 风险
如果不从 DDL 层就将 `run_id`、`data_origin` 和 `rule_code` 形成外键和字典约束，极易再次将临时清洗或脚本造出的合成数据通过侧信道混入正式数据库中。

### 校验
通过 `PG17 MCP` 中的 `mcp_PG17_search_objects` 和 `mcp_PG17_execute_sql` 直接检阅 `rebuild4` 库 DDL 定义中是否存在对应的非空字段 (NOT NULL) 限制及外键关系引用。

## 3. API 输入输出约束
### 结论
全量重构的 API 接口约束必须与页面主语/表底层 100% 对齐：
- **ODS 治理 API 分离**：
  - `GET /api/governance/ods_rules`：强制响应 `200 OK` 并返回定长的 26 行 JSON 对象：`[ { rule_code: string, rule_desc: string, status: string } ]`。
  - `GET /api/governance/ods_executions?run_id={id}`：仅返回真实有统计的数据，格式为 `[ { rule_code: string, hit_count: number } ]`。
- **对象列表数据读取**：
  - `GET /api/objects/cells?baseline_version={version}`：输出响应体必须对每个对象包含 `data_origin: "real" | "synthetic" | "fallback"`，不允许缺省。
- **可信损耗分析查询**：
  - `GET /api/governance/trusted_loss?run_id={id}`：输出需包含 `total_loss`, `loss_by_source: [{source_name, count}]`, `loss_by_radio: [{radio_type, count}]` 严谨结构。

### 依据
`rebuild4/docs/02_rounds/round1_plan/decisions/01_待裁决问题清单.md` D-003 及 `01_统一计划.md` 中的 API 最小交付范围界定。

### 风险
如果 API 参数允许弱引用或响应缺失来源依据，前端会直接渲染无法溯源的页面图表，导致主干逻辑再次“为了渲染而渲染”。

### 校验
API 集成测试或 e2e 流转测试时，拦截所有 Response JSON Schema。凡是未包含 `data_origin` 或缺失对应 UUID 查询主语的端点，视为校验不通过。

## 4. Gate 条件与阻断动作
### 结论
在系统架构层面和实施部署流程中，设立严格的前置 Gate：
- **Gate 1: real 主干数据完成注入网关**
  - **条件**：查询 `rebuild4_meta.run` 至少存在一条 `run_type = 'full_initialization'` 且 `status = 'completed'` 的真实运行记录。
  - **阻断动作**：一旦不满足，所有调用概览 (`/overview`)、基线 (`/baseline`)、对象检索 (`/objects`) 的 API 层全部抛出 `HTTP 409 Conflict` (Gate Unpassed) 并拒绝响应数据结构。
- **Gate 2: 解释层与元数据结构完备网关**
  - **条件**：查询 `rebuild4_meta.parse_rule` 及 `compliance_rule` 必须存在对应真实提取出的规则记录；`ods_clean_rule` 记录数为 26。
  - **阻断动作**：若查询为空或者条数不符，API 端对 `/governance/*` 路由抛出 `HTTP 503 Service Unavailable` 异常。

### 依据
`rebuild4/docs/02_rounds/round1_plan/merged/02_统一风险与缺口.md` 中 R-01 明确强调“如果不将唯一任务书和 Gate 独立为硬核停机线”，项目依然会退回重头再补。

### 风险
若只是口头规定而不在业务中间件或服务入口增加实体鉴别，一旦工期紧张，研发会跳过这些规则补入测试数据以求快速推进前端展现。

### 校验
应用服务端注入中间件拦截器：模拟数据库表中 `run` 数据清空状态下请求主流程 API，服务端应当立刻返回上述 `409/503` 指定错误；此时前端应当捕获该 Code 并展示诚实空状态停机拦截页。

## 5. 结尾
### 自检清单
- [x] 是否列出实际阅读的输入文件？
- [x] 每一部分是否包含结论、依据、风险、校验四个必填项？
- [x] 是否明确定义关键表与字段矩阵？
- [x] 是否包含 API 输入输出的具体参数约束？
- [x] 是否有硬性的 Gate 条件以及其对应的系统级阻断动作？

### 可能遗漏点
- 当 Gate 1 阻断时，未定义前端该重定向到具体的“无数据环境启动向导”或“后端同步等待中”视图。
- 各表的外键级联删除策略 (ON DELETE CASCADE 等) 是否适用于 `rebuild4_meta` 尚未深究。

### 你认为最危险的 3 个未决问题
1. **ODS 24 个执行结果如何关联到 26 个规则定义页？** API 既然已经拆分，缺失的 2 个规则如何在前端组件稳妥呈现不致引发 JS 报错崩溃。
2. **初始化数据的耗时性能监控。** `rebuild2.l0_gps / l0_lac` 达8000万行数据，`full_initialization` 的真实跑批时长对 Gate 1 畅通产生巨大时间线风险。
3. **Trusted 层漏斗在复杂多维联查情况下的数据库索引方案。** 若未设定合理复合索引，API 会大面积超时。