# 第二轮最终审计报告

> 合并日期：2026-03-24
> 审计来源：Codex / Claude / Gemini

## 1. 维度评定总表

| 维度 | Codex | Claude | Gemini | 合并判定 |
|------|-------|--------|--------|---------|
| A 性能与缓存 | 未通过 | 未通过 | 未通过 | 必须修改 |
| B UI完整性 | 未通过 | 未通过 | 未通过 | 必须修改 |
| C 可理解性 | 未通过 | 部分通过 | 未通过 | 必须修改 |
| D 代码/架构 | 部分通过 | 部分通过 | 部分通过 | 必须修改 |

## 2. 审计质量评估

- Codex 审计最充分，尤其是性能证据、PG17 实际规模、V2 UI 对比和中文化缺口梳理最细；本次合并优先采信其 A/B 维度结论。
- Claude 审计充分，在 API 覆盖率、异常处理、连接池、workbench/meta 表覆盖率方面补足了架构视角。
- Gemini 审计也提供了完整证据，不属于敷衍审计；但在 C/D 维度判定偏乐观。合并时采纳其数据和改造建议，不采纳其“问题较轻”的结论。

## 3. 必须修改项（按优先级排序）

| # | 优先级 | 问题 | 涉及文件 | 具体修改方案 | 工作量 |
|---|--------|------|---------|------------|--------|
| 1 | P0 | `metrics.py` 和部分 `pipeline.py` 端点直接对 `pipeline.raw_records`、`fact_*`、`profile_*` 做实时聚合，首页首屏默认触发重型查询，性能模型错误。 | `rebuild/backend/app/api/metrics.py`；`rebuild/backend/app/api/pipeline.py`；新增 `rebuild/backend/app/services/snapshot_service.py` 或等价模块；Run 完成回写脚本/Worker | 把 `GET /metrics/layer-snapshot`、`/metrics/step-summary`、`/metrics/anomaly-summary` 改为只读 `workbench.wb_layer_snapshot`、`wb_step_metric`、`wb_anomaly_stats`；把 `GET /pipeline/stats/operator-tech`、`/gps-status`、`/signal-fill` 改成读取物化视图或快照表；在 Run 完成路径中新增“写快照/刷新物化视图”步骤；接口统一补 `generated_at`、`source`、`cache_hit` 字段，禁止首页再直接扫大表。 | 中 |
| 2 | P0 | 前端没有任何缓存、请求去重、刷新控制或降级策略；`loadOverview()` / `loadAnomaly()` / `loadStep()` 每次切页都重查，放大了后端慢查询问题。 | `rebuild/frontend/app.js`；`rebuild/frontend/index.html` | 重写 `api()` 为带 TTL、内存去重、`sessionStorage` 缓存、`force` 参数和超时控制的统一数据层；`loadOverview()` 先渲染缓存快照再后台刷新；顶部上下文条新增“上次刷新时间 / 刷新缓存 / 强制重算”；`Promise.all` 改为带页面级兜底的加载逻辑，失败时回退到 stale cache，不让页面卡死在“加载中”。 | 中 |
| 3 | P0 | P2 步骤工作台只实现了 A/B/D 的简化版本，核心的规则、SQL、数据变化、差异、样本全部缺失，当前页面不足以支持调试与验证。 | `rebuild/frontend/app.js`；`rebuild/frontend/index.html`；`rebuild/backend/app/main.py`；`rebuild/backend/app/api/steps.py`；新增 `rebuild/backend/app/api/version.py`、`fields.py`、`samples.py` 或等价路由 | 在后端新增 `GET /steps/{step_id}/rules`、`/sql`、`/metrics`、`/diff`、`/samples`，数据分别来自 `wb_rule_hit`、`wb_sql_bundle`、`wb_step_metric`、compare-run 差异查询、`wb_sample_set`；前端把 `loadStep()` 拆成 `renderStepIntro/renderStepIO/renderStepRules/renderStepSql/renderStepMetrics/renderStepDiff/renderStepSamples/renderStepActions`，补齐 V2 的 8 个区块和操作区，不再只渲染 IO/参数表。 | 大 |
| 4 | P1 | P1 总览、P3 字段治理、P4 样本研究以及 D1/D2/D3 抽屉大面积缺失，当前 UI 只覆盖了 V2 的一小部分。 | `rebuild/frontend/index.html`；`rebuild/frontend/app.js`；`rebuild/backend/app/main.py`；新增版本/字段/样本相关 API；`rebuild/launcher_web.py` | `index.html` 恢复 `P1/P3/P4` 主导航和抽屉挂载点；`loadOverview()` 新增当前 Run 摘要、Compare Run 摘要、步骤差异摘要、重点关注和操作区；后端补 `GET /version/current`、`/version/history`、`/fields`、`/fields/{field}`、`/samples`、`/samples/{id}` 等接口；`launcher_web.py` 同步补 P3/P4 链接和快照刷新入口。 | 大 |
| 5 | P1 | 用户可见英文名过多，数据库注释体系基本空白，中文步骤名虽然已接入，但层级码、表名、异常码、参数键名、Launcher 文案仍直接暴露英文。 | `rebuild/frontend/app.js`；`rebuild/frontend/index.html`；`rebuild/launcher_web.py`；新增数据库注释/初始化 SQL；可选新增 `meta` 初始化脚本 | 基于 `Doc02` 的表映射和字段映射补 `COMMENT ON TABLE/COLUMN`，初始化 `meta.meta_field_registry.field_name_cn`；后端接口返回 `code + label` 双字段，如 `table_name/table_name_cn`、`anomaly_type/anomaly_type_cn`；前端统一“中文主展示 + 英文码灰字附属”；步骤页默认只显示 `step_name`，把 `step_name_en` 放到 tooltip 或技术详情；`index.html` `<title>` 和 `launcher_web.py` 按钮/页面名改中文。 | 中 |
| 6 | P1 | 当前架构仍是 router 直接写 SQL，缺 service/cache 层；同时缺少全局异常处理、查询超时、运行状态校验，稳定性和可维护性不足。 | `rebuild/backend/app/main.py`；`rebuild/backend/app/core/database.py`；`rebuild/backend/app/core/config.py`；`rebuild/backend/app/api/runs.py`；`rebuild/backend/app/api/pipeline.py`；`rebuild/backend/app/api/metrics.py` | 新增 `services/` 层承接快照读取、翻译字典、缓存和版本上下文拼装；`database.py` 增加 `statement_timeout`/`pool_timeout` 并按慢查询修复后再评估 `pool_size`；`main.py` 增加统一异常处理；`runs.py` 在 `PATCH /runs/{id}/status` 中检查 `UPDATE ... RETURNING` 是否命中，避免不存在的 run 也返回成功；`config.py` 去掉源码中的明文连接串，改为 `.env` 驱动。 | 中 |

## 4. 建议改进项

| # | 建议 | 收益 | 成本 |
|---|------|------|------|
| 1 | 把 `pipeline/stats/operator-tech`、`/gps-status`、`/signal-fill` 从公共首屏能力降级为“详情页 + 手动刷新”的探索接口。 | 立刻缩小首屏性能风险，避免重型统计再次回到公共路径。 | 小 |
| 2 | 流程节点和步骤标签从 `workbench.wb_step_registry` 动态派生，不再在 `app.js` 中硬编码。 | 避免中文名、层级和步骤顺序再次与注册表脱节。 | 小 |
| 3 | 前端把 `Promise.all` 改为 `Promise.allSettled`，并为各卡片增加局部错误块。 | 局部接口失败时页面仍可用，调试体验明显更稳。 | 小 |
| 4 | 补 URL hash 路由和可分享链接。 | P1/P2/P3/P4 与具体步骤/样本可以直接跳转，便于协作。 | 中 |
| 5 | 前端渲染函数继续拆分，减少单文件模板字符串堆积。 | 为后续补齐 P3/P4/D1-D3 降低维护成本。 | 中 |

## 5. 最终结论与行动计划

**结论：** 需修改后可用

**修改顺序建议：**
1. 先修性能根因：让 Run 完成后写入 `wb_layer_snapshot`、`wb_step_metric`、`wb_anomaly_stats`，并把 `metrics.py`/重型 `pipeline.py` 端点改成只读快照或物化视图。
2. 再补后端基础设施：建立 `services/` 层，加入缓存、查询超时、异常处理、Run 状态校验，并补齐规则/SQL/差异/样本/版本/字段 API。
3. 然后重构前端数据层：统一缓存 API、刷新控件、页面级错误恢复和 stale cache 回退。
4. 接着补核心 UI：先补 P2 的 8 个区块和操作区，再补 P1 的 compare/diff/focus，再恢复 P3/P4 和 D1/D2/D3。
5. 最后完成中文化和元数据治理：补数据库注释、接口 `code + label`、前端中文主展示、Launcher 中文化，并把所有字典沉淀到 `meta`/版本化资源中。
