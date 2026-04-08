# 当前目录审计（Gate A0）

> 审计时间：2026-04-05  
> 审计依据：`04f_prompt_开发实施_UI优先纠偏与归档版.md`、冻结文档、`UI_v2` 基线、当前 `rebuild3/` 目录与实际数据库状态。

## 1. 当前目录主要模块树

```text
rebuild3/
├── docs/                  # 冻结文档、UI_v2 基线、样本/全量报告、纠偏输入
├── backend/
│   ├── sql/               # schema、sample/full pipeline、compare SQL
│   ├── scripts/           # sample/full pipeline 执行脚本
│   └── app/               # FastAPI 读模型 API，当前仅 Cell 方向较完整
├── frontend/              # Vue 3 + TS + Vite；当前为 Cell 局部 spike
├── launcher/              # 仅 README 占位，未形成正式启动器
├── config/                # thresholds / versions / services / compare_rules
├── .logs/                 # 样本/全量执行日志
└── README.md              # 仍停留在样本 Gate 叙述
```

## 2. 已存在成果

### 2.1 已形成、且具备复用价值的正式资产

- 冻结文档齐全：`rebuild3/docs/01_rebuild3_说明_最终冻结版.md`、`rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`、`rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`
- `UI_v2` 设计基线齐全：`rebuild3/docs/UI_v2/`
- 独立 schema 与主链路 SQL 已落地：
  - `rebuild3/backend/sql/schema/001_foundation.sql`
  - `rebuild3/backend/sql/govern/001_rebuild3_sample_pipeline.sql`
  - `rebuild3/backend/sql/govern/002_rebuild3_full_pipeline.sql`
  - `rebuild3/backend/sql/compare/002_prepare_full_compare.sql`
- 样本/全量验证报告齐全：
  - `rebuild3/docs/sample_scope.md`
  - `rebuild3/docs/sample_run_report.md`
  - `rebuild3/docs/sample_compare_report.md`
  - `rebuild3/docs/full_run_report.md`
  - `rebuild3/docs/full_compare_report.md`
- 运行配置已形成：`rebuild3/config/*.yaml`
- 实际数据库中已存在可用正式表：
  - `rebuild3.obj_cell / obj_bs / obj_lac`
  - `rebuild3.fact_*`
  - `rebuild3.baseline_*`
  - `rebuild3_meta.run / batch / baseline_version / batch_snapshot / batch_flow_summary / batch_anomaly_summary / batch_baseline_refresh_log`

### 2.2 已存在但只属于部分实现的资产

- `rebuild3/backend/app/api/object.py`
  - 已具备 Cell 列表、详情、画像接口与 SQL fallback
  - 但仍明显偏向 Cell 局部工作台，不足以覆盖 `UI_v2` 页面全集
- `rebuild3/frontend/`
  - 已具备 Vue/Vite 脚手架与少量复用组件
  - 但当前路由、布局、页面边界与 `UI_v2` 正式 IA 明显不一致

## 3. 哪些成果符合 `04e`

### 3.1 基本符合 `04e` 的部分

- 独立 schema 原则：已做到不写回 `rebuild2*`
- 样本先行、双跑、偏差评估、全量运行：均已形成可复用结果
- 配置文件与目录骨架：已存在
- 样本与全量日志：可追溯

### 3.2 未满足 `04e` / `04f` 正式交付要求的部分

- `UI_v2` 没有被当作正式页面基线完整实现
- `launcher/` 未落地，用户无法按现有交付物独立启动系统
- `run.py`、`compare.py`、`governance.py` 仍是占位骨架
- 共享组件域未形成统一的 `VersionContext`、四分流组件、健康/资格状态表达
- 页面级验收报告与页面-API-数据追踪矩阵缺失

## 4. 哪些成果只属于 spike

以下内容应认定为 2026-04-04 这轮偏航 UI spike：

- `rebuild3/frontend/src/App.vue`
- `rebuild3/frontend/src/main.ts`
- `rebuild3/frontend/src/router.ts`
- `rebuild3/frontend/src/styles.css`
- `rebuild3/frontend/src/lib/cellApi.ts`
- `rebuild3/frontend/src/lib/format.ts`
- `rebuild3/frontend/src/components/BadgePill.vue`
- `rebuild3/frontend/src/components/MetricBars.vue`
- `rebuild3/frontend/src/components/QualificationStrip.vue`
- `rebuild3/frontend/src/pages/CellObjectsPage.vue`
- `rebuild3/frontend/src/pages/CellDetailPage.vue`
- `rebuild3/frontend/src/pages/CellProfilePage.vue`

原因：这些文件围绕 Cell 局部工作台构建，不符合 `UI_v2` 全量页面体系、三组侧边栏结构与启动器独立入口要求。

## 5. 建议保留复用的对象

### 5.1 直接保留复用

- `rebuild3/docs/UI_v2/` 全量设计资产
- `rebuild3/docs/Docs/UI_v2_审计后修改执行清单.md`
- `rebuild3/docs/Docs/rebuild3_开发文档最终修订补丁.md`
- `rebuild3/backend/sql/` 下 schema / sample / full / compare SQL
- `rebuild3/backend/scripts/run_sample_pipeline.py`
- `rebuild3/backend/scripts/run_full_pipeline.py`
- `rebuild3/config/*.yaml`
- `rebuild3/.logs/*`
- 数据库中的 `rebuild3*` / `rebuild3_meta*` 实际产物

### 5.2 保留但需重构后吸收

- `rebuild3/backend/app/api/object.py`
  - 复用其中的 DB 连接、Cell 快照序列化、部分 compare 逻辑
  - 但需重构为面向全页面的读模型 API
- `rebuild3/frontend/package.json`、`tsconfig.json`、`vite.config.ts`
  - 工具链可以保留
  - 页面、路由、样式和数据层需正式重建

## 6. 新实现完成后应归档的对象

归档时机：Gate F 通过后。

### 6.1 归档到 `rebuild3/archive/20260404_ui_spike/`

- 2026-04-04 Cell spike 前端源码（见第 4 节清单）
- 若对象读模型 API 被整体重写，则归档旧版 `rebuild3/backend/app/api/object.py`

### 6.2 保留但不归档

- 样本/全量 SQL 与报告
- `UI_v2` 原型与冻结文档
- 运行日志 `.logs/`

## 7. 生成产物：应清理而非归档

以下内容属于可再生产物，不做历史归档：

- `rebuild3/frontend/dist/`
- `rebuild3/frontend/node_modules/`
- `rebuild3/frontend/node_modules/.vite/`
- `rebuild3/frontend/node_modules/.vite-temp/`

处理策略：新实现完成后清理并重建，在 `archive_execution_report.md` 中留痕即可。

## 8. 审计结论

- 数据主链路、样本/全量双跑、对比报告属于正式可复用资产，不应推倒重来。
- 当前真正缺的是：`UI_v2` 页面全集落地、启动器、页面级 API 闭环、可运行交付与最终归档治理。
- 因此后续实施策略应是：**保留 SQL/数据主链路，重建前端页面体系与 API 读模型，补齐启动入口，再执行 spike 归档。**
