# rebuild3 UI 完整审计 + 分层修复 Prompt

> 本 prompt 用于对已完成 ~70% 的 UI 重构做全面摸底，然后按 **功能 → 排版 → 抛光** 三层逐步修复。

---

## 项目根目录

`/Users/yangcongan/cursor/WangYou_Data`

你有 Playwright MCP 可用，可以直接打开浏览器截图检查页面。
你有 Impeccable skills 可用（如 `/audit`、`/polish`、`/arrange`、`/clarify`、`/distill` 等），在最终抛光阶段调用。

## 服务

- 后端：http://127.0.0.1:47121
- 前端：http://127.0.0.1:47122
- 如未启动：`./rebuild3/scripts/dev/start_backend.sh && ./rebuild3/scripts/dev/start_frontend.sh`
- 设计稿 HTML 需本地起服务查看：`python3 -m http.server 47199 --directory rebuild3/docs/UI_v2`

## 硬约束

1. 遵守 `.impeccable.md` 设计原则
2. 不改业务术语
3. 浅色模式、蓝靛蓝主色 `#4F46E5`
4. 可见文案优先中文
5. 修完后必须 `cd rebuild3/frontend && npm run build` 验证

---

## 你必须读取的文档

- `.impeccable.md` — 设计原则与风格约束
- `rebuild3/docs/UI_v2/design_notes.md` — 整体设计说明
- `rebuild3/docs/UI_v2/design_system.html` — 设计系统
- `rebuild3/docs/UI_v2/pages/*_doc.md` — 13 个页面设计文档
- `rebuild3/docs/UI_v2/pages/*.html` — 13 个页面设计稿 HTML
- `rebuild3/docs/01_rebuild3_说明_最终冻结版.md` — 冻结业务文档（特别是 Section 7）

---

## 总纲：三层工作法

```
第一层：功能审计 + 功能修复（让每个页面都能正确加载、数据真实、交互可用）
第二层：排版审计 + 排版修复（对照设计稿 HTML，逐页修正结构/布局偏差）
第三层：视觉抛光（调用 Impeccable skills: /audit → /polish → /arrange 等）
```

**严格按层执行，不要在第一层就去调排版，不要在第二层就去抛光。**

---

## 第一层：功能审计

### 1.1 用 Playwright 打开每个页面，记录实际状态

对每个页面执行：
1. 用 Playwright 导航到该页面 URL
2. 等待加载完成
3. 截图
4. 判断：**真实页面** vs **占位符** vs **加载失败** vs **数据为空**

### 1.2 页面清单与预期

| # | 页面 | URL | 前端文件 | API 端点 | 预判状态 |
|---|------|-----|---------|---------|---------|
| 01 | 流转总览 | `/flow/overview` | `FlowOverviewPage.vue` | `GET /api/v1/runs/flow-overview` | 有真实数据，已重构 |
| 01B | 流转快照 | `/flow/snapshot` | `FlowSnapshotPage.vue` | `GET /api/v1/runs/flow-snapshots` | **已知占位符**，仅显示"即将实现" |
| 02 | 批次中心 | `/runs` | `RunBatchCenterPage.vue` | `GET /api/v1/runs/batches` + `GET /api/v1/runs/batch/{id}` | 已重构，需验证 |
| 03 | 对象浏览 | `/objects` | `ObjectsPage.vue` | `GET /api/v1/objects/summary` + `GET /api/v1/objects/list` | 已重构，需验证 |
| 04 | 对象详情 | `/objects/:type/:id` | `ObjectDetailPage.vue` | `GET /api/v1/objects/detail` | 已重构，需从对象浏览点进去验证 |
| 05 | 观察工作台 | `/observation` | `ObservationWorkspacePage.vue` | `GET /api/v1/runs/observation-workspace` | 已重构，需验证三层资格卡片 |
| 06 | 异常工作台 | `/anomalies` | `AnomalyWorkspacePage.vue` | `GET /api/v1/runs/anomaly-workspace` | 已重构，需验证双 Tab |
| 07 | 基线画像 | `/baseline` | `BaselineProfilePage.vue` | `GET /api/v1/runs/baseline-profile` | 已重构，需验证触发详情 |
| 08 | 验证对照 | `/compare` | `ValidationComparePage.vue` | `GET /api/v1/compare/overview` + `GET /api/v1/compare/diffs` | 已重构，需验证 |
| 09 | LAC 画像 | `/profiles/lac` | `LacProfilePage.vue` | `GET /api/v1/objects/profile-list?object_type=lac` | 新独立页面，需验证 |
| 10 | BS 画像 | `/profiles/bs` | `BsProfilePage.vue` | `GET /api/v1/objects/profile-list?object_type=bs` | 新独立页面，需验证 |
| 11 | Cell 画像 | `/profiles/cell` | `CellProfilePage.vue` | `GET /api/v1/objects/profile-list?object_type=cell` | 新独立页面，需验证 |
| 12 | 初始化 | `/initialization` | `InitializationPage.vue` | `GET /api/v1/runs/initialization` | 已重构，需验证 |
| 13 | 数据治理 | `/governance` | `GovernancePage.vue` | `GET /api/v1/governance/*` (4 个端点) | 已重构，需验证 |

### 1.3 API 兼容性审计

后端实际存在的端点（已确认）：
```
# run.py
GET /api/v1/runs/current
GET /api/v1/runs/flow-overview
GET /api/v1/runs/flow-snapshots
GET /api/v1/runs/batches
GET /api/v1/runs/batch/{batch_id}
GET /api/v1/runs/observation-workspace
GET /api/v1/runs/anomaly-workspace
GET /api/v1/runs/baseline-profile
GET /api/v1/runs/initialization

# object.py
GET /api/v1/objects/summary
GET /api/v1/objects/list
GET /api/v1/objects/detail
GET /api/v1/objects/profile-list

# compare.py
GET /api/v1/compare/overview
GET /api/v1/compare/diffs

# governance.py
GET /api/v1/governance/overview
GET /api/v1/governance/fields
GET /api/v1/governance/tables
GET /api/v1/governance/usage/{table_name}
GET /api/v1/governance/migration
```

**需要检查的潜在问题：**

前端页面可能引用了后端 **不返回** 的字段。以下是已知的可疑字段（在前端代码中使用但后端可能未提供）：

| 前端文件 | 使用的字段 | 可能的问题 |
|---------|-----------|-----------|
| `FlowOverviewPage.vue` | `overview.context.contract_version`, `overview.promotions`, `overview.demotions`, `overview.cascade_bs/lac/total`, `overview.baseline_refreshed` | 后端 flow-overview 可能不返回这些 |
| `ObservationWorkspacePage.vue` | `card.existence_details`, `card.anchor_details`, `card.baseline_details`, `card.trend_values`, `card.centroid_lat/lon`, `card.first_seen`, `card.stalled_batches` | 后端 observation-workspace 可能不返回明细 |
| `AnomalyWorkspacePage.vue` | `row.evidence_trend`, `row.collision_group`, `row.affected_cells`, `row.fact_explanation`, `record_tab.batch_new` | 后端 anomaly-workspace 可能不返回展开信息 |
| `BaselineProfilePage.vue` | `payload.trigger_detail`, `payload.quality.stability_score` | 后端 baseline-profile 可能没有 trigger_detail 对象 |
| `RunBatchCenterPage.vue` | `row.is_rerun`, `detail.cascade_summary` | 后端 batch 接口可能没有 is_rerun 和 cascade |
| `ObjectDetailPage.vue` | `detail.downstream` 对象格式 | 需验证返回格式 |
| `GovernancePage.vue` | `overview.core_field_count`, `overview.direct_reuse_count` | 后端 governance/overview 可能只有 4 个字段 |

**对每个 API，你需要：**
1. 直接 curl 调用后端 API 看实际返回
2. 比对前端使用的字段
3. 如果字段缺失：
   - 后端能补 → 改后端
   - 后端数据不支持 → 前端做 fallback 或显示占位

### 1.4 死代码清理

以下文件已确认不再被路由引用，但仍存在：
- `ProfileListPage.vue` — 已被 `LacProfilePage` / `BsProfilePage` / `CellProfilePage` 替代
- `BadgePill.vue` — 仅被 `ProfileListPage` 和 `QualificationStrip` 和 `VersionContextBar` 引用
- `MetricCard.vue` — 仅被 `ProfileListPage` 引用
- `PageSection.vue` — 仅被 `ProfileListPage` 引用
- `QualificationStrip.vue` — 仅被 `ProfileListPage` 引用
- `VersionContextBar.vue` — 不再被 `App.vue` 引用

**行动：确认无其他引用后，删除这些文件。**

### 1.5 功能修复优先级

修完审计后，按以下顺序修功能：
1. **P0 — 页面加载失败**（API 报错、字段缺失导致白屏）
2. **P1 — 数据不真实**（前端用了后端不存在的字段，显示 undefined/NaN）
3. **P2 — 交互不工作**（筛选器无效、展开行不动、分页坏了）
4. **P3 — 占位符页面**（FlowSnapshotPage 需要真正实现）

---

## 第二层：排版审计

### 工作方法

对每个页面：
1. 启动设计稿 HTTP 服务：`python3 -m http.server 47199 --directory rebuild3/docs/UI_v2`
2. 用 Playwright 截图设计稿 `http://127.0.0.1:47199/pages/XX_xxx.html`
3. 用 Playwright 截图当前实现 `http://127.0.0.1:47122/path`
4. 逐区块结构对比（不是看文案，是看结构、层次、组件边界）
5. 记录偏差 → 修代码

### 设计稿对照表

| 设计稿 HTML | 对应实现 URL | 设计文档 |
|------------|-------------|---------|
| `01_flow_overview.html` | `/flow/overview` | `01_flow_overview_doc.md` |
| `01_flow_overview_timeline.html` | `/flow/snapshot` | `01_flow_overview_doc.md` |
| `02_run_batch_center.html` | `/runs` | `02_run_batch_center_doc.md` |
| `03_objects.html` | `/objects` | `03_objects_doc.md` |
| `04_object_detail.html` | `/objects/:type/:id` | `04_object_detail_doc.md` |
| `05_observation_workspace.html` | `/observation` | `05_observation_workspace_doc.md` |
| `06_anomaly_workspace.html` | `/anomalies` | `06_anomaly_workspace_doc.md` |
| `07_baseline_profile.html` | `/baseline` | `07_baseline_profile_doc.md` |
| `08_validation_compare.html` | `/compare` | `08_validation_compare_doc.md` |
| `09_lac_profile.html` | `/profiles/lac` | `09_lac_profile_doc.md` |
| `10_bs_profile.html` | `/profiles/bs` | `10_bs_profile_doc.md` |
| `11_cell_profile.html` | `/profiles/cell` | `11_cell_profile_doc.md` |
| `12_initialization.html` | `/initialization` | `12_initialization_doc.md` |
| `13_data_governance.html` | `/governance` | `13_data_governance_doc.md` |

### 全局视觉系统检查项

- [ ] 侧边栏：深靛蓝 `#1E1B4B`，白色文字，当前页高亮 `#4F46E5`
- [ ] Topbar：白底 sticky，56px 高度，页面标题 + 状态灯
- [ ] 主色：`#4F46E5` (Indigo-600)
- [ ] 圆角：8px(lg) / 6px(md) / 4px(sm)
- [ ] 组件库：LifecycleBadge、HealthBadge、WatchIndicator、QualificationTags、FactLayerBadge、DeltaIndicator、MetricCardWithDelta 全部使用正确
- [ ] Delta 展示：三行格式（当前值 / 本批 / 较上批）
- [ ] WATCH 标记：橙色左边框 + WATCH 徽标 + 行背景微橙

---

## 第三层：视觉抛光

当第一层和第二层全部完成后，使用 Impeccable skills 做最终抛光：

```
步骤 1：/audit — 全局质量审计，得到评分报告和 P0-P3 问题清单
步骤 2：修复 /audit 发现的 P0/P1 问题
步骤 3：/arrange — 检查布局、间距、视觉层次
步骤 4：/polish — 最终细节打磨（对齐、间距一致性、微交互）
步骤 5：/clarify — 检查文案（标签、错误消息、空状态提示）
```

**注意：只有在功能和排版都正确之后才执行这一层。**

---

## docs 目录整理

`rebuild3/docs/` 目录已经积累了大量多版本中间产物。需要整理：

### 核心文档（保留）
- `01_rebuild3_说明_最终冻结版.md` — 业务冻结文档
- `02_rebuild3_预实施任务书_最终冻结版.md` — 任务书
- `03_rebuild3_技术栈要求_最终冻结版.md` — 技术栈要求
- `UI_v2/` — 当前设计基线（所有 *_doc.md + *.html + design_notes.md + design_system.html）
- `api_models.md` — API 模型文档
- `runtime_startup_guide.md` — 启动指南

### 审计/报告文档（保留但标记版本）
- `ui_final_rectification_report.md` — 最终修正报告（需更新）
- `ui_restructure_prompt.md` — 重构 prompt
- `ui_restructure_audit_prompt.md` — 本审计 prompt

### 可能过时的文档（审计后决定是否归档）
- `04_agent_prompts_UI与开发.md` / `04a~04f` — 多版本 prompt，检查是否还有用
- `archive_*` — 已经是归档
- `ui_audit/` / `gemini_ui_audit/` — 旧审计结果
- `UI/` — 旧版设计（UI_v1?），检查是否已被 UI_v2 完全替代
- `impl_plan.md` / `impl_alignment.md` — 旧实施计划
- `issues.md` — 旧 issue 列表，检查是否还有未关闭的

**行动：**
1. 列出所有 docs 文件，标注：保留 / 归档 / 删除
2. 创建 `rebuild3/docs/archive/` 目录，将过时文档移入
3. 更新 `rebuild3/docs/README.md` 作为目录索引

---

## 输出要求

完成后更新 `rebuild3/docs/ui_final_rectification_report.md`，包含：

1. **功能审计结果**
   - 每页状态：✅ 正常 / ⚠️ 部分工作 / ❌ 失败 / 📋 占位符
   - API 兼容性问题清单
   - 已修复的问题

2. **排版审计结果**
   - 每页覆盖率评估（%）
   - 仍存在的结构偏差

3. **抛光结果**
   - Impeccable /audit 评分
   - 修复的细节问题

4. **docs 整理结果**
   - 文件归档清单
   - 最终目录结构
