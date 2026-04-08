# 第三阶段规划审计 — Codex Agent

> 身份：**Codex 规划审计 Agent（第三阶段）**
> 审计目标：基于当前系统状态，独立分析所有优化项，输出可执行的第三阶段开发计划
> 输出路径：`rebuild/audit/phase3_codex.md`

---

## 1. 审计背景

### 项目定位
本地网优数据治理系统——"治理链路调试与验证工作台"。NOT 自动化平台，NOT 数仓门户，IS 调试验证工具。

### 已完成工作
- **第一阶段（文档）**：6 份设计文档（Doc00~05），两轮三方审计
- **第二阶段（开发）**：
  - PG17 数据库：4 个 schema（legacy/pipeline/workbench/meta），68+ 张表，数据已迁移
  - FastAPI 后端：5 个 router，~35 个 API 端点，3 个 service 模块
  - 前端工作台：P1~P4 四页面 + D1~D3 三抽屉（骨架级），1,184 行 app.js + 720 行 style.css
  - 快照架构 + AsyncTTLCache 缓存 + 中文标签（labels.py 561 条字段注册）
  - 19 个 API 测试通过

### 当前评估快照（由协调 agent 预扫描得出）

| 维度 | 评分 | 核心问题 |
|------|------|---------|
| 整体完成度 | 62/100 | 多项核心功能停留在骨架级 |
| V2 设计还原度 | 55/100 | P3 字段治理严重缺失(35%)，P4 样本研究偏弱(45%) |
| 字段治理 | **35/100** | 只有过程字段注册，无原始字段业务定义/合规规则/合规率 |
| 代码质量 | 50/100 | workbench.py 2,045行、app.js 1,184行，严重超标 |
| 性能缓存 | 75/100 | 快照+缓存架构已到位，但快照刷新仍按需触发 |
| 中文化 | 70/100 | 基本覆盖，但字段 description 全空，上下文栏英文 |

### 数据库现状

| 表 | 行数 | 说明 |
|----|------|------|
| pipeline.raw_records | 251,172,880 | 原始合并数据 |
| pipeline.fact_final | 30,492,108 | 最终事实表 |
| pipeline.fact_filtered | 21,788,532 | 过滤后事实表 |
| pipeline.dim_bs_trusted | 138,121 | 可信BS维表 |
| pipeline.dim_cell_stats | 502,199 | Cell统计维表 |
| pipeline.dim_lac_trusted | 881 | 可信LAC维表 |
| meta.meta_field_registry | 561 | 字段注册（全部active，description全空） |
| meta.meta_field_health | 0 | **空表** |
| meta.meta_field_mapping_rule | 0 | **空表** |
| workbench.wb_layer_snapshot | 36 | 层快照 |
| workbench.wb_step_metric | 123 | 步骤指标 |
| workbench.wb_anomaly_stats | 27 | 异常统计 |
| workbench.wb_rule_hit | 39 | 规则命中 |
| workbench.wb_run | 5 | 运行记录 |
| workbench.wb_step_registry | 22 | 步骤注册 |
| workbench.wb_parameter_set | 1 | 参数集（P-001，含全局合规参数） |

**wb_parameter_set P-001 中已有的全局合规参数：**
```json
{
  "operator_whitelist": ["46000","46001","46011","46015","46020"],
  "tech_whitelist": ["4G","5G"],
  "china_bbox": {"lon_min":73,"lon_max":135,"lat_min":3,"lat_max":54},
  "lac_overflow_values": [65534,65535,16777214,16777215,2147483647],
  "rsrp_invalid_values": [-110, -1],
  "rsrp_max_valid": -1
}
```

---

## 2. 待审计文件清单

**你必须完整读取以下所有文件，不得跳过。**

### 当前实现（11文件）
1. `rebuild/backend/app/main.py` — 后端入口
2. `rebuild/backend/app/api/pipeline.py` — 管线 API（293行）
3. `rebuild/backend/app/api/steps.py` — 步骤 API（166行）
4. `rebuild/backend/app/api/metrics.py` — 指标 API（80行）
5. `rebuild/backend/app/api/workbench.py` — 工作台 API（127行）
6. `rebuild/backend/app/services/workbench.py` — 核心服务层（2,045行）
7. `rebuild/backend/app/services/labels.py` — 中文标签（207行）
8. `rebuild/backend/app/services/cache.py` — 缓存（85行）
9. `rebuild/frontend/app.js` — 前端主逻辑（1,184行）
10. `rebuild/frontend/index.html` — 前端结构（82行）
11. `rebuild/frontend/style.css` — 前端样式（720行）

### V2 UI 设计原型（5文件，必须对比）
12. `docs/data_warehouse/Pre_UI/V2/index.html` — P1 链路总览
13. `docs/data_warehouse/Pre_UI/V2/step-lac.html` — P2 步骤工作台
14. `docs/data_warehouse/Pre_UI/V2/fields.html` — P3 字段治理
15. `docs/data_warehouse/Pre_UI/V2/samples.html` — P4 样本研究
16. `docs/data_warehouse/Pre_UI/V2/wb.css` — 设计样式

### 设计文档（7文件，理解业务本质）
17. `rebuild/docs/00_重构上下文与范围.md` — UI结构定义
18. `rebuild/docs/02_新旧表体系映射.md` — 表名对照+字段映射
19. `rebuild/docs/04_指标注册表.md` — 指标定义
20. `rebuild/docs/05_工作台元数据DDL.md` — 元数据表定义
21. `docs/data_warehouse/00_业务逻辑与设计原则.md` — 核心业务原则
22. `docs/data_warehouse/本地治理链路工作台_开发基础文档.md` — 开发基础
23. `docs/data_warehouse/本地治理链路工作台_UI开发意见.md` — UI 开发意见

### 历史参考
24. `rebuild/audit/audit_round2_final.md` — 第二轮审计合并报告
25. `docs/data_warehouse/2026-03-24_本地治理工作台完整修复与优化说明.md` — 上轮修复说明

---

## 3. 分析维度（6个维度，全部必须评估并给出实施方案）

### 维度 F：字段治理完整性（最高优先级）

**这是用户明确要求的重点改进方向。当前是系统最大缺口。**

当前 P3 字段治理仅展示 pipeline 表的过程字段注册（information_schema 抓取的列定义）。**缺失了原始字段的业务定义和合规规则管理。**

你需要分析并给出完整方案：

1. **原始字段合规规则存储方案**
   - 选项A：扩展现有 `meta.meta_field_registry` 表，增加合规规则列（valid_range_min, valid_range_max, invalid_values, compliance_rule_expr 等）
   - 选项B：新建独立表 `meta.meta_source_field_compliance`，专门存储原始字段合规规则
   - 选项C：利用 `meta.meta_field_mapping_rule` 表（rule_type='compliance'），存储合规规则
   - 需要考虑：字段列表见 session_restore_v2.md §F（LAC, cell_id, RSRP, RSRQ, SINR, RSSI, GPS, 运营商, 制式等）
   - wb_parameter_set P-001 已有部分合规参数（operator_whitelist, lac_overflow_values, rsrp_invalid_values），如何与字段级合规关联？

2. **合规率计算方案**
   - 从哪张表计算？raw_records(2.5亿行) vs fact_filtered(2180万行) vs fact_final(3050万行)？
   - 实时计算 vs 预计算快照？
   - 计算频率和触发时机？
   - 如何按运营商/制式/批次切片？

3. **P3 前端改造方案**
   - 如何在现有 P3 页面增加"原始字段"标签页或区块？
   - 字段详情展开区需要哪些子块？（V2 设计中有：基本信息/映射规则/健康趋势/影响步骤/变更历史）
   - 合规率可视化方案

4. **后端 API 新增**
   - 需要哪些新 API？
   - 是否需要新的 service 模块？

### 维度 A：V2 设计还原度

**你必须逐个读取 V2 设计的 HTML 文件，与当前 app.js 逐函数对比。**

1. **P1 链路总览**：逐区块对比 V2 index.html vs loadOverview()
2. **P2 步骤工作台**：逐区块(A~H)对比 V2 step-lac.html vs loadStep()
3. **P3 字段治理**：对比 V2 fields.html vs loadFields()（预期差距最大）
4. **P4 样本研究**：对比 V2 samples.html vs loadSamples()
5. **D1/D2/D3 抽屉**：对比 V2 设计中的抽屉交互 vs openVersionDrawer/openSqlDrawer/openSampleDrawer

对每个缺失组件，给出：
- 缺失严重性（P0/P1/P2）
- 前端实现工作量
- 所需后端 API 支持

### 维度 B：性能与缓存优化

1. **当前缓存架构评估**：
   - 快照表（wb_layer_snapshot 等）作为数据库物化层是否足够？
   - AsyncTTLCache 内存缓存是否有必要保留？（考虑单进程重启场景）
   - 是否需要 Redis 或更重的方案？

2. **快照刷新机制**：
   - 当前按需触发（API请求时 ensure_snapshot_bundle）是否合理？
   - 是否应改为独立脚本/cron 定时刷新？
   - 手动刷新 UI 按钮是否到位？

3. **合规率计算的性能考量**：
   - 对 raw_records(2.5亿行) 做合规率计算的性能方案
   - 是否需要专门的合规率快照表？

### 维度 C：代码架构改造

**当前违反"单文件不超过500行"规则的文件：**
- `services/workbench.py`：2,045行 — 必须拆分
- `frontend/app.js`：1,184行 — 必须拆分

1. **后端拆分方案**：
   - 如何按职责拆分 workbench.py？
   - 拆分后的模块结构和接口设计
   - 导入依赖如何处理？
   - 是否需要 base service 或 utils 模块？

2. **前端拆分方案**：
   - 如何将 app.js 拆为多个 JS 模块？
   - 考虑到不引入框架（原生 HTML/CSS/JS），用什么模块化方案？（ES Module import？script 标签顺序？全局命名空间？）
   - 拆分后的文件结构

3. **函数级重构**：
   - loadOverview()（~250行）和 loadStep()（~230行）如何拆分？
   - 重复的 HTML 模板生成逻辑如何提取？

### 维度 D：中文化完善

1. meta_field_registry 中 561 条记录的 description 全为空 — 如何批量填充？
2. 上下文栏的英文标签（Run, Compare, Parameter 等）是否需要中文化？
3. 原始字段的业务含义注释（LAC="位置区域码"等）在哪里维护？

### 维度 E：业务逻辑正确性

1. 版本体系闭环检查：wb_rule_set / wb_sql_bundle / wb_contract / wb_baseline 表是否有数据？
2. 指标计算与 Doc04 定义的对齐度
3. 快照数据与 pipeline 表的一致性

---

## 4. 输出格式

```markdown
# Codex 第三阶段规划审计报告

> 审计日期：[日期]
> 审计文件数：25

## 1. 各维度评估

### 维度 F：字段治理完整性
**当前状态评估：** [详细分析]

**实施方案：**
#### F1. 数据库层
- 表结构设计（DDL）
- 初始数据填充方案
- 与 wb_parameter_set 的关联方式

#### F2. 后端 API 层
- 新增 API 端点列表
- Service 模块设计
- 合规率计算逻辑

#### F3. 前端展示层
- P3 页面改造方案
- 新增组件设计
- 与现有代码的集成方式

### 维度 A：V2 设计还原度
**V2 vs 当前实现对比矩阵**
| 组件/区块 | V2 设计 | 当前状态 | 差距 | 优先级 | 工作量 |
|-----------|---------|---------|------|--------|--------|

**补齐方案：** [具体到函数/组件级别]

### 维度 B：性能与缓存
**评估：** [分析]
**建议：** [具体方案]

### 维度 C：代码架构
**拆分方案：**
- workbench.py → [列出拆分后的模块]
- app.js → [列出拆分后的模块]
- [每个模块的职责和接口]

### 维度 D：中文化
**方案：** [具体方案]

### 维度 E：业务逻辑
**检查结果：** [详细分析]

## 2. 第三阶段开发计划

### 开发顺序建议
| 序号 | 任务 | 依赖 | 工作量 | 涉及文件 |
|------|------|------|--------|---------|

### 里程碑定义
| 里程碑 | 包含任务 | 验收标准 |
|--------|---------|---------|

### 有争议/需决策的问题
[列出你认为需要用户决策的问题，说明各选项的利弊]
```

---

## 5. 注意事项

- **你是最擅长代码分析的审计者**，请给出代码级别的具体方案（DDL、函数签名、API 路径）
- 字段治理方案必须包含完整的 DDL 和示例数据
- 后端拆分方案必须说明模块间的导入关系和依赖方向
- 前端拆分方案必须考虑"不引入框架"的约束
- 合规率计算必须给出性能估算（2.5亿行表的查询时间）
- 如果某个方案有多种实现路径且各有利弊，列出选项供最终裁决
- **不要修改任何文件，只输出分析报告**
