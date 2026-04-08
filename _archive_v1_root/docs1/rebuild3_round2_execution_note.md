# rebuild3 第二轮主修复与彻底复评执行说明

## 这轮工作的定位

这轮不再是普通的页面修补，而是两段式工作：

1. 先修正已经确认的严重偏差
2. 再基于新的基线，重新发起一次彻底深度评估

上一轮的问题已经证明：

- 页面能打开，不代表页面主语正确
- 接口有值，不代表字段口径正确
- 有 fallback，不代表真实数据链路已经落地
- UI_v2 设计对齐过，不代表底层仍然遵守冻结原始文档

因此，本轮必须同时看 4 层：

- 冻结原始文档
- UI_v2 最终设计
- 派生 prompt / 审计 / 修订文档
- 当前代码、API、SQL、真实数据

## 真相源优先级

### Tier 0：冻结原始文档
- `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`
- `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`
- `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`

### Tier 1：UI_v2 人类最终对齐设计
- `rebuild3/docs/UI_v2/design_notes.md`
- `rebuild3/docs/UI_v2/pages/*.html`
- `rebuild3/docs/UI_v2/pages/*_doc.md`

### Tier 2：派生实施与修订文档
- `rebuild3/docs/04*.md`
- `rebuild3/docs/ui_restructure_prompt.md`
- `rebuild3/docs/ui_restructure_audit_prompt.md`
- `rebuild3/docs/UI_v2/audit_*.md`
- `rebuild3/docs/Docs/*.md`
- `rebuild3/docs/api_models.md`
- `rebuild3/docs/param_matrix.md`
- `rebuild3/docs/ui_final_rectification_report.md`
- `docs1/*.md`

### Tier 3：当前实现
- 前端页面、组件、样式
- FastAPI 路由、读模型、缓存
- SQL schema / procedure / runner
- PostgreSQL 真实数据

规则：

- 页面设计语义优先参考 UI_v2
- 底层业务与数据口径优先参考 Tier 0 冻结文档
- 当前代码只能被审，不能反推设计

## 本轮主修复目标

### P0：时间快照语义与数据链路
- `/flow/snapshot` 必须回到“初始化后 + 时间点 A + 时间点 B”
- 不能再是 `sample / full / baseline` 的伪时间对照
- 页面必须区分：
  - 场景选择
  - 场景内时间点选择
- 两套初始化场景必须是一等公民、可被明确选择

### P1：画像页资格列纠偏
- LAC 只表达 `anchorable`
- BS / Cell 表达 `anchorable + baseline_eligible`
- 不能再因共享组件抹平页面差异
- 不能再出现窄列竖排或错误换行

### P1：真实时间快照能力落地
- `run / batch / batch_snapshot` 必须承担真实时间点语义
- 初始化与 2 小时增量必须能形成完整时间线
- smoke 通过后直接后台跑两套长时场景，不等待跑完再继续前端/API修复

### P1：为彻底复评建立正式基线
- 新的深度复评 Prompt 必须以冻结原始文档开头
- 必须有分阶段任务
- 每个阶段都必须有检查点与产物
- 必须产出字段、边界、页面主语、scenario/timepoint 的基线表

## 本轮数据场景要求

为了保证后续联调与复评使用的是真实时间数据，而不是伪造对照，默认使用两套初始化场景：

### 场景 A
- `1 天初始化`
- 后续 `每 2 小时` 一个 rolling snapshot

### 场景 B
- `2 天初始化`
- 后续 `每 2 小时` 一个 rolling snapshot

验收要求：

- 两套场景都写入 `rebuild3_meta.run`
- 各自批次写入 `rebuild3_meta.batch`
- 各批次快照写入 `rebuild3_meta.batch_snapshot`
- UI 能明确切换场景，而不是只切换时间点

## 重跑策略

长时数据重跑不阻塞本轮开发：

1. 先做 SQL / procedure / runner smoke 验证
2. smoke 通过后立刻启动长时场景
3. 长任务在后台继续跑
4. 主线程继续修前端/API/文档
5. 待长任务形成足够时间点后，再做真实场景联调与彻底复评

具体执行细节见：
- `docs1/rebuild3_snapshot_rerun_plan.md`

## 彻底复评的执行方式

彻底复评不再采用“看几个页面 + 看几个接口”的方式，而采用分阶段基线法：

1. 资料盘点与真相源分级
2. 原始文档与 UI_v2 设计对齐
3. 数据流程与快照机制对齐
4. 页面语义逐页对齐
5. API / 字段 / 边界逐项对齐
6. 真实运行验证 + 性能 / 代码规模检查
7. 偏差登记与实施优先级输出

正式 Prompt 见：
- `docs1/rebuild3_round2_reaudit_prompt.md`

## 本轮之后的验收口径

本轮之后，所有页面与 API 都按以下规则验收：

1. 页面回答的问题必须和设计一致
2. 页面背后的业务口径必须和冻结原始文档一致
3. 字段必须能追到真实来源表 / 视图 / 过程
4. scenario 与 timepoint 必须语义清楚，不能混用
5. fallback 必须被明确标识，不能冒充正式数据
6. 性能优化不能改变页面主语或字段定义
7. 大文件如果已经影响理解、联调或后续修复，必须拆分
