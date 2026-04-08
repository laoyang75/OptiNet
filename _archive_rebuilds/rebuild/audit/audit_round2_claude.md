# Claude 第二轮审计报告

> 审计日期：2026-03-24
> 审计文件数：24
> 审计 Agent：Claude（第二轮）

---

## 维度 A：性能与缓存

**评定：** 🔴 未通过

### A.1 逐 API 性能分析

| API 端点 | 文件 | 查询目标表 | 是否全表扫描 | 风险等级 |
|---------|------|-----------|------------|---------|
| `GET /metrics/layer-snapshot` | metrics.py:12 | `raw_records` (2.5亿) + `fact_final` (3050万) 等12张表 | ✅ **全表 COUNT(*)** x12 | 🔴 极高 |
| `GET /metrics/step-summary` | metrics.py:43 | `raw_records`, `dim_lac_trusted`, `fact_filtered`, `dim_bs_trusted`, `fact_gps_corrected`, `fact_signal_filled`, `fact_final`, `profile_*` | ✅ **全表 COUNT(*) FILTER** x8 | 🔴 极高 |
| `GET /metrics/anomaly-summary` | metrics.py:138 | `profile_bs` x6 + `profile_cell` x3 | ✅ **全表 COUNT(*)** x9 | 🟠 高 |
| `GET /pipeline/overview` | pipeline.py:17 | `pg_stat_user_tables` | ❌ 系统表查询 | 🟢 低 |
| `GET /pipeline/stats/operator-tech` | pipeline.py:236 | `fact_final` (3050万) | ✅ **全表 GROUP BY** | 🔴 极高 |
| `GET /pipeline/stats/gps-status` | pipeline.py:252 | `fact_gps_corrected` (2178万) | ✅ **全表 GROUP BY** | 🔴 极高 |
| `GET /pipeline/stats/signal-fill` | pipeline.py:265 | `fact_signal_filled` (2178万) | ✅ **全表 GROUP BY + AVG** | 🔴 极高 |
| `GET /pipeline/dim/lac-trusted` | pipeline.py:42 | `dim_lac_trusted` (881行) | ❌ 分页 | 🟢 低 |
| `GET /pipeline/dim/bs-trusted` | pipeline.py:76 | `dim_bs_trusted` (14万行) | ❌ 分页 | 🟢 低 |
| `GET /pipeline/profile/lac` | pipeline.py:113 | `profile_lac` (878行) | ❌ 分页 | 🟢 低 |
| `GET /pipeline/profile/bs` | pipeline.py:147 | `profile_bs` (16万行) | ❌ 分页 | 🟡 中 |
| `GET /pipeline/profile/cell` | pipeline.py:191 | `profile_cell` (49万行) | ❌ 分页 | 🟡 中 |
| `GET /steps` | steps.py:13 | `wb_step_registry` (22行) | ❌ 小表 | 🟢 低 |
| `GET /steps/{id}` | steps.py:35 | `wb_step_registry` | ❌ 主键查询 | 🟢 低 |
| `GET /steps/{id}/io-summary` | steps.py:48 | `pg_stat_user_tables` | ❌ 系统表 | 🟢 低 |
| `GET /steps/{id}/parameters` | steps.py:77 | `wb_parameter_set` | ❌ 小表 | 🟢 低 |
| `POST /runs` | runs.py:13 | `wb_run` 写入 | ❌ | 🟢 低 |
| `GET /runs` | runs.py:34 | `wb_run` (百级) | ❌ 分页 | 🟢 低 |
| `GET /runs/{id}` | runs.py:61 | `wb_run` 单行 | ❌ | 🟢 低 |
| `PATCH /runs/{id}/status` | runs.py:72 | `wb_run` 更新 | ❌ | 🟢 低 |
| `GET /health` | main.py:34 | 无查询 | ❌ | 🟢 无 |

**关键问题**：P1 总览页加载时同时触发 `/pipeline/overview` + `/metrics/step-summary` + `/metrics/layer-snapshot` 三个 API，其中后两个合计发起 **~20+ 个全表 COUNT(*) 扫描**，涉及 `raw_records`(2.5亿行)、`fact_final`(3050万行)、`fact_filtered`(2178万行) 等大表。预估首次加载耗时 **30秒~数分钟**。

### A.2 前端数据加载策略分析

| 问题 | 位置 | 说明 |
|------|------|------|
| 页面加载即触发3个并行API | app.js:74 `Promise.all([overview, stepSummary, layers])` | 无缓存，每次进入 P1 都重新查询 |
| 步骤切换触发3个API | app.js:186 `Promise.all([step, io, params])` | 每次切换步骤都重查，但 step/params 数据基本不变 |
| 无 loading 超时/重试 | 全局 | 大表查询超时后无友好提示 |
| 无数据缓存 | 全局 | 无 localStorage/sessionStorage/内存缓存 |

### A.3 分层缓存方案建议

#### DB 层
- 为 `layer-snapshot` 创建物化视图 `mv_layer_snapshot`，含每表预计算行数
- 为 `step-summary` 创建物化视图 `mv_step_summary`，含每步骤关键指标
- 为 `anomaly-summary` 创建物化视图 `mv_anomaly_summary`
- 刷新策略：每次 Run 完成后执行 `REFRESH MATERIALIZED VIEW CONCURRENTLY`

#### 后端层
- 为 `step-summary`、`layer-snapshot`、`anomaly-summary` 添加内存缓存（TTL=300s）
- 添加 `GET /cache/status` 和 `POST /cache/refresh` 端点供手动刷新
- 缓存键：`{endpoint}:{run_id}`

#### 前端层
- 步骤注册表（`/steps`）和参数集数据缓存到 `sessionStorage`（会话内不变）
- 指标数据缓存到 JS 内存，切换步骤时复用
- 添加「上次刷新: XX秒前」显示和手动刷新按钮

### A.4 手动刷新 vs 自动刷新 UI 设计

**建议方案**：
1. 首次加载从缓存读取（如有），并行发起后台刷新
2. 顶部上下文条添加「🔄 刷新数据 | 最后更新: 2分钟前」
3. 治理链路逐步推进时，已调好的步骤数据不自动刷新（用户明确点刷新才重查）
4. 每个 card 右上角添加独立刷新按钮（局部刷新而非全页重载）

### A.5 代码级修改建议

| 修改项 | 涉及文件 | 优先级 | 工作量 |
|--------|---------|--------|--------|
| 创建 3 个物化视图 | 新增 SQL 迁移脚本 | P0 | 2h |
| `metrics.py` 改查物化视图 | metrics.py `get_layer_snapshot`, `get_step_summary`, `get_anomaly_summary` | P0 | 1h |
| 后端添加缓存中间件 | 新增 `app/core/cache.py` | P1 | 2h |
| 添加缓存刷新 API | 新增路由 | P1 | 1h |
| 前端 sessionStorage 缓存 | app.js `api()` 函数 | P1 | 1h |
| 前端刷新按钮 | index.html + app.js | P2 | 1h |

---

## 维度 B：UI 完整性

**评定：** 🔴 未通过

### V2 vs 当前对比矩阵

#### P1 治理链路总览

| V2 组件 | V2 功能 | 当前状态 | 缺失项 |
|---------|--------|---------|--------|
| 顶部上下文条 | Run#/Compare#/参数集/规则集/SQL/契约/基线 + 版本抽屉按钮 | ⚠️ 部分实现：仅 Run/参数集/状态 | 缺 Compare Run、规则集、SQL版本、契约、基线、版本抽屉按钮 |
| 链路节点图 | 9 节点，含状态色(done/current/pending)、行数、diff 标记(+2/+453) | ⚠️ 部分实现：有8节点 | 缺 done/current/pending 状态色区分、diff 标记、"伪日更"节点 |
| Run 摘要对比 | 当前 Run vs 对比 Run 并排的详情网格 | ❌ 完全缺失 | 整块缺失 |
| 步骤差异摘要表 | 每步骤的 #当前/#对比/变化/变化率，可点击跳转 | ❌ 完全缺失 | 整块缺失 |
| 重点关注 | 自动识别变化最大步骤、新增问题、字段变化、改善 | ❌ 完全缺失 | 整块缺失 |
| 操作区 | "全链路重跑"/"选择步骤局部重跑"按钮 | ❌ 完全缺失 | 整块缺失 |

#### P2 步骤工作台（8区块）

| V2 区块 | V2 功能 | 当前状态 | 缺失项 |
|---------|--------|---------|--------|
| A 步骤说明 | 名称/业务目的/上下游步骤/状态/当前库映射 | ⚠️ 极简实现：仅 step_name + step_name_en + layer + sql_file | 缺业务目的、上下游步骤链接、当前库映射 |
| B 输入/输出 | 输入表/输出表的行数 + vs 对比 Run 的差异 | ⚠️ 部分实现：仅表名和行数 | 缺 vs 对比 Run 差异标记 |
| C 规则区 | 每条规则的名称/目的/关键参数/命中数/影响范围，可展开 | ❌ 完全缺失 | 整块缺失 |
| D 参数区 | 当前值 vs 上次值，变化高亮 | ⚠️ 部分实现：显示参数 JSON | 缺 vs 上次值对比、变化高亮 |
| E SQL 区 | SQL 列表，可展开查看代码，参数替换，版本差异 | ❌ 完全缺失 | 整块缺失 |
| F 数据变化 | 指标卡片行 + 分类统计表 | ❌ 完全缺失 | 整块缺失 |
| G 差异区 | 当前 Run vs 对比 Run 的逐项对比表 + 对象变化明细 | ❌ 完全缺失 | 整块缺失 |
| H 样本区 | 分类样本列表（典型/异常/边界），可展开详情抽屉 | ❌ 完全缺失 | 整块缺失 |
| 操作区 | "从此步骤重跑"/"仅重跑此步骤"/"样本重跑"按钮 | ❌ 完全缺失 | 整块缺失 |

#### P3 字段治理

| V2 组件 | V2 功能 | 当前状态 | 缺失项 |
|---------|--------|---------|--------|
| 筛选条 | 搜索字段名 + 状态筛选 + 影响步骤筛选 | ❌ 完全缺失 | 整页缺失 |
| 健康概览 | 正常/关注/异常/缺失数量卡片 | ❌ 完全缺失 | |
| 字段注册表 | 原始字段→标准字段映射 + 类型 + 状态 + 空值率 + 异常率 + 影响步骤 | ❌ 完全缺失 | |
| 字段展开详情 | 基本信息/映射规则/健康度趋势/影响步骤/变更历史 | ❌ 完全缺失 | |

#### P4 样本研究

| V2 组件 | V2 功能 | 当前状态 | 缺失项 |
|---------|--------|---------|--------|
| 问题类型标签筛选 | 全部/GPS漂移/碰撞BS/移动Cell/映射异常/字段变化 | ❌ 完全缺失 | 整页缺失 |
| 来源步骤筛选 | 选择来源步骤和 Run | ❌ 完全缺失 | |
| 样本集列表 | 样本集展开式明细列表 | ❌ 完全缺失 | |
| 样本重跑按钮 | "用此样本集做样本重跑"/"导出样本" | ❌ 完全缺失 | |

#### 抽屉（D1/D2/D3）

| V2 组件 | V2 功能 | 当前状态 | 缺失项 |
|---------|--------|---------|--------|
| D1 版本与运行 | 当前版本体系 + 最近运行列表 + 参数集/规则集变更 | ❌ 完全缺失 | 整组缺失 |
| D2 SQL 查看 | SQL 代码展示（语法高亮）+ 参数替换 + 版本差异 | ❌ 完全缺失 | |
| D3 样本/对象详情 | 对象基本信息 + 原始值 + 处理后值 + 命中规则 + 对比 Run | ❌ 完全缺失 | |

### 完成度总结

| 组件 | V2 设计要素 | 当前实现 | 完成率 |
|------|-----------|---------|--------|
| P1 治理链路总览 | 6 区块 | 3 部分实现 | ~25% |
| P2 步骤工作台 | 8+1 区块 | 2 部分实现 | ~15% |
| P3 字段治理 | 4 区块 | 0 | 0% |
| P4 样本研究 | 4 区块 | 0 | 0% |
| D1 版本抽屉 | 4 区块 | 0 | 0% |
| D2 SQL 抽屉 | 3 区块 | 0 | 0% |
| D3 详情抽屉 | 5 区块 | 0 | 0% |
| **总体** | **~34 区块** | **~5 部分** | **~10%** |

### 补齐建议

1. **P0 — P2 步骤工作台补齐**（最核心页面）
   - 添加 C 规则区 → 需新增 API `/steps/{id}/rules`（查 `wb_rule_hit`）
   - 添加 F 数据变化 → 需新增 API `/steps/{id}/metrics`（查 `wb_step_metric`）
   - 添加 G 差异区 → 需新增 API `/steps/{id}/diff?compare_run_id=`
   - 添加 H 样本区 → 需新增 API `/steps/{id}/samples`

2. **P1 — P1 总览补齐**
   - 添加 Run 摘要对比卡片
   - 添加步骤差异摘要表
   - 添加重点关注区

3. **P2 — P3 字段治理页新增**
   - 需新增 API 查 `meta.*` 5张表
   - 实现字段注册表 + 展开式详情

4. **P3 — P4 样本研究页新增**
   - 需新增 API 查 `wb_sample_set`
   - 实现样本集列表 + 详情

5. **P4 — 抽屉组件**
   - D1 版本抽屉：查 wb_run + wb_parameter_set + wb_rule_set
   - D2 SQL 抽屉：查 wb_sql_bundle 或文件系统
   - D3 详情抽屉：查 pipeline 表的单对象

---

## 维度 C：可理解性

**评定：** 🟠 部分通过

### C.1 前端英文文本清单

| 位置 | 英文文本 | 建议中文 |
|------|---------|---------|
| index.html:6 | `<title>WangYou Data Governance Workbench</title>` | 望优数据治理工作台 |
| index.html:16 | `Run: —` | 保留（已是业界通用术语） |
| app.js:198 | `${step.step_name_en}` | 已有中文 step_name 为主显示✅ |
| app.js:200 | `SQL: ${step.sql_file}` | 无需翻译（SQL文件名） |
| app.js:200 | `主链路` / `附加步骤` | 已为中文✅ |
| launcher_web.py:329 | `Service Launcher & Control Panel` | 服务启动器与控制面板 |
| launcher_web.py:346 | `Start` / `Stop` / `Restart` / `Kill Port` | 启动 / 停止 / 重启 / 释放端口 |
| launcher_web.py:364 | `P1 治理链路总览` | 已为中文✅ |
| launcher_web.py:369 | `API 文档 (Swagger)` | 已为中文✅ |
| launcher_web.py:397 | `Service Logs` | 服务日志 |

**结论**：前端主工作台已基本中文化（标题/导航/数据标签），但 Launcher 面板和页面 `<title>` 仍为英文。

### C.2 数据库 COMMENT ON TABLE 检查

经代码审查，**未发现任何 COMMENT ON TABLE 或 COMMENT ON COLUMN 语句**用于 pipeline schema 的 18 张新表。文档 `02_新旧表体系映射.md` 有完整的中英文映射字典（~130 条），但未转化为数据库注释。

**缺失项**：
- pipeline 的 18 张表无 TABLE COMMENT
- pipeline 表的 ~500+ 列无 COLUMN COMMENT
- workbench 的 17 张表仅 `wb_parameter_set.parameters` 有 COMMENT
- meta 的 5 张表无 COMMENT

### C.3 step_name 中文使用情况

`wb_step_registry` 表结构设计有 `step_name`（中文）和 `step_name_en`（英文）双语字段✅。

API 层（`steps.py`）的 `StepOut` 模型包含 `step_name` 和 `step_name_en` ✅。

前端侧栏导航使用 `step_name`（中文名）显示✅。步骤详情页同时显示中英文✅。

**但** `metrics.py` 中的 `step-summary` API 直接硬编码了中文步骤名（如 `"数据标准化"`, `"可信LAC"`），而不是从 `wb_step_registry` 动态获取。

### C.4 中文化方案

| 措施 | 涉及文件 | 优先级 | 工作量 |
|------|---------|--------|--------|
| 为 pipeline 18张表添加 COMMENT ON TABLE | 新增 SQL 脚本 | P1 | 2h |
| 为 pipeline 核心列添加 COMMENT ON COLUMN | 新增 SQL 脚本（参照 Doc02 映射字典） | P1 | 4h |
| 页面 `<title>` 改中文 | index.html:6 | P2 | 5min |
| Launcher 按钮文本中文化 | launcher_web.py 346-356行, 397行 | P2 | 15min |
| 步骤名改为从 step_registry 动态获取 | metrics.py `get_step_summary()` | P2 | 30min |

---

## 维度 D：代码质量与架构

**评定：** 🟠 部分通过

### D.1 SQL 注入风险

| 文件 | 风险模式 | 风险等级 | 说明 |
|------|---------|---------|------|
| pipeline.py | f-string 拼接 WHERE 但参数用 `:param` 绑定 | 🟢 安全 | 所有用户输入通过 SQLAlchemy `text()` 绑定参数 |
| runs.py | 同上 | 🟢 安全 | |
| steps.py:63 | `text(f"...WHERE relname = :tbl")` | 🟢 安全 | 表名来自 `wb_step_registry`（受控数据） |
| metrics.py | 纯硬编码 SQL | 🟢 安全 | 无用户输入 |
| runs.py:73 | `status` 参数通过白名单校验 | 🟢 安全 | `valid = {"running", "completed", "failed", "cancelled"}` |

**结论**：无 SQL 注入风险。所有动态部分使用参数绑定。✅

### D.2 错误处理

| 问题 | 位置 | 说明 |
|------|------|------|
| 全局无异常处理中间件 | main.py | 未定义 `@app.exception_handler`，数据库错误会以 500 + FastAPI 默认 JSON 响应返回 |
| pipeline.py 无 try/except | 全文件 | 12 个 API 端点均无异常捕获，大表查询超时会直接 500 |
| metrics.py 无 try/except | 全文件 | 同上 |
| runs.py `create_run` 缺输入校验 | runs.py:14 | `body.model_dump()` 直接传入 SQL，未校验 `run_mode` 有效值 |
| 前端错误处理 | app.js:242-248 | 仅在 `init()` 有全局 catch，`loadOverview`/`loadStep` 等无单独错误处理 |

**建议**：
1. `main.py` 添加全局异常处理器
2. 为查大表的 API 添加查询超时参数（`statement_timeout`）
3. 前端各 `load*` 函数添加 try/catch 和错误展示

### D.3 连接池配置

```python
# database.py:6-9
_pool_kwargs = (
    {"poolclass": NullPool}
    if os.environ.get("TESTING")
    else {"pool_size": 5, "max_overflow": 10, "pool_pre_ping": True, "pool_recycle": 300}
)
```

| 配置项 | 当前值 | 评价 |
|--------|--------|------|
| pool_size | 5 | ⚠️ 偏小。`step-summary` 连续8个查询串行执行，加上前端 3 个并行 API，5+10=15 连接可能不够 |
| max_overflow | 10 | 合理 |
| pool_pre_ping | True | ✅ 防断连 |
| pool_recycle | 300秒 | ✅ 合理 |
| 查询超时 | 未设置 | ⚠️ 缺失。大表 COUNT 可能超时无法中断 |

**建议**：
1. `pool_size` 提升到 10
2. 添加 `connect_args={"options": "-c statement_timeout=30000"}`（30秒查询超时）

### D.4 后端 API 覆盖率

#### workbench schema 覆盖

| 表名 | 有API | 说明 |
|------|-------|------|
| wb_run | ✅ CRUD | runs.py |
| wb_step_registry | ✅ 读 | steps.py |
| wb_parameter_set | ⚠️ 间接读 | 仅通过 steps/{id}/parameters 读取 |
| wb_step_execution | ❌ | 无 API |
| wb_step_metric | ❌ | 无 API（metrics.py 是实时计算而非读表） |
| wb_layer_snapshot | ❌ | 无 API |
| wb_gate_result | ❌ | 无 API |
| wb_anomaly_stats | ❌ | 无 API（metrics.py 实时计算） |
| wb_rule_set | ❌ | 无 API |
| wb_sql_bundle | ❌ | 无 API |
| wb_contract | ❌ | 无 API |
| wb_baseline | ❌ | 无 API |
| wb_reconciliation | ❌ | 无 API |
| wb_rule_hit | ❌ | 无 API |
| wb_issue_log | ❌ | 无 API |
| wb_patch_log | ❌ | 无 API |
| wb_sample_set | ❌ | 无 API |

#### meta schema 覆盖

| 表名 | 有API | 说明 |
|------|-------|------|
| meta_field_registry | ❌ | P3 字段治理页需要 |
| meta_field_health | ❌ | |
| meta_field_mapping_rule | ❌ | |
| meta_field_change_log | ❌ | |
| meta_exposure_matrix | ❌ | |

**覆盖率**：workbench 17张表中仅 3 张有 API（**18%**），meta 5张表 **0% 覆盖**。

### D.5 前端架构

| 问题 | 说明 |
|------|------|
| 单文件架构 | 全部逻辑在 app.js（249行），无组件化 |
| HTML 字符串模板 | 使用模板字符串拼接 HTML（`setMain(...)`)，无虚拟 DOM 或模板引擎 |
| 无状态管理 | 无全局状态，每次切换页面重新请求 |
| 无路由管理 | 使用 `onclick` 直接调用函数，浏览器前进/后退无效 |
| CSS 规模 | style.css 仅 93 行，覆盖基本布局 |
| 无错误边界 | 单个 API 失败可能导致整页空白 |

**正面评价**：
- 代码简洁可读，函数命名清晰
- 辅助函数 `fmt()`/`pct()`/`sizePretty()` 实用
- Launcher 面板设计完善（状态检测/服务管理/日志查看/自动恢复端口）

---

## 总体结论

**结论：** 需修改后可用

当前实现是一个可运行的 MVP 骨架，后端 API 设计合理、代码质量尚可，但距离 V2 设计目标差距巨大，且存在严重性能瓶颈。

### 必须修改项

| # | 优先级 | 问题 | 涉及文件 | 修改方案 | 工作量 |
|---|--------|------|---------|---------|--------|
| 1 | P0 | 性能极慢：`step-summary` 和 `layer-snapshot` 对大表全表扫描 | metrics.py | 创建 3 个物化视图，API 改查物化视图 | 3h |
| 2 | P0 | 无查询超时：大表查询可能无限等待 | database.py | 添加 `statement_timeout=30000` | 15min |
| 3 | P0 | P2 步骤工作台仅实现 8 区块中的 2 个 | app.js, 新增 API | 补齐 C规则/F数据变化/G差异/H样本 区块 | 16h |
| 4 | P1 | P1 总览缺 Run 对比/差异摘要/重点关注 | app.js | 添加对比视图和差异表 | 8h |
| 5 | P1 | 完全缺失 P3 字段治理页 | 新增 API + 前端页面 | 为 meta 表创建 API + 前端页面 | 12h |
| 6 | P1 | 完全缺失 P4 样本研究页 | 新增 API + 前端页面 | 为 wb_sample_set 创建 API + 前端页面 | 8h |
| 7 | P1 | 完全缺失 D1/D2/D3 抽屉 | 新增前端组件 | 实现 3 个抽屉组件 | 8h |
| 8 | P1 | pipeline 18张新表无数据库注释 | 新增 SQL 脚本 | 根据 Doc02 添加 COMMENT ON TABLE/COLUMN | 6h |
| 9 | P1 | workbench/meta 表的 API 覆盖率仅 18%/0% | 新增 API 路由 | 为关键表创建读取 API | 8h |
| 10 | P2 | 全局无异常处理中间件 | main.py | 添加 exception_handler | 1h |
| 11 | P2 | 前端无数据缓存 | app.js | 添加 sessionStorage/内存缓存 | 2h |
| 12 | P2 | 连接池偏小 | database.py | pool_size 5→10 | 5min |

### 建议改进项

| # | 类别 | 建议 | 涉及文件 |
|---|------|------|---------|
| 1 | 架构 | 前端考虑引入轻量组件框架（如 Preact/Alpine.js），当前单文件在补齐 P3/P4/D1-D3 后将膨胀到 1000+ 行 | app.js |
| 2 | 架构 | 添加 URL hash 路由，支持浏览器前进/后退和分享链接 | app.js |
| 3 | 代码 | `runs.py:14` `create_run` 对 `run_mode` 添加白名单校验 | runs.py |
| 4 | 代码 | `steps.py:43` HTTPException 导入移到文件顶部 | steps.py |
| 5 | 可维护性 | metrics.py 硬编码的步骤名改为从 wb_step_registry 动态获取 | metrics.py |
| 6 | 安全 | config.py 数据库密码 `123456` 明文硬编码，改为环境变量 | config.py |
| 7 | 前端 | 长表格添加虚拟滚动，profile_bs (16万行) 和 profile_cell (49万行) 分页加载性能 | app.js |
| 8 | Launcher | 按钮文本中文化 | launcher_web.py |
