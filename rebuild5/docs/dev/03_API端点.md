# API 端点

本文件定义 rebuild5 后端 API 的端点清单和响应格式。

## 总体规则

- API 主要用途是**查询和展示**，供前端页面消费
- ETL 触发作为辅助功能封装为 API，方便 agent 调用和未来自动化
- 所有响应走统一信封格式
- 不做认证（内部工具）

## 统一响应格式

```json
{
  "data": { ... },
  "meta": {
    "timestamp": "2026-04-09T12:00:00Z",
    "dataset_key": "sample_6lac",
    "batch_id": 3
  },
  "error": null
}
```

错误时：

```json
{
  "data": null,
  "meta": { ... },
  "error": {
    "code": "STEP_NOT_READY",
    "message": "Step 2 尚未运行"
  }
}
```

## 执行类端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/etl/run` | 触发 Step 1 ETL（解析 → 清洗 → 补齐） |
| POST | `/api/routing/run` | 触发 Step 2 路由分流 + 基础画像 |
| POST | `/api/evaluation/run` | 触发 Step 3 流式质量评估 |
| POST | `/api/enrichment/run` | 触发 Step 4 知识补数 |
| POST | `/api/maintenance/run` | 触发 Step 5 画像维护 |
| POST | `/api/pipeline/run` | 顺序触发 Step 1-5 全流程 |

执行类端点返回运行统计，同步执行（数据量不大，不需要异步任务队列）。

## 查询类端点

### Step 1: 数据源接入（对应 5 个页面）

| 方法 | 路径 | 说明 | 对应页面 |
|------|------|------|----------|
| GET | `/api/etl/stats` | 最近一次 ETL 运行统计（解析/清洗/补齐） | 解析页、清洗页、补齐页 |
| GET | `/api/etl/source` | 数据源注册信息（来源表、行数、时间范围） | 数据源注册页 |
| GET | `/api/etl/field-audit` | 原始字段覆盖率和有效率统计 | 字段审计页 |
| GET | `/api/etl/coverage` | 补齐后字段覆盖率对比（补齐前 vs 补齐后） | 补齐页 |
| GET | `/api/etl/clean-rules` | 清洗规则命中明细（每条规则过滤了多少行） | 清洗页 |

### Step 2: 基础画像 + 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/routing/stats` | 分流统计（Path A/B/C 数量和比例） |
| GET | `/api/routing/collision` | 碰撞防护统计 |
| GET | `/api/routing/profile-base` | Path B Cell 基础指标列表（分页） |

### Step 3: 流式质量评估

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/evaluation/stats` | 评估运行统计 |
| GET | `/api/evaluation/cells` | Cell 评估列表（分页，支持状态筛选） |
| GET | `/api/evaluation/cells/:id` | 单个 Cell 详情 |
| GET | `/api/evaluation/bs` | BS 评估列表（分页） |
| GET | `/api/evaluation/bs/:id` | 单个 BS 详情（含下属 Cell） |
| GET | `/api/evaluation/lac` | LAC 评估列表（分页） |
| GET | `/api/evaluation/lac/:id` | 单个 LAC 详情（含下属 BS） |
| GET | `/api/evaluation/snapshot/diff` | 快照差分 |
| GET | `/api/evaluation/trend` | 跨批次收敛趋势 |

### Step 4: 知识补数

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/enrichment/stats` | 补数运行统计 |
| GET | `/api/enrichment/coverage` | 补数覆盖率（GPS / 信号 / 运营商） |
| GET | `/api/enrichment/anomalies` | GPS 异常列表 |

### Step 5: 画像维护

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/maintenance/stats` | 维护运行统计 |
| GET | `/api/maintenance/cells` | Cell 维护列表（分页，支持漂移/碰撞/多质心筛选） |
| GET | `/api/maintenance/cells/:id` | 单个 Cell 维护详情（含多质心簇） |
| GET | `/api/maintenance/bs` | BS 维护列表 |
| GET | `/api/maintenance/bs/:id` | 单个 BS 维护详情（含多质心簇） |
| GET | `/api/maintenance/lac` | LAC 维护列表 |
| GET | `/api/maintenance/collision` | 碰撞 Cell 列表 |
| GET | `/api/maintenance/drift` | 漂移分类分布 |

### Step 6: 服务查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/service/cell/:cell_id` | 查询可信 Cell 画像 |
| GET | `/api/service/bs/:bs_id` | 查询可信 BS 画像 |
| GET | `/api/service/lac/:lac` | 查询可信 LAC 画像 |
| GET | `/api/service/search` | 按条件搜索可信对象 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/system/health` | 服务健康检查 |
| GET | `/api/system/run-log` | 运行日志查询 |
| GET | `/api/system/config` | 当前配置快照 |

## API 与页面映射

每个前端页面需要消费的 API 端点清单，开发时按此对接：

| 页面 | 路由 | 消费的 API 端点 |
|------|------|----------------|
| 数据集选择 | `/global/dataset` | `/api/system/config` |
| 运行历史 | `/global/history` | `/api/system/run-log` |
| 数据源注册 | `/etl/source` | `/api/etl/source` |
| 字段审计 | `/etl/field-audit` | `/api/etl/field-audit` |
| 解析 | `/etl/parse` | `/api/etl/stats` |
| 清洗 | `/etl/clean` | `/api/etl/stats`, `/api/etl/clean-rules` |
| 补齐 | `/etl/fill` | `/api/etl/stats`, `/api/etl/coverage` |
| 基础画像与分流 | `/profile/routing` | `/api/routing/stats`, `/api/routing/collision`, `/api/routing/profile-base` |
| 流转总览 | `/evaluation/overview` | `/api/evaluation/stats`, `/api/evaluation/trend` |
| 流转快照 | `/evaluation/snapshot` | `/api/evaluation/snapshot/diff` |
| 观察工作台 | `/evaluation/watchlist` | `/api/evaluation/cells?lifecycle_state=waiting,observing` |
| Cell 评估 | `/evaluation/cell` | `/api/evaluation/cells`, `/api/evaluation/cells/:id` |
| BS 评估 | `/evaluation/bs` | `/api/evaluation/bs`, `/api/evaluation/bs/:id` |
| LAC 评估 | `/evaluation/lac` | `/api/evaluation/lac`, `/api/evaluation/lac/:id` |
| 知识补数 | `/governance/fill` | `/api/enrichment/stats`, `/api/enrichment/coverage`, `/api/enrichment/anomalies` |
| Cell 维护 | `/governance/cell` | `/api/maintenance/cells`, `/api/maintenance/cells/:id`, `/api/maintenance/drift` |
| BS 维护 | `/governance/bs` | `/api/maintenance/bs`, `/api/maintenance/bs/:id` |
| LAC 维护 | `/governance/lac` | `/api/maintenance/lac` |
| 晋级规则 | `/config/promotion` | `/api/system/config` |
| 防毒化规则 | `/config/antitoxin` | `/api/system/config` |
| 数据保留策略 | `/config/retention` | `/api/system/config` |
| 基站查询 | `/service/query` | `/api/service/search`, `/api/service/cell/:id`, `/api/service/bs/:id` |
| 覆盖分析 | `/service/coverage` | `/api/service/search`, `/api/service/lac/:lac` |
| 统计报表 | `/service/report` | `/api/maintenance/stats`, `/api/evaluation/stats` |

## 分页约定

列表类端点统一使用 `page` + `page_size` 参数：

```
GET /api/evaluation/cells?page=1&page_size=50&lifecycle_state=qualified
```

响应 meta 中包含分页信息：

```json
{
  "meta": {
    "page": 1,
    "page_size": 50,
    "total_count": 3825,
    "total_pages": 77
  }
}
```
