# 第三阶段规划审计 — Claude Agent

> 身份：**Claude 规划审计 Agent（第三阶段）**
> 审计目标：基于当前系统状态，独立分析所有优化项，输出可执行的第三阶段开发计划
> 输出路径：`rebuild/audit/phase3_claude.md`

---

## 1. 审计背景

### 项目定位
本地网优数据治理系统——"治理链路调试与验证工作台"。核心功能：调参→重跑→看差异→看样本→判断是否可信。不是自动化平台，不是数仓门户。

### 已完成工作
- **第一阶段（文档）**：6 份设计文档（Doc00~05），两轮三方审计
- **第二阶段（开发）**：
  - PG17 数据库：4 个 schema（legacy/pipeline/workbench/meta），68+ 张表
  - FastAPI 后端：5 个 router，~35 个 API 端点，3 个 service 模块
  - 前端工作台：P1~P4 四页面 + D1~D3 三抽屉（骨架级），原生 HTML/CSS/JS
  - 快照架构 + AsyncTTLCache 缓存 + 中文标签（561 条字段注册）
  - 19 个 API 测试通过

### 当前评估快照

| 维度 | 评分 | 核心问题 |
|------|------|---------|
| 整体完成度 | 62/100 | 多项核心功能停留在骨架级 |
| V2 设计还原度 | 55/100 | P3(35%), P4(45%), D1-D3(50-60%) |
| 字段治理 | **35/100** | 只有过程字段注册，缺原始字段业务定义/合规规则/合规率 |
| 代码质量 | 50/100 | workbench.py 2,045行、app.js 1,184行，严重超标 |
| 性能缓存 | 75/100 | 快照+缓存架构已到位 |
| 中文化 | 70/100 | 基本覆盖，细节不完整 |

### 数据库现状

| 表 | 行数 | 说明 |
|----|------|------|
| pipeline.raw_records | 251,172,880 | 原始合并数据（2.5亿行） |
| pipeline.fact_final | 30,492,108 | 最终事实表 |
| pipeline.fact_filtered | 21,788,532 | 过滤后事实表 |
| pipeline.dim_bs_trusted | 138,121 | 可信BS维表 |
| pipeline.dim_cell_stats | 502,199 | Cell统计维表 |
| pipeline.dim_lac_trusted | 881 | 可信LAC维表 |
| meta.meta_field_registry | 561 | 字段注册（全active，description全空） |
| meta.meta_field_health | **0** | 空表 |
| meta.meta_field_mapping_rule | **0** | 空表 |
| workbench.wb_layer_snapshot | 36 | 层快照 |
| workbench.wb_step_metric | 123 | 步骤指标 |
| workbench.wb_run | 5 | 运行记录 |
| workbench.wb_parameter_set | 1 | 参数集 P-001 |

**P-001 全局合规参数：**
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

### V2 UI 设计原型（5文件，对比基准）
12. `docs/data_warehouse/Pre_UI/V2/index.html` — P1 链路总览
13. `docs/data_warehouse/Pre_UI/V2/step-lac.html` — P2 步骤工作台
14. `docs/data_warehouse/Pre_UI/V2/fields.html` — P3 字段治理
15. `docs/data_warehouse/Pre_UI/V2/samples.html` — P4 样本研究
16. `docs/data_warehouse/Pre_UI/V2/wb.css` — 设计样式

### 设计文档（7文件）
17. `rebuild/docs/00_重构上下文与范围.md`
18. `rebuild/docs/02_新旧表体系映射.md`
19. `rebuild/docs/04_指标注册表.md`
20. `rebuild/docs/05_工作台元数据DDL.md`
21. `docs/data_warehouse/00_业务逻辑与设计原则.md`
22. `docs/data_warehouse/本地治理链路工作台_开发基础文档.md`
23. `docs/data_warehouse/本地治理链路工作台_UI开发意见.md`

### 历史参考
24. `rebuild/audit/audit_round2_final.md`
25. `docs/data_warehouse/2026-03-24_本地治理工作台完整修复与优化说明.md`

---

## 3. 分析维度（6个维度，全部必须评估并给出实施方案）

### 维度 F：字段治理完整性（最高优先级）

**当前缺口：**
- meta_field_registry 561 条记录全是 information_schema 同步的列定义，description 全空
- meta_field_health 0 条 — 无任何字段健康数据
- meta_field_mapping_rule 0 条 — 无任何转换/合规规则
- P3 前端只展示过程字段列表，无业务含义、无合规规则、无合规率

**用户期望的完整字段治理包含两层：**

**第一层（缺失）— 原始字段定义（Source Field Registry）：**
- 网优原始字段业务含义和合规规则，包括但不限于：
  - LAC：位置区域码，4G范围[0,65535]，5G范围[0,16777215]，异常值{65534,65535,FFFF}
  - cell_id：小区标识，4G[1,268435455]，5G[1,68719476735]
  - RSRP：参考信号接收功率，正常[-140,-44]dBm，无效{-110,-1,≥0}
  - RSRQ：参考信号接收质量，正常[-20,-3]dB
  - SINR：信噪比，正常[-20,30]dB
  - RSSI：接收信号强度，正常[-110,-25]dBm
  - GPS：lon[73,135], lat[3,54]（中国境内）
  - 运营商：五大PLMN编码
  - 制式：4G/5G标准化规则
- 每个字段的合规规则（什么合规、什么异常、什么清洗）
- 合规覆盖率：当前数据各字段合规率

**第二层（已有）— 过程字段注册（Pipeline Column Registry）**

**你需要分析并给出方案：**

1. **数据模型设计**：如何在 meta schema 中存储原始字段合规规则？
   - 是扩展 meta_field_registry？新建表？还是用 meta_field_mapping_rule？
   - 合规规则的数据结构设计（JSON Schema？独立列？）
   - 与 wb_parameter_set 全局参数的关系

2. **合规率计算引擎**：
   - 计算源表选择（raw_records 2.5亿 vs fact_filtered 2180万 vs 分表计算）
   - 计算策略（全量预计算 vs 抽样 vs 增量）
   - 存储方案（复用 meta_field_health？新建 compliance_snapshot？）
   - 性能估算

3. **API 设计**：新增哪些端点、请求/响应结构

4. **前端改造**：P3 页面如何改造以承载两层字段治理

### 维度 A：V2 设计还原度

逐页面、逐区块对比 V2 设计与当前实现，重点关注：

1. **P1 链路总览**的 Context Bar / Pipeline Flow / Run Summary / Step Diff / Focus Areas
2. **P2 步骤工作台**的 8 个区块（A说明/B IO/C规则/D参数/E SQL/F数据变化/G差异/H样本）
3. **P3 字段治理**的完整组件体系（健康概览/筛选栏/字段表/展开区）
4. **P4 样本研究**的问题类型筛选/样本集列表/展开子表/详情抽屉
5. **D1/D2/D3 抽屉**的完整交互

对每个缺失项评估实现难度和依赖关系。

### 维度 B：性能与缓存

1. 当前三层缓存（大表→快照表→内存缓存→API）是否合理
2. 快照刷新策略：按需 vs 定时 vs 手动
3. **新增合规率计算**对性能的影响和缓存策略
4. 是否有遗留的大表实时扫描

### 维度 C：代码架构

1. **后端 workbench.py（2,045行）拆分方案**
   - 按职责划分模块
   - 共享依赖（数据库连接、缓存实例）如何处理
   - 避免循环导入

2. **前端 app.js（1,184行）拆分方案**
   - 原生 JS 模块化方案（不引入框架）
   - 共享状态管理
   - 事件绑定和路由

### 维度 D：中文化完善

1. 字段 description 批量填充策略
2. 原始字段业务含义的维护位置
3. 用户操作路径上的英文障碍清单

### 维度 E：业务逻辑正确性

1. 版本体系闭环（run + parameter_set + rule_set + sql_bundle + contract + baseline）
2. 指标覆盖度 vs Doc04 定义
3. 质量门检查（10 个 Gate）的实现状态

---

## 4. 输出格式

```markdown
# Claude 第三阶段规划审计报告

> 审计日期：[日期]

## 1. 各维度分析与实施方案

### F. 字段治理完整性
[当前状态 → 目标状态 → 实施方案（数据库/API/前端三层）]

### A. V2 设计还原度
[对比矩阵 → 补齐优先级 → 实施方案]

### B. 性能与缓存
[评估 → 建议]

### C. 代码架构
[拆分方案 → 模块依赖图]

### D. 中文化
[方案]

### E. 业务逻辑
[检查结果]

## 2. 第三阶段开发计划

### 任务分解与排序
| 序号 | 任务 | 依赖 | 涉及层 | 工作量 | 优先级 |
|------|------|------|--------|--------|--------|

### 里程碑
| 里程碑 | 任务集 | 验收标准 |

### 架构决策点
[列出需要用户决策的技术选型问题，每个给出推荐方案和理由]

## 3. 风险与注意事项
[实施过程中的技术风险、依赖风险、回退方案]
```

---

## 5. 注意事项

- **你是最擅长架构设计的审计者**，请重点关注方案的整体架构合理性和模块间依赖关系
- 字段治理方案要从"用户如何使用"的角度出发，不要过度工程化
- 拆分方案要给出清晰的模块依赖方向图
- 合规率计算要考虑实际数据规模（2.5亿行）的可行性
- 如果某个方案过于复杂（实现成本远高于收益），明确说"不建议做"并给出理由
- 注意这是调试工具，不是生产系统——简单实用优先
- **不要修改任何文件，只输出分析报告**
