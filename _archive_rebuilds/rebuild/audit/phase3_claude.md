# Claude 第三阶段规划审计报告

> 审计日期：2026-03-24
> 审计身份：Claude 规划审计 Agent（第三阶段）
> 审计范围：11 个实现文件 + 5 个 V2 设计原型 + 7 个设计文档 + 2 个历史参考
> 输出目标：可执行的第三阶段开发计划

---

## 1. 各维度分析与实施方案

### F. 字段治理完整性（最高优先级）

#### 当前状态

**第一层（缺失）— 原始字段业务定义与合规规则：**

- `meta_field_registry` 561 条记录全部来自 `information_schema` 自动同步，`description` 全空
- `meta_field_health` 0 条 — 没有任何字段健康快照
- `meta_field_mapping_rule` 0 条 — 没有任何转换/合规规则
- 合规参数散落在 `wb_parameter_set.parameters` JSON 中（如 `operator_whitelist`、`china_bbox`、`rsrp_invalid_values`），未与字段治理关联
- 前端 P3 只展示 pg_stats 近似值（null_frac、n_distinct），无业务含义、无合规规则、无合规率

**第二层（已有）— 过程字段注册：**

- `ensure_field_registry()` 从 information_schema 同步列定义，ON CONFLICT 更新
- `list_fields()` 关联 pg_stats 计算 null_rate 和 distinct_estimate
- `get_field_detail()` 查询 meta_field_health、meta_field_mapping_rule、meta_field_change_log，但这三张表全空
- 前端 P3 有筛选栏（搜索/表名/健康度）和字段表，有字段详情抽屉

#### 目标状态

用户在 P3 页面可以：
1. 看到每个网优原始字段的**业务含义**和**合规规则**（LAC 范围、RSRP 有效值域、GPS 边界等）
2. 看到当前数据各字段的**合规率**（多少行符合规则、多少行异常）
3. 字段合规规则与 `wb_parameter_set` 全局参数联动，调参后可重算合规率
4. 合规率可按 run 对比，发现数据质量变化趋势

#### 实施方案

**1. 数据模型设计：复用 meta_field_mapping_rule + 扩展 meta_field_health**

不建议新建表。理由：meta_field_mapping_rule 和 meta_field_health 已存在且设计合理，只需填充数据。

```
meta_field_mapping_rule（已有表，填充合规规则）:
  field_id         → 关联 meta_field_registry
  rule_code        → 如 'range_check', 'whitelist_check', 'bbox_check'
  rule_name        → 中文名
  source_expression → 合规判断 SQL 表达式，如 'lac_dec BETWEEN 0 AND 65535'
  target_expression → 参数引用键，如 'global.china_bbox'
  applies_to_steps  → 影响步骤列表
  is_active         → 是否启用

meta_field_health（已有表，填充合规率快照）:
  field_id      → 关联 meta_field_registry
  run_id        → 关联 wb_run（新增列，用于 run 级合规率对比）
  total_rows    → 总行数
  null_count    → 空值数
  null_rate     → 空值率
  compliant_count → 合规数（新增列）
  compliance_rate → 合规率（新增列）
  distinct_count  → 基数
  is_anomalous    → 是否异常
  anomaly_reason  → 异常原因
```

需要给 `meta_field_health` 新增两列：`compliant_count bigint` 和 `compliance_rate numeric`，以及 `run_id integer`。

**合规规则的数据结构**：直接使用 `source_expression` 存 SQL 片段，`target_expression` 存参数键名。规则与 `wb_parameter_set` 的关系通过参数键名动态解析，不做 FK 关联——因为参数是 JSON 结构，FK 反而增加复杂度。

**2. 合规率计算引擎**

**计算源表选择**：fact_filtered（2180 万行）。理由：
- raw_records 2.5 亿行，全量扫描单字段合规率约需 30-60s，不可接受作为常规操作
- fact_filtered 是合规过滤后的主事实表，代表"工作台实际工作范围内的数据"
- 用户关心的是"进入治理链路的数据的字段质量"，而非原始数据整体质量
- 2180 万行单字段 COUNT + FILTER 约 2-5s，可接受

**计算策略**：按 run 预计算 + 写入 meta_field_health。
- 在 `ensure_snapshot_bundle()` 流程中新增 `_compute_field_health()` 步骤
- 一次性对所有关键字段执行合规率计算（约 15 个字段 × 1 条 SQL = 15 条查询，总耗时约 30-60s）
- 结果写入 `meta_field_health`，带 `run_id`，支持 run 间对比
- 不建议抽样：2180 万行 COUNT FILTER 在 PG17 上足够快，抽样引入不确定性

**性能估算**：
- 15 个字段的合规率计算（fact_filtered，2180 万行）：~45s
- 写入 meta_field_health：~1s
- 总增量：快照刷新多花 ~46s，可接受（只在手动强制刷新时执行）

**3. 原始字段合规规则种子数据**

需要初始化以下核心字段的合规规则（基于 P-001 参数和业务文档）：

| 字段 | 规则 | 合规条件 |
|------|------|---------|
| operator_id_raw | 运营商白名单 | IN ('46000','46001','46011','46015','46020') |
| tech_norm | 制式白名单 | IN ('4G','5G') |
| lac_dec | LAC 范围 | 4G: [0,65535], 5G: [0,16777215], NOT IN overflow_values |
| cell_id_dec | Cell 范围 | 4G: [1,268435455], 5G: [1,68719476735] |
| lon/lat | GPS 边界 | lon [73,135], lat [3,54] |
| sig_rsrp | RSRP 有效 | [-140,-44] dBm, NOT IN (-110,-1) |
| sig_rsrq | RSRQ 有效 | [-20,-3] dB |
| sig_sinr | SINR 有效 | [-20,30] dB |
| sig_rssi | RSSI 有效 | [-110,-25] dBm |

**4. API 设计**

新增 3 个端点：

```
GET /api/v1/fields/compliance-rules
  → 返回所有字段合规规则列表（关联参数值）
  → 响应：{ rules: [{ field_name, rule_code, rule_name, source_expression, current_param_value, compliance_rate }] }

GET /api/v1/fields/{field_name}/compliance
  → 返回单字段合规详情（含 run 间趋势）
  → 响应：{ field, rule, history: [{ run_id, compliance_rate, total, compliant, anomaly_reason }] }

POST /api/v1/fields/compliance/refresh
  → 手动触发合规率重算（可指定 run_id）
  → 响应：{ run_id, fields_computed, duration_seconds }
```

**5. 前端 P3 改造**

当前 P3 = 健康概览 + 筛选栏 + 字段表 + 字段详情抽屉。

改造为两层结构：

**上半部分——原始字段合规概览（新增）：**
- 合规概览卡片：总字段数、合规率均值、异常字段数、关注字段数
- 合规规则表：字段名 | 规则 | 当前合规率 | 上次合规率 | 变化 | 参数关联
- 点击字段行展开合规详情（规则定义、趋势、关联参数、影响步骤）

**下半部分——过程字段注册表（已有，微调）：**
- 保持现有筛选栏和字段表
- 在字段详情抽屉中新增"合规规则"和"合规趋势"区块

---

### A. V2 设计还原度

#### 对比矩阵

| 页面/区块 | V2 设计 | 当前实现 | 缺失项 | 优先级 |
|-----------|---------|---------|--------|--------|
| **P1 Context Bar** | 7 个 tag + 版本抽屉 + 刷新时间 | ✅ 完整实现 | — | — |
| **P1 Pipeline Flow** | 9 节点链路图 + delta | ✅ 完整实现 | — | — |
| **P1 Run Summary** | 双栏 current/compare | ✅ 完整实现 | — | — |
| **P1 Step Diff** | 差异摘要表 | ✅ 完整实现 | — | — |
| **P1 Focus Areas** | 类型标签 + 描述 + 跳转链接 | ✅ 基本实现 | V2 有"新增问题""字段变化"等具体分类，当前只做了通用 buildFocusItems | P2 |
| **P1 操作区** | 全链路重跑 + 局部重跑选择 | ✅ 只有全链路重跑按钮 | 缺"选择步骤局部重跑"入口 | P2 |
| **P2 A. 步骤说明** | 业务目的 + 上下游 + 当前状态 + 库映射 | ✅ 已有说明 + 技术标识 | 缺上下游步骤链接、当前状态标签 | P2 |
| **P2 B. IO** | 双栏输入/输出 + vs Compare | ✅ 完整实现 | 缺 vs Compare 行数差异 | P3 |
| **P2 C. 规则** | 规则名 + 目的 + 参数 + 命中率 + 影响范围 | ✅ 完整实现 | — | — |
| **P2 D. 参数** | 当前值 + 上次值 + 变化标签 | ✅ 当前值已有 | 缺上次值和变化标签 | P2 |
| **P2 E. SQL** | SQL 列表 + 展开查看 | ✅ 完整实现 + D2 抽屉 | — | — |
| **P2 F. 数据变化** | 指标卡片 + 结构化指标表 | ✅ 完整实现 | — | — |
| **P2 G. 差异** | 当前 vs Compare 指标对比 | ✅ 完整实现 | — | — |
| **P2 H. 样本** | 样本集 + 预览 + 详情抽屉 + 样本重跑 | ✅ 完整实现 | — | — |
| **P3 健康概览** | 4 个状态卡片 | ✅ 完整实现 | — | — |
| **P3 筛选栏** | 搜索 + 状态 + 步骤 | ✅ 搜索 + 表名 + 健康度 | 缺按步骤筛选（V2 有"全部影响步骤"下拉） | P3 |
| **P3 字段表** | 原始字段 + 标准字段 + 类型 + 状态 + 空值率 + 异常率 + 步骤 | ⚠️ 只有标准字段 | **缺原始字段列、异常率列**（V2 有 raw→standard 双列） | P1 |
| **P3 展开区** | 基本信息 + 映射规则 + 健康趋势 + 影响步骤 + 变更历史 | ⚠️ 只通过抽屉展示基础信息 | **缺映射规则内容、健康趋势、变更历史**（表全空） | P1 |
| **P4 问题类型筛选** | tag 切换（GPS漂移/碰撞BS/移动Cell/映射异常/字段变化） | ❌ 无 | **完全缺失** | P1 |
| **P4 来源步骤筛选** | 下拉筛选 + Run 选择 | ❌ 无 | **完全缺失** | P1 |
| **P4 样本集列表** | 样本集 + 问题类型 + 来源步骤 + 数量 + Run + 状态 | ⚠️ 有样本卡片列表 | 缺问题类型标签、来源步骤链接、Run 标识 | P2 |
| **P4 展开子表** | 对象 ID + 标签 + 核心指标 + 结论 + 详情链接 | ⚠️ 有预览表 | 缺标签列、结论列 | P2 |
| **D1 版本抽屉** | 版本体系 + 运行列表 + 参数变更 + 规则变更 | ⚠️ 只有运行列表 | **缺参数变更历史、规则变更历史** | P2 |
| **D2 SQL 抽屉** | SQL 展开 | ✅ 完整实现 | — | — |
| **D3 样本详情抽屉** | 对象信息 + 原始值 + 处理后 + 命中规则 + Compare 对比 | ⚠️ 只展示样本记录表 | **缺原始值 vs 处理后对比、命中规则展示、Compare Run 对比** | P1 |

#### 还原度评分

| 页面 | 上轮评估 | 当前评估 | 说明 |
|------|---------|---------|------|
| P1 | 70% | **85%** | 主体完整，细节改进（Focus 分类、操作区） |
| P2 | 60% | **82%** | 8 区块框架完整，参数对比和 IO 差异需补 |
| P3 | 35% | **45%** | 有骨架但缺原始字段层和展开区数据填充 |
| P4 | 45% | **55%** | 有样本列表但缺问题类型筛选和详情深度 |
| D1 | 60% | **65%** | 有运行列表，缺版本变更 |
| D2 | 90% | **95%** | 基本完整 |
| D3 | 50% | **40%** | 只展示记录表，缺核心对比能力 |

#### 补齐优先级

**P1（必做）：**
1. P3 原始字段合规层（与维度 F 合并）
2. P4 问题类型筛选和来源步骤筛选
3. D3 样本详情：原始值 vs 处理后 + 命中规则

**P2（应做）：**
4. P2 D 参数区增加上次值和变化标签
5. P1 Focus Areas 增加具体问题分类
6. D1 版本抽屉增加参数/规则变更历史
7. P4 样本集列表增加问题类型标签

**P3（可选）：**
8. P2 B IO 增加 Compare Run 对比行
9. P3 筛选栏增加按步骤筛选

---

### B. 性能与缓存

#### 评估

**1. 三层缓存架构（合理）：**

```
大表数据 → 快照表（wb_layer_snapshot/wb_step_metric/wb_anomaly_stats/wb_rule_hit）
    → AsyncTTLCache 内存缓存（TTL 60s~1800s）
    → API 响应
```

这个架构在第二轮修复中已经建立，是正确的。

**2. 快照刷新策略（当前：手动触发 + 懒初始化）：**

- `ensure_snapshot_bundle()` 在 API 被调用时检查快照是否存在，不存在则计算
- `refresh_all()` 由前端 POST /cache/refresh 触发，强制重算
- `APP_CACHE.invalidate()` 清除所有内存缓存

**问题：** 首次访问某个 run 时会触发全量快照计算（涉及 2.5 亿行 raw_records 的 COUNT 查询），可能导致首屏超时。

**建议：**
- 在 `_compute_step_metrics()` 中，s0 的 raw_records COUNT 查询替换为 pg_stat_user_tables 的近似值（已有 `_fallback_pipeline_counts()`，但只用于 fallback，应提升为默认策略）
- 快照计算超时保护已有（`SET LOCAL statement_timeout = 0`），但这恰恰是风险——应该设一个合理上限（如 300s）

**3. 新增合规率计算对性能的影响：**

如前述，15 个字段 × fact_filtered 2180 万行 ≈ 45s 增量。可接受，因为只在手动刷新时触发。

**建议：** 合规率计算和快照计算共享同一个 `ensure_snapshot_bundle()` 入口，避免多次重复查询。

**4. 遗留的大表实时扫描：**

检查 `pipeline.py`：
- `/dim/lac-trusted`、`/dim/bs-trusted`、`/profile/lac`、`/profile/bs`、`/profile/cell`：直接 SELECT 维表/画像表，带分页。这些表行数在 881~502,199 之间，有分页限制（默认 50），**无问题**。
- `/pipeline/overview`：读 pg_stat_user_tables，有 300s 缓存，**无问题**。
- `/stats/operator-tech`、`/gps-status`、`/signal-fill`：通过快照表读取，**无问题**。

**结论：** 大表实时扫描问题已在第二轮修复中解决。第三阶段需关注合规率计算的增量开销。

---

### C. 代码架构

#### 1. 后端 workbench.py（2,045 行）拆分方案

**当前职责分析：**

| 行范围 | 职责 | 建议模块 |
|--------|------|---------|
| 1-76 | 常量定义（DEFAULT_RULE_SET、DEFAULT_SAMPLE_SETS、SAMPLE_TABLE_CONFIG） | `services/constants.py` |
| 77-250 | 工具函数（_scalar/_first/_all/_json/_number 等） | `services/db_helpers.py` |
| 256-398 | 版本初始化（ensure_reference_data） | `services/bootstrap.py` |
| 400-466 | 字段注册（ensure_field_registry） | `services/field_service.py` |
| 469-656 | 版本上下文（latest_run_id、build_run_summary、get_version_context、get_version_history） | `services/version_service.py` |
| 659-987 | 快照计算（_compute_layer_snapshot、_compute_step_metrics、_compute_anomaly_stats） | `services/snapshot_service.py` |
| 990-1276 | 规则命中计算（_compute_rule_hits） | `services/snapshot_service.py` |
| 1279-1499 | 快照读取（ensure_snapshot_bundle、list_layer_snapshot、list_step_summary、list_anomaly_summary） | `services/snapshot_service.py` |
| 1503-1551 | 分布查询（list_operator_tech_distribution 等） | `services/snapshot_service.py` |
| 1554-1932 | 步骤详情（get_step_metrics、get_step_rules、get_step_sql、get_step_diff、list_fields、get_field_detail） | `services/step_service.py` + `services/field_service.py` |
| 1935-2045 | 样本（_build_sample_sql、list_sample_sets、get_sample_set_detail、get_step_samples、refresh_all） | `services/sample_service.py` |

**建议拆分为 7 个模块：**

```
services/
├── constants.py          (~120 行) 常量、默认配置
├── db_helpers.py          (~60 行)  _scalar/_first/_all 等通用查询工具
├── bootstrap.py           (~160 行) ensure_reference_data, ensure_field_registry
├── version_service.py     (~200 行) 版本上下文和历史
├── snapshot_service.py    (~600 行) 快照计算和读取（最大模块）
├── step_service.py        (~350 行) 步骤详情、规则、SQL、差异
├── field_service.py       (~250 行) 字段列表、详情、合规率（第三阶段新增）
├── sample_service.py      (~200 行) 样本集和样本查询
├── labels.py              (不变)    中文标签
└── cache.py               (不变)    TTL 缓存
```

**共享依赖处理：**
- `db_helpers.py` 提供 `_scalar`、`_first`、`_all`、`_json`、`_number` 等基础函数，其他模块直接导入
- `APP_CACHE` 从 `cache.py` 导入
- `get_db` 从 `core/database.py` 导入
- `labels.py` 从各模块直接导入需要的翻译函数

**模块依赖方向图：**

```
constants.py ← db_helpers.py ← bootstrap.py
                                    ↑
cache.py ← snapshot_service.py ← version_service.py
               ↑                       ↑
           step_service.py        field_service.py
               ↑
           sample_service.py

labels.py ← (所有 service 模块)
```

**关键原则：** 所有模块单向依赖，不允许循环导入。`snapshot_service.py` 不导入 `step_service.py`；`step_service.py` 可导入 `snapshot_service.py`。

#### 2. 前端 app.js（1,184 行）拆分方案

**当前职责分析：**

| 行范围 | 职责 | 建议模块 |
|--------|------|---------|
| 1-55 | 常量 + 状态 | `state.js` |
| 56-225 | 工具函数（escapeHtml, fmt, pct, api, cache） | `utils.js` |
| 226-308 | 通用 UI（renderMetricTable, openDrawer, closeDrawer） | `ui.js` |
| 309-607 | P1 总览（refreshContext, loadOverview） | `pages/overview.js` |
| 608-877 | P2 步骤工作台（loadStep） | `pages/step.js` |
| 878-984 | P3 字段治理（loadFields, renderFieldsTable） | `pages/fields.js` |
| 985-1040 | P4 样本研究（loadSamples） | `pages/samples.js` |
| 1042-1148 | 抽屉（openVersionDrawer, openSqlDrawer, openSampleDrawer, openFieldDrawer） | `drawers.js` |
| 1150-1185 | 路由 + 初始化 | `app.js`（入口） |

**模块化方案（原生 ES Modules，不引入框架）：**

```html
<!-- index.html -->
<script type="module" src="app.js"></script>
```

```
frontend/
├── app.js           (~50 行)  入口：import 各模块，init(), 路由绑定
├── state.js         (~30 行)  export state 对象和常量
├── utils.js         (~120 行) export escapeHtml, fmt, pct, api, cache 等
├── ui.js            (~80 行)  export renderMetricTable, openDrawer, closeDrawer, showToast
├── drawers.js       (~120 行) export openVersionDrawer, openSqlDrawer, openSampleDrawer, openFieldDrawer
├── pages/
│   ├── overview.js  (~300 行) export loadOverview
│   ├── step.js      (~280 行) export loadStep
│   ├── fields.js    (~150 行) export loadFields, applyFieldFilters
│   └── samples.js   (~100 行) export loadSamples
├── index.html
└── style.css
```

**共享状态管理：**
- `state.js` 导出一个全局 state 对象，所有模块导入同一实例
- 不需要 Proxy 或事件系统——当前是手动渲染模式，状态变化后直接 setMain()

**事件绑定：**
- onclick 属性中的全局函数调用（如 `onclick="createRun(...)"`) 改为 `app.js` 入口将函数挂到 `window` 上
- 或者改用 `data-action` 属性 + 全局事件委托

**路由：** 现有 hash 路由已工作正常，保持不变。

---

### D. 中文化完善

#### 1. 字段 description 批量填充策略

当前 `meta_field_registry.description` 全空。有两个数据来源可用：

**方案：两步填充**

**第一步（自动）：** 从 `labels.py` 的 `FIELD_LABELS` 字典（当前 ~65 个字段映射）反向写入 description。在 `ensure_field_registry()` 中，将 `field_label(column_name)` 的结果作为 description 写入（仅当 description 为空时）。

**第二步（手动 + SQL 脚本）：** 对未覆盖的字段（如 seq_id、cell_ts_raw、sdk_ver 等技术字段），准备一个 SQL 脚本批量 UPDATE：

```sql
UPDATE meta.meta_field_registry SET description = '原始序列号' WHERE field_name = 'seq_id' AND description = '';
UPDATE meta.meta_field_registry SET description = '原始时间戳文本' WHERE field_name = 'cell_ts_raw' AND description = '';
-- ... 约 500 条
```

建议将这个 SQL 脚本放入 `rebuild/scripts/seed_field_descriptions.sql`。

#### 2. 原始字段业务含义的维护位置

维护在 `meta_field_mapping_rule` 中。每个原始字段的合规规则（值域、白名单等）本身就是业务含义的结构化表达。

同时在 `meta_field_registry.description` 中存放一句话的中文业务说明（如"参考信号接收功率，正常范围 [-140,-44] dBm"）。

#### 3. 用户操作路径上的英文障碍清单

| 位置 | 英文内容 | 建议中文 |
|------|---------|---------|
| 侧栏步骤名 | 已中文化 | — |
| Context Bar tag | "Run:", "Compare:" | 已足够直观，不改 |
| P2 区块标题 | "A. 步骤说明" 等 | 已中文化 |
| 字段表列头 | data_type, null_rate | 改为"数据类型""空值率" |
| 样本表列头 | 使用 field_name 作为列头 | 替换为 field_label 对应中文 |
| 抽屉标题 | "D1", "D2 SQL 查看", "D3 样本详情" | 保留编号但前置中文："D1 版本与运行""D2 SQL 查看""D3 样本详情" |
| 字段详情抽屉 | "基础信息""健康度" | 已中文化 |
| 错误消息 | "Step {step_id} not found" | 改为"步骤 {step_id} 未找到" |

---

### E. 业务逻辑正确性

#### 1. 版本体系闭环

| 版本组件 | DDL 定义 | 实现状态 | 说明 |
|---------|---------|---------|------|
| wb_run | ✅ | ✅ 有 5 条记录 | 可创建/查询 |
| wb_parameter_set | ✅ | ✅ 1 条 P-001 | 全局参数已填充 |
| wb_rule_set | ✅ | ✅ 自动创建 R-001 | ensure_reference_data 初始化 |
| wb_sql_bundle | ✅ | ✅ 自动创建 S-001 | 扫描 lac_enbid_project |
| wb_contract | ✅ | ✅ 自动创建 C-001 | 基础契约 |
| wb_baseline | ✅ | ❌ 0 条 | **基线功能未实现** |

**缺口：** wb_baseline 表存在但无数据、无创建/使用逻辑。基线是"伪日更"的前提，但伪日更不在当前阶段范围内。**不建议第三阶段实现基线功能。**

版本体系闭环在当前范围内是完整的：run 创建时自动关联 parameter_set/rule_set/sql_bundle/contract。

#### 2. 指标覆盖度 vs Doc04 定义

Doc04 定义了约 60+ 个指标代码（s0~s52）。当前 `_compute_step_metrics()` 实际计算了以下指标：

| 步骤 | Doc04 指标数 | 实际实现 | 覆盖率 |
|------|------------|---------|--------|
| s0 | 6 | 3 (total, lac_rows, gps_rows) | 50% |
| s1 | 8 | 0 | 0% |
| s2 | 8 | 0 | 0% |
| s3 | 3 | 0 | 0% |
| s4 | 4 | 4 | 100% |
| s5 | 4 | 0 | 0% |
| s6 | 5 | 4 | 80% |
| s30 | 9 | 5 | 56% |
| s31 | 8 | 6 + 分布 | 75% |
| s32 | 5 | 0 | 0% |
| s33 | 7 | 6 + 分布 | 86% |
| s34 | 3 | 0 | 0% |
| s35 | 3 | 1 (通过 s52 profile_cell) | 33% |
| s36 | 3 | 0 | 0% |
| s37 | 4 | 0 | 0% |
| s40 | 6 | 0 | 0% |
| s41 | 5+ | 5 + 分布 | 100% |
| s50 | 1 | 1 | 100% |
| s51 | 2 | 2 | 100% |
| s52 | 2 | 2 | 100% |

**总覆盖率约 40%。** 缺失集中在辅助步骤（s1/s2/s3/s5）和对比报表步骤（s32/s34/s36/s37）。

**建议：** 只补主链路步骤的核心指标（s0 的 has_gps_pct、s5 的 total_cell_cnt），辅助步骤指标在有实际调试需求时再补。

#### 3. 质量门检查（10 个 Gate）

`wb_gate_result` 表已创建，`get_step_metrics()` 中有查询逻辑，但 **0 条数据**——没有任何 gate 被计算和写入。

Gate 需要在 `ensure_snapshot_bundle()` 中新增 `_compute_gate_results()` 函数。Doc04 未明确定义 10 个 Gate 的具体规则，需要根据业务文档推导。

**建议的 10 个 Gate：**

| Gate | 步骤 | 规则 | 严重级别 |
|------|------|------|---------|
| G01 | s0 | raw_records 行数 > 0 | CRITICAL |
| G02 | s4 | trusted_lac_cnt >= 10 | CRITICAL |
| G03 | s6 | fact_filtered 行数 > raw_records × 0.5 | WARNING |
| G04 | s30 | collision_suspect_rate < 20% | WARNING |
| G05 | s31 | gps_fill_rate > 50% | WARNING |
| G06 | s33 | signal_fill_rate > 30% | WARNING |
| G07 | s41 | fact_final 行数 > fact_filtered × 0.95 | CRITICAL |
| G08 | s41 | severe_collision_rate < 5% | WARNING |
| G09 | s50-52 | 三个画像表行数 > 0 | CRITICAL |
| G10 | 全局 | meta_field_registry.description 非空率 > 80% | INFO |

**优先级：P2（应做但非阻塞项）。**

---

## 2. 第三阶段开发计划

### 任务分解与排序

| 序号 | 任务 | 依赖 | 涉及层 | 工作量 | 优先级 |
|------|------|------|--------|--------|--------|
| T01 | **后端拆分：workbench.py → 7 个模块** | 无 | 后端 | 中 | P0 |
| T02 | **前端拆分：app.js → ES Modules** | 无 | 前端 | 中 | P0 |
| T03 | **DDL 变更：meta_field_health 新增 compliant_count/compliance_rate/run_id 列** | 无 | 数据库 | 小 | P0 |
| T04 | **合规规则种子数据：初始化 meta_field_mapping_rule（~15 条核心字段规则）** | T03 | 数据库+后端 | 小 | P0 |
| T05 | **合规率计算引擎：在 snapshot_service 中新增 _compute_field_health()** | T01, T03, T04 | 后端 | 中 | P0 |
| T06 | **合规率 API：新增 3 个字段合规端点** | T05 | 后端 | 小 | P0 |
| T07 | **P3 前端改造：新增原始字段合规概览区** | T02, T06 | 前端 | 中 | P0 |
| T08 | **字段 description 批量填充脚本** | T01 | 数据库 | 小 | P1 |
| T09 | **P4 问题类型筛选 + 来源步骤筛选** | T02 | 前端+后端 | 中 | P1 |
| T10 | **D3 样本详情抽屉：原始值 vs 处理后 + 命中规则** | T02 | 前端+后端 | 中 | P1 |
| T11 | **P2 D 参数区：增加 Compare Run 参数对比** | T02 | 前端+后端 | 小 | P1 |
| T12 | **D1 版本抽屉：增加参数/规则变更历史** | T02 | 前端+后端 | 小 | P1 |
| T13 | **Gate 计算引擎：_compute_gate_results() + 10 个 Gate** | T01 | 后端 | 中 | P2 |
| T14 | **中文化收尾：样本表列头中文化 + 错误消息中文化** | T02 | 前端+后端 | 小 | P2 |
| T15 | **辅助步骤指标补齐（s1/s2/s3/s5 核心指标）** | T01 | 后端 | 中 | P2 |
| T16 | **P1 Focus Areas 智能分类（字段变化/新增问题/参数变化）** | T07, T13 | 前端 | 小 | P3 |

### 里程碑

| 里程碑 | 任务集 | 验收标准 |
|--------|--------|---------|
| **M1：代码架构就绪** | T01, T02 | workbench.py 拆成 7 个模块，app.js 拆成 ES Modules，所有现有功能不回归 |
| **M2：字段治理完整** | T03, T04, T05, T06, T07, T08 | P3 页面展示原始字段合规规则和合规率，meta_field_health 有数据，字段 description 覆盖率 > 80% |
| **M3：V2 还原度 ≥ 75%** | T09, T10, T11, T12 | P4 有问题筛选，D3 有对比详情，P2 参数有变化标签，D1 有变更历史 |
| **M4：业务逻辑健全** | T13, T14, T15, T16 | Gate 有数据，P1 Focus 有智能分类，指标覆盖率 > 60% |

### 架构决策点

**决策 1：合规率计算源表**

- **推荐方案：** fact_filtered（2180 万行）
- **理由：** 代表治理链路工作范围内的数据，性能可控（~45s），不需要抽样
- **备选方案：** raw_records（2.5 亿行），需要抽样或物化视图，复杂度高
- **需用户确认：** 是否认同"字段合规率基于 fact_filtered 而非 raw_records"

**决策 2：合规规则的参数联动方式**

- **推荐方案：** meta_field_mapping_rule.target_expression 存参数键名（如 'global.operator_whitelist'），运行时动态解析 wb_parameter_set.parameters
- **理由：** 调参后重算合规率可以自动使用新参数值
- **备选方案：** 规则中硬编码阈值，需要在调参后手动同步更新
- **需用户确认：** 无，推荐方案明显更优

**决策 3：前端模块化方案**

- **推荐方案：** 原生 ES Modules（`<script type="module">`）
- **理由：** 不引入构建工具，保持项目简单性，现代浏览器全支持
- **备选方案：** 引入 Vite 等构建工具，提供更好的 HMR 开发体验
- **需用户确认：** 是否接受纯 ES Modules 方案（不需要 npm/node）

**决策 4：meta_field_health 是否需要 run_id**

- **推荐方案：** 新增 run_id 列
- **理由：** 支持不同 run 之间的字段合规率对比，这是"调参→重跑→看差异"闭环的一部分
- **备选方案：** 不加 run_id，每次覆盖写入最新数据
- **需用户确认：** 无，推荐方案明显更优

---

## 3. 风险与注意事项

### 技术风险

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| 后端拆分引入循环导入 | 启动失败 | 严格遵循单向依赖图，db_helpers 不导入任何 service |
| 前端 ES Modules 不兼容旧浏览器 | 页面空白 | 目标用户为内部调试，确认使用 Chrome/Edge 即可 |
| 合规率计算超时 | 快照刷新失败 | 设置 statement_timeout = 300s，计算失败不影响已有快照 |
| 前端拆分后 onclick 全局函数失效 | 按钮不响应 | 入口 app.js 统一将函数挂到 window |

### 依赖风险

| 依赖 | 风险 | 缓解方案 |
|------|------|---------|
| fact_filtered 表行数可能变化（重跑后） | 合规率计算基数不一致 | 合规率快照绑定 run_id，每次基于当时的数据计算 |
| wb_parameter_set 只有 P-001 一个版本 | 参数对比无意义 | D1 抽屉在只有一个版本时显示"暂无历史版本" |

### 回退方案

- 后端拆分：每个模块拆完后立即运行现有 19 个 API 测试，任何失败立即回退该模块
- 前端拆分：保留 app.js 原文件为 app.js.bak，新模块逐步替换，验证后删除备份
- 合规率计算：作为 ensure_snapshot_bundle 的可选步骤，默认开启，出错时跳过不影响其他快照

### 不建议做的事项

1. **不建议实现 wb_baseline 和伪日更功能。** 理由：当前只有 5 个 run 记录，基线驱动的日常运营在数据量不足时没有实际验证价值。等 run 积累到 20+ 再考虑。
2. **不建议在 raw_records 上计算合规率。** 理由：2.5 亿行全量扫描单次 30-60s × 15 字段 = 7-15 分钟，超出调试工具可接受的等待时间。
3. **不建议引入前端框架（React/Vue）。** 理由：当前 1,184 行 JS 拆分后每个模块 100-300 行，原生 ES Modules 完全够用。引入框架需要构建工具链，增加项目复杂度，与"调试工具"定位不符。
4. **不建议补齐所有 Doc04 指标。** 理由：s1/s2/s3 等辅助步骤的指标在当前调试流程中很少被查看。只补主链路核心指标即可，后续按需扩展。
