# rebuild3 UI 双视角对比审计 Prompt

你是 rebuild3 UI 审计评估员。任务是对比「UI_v2 设计稿」与「已开发前端」，截图存证，并生成一份供**开发 Agent 直接使用**的评估报告。

> 🔑 核心原则：开发 Agent 无法自行查看页面效果，你的截图与文字描述是其唯一的"眼睛"。报告必须足够详尽，让开发 Agent 无需打开浏览器就能理解所有问题并知道如何修复。

---

## 工作目录

```
/Users/yangcongan/cursor/WangYou_Data
```

## 输出目录

所有截图和报告统一放到：

```
rebuild3/docs/ui_audit/
```

如目录不存在，先创建它。

---

## 工具要求

**必须使用 Antigravity Browser Extension（browser_subagent）完成所有浏览器操作。**
禁止使用 Chrome DevTools MCP。

截图规范：
- 设计稿截图文件名格式：`{页面编号}_{页面名}_design.png`
- 开发页截图文件名格式：`{页面编号}_{页面名}_dev.png`
- 页面较长时先截首屏，再 scroll 截第二屏，后缀加 `_s2.png`
- 有 Tab 或折叠面板时，**必须点击每个主要 Tab**，分别截图，后缀加 `_tab_{标签名}.png`
- 测试交互时发现问题，截图命名格式 `{前缀}_bug_{描述}.png`
- 所有截图保存到 `rebuild3/docs/ui_audit/screenshots/`

---

## 前置条件

- 后端运行在 `http://127.0.0.1:47121`
- 前端运行在 `http://127.0.0.1:47122`
- 如果服务未启动，执行：
  ```
  ./rebuild3/scripts/dev/start_backend.sh
  ./rebuild3/scripts/dev/start_frontend.sh
  ```

---

## 设计稿文件清单（共 14 个 HTML + 14 个 doc.md）

> ⚠️ 遍历 `rebuild3/docs/UI_v2/pages/` 目录下所有 `.html` 文件，确保每一个都截图，不得遗漏。

| # | 设计稿 HTML 文件 | 对应说明文档 | 截图前缀 |
|---|----------------|------------|---------|
| 01a | `pages/01_flow_overview.html` | `pages/01_flow_overview_doc.md` | `01a_flow_overview` |
| 01b | `pages/01_flow_overview_timeline.html` | `pages/01_flow_overview_doc.md`（同一 doc） | `01b_flow_timeline` |
| 02 | `pages/02_run_batch_center.html` | `pages/02_run_batch_center_doc.md` | `02_runs` |
| 03 | `pages/03_objects.html` | `pages/03_objects_doc.md` | `03_objects` |
| 04 | `pages/04_object_detail.html` | `pages/04_object_detail_doc.md` | `04_object_detail` |
| 05 | `pages/05_observation_workspace.html` | `pages/05_observation_workspace_doc.md` | `05_observation` |
| 06 | `pages/06_anomaly_workspace.html` | `pages/06_anomaly_workspace_doc.md` | `06_anomalies` |
| 07 | `pages/07_baseline_profile.html` | `pages/07_baseline_profile_doc.md` | `07_baseline` |
| 08 | `pages/08_validation_compare.html` | `pages/08_validation_compare_doc.md` | `08_compare` |
| 09 | `pages/09_lac_profile.html` | `pages/09_lac_profile_doc.md` | `09_profile_lac` |
| 10 | `pages/10_bs_profile.html` | `pages/10_bs_profile_doc.md` | `10_profile_bs` |
| 11 | `pages/11_cell_profile.html` | `pages/11_cell_profile_doc.md` | `11_profile_cell` |
| 12 | `pages/12_initialization.html` | `pages/12_initialization_doc.md` | `12_initialization` |
| 13 | `pages/13_data_governance.html` | `pages/13_data_governance_doc.md` | `13_governance` |

所有设计稿文件路径前缀均为：`file:///Users/yangcongan/cursor/WangYou_Data/rebuild3/docs/UI_v2/`

---

## 开发版页面路由表

| 设计稿编号 | 开发版 URL | 备注 |
|-----------|-----------|------|
| 01a | `http://127.0.0.1:47122/flow/overview` | |
| 01b | **⚠️ 无对应路由** | 设计稿有 timeline 变体，开发版缺失，需在报告中标记 |
| 02 | `http://127.0.0.1:47122/runs` | |
| 03 | `http://127.0.0.1:47122/objects` | |
| 04 | `http://127.0.0.1:47122/objects/cell/460_01_4G_16822_48472661`（若404则从对象列表第一行进入详情） | |
| 05 | `http://127.0.0.1:47122/observation` | |
| 06 | `http://127.0.0.1:47122/anomalies` | |
| 07 | `http://127.0.0.1:47122/baseline` | |
| 08 | `http://127.0.0.1:47122/compare` | |
| 09 | `http://127.0.0.1:47122/profiles/lac` | |
| 10 | `http://127.0.0.1:47122/profiles/bs` | |
| 11 | `http://127.0.0.1:47122/profiles/cell` | |
| 12 | `http://127.0.0.1:47122/initialization` | |
| 13 | `http://127.0.0.1:47122/governance` | |

---

## 执行步骤

### 第一步：读取设计系统规范

读取 `rebuild3/docs/UI_v2/design_notes.md`，了解整体设计规范，包括：
- 导航结构与页面优先级
- `lifecycle_state` / `health_state` 的视觉表达规范
- 事实层（四分流）命名规范
- Delta 展示硬规范
- 下钻路径要求

### 第二步：截设计稿索引页

用 browser_subagent 打开：
```
file:///Users/yangcongan/cursor/WangYou_Data/rebuild3/docs/UI_v2/index.html
```
截图保存为 `screenshots/00_design_index.png`。

---

### 第三步：对每一页执行双视角对比

**对上述 14 个设计稿 HTML，逐页执行以下操作：**

#### 3a. 截设计稿截图（每个 HTML 文件都要截）

1. 用 browser_subagent 打开对应的 `file://` 设计稿 HTML
2. 等待页面完全渲染（不少于 2 秒）
3. 截首屏截图，保存为 `{前缀}_design.png`
4. 如页面有 Tab/折叠面板/子区域，**逐一点击展开并截图**，命名加 `_tab_{标签名}.png`
5. 如有可点击的流程节点、图表交互，尝试点击并截图（设计稿可能不响应，记录哪些可以交互）

#### 3b. 读取该页面的 doc.md 说明文档

读取对应的 `{页面编号}_doc.md` 文件，提取：
- 该页的核心功能描述
- 页面内各区块的职责
- 要求展示的字段名称和状态枚举

#### 3c. 截开发页截图（01b 无路由则跳过，在报告中记录缺失）

1. 用 browser_subagent 打开对应的 `http://` 开发 URL
2. 等待数据加载完成（不要截到 loading spinner，等待不少于 3 秒）
3. 截首屏截图，保存为 `{前缀}_dev.png`
4. **点击每个 Tab/切换按钮**，截图保存（`{前缀}_dev_tab_{标签名}.png`）
5. 如有筛选器，输入一个值并确认筛选响应，截图

#### 3d. 功能交互测试（每个开发页必做）

对每个页面执行以下交互，截图记录问题：

| 测试项 | 具体操作 | 通过条件 |
|--------|---------|---------|
| 主要按钮 | 点击页面上所有主要操作按钮 | 有響應，不卡死不报错 |
| Tab 切换 | 点击每个 Tab，确认内容切换 | 对应内容正确显示 |
| 表格下钻 | 点击表格第一行，确认跳转到详情 | 跳转成功，或记录跳转失败 |
| 筛选器 | 在搜索框/下拉框输入/选择值，点击应用 | 列表正确过滤 |
| 空状态 | 筛选出空结果，确认有中文提示 | 显示"无数据"类中文提示而非空白 |
| 错误状态 | 如 404 页面，确认错误提示是中文 | 显示中文错误信息 |

---

### 第四步：检查关键对齐点

在完成全部截图后，重点核查以下已知的潜在不一致项：

#### 4a. 结构层面的缺失
- **01b 时间快照页**：设计稿有 `01_flow_overview_timeline.html`，开发版是否有对应的"时间快照"切换视图？首页是否有切换按钮？
- **导航侧边栏**：开发版的侧边栏菜单项数量是否与设计稿一致？（设计稿要求14个页面入口）

#### 4b. 命名与标签
- 四分流标签是否全部使用全称：`fact_governed` / `fact_pending_observation` / `fact_pending_issue` / `fact_rejected`（不允许缩写如 `pending_obs`）
- `lifecycle_state` 枚举是否统一：`waiting / observing / active / dormant / retired / rejected`
- `health_state` 枚举是否统一：`healthy / insufficient / gps_bias / collision_suspect / collision_confirmed / dynamic / migration_suspect`

#### 4c. Delta 展示规范
- 首页的指标卡是否显示三行格式：当前值 | 本批新增 | 较上批 delta
- 异常数量的 delta 是否使用正确颜色方向（增加 = 恶化 = 红色）

#### 4d. 下钻路径
- 流转总览 → 四分流节点 → 是否有链接？
- 等待/观察工作台 → 候选对象 → 是否跳转到对象详情？
- 异常工作台 → 异常对象行 → 是否跳转到对象详情？

#### 4e. 画像页（09/10/11）共用组件问题
- 三个画像页使用同一个 `ProfileListPage.vue` 组件，检查：
  - LAC 画像是否根据设计稿展示了区域质量标签（`region_quality_label`）？
  - BS 画像是否把旧分类（`classification_v2`）降级为解释层而非主状态？
  - Cell 画像是否展示了基线质心偏差和四分流分布？

---

### 第五步：生成评估报告

将评估结果写入：
```
rebuild3/docs/ui_audit/ui_audit_report.md
```

报告格式如下：

---

```markdown
# rebuild3 UI 双视角对比审计报告

**日期**: [执行日期]
**评估方式**: Antigravity Browser Extension 逐页截图 + 设计稿双视角对比
**设计稿页面数**: 14（HTML 文件）
**开发版路由数**: 13（01b 时间快照页缺失）
**报告受众**: 开发 Agent（无法直接查看页面，依赖本报告理解现状）

---

## 阅读指引

本报告为每个页面提供：
1. 设计稿截图（预期效果）
2. 开发页截图（实际效果）
3. 逐项评分与具体问题描述（精确到 DOM 位置 / CSS 属性 / 文案内容）
4. 开发 Agent 可直接执行的修复建议

---

## 总评

[100 字以内，说明整体完成度、最突出的问题类型，以及缺失的页面]

---

## 逐页评估

### 页面 01a：流转总览 (/flow/overview)

**截图对比**

| 设计稿 | 开发页 |
|--------|--------|
| ![设计稿](screenshots/01a_flow_overview_design.png) | ![开发页](screenshots/01a_flow_overview_dev.png) |

**评分**（每项 1-5 分，5 分为完全符合设计稿）

| 维度 | 得分 | 具体发现 |
|------|------|---------|
| 中文化完整度 | X/5 | [列出所有残留英文，精确到文字内容] |
| 布局与 UI_v2 对齐度 | X/5 | [指出具体哪个区块位置/尺寸不对] |
| 视觉风格 | X/5 | [颜色/字体/间距的具体偏差] |
| 功能完整度 | X/5 | [哪些按钮无效、哪些链接 404、哪些空状态缺失] |
| 信息密度与可扫描性 | X/5 | [首屏关键信息是否可见] |

**功能测试结果**

- [ ] 主要按钮点击：[通过/失败 + 截图路径]
- [ ] 表格/列表下钻：[通过/失败 + 截图路径]
- [ ] 筛选/搜索：[通过/失败 + 截图路径]
- [ ] Tab 切换：[通过/失败 + 截图路径]

**关键问题（供开发 Agent 修复）**

> 问题按严重度排序，描述精确到可执行级别

1. **[P0/P1/P2] 问题标题**
   - 现象：[精确描述，如"表头'状态'列显示英文 Status"]
   - 位置：[如"顶部导航栏第3个菜单项" / "表格第2列表头" / "右侧筛选面板标题"]
   - 设计稿要求：[引用设计稿文案或截图坐标]
   - 修复建议：[如"将 `<th>Status</th>` 改为 `<th>状态</th>`"]

---

### 页面 01b：流转时间快照（开发版缺失）

**状态**: ⚠️ **开发版无对应路由**

**设计稿截图**

| 设计稿 |
|--------|
| ![设计稿](screenshots/01b_flow_timeline_design.png) |

**设计稿描述**：[描述时间快照页的主要内容：3列对比、日期选择器等]

**缺失说明**：设计稿要求流转总览有"流程图版"和"时间快照版"两个视图通过按钮切换。开发版首页未实现时间快照视图，也没有视图切换按钮。

**修复建议**：
- P0：在 `/flow/overview` 页面新增视图切换按钮（流程图版 / 时间快照版）
- P0：实现时间快照版视图（参考 `01_flow_overview_timeline.html`）

---

[对 02-13 每页重复以上格式]

---

## 关键问题汇总（全局，按严重度排序）

| 严重度 | 页面 | 问题类型 | 问题描述 | 修复建议 |
|--------|------|---------|---------|---------|
| P0 | 01b | 页面缺失 | 时间快照视图完全缺失 | 实现时间快照视图和切换按钮 |
| P0 | [页面名] | [中文化/布局/功能/视觉/字段命名] | [精确描述] | [可执行修复步骤] |
| P1 | ... | ... | ... | ... |
| P2 | ... | ... | ... | ... |

---

## 开发优先级建议

### 立即修复（P0，影响可用性或结构完整性）

[列出所有 P0 问题，说明影响]

### 近期修复（P1，影响专业度）

[列出所有 P1 问题]

### 待优化（P2，锦上添花）

[列出所有 P2 问题]

---

*不要美化结果。如实报告你看到的问题。截图是最重要的证据。*
```

---

## 附录：已知背景信息（供审计参考）

以下是审计前已通过代码分析确认的背景信息，不需要重新发现，直接在报告中核实并更新状态：

### 已确认的结构差异

1. **设计稿有 14 个 HTML，开发版有 13 条路由**：`01_flow_overview_timeline.html` 没有对应路由
2. **画像页（09/10/11）共用一个 Vue 组件**：`ProfileListPage.vue` 通过 props 区分类型，需核实功能是否已分别适配

### 设计稿要求的核心规范（审计时必须核对）

来自 `design_notes.md`：
- 所有指标卡必须显示三行格式：当前值 | 本批新增 | 较上批 delta
- 四分流全部使用全称（不允许缩写）
- `rebuild2` 旧分类（`classification_v2` 等）只能作为解释层
- 基线原则必须在相关页面显式可见
- 每个页面必须有进入路径和下钻出口

### 本次审计不需要处理的问题

`rebuild3/docs/UI_v2/audit_deviation_report.md` 记录了**设计稿与业务冻结文档**之间的偏差（如数据库表结构、字段命名等），这是业务问题，不是本次 UI 视觉审计的范围。本次审计只对比**设计稿 HTML 与开发版页面**的视觉和功能差异。