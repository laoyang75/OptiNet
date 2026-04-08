# rebuild3 开发文档最终修订补丁

> 状态：基于 UI v2 修复稿的最终开发输入  
> 适用对象：后续开发 agent、架构整理者、实施任务拆解者  
> 作用：不改动 01/02/03 三份最终冻结文档的业务冻结地位，而是在“UI 已完成修复”之后，把可直接进入实现的最终补充约束补齐。

---

## 1. 本补丁的定位与优先级

本补丁用于连接三类输入：

1. 冻结业务语义  
   - `docs/rebuild3/01_rebuild3_说明_最终冻结版.md`
   - `docs/rebuild3/02_rebuild3_预实施任务书_最终冻结版.md`
   - `docs/rebuild3/03_rebuild3_技术栈要求_最终冻结版.md`

2. 已修复的 UI v2 方案  
   - `docs/rebuild3/UI_v2/design_notes.md`
   - `docs/rebuild3/UI_v2/pages/*.html`
   - `docs/rebuild3/UI_v2/pages/*_doc.md`

3. 审计与修订过程产物  
   - `docs/rebuild3/UI_v2/audit_deviation_report.md`
   - `docs/rebuild3/UI_v2/audit_decisions_required.md`
   - `docs/rebuild3/Docs/UI_v2_审计后修改执行清单.md`

### 优先级规则

开发阶段遇到冲突时，按以下顺序处理：

1. **业务语义与状态枚举**：以 01/02/03 冻结文档为准
2. **页面结构、栏目组织、页面边界**：以当前 `UI_v2` 修复稿为准
3. **命名统一、元数据补充、实现级补丁**：以本补丁为准

说明：
- 本补丁允许覆盖 UI 原型中残留的少量命名不一致；
- 但不允许推翻冻结文档中已经冻结的业务语义。

---

## 2. 当前评估结论：可以进入开发文档最终修订

对照 `docs/rebuild3/Docs/UI_v2_审计后修改执行清单.md` 复核后，结论是：

- UI v2 已达到“**基本符合，可进入开发文档最终修订**”的门槛；
- 主体方向已收敛：三层资格、异常双视角、基线时序、LAC/BS/Cell 画像主状态、新增“基础数据治理”栏目都已进入现稿；
- 仍有少量残余项不建议回到 UI 再做一轮大改，而应直接作为**开发阶段强制归一化要求**落入实现与文档。

### 2.1 本轮确认通过的重点项

- 已新增“基础数据治理”栏目与 `13_data_governance` 页面
- 等待/观察页已改为三层资格推进
- 异常页已补入记录级异常 / 结构不合规视角
- 基线页已显式写出生效时序
- LAC 页已把“覆盖不足”降为区域质量标签
- 验证页已补入“热层稳定性”

### 2.2 开发阶段必须顺手归一化的残余项

以下残余项不阻塞进入开发，但实现时必须统一修正：

#### R1. 仍存在 `pending_obs` 缩写残留

残留示例：

- `docs/rebuild3/UI_v2/design_notes.md:334`
- `docs/rebuild3/UI_v2/pages/02_run_batch_center_doc.md:38`
- `docs/rebuild3/UI_v2/components/shared_components.html:107`

开发阶段要求：

- 一律统一为 `fact_pending_observation`
- 技术字段、读模型、CSS 语义类名、组件 props、API 字段都不要再出现 `pending_obs`

#### R2. 初始化文档示例仍残留 `rule_version`

残留示例：

- `docs/rebuild3/UI_v2/pages/12_initialization_doc.md:129`
- `docs/rebuild3/UI_v2/pages/12_initialization_doc.md:135`

开发阶段要求：

- 一律统一为 `rule_set_version`
- 禁止实现层同时存在 `rule_version` 和 `rule_set_version`

#### R3. 版本上下文条尚未在全部核心页面落齐

已具备上下文条的页面：

- `docs/rebuild3/UI_v2/pages/01_flow_overview.html`
- `docs/rebuild3/UI_v2/pages/02_run_batch_center.html`
- `docs/rebuild3/UI_v2/pages/07_baseline_profile.html`
- `docs/rebuild3/UI_v2/pages/12_initialization.html`

仍需在实现阶段统一补齐的核心页面：

- `docs/rebuild3/UI_v2/pages/03_objects.html`
- `docs/rebuild3/UI_v2/pages/04_object_detail.html`
- `docs/rebuild3/UI_v2/pages/05_observation_workspace.html`
- `docs/rebuild3/UI_v2/pages/06_anomaly_workspace.html`
- `docs/rebuild3/UI_v2/pages/08_validation_compare.html`
- `docs/rebuild3/UI_v2/pages/09_lac_profile.html`
- `docs/rebuild3/UI_v2/pages/10_bs_profile.html`
- `docs/rebuild3/UI_v2/pages/11_cell_profile.html`

开发阶段要求：

- 将版本上下文条抽象为统一组件 `VersionContext`
- 作为前端实现强制项，而不是“看页面是否需要再决定”

---

## 3. 最终确认的页面范围

本轮 UI 确认后，rebuild3 前端页面范围冻结为以下集合：

### 主流程层

1. 流转总览
2. 流转快照
3. 运行/批次中心
4. 对象浏览
5. 对象详情
6. 等待/观察工作台
7. 异常工作台
8. 基线/画像

### 画像视角层

9. LAC 画像
10. BS 画像
11. Cell 画像

### 支撑治理层

12. 验证/对照
13. 初始化数据
14. 基础数据治理

### 独立页面

15. 启动器

说明：
- “基础数据治理”已正式进入首轮开发范围，不再视为可选页面；
- 它虽然不属于主流程首页叙事，但属于迁移与实施的必须支撑模块。

---

## 4. 最终确认的实现级统一规则

以下规则进入开发时不再讨论，直接执行。

### 4.1 生命周期与健康状态

统一使用：

- `lifecycle_state = waiting / observing / active / dormant / retired / rejected`
- `health_state = healthy / insufficient / gps_bias / collision_suspect / collision_confirmed / dynamic / migration_suspect`

约束：

- 不允许页面自行发明新的主状态；
- `watch` 只允许做 UI 派生态。

### 4.2 三层资格

对象与工作台必须同时能回答：

1. 存在资格
2. `anchorable`
3. `baseline_eligible`

约束：

- 等待/观察页的进度表达必须服务于这三层；
- 不允许把单一阈值表达成“对象是否晋升”的总代替。

### 4.3 四分流命名

统一使用：

- `fact_governed`
- `fact_pending_observation`
- `fact_pending_issue`
- `fact_rejected`

约束：

- 文档、DDL、API、前端类型、读模型、组件命名全部一致；
- 页面展示可用中文说明，但英文技术名必须保持以上全称。

### 4.4 旧画像分类的角色

rebuild2 遗留字段如：

- `classification_v2`
- `gps_confidence`
- `signal_confidence`

只能作为：

- 画像解释信息
- 迁移参考信息
- 旧系统对照字段

不能作为：

- 对象主状态
- 生命周期替代物
- 锚点资格或 baseline 资格的直接替代字段

### 4.5 baseline 时序语义

统一坚持：

- 当前批次只读取上一版冻结 baseline
- 本批次结束后如触发刷新，新 baseline 仅供下一批次使用

约束：

- 这一原则既是后端判定约束，也是前端必须显式展示的上下文；
- 不允许页面或 API 给出“同批边判边刷”的暗示。

---

## 5. “基础数据治理”正式纳入首轮实施范围

这是本轮开发文档最终修订最重要的新增点之一。

### 5.1 页面目标冻结

`基础数据治理` 页面必须回答四类问题：

1. 系统有哪些字段
2. 系统有哪些表
3. 这些表/字段到底被谁在用
4. 每项资产未来是直接复用、重组迁移、仅参考还是可淘汰

### 5.2 页面结构冻结

首轮实现按一个页面 + 四个 Tab：

1. 字段目录
2. 表目录
3. 实际使用
4. 迁移状态

### 5.3 后端支持不再视为“纯 mock”

前端虽然可以先使用 mock，但开发文档中必须正式落入以下读模型与元数据表设计。

---

## 6. 新增元数据与读模型要求

除冻结文档中已明确的 `run / batch / baseline / fact / obj_*` 体系外，开发阶段补充以下支撑对象。

### 6.1 批次快照与批次汇总

以下对象正式纳入首轮实施：

- `batch_snapshot`
- `batch_flow_summary`
- `batch_decision_summary`
- `batch_anomaly_summary`
- `batch_baseline_refresh_log`

用途：

- 支撑流转总览、流转快照、运行/批次中心、验证对照

### 6.2 基础数据治理元数据表

建议落在 `rebuild3_meta` schema 下，至少包含：

- `asset_table_catalog`
- `asset_field_catalog`
- `asset_usage_map`
- `asset_migration_decision`

建议职责：

#### `asset_table_catalog`

至少包含：

- `table_name`
- `table_schema`
- `table_type`
- `grain_desc`
- `primary_key_desc`
- `refresh_mode`
- `upstream_desc`
- `retention_policy`
- `owner_domain`
- `is_core`
- `status`

#### `asset_field_catalog`

至少包含：

- `table_name`
- `field_name`
- `field_label_cn`
- `layer_name`
- `data_type`
- `is_nullable`
- `is_core`
- `source_desc`
- `semantic_desc`
- `status`

#### `asset_usage_map`

至少包含：

- `asset_type`（table / field）
- `asset_name`
- `consumer_type`（ui_page / api / batch_job / script / validation）
- `consumer_name`
- `usage_role`（core / support / legacy / audit）
- `usage_desc`

#### `asset_migration_decision`

至少包含：

- `asset_type`
- `asset_name`
- `decision`（reuse / reshape / reference_only / retire）
- `target_asset`
- `decision_reason`
- `owner_note`

说明：
- 首轮可以人工维护这些表；
- 后续再考虑由 DDL/代码扫描自动补全，不作为首轮阻塞。

### 6.3 基础数据治理 API

首轮正式纳入：

- `GET /api/governance/overview`
- `GET /api/governance/fields`
- `GET /api/governance/tables`
- `GET /api/governance/usage/{asset_name}`
- `GET /api/governance/migration`

---

## 7. 对最终实施任务书的补丁要求

后续生成 `impl_plan.md` 时，必须把下面内容显式写进去。

### 7.1 数据库与元数据任务必须新增

新增任务：

- 基础数据治理元数据表设计与 DDL
- `batch_snapshot` 与批次汇总表设计
- 资产登记与资产使用关系初始化脚本

### 7.2 后端任务必须新增

新增任务：

- 资产目录读模型服务
- 资产使用关系读模型服务
- 批次快照写入服务
- 流转总览 / 流转快照专用汇总服务

### 7.3 前端任务必须新增

新增任务：

- `VersionContext` 共享组件
- `基础数据治理` 页面与四个 Tab
- 页面顶部统一版本上下文接入
- `batch_snapshot` 视图的数据接入

### 7.4 API / 类型任务必须新增

新增任务：

- 治理元数据 API 契约
- 版本上下文公共类型
- 四分流枚举公共类型
- 迁移状态枚举公共类型

---

## 8. 前端实现的统一补充规则

### 8.1 版本上下文组件

以下页面前端实现时必须接入统一 `VersionContext`：

- 流转总览
- 流转快照
- 运行/批次中心
- 对象浏览
- 对象详情
- 等待/观察工作台
- 异常工作台
- 基线/画像
- 验证/对照
- LAC/BS/Cell 画像
- 初始化数据

### 8.2 技术英文与中文说明

开发实现中允许保留必要英文技术字段，但要遵守：

- 面向业务展示时优先中文
- 必须出现英文技术名时，旁边要给中文解释或中文标签
- 不允许只给缩写、不做解释

说明：
- 这是开发与文档约束，不要求改动文件名
- 其目的是减少审阅和协作时的歧义

### 8.3 画像页主语

LAC / BS / Cell 画像页统一采用：

- 主状态 = `lifecycle_state + health_state + qualification`
- 参考信息 = rebuild2 遗留分类/可信度
- 质量画像 = 空间、样本、原始率、信号、质心差异

不允许反过来由旧分类决定页面主语。

---

## 9. 开发起步顺序修正

在原开发顺序上补充一个前置动作：

### Phase 0.5：开发级收敛与元数据底座

在正式写大规模业务实现前，先完成：

1. `UI_v2` 命名残留归一化（`pending_obs`、`rule_version` 等）
2. `VersionContext` 公共类型与共享组件定义
3. `batch_snapshot` 与批次汇总表 DDL
4. 基础数据治理元数据表 DDL
5. 治理元数据最小样本数据写入

完成后再进入：

- 标准化事件层
- 对象层
- 四分流
- 异常 / baseline / profile
- API / 前端实现

---

## 10. 结论

从当前状态看，rebuild3 已经具备进入开发文档最终修订和实施拆解的条件。

后续开发阶段应当把注意力集中在两件事上：

1. 不要再回到 UI 口径争论，而是按冻结语义 + UI_v2 修复稿 + 本补丁直接落实现
2. 把“基础数据治理”和“批次快照/版本上下文”视为首轮正式能力，而不是后补功能
