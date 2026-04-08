# Prompt E：rebuild3 开发实施（正式重构流程版）

> 使用场景：UI v2 已完成审计、修订并经人工确认后，开启新的正式开发对话时使用。  
> 适用目标：不是只输出计划，而是按“样本先行、双跑对比、通过后全量”的正式重构流程推进。  
> 与 `04b_prompt_开发实施.md` 的关系：本文件是在其基础上的正式收敛版。进入下一阶段时，优先使用本文件。

---

## 你的角色

你现在扮演 **首席架构师 + 技术负责人 + 全栈实现负责人 + 验证负责人**。

你不是来做一轮松散尝试，而是来按正式重构流程完成 rebuild3：

1. 搭建目录、配置、独立 schema 与项目骨架
2. 完成 rebuild3 的首轮实现
3. 先抽取少量样本数据
4. 在同一份样本上分别跑 `rebuild2` 与 `rebuild3`
5. 输出偏差评估
6. 只有样本跑通且偏差可解释后，才允许进入全量
7. 全量完成后，再输出一次全量偏差评估与收敛结论

---

## 必须先读取的输入材料

以下文档已存在，请直接读取，不要等待用户补充：

1. `docs/rebuild3/01_rebuild3_说明_最终冻结版.md`
2. `docs/rebuild3/02_rebuild3_预实施任务书_最终冻结版.md`
3. `docs/rebuild3/03_rebuild3_技术栈要求_最终冻结版.md`
4. `docs/rebuild3/UI_v2/` 下全部设计产物
5. `docs/rebuild3/UI_v2/design_notes.md`
6. `docs/rebuild3/UI_v2/pages/*.html`
7. `docs/rebuild3/UI_v2/pages/*_doc.md`
8. `docs/rebuild3/UI_v2/audit_deviation_report.md`
9. `docs/rebuild3/UI_v2/audit_decisions_required.md`
10. `docs/rebuild3/Docs/UI_v2_审计后修改执行清单.md`
11. `docs/rebuild3/Docs/rebuild3_开发文档最终修订补丁.md`

> 注意：在第 0 步完成目录迁移前，从 `docs/rebuild3/` 读取；迁移后统一改为 `rebuild3/docs/`。

---

## 正式重构流程的硬性原则

以下原则不可违反：

### 1. UI 与业务语义来源

1. 业务语义、状态枚举、资格原则，以 01/02/03 冻结文档为准
2. 页面结构、页面边界、栏目组织，以 `UI_v2` 修复稿为准
3. 命名归一化、开发级补丁、基础数据治理补充，以 `rebuild3_开发文档最终修订补丁.md` 为准

### 2. 数据库独立 schema 原则

1. rebuild3 产生的所有新数据，必须写入**独立 schema**
2. 推荐正式 schema：
   - `rebuild3`
   - `rebuild3_meta`
3. 如需把样本验证与正式全量彻底隔离，可增加：
   - `rebuild3_sample`
   - `rebuild3_sample_meta`
4. `rebuild2 / rebuild2_meta / legacy` 一律只读，不得改写

### 3. 样本先行原则

1. **不允许一上来直接跑全量**
2. 必须先抽取少量样本数据
3. 必须在**同一份样本**上分别跑 `rebuild2` 与 `rebuild3`
4. 必须先输出样本偏差评估
5. 只有样本阶段通过，才能进入全量

### 4. 对比与偏差评估原则

1. 样本阶段必须出一份对比报告
2. 全量阶段必须再出一份对比报告
3. 偏差不能只报数字，必须说明：
   - 差异是什么
   - 差异是预期语义变化、参数差异、样本偏差，还是实现问题
   - 是否阻塞进入下一阶段

### 5. 实施门禁原则

以下阶段门必须显式通过：

- Gate A：文档与 UI 对齐完成
- Gate B：目录、独立 schema、配置与项目骨架完成
- Gate C：样本数据集定义完成
- Gate D：rebuild2 / rebuild3 样本双跑完成
- Gate E：样本偏差评估通过
- Gate F：全量运行完成
- Gate G：全量偏差评估完成

如果 Gate D 或 Gate E 未通过，**禁止进入全量**。

---

## 第 0 步：建立项目目录结构与文档迁移

如果项目根目录下还没有 `rebuild3/`，先创建。

目录结构至少为：

```text
rebuild3/
├── docs/
│   ├── UI/                      # 旧版 UI 产物（保留只读）
│   ├── UI_v2/                   # 当前确认版 UI
│   └── Docs/                    # 审计、修订清单、开发补丁
├── backend/
│   ├── app/
│   ├── sql/
│   │   ├── schema/
│   │   ├── init/
│   │   ├── increment/
│   │   ├── govern/
│   │   ├── baseline/
│   │   ├── compare/
│   │   └── governance/
│   ├── scripts/
│   └── requirements.txt
├── frontend/
├── launcher/
├── config/
└── README.md
```

### 0.1 迁移文档

把 `docs/rebuild3/*` 复制到 `rebuild3/docs/`。

迁移后至少验证：

- `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`
- `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`
- `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`
- `rebuild3/docs/UI_v2/`
- `rebuild3/docs/Docs/UI_v2_审计后修改执行清单.md`
- `rebuild3/docs/Docs/rebuild3_开发文档最终修订补丁.md`

### 0.2 初始化配置

在 `rebuild3/config/` 下至少创建：

- `thresholds.yaml`
- `versions.yaml`
- `services.yaml`
- `compare_rules.yaml`

其中：

**`compare_rules.yaml`** 至少包含：
- 样本阶段对比维度
- 全量阶段对比维度
- 可接受偏差阈值
- 偏差严重度分级规则
- 是否阻塞进入下一阶段的判断规则

---

## 第 1 步：实施前对齐（Gate A）

在写业务实现前，先输出一份**实施前对齐结果**，至少回答：

1. 你如何理解 rebuild3 的业务主语
2. 当前 UI v2 与冻结文档是否还有残余冲突
3. 哪些命名需要在实现阶段统一归一化
4. 哪些参数应该进入 `config/`
5. 哪些数据依赖来自 rebuild2 / rebuild2_meta / legacy
6. 后续样本验证如何切片，才能覆盖主要治理路径

输出文件写入：

- `rebuild3/docs/impl_alignment.md`

如果这里发现重大冲突，先收敛，再继续。

---

## 第 2 步：最终实施任务书（Gate B 的一部分）

输出一份真正可执行的最终实施任务书，每个任务必须包含：

- 输入
- 输出
- 依赖
- 验收标准
- 风险
- 回归影响
- 推荐顺序

输出文件写入：

- `rebuild3/docs/impl_plan.md`

### 必须覆盖的任务域

#### A. schema 与元数据

- `rebuild3 / rebuild3_meta` schema
- 如需样本隔离，`rebuild3_sample / rebuild3_sample_meta`
- `run / batch / baseline / version`
- `obj_cell / obj_bs / obj_lac`
- `obj_state_history / obj_relation_history`
- `fact_standardized`
- `fact_governed / fact_pending_observation / fact_pending_issue / fact_rejected`
- `batch_snapshot`
- `batch_flow_summary / batch_decision_summary / batch_anomaly_summary / batch_baseline_refresh_log`
- 基础数据治理元数据表：
  - `asset_table_catalog`
  - `asset_field_catalog`
  - `asset_usage_map`
  - `asset_migration_decision`

#### B. 后端与编排

- 源适配
- 标准化事件层
- 初始化链路
- 增量链路
- 等待/观察推进
- Cell 晋升与级联
- 异常检测
- baseline / profile
- 对比引擎
- 偏差评估输出

#### C. 读模型与 API

- 运行/批次中心
- 对象浏览 / 对象详情
- 等待/观察工作台
- 异常工作台
- baseline / profile
- 验证/对照
- 基础数据治理

#### D. 前端

- Vue 3 + TypeScript + Vite 初始化
- 页面级实现（以 `UI_v2` 为准）
- `VersionContext` 共享组件
- 四分流与资格状态的统一组件
- 基础数据治理页面

#### E. 验证与对比

- 样本切片定义
- rebuild2 样本跑批
- rebuild3 样本跑批
- 样本对比
- 全量跑批
- 全量对比

---

## 第 3 步：先完成最小可运行实现，不直接跑全量

你必须先完成最小可运行实现，再进入样本阶段。

最小可运行闭环至少包括：

1. 标准化事件输入
2. 对象层最小闭环
3. 四分流最小闭环
4. run / batch / baseline 最小元数据
5. 关键读模型最小接口
6. 基础数据治理最小元数据接口

### 注意

这一步的目标不是“所有细节都完美”，而是为了让样本阶段可真实跑通，而不是只做静态 mock。

---

## 第 4 步：定义样本数据集（Gate C）

这是正式门禁，必须单独完成，不得跳过。

### 4.1 样本数据集要求

样本必须是**少量但有代表性**的数据，不是随便随机抽几条。

样本应尽量覆盖：

- 正常 active 对象
- waiting / observing 候选对象
- `collision_suspect`
- `collision_confirmed`
- `dynamic`
- `migration_suspect`（如样本中可覆盖）
- `fact_rejected`
- 记录级异常（如 `single_large`、`normal_spread`）
- baseline 相关对象

### 4.2 样本切片原则

切片时至少明确：

- 时间窗口
- 运营商范围
- 制式范围
- LAC / BS / Cell 范围
- 目标样本量级
- 预期覆盖哪些治理场景

### 4.3 样本输出

输出文件写入：

- `rebuild3/docs/sample_scope.md`

文件中必须写清楚：

- 为什么这样切
- 样本覆盖了哪些场景
- 哪些场景样本仍未覆盖
- 是否需要补充第二批样本

---

## 第 5 步：在同一份样本上双跑 rebuild2 与 rebuild3（Gate D）

这是本 Prompt 最关键的正式约束之一。

### 5.1 rebuild2 样本跑批

你必须在样本数据上重新跑 `rebuild2`，而不是只拿历史结果想当然对照。

要求：

- 明确样本输入来源
- 明确 rebuild2 使用了哪些脚本 / SQL / API 链路
- 明确 rebuild2 样本输出落在哪里

### 5.2 rebuild3 样本跑批

你必须在**同一份样本**上跑 `rebuild3`。

要求：

- 输入契约与 rebuild2 样本保持一致
- 输出落在独立 schema
- 显式记录 `run_id / batch_id / contract_version / rule_set_version / baseline_version`

### 5.3 样本运行记录

输出文件写入：

- `rebuild3/docs/sample_run_report.md`

报告中至少包含：

- 样本输入范围
- rebuild2 样本运行步骤
- rebuild3 样本运行步骤
- 成功/失败情况
- 中间产物位置

---

## 第 6 步：样本偏差评估（Gate E）

样本双跑完成后，必须输出正式偏差报告。

### 6.1 样本对比维度至少包括

1. 对象数量：
   - Cell / BS / LAC
2. 状态分布：
   - `lifecycle_state`
   - `health_state`
3. 资格分布：
   - `anchorable`
   - `baseline_eligible`
4. 四分流分布：
   - `fact_governed`
   - `fact_pending_observation`
   - `fact_pending_issue`
   - `fact_rejected`
5. 异常分布：
   - 对象级异常
   - 记录级异常
6. 画像与空间指标：
   - 质心
   - P50 / P90
   - GPS 原始率 / 信号原始率
7. baseline 相关差异：
   - 触发条件
   - 版本结果

### 6.2 每个差异必须分类

每个差异都要判断属于哪类：

- A. 预期语义差异（rebuild3 设计本来就不同）
- B. 参数差异
- C. 样本噪声 / 输入差异
- D. 实现缺陷
- E. 未确认问题

### 6.3 样本阶段通过条件

只有满足以下条件，才允许进入全量：

1. 样本双跑均成功
2. 主要对象、事实、状态、资格分布可解释
3. 无 P0 / P1 级实现缺陷未处理
4. 偏差报告给出明确结论：可进入全量

### 6.4 样本偏差报告输出

输出文件写入：

- `rebuild3/docs/sample_compare_report.md`

如果未通过 Gate E：

- 停止进入全量
- 输出阻塞项与修正计划

---

## 第 7 步：只有样本通过后，才允许进入全量（Gate F）

### 7.1 全量运行前检查

进入全量前，必须再次确认：

- 独立 schema 已就绪
- 样本门禁已通过
- 关键索引与分区已建立
- 必要的幂等与回滚策略已具备

### 7.2 全量运行要求

全量阶段至少完成：

- 初始化全量或所需历史回灌
- 增量链路全量跑通
- 基线 / profile 生成
- 核心读模型生成
- UI 对应数据可读取

### 7.3 全量运行记录

输出文件写入：

- `rebuild3/docs/full_run_report.md`

---

## 第 8 步：全量偏差评估（Gate G）

全量完成后，必须再做一次偏差评估。

### 8.1 全量对比来源

优先级如下：

1. 若可复用当前有效的 rebuild2 全量结果，优先作为对照基线
2. 若现有 rebuild2 全量结果不足以支撑关键对比，再补跑必要的 rebuild2 全量链路

### 8.2 全量偏差评估内容

至少包括：

- 对象总量与状态分布
- 四分流总量与比例
- 关键异常分布
- baseline 版本结果
- 画像关键统计
- 热层稳定性
- 关键页面读模型结果与旧系统/旧样本的一致性

### 8.3 全量偏差报告输出

输出文件写入：

- `rebuild3/docs/full_compare_report.md`

结论必须明确给出：

- 可以接受的偏差
- 必须继续修正的偏差
- 是否满足首轮正式切换前提

---

## 第 9 步：持续维护的文档

开发过程中持续维护以下文档：

- `rebuild3/docs/impl_alignment.md`
- `rebuild3/docs/impl_plan.md`
- `rebuild3/docs/param_matrix.md`
- `rebuild3/docs/api_models.md`
- `rebuild3/docs/sample_scope.md`
- `rebuild3/docs/sample_run_report.md`
- `rebuild3/docs/sample_compare_report.md`
- `rebuild3/docs/full_run_report.md`
- `rebuild3/docs/full_compare_report.md`
- `rebuild3/docs/replay_log.md`
- `rebuild3/docs/issues.md`

---

## 实现约束（硬性约束）

### 状态与资格

- 不允许把生命周期和健康状态混成一个枚举
- 不允许省略 `anchorable` / `baseline_eligible`
- `watch` 只允许做 UI 派生状态

### 事实分层

- 不允许只落一张总事实表
- 必须保留：
  - `fact_standardized`
  - `fact_governed`
  - `fact_pending_observation`
  - `fact_pending_issue`
  - `fact_rejected`

### 命名统一

- 不允许继续使用 `pending_obs` / `fact_pending_obs`
- 不允许继续使用 `rule_version`
- 必须统一为：
  - `fact_pending_observation`
  - `rule_set_version`

### 独立 schema

- 所有 rebuild3 数据都在独立 schema 中完成
- 不允许把 rebuild3 中间结果写入 `rebuild2*`

### 前端

- 不允许退回旧 Step 页面心智
- 不允许在没有读模型的情况下直接拼底层表
- 核心页面必须统一接入版本上下文条
- `基础数据治理` 是正式页面，不允许在首轮实现中删除

### 阶段门禁

- 样本双跑和样本偏差评估未通过，不允许进入全量

---

## 你的输出风格要求

1. 先对齐，再计划，再实现，再验证
2. 不要只给抽象建议，要写成可执行任务和实际推进步骤
3. 不要把“样本对比”写成附加项，它是主流程门禁
4. 不要把“独立 schema”写成建议项，它是硬约束
5. 所有偏差报告都必须给出结论，不允许只堆数字

---

> 完成本 Prompt 后，rebuild3 应达到以下状态：  
> - 项目目录与独立 schema 完整  
> - 首轮实现已可真实跑通  
> - 样本数据上已完成 rebuild2 / rebuild3 双跑与偏差评估  
> - 样本通过后完成全量运行  
> - 全量偏差评估已形成正式结论
