# rebuild3 第二轮 repair 执行说明

更新时间：2026-04-05
对应任务：`docs1/rebuild3_round2_repair_task_doc.md`

## 1. 本轮执行边界

本轮只做“语义回正 + 说真话”修复，没有执行以下动作：

- 没有重跑 `scenario replay` SQL / shell 任务
- 没有重建真实 scenario 治理流水线
- 没有写入新的 compare / governance 实时结果表
- 没有改动 Tier 0 / UI_v2 真相源文档
- 没有执行会修改当前数据库内容的治理重跑

本轮对数据库只做了只读查询，用于确认 `run / batch / baseline_version / obj_*` 的真实现状。

## 2. 已完成的修复包

### A. 统一来源契约

新增统一来源契约输出，后端统一返回：

- `data_origin`
- `origin_detail`
- `subject_scope`
- `subject_note`

涉及接口：

- `/api/v1/runs/flow-overview`
- `/api/v1/runs/flow-snapshots`
- `/api/v1/runs/batches`
- `/api/v1/runs/baseline-profile`
- `/api/v1/runs/initialization`
- `/api/v1/compare/overview`
- `/api/v1/compare/diffs`
- `/api/v1/governance/*`

统一逻辑落在：`rebuild3/backend/app/api/run_shared.py`

本轮对外合同只保留三类来源：

- `real`
- `synthetic`
- `fallback`

### B. `/flow/snapshot` 回正为“诚实快照页”

修复结果：

- 正式快照选择器不再收录 synthetic `scenario_replay`
- `full_initialization` 不再混入时间点快照下拉
- 当前没有真实 timepoint snapshot 时，页面改为显式 synthetic 评估模式，而不是继续伪装成正式快照
- 页面不再展示 synthetic 百分比对照，因此不再出现 `2437.4%`、`5025.1%`、`10896.5%` 一类错误值
- 场景标签补充 `scenario_key`，smoke 场景显示 `[SMOKE]`

当前结果：

- `/flow/snapshot` 首屏默认加载 `INIT2D_STEP2H` synthetic 场景，便于功能评估
- 首屏 banner 明确提示：`当前暂无真实时间点快照，已自动切换到 synthetic scenario 评估模式；仅供功能验证，不代表正式主流程结果。`

### C. `/flow/overview` 与 `/runs` 主语回正

`/flow/overview`：

- 取消 sample validation 作为 delta 基线
- 仅接受真实 batch 作为主语
- 当前正式库没有可用真实 batch 时，页面自动切换到 synthetic 场景批次用于功能评估，并显式显示 synthetic banner
- `compare_callout` 不再使用历史硬编码数字伪装当前结论

`/runs`：

- 数据源改为 `rebuild3_meta.run + rebuild3_meta.batch + rebuild3_meta.batch_snapshot`
- 主列表变为 run 级条目，不再是 sample/full 两条伪批次
- 每个 run 带批次子列表、趋势区和详情区
- synthetic run 在主列表和子列表中都显示显式标记，不再伪装成正式结果

### D. `/baseline` 与 `/initialization` 主语修正

`/baseline`：

- 页面只回答“当前正式 baseline 版本”
- 当前版本指向 `BASELINE-FULL-V1`
- 没有上一版时，明确显示：`暂无上一版 baseline，无法比较版本差异。`
- 不再用 rebuild2 对照结果冒充版本差异

`/initialization`：

- 页面主体切回真实 full initialization run/batch
- 当前 run 为 `RUN-FULL-20251201-20251207-V1`
- API 顶层与 `context` 同步暴露 `run_id / batch_id`
- 因当前 initialization 汇总快照仍属估算写入，所以显式标记为 `synthetic`
- 不再使用 sample validation 作为初始化页主语

### E. `/compare` 与 `/governance` fallback 透明化

后端继续保留 fallback 数据，但前后端统一显式降级。

当前页面首屏固定展示 banner：

- `/compare`：`当前为 fallback 对照结果，仅供参考，不代表实时比对结果`
- `/governance`：`当前为 fallback 资产目录，仅供梳理，不代表已接入实时元数据注册表`

同时，页面上的按钮文案已避免继续暗示“实时结果”。

### F. 字段表达漂移修复

LAC：

- `region_quality_label` 由技术码改为稳定中文展示
- 原始技术码保留在 `region_quality_code`
- 当前已验证 `issue_present -> 存在问题`、`coverage_insufficient -> 覆盖不足`

BS：

- 列名改为 `GPS质量(参考)`
- 不再把该列伪装成旧的 `gps_confidence`
- 无真实来源的 `信号可信度(参考)` 主表列已移除

Cell：

- 对象质心改为读取 `obj_cell.centroid_*`，经 API 输出为页面主坐标字段
- `stg_cell_profile.center_*` 改为 `profile_center_*` 参考字段，不再与对象质心混名
- 原 `bs_gps_quality` 明确改名为 `BS侧GPS质量(参考)`
- 页面补充 `coordinate_source_note`，说明主坐标与参考坐标来源

## 3. 新增 / 调整文件

后端：

- `rebuild3/backend/app/api/run_shared.py`
- `rebuild3/backend/app/api/run.py`
- `rebuild3/backend/app/api/run_snapshot.py`
- `rebuild3/backend/app/api/run_workspaces.py`
- `rebuild3/backend/app/api/object_common.py`
- `rebuild3/backend/app/api/compare.py`
- `rebuild3/backend/app/api/governance.py`

前端：

- `rebuild3/frontend/src/components/OriginBadge.vue`
- `rebuild3/frontend/src/components/DataOriginBanner.vue`
- `rebuild3/frontend/src/pages/FlowSnapshotPage.vue`
- `rebuild3/frontend/src/pages/FlowOverviewPage.vue`
- `rebuild3/frontend/src/pages/RunBatchCenterPage.vue`
- `rebuild3/frontend/src/pages/BaselineProfilePage.vue`
- `rebuild3/frontend/src/pages/InitializationPage.vue`
- `rebuild3/frontend/src/pages/ValidationComparePage.vue`
- `rebuild3/frontend/src/pages/GovernancePage.vue`
- `rebuild3/frontend/src/pages/BsProfilePage.vue`
- `rebuild3/frontend/src/pages/CellProfilePage.vue`

测试与验收补充：

- `rebuild3/tests/round2_repair_api_smoke.py`
- `docs1/Claude_field_baseline.md`

## 4. fallback / synthetic 展示策略

### fallback banner 页面

- `/compare`
- `/governance`

### synthetic 小标记 / 提示页面

- `/runs`（run 列表、批次子列表、详情区）
- `/initialization`

### synthetic 评估模式页面

- `/flow/snapshot`
- `/flow/overview`

## 5. 验收执行结果

### 5.1 后端静态检查

执行：

```bash
python3 -m py_compile \
  rebuild3/backend/app/api/run_shared.py \
  rebuild3/backend/app/api/run.py \
  rebuild3/backend/app/api/run_snapshot.py \
  rebuild3/backend/app/api/run_workspaces.py \
  rebuild3/backend/app/api/compare.py \
  rebuild3/backend/app/api/governance.py \
  rebuild3/backend/app/api/object_common.py \
  rebuild3/backend/app/api/object_detail.py \
  rebuild3/backend/app/api/object.py \
  rebuild3/backend/app/api/main.py
```

结果：通过。

### 5.2 前端构建检查

执行：

```bash
cd rebuild3/frontend
npm run build
```

结果：通过。

### 5.3 API smoke 验收

验收脚本：`rebuild3/tests/round2_repair_api_smoke.py`

执行：

```bash
python3 rebuild3/tests/round2_repair_api_smoke.py
```

结果：`round2 repair api smoke: ok`

脚本覆盖点：

- `/api/v1/runs/flow-snapshots` 在无真实时间点时自动切换到 synthetic 评估模式，并保留显式 banner
- `/api/v1/runs/flow-overview` 不再使用 sample delta；无真实 batch 时自动切换到 synthetic 评估批次
- `/api/v1/runs/batches` 改为真实 run/batch 目录
- `/api/v1/runs/baseline-profile` 不再伪造上一版 baseline
- `/api/v1/runs/initialization` 指向真实 full initialization run
- `/api/v1/compare/overview`、`/api/v1/governance/overview` fallback 标记
- `/api/v1/objects/profile-list` 中 LAC / BS / Cell 字段表达修复

### 5.4 Playwright 页面验收

已通过 Playwright 逐页复查以下页面：

- `/flow/snapshot`：首屏已加载 synthetic 场景数据，可切换时间点，且未见离谱百分比
- `/flow/overview`：首屏已加载 synthetic 批次流转，可评估流程图、累计状态与问题入口
- `/runs`：主列表为 run 级目录，synthetic run 显式带标记
- `/baseline`：当前版本为 `BASELINE-FULL-V1`，明确提示无上一版可比
- `/initialization`：主体 run 为 `RUN-FULL-20251201-20251207-V1`，首屏显示 synthetic 提示
- `/compare`：首屏可见 fallback banner
- `/governance`：首屏可见 fallback banner
- `/profiles/lac`：页面展示 `存在问题` 等中文标签，不再直出技术码
- `/profiles/bs`：首表列名为 `GPS质量(参考)`，无“信号可信度(参考)”假列
- `/profiles/cell`：首表列名为 `BS侧GPS质量(参考)`，展开区明确区分对象质心与画像参考中心

补充结果：浏览器控制台未发现错误级报错。

## 6. 当前剩余事实与后续边界

以下不是本轮缺陷，而是本轮刻意保留的真实状态：

- 当前仍然没有“真实时间点快照”，因此 `/flow/snapshot` 现在采用显式 synthetic 评估模式供功能验证
- 当前仍然没有可作为 `/flow/overview` 主语的真实 batch，因此该页现在采用显式 synthetic 批次供流程评估
- 当前 `scenario_replay` 与 `full_initialization` 的汇总快照仍属 `synthetic`
- `/compare` 与 `/governance` 仍然是 fallback 数据，只是现在已经显式告知用户

下一轮如要推进，必须单独立项：

1. 重建真实 scenario replay 治理链
2. 建 compare 实时结果表 / 读模型
3. 建 governance 实时元数据注册表
4. 继续清理 `rebuild3_sample_meta` 的正式归属
