# rebuild3 纠偏审计

> 目的：基于当前目录与 `04e` 正式重构流程，定位本轮开发为何跑偏，判断当前成果哪些可保留、哪些必须重做，并为下一轮 UI-first 正式重构提供明确边界。

## 1. 审计结论

当前问题不是单一的 UI 偏差，而是 **任务构建阶段就发生了范围收缩和门禁误判**，导致后续实现偏离了 `UI_v2` 作为正式页面基线的要求。

简化结论如下：

1. 数据验证主线已有较多可保留成果：独立 schema、样本切片、样本双跑、样本偏差评估、全量运行、全量偏差评估均已形成产物。
2. 但 `04e` 要求的“正式系统交付”并未完成；当前状态不能视为“只差 UI”。
3. 最严重的偏差不是样式问题，而是：
   - `UI_v2` 没被当作强约束页面体系来实现
   - 启动器没有真正落地
   - 多个正式 API / 读模型域仍是占位骨架
   - 当前前端更像一个独立 spike，而不是接入既有 `UI_v2` 体系的正式实现
4. 下一轮必须以 **UI-first + 页面级验收 + 启动可运行 + 完成后归档本轮偏航文件** 为主线重新推进。

---

## 2. `04e` 的原始要求与当前偏差

### 2.1 原始要求

`04e` 明确要求：

- 业务语义、状态枚举、资格原则，以冻结文档为准
- 页面结构、页面边界、栏目组织，以 `UI_v2` 修复稿为准
- 在 Gate A / B 完成后，再推进实现
- 任务书必须覆盖 schema、后端编排、读模型/API、前端页面、验证/对比
- 前端页面不是附属项，而是正式交付域
- `launcher/` 是正式目录的一部分，不是可选占位目录

关键依据：

- `docs/rebuild3/04e_prompt_开发实施_正式重构流程版.md:49`
- `docs/rebuild3/04e_prompt_开发实施_正式重构流程版.md:83`
- `docs/rebuild3/04e_prompt_开发实施_正式重构流程版.md:181`
- `docs/rebuild3/04e_prompt_开发实施_正式重构流程版.md:241`

### 2.2 当前偏差

#### 偏差 A：任务书被缩成“样本链路优先版”

当前 `rebuild3/docs/impl_plan.md` 明确写了“当前版本聚焦样本阶段 Gate A-E；Gate F/G 在样本确认通过后展开”，并且前端只保留了最小 scaffold，读模型只保留了最小骨架。

这导致：

- 任务域覆盖不足
- UI 页面实现没有被当作 Gate B 之后的正式工作域
- 后续开发自然会把注意力集中到数据链路，而不是整套系统交付

依据：

- `rebuild3/docs/impl_plan.md:3`
- `rebuild3/docs/impl_plan.md:64`
- `rebuild3/docs/impl_plan.md:75`

#### 偏差 B：Gate A 被误判为“已完成”

虽然做了文档对齐和数据对齐，但没有把 `UI_v2/pages/*.html` 和 `*_doc.md` 逐页转成正式实现约束，也没有完成页面-路由-API-读模型映射矩阵。

结果是：

- 后续实现虽然参考了 `03/04/11` 页面语义
- 但并没有沿用 `UI_v2` 的页面体系、导航关系、启动方式、页面群结构
- 最终产物被感知为“另一套新 UI”

#### 偏差 C：启动器没有落地

当前 `rebuild3/launcher/README.md` 仍然是占位说明，无法支撑用户独立启动系统验证。

这直接违反了“用户可运行验证”的基本交付预期。

依据：

- `rebuild3/launcher/README.md:1`
- `rebuild3/docs/UI_v2/index.html:72`
- `rebuild3/docs/UI_v2/launcher/launcher.html`

#### 偏差 D：正式 API 域未闭合

虽然 `object.py` 已经有较多实现，但 `run.py`、`compare.py`、`governance.py` 仍是占位返回；而 `increment/`、`baseline/`、`governance/` SQL 目录也仍为空。

这说明当前不是“完整系统只剩 UI 没完成”，而是多个正式域仍未闭环。

依据：

- `rebuild3/backend/app/api/run.py:1`
- `rebuild3/backend/app/api/compare.py:1`
- `rebuild3/backend/app/api/governance.py:1`
- `rebuild3/backend/sql/increment/`
- `rebuild3/backend/sql/baseline/`
- `rebuild3/backend/sql/governance/`

#### 偏差 E：本轮前端属于 spike，不属于正式实现

当前 `rebuild3/frontend/src/` 已新增了新的路由、页面和样式体系，但它没有和 `UI_v2` 的正式导航、启动器、页面全集保持一致，因此应定性为：

- 可参考的实现性探索
- 不可直接视为正式页面交付

---

## 3. 当前成果分类

### 3.1 建议保留的成果（作为下一轮输入）

这些产物有较高保留价值，不应因 UI 跑偏而整体废弃：

- 目录与文档迁移结果：`rebuild3/docs/`
- 配置文件：
  - `rebuild3/config/thresholds.yaml`
  - `rebuild3/config/versions.yaml`
  - `rebuild3/config/services.yaml`
  - `rebuild3/config/compare_rules.yaml`
- schema / SQL / 脚本：
  - `rebuild3/backend/sql/schema/001_foundation.sql`
  - `rebuild3/backend/sql/init/001_sample_extract.sql`
  - `rebuild3/backend/sql/init/002_rebuild2_sample_eval.sql`
  - `rebuild3/backend/sql/govern/001_rebuild3_sample_pipeline.sql`
  - `rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql`
  - `rebuild3/backend/sql/compare/002_prepare_full_compare.sql`
  - `rebuild3/backend/scripts/run_sample_pipeline.py`
  - `rebuild3/backend/scripts/run_full_pipeline.py`
- 报告与记录：
  - `rebuild3/docs/sample_scope.md`
  - `rebuild3/docs/sample_run_report.md`
  - `rebuild3/docs/sample_compare_report.md`
  - `rebuild3/docs/full_run_report.md`
  - `rebuild3/docs/full_compare_report.md`
  - `rebuild3/.logs/*`

### 3.2 建议重新审计后决定是否保留的成果

这些产物可能有价值，但不能未经审计直接视为正式版：

- `rebuild3/backend/app/api/object.py`
  - 其 Cell 读模型、规则审计、compare 上下文可以作为参考
  - 但是否适配正式 `UI_v2` 页面体系，需要重新映射后确认

### 3.3 明确需要重做或重构的成果

这些部分在下一轮必须按 UI-first 方式重构：

- `rebuild3/frontend/` 下当前这套 spike 页面结构
- 正式 launcher 启动链路
- 页面-路由-数据-组件的整体映射
- `run` / `compare` / `governance` 正式 API
- `UI_v2` 其余页面的正式实现与验收

---

## 4. 是否只是 UI 问题？

结论：**不是。**

更准确地说：

1. 数据验证主线已经形成较强成果，不能简单视为失败
2. 但“正式系统交付”明显未完成，也不能说只剩 UI 样式问题
3. 当前属于：
   - 数据主链路部分可保留
   - 正式产品化实现需要重新组织任务并补齐多个域

因此下一轮不能只说“把 UI 调整一下”，而必须：

- 重新构建完整任务书
- 让 UI 成为主线验收对象
- 重新检查所有不可见域是否满足 `04e`

---

## 5. 下一轮必须执行的纠偏动作

### 5.1 先做当前目录审计，不直接写代码

必须先输出一份新的目录审计与分类结果，至少分类为：

- 保留并复用
- 保留但待重审
- 必须重做
- 实现完成后归档
- 生成产物，不纳入归档

### 5.2 先做 `UI_v2` 页面映射矩阵

必须把以下内容做成明确矩阵：

- `UI_v2` 页面 -> 正式路由
- 页面 -> 读模型/API
- 页面 -> 数据表 / 汇总表
- 页面 -> 共享组件
- 页面 -> 当前实现状态（未开始 / 部分完成 / 已完成）

### 5.3 启动器必须前置

下一轮必须把“用户可独立运行”作为正式门禁，至少交付：

- 启动器页面入口
- 前后端启动脚本或一键命令
- README 启动说明
- 运行状态检查

### 5.4 页面验收必须逐页进行

至少针对以下正式页面逐页验收：

- 启动器
- 流转总览
- 运行 / 批次中心
- 对象浏览
- 对象详情
- 等待 / 观察工作台
- 异常工作台
- 基线 / 画像
- 验证 / 对照
- LAC / BS / Cell 画像
- 初始化
- 基础数据治理

### 5.5 本轮 spike 文件必须在新实现通过后归档

但注意：

- 不允许现在立刻清空
- 必须等替代实现通过页面验收和可运行验收之后，再归档
- 归档时要附说明，避免未来目录混乱

---

## 6. 归档原则

归档原则如下：

1. 只归档本轮跑偏的实现性 spike，不归档已确认有效的数据报告与 SQL 产物
2. 归档动作发生在“新实现通过验收之后”，不能提前破坏当前参考材料
3. 归档目录必须具备：
   - 时间戳
   - 原因说明
   - 来源说明
   - 被哪个新实现替代
4. `node_modules/`、`dist/`、Vite 临时缓存不做历史归档；它们属于可再生构建产物，应通过清理/重建处理

具体文件清单见：

- `rebuild3/docs/archive_manifest_20260404_ui_spike.md`

---

## 7. 下一轮的总目标

下一轮对话的目标不再是“继续补当前代码”，而是：

1. 基于当前目录重建一份 UI-first 的完整任务书
2. 重新审计哪些部分已经满足、哪些部分未满足 `04e`
3. 以 `UI_v2` 为唯一正式页面基线重新推进开发
4. 在开发完成后，把本轮跑偏的 spike 文件归档，保持目录整洁

