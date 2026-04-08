# rebuild3 技术栈要求（最终冻结版）

> 状态：最终冻结版（UI 设计前置）  
> 适用对象：架构/实现评审、UI 设计协作者、后续实施 agent  
> 重要说明：本文约束的是“当前阶段与首轮实施”的技术边界，不是未来全国化云端系统的最终技术蓝图。

---

## 1. 总原则

rebuild3 的技术方案，当前必须遵守下面 8 条原则：

1. 以现有本地工程底座为主，不另起一套全新技术体系。
2. 以 PostgreSQL 为主计算与主存储底座，保持 **SQL-first**。
3. 以后端编排、读模型和批次控制为核心，不把大规模统计逻辑搬到前端或 Python 内存循环里。
4. 前端重构明确选择 **Vue 3 + TypeScript + Vite**，复用业务逻辑、读模型和接口，不复用旧前端结构本身。
5. rebuild2 / rebuild2_meta / legacy 资产保留，用作初始化输入、对照输入和回归输入。
6. 当前先满足本地验证、UI 设计和首轮实施，不提前做云端平台化和复杂基础设施。
7. 页面与 API 必须围绕对象 / 决策 / 事实 / baseline 读模型，而不是旧 Step 页面。
8. 批次与 baseline 的冻结语义必须先于实现细节。

---

## 2. 核心技术栈

| 层 | 当前要求 | 说明 |
|---|---|---|
| 数据库 | PostgreSQL 17 | 主计算、主存储、主回放环境 |
| 后端 | Python 3.11+ + FastAPI | 编排、读模型 API、状态输出 |
| 数据访问 | `asyncpg` / 现有 `SQLAlchemy asyncio` 连接能力 | **允许沿用已有依赖，但不使用 ORM 领域模型** |
| 数据模型 | Pydantic 2 | API 出入参、配置模型、读模型定义 |
| 前端 | Vue 3 + TypeScript + Vite | desktop-first 本地工作台 |
| 路由 | Vue Router | 围绕对象/批次/异常/baseline 组织 |
| 状态管理 | Pinia | 承接筛选条件、抽屉状态、基线上下文等共享状态 |
| 图表 | ECharts | 漏斗、趋势、空间分布、对比图 |
| 静态托管 | Vite 构建产物 + FastAPI `StaticFiles` | 开发期用 Vite，交付仍可由 FastAPI 托管 |
| 配置 | `.env` + DB 元数据表 | 敏感配置在 `.env`，规则和版本在表内 |
| 文档 | Markdown + Mermaid | 可直接审阅与版本管理 |

---

## 3. 当前明确不引入的技术

首轮范围内不主动引入：

- ORM 领域建模（SQLAlchemy ORM / Tortoise）
- Kafka / RabbitMQ / Celery / Airflow
- Redis / Elasticsearch / ClickHouse
- Spark / Flink / 大数据平台
- Docker / K8s / 云端调度系统
- Nuxt / SSR / 微前端 / 跨端框架
- 重型 UI 组件库（Element Plus / Ant Design Vue）
- CSS 框架（Tailwind / Bootstrap）

说明：

- 若仓库内已存在 `SQLAlchemy asyncio` 依赖，可仅作为连接/执行层沿用
- 但领域实现仍坚持 **SQL-first + 明确 SQL 脚本 / 参数化查询**
- 不将 ORM 实体映射作为主实现方式

---

## 4. 数据库与 schema 组织

### 4.1 schema 策略

首轮采用“增量新增，不覆盖旧库”的原则。

| Schema | 用途 | 操作权限 |
|---|---|---|
| `rebuild3` | 对象、事实、画像、异常、热层/长层/归档层 | rebuild3 代码读写 |
| `rebuild3_meta` | run、batch、version、source_adapter、控制元数据 | rebuild3 代码读写 |
| `rebuild2` | rebuild2 历史验证结果 | rebuild3 只读 |
| `rebuild2_meta` | rebuild2 元数据与规则定义 | rebuild3 只读 |
| `legacy` | 更早历史研究结果 | rebuild3 只读 |

### 4.2 命名原则

| 类型 | 命名规则 | 示例 |
|---|---|---|
| 表名 | 小写下划线，按功能前缀分组 | `obj_cell`, `fact_governed`, `profile_bs` |
| 列名 | 小写下划线 | `lifecycle_state`, `baseline_eligible` |
| 主键 | 业务主键优先 | `(operator_code, tech_norm, lac, cell_id)` |
| 索引 | `idx_{table}_{columns}` | `idx_obj_cell_bs_id` |
| ENUM | `{domain}_{name}_enum` | `lifecycle_state_enum` |
| 分区 | 大表按 `batch_id` 或等价批次键分区 | `fact_standardized` |

---

## 5. 状态、资格与枚举约束

### 5.1 lifecycle_state

最终冻结为：

- `waiting`
- `observing`
- `active`
- `dormant`
- `retired`
- `rejected`

### 5.2 health_state

最终冻结为：

- `healthy`
- `insufficient`
- `gps_bias`
- `collision_suspect`
- `collision_confirmed`
- `dynamic`
- `migration_suspect`

### 5.3 UI 派生状态

`watch` 不作为数据库持久化状态。  
如果需要展示“active 但需重点观察”，由读模型派生。

### 5.4 资格字段

对象快照或读模型中必须能直接回答：

- `anchorable`
- `baseline_eligible`

说明：

- 这两个字段可由规则推导，但必须在读模型中显式可见
- 不允许页面再通过多字段自行猜测对象资格

---

## 6. 数据层要求

### 6.1 标准化事件层

标准事件层必须满足：

1. 不可变
2. 保留原始来源信息和解析来源信息
3. 关键治理字段不能只放 JSON，必须落成可索引显式列
4. 必须有标准事件级幂等键

建议字段至少包含：

- `source_name`
- `source_record_id`
- `parsed_from`
- `source_group_seq`
- `source_cell_seq`
- `event_time`
- `operator_code`
- `tech_norm`
- `lac`
- `cell_id`
- `bs_id`

### 6.2 对象层

对象层必须是 rebuild3 核心，不允许只靠临时聚合维表替代。

最少应有：

- `obj_cell`
- `obj_bs`
- `obj_lac`
- `obj_state_history`
- `obj_relation_history`

对象快照必须显式支持：

- 业务主键
- `lifecycle_state`
- `health_state`
- `anchorable`
- `baseline_eligible`
- 当前有效关系
- 版本归属
- 最近活跃时间
- 样本与空间摘要

### 6.3 事实层

事实层最少分为：

1. `fact_governed`
2. `fact_pending_observation`
3. `fact_pending_issue`
4. `fact_rejected`

并保留独立的：

5. `fact_standardized`

要求：

1. 事实分层必须可追溯到决策结果
2. `fact_governed` 中显式记录：
   - `gps_source`
   - `signal_source`
   - `baseline_eligible`
   - `anomaly_tags`
3. 同一标准事件只能落到**一个主事实归宿**
4. `fact_pending_observation` 与 `fact_pending_issue` 不得混用

### 6.4 热层 / 长层 / 归档层

首轮方案必须允许三层长期保留：

| 层 | 要求 |
|---|---|
| 热层 | 服务近期画像、等待池、观察池、异常复核，按窗口滚动保留 |
| 长层 | 服务活跃节奏、成熟度、退役判断，按日或更粗粒度保留 |
| 归档层 | 服务审计、回放、完整回归，保留完整治理后事实历史 |

结论：

- per-Cell 热明细可以有
- 但不能只有 per-Cell 热明细

---

## 7. 版本、批次与幂等要求

### 7.1 最小版本体系

所有对象、事实、决策、画像都必须能追溯：

1. `run_id`
2. `contract_version`
3. `rule_set_version`
4. `baseline_version`

### 7.2 batch 要求

必须满足：

1. `run_id` 与 `batch_id` 分离
2. 批次显式记录窗口范围与来源
3. 2 小时批次不能只靠表名或文件名隐式推断
4. 同一批次必须能被重复回放和结果比对

### 7.3 event_time 要求

当前冻结版为：

- 默认以 `ts_std` 作为系统事件时间
- 保留 `cell_infos / ss1 / 原始字段` 中的时间证据列
- 后续如需升级，以 `contract_version` 管理

### 7.4 幂等要求

标准事件级幂等键必须显式落库，且不得只依赖原始 `record_id`。

原因：

- 一条原始记录会拆成多条标准事件
- `cell_infos` / `ss1` 有展开序号
- 同一 run、同一 batch 必须可重放、可去重、可比对

---

## 8. 性能与 SQL 规范

### 8.1 大表操作原则

- 千万级行操作优先通过 `psql`、批量 SQL 或后端批量执行完成
- 不走前端 API 直接扫大表
- 大表 JOIN 前必须确认索引覆盖
- 批量写入使用 `COPY`、`INSERT ... SELECT`、批量 upsert 等方式
- 所有 SQL 使用参数化查询，禁止字符串拼接

### 8.2 事务原则

**批次是逻辑事务单位，但不要求整批处理必须包在一个超大数据库事务中。**

最终要求是：

- 各步骤必须幂等
- step 级事务边界清晰
- 失败可重试、可回放、可恢复
- run / batch 状态机能正确反映执行进度

这样比“整个批次单事务”更适合首轮本地大批量回放。

### 8.3 执行计划检查

对新增的大表查询与写入，必须检查：

- `EXPLAIN`
- `EXPLAIN ANALYZE`
- 索引命中情况
- 行数估计偏差

---

## 9. 后端实现要求

### 9.1 服务职责

后端主要负责：

- 编排
- 校验
- 状态控制
- SQL 执行
- 读模型 API 输出

不建议在 Python 内存中做大规模明细聚合。

### 9.2 推荐目录结构

```text
rebuild3/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── run.py
│   │   │   ├── object.py
│   │   │   ├── decision.py
│   │   │   ├── anomaly.py
│   │   │   ├── profile.py
│   │   │   └── replay.py
│   │   ├── core/
│   │   │   ├── standardize.py
│   │   │   ├── registry.py
│   │   │   ├── route.py
│   │   │   ├── govern.py
│   │   │   ├── waiting_pool.py
│   │   │   ├── cascade.py
│   │   │   ├── anomaly_detect.py
│   │   │   ├── profile_build.py
│   │   │   ├── replay_compare.py
│   │   │   └── orchestrator.py
│   │   ├── models/
│   │   └── utils/
│   ├── requirements.txt
├── frontend/
├── sql/
├── scripts/
└── docs/
```

### 9.3 API 原则

- API 以**读模型优先**，不是先暴露底层表
- 路由围绕：
  - 运行 / 批次
  - 对象
  - 等待池
  - 异常
  - baseline / profile
  - 回放对比
- 返回统一 JSON 结构
- 大列表必须分页
- 错误码和 HTTP 状态码分离表达

### 9.4 长耗时任务原则

长耗时任务不应绑在单个同步 HTTP 请求里。

要求：

1. run / batch 先注册
2. 编排任务按状态推进
3. UI 主要读取进度和结果
4. 大统计优先落缓存表或汇总表后再给 UI 读取

### 9.5 配置参数化

以下内容必须配置化，不能硬编码：

- GPS 修正阈值
- 区域边界框开关与范围
- Cell 晋升阈值
- 热层保留策略
- 消失 / dormancy 判定参数
- 画像刷新批次数 / 触发条件
- 运营商白名单
- 信号有效范围
- 批次窗口大小

---

## 10. 前端与 UI 设计阶段要求

### 10.1 当前默认前端栈

- Vue 3
- TypeScript
- Vite
- Vue Router
- Pinia
- ECharts

### 10.2 当前前端组织原则

前端应围绕下面几类页面组织：

- 运行中心
- 对象浏览 / 对象详情
- 等待 / 观察池
- 日更审查 / 批次决策
- 异常看板
- baseline / profile
- 回放对比

### 10.3 当前默认不引入的前端基础设施

- React / Next / Nuxt
- SSR
- 微前端
- 跨端框架
- 重型 UI 组件库
- CSS 框架

### 10.4 Vue 组件规范

- 使用 `<script setup lang="ts">`
- Composition API
- Props / Emits 类型化
- 模板中不写复杂业务逻辑
- 组件边界按页面 / 共享组件 / 详情抽屉 / 筛选器组织
- 桌面优先，不要求移动端

### 10.5 样式规范

- 全局变量使用 CSS Custom Properties
- 组件内使用 scoped 样式
- 状态颜色统一表达：
  - active = 绿
  - waiting / observing = 黄
  - issue / anomaly = 橙
  - dormant = 灰
  - retired = 淡灰
  - rejected = 红

---

## 11. 测试与验证要求

### 11.1 测试层次

| 层次 | 范围 | 工具 |
|---|---|---|
| SQL 验证 | DDL、索引、枚举、分区 | `psql` |
| 单元测试 | core 模块核心函数 | `pytest` |
| 集成测试 | 初始化 / 增量编排 | `pytest` + 测试数据 |
| 收敛性验证 | 3 天初始化 + 4 天增量 vs 7 天初始化 | 对比脚本 |

### 11.2 验证顺序

必须遵守：

1. 先样本子集
2. 再小窗口回放
3. 再全量回放
4. 最后做收敛对比与性能优化

### 11.3 交付检查项

每个模块交付时至少满足：

- SQL 可执行
- 函数有类型注解
- 参数可配置
- 写入幂等
- 有日志与耗时统计
- 可与 rebuild2 结果对比（适用时）

---

## 12. 当前明确不做的事情

为了防止实现失焦，当前明确不要求：

1. 云端平台化
2. 流式计算与消息队列
3. 微服务拆分
4. 多城市 / 全国长期规则一次性定完
5. 在 UI 设计前冻结最终 API 细节
6. 把旧页面直接改造成最终页面

---

## 13. 必须预留的未来兼容边界

虽然当前不做云端化，但技术上必须预留下面这些边界：

1. 源适配接口边界
2. 批次回放接口边界
3. baseline 全量刷新与局部刷新边界
4. 局部重算与全量回归边界
5. UI 读模型边界
6. 异常样本与规则实验边界

这意味着当前实现不能把主逻辑写死在：

- 某一张具体原始表名
- 某一个具体城市边界
- 某一种固定批次粒度
- 某一版具体 UI 结构

---

## 14. 一句话结论

当前 rebuild3 的技术栈要求，核心不是“换技术”，而是：

**把已有的本地技术底座组织成一套可持续运行、可回放验证、可被 UI 稳定消费的动态治理系统。**
