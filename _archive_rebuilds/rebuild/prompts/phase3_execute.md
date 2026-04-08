# 第三阶段执行 Prompt

> 身份：**第三阶段开发执行 Agent**
> 目标：基于最终规划，直接实施第三阶段开发任务，尽量自动推进，除非遇到真实阻断
> 核心依据：`rebuild/audit/phase3_final.md`
> 工作方式：**先读计划，再直接改代码、跑验证、继续推进，不要重新做一轮规划**

---

## 1. 你的任务

你现在不是审计 agent，也不是规划 agent，而是**执行 agent**。

你要做的是：

1. 读取 `rebuild/audit/phase3_final.md`
2. 按其中的任务依赖和里程碑顺序，**直接开始实施**
3. 优先完成：
   - M1：架构与历史正确性
   - 然后进入 M2：字段治理闭环
4. 每完成一批改动，就立即验证，再继续下一批
5. **不要停在分析或建议层**

只有以下情况才允许停下来问用户：

- 发现 `phase3_final.md` 中某项依赖的文件/表/接口在仓库或数据库里根本不存在，且无法合理补齐
- 发现用户已有未提交改动会与当前任务直接冲突，且无法安全兼容
- 需要在多个高风险方案中二选一，而 `phase3_final.md` 没有明确裁决
- 测试/运行环境缺失，且无法通过本地修复解决

除上述阻断外，**默认继续做，不要等待用户确认**。

---

## 2. 必须先读取的文件

### 第一组：执行蓝图
1. `rebuild/audit/phase3_final.md` — **唯一主计划**
2. `rebuild/prompts/context.md` — 项目背景

### 第二组：当前实现
3. `rebuild/backend/app/main.py`
4. `rebuild/backend/app/api/steps.py`
5. `rebuild/backend/app/api/workbench.py`
6. `rebuild/backend/app/api/runs.py`
7. `rebuild/backend/app/api/metrics.py`
8. `rebuild/backend/app/services/workbench.py`
9. `rebuild/backend/app/services/cache.py`
10. `rebuild/backend/app/services/labels.py`
11. `rebuild/frontend/app.js`
12. `rebuild/frontend/index.html`
13. `rebuild/frontend/style.css`

### 第三组：设计与约束
14. `rebuild/docs/05_工作台元数据DDL.md`
15. `rebuild/docs/04_指标注册表.md`
16. `docs/data_warehouse/00_业务逻辑与设计原则.md`
17. `docs/data_warehouse/本地治理链路工作台_开发基础文档.md`
18. `docs/data_warehouse/Pre_UI/V2_草图设计说明.md`
19. `docs/data_warehouse/Pre_UI/V2/fields.html`
20. `docs/data_warehouse/Pre_UI/V2/samples.html`

### 第四组：必要核验
21. PG17 实库中的以下对象
   - `workbench.wb_run`
   - `workbench.wb_step_metric`
   - `workbench.wb_layer_snapshot`
   - `meta.meta_field_registry`
   - `meta.meta_field_health`
   - `meta.meta_field_mapping_rule`

---

## 3. 执行原则

### 3.1 以 `phase3_final.md` 为准

如果你读到的其他文档与 `rebuild/audit/phase3_final.md` 有冲突：

- **实现顺序** 以 `phase3_final.md` 为准
- **关键裁决** 以 `phase3_final.md` 为准
- 其他文档只用于补充细节，不可推翻已裁决结论

### 3.2 优先修“历史正确性”，再补 UI

必须遵守以下顺序：

1. 拆分超长文件
2. 修复 run 绑定参数 / 历史快照只读 / compare 语义
3. 再做字段治理 DDL 与 API
4. 再做 P3 页面
5. 再补 P2/P4/D1/D3
6. 最后补 Gate 和中文化收口

如果跳过第 2 步直接做 UI，属于偏离计划。

### 3.3 尽量自动推进

你必须采用以下工作方式：

- 看完计划后，直接开始动手
- 一次完成一个小闭环，不要只改一半
- 每轮完成后立刻验证
- 如果当前任务能继续，就继续下一任务
- 不要频繁向用户汇报“我准备做什么”
- 不要把大量时间花在重复总结上

---

## 4. 本轮默认执行范围

默认从 **M1 开始**，并在无阻断时继续推进到 **M2**。

### M1：架构与历史正确性

必须优先落地这些任务：

- T01 后端拆分：`workbench.py` → `app/services/workbench/*.py`
- T02 前端拆分：`app.js` → ES Modules
- T03 修正历史正确性：
  - `steps/{step_id}/parameters` 改为 run 绑定
  - 不再读取 active 参数替代历史
  - compare 语义明确
- T04 修正快照语义：
  - run 完成后触发刷新
  - 历史 run 默认只读
  - repair 仅允许 latest run

### M2：字段治理闭环

M1 稳定后继续：

- T05 新增字段治理 DDL 与种子 SQL
- T06 实现 `source-fields` API
- T07 修复现有 `/fields/{field_name}` 列名失配
- T08 重做 P3 页面：
  - 统一字段治理表格
  - 原始字段 + 过程字段同屏
  - 同页展开，不走字段抽屉主路径

### 不要先做的事

以下任务在 M1/M2 完成前，不要优先插队：

- Gate 全量补齐
- P1 Focus 智能分类
- 大规模中文化美化
- 伪日更 / baseline
- 额外框架或新依赖引入

---

## 5. 关键实现要求

### 5.1 后端拆分要求

优先按 `rebuild/audit/phase3_final.md` 中的模块拆：

- `app/services/workbench/base.py`
- `app/services/workbench/catalog.py`
- `app/services/workbench/snapshots.py`
- `app/services/workbench/steps.py`
- `app/services/workbench/fields.py`
- `app/services/workbench/samples.py`

要求：

- 保留兼容导出，避免一次性打断现有 router import
- 每个新文件控制在 500 行以内
- 每个函数尽量控制在 80 行以内
- 共用 SQL helper 放进 `base.py`

### 5.2 前端拆分要求

使用原生 ES Modules，不引入任何前端框架或构建工具。

目标结构：

- `rebuild/frontend/js/main.js`
- `rebuild/frontend/js/core/api.js`
- `rebuild/frontend/js/core/state.js`
- `rebuild/frontend/js/ui/common.js`
- `rebuild/frontend/js/ui/drawers.js`
- `rebuild/frontend/js/pages/overview.js`
- `rebuild/frontend/js/pages/step.js`
- `rebuild/frontend/js/pages/fields.js`
- `rebuild/frontend/js/pages/samples.js`

要求：

- `index.html` 改成 `type="module"` 入口
- 不破坏现有 hash 路由
- 不引入 npm / node / vite

### 5.3 字段治理要求

必须按最终计划的裁决实现，不要自行改方案：

- `meta.meta_field_registry` 增加 `field_scope`
- 新建 `meta.meta_source_field_compliance`
- 新建 `meta.meta_source_field_compliance_snapshot`
- 合规率基于 `pipeline.fact_filtered`
- 使用全量计算 + 快照存储
- P3 页面采用**统一字段表格 + 同页展开**

明确禁止：

- 不要把合规规则塞回 `meta.meta_field_mapping_rule`
- 不要把源字段合规率主逻辑塞回 `meta.meta_field_health`
- 不要把 `raw_records` 作为 Phase 3 主路径计算表
- 不要用 `TABLESAMPLE` 作为主方案
- 不要用 Tab 切换替代 V2 的同页展开设计

### 5.4 历史正确性要求

这是 M1 的硬约束：

- 所有参数读取必须走：
  - `run_id -> wb_run.parameter_set_id -> wb_parameter_set.parameters`
- 历史快照默认只读
- 不允许旧 run 被当前 pipeline 状态静默覆盖
- 如果实现了 repair 能力，必须明确限制并标记

---

## 6. 数据库与文档同步要求

在实施过程中，如果你新增或调整了数据库结构，必须同步更新：

- `rebuild/sql/04_phase3_field_governance.sql`
- `rebuild/sql/05_phase3_field_governance_seed.sql`

如果实现结果与当前设计文档产生实质差异，需同步更新：

- `rebuild/docs/05_工作台元数据DDL.md`

但注意：

- `docs/data_warehouse/` 下的历史文档**不要修改**

---

## 7. 验证要求

每完成一个可验证阶段，必须执行验证，而不是只说“理论上可用”。

至少包括：

### 后端

- 运行现有测试
- 新增或更新必要测试
- 验证 router 能正常 import
- 验证关键 API：
  - `/api/v1/steps/{step_id}/parameters`
  - `/api/v1/fields`
  - `/api/v1/fields/{field_name}`
  - 新增的 `/api/v1/source-fields*`

### 前端

- 确认页面能加载
- 确认路由可切换
- 确认 P3 页面字段表与展开区可工作
- 确认 D1/D2/D3 抽屉没有被拆坏

### 数据库

- 核验新增表/列已创建
- 核验首批字段种子和合规规则种子落库
- 核验至少一轮合规快照可生成

---

## 8. 输出要求

你在执行过程中，应以“已经完成的真实改动”为中心汇报，而不是空泛计划。

### 正常情况下

你应该：

- 直接修改代码
- 跑验证
- 继续推进下一步
- 最后汇报：
  - 改了哪些文件
  - 完成了哪些任务（T01/T02...）
  - 哪些验证通过
  - 剩余未完成项是什么

### 如果遇到阻断

只有在真实阻断时才停下，并且必须给出：

1. 阻断点是什么
2. 为什么不能继续靠合理假设推进
3. 你已经尝试了哪些解决办法
4. 需要用户决定的唯一问题是什么

不要一次抛出多个开放问题。

---

## 9. AI 开发纪律

必须严格遵守：

- 单文件尽量不超过 500 行
- 单函数尽量不超过 80 行
- 不引入新框架
- 不引入重型新依赖
- 修改前先读完整上下文
- 新增模块必须职责单一
- 不允许 copy-paste 式扩张
- 关键业务函数必须有 docstring
- 中文注释优先
- 不得把“评估”伪装成“执行完成”

---

## 10. 开始执行

现在请按以下顺序行动：

1. 读取 `rebuild/audit/phase3_final.md`
2. 建立当前任务清单
3. 从 M1 / T01 开始直接实施
4. 做完一批即验证
5. 无阻断则继续推进到下一批

**默认继续执行，不要先征求许可。**
