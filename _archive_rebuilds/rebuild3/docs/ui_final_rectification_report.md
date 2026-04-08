# rebuild3 UI 最终修复报告

**日期**: 2026-04-05  
**执行方式**: 文档审计 + 前后端联调 + Playwright 实页核查 + 代码修复 + 构建验证 + 性能测量/SQL 优化 + 代码规模审计 + docs 整理  
**执行范围**: `rebuild3/frontend`、`rebuild3/backend`、`rebuild3/docs`

---

## 一、执行结论

本轮按 `ui_restructure_audit_prompt.md` 的三层工作法完成了：

1. **第一层：功能审计与修复**
   - 13 个页面 + 1 个对象详情路由全部可正常加载。
   - 已知占位符页 `/flow/snapshot` 已替换为真实实现。
   - 前端引用但后端未返回的关键字段已补齐或加了 fallback。
   - 画像页、观察工作台、治理页、流转总览等多处真实数据/筛选/默认状态问题已修复。

2. **第二层：排版审计与修复**
   - 对照 `UI_v2` 设计稿与页面设计文档完成结构性修正。
   - 修复了移动端横向溢出，`390x844` 下主路由全部无页面级横向滚动。
   - 治理页、流转总览页补齐移动端布局适配，导航、流程图、治理分栏均可收敛到单列/双列安全布局。

3. **第三层：抛光与文档整理**
   - 按 Impeccable 的 `/audit`、`/arrange`、`/polish`、`/clarify` 思路完成最终检查。
   - 更新 `rebuild3/docs/README.md` 为当前索引。
   - 创建 `rebuild3/docs/archive/20260405_ui_reaudit/` 并归档旧中间产物。

当前结论：**前端与主要读接口已达到可交付状态，剩余风险主要在后端数据完整性与后续长期工程化收敛，而不是当前 UI 可用性或页面读性能。**

---

## 二、功能审计结果

### 2.1 页面状态总览

| 页面 | URL | 状态 | 结果说明 |
|---|---|---|---|
| 流转总览 | `/flow/overview` | ✅ 正常 | 真数据加载，流程图/问题入口/累计指标可用 |
| 流转快照 | `/flow/snapshot` | ✅ 正常 | 已从占位符改为真实快照页面 |
| 运行/批次中心 | `/runs` | ✅ 正常 | 批次列表与详情联动正常 |
| 对象浏览 | `/objects` | ✅ 正常 | 筛选、汇总卡片、详情跳转正常 |
| 对象详情 | `/objects/:type/:id` | ✅ 正常 | 通过真实对象路由核查通过 |
| 等待/观察工作台 | `/observation` | ✅ 正常 | 默认不再空白，卡片与趋势筛选可用 |
| 异常工作台 | `/anomalies` | ✅ 正常 | 双 Tab 与对象/记录明细字段正常 |
| 基线/画像 | `/baseline` | ✅ 正常 | 触发详情、质量信息、差异样本正常 |
| 验证/对照 | `/compare` | ✅ 正常 | 页面可用，当前仍依赖回退数据 |
| LAC 画像 | `/profiles/lac` | ✅ 正常 | 修复 `page_size` 参数后可正常加载 |
| BS 画像 | `/profiles/bs` | ✅ 正常 | 技术制式/资格筛选值已与后端对齐 |
| Cell 画像 | `/profiles/cell` | ✅ 正常 | 技术制式/资格筛选值已与后端对齐 |
| 初始化数据 | `/initialization` | ✅ 正常 | 读模型与状态展示正常 |
| 基础数据治理 | `/governance` | ✅ 正常 | 概览、字段/表/使用/迁移四视图可用 |

### 2.2 Playwright 逐页验证结果

使用 Playwright 对以下 14 个路由进行了真实页面校验：

- `/flow/overview`
- `/flow/snapshot`
- `/runs`
- `/objects`
- `/observation`
- `/anomalies`
- `/baseline`
- `/compare`
- `/profiles/lac`
- `/profiles/bs`
- `/profiles/cell`
- `/initialization`
- `/governance`
- `/objects/cell/cell|46000|5G|2097240|5751177217`

验证结果：

- 桌面端 `1440x900`：全部页面无 `.error-banner`，无永久 loading，均能完成渲染。
- 移动端 `390x844`：全部页面 `documentElement.scrollWidth === viewportWidth`，无页面级横向溢出。
- `/flow/snapshot`：现在可正常展示 3 个快照卡片与指标对照表。
- `/profiles/lac`：修复参数后不再返回 422。
- `/observation`：由默认空状态恢复为真实候选卡片列表。
- `/governance`：核心字段 / 直接复用概览值修正为 `8 / 8`。

### 2.3 API 兼容性问题与修复

| 模块 | 问题 | 处理结果 |
|---|---|---|
| `run.py` / `FlowOverviewPage.vue` | 前端使用 `promotions`、`demotions`、`cascade_*`、`baseline_refreshed`、异常统计等字段，原接口信息不足 | ✅ 后端补齐 `decision_summary`、`baseline_refreshed`、`baseline_next_version`、`anomaly_total`、`anomaly_new` |
| `run.py` / `ObservationWorkspacePage.vue` | 观察卡片所需明细字段不足，默认 Tab 与后端数据语义不匹配 | ✅ 后端补齐 existence/anchor/baseline/trend/坐标/累计摘要字段；前端默认切到 `all` 并兼容 trend 值 |
| `run.py` / `AnomalyWorkspacePage.vue` | 异常页展开信息不足 | ✅ 后端补齐 `evidence_trend`、`collision_group`、`affected_cells`、`fact_explanation`、`batch_new`、`type_class` |
| `run.py` / `BaselineProfilePage.vue` | 前端使用 `trigger_detail`、`quality.stability_score`，原接口不完整 | ✅ 后端补齐触发详情、稳定度、异常统计与差异样本字段 |
| `governance.py` / `GovernancePage.vue` | 概览缺 `core_field_count`、`direct_reuse_count`；多数表 usage 可能 404 | ✅ 后端补齐概览字段，并为未登记表生成 fallback usage 详情 |
| `object.py` / 画像页 | 画像页需要更丰富的解释层/GPS/坐标字段 | ✅ 后端补齐 `classification_v2`、`gps_quality`、中心点与偏差字段 |
| `LacProfilePage.vue` | `page_size=8` 不满足后端最小值 10 | ✅ 改为 `page_size=10` |
| `BsProfilePage.vue` / `CellProfilePage.vue` / `ObjectsPage.vue` | 筛选值与后端枚举不一致，出现空结果或误筛选 | ✅ 前端筛选值统一改为后端支持的 `4G/5G`、`anchorable/not_anchorable/baseline/not_baseline` |
| `FlowSnapshotPage.vue` | 已知占位符页，仅显示“即将实现” | ✅ 已重写为真实页面，接入 `/api/v1/runs/flow-snapshots` |

### 2.4 已修复的功能问题清单

#### P0 / P1

- `/flow/snapshot` 占位符页面已替换为真实实现。
- `/profiles/lac` 422 加载失败已修复。
- `/observation` 默认进入空状态的问题已修复。
- `governance/overview` 关键统计缺失已修复。
- 治理页 usage 详情对多数表 404 的问题已修复为 fallback 可读详情。
- BS/Cell/LAC 画像页与对象浏览页的筛选值不兼容问题已修复。
- `ObjectsPage.vue` 与 `BsProfilePage.vue` 中的乱码文案已修复。

#### P2 / P3

- 流转总览不再虚构输入/输出计数，改为直接读取真实上下文或安全 fallback。
- 运行/批次中心缺少 `cascade_summary` 时，回退显示 `decision_summary` 生命周期分布。
- 基线页触发状态、差异样本、质量指标展示逻辑已兼容真实数据。
- 观察工作台新增排序处理与趋势值归一化。
- 全局移动端壳层改为可滚动导航条，避免小屏导航挤压正文。

### 2.5 死代码清理结果

已确认无路由引用后删除：

- `rebuild3/frontend/src/pages/ProfileListPage.vue`
- `rebuild3/frontend/src/components/BadgePill.vue`
- `rebuild3/frontend/src/components/MetricCard.vue`
- `rebuild3/frontend/src/components/PageSection.vue`
- `rebuild3/frontend/src/components/QualificationStrip.vue`
- `rebuild3/frontend/src/components/VersionContextBar.vue`
- `rebuild3/frontend/src/lib/options.ts`

### 2.6 代码规模审计结果（新增）

本轮额外按“活跃应用代码文件规模”做了一次审计，统计时排除了 `node_modules`、`.venv`、`dist`、`runtime`、`archive`。

#### 单文件规模变化

| 文件 | 优化前 | 优化后 | 处理方式 |
|---|---:|---:|---|
| `frontend/src/styles.css` | 1451 行 | 4 行 | ✅ 拆为 `foundation.css` / `surfaces.css` / `features.css` / `responsive.css` |
| `backend/app/api/run.py` | 874 行 | 305 行 | ✅ 拆为 `run.py` + `run_shared.py` + `run_workspaces.py` |
| `frontend/src/pages/ObservationWorkspacePage.vue` | 707 行 | 453 行 | ✅ 页面样式抽到 `styles/pages/observation-workspace.css` |
| `backend/app/api/object.py` | 604 行 | 162 行 | ✅ 拆为 `object.py` + `object_common.py` + `object_detail.py` |

#### 当前活跃代码最大文件

| 排名 | 文件 | 行数 | 结论 |
|---|---|---:|---|
| 1 | `frontend/src/styles/surfaces.css` | 574 | 可继续观察，但已低于 600 行警戒线 |
| 2 | `frontend/src/pages/ObservationWorkspacePage.vue` | 453 | 可维护 |
| 3 | `backend/app/api/run_workspaces.py` | 447 | 可维护 |
| 4 | `frontend/src/styles/features.css` | 445 | 可维护 |
| 5 | `frontend/src/pages/FlowOverviewPage.vue` | 415 | 可维护 |

#### 规模结论

- `frontend/src` 总行数：`5940 -> 5939`，总量基本不变，但结构从“大文件堆叠”变为“模块分摊”。
- `backend/app` 总行数：`2118 -> 2327`，总量略增，主要来自缓存/共享模块/对象详情拆分；这是**为降低单文件复杂度而做的有意扩展**。
- 活跃应用代码中 `> 600 行` 的文件数量：`4 -> 0`。
- 当前未再发现必须立即拆分的单文件阻塞项。

### 2.7 速度审计与优化结果（新增）

#### API 基线与优化后对比

| 接口 | 优化前均值 | 优化后表现 | 说明 |
|---|---:|---:|---|
| `/api/v1/runs/flow-overview` | ~1.17s | ~0.05s | 共享查询缓存 + 连接复用 |
| `/api/v1/runs/batches` | ~1.55s | ~0.01s | 共享缓存 + 避免重复建连 |
| `/api/v1/runs/anomaly-workspace` | ~6.86s | 冷启动 ~0.95s，热缓存 ~0.004s | ✅ 改为优先读 `batch_anomaly_summary` 的记录级汇总，并保留 TTL cache |
| `/api/v1/runs/baseline-profile` | ~2.53s | ~0.26s | 元数据缓存 + 连接复用 |
| `/api/v1/objects/summary?object_type=cell` | ~1.11s | ~0.22s | TTL cache |
| `/api/v1/objects/list?object_type=cell&page=1&page_size=20` | ~7.07s | ~0.46s ~ 0.55s | ✅ 分离 `count(*)` 与分页查询，只对当前页做画像/compare join |
| `/api/v1/objects/profile-list?object_type=lac&page=1&page_size=10` | ~1.23s | ~0.17s | 复用优化后的 list/summary 路径 |
| `/api/v1/objects/detail?object_type=cell&object_id=...` | 页面约 5.9s | 冷启动 ~0.71s，热缓存 ~0.005s | ✅ 新增对象范围索引 + 合并 source mix 查询 + 详情级缓存 |

#### 本轮性能优化动作

1. 数据库连接层：`backend/app/core/database.py` 改为线程内连接复用，消除每个查询都新建/关闭连接的额外成本。
2. 读接口缓存：在 `backend/app/api/common.py` 增加 TTL cache，并用于 `run` / `run_workspaces` / `object` 的高频只读接口。
3. 对象列表查询：`backend/app/api/object.py` 改为“先 count、再分页、最后只 join 当前页”的两段式查询，移除全量 `WindowAgg` 成本。
4. 对象详情查询：
   - 为 `fact_governed` / `fact_pending_observation` / `fact_pending_issue` / `fact_rejected` 增加对象范围索引；
   - 为 `obj_state_history` 增加详情查询索引；
   - 将 source mix 合并为一次 scoped 查询；
   - 详情接口本身增加 TTL cache。
5. 异常工作台：不再在每次首屏加载时全表扫描 `fact_governed` 计算记录级统计，而是优先读取 `rebuild3_meta.batch_anomaly_summary` 中的批次级记录汇总；当前正式库已补写这批统计。

#### 前端实页测速结果

使用 Playwright 在 `1440x900` 下做真实路由加载，当前 14 个主路由全部：

- 无 `.error-banner`
- 无永久 loading
- 无页面级横向溢出

本轮回归中有代表性的页面耗时：

| 页面 | 当前耗时 | 说明 |
|---|---:|---|
| `/objects` | ~810ms | 已不再受全量 join 阻塞 |
| `/anomalies` | ~380ms | 记录级统计改读批次汇总后明显下降 |
| `/profiles/cell` | ~511ms | 画像页稳定 |
| `/baseline` | ~982ms | 当前仍是主路由里最重页面之一，但已可接受 |
| `/objects/cell/cell|46000|5G|2097240|5751177217` | ~885ms | 对象详情页从多秒级下降到亚秒级 |

#### 性能结论

- 当前主要读路径已经从“秒级阻塞”降到“冷启动可接受、热缓存快速返回”。
- 这轮没有引入新的慢页；对象详情与异常工作台两个历史慢点都已压到可交付范围。
- 后续若要继续压缩首个冷请求，可优先考虑把更多详情摘要在批次结束时预汇总到 meta 表，而不是继续叠加运行时 SQL 复杂度。

---

## 三、排版审计结果

### 3.1 审计方法

- 对照文档：
  - `.impeccable.md`
  - `rebuild3/docs/UI_v2/design_notes.md`
  - `rebuild3/docs/UI_v2/design_system.html`
  - `rebuild3/docs/UI_v2/pages/*_doc.md`
  - `rebuild3/docs/UI_v2/pages/*.html`
  - `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`（重点 Section 7）
- 对照方式：
  - 设计稿 HTML 本地服务对照
  - Playwright 实页截图/快照检查
  - 桌面端 + 移动端布局回归检查

### 3.2 覆盖率评估

下表是本轮按“结构层级、区块关系、信息密度、响应式收敛”综合给出的对齐度估计，不是像素级视觉 diff：

| 页面 | 结构对齐度 | 说明 |
|---|---:|---|
| `/flow/overview` | 93% | 主流程图、累计指标、问题入口结构已稳定；移动端流程图已收敛 |
| `/flow/snapshot` | 95% | 页面已从占位实现为真实快照布局 |
| `/runs` | 92% | 批次总览、批次列表、详情结构完整 |
| `/objects` | 93% | 汇总卡片、筛选栏、对象表结构稳定 |
| `/objects/:type/:id` | 91% | 明细块与下游/历史结构齐备 |
| `/observation` | 92% | 候选卡片、积累摘要、趋势筛选结构可用 |
| `/anomalies` | 92% | 双 Tab 与对象/记录明细结构齐备 |
| `/baseline` | 91% | 触发概览、质量评估、差异样本结构完整 |
| `/compare` | 89% | 结构基本到位，但数据源仍为回退模式 |
| `/profiles/lac` | 90% | 汇总 + 表格型结构稳定 |
| `/profiles/bs` | 90% | 汇总 + 表格型结构稳定 |
| `/profiles/cell` | 90% | 汇总 + 表格型结构稳定 |
| `/initialization` | 91% | 初始化步骤/说明块结构完整 |
| `/governance` | 90% | 四视图已稳定，移动端分栏已修复 |

### 3.3 本轮完成的排版修复

- 全局样式：
  - 修复移动端文档级横向溢出。
  - `html/body/page-content/table-wrap` 增加安全宽度与裁剪约束。
  - 小屏下侧边栏切换为横向导航条，主内容可独立收敛。
- 流转总览：
  - 为小屏流程图重排 `flow-stage / flow-data / flow-info`，避免流程节点和数值列相互挤压。
  - 缩小移动端流程节点尺寸并允许长文本换行。
- 数据治理：
  - 将 summary、字段筛选、使用情况、迁移状态从内联固定布局改为响应式 class。
  - 小屏下 summary / filter / migration 自动降为 2 列或 1 列，usage 双栏收敛为单栏。

### 3.4 仍存在的结构偏差

这些问题不阻塞交付，但仍与理想状态有轻微差距：

1. `compare` 页的数据内容仍受后端回退数据限制，导致“结构对了、语义深度不足”。
2. `governance` 页在移动端仍保留局部表格横向滚动，这是为了保全字段目录的信息密度，属于**容器内滚动**而非页面级溢出。
3. 部分页面仍存在少量内联样式与 `any` 类型读模型，后续若继续打磨，建议做一次组件化/类型化收敛。

---

## 四、抛光结果（Impeccable 最终检查）

### 4.1 使用的技能思路

本轮最终抛光按以下顺序执行：

1. `audit` — 用可验证的技术维度重新核查可用性、响应式与实现反模式
2. `arrange` — 修复剩余布局收敛问题，重点是治理页与流转总览页的移动端结构
3. `polish` — 做最后一轮视觉/边界状态检查，补齐 favicon 与默认壳层细节
4. `clarify` — 清理乱码与筛选/状态文案不一致问题

### 4.2 Audit Health Score

| # | 维度 | 分数 | 关键结论 |
|---|---|---:|---|
| 1 | Accessibility | 2/4 | 语义结构基本可用，但未做系统化键盘/ARIA 补强 |
| 2 | Performance | 3/4 | 数据页以静态渲染为主，未见明显性能阻塞 |
| 3 | Responsive Design | 4/4 | 本轮已消除主路由页面级横向溢出 |
| 4 | Theming | 3/4 | 主色、层级、圆角、表面 token 基本统一，仍有少量内联样式 |
| 5 | Anti-Patterns | 3/4 | 已摆脱占位/AI 套壳感，仍可继续减少零散内联表现逻辑 |
| **Total** |  | **15/20** | **Good** |

### 4.3 Anti-Patterns Verdict

**结论：通过。** 当前界面已不再呈现“占位符拼装页”或“AI slop 卡片墙”的明显特征，整体是明确的数据工作台风格。剩余问题更多是工程一致性，而不是审美方向错误。

### 4.4 本轮抛光修复

- 修复了移动端剩余横向溢出。
- 统一了治理页响应式布局类，减少内联固定网格。
- 为前端 `index.html` 补充 favicon、`theme-color` 与更合理的默认标题。
- 清理了对象浏览 / BS 画像中的乱码文案。
- 统一了多处筛选值与文案标签，避免“文案像是可选项，但接口不支持”的错觉。

### 4.5 仍建议后续补强的点

- 增补更系统的键盘导航 / focus / ARIA 检查。
- 收敛页面中的 `any` 类型和零散内联样式。
- 若 compare/governance 后端数据继续完善，可再做一轮信息层级精调。

---

## 五、docs 整理结果

### 5.1 归档动作

已创建：

- `rebuild3/docs/archive/20260405_ui_reaudit/`

已移入归档的内容：

- 旧审计：`ui_audit/`、`gemini_ui_audit/`、`ui_acceptance_report.md`
- 旧实施计划：`impl_plan.md`、`impl_alignment.md`、`ui_first_impl_plan.md`
- 旧映射/问题清单：`ui_mapping_matrix.md`、`issues.md`
- 旧运行报告：`sample_scope.md`、`sample_run_report.md`、`sample_compare_report.md`、`full_run_report.md`、`full_compare_report.md`、`replay_log.md`
- 旧复核报告：`current_tree_audit.md`、`data_reaudit_report.md`、`rectification_audit.md`
- 旧归档报告：`archive_execution_report.md`、`archive_manifest_20260404_ui_spike.md`

### 5.2 保留策略

#### 当前基线

- 冻结业务/任务/技术文档：`01`、`02`、`03`
- 设计基线：`UI_v2/`
- 运行/API/审计入口：`api_models.md`、`runtime_startup_guide.md`、`ui_restructure_audit_prompt.md`、`ui_final_rectification_report.md`

#### 保留为历史参考但未归档

以下内容仍保留在根目录，原因是它们之间存在交叉引用，且有追溯价值：

- `Docs/`
- `Prompt/`
- `UI/`
- `claude/`
- `codex/`
- `04_*` 多版 Prompt 文档

### 5.3 README 更新

已重写 `rebuild3/docs/README.md`，现在包含：

- 当前推荐阅读顺序
- 保留 / 参考 / 已归档三类状态说明
- 推荐目录结构
- archive 的使用规则

---

## 六、验证结果

### 6.1 构建与语法验证

```bash
cd rebuild3/frontend && npm run build
cd rebuild3/backend && python3 -m py_compile \
  app/api/run.py app/api/run_shared.py app/api/run_workspaces.py \
  app/api/object.py app/api/object_common.py app/api/object_detail.py \
  app/api/governance.py app/api/common.py app/core/database.py app/main.py
```

结果：

- ✅ 前端构建通过（Vite build 成功）
- ✅ 后端 `py_compile` 通过

### 6.2 页面验证

- ✅ Playwright 桌面端逐页加载通过（14 个主路由全部可渲染）
- ✅ Playwright 移动端逐页横向溢出检查通过
- ✅ 当前页 console error 为 0（不含历史保留日志）
- ✅ 关键页面测速通过：`/anomalies` ≈ 380ms、`/objects` ≈ 810ms、对象详情页 ≈ 885ms
- ✅ 关键 API 测速通过：`anomaly-workspace` 冷启动 ≈ 0.95s、`objects/list` ≈ 0.5s、对象详情冷启动 ≈ 0.71s

---

## 七、最终结论与剩余风险

### 已完成

- 功能修复：完成
- 排版修复：完成
- 最终抛光：完成
- docs 整理：完成

### 剩余风险

1. `compare` 页仍是**结构已就位、数据待后端补全**的状态。
2. `governance` 页的 usage 对部分表采用 fallback 详情，后续仍建议补齐真实登记。
3. A11y 还没有做到“系统级验收”，当前更偏可用而非严格合规。
4. 当前性能瓶颈已不再阻塞交付，但首个冷请求仍会明显慢于热缓存命中，后续若做长期运营优化，建议继续把详情类统计下沉到批次级汇总表。

### 交付判断

**可以进入下一阶段。**

如果后续继续迭代，建议顺序为：

1. 补齐 compare 真数据
2. 完善 governance usage 真实登记
3. 做一轮专门的 A11y / 类型收敛 / 组件化清理
