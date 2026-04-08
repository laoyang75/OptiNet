# Codex 第二轮审计报告

> 审计日期：2026-03-24
> 审计文件数：24
> 审计范围：代码 20 文件 + 设计文档 4 文件 + PG17 实际 schema / 行数 / 注释 / 索引 / EXPLAIN 证据

## 维度 A：性能与缓存
**评定：** 未通过

当前实现最主要的问题不是“某一条 SQL 慢”，而是“首页和页面切换路径默认触发重型实时查询”。`rebuild/backend/app/api/metrics.py:12-174` 直接对 `pipeline.raw_records`、`fact_filtered`、`fact_gps_corrected`、`fact_signal_filled`、`fact_final` 做实时 `count(*)` / 聚合；`rebuild/frontend/app.js:72-79` 又把这些接口放在首页 `Promise.all()` 里，每次进入总览都重新请求。设计文档原本已经预留了 `workbench.wb_step_metric`、`wb_layer_snapshot`、`wb_anomaly_stats` 作为快照承载层，但当前实现完全绕过了它们，导致工作台把“运行后快照”做成了“每次打开现算”。

PG17 实际规模也印证了这个问题：
- `pipeline.raw_records`：251,172,880 行 / 109 GB
- `pipeline.fact_final`：30,492,108 行 / 18 GB
- `pipeline.fact_filtered`：21,788,532 行 / 13 GB
- `pipeline.fact_gps_corrected`：21,787,519 行 / 8.6 GB
- `pipeline.fact_signal_filled`：21,790,333 行 / 7.0 GB
- `EXPLAIN SELECT count(*) FROM pipeline.raw_records` 显示 `Parallel Index Only Scan using idx_raw_records_biz`，说明虽然不是顺序扫表，但仍要完整扫过一棵 1.8 GB 的大索引，仍然是 O(N) 成本。
- `EXPLAIN SELECT operator_id_raw, tech_norm, count(*) FROM pipeline.fact_final GROUP BY ...` 显示 `Parallel Index Only Scan using idx_fact_final_biz`，同样是全索引聚合，不适合放在页面首屏实时请求里。

### API 性能分析表
| API 端点 | 涉及表 | 查询类型 | 预估耗时 | 问题 |
|---------|--------|---------|---------|------|
| `GET /api/v1/health` | 无 | 常量返回 | 低 | 无 |
| `GET /api/v1/pipeline/overview` | `pg_stat_user_tables` | 系统统计查询 | 低 | 成本可接受，但仍应做短 TTL 缓存；见 `rebuild/backend/app/api/pipeline.py:17-37` |
| `GET /api/v1/pipeline/dim/lac-trusted` | `dim_lac_trusted`(881行) | `count(*)` + 分页 | 低 | 精确 count 可接受；见 `rebuild/backend/app/api/pipeline.py:42-71` |
| `GET /api/v1/pipeline/dim/bs-trusted` | `dim_bs_trusted`(13.8万行) | `count(*)` + 分页 | 中 | 每次两次查询；布尔/等级过滤可缓存；见 `rebuild/backend/app/api/pipeline.py:76-108` |
| `GET /api/v1/pipeline/profile/lac` | `profile_lac`(878行) | `count(*)` + 分页 | 低 | 问题不大；见 `rebuild/backend/app/api/pipeline.py:113-142` |
| `GET /api/v1/pipeline/profile/bs` | `profile_bs`(16.4万行) | `count(*)` + 分页 | 中 | 精确 count 每次重算；见 `rebuild/backend/app/api/pipeline.py:147-186` |
| `GET /api/v1/pipeline/profile/cell` | `profile_cell`(49.4万行) | `count(*)` + 分页 | 中 | 精确 count 每次重算；见 `rebuild/backend/app/api/pipeline.py:191-231` |
| `GET /api/v1/pipeline/stats/operator-tech` | `fact_final`(3049万行/18GB) | 全量 `GROUP BY` 聚合 | 高 | 不应做实时接口；见 `rebuild/backend/app/api/pipeline.py:236-249` |
| `GET /api/v1/pipeline/stats/gps-status` | `fact_gps_corrected`(2179万行/8.6GB) | 全量 `GROUP BY` 聚合 | 高 | 不应做实时接口；见 `rebuild/backend/app/api/pipeline.py:252-262` |
| `GET /api/v1/pipeline/stats/signal-fill` | `fact_signal_filled`(2179万行/7.0GB) | 全量 `GROUP BY` + `AVG` | 高 | 不应做实时接口；见 `rebuild/backend/app/api/pipeline.py:265-277` |
| `POST /api/v1/runs` | `wb_run` | 单行插入 | 低 | 无明显性能问题；见 `rebuild/backend/app/api/runs.py:13-31` |
| `GET /api/v1/runs` | `wb_run`(3行) | `count(*)` + 分页 | 低 | 量小；见 `rebuild/backend/app/api/runs.py:34-58` |
| `GET /api/v1/runs/{run_id}` | `wb_run` | 主键查询 | 低 | 无 |
| `PATCH /api/v1/runs/{run_id}/status` | `wb_run` | 单行更新 | 低 | 无性能问题，但缺不存在校验；见 `rebuild/backend/app/api/runs.py:72-87` |
| `GET /api/v1/steps` | `wb_step_registry`(22行) | 列表查询 | 低 | 可长 TTL 缓存；见 `rebuild/backend/app/api/steps.py:13-32` |
| `GET /api/v1/steps/{step_id}` | `wb_step_registry` | 主键查询 | 低 | 可长 TTL 缓存；见 `rebuild/backend/app/api/steps.py:35-45` |
| `GET /api/v1/steps/{step_id}/io-summary` | `wb_step_registry` + `pg_stat_user_tables` | 元数据查询 | 低 | 逻辑正确，但应批量查一次 stats 表；见 `rebuild/backend/app/api/steps.py:48-74` |
| `GET /api/v1/steps/{step_id}/parameters` | `wb_parameter_set`(1行) | 取最新 active JSON | 低 | 可长 TTL 缓存；见 `rebuild/backend/app/api/steps.py:77-100` |
| `GET /api/v1/metrics/layer-snapshot` | `raw_records`、`fact_*`、`profile_*` 等 11 表 | 11 次实时 `count(*)` | 极高 | 首页每次打开都会触发；见 `rebuild/backend/app/api/metrics.py:12-40` |
| `GET /api/v1/metrics/step-summary` | `raw_records`、`fact_filtered`、`dim_bs_trusted`、`fact_gps_corrected`、`fact_signal_filled`、`fact_final`、`profile_*` | 多段实时聚合 + 子查询 | 极高 | 绕过 `wb_step_metric` 设计；见 `rebuild/backend/app/api/metrics.py:43-135` |
| `GET /api/v1/metrics/anomaly-summary` | `profile_bs`、`profile_cell` | 9 段 `UNION ALL` 重复聚合 | 中 | 应改读 `wb_anomaly_stats`；见 `rebuild/backend/app/api/metrics.py:138-174` |

### 前端缓存分析
- `rebuild/frontend/app.js:5-8` 的 `api()` 只是裸 `fetch`，没有内存缓存、`sessionStorage`、`localStorage`、ETag、超时控制，也没有请求去重。
- `rebuild/frontend/app.js:41-62` 启动时先请求一次 `/steps` 和 `/steps/s0/parameters`，然后立刻进入 `loadOverview()`。
- `rebuild/frontend/app.js:72-79` 的 `loadOverview()` 每次都会重新请求 `/pipeline/overview`、`/metrics/step-summary`、`/metrics/layer-snapshot`。这正好把两个最重的 metrics 接口放到了首页首屏路径。
- `rebuild/frontend/app.js:151-153` 的 `loadAnomaly()` 每次进入异常页都重新请求 `/metrics/anomaly-summary`。
- `rebuild/frontend/app.js:182-190` 的 `loadStep()` 每次切步骤都重新请求 `/steps/{id}`、`/io-summary`、`/parameters`，没有 step 级缓存。
- `rebuild/frontend/index.html:11-19` 当前上下文条没有任何“刷新 / 强制刷新 / 更新时间”控件，用户无法手动控制数据更新频率。
- `rebuild/frontend/app.js:242-247` 只在 `init()` 顶层做了一次 `catch`。初始化之后的 `loadOverview()` / `loadAnomaly()` / `loadStep()` 没有页面级错误恢复，接口失败时页面可能卡在“加载中...”。

### 缓存方案建议
#### 1. 后端内存缓存（TTL）
适合“元数据小、变更少、用户希望秒开”的接口：
- `GET /steps`
- `GET /steps/{step_id}`
- `GET /steps/{step_id}/parameters`
- `GET /steps/{step_id}/io-summary`
- `GET /pipeline/overview`

建议：
- `steps` / `step detail` / `parameters`：TTL 30 分钟到 1 小时。
- `io-summary` / `pipeline/overview`：TTL 5 分钟。
- 增加统一返回字段：`generated_at`、`cache_hit`、`source`。

#### 2. 快照表 / 物化视图
适合“依赖千万级事实表聚合”的接口：
- `GET /metrics/layer-snapshot` -> 读 `workbench.wb_layer_snapshot`
- `GET /metrics/step-summary` -> 读 `workbench.wb_step_metric`
- `GET /metrics/anomaly-summary` -> 读 `workbench.wb_anomaly_stats`
- `GET /pipeline/stats/operator-tech` / `gps-status` / `signal-fill` -> 改为物化视图或 `wb_step_metric` 的衍生快照

设计文档本来就是这么规划的：
- `rebuild/docs/04_指标注册表.md:12-18`
- `rebuild/docs/04_指标注册表.md:241-275`
- `rebuild/docs/04_指标注册表.md:308-315`
- `rebuild/docs/05_工作台元数据DDL.md:222-295`

当前数据库里这些表已经存在，但还没有被使用，且数据基本为空：
- `wb_step_metric` 0 行
- `wb_layer_snapshot` 0 行
- `wb_anomaly_stats` 0 行
- `wb_gate_result` 0 行

#### 3. 前端缓存
建议按数据性质分层：
- `sessionStorage`：`overview`、`anomaly`、`step:{id}`，适合“当前 tab 的最近结果”
- `localStorage`：表名/字段名中文字典、步骤注册表、最近一次成功的版本上下文
- 内存 `Map`：同一页面生命周期内请求去重

#### 4. 手动刷新 vs 自动刷新
建议改成“默认读缓存 + 用户手动刷新”，而不是“每次进页面现算”：
- 顶部上下文条增加：`上次刷新时间`、`刷新缓存`、`强制重算` 三个控件
- 当存在运行中的 run 时，只自动轮询轻量状态接口，不自动刷新重型指标
- 如果缓存过期，只提示“数据可能不是最新”，不要自动触发重算

### 代码级修改建议
- `rebuild/backend/app/api/metrics.py:get_layer_snapshot` (`12-40`)
  - 当前问题：11 次实时 `count(*)`
  - 建议：改读 `workbench.wb_layer_snapshot` 最新 run；若 `refresh=true`，触发后台任务重算后回写
- `rebuild/backend/app/api/metrics.py:get_step_summary` (`43-135`)
  - 当前问题：多张大表实时聚合，绕过 `wb_step_metric`
  - 建议：把 Step0/4/6/30/31/33/41/50-52 的聚合改为 run 完成后写入 `wb_step_metric`；接口只做读取和整形
- `rebuild/backend/app/api/metrics.py:get_anomaly_summary` (`138-174`)
  - 当前问题：`profile_bs` / `profile_cell` 重复扫描
  - 建议：改读 `wb_anomaly_stats`
- `rebuild/backend/app/api/pipeline.py:get_operator_tech_stats` / `get_gps_status_distribution` / `get_signal_fill_distribution` (`236-277`)
  - 当前问题：大表实时聚合
  - 建议：改成物化视图或 snapshot 表；前台只在“查看详情”时手动刷新
- `rebuild/backend/app/api/steps.py:get_step_io_summary` (`48-74`)
  - 当前问题：按表循环查 `pg_stat_user_tables`
  - 建议：一次性 `WHERE relname = ANY(...)` 批量查询，减少 round trip
- `rebuild/frontend/index.html:11-19`
  - 当前问题：没有刷新控制和刷新时间
  - 建议：增加 `ctx-last-refresh`、`ctx-refresh`、`ctx-force-refresh`
- `rebuild/frontend/app.js:5-8`
  - 当前问题：裸 `fetch`
  - 建议：把 `api(path, {ttl, storageKey, force})` 做成统一缓存层
- `rebuild/frontend/app.js:72-79`
  - 当前问题：首页直接并发拉最重的三个接口
  - 建议：先渲染缓存快照，再允许手动刷新
- `rebuild/frontend/app.js:151-153`、`182-190`
  - 当前问题：切页必重拉，无错误恢复
  - 建议：加页面级 `try/catch`、stale cache fallback、请求去重

## 维度 B：UI 完整性
**评定：** 未通过

当前前端只实现了“粗略版 P1 + 简化版 P2 + 额外一个异常统计页”。和 `rebuild/docs/00_重构上下文与范围.md:185-199` 及 V2 设计稿相比，P3 字段治理、P4 样本研究、D1/D2/D3 抽屉基本缺席；P2 的 8 个区块只覆盖了 2 个半区块。

### V2 设计 vs 当前实现对比矩阵
| V2 组件 | V2 功能描述 | 当前状态 | 缺失项 |
|---------|-----------|---------|--------|
| P1-顶部上下文条 | Run / Compare / 参数集 / 规则集 / SQL / 契约 + 版本抽屉 + 刷新时间；见 `docs/data_warehouse/Pre_UI/V2/index.html:12-23` | 部分实现：当前只有 `Run / 参数集 / 状态` 三个标签；见 `rebuild/frontend/index.html:11-19`。且 JS 只写入参数集和状态，不写 Run；见 `rebuild/frontend/app.js:54-59` | 缺 Compare、规则集、SQL 版本、契约版本、版本抽屉、刷新时间、刷新按钮 |
| P1-侧栏辅助页 | 字段治理 / 样本研究；见 `docs/data_warehouse/Pre_UI/V2/index.html:56-58` | 当前是 `P1 链路总览` + `异常统计`；见 `rebuild/frontend/index.html:29-37` | 缺 P3、P4 入口；异常统计不是 V2 替代品 |
| P1-链路节点图 | 9 个节点，含 `Cell统计`、`画像/基线`、`伪日更`，并展示 diff tag；见 `docs/data_warehouse/Pre_UI/V2/index.html:64-113` | 部分实现：有流程图，但节点集合不同；见 `rebuild/frontend/app.js:95-114` | 缺 `Cell统计`、`伪日更`、`画像/基线` 拆分；没有 run 对比变化标签；反而硬编码了 `合规过滤` |
| P1-当前 Run 摘要 | 当前 run 详情卡；见 `docs/data_warehouse/Pre_UI/V2/index.html:115-130` | 缺失 | 缺 run 类型、输入窗口、版本绑定、耗时 |
| P1-对比 Run 摘要 | compare run 详情卡；见 `docs/data_warehouse/Pre_UI/V2/index.html:131-145` | 缺失 | 缺 compare run 上下文 |
| P1-步骤差异摘要 | `Run#A vs Run#B` 步骤级 diff 表；见 `docs/data_warehouse/Pre_UI/V2/index.html:147-185` | 缺失 | 无步骤级 diff、无 drill-down |
| P1-重点关注 | 问题/改善/字段变化列表；见 `docs/data_warehouse/Pre_UI/V2/index.html:187-215` | 缺失 | 无关注项列表，无跨页跳转 |
| P1-操作区 | 全链路重跑 / 局部重跑；见 `docs/data_warehouse/Pre_UI/V2/index.html:217-221` | 缺失 | 无任何重跑操作入口 |
| D1-版本与运行抽屉 | 当前版本体系、最近运行、参数变更、规则变更；见 `docs/data_warehouse/Pre_UI/V2/index.html:224-268` | 缺失。当前前端无 drawer 结构；`main.py` 也只挂了 4 组路由；见 `rebuild/backend/app/main.py:28-31` | 缺 UI、缺聚合 API、缺真实版本数据 |
| P2-A 步骤说明 | 业务目的、上下游、状态、当前库映射；见 `docs/.../step-lac.html:42-53`、`step-bs.html:45-56`、`step-cell.html:39-49`、`step-gps.html:39-49` | 部分实现：只在页头显示 `step_id / layer / sql_file / 主链路`；见 `rebuild/frontend/app.js:197-201` | 缺业务目的、上下游链接、状态 tag、旧表映射 |
| P2-B 输入/输出 | 输入/输出表 + 行数 + 主键 + 粒度 + vs compare；见 `docs/.../step-*.html` 各自 B 区块 | 部分实现：只有输入表/输出表名和行数；见 `rebuild/frontend/app.js:203-219` | 缺主键、维度、compare 差异、业务解释 |
| P2-C 规则 | 规则列表、参数、命中率、影响范围；见 `docs/.../step-lac.html:70-106`、`step-bs.html:73-135`、`step-cell.html:64-81`、`step-gps.html:65-102` | 缺失 | 完全没有规则区 |
| P2-D 参数 | 参数表 + 与上版本 diff；见 `docs/.../step-*.html` 各自 D 区块 | 部分实现：能展示当前参数；见 `rebuild/frontend/app.js:221-236` | 缺上版本比较、参数变化标识、参数集来源说明 |
| P2-E SQL | SQL 列表、用途、展开入口；见 `docs/.../step-*.html` 各自 E 区块 | 缺失。当前只在页头打印 `sql_file` 字符串；见 `rebuild/frontend/app.js:200` | 缺 SQL 清单、SQL 正文、参数替换、版本 diff |
| P2-F 数据变化 | metric cards + 变化表；见 `docs/.../step-*.html` 各自 F 区块 | 缺失 | 完全没有数据变化区 |
| P2-G 差异 | 当前 run vs compare run 差异；见 `docs/.../step-*.html` 各自 G 区块 | 缺失 | 完全没有差异区 |
| P2-H 样本 | 典型/异常/边界样本列表；见 `docs/.../step-*.html` 各自 H 区块 | 缺失 | 完全没有样本区 |
| P2-操作区 | 从此步骤开始重跑 / 仅重跑此步骤 / 样本重跑；见 `docs/.../step-*.html` 尾部 | 缺失 | 无操作入口 |
| D2-SQL 查看抽屉 | SQL 正文、参数替换、版本差异；见 `docs/data_warehouse/Pre_UI/V2/step-bs.html:295-360` | 缺失 | 无抽屉、无 SQL API、无 diff API |
| D3-样本/对象详情抽屉 | 原始值 vs 处理后 + 命中规则 + compare run；见 `docs/data_warehouse/Pre_UI/V2/step-bs.html:362-409`、`samples.html:188-247` | 缺失 | 无抽屉、无样本详情 API |
| P3-字段治理 | 筛选条、健康概览、字段注册表、展开治理详情；见 `docs/data_warehouse/Pre_UI/V2/fields.html:39-250` | 完全缺失。当前前端无入口，后端也无 `meta` API；`main.py:28-31` 仅挂 `pipeline/runs/steps/metrics` | 缺页面、缺 API、缺数据填充 |
| P4-样本研究 | 标签筛选、来源步骤/Run 筛选、样本集列表、样本集展开、样本详情抽屉；见 `docs/data_warehouse/Pre_UI/V2/samples.html:39-247` | 完全缺失。当前前端无入口，后端无样本 API；`wb_sample_set` 也是空表 | 缺页面、缺 API、缺数据填充 |

### P2 八区块覆盖结论
- 已覆盖：B 输入/输出（简化版）、D 参数（简化版）
- 半覆盖：A 步骤说明（只剩页头元信息）
- 未覆盖：C 规则、E SQL、F 数据变化、G 差异、H 样本

也就是说，当前 `loadStep()` 只覆盖了 V2 P2 的 `2.5 / 8`。

### 补齐建议
- `rebuild/frontend/index.html`
  - 把辅助导航恢复为 `P1/P3/P4`，异常统计可并入 P1 或 P2 的次级卡片，不要占掉主导航名额
  - 顶部上下文条补齐 compare run / 规则集 / SQL / 契约 / 刷新控件
- `rebuild/frontend/app.js`
  - 拆成 `renderOverview()`、`renderStepSummary()`、`renderStepRules()`、`renderStepSql()`、`renderFieldGovernance()`、`renderSamples()` 等渲染函数
  - `loadOverview()` 需要新增：run 摘要、compare run 摘要、步骤差异摘要、重点关注、操作区
  - `loadStep()` 需要补齐 8 个区块，并按 step 类型支持不同字段
- 后端新增 API 组
  - `GET /api/v1/version/current`
  - `GET /api/v1/version/history`
  - `GET /api/v1/steps/{step_id}/rules`
  - `GET /api/v1/steps/{step_id}/sql`
  - `GET /api/v1/steps/{step_id}/diff`
  - `GET /api/v1/steps/{step_id}/samples`
  - `GET /api/v1/fields`
  - `GET /api/v1/fields/{field_name}`
  - `GET /api/v1/samples`
  - `GET /api/v1/samples/{sample_set_id}`

## 维度 C：可理解性
**评定：** 未通过

“中文步骤名”这一点只做对了一半。`wb_step_registry.step_name` 确实在导航和步骤标题中被用了起来，但用户实际看到的仍然有大量英文表名、层级码、异常码、SQL 文件名和 Launcher 文案，尤其是 `pipeline.xxx` 表名会直接暴露给用户。

### 前端展示给用户的英文名清单
#### 1. Pipeline 表名
这些名称会直接出现在工作台表格中：
- `raw_records`
- `dim_lac_trusted`
- `dim_cell_stats`
- `fact_filtered`
- `dim_bs_trusted`
- `fact_gps_corrected`
- `fact_signal_filled`
- `fact_final`
- `profile_lac`
- `profile_bs`
- `profile_cell`
- `map_cell_bs`
- `stats_base_raw`
- `stats_lac`
- `compare_gps`
- `compare_signal`
- `detect_anomaly_bs`
- `detect_collision`

证据：
- `rebuild/frontend/app.js:142`
- `rebuild/frontend/app.js:209`
- `rebuild/frontend/app.js:216`

#### 2. 层级和异常编码
- 层级码：`L0_raw`、`L2_filtered`、`L2_lac_trusted`、`L2_cell_stats`、`L3_bs_trusted`、`L3_gps_corrected`、`L3_signal_filled`、`L3_cell_bs_map`、`L4_final`、`L5_lac_profile`、`L5_bs_profile`、`L5_cell_profile`
- 对象级别：`BS`、`Cell`
- 异常类型：`collision_suspect`、`severe_collision`、`gps_unstable`、`bs_id_lt_256`、`multi_operator_shared`、`insufficient_sample`、`dynamic_cell`

证据：
- `rebuild/frontend/app.js:81-83`
- `rebuild/frontend/app.js:135`
- `rebuild/frontend/app.js:162-163`
- `rebuild/backend/app/api/metrics.py:142-167`

#### 3. 步骤英文名
步骤页标题会同时显示中文名和 `step_name_en`：
- `Standardization`
- `Base Statistics`
- `Compliance Marking`
- `LAC Statistics`
- `Trusted LAC Library`
- `Cell Statistics`
- `Compliance Filtering`
- `Master BS Library`
- `GPS Correction`
- `GPS Comparison`
- `Signal Fill`
- `Signal Comparison`
- `Dynamic Cell Detection`
- `BS ID Anomaly Mark`
- `Collision Insufficient Mark`
- `Cell-BS Map Delivery`
- `Full Return GPS`
- `Full Return Signal`
- `Final Comparison`
- `LAC Profile`
- `BS Profile`
- `Cell Profile`

证据：
- `rebuild/frontend/app.js:198`
- `workbench.wb_step_registry` 实际数据

#### 4. Launcher 文案
Launcher 仍有明显英文控制面板文案：
- `Service Launcher & Control Panel`
- `Start`
- `Stop`
- `Restart`
- `Kill Port`
- `Workbench Pages`
- `Pipeline Overview API`
- `Step Summary API`
- `Anomaly Summary API`

证据：
- `rebuild/launcher_web.py:330`
- `rebuild/launcher_web.py:346-355`
- `rebuild/launcher_web.py:360`
- `rebuild/launcher_web.py:379-389`

### COMMENT ON TABLE / COMMENT ON COLUMN 检查
PG17 实际检查结果：
- `pipeline` 18 张表里，只有 `raw_records` 有表注释；其余 17 张都没有
- `pipeline` 18 张表的 561 个字段，`COMMENT ON COLUMN` 为 0

这意味着：
- 用户在数据库工具里几乎看不到中文说明
- 前端如果想走“数据库注释回显”，当前没有任何可用元数据

### wb_step_registry.step_name 是否正确用于 UI
结论：部分正确。

已正确使用：
- 侧栏导航：`rebuild/frontend/app.js:46-52`
- 步骤页标题：`rebuild/frontend/app.js:198`

仍有问题：
- P1 概览流程节点不是从 `wb_step_registry` 派生，而是硬编码中文标签；见 `rebuild/frontend/app.js:99-113`
- 同一页面又同时显示 `step_name_en`，导致“中文已存在但仍把英文抛给用户”；见 `rebuild/frontend/app.js:198`
- 异常页没有本地化 `object_level` / `anomaly_type`，直接显示英文码；见 `rebuild/frontend/app.js:162-163`

### Doc02 §2.1 映射字典是否可直接用于前端翻译
结论：可直接用于“字段名中文化”，但不足以单独完成整个前端中文化。

可直接用的部分：
- `rebuild/docs/02_新旧表体系映射.md:53-129`
- 这部分已经给出中文字段名 -> 英文字段名的映射，可直接转成 `field_name -> field_name_cn`

还不够的部分：
- 表名中文化还需要 `Doc02` 的 1.2 新旧表对照；见 `rebuild/docs/02_新旧表体系映射.md:19-47`
- 异常码、层级码、Launcher 文案、SQL 文件名，不在 §2.1 里
- 当前 `meta_field_registry` 虽然有 `field_name_cn` 列，但表是空的，不能直接供前端用

### 具体中文化方案
- 后端
  - 为所有 `pipeline` 表补 `COMMENT ON TABLE`
  - 为核心字段补 `COMMENT ON COLUMN`
  - 初始化 `meta.meta_field_registry.field_name_cn`
  - 在接口里同时返回 `code + label`，例如 `table_name` + `table_name_cn`、`anomaly_type` + `anomaly_type_cn`
- 前端
  - 表名展示改为 `中文名` 主展示，`pipeline.xxx` 作为次级灰字
  - 层级码展示改为 `L0 原始层`、`L3 GPS修正层` 之类的中文 label
  - 异常类型统一做字典映射，不直接暴露 snake_case
  - 步骤页默认只显示中文名，英文名放到 tooltip 或“技术标识”里
- 数据来源
  - 表级字典：来自 `Doc02` §1.2
  - 字段级字典：来自 `Doc02` §2.1
  - 步骤级字典：来自 `workbench.wb_step_registry.step_name`
  - 异常级字典：新增一张 `workbench.wb_anomaly_type_dict` 或写死到前端常量

## 维度 D：代码质量与架构
**评定：** 部分通过

### 1. SQL 注入风险
结论：当前没有发现“直接把用户输入拼进 SQL 值位”的高危注入点，但动态 SQL 的写法不稳妥。

具体情况：
- `rebuild/backend/app/api/pipeline.py:59`
- `rebuild/backend/app/api/pipeline.py:96`
- `rebuild/backend/app/api/pipeline.py:130`
- `rebuild/backend/app/api/pipeline.py:174`
- `rebuild/backend/app/api/pipeline.py:219`
- `rebuild/backend/app/api/runs.py:47`
- `rebuild/backend/app/api/runs.py:52`
- `rebuild/backend/app/api/steps.py:28`
- `rebuild/backend/app/api/steps.py:63`

这些位置都用了 f-string 拼接 SQL 片段，但当前 `where_clause` 只来自代码里固定的列名片段，实际值仍走参数绑定，所以“现在”不是立即可打的注入洞。问题在于：
- 这种模式很容易被后续维护者误扩展成拼接用户输入
- 读起来难以判断边界是否安全

建议：
- 改用 SQLAlchemy Core 条件拼装
- 或至少把 `where_clause` 约束在受控枚举，不允许拼接自由文本

### 2. 错误处理
- 前端只有启动阶段有总 `catch`；见 `rebuild/frontend/app.js:242-247`
- `loadOverview()`、`loadAnomaly()`、`loadStep()` 都没有局部错误恢复；见 `rebuild/frontend/app.js:72-79`、`151-153`、`182-190`
- `api()` 只抛出 `API ${path}: ${status}`，没有响应体、没有超时、没有重试；见 `rebuild/frontend/app.js:5-8`
- `update_run_status()` 没校验 `run_id` 是否存在，更新 0 行时也会返回成功；见 `rebuild/backend/app/api/runs.py:78-87`
- `setActive()` 只认 `data-id`，但 `overview/anomaly` 侧栏项没有 `data-id`，导致辅助页激活态失效；见 `rebuild/frontend/app.js:33-37` 对比 `rebuild/frontend/index.html:31-35`

### 3. 连接池配置
- 当前连接池配置：`pool_size=5`、`max_overflow=10`、`pool_pre_ping=True`、`pool_recycle=300`；见 `rebuild/backend/app/core/database.py:6-13`
- Launcher 默认只起 1 个 worker；见 `rebuild/launcher_web.py:78-85`

判断：
- 对开发环境本身算“够用”
- 但在首页每次都跑重型聚合的前提下，5 个常驻连接非常容易被长查询占满
- 没有 `statement_timeout` / `command_timeout` / `pool_timeout`，慢查询会长时间占住连接

### 4. 前端代码复用
结论：几乎没有组件化复用。

证据：
- `rebuild/frontend/app.js:72-146`
- `rebuild/frontend/app.js:155-177`
- `rebuild/frontend/app.js:197-237`

问题：
- 大量 HTML 直接用模板字符串拼接
- 表格、卡片、状态条、错误块都没有抽象成可复用 render 函数
- 这也是 P3/P4 迟迟补不上的一个直接原因，扩展成本太高

### 5. 后端 service 层抽象
结论：没有。

证据：
- `rebuild/backend/app/api/pipeline.py` 整体
- `rebuild/backend/app/api/runs.py` 整体
- `rebuild/backend/app/api/steps.py` 整体
- `rebuild/backend/app/api/metrics.py` 整体

当前结构是“router 直接写 SQL + 直接整形返回”。结果是：
- 缓存逻辑无处安放
- `pipeline` / `metrics` / `steps` 无法复用同一套表翻译和快照逻辑
- 想接 `workbench/meta` 也只能继续把逻辑塞进 router

### 6. 额外架构风险
- 数据库连接串硬编码在源码中；见 `rebuild/backend/app/core/config.py:5-6`
- CORS 配置为 `allow_origins=["*"]` 且 `allow_credentials=True`；见 `rebuild/backend/app/main.py:20-26`
- Launcher 的控制台和页面链接文案仍然偏英文，且没有 P3/P4 快捷入口；见 `rebuild/launcher_web.py:360-391`

## 总体结论
**结论：** 需修改后可用

当前版本更像“把数据库接上后的第一版浏览器面板”，还不是设计文档和 V2 草图里定义的“治理链路调试与验证工作台”。核心卡点有三类：
- 性能路径错误：把快照类工作做成了实时重算，导致首页天然慢
- UI 完整性不足：P2 只有 2.5/8 区块，P3/P4/D1/D2/D3 基本没落地
- 可理解性不足：表名、异常码、Launcher 文案仍大量英文，数据库注释体系几乎空白

但也有一个积极点：底层数据库 schema 已经把 `workbench` / `meta` 的骨架建好了，`wb_step_registry` 也有 22 个步骤定义。这意味着问题更多是“实现没有沿着设计去接”，不是“设计基础不存在”。

### 必须修改项
| # | 优先级 | 问题 | 涉及文件 | 修改方案 | 工作量 |
|---|--------|------|---------|---------|--------|
| 1 | P0 | 首页和概览接口实时扫描大表，性能模型错误 | `rebuild/backend/app/api/metrics.py`、`rebuild/frontend/app.js` | 改为 `wb_layer_snapshot` / `wb_step_metric` / `wb_anomaly_stats` 快照读取，前端默认读缓存并提供手动刷新 | M |
| 2 | P0 | P2 只实现 IO + 参数，P3/P4/D1/D2/D3 缺失 | `rebuild/frontend/index.html`、`rebuild/frontend/app.js`、`rebuild/backend/app/main.py` 及新增 API | 按 V2 恢复 4 主页面 + 3 抽屉结构，补规则/SQL/差异/样本/字段/样本集 API | L |
| 3 | P0 | `workbench/meta` 表已建但没有被业务代码使用，且数据基本为空 | `rebuild/backend/app/api/metrics.py`、新增任务/初始化脚本 | 把 run 完成后的指标/异常/字段健康写入 `workbench/meta`，不要继续在 GET 接口实时算 | M |
| 4 | P1 | 用户可见英文名过多，17/18 表无注释，561 列 0 注释 | 数据库 DDL / 初始化脚本、`rebuild/frontend/app.js`、`rebuild/launcher_web.py` | 补 COMMENT、填充 `meta_field_registry.field_name_cn`，前端统一 `code + label` 展示 | M |
| 5 | P1 | 前端没有缓存、没有刷新控件、页面级错误恢复缺失，`ctx-run` 永远为空 | `rebuild/frontend/index.html`、`rebuild/frontend/app.js` | 增加缓存层、刷新按钮、更新时间、页面级 `try/catch`，并接入当前 run 信息 | S-M |
| 6 | P1 | Router 直写 SQL，没有 service/cache 层，难以承载后续 P3/P4 和快照逻辑 | `rebuild/backend/app/api/*.py`、新增 `services/` 模块 | 把 metrics/version/translation/cache 逻辑下沉到 service 层 | M |

### 建议改进项
- 把 `pipeline/stats/operator-tech`、`gps-status`、`signal-fill` 变成“次级详情页 + 手动刷新”，不要留在公共实时接口层
- `loadOverview()` 的流程节点改从 `wb_step_registry` 派生，而不是硬编码
- 统一前端展示规则：中文主标题，英文码灰字附属，不再裸露 snake_case
- Launcher 补齐 P3/P4 链接和“刷新快照”入口
- 将 `config.py` 中硬编码连接串迁移到 `.env`

## 审计备注
- 已按提示完整阅读 24 个指定文件
- 已补充 PG17 实际结构、行数、索引、注释、EXPLAIN 证据
- 本次审计为只读分析，未修改业务代码；仅新增本报告文件
