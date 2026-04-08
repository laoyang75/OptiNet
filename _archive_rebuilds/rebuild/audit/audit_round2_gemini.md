# Gemini 第二轮审计报告

> 审计日期：2026-03-24
> 审计文件数：24
> 已读取文件确认：
> 1. ✅ `rebuild/backend/app/main.py`
> 2. ✅ `rebuild/backend/app/core/config.py`
> 3. ✅ `rebuild/backend/app/core/database.py`
> 4. ✅ `rebuild/backend/app/api/pipeline.py`
> 5. ✅ `rebuild/backend/app/api/runs.py`
> 6. ✅ `rebuild/backend/app/api/steps.py`
> 7. ✅ `rebuild/backend/app/api/metrics.py`
> 8. ✅ `rebuild/backend/app/models/schemas.py`
> 9. ✅ `rebuild/frontend/index.html`
> 10. ✅ `rebuild/frontend/style.css`
> 11. ✅ `rebuild/frontend/app.js`
> 12. ✅ `rebuild/launcher_web.py`
> 13. ✅ `docs/data_warehouse/Pre_UI/V2/index.html`
> 14. ✅ `docs/data_warehouse/Pre_UI/V2/step-lac.html`
> 15. ✅ `docs/data_warehouse/Pre_UI/V2/step-bs.html`
> 16. ✅ `docs/data_warehouse/Pre_UI/V2/step-cell.html`
> 17. ✅ `docs/data_warehouse/Pre_UI/V2/step-gps.html`
> 18. ✅ `docs/data_warehouse/Pre_UI/V2/fields.html`
> 19. ✅ `docs/data_warehouse/Pre_UI/V2/samples.html`
> 20. ✅ `docs/data_warehouse/Pre_UI/V2/wb.css`
> 21. ✅ `rebuild/docs/00_重构上下文与范围.md`
> 22. ✅ `rebuild/docs/02_新旧表体系映射.md`
> 23. ✅ `rebuild/docs/04_指标注册表.md`
> 24. ✅ `rebuild/docs/05_工作台元数据DDL.md`

---

## 维度 A：性能与缓存

**评定：未通过**

### API 性能分析（逐个列出）

| # | API 端点 | SQL 查询摘要 | 涉及表 | 是否全表扫描 | 预估耗时(2.5亿行) |
|---|---------|-------------|--------|:----------:|:---------------:|
| 1 | `GET /pipeline/overview` | `SELECT ... FROM pg_stat_user_tables WHERE schemaname='pipeline'` | pg_stat_user_tables | 否 | <100ms ✅ |
| 2 | `GET /pipeline/dim/lac-trusted` | `count(*)` + 分页查询 | dim_lac_trusted (~881行) | 是,表极小 | <100ms ✅ |
| 3 | `GET /pipeline/dim/bs-trusted` | `count(*)` + 分页查询 | dim_bs_trusted (~14万行) | 是,表较小 | <500ms ✅ |
| 4 | `GET /pipeline/profile/lac` | `count(*)` + 分页查询 | profile_lac (~878行) | 是,表极小 | <100ms ✅ |
| 5 | `GET /pipeline/profile/bs` | `count(*)` + 分页查询 | profile_bs (~16万行) | 是,表较小 | <500ms ✅ |
| 6 | `GET /pipeline/profile/cell` | `count(*)` + 分页查询 | profile_cell (~49万行) | 是,表中等 | <1s ✅ |
| 7 | **`GET /pipeline/stats/operator-tech`** | `count(*) GROUP BY ... FILTER(...)` | **fact_final (3050万行)** | **是** | **≥30s ❌** |
| 8 | **`GET /pipeline/stats/gps-status`** | `count(*) GROUP BY ...` | **fact_gps_corrected (2178万行)** | **是** | **≥20s ❌** |
| 9 | **`GET /pipeline/stats/signal-fill`** | `count(*) GROUP BY ... + AVG()` | **fact_signal_filled (2178万行)** | **是** | **≥25s ❌** |
| 10 | **`GET /metrics/layer-snapshot`** | 12个 `count(*)` UNION ALL | **raw_records(2.5亿) + 全部大表** | **是** | **≥120s ❌❌** |
| 11 | **`GET /metrics/step-summary`** | 8个独立全表 `count(*) FILTER(...)` | **raw_records(2.5亿) + 全部事实表** | **是** | **≥180s ❌❌❌** |
| 12 | `GET /metrics/anomaly-summary` | 9个 `count(*) FILTER(...)` UNION ALL | profile_bs(16万) + profile_cell(49万) | 是,中等 | ~5s ⚠️ |
| 13 | `GET /steps` | `SELECT * FROM wb_step_registry` | wb_step_registry (22行) | 是,微表 | <50ms ✅ |
| 14 | `GET /steps/{id}` | `WHERE step_id = :id` | wb_step_registry | 否,主键 | <50ms ✅ |
| 15 | `GET /steps/{id}/io-summary` | 循环查询 `pg_stat_user_tables` | pg_stat_user_tables | 否 | <200ms ✅ |
| 16 | `GET /steps/{id}/parameters` | `WHERE is_active=true LIMIT 1` | wb_parameter_set (~10行) | 否 | <50ms ✅ |
| 17 | `GET /runs` | 分页查询 | wb_run (~百行) | 否 | <100ms ✅ |
| 18 | `POST /runs` | INSERT | wb_run | — | <100ms ✅ |
| 19 | `GET /runs/{id}` | 主键查询 | wb_run | 否 | <50ms ✅ |
| 20 | `PATCH /runs/{id}/status` | UPDATE | wb_run | — | <100ms ✅ |
| 21 | `GET /health` | 无 SQL | — | — | <10ms ✅ |

### 前端缓存分析

通过审阅 `app.js`（249行），发现以下严重问题：

1. **零缓存机制**：没有 `localStorage`、`sessionStorage` 或 JS 变量缓存。每次调用 `loadOverview()` 并发 3 个 fetch（`/pipeline/overview`、`/metrics/step-summary`、`/metrics/layer-snapshot`）；每次切换步骤调用 `loadStep()` 并发 3 个 fetch。
2. **无手动刷新按钮**：用户无法控制数据更新时机。`ctx-status` 显示"状态: 就绪"是硬编码文本。
3. **无加载状态管理**：无错误重试或降级机制。如果 `step-summary`（Top 1 最慢，预估 180s+）超时，页面将卡死。

### Top 5 最慢 API

| 排名 | API 端点 | 根因 | 预估耗时 |
|:----:|---------|------|:-------:|
| 1 | **`GET /metrics/step-summary`** | 对 raw_records(2.5亿)、fact_final(3050万) 等 8 张表分别执行全表 `count(*) FILTER(...)`，串行 8 次查询 | **≥180s** |
| 2 | **`GET /metrics/layer-snapshot`** | 12 个 `count(*)` UNION ALL，涉及 raw_records(2.5亿) 等大表 | **≥120s** |
| 3 | **`GET /pipeline/stats/operator-tech`** | 对 fact_final(3050万) 全表扫描 + GROUP BY + 4 个 FILTER | **≥30s** |
| 4 | **`GET /pipeline/stats/signal-fill`** | 对 fact_signal_filled(2178万) 全表扫描 + GROUP BY + AVG | **≥25s** |
| 5 | **`GET /pipeline/stats/gps-status`** | 对 fact_gps_corrected(2178万) 全表扫描 + GROUP BY | **≥20s** |

**致命问题**：`loadOverview()` 使用 `Promise.all` 同时请求排名 1+2 的 API，合计耗时 ≥300s（5分钟+），**P1 首页每次打开需等待 5 分钟以上**。

### 缓存方案

#### 后端方案（三层）

**第一层：改查预计算表（根本解决方案）**

`metrics.py` 当前直接查 pipeline 大表，但 Doc05 已设计了 `wb_layer_snapshot` 和 `wb_step_metric` 专门存储 run 级快照结果。应改为：

```python
# 修改前（metrics.py L12-53）—— 直接查 pipeline 大表
"SELECT 'L0_raw' AS layer_id, count(*) AS row_count FROM pipeline.raw_records"

# 修改后 —— 查预计算快照表
"SELECT layer_id, row_count, pass_flag FROM workbench.wb_layer_snapshot WHERE run_id = :run_id"
```

**第二层：后端内存缓存（针对实时探索类查询）**

```python
# app/core/cache.py — 建议新增
from cachetools import TTLCache
_cache = TTLCache(maxsize=100, ttl=3600)  # 1小时 TTL

# 在 pipeline.py 中使用
@router.get("/stats/operator-tech")
async def get_operator_tech_stats(db = Depends(get_db)):
    key = "operator_tech_stats"
    if key in _cache:
        return _cache[key]
    result = ...  # 原有查询
    _cache[key] = result
    return result
```

**第三层：物化视图（针对无法改查快照表的场景）**

```sql
CREATE MATERIALIZED VIEW mv_layer_snapshot AS
SELECT 'L0_raw' AS layer_id, count(*) FROM pipeline.raw_records
UNION ALL ...;

CREATE UNIQUE INDEX ON mv_layer_snapshot(layer_id);
-- 刷新：REFRESH MATERIALIZED VIEW CONCURRENTLY mv_layer_snapshot;
```

新增手动刷新端点：
```python
@router.post("/cache/invalidate")
async def invalidate_cache():
    _cache.clear()
    return {"status": "ok"}
```

#### 前端方案

```javascript
const _cache = {};
const CACHE_TTL = 3600 * 1000; // 1小时

async function cachedApi(path) {
    const now = Date.now();
    if (_cache[path] && (now - _cache[path].ts) < CACHE_TTL) {
        return _cache[path].data;
    }
    const data = await api(path);
    _cache[path] = { ts: now, data };
    return data;
}
```

手动刷新按钮（放在 context-bar 右侧）：
```html
<button id="btn-refresh" class="tag tag-blue" style="cursor:pointer"
        onclick="forceRefresh()">🔄 刷新数据</button>
```

---

## 维度 B：UI 完整性

**评定：未通过**

### V2 vs 当前实现对比矩阵

| V2 组件 | V2 区块名 | V2 功能描述（从 HTML 提取） | 当前实现状态 | 缺失程度 |
|---------|----------|--------------------------|:----------:|:-------:|
| P1 总览 | ctx-bar(上下文条) | Run/Compare/参数集/规则集/SQL/契约/基线 7 个标签+版本抽屉按钮+刷新倒计时 | ⚠️ 仅 Run/参数集/状态 3 个标签 | **重度缺失** |
| P1 总览 | pipeline-flow(链路节点图) | 9 步骤节点含数量+差异标记(+N)，可点击 | ✅ 已实现 8 步骤，有数量可点击 | 轻微偏差 |
| P1 总览 | Run摘要对比(cols-2) | 当前 Run 与对比 Run 并排 9 项详情 | ❌ | **完全缺失** |
| P1 总览 | 步骤差异摘要表 | 7 行差异表格含变化/变化率/跳转 | ❌ | **完全缺失** |
| P1 总览 | 重点关注区 | 问题标签+描述+跳转 | ❌ | **完全缺失** |
| P1 总览 | 操作区 | 全链路重跑/局部重跑按钮 | ❌ | **完全缺失** |
| P2 步骤 | A.步骤说明 | 名称/业务目的/上下游/状态/库映射 | ⚠️ 仅名称+layer+SQL文件 | **重度缺失** |
| P2 步骤 | B.输入/输出 | 库名/行数/主键/维度/vs对比Run | ⚠️ 仅表名+行数 | **中度缺失** |
| P2 步骤 | C.规则区 | 逐条规则（名称/目的/参数/命中/范围） | ❌ | **完全缺失** |
| P2 步骤 | D.参数区 | 参数名/当前值/上次值/变化高亮 | ⚠️ 仅 key:value 列表 | **中度缺失** |
| P2 步骤 | E.SQL区 | SQL列表+展开代码+参数替换+diff | ❌ | **完全缺失** |
| P2 步骤 | F.数据变化区 | 指标卡片+过滤环节明细表 | ❌ | **完全缺失** |
| P2 步骤 | G.差异区 | Run间指标对比+新增/消失对象 | ❌ | **完全缺失** |
| P2 步骤 | H.样本区 | 分类样本列表+跳转详情抽屉 | ❌ | **完全缺失** |
| P2 步骤 | 操作区 | 从此步骤重跑/仅重跑/样本重跑 | ❌ | **完全缺失** |
| P3 字段 | 整页 | 字段注册表+搜索+过滤+健康概览+展开详情（基本信息/映射规则/健康趋势/影响步骤/变更历史） | ❌ 无页面入口 | **完全缺失** |
| P4 样本 | 整页 | 问题类型筛选+样本集+明细+详情抽屉+样本重跑 | ❌ 无页面入口 | **完全缺失** |
| D1 抽屉 | 版本与运行 | 版本体系+运行列表+参数历史+规则历史 | ❌ | **完全缺失** |
| D2 抽屉 | SQL查看 | SQL代码+参数替换表+版本diff | ❌ | **完全缺失** |
| D3 抽屉 | 对象详情 | BS/Cell详情（原始值/处理后/命中规则/vs对比Run） | ❌ | **完全缺失** |
| 全局 | 侧栏-辅助入口 | P3字段治理+P4样本研究入口 | ⚠️ 有"异常统计"替代入口 | **重度缺失** |

### 补齐建议（优先级排序）

| 优先级 | 目标 | 前置条件 | 工作量 |
|:------:|------|---------|:------:|
| P0 | P2 增加 C.规则区 + F.数据变化区 | 填充 `wb_rule_hit` / `wb_step_metric` 表数据 | 5天 |
| P1 | P3 字段治理页面 | 对接 `meta` schema 5 张表 + 新增 API | 3天 |
| P1 | P4 样本研究页面 | 对接 `wb_sample_set` + 新增 API | 3天 |
| P1 | D1/D2/D3 三个抽屉 | 前端抽屉组件 + 版本/SQL/对象 API | 3天 |
| P2 | P1 Run摘要对比+差异摘要+重点关注 | 需要 `compare_run_id` 参数和差异计算逻辑 | 3天 |
| P2 | ctx-bar 完善 | 扩充为 7 个上下文标签 | 0.5天 |

---

## 维度 C：可理解性

**评定：未通过**

### 前端英文名清单（直接暴露给用户）

**表名/层级名（在页面上直接显示）：**

| 位置 | 英文名示例 | 出现方式 |
|------|----------|---------|
| 层级快照表格 | `L0_raw`, `L2_filtered`, `L2_lac_trusted` 等 12 个值 | `app.js` L72-146 渲染 |
| 表空间概况 | `raw_records`, `dim_lac_trusted` 等 pipeline.* 表名 | `app.js` loadOverview() 渲染 |
| 步骤元数据 | `s0`, `s4`, `s30` 等 step_id | 步骤详情页 |
| 步骤标题 | `Standardization`, `Trusted LAC Library` 等 step_name_en | 并列显示于中文名旁 |
| SQL 文件名 | `00_step0_std_views.sql` | 步骤详情 |
| 异常统计表格 | `collision_suspect`, `gps_unstable`, `dynamic_cell` 等 | `app.js` loadAnomaly() 渲染 |
| 参数键名 | `active_days_threshold`, `min_device_count` 等 | 来自 JSON 直接渲染 |

**已中文化的部分（✅）：** 侧栏导航步骤中文名、链路流程图中文标签、stat-grid 中文标签。

### Doc02 §2.1 映射字典利用建议

Doc02 提供了完整的 129 个中文→英文字段映射字典。建议在三个层面利用：

### 中文化方案

#### 层面 1：DB COMMENT

```sql
COMMENT ON TABLE pipeline.raw_records IS '原始记录合并表（Layer0_Lac + Layer0_Gps_base）';
COMMENT ON COLUMN pipeline.raw_records.record_id IS '记录ID';
COMMENT ON COLUMN pipeline.dim_bs_trusted.is_collision_suspect IS '疑似碰撞标记';
-- ... 根据 Doc02 §2.1 为全部列添加
```

#### 层面 2：API 响应

在 `pipeline.py` 和 `metrics.py` 中添加翻译字典：

```python
TABLE_NAME_CN = {
    "raw_records": "原始记录表",
    "dim_lac_trusted": "可信LAC维表",
    "dim_cell_stats": "Cell统计维表",
    "dim_bs_trusted": "可信BS维表",
    "fact_filtered": "合规过滤明细",
    "fact_gps_corrected": "GPS修正明细",
    "fact_signal_filled": "信号补齐明细",
    "fact_final": "最终明细表",
    "profile_lac": "LAC画像",
    "profile_bs": "BS画像",
    "profile_cell": "Cell画像",
    "map_cell_bs": "Cell-BS映射",
}

ANOMALY_TYPE_CN = {
    "collision_suspect": "碰撞疑似",
    "severe_collision": "严重碰撞",
    "gps_unstable": "GPS不稳定",
    "dynamic_cell": "动态Cell",
    "insufficient_sample": "样本不足",
    "bs_id_lt_256": "BS_ID异常(<256)",
    "multi_operator_shared": "多运营商共建",
}
```

#### 层面 3：前端翻译

```javascript
const LAYER_CN = {
    'L0_raw': 'L0 原始记录',
    'L2_filtered': 'L2 合规过滤',
    'L2_lac_trusted': 'L2 可信LAC',
    'L2_cell_stats': 'L2 Cell统计',
    'L3_bs_trusted': 'L3 可信BS',
    'L3_gps_corrected': 'L3 GPS修正',
    'L3_signal_filled': 'L3 信号补齐',
    'L4_final': 'L4 最终明细',
    'L5_lac_profile': 'L5 LAC画像',
    'L5_bs_profile': 'L5 BS画像',
    'L5_cell_profile': 'L5 Cell画像',
    'L5_cell_bs_map': 'L5 Cell-BS映射',
};

const ANOMALY_CN = {
    'collision_suspect': '碰撞疑似',
    'severe_collision': '严重碰撞',
    'gps_unstable': 'GPS不稳定',
    'dynamic_cell': '动态Cell',
    'insufficient_sample': '样本不足',
    'bs_id_lt_256': 'BS_ID异常(<256)',
    'multi_operator_shared': '多运营商共建',
    'multi_lac_anomaly': '多LAC归属',
    'gps_drift': 'GPS漂移',
};

const t = (key) => LAYER_CN[key] || ANOMALY_CN[key] || key;
```

渲染时使用：
```javascript
// 修改前
${l.layer_id}
// 修改后
${t(l.layer_id)}
```

---

## 维度 D：代码质量与架构

**评定：部分通过**

### SQL 注入检查

| 文件 | 检查结果 | 说明 |
|------|:-------:|------|
| `pipeline.py` | ✅ 安全 | 所有查询使用 `text()` + 命名参数 (`:param`)。f-string 仅拼接 WHERE 子句结构，值通过 params 传递 |
| `runs.py` | ✅ 安全 | INSERT/UPDATE 均使用命名参数。`status` 字段有白名单校验 (L75-77) |
| `steps.py` | ✅ 安全 | `relname = :tbl` 中 tbl 来自数据库内部数据 |
| `metrics.py` | ✅ 安全 | 全部硬编码 SQL，无用户输入拼接 |

**结论：无 SQL 注入风险**。

### API 错误处理

| 层面 | 现状 | 问题 |
|------|------|------|
| `runs.py` | ✅ 正确返回 404/400 | — |
| `steps.py` | ✅ 正确返回 404 | — |
| `pipeline.py` | ❌ **无 try-except** | 数据库异常直接抛 500 |
| `metrics.py` | ❌ **无 try-except** | 数据库异常直接抛 500 |
| `app.js` 前端 | ⚠️ 仅顶层 `.catch()` | `Promise.all` 中任一请求失败导致整页空白 |

### database.py 连接池

```python
pool_size=5, max_overflow=10, pool_pre_ping=True, pool_recycle=300
```

- `pool_size=5` + `max_overflow=10`：峰值 15 连接，对于当前慢查询场景偏小
- `pool_pre_ping=True`：✅ 防止断线
- `pool_recycle=300`：✅ 合理
- **风险**：密码 `123456` 硬编码在 `config.py` L5，应改用 `.env`

### API 覆盖率

Doc05 定义 22 张 workbench/meta 表，当前 API 覆盖情况：

| 表名 | 有 API | 覆盖方式 |
|------|:------:|---------|
| wb_run | ✅ | CRUD (runs.py) |
| wb_step_registry | ✅ | Read (steps.py) |
| wb_parameter_set | ⚠️ | 仅间接读取 (steps.py) |
| wb_rule_set | ❌ | — |
| wb_sql_bundle | ❌ | — |
| wb_contract | ❌ | — |
| wb_baseline | ❌ | — |
| wb_step_execution | ❌ | — |
| wb_step_metric | ❌ | metrics.py 直接查大表而非此表 |
| wb_layer_snapshot | ❌ | metrics.py 直接查大表而非此表 |
| wb_gate_result | ❌ | — |
| wb_anomaly_stats | ❌ | metrics.py 直接查大表而非此表 |
| wb_reconciliation | ❌ | — |
| wb_rule_hit | ❌ | — |
| wb_issue_log | ❌ | — |
| wb_patch_log | ❌ | — |
| wb_sample_set | ❌ | — |
| meta_field_registry | ❌ | — |
| meta_field_health | ❌ | — |
| meta_field_mapping_rule | ❌ | — |
| meta_field_change_log | ❌ | — |
| meta_exposure_matrix | ❌ | — |

**API 覆盖率：22 张表中仅 3 张有部分 API，覆盖率 ~14%。**

**关键发现**：`metrics.py` 直接查 pipeline 大表，而不是查 Doc05 设计的 `wb_layer_snapshot` / `wb_step_metric` 快照表。**这是性能极慢的根本原因——设计文档已预见了需要快照表，但实现跳过了这一层。**

### 前端组件化

- **全部 JS 模板字符串拼接 HTML**：`loadOverview()` 50+ 行模板、`loadStep()` 40+ 行模板、`loadAnomaly()` 20+ 行模板
- 无 Web Components / 模板引擎 / 公共片段提取
- 重复表格生成代码至少 5 处
- **正面**：代码可读性尚可，函数命名清晰

---

## 总体结论

**结论：需修改后可用**

当前完成了最小化概念验证原型（P1 简版 + P2 简版 + 异常统计），但与 V2 设计差距巨大。**三个核心问题全部存在**：

1. ❌ **性能**：首页加载 ≥5 分钟（直接查大表无缓存）
2. ❌ **UI 缺失**：V2 设计 4 页面+3 抽屉仅实现 P1(30%)+P2(20%)，P3/P4/D1/D2/D3 完全缺失
3. ❌ **英文不可理解**：异常类型/layer_id/表名/参数键名全是英文

### 必须修改项

| # | 优先级 | 问题 | 涉及文件 | 修改方案 | 工作量 |
|:---:|:------:|------|---------|---------|:------:|
| 1 | **P0** | step-summary/layer-snapshot 直接查大表导致首页 5min+ | `metrics.py` | 改查 `wb_layer_snapshot`/`wb_step_metric` 或创建物化视图+内存缓存 | 2天 |
| 2 | **P0** | 前端无缓存，每次页面切换重查全部 | `app.js` | 添加 JS 变量缓存层+手动刷新按钮 | 1天 |
| 3 | **P0** | stats/operator-tech 对 fact_final(3050万行) 全表扫描 | `pipeline.py` | 预计算存入 wb_step_metric 或物化视图 | 1天 |
| 4 | **P1** | P2 缺少 C.规则/E.SQL/F.数据变化/G.差异/H.样本 5 区块 | `app.js` + 新增 API | 需先填充 wb_rule_hit/wb_sql_bundle/wb_step_metric | 5天 |
| 5 | **P1** | P3 字段治理完全缺失 | 新增 `field.py` + `app.js` | 对接 meta schema 5 张表 | 3天 |
| 6 | **P1** | P4 样本研究完全缺失 | 新增 `samples.py` + `app.js` | 对接 wb_sample_set | 3天 |
| 7 | **P1** | D1/D2/D3 抽屉完全缺失 | `app.js` + `index.html` | 版本/SQL/对象详情抽屉组件 | 3天 |
| 8 | **P1** | 英文名无中文翻译 | `app.js` + `pipeline.py` + `metrics.py` | 添加翻译字典（前端+后端两层） | 1天 |
| 9 | **P2** | ctx-bar 缺少 5 个上下文标签 | `index.html` + `app.js` | 扩充上下文条 | 0.5天 |
| 10 | **P2** | pipeline.py/metrics.py 无 try-except | `pipeline.py`, `metrics.py` | 添加错误处理 | 0.5天 |
| 11 | **P2** | 20/22 workbench/meta 表无 API | 新增 API 文件 | 按需添加 CRUD | 3天 |
| 12 | **P2** | 数据库密码硬编码 | `config.py` | 改为 `.env` 读取 | 0.5天 |

### 建议改进项

1. **前端重构**：将 HTML 模板提取为独立函数或 Web Components
2. **错误降级**：`Promise.all` 改为 `Promise.allSettled`，部分失败仍展示已加载数据
3. **DB COMMENT**：根据 Doc02 §2.1 为 pipeline schema 全部列添加 COMMENT
4. **连接池调整**：慢查询修复前临时提高 `pool_size` 至 20
5. **API 文档**：为每个端点添加 Pydantic response_model 和 docstring