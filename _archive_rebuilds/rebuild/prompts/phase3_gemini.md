# 第三阶段规划审计 — Gemini Agent

> 身份：**Gemini 规划审计 Agent（第三阶段）**
> 审计目标：基于当前系统状态，独立分析所有优化项，输出可执行的第三阶段开发计划
> 输出路径：`rebuild/audit/phase3_gemini.md`

---

## 1. 审计背景

### 项目定位
本地网优数据治理系统——"治理链路调试与验证工作台"。用户是数据治理工程师，工作模式：调参→重跑→看差异→看样本→判断结果是否可信。这是单用户本地调试工具，不是多租户平台。

### 已完成工作
- **第一阶段（文档）**：6 份设计文档（Doc00~05），两轮三方审计
- **第二阶段（开发）**：
  - PG17 数据库：4 个 schema（legacy/pipeline/workbench/meta），68+ 张表
  - FastAPI 后端：5 个 router，~35 个 API 端点，3 个 service 模块（workbench/labels/cache）
  - 前端工作台：P1~P4 + D1~D3（骨架级），原生 HTML/CSS/JS，无框架
  - 快照表 + 内存缓存 + 中文标签
  - 19 个 API 测试通过

### 当前评估快照

| 维度 | 评分 | 核心问题 |
|------|------|---------|
| 整体完成度 | 62/100 | |
| V2 设计还原度 | 55/100 | P3(35%), P4(45%) |
| 字段治理 | **35/100** | 缺原始字段定义层、合规规则、合规率 |
| 代码质量 | 50/100 | workbench.py 2,045行、app.js 1,184行 |
| 性能缓存 | 75/100 | 三层架构已到位 |
| 中文化 | 70/100 | 基本覆盖 |

### 数据库现状

| 表 | 行数 |
|----|------|
| pipeline.raw_records | 251,172,880 |
| pipeline.fact_final | 30,492,108 |
| pipeline.fact_filtered | 21,788,532 |
| pipeline.dim_bs_trusted | 138,121 |
| pipeline.dim_cell_stats | 502,199 |
| pipeline.dim_lac_trusted | 881 |
| meta.meta_field_registry | 561（全active，description全空） |
| meta.meta_field_health | **0（空表）** |
| meta.meta_field_mapping_rule | **0（空表）** |
| workbench.wb_layer_snapshot | 36 |
| workbench.wb_step_metric | 123 |
| workbench.wb_anomaly_stats | 27 |
| workbench.wb_rule_hit | 39 |
| workbench.wb_run | 5 |
| workbench.wb_step_registry | 22 |
| workbench.wb_parameter_set | 1（P-001） |

**P-001 已有合规参数：** operator_whitelist, tech_whitelist, china_bbox, lac_overflow_values, rsrp_invalid_values, rsrp_max_valid

---

## 2. 待审计文件清单

**你必须完整读取以下所有文件，不得跳过。**

### 当前实现（11文件）
1. `rebuild/backend/app/main.py`
2. `rebuild/backend/app/api/pipeline.py`（293行）
3. `rebuild/backend/app/api/steps.py`（166行）
4. `rebuild/backend/app/api/metrics.py`（80行）
5. `rebuild/backend/app/api/workbench.py`（127行）
6. `rebuild/backend/app/services/workbench.py`（2,045行）
7. `rebuild/backend/app/services/labels.py`（207行）
8. `rebuild/backend/app/services/cache.py`（85行）
9. `rebuild/frontend/app.js`（1,184行）
10. `rebuild/frontend/index.html`（82行）
11. `rebuild/frontend/style.css`（720行）

### V2 UI 设计原型（5文件）
12. `docs/data_warehouse/Pre_UI/V2/index.html`
13. `docs/data_warehouse/Pre_UI/V2/step-lac.html`
14. `docs/data_warehouse/Pre_UI/V2/fields.html`
15. `docs/data_warehouse/Pre_UI/V2/samples.html`
16. `docs/data_warehouse/Pre_UI/V2/wb.css`

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

## 3. 分析维度（6个维度）

### 维度 F：字段治理完整性（最高优先级）

**核心缺口描述：**

当前 P3 字段治理只有"第二层"——从 information_schema 同步的 pipeline 列定义（561条）。完全缺失"第一层"——原始字段的业务定义和合规规则。

用户期望的第一层内容：

| 原始字段 | 业务含义 | 合规规则 | 异常值 |
|---------|---------|---------|--------|
| LAC | 位置区域码 | 4G:[0,65535], 5G:[0,16777215] | 65534,65535,FFFF等 |
| cell_id | 小区标识 | 4G:[1,268435455], 5G:[1,68719476735] | |
| RSRP | 参考信号接收功率 | [-140,-44] dBm | -110,-1,≥0 |
| RSRQ | 参考信号接收质量 | [-20,-3] dB | |
| SINR | 信噪比 | [-20,30] dB | |
| RSSI | 接收信号强度 | [-110,-25] dBm | |
| lon/lat | GPS坐标 | 中国境内[73,135]×[3,54] | |
| operator_id | 运营商ID | 五大PLMN编码 | |
| tech | 制式 | 4G/5G | |

**你需要回答的关键问题：**

1. **合规规则存在哪里最合理？**
   - 选项A：在 meta_field_registry 中增加合规列（valid_min, valid_max, invalid_values JSONB, compliance_expr text）
   - 选项B：新建 meta.meta_source_field_compliance 独立表
   - 选项C：用 meta_field_mapping_rule（rule_type='compliance'）
   - 各选项的优劣分析

2. **合规率从哪算？**
   - raw_records(2.5亿) — 最全面但最慢
   - fact_filtered(2180万) — 已过滤但保留了主要字段
   - 按字段分别选最合适的源表？
   - 用采样还是全量？

3. **合规率结果存在哪？**
   - meta_field_health 表（已存在但空）— 设计上就是为此用的
   - 新建 compliance_snapshot 表
   - 与 wb_layer_snapshot 类似的快照模式

4. **前端如何展示？**
   - P3 页面增加 Tab 切换（"原始字段" vs "过程字段"）？
   - 还是分为两个独立区域？
   - 合规率的可视化方式

### 维度 A：V2 设计还原度

**请用最严格的标准**逐组件对比。对每个V2组件，标注：
- ✅ 已实现且功能完整
- ⚠️ 已实现但功能不完整（说明缺什么）
- ❌ 未实现

重点关注 V2 fields.html 中的字段详情展开区（5个子块）和 samples.html 中的分类筛选+子表展开。

### 维度 B：性能与缓存

重点评估：
1. 新增合规率计算（可能涉及2.5亿行扫描）的性能影响
2. 是否需要专门的合规率预计算脚本
3. 当前快照刷新策略是否需要调整

### 维度 C：代码架构

**workbench.py 2,045行拆分分析：**
- 读取文件，识别所有函数和类
- 按职责分组，提出拆分方案
- 评估拆分的复杂度和风险

**app.js 1,184行拆分分析：**
- 读取文件，识别所有函数
- 在"不引入框架"约束下的模块化方案
- 全局状态如何共享

### 维度 D：中文化

- description 空字段的批量填充方案
- 原始字段业务含义文本的来源和维护

### 维度 E：业务逻辑

- 版本体系各组件的数据完整性
- 指标与 Doc04 的对齐
- 质量门是否有实现

---

## 4. 输出格式

```markdown
# Gemini 第三阶段规划审计报告

> 审计日期：[日期]

## 1. 各维度分析

### F. 字段治理
**选型推荐：** [A/B/C 选哪个，为什么]
**合规率计算方案：** [源表/策略/存储/性能]
**API设计：** [端点列表]
**前端方案：** [交互设计]

### A. V2 还原度
**对比清单：**
| 组件 | V2 | 当前 | 状态 |
|------|-----|------|------|

### B. 性能
[评估与建议]

### C. 代码架构
**workbench.py 拆分：**
[方案]

**app.js 拆分：**
[方案]

### D. 中文化
[方案]

### E. 业务逻辑
[检查结果]

## 2. 开发计划

### 任务排序
| # | 任务 | 前置依赖 | 工作量 | 产出 |
|---|------|---------|--------|------|

### 里程碑
[定义]

### 决策问题
[列出需要用户裁决的问题]

## 3. 实施建议
[你认为最高效的实施路径]
```

---

## 5. 注意事项

- **你是最擅长数据工程的审计者**，请重点关注数据规模对方案可行性的影响
- 合规率计算方案必须给出对 2.5亿行表的性能估算（基于 PG17 的能力）
- 要特别注意"过度工程化"风险——这是单用户调试工具，不需要企业级方案
- 如果某个 V2 设计组件实现成本高但使用频率低，建议降级或简化
- 请给出你认为最务实的方案，而不是最完美的方案
- **不要修改任何文件，只输出分析报告**
