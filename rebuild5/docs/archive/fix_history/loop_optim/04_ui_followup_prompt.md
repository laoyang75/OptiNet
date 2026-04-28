# OptiNet rebuild5 / loop_optim / 04 UI 跟进 — 后端 API + 前端组件(agent 新实例对话)

## § 1 元目标

把 fix5/fix6/loop_optim 累积的 3 块清洗规则 / 算法成果在前端暴露,**让运营 / 研究人员能在治理页看到**:

- **C 块:ODS 规则 hit count**(ODS-019/020/021/022/023b/024b)— ETL 清洗各规则被命中多少行,数据质量监控
- **D 块:device-weighted p90 可视化**(`docs/gps研究/12_单设备污染与加权p90方案.md`)— 单设备污染识别 + 加权 p90 统计
- **E 块:TA 字段筛选** — fix5 期间已经在 CellMaintain.vue 加了基础展示,这次补**筛选条件**(TA 估距区间 / freq_band / ta_verification)

**已经做的(本 prompt 不重做)**:
- ✅ A. 升级后版本信息显示(GovernanceOverview.vue 已加版本条:PG 18.3 / Citus 14 / PostGIS 3.6.3 / 4 worker / 5487 fallback)
- ✅ B. drift_pattern 8 类分布(GovernanceOverview.vue 已修 driftKeys 为 8 类对齐数据库)

## § 2 上下文启动顺序

按序读完直接开干:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/PROJECT_STATUS.md` —— 当前生产环境
3. `rebuild5/docs/runbook.md` —— 操作手册
4. `rebuild5/docs/fix6_optim/_prompt_template.md` § 11/§ 12
5. `rebuild5/docs/01b_数据源接入_处理规则.md` —— **C 块依据**:ODS-019/020/021/022/023b/024b 各规则定义
6. `rebuild5/docs/gps研究/12_单设备污染与加权p90方案.md` —— **D 块算法依据**
7. `rebuild5/backend/app/etl/clean.py` / `parse.py` / `fill.py` —— C 块需要的 hit count 在哪生成
8. `rebuild5/backend/app/maintenance/cell_maintain.py` —— device-weighted p90 算法实现位置
9. `rebuild5/frontend/design/src/views/governance/CellMaintain.vue` —— E 块要补筛选条件的页面
10. `rebuild5/frontend/design/src/views/governance/GovernanceOverview.vue` —— A/B 已完成,做参考
11. `rebuild5/frontend/design/src/api/maintenance.ts` / `etl.ts` —— 后端 API 入口
12. 本 prompt

读完直接开干。

## § 3 环境硬信息

- 仓库:`/Users/yangcongan/cursor/WangYou_Data`
- 生产 Citus(只读):`postgres://postgres:123456@192.168.200.217:5488/yangca`,MCP `mcp__PG_Citus__execute_sql`
- 前端:Vue 3 + TypeScript,目录 `rebuild5/frontend/design/`
- 启动 dev server:`cd rebuild5/frontend/design && npm run dev`(假设依赖已装)
- 后端 FastAPI:`rebuild5/backend/app/`,routers 在 `app/routers/`

## § 4 关联文档清单

| 路径 | 阅读 / 修改 |
|---|---|
| `rebuild5/docs/01b_数据源接入_处理规则.md` | 阅读 — ODS 规则定义 |
| `rebuild5/docs/gps研究/12_*.md` | 阅读 — 加权 p90 算法 |
| `rebuild5/backend/app/etl/clean.py` | **可能修改** — C 块需要在 ETL 期间记 hit count(rb5_meta.etl_rule_stats 或类似表) |
| `rebuild5/backend/app/routers/etl.py` | 修改 — C 块新加 endpoint `/etl/rule-stats` |
| `rebuild5/backend/app/routers/maintenance.py` | 修改 — D 块新加 endpoint `/maintenance/device-weighted-p90` |
| `rebuild5/frontend/design/src/api/etl.ts` | 修改 — 加 C 块 API client |
| `rebuild5/frontend/design/src/api/maintenance.ts` | 修改 — 加 D 块 API client |
| `rebuild5/frontend/design/src/views/etl/`(可能新建)| 新建 — C 块新页面 `RuleStats.vue` |
| `rebuild5/frontend/design/src/views/governance/CellMaintain.vue` | 修改 — E 块加筛选条件 |
| 本阶段产出 `04_ui_followup_report.md` | 新建 |

## § 5 任务清单(按优先级)

### 阶段 1:C 块 — ODS 规则 hit count(高优先级,~半天)

#### 5.1.1 后端

1. **决定数据来源**:
   - 选项 A:ETL 期间在 `clean.py` / `parse.py` / `fill.py` 里记数,落 `rb5_meta.etl_rule_stats` 表(每批一条:batch_id, rule_code, hit_count, time)
   - 选项 B:从已有 `rb5.etl_*` 表反推(查特定 cell_origin / freq_channel / age 条件命中量)
   - **选 A**:精确,但要改 ETL 代码 + 加一张 reference table。
   - 如果 user 的 backend 没运行(你看不到运行时),只做 schema + endpoint scaffold,数据 0 行也接受;ETL 改动留给以后实际运行时

2. **新加 router endpoint**:`GET /etl/rule-stats?batch_id=<n>&rule_code=<str>`
   - 返回:`[{batch_id, rule_code, rule_desc, hit_count, total_rows, hit_pct, recorded_at}]`

3. **schema(如果选 A)**:
   ```sql
   CREATE TABLE IF NOT EXISTS rb5_meta.etl_rule_stats (
       batch_id INTEGER NOT NULL,
       rule_code TEXT NOT NULL,            -- 'ODS-019' / 'ODS-020' / ...
       rule_desc TEXT,                     -- 一句话规则说明
       hit_count BIGINT NOT NULL,          -- 命中行数
       total_rows BIGINT,                  -- 当时总行数(算 hit_pct 用)
       recorded_at TIMESTAMPTZ DEFAULT NOW(),
       PRIMARY KEY (batch_id, rule_code)
   );
   SELECT create_reference_table('rb5_meta.etl_rule_stats');
   ```

#### 5.1.2 前端

1. 新建页面 `views/etl/RuleStats.vue`
2. UI 元素:
   - 顶部 batch_id 选择器(默认最新)
   - 表格 columns:rule_code, rule_desc, hit_count(右对齐 numeric), hit_pct(进度条), recorded_at
   - 按 hit_count 降序
   - rule_code 可点击 → 弹出 modal 显示该规则全文(从 `01b_数据源接入_处理规则.md` 拉)— 如果 backend 没暴露 rule 全文,就硬编码到前端 i18n

3. 路由:`/etl/rule-stats`(在 router 里加一项)
4. 导航菜单:加链接(可能在 ETL 一级菜单下)

### 阶段 2:D 块 — device-weighted p90 可视化(中优先级,~半天)

#### 5.2.1 后端

1. 看 `cell_maintain.py` 已经计算的 device-weighted p90 字段是否落表
2. 如果有(很可能在 `rb5.cell_metrics_base` 或类似),直接 endpoint 暴露:
   - `GET /maintenance/device-weighted-p90?cell_id=<bigint>`
   - 返回:`{cell_id, p90_unweighted_m, p90_device_weighted_m, top_polluting_devices: [{dev_id, weight, contribution_pct}], delta_pct}`
3. 如果没落表,**先在 cell_maintain.py 里增量计算 + 落 reference table** `rb5.cell_p90_weighted_summary`(per-cell per-batch)

#### 5.2.2 前端

1. 在 `views/governance/CellMaintain.vue` 详情面板里加一个新 tab "加权 P90"
2. UI 元素:
   - 双 bar 对比(unweighted vs device-weighted)
   - top 5 污染设备列表(dev_id mask 化展示,weight + contribution%)
   - delta % 显示("加权后半径减少 X%")
3. 默认折叠,点击 cell 详情才展开

### 阶段 3:E 块 — CellMaintain TA 筛选(低优先级,~2 小时)

#### 5.3.1 前端(纯前端工作,无需后端改动)

CellMaintain.vue 已经有 TA 字段展示,加**筛选条件**(已有 list 页过滤器):

1. 加 4 个新筛选条件控件:
   - **TA 估距区间**:double slider(0-1300m,步进 50m)
   - **freq_band**:dropdown(Bnn / 4G / 5G 全选)
   - **ta_verification**:checkbox 多选(verified / disputed / unverified)
   - **timing_advance 是否有值**:三态(有 / 无 / 全部)

2. 筛选逻辑:client-side(数据已 in-memory)or server-side(改 maintenance API 加 query params)
   - **倾向 client-side**(简单),除非数据量超 1000 行不分页

3. 筛选后展示 hit count 在筛选区右上角

### 不做(显式禁止)

- ❌ 不重做 A/B 块(版本条 + drift_pattern 8 类已完成)
- ❌ 不改 backend 业务逻辑(只加 endpoint 暴露已有数据,不改 ETL 业务规则)
- ❌ 不引入新前端 lib(echarts / chart.js 等如果还没装就用 SVG/CSS 简易实现)
- ❌ 不动 fix5/fix6/loop/upgrade 已交付产物
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc

## § 6 验证标准

1. **C 块**:`/etl/rule-stats` endpoint 返回 6+ 条 ODS 规则数据(可能是 0 hit count,但 schema 全);前端页面渲染表格 + 进度条
2. **D 块**:`/maintenance/device-weighted-p90?cell_id=...` 返回 polluting 设备列表;前端 CellMaintain 详情有"加权 P90"tab
3. **E 块**:CellMaintain 列表页有 4 个 TA 筛选控件,筛选生效 + hit count 显示
4. **前端构建无错**:`cd rebuild5/frontend/design && npm run build`(如果 deps 装了)/ 或 `vue-tsc --noEmit` 类型检查无错
5. **commit + push**(允许标 push pending)
6. **note `loop_optim_04_ui_done`** 写入

## § 7 产出物 `04_ui_followup_report.md`

```markdown
# loop_optim / 04 UI 跟进报告

## 0. TL;DR
- C 块(ODS 规则 hit count):后端 endpoint + 前端页面 RuleStats.vue 已落地;hit count 数据来源 = <选项 A/B>
- D 块(device-weighted p90):后端 endpoint + 前端 CellMaintain "加权 P90" tab 已落地
- E 块(TA 筛选):4 个筛选控件已加,client-side 过滤
- 已确认 A/B 块(GovernanceOverview 版本条 + drift 8 类)是 Claude 做的,不重做
- commit SHA / push 状态

## 1. C 块实现细节
- schema 决策(选项 A 落表 / B 反推)
- router endpoint signature
- 前端页面截图(可选)+ 关键代码节选

## 2. D 块实现细节
- 后端算法位置(cell_maintain.py 哪行)
- 前端组件位置 + tab 集成方式

## 3. E 块实现细节
- CellMaintain.vue 改动 diff 节选
- client-side filter 逻辑

## 4. 前端构建验证
- `npm run build` 输出 / `vue-tsc --noEmit` 输出

## 5. 已知限制
- 后端 ETL 期间真实 hit count 还需要 user 触发一次 reset+rerun 才能填充(本 prompt 不跑 runner)
```

## § 8 notes 协议

- 完工:`loop_optim_04_ui_done` info,body 含 C/D/E 三块各完成情况 + commit SHA

## § 9 完工话术

> "loop_optim 04 UI 跟进完成。04_ui_followup_report.md 已写入。C 块(ODS 规则 hit count) / D 块(device-weighted p90) / E 块(TA 筛选)三块各落地。前端 build 无错。commit=<SHA>(push <成功/pending>)。notes `topic='loop_optim_04_ui_done'` 已插入。A/B 块(版本条 + drift 8 类)由 Claude 直接做了,本 prompt 不重做。"

## § 10 失败兜底

- **C 块 backend 没运行无法测真实数据**:只 scaffold schema + endpoint + 前端 mock 数据,在报告 §1 标"等 ETL 重跑后 backfill"
- **D 块算法字段没在数据库里**:写一个简单的 fallback 算法(假设固定 weight=1/n_dev,只暴露 unweighted p90)+ 在报告 §2 标"完整加权 p90 等待 backend 实现"
- **前端 deps 没装 / build 失败**:不强制 build,只 `vue-tsc --noEmit` 类型检查;或者标"前端 build 待 user 跑 npm install"
- **路由配置位置不明显**:grep `path:` 找现有 router 配置,加一行
- **任何挂** → blocker note + 报告完整 traceback
