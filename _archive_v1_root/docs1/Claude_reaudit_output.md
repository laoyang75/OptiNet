# rebuild3 系统级独立复评报告（Claude 专版）

> 评估时间：2026-04-05  
> 评估者：Claude（独立复评，未参考任何已有审计输出文档）  
> 输出路径：`docs1/Claude_reaudit_output.md`（主报告）、`docs1/Claude_field_baseline.md`（字段基线）  
> 截图路径：`docs1/claude_reaudit/*.png`

---

## 第一部分：总评结论

| 维度 | 结论 |
|---|---|
| **总评** | ❌ **不通过** |
| **核心原因** | `/runs` 批次中心与 `/initialization` 页面主语严重跑偏：前者被硬编码为 `FULL_BATCH_ID`/`SAMPLE_BATCH_ID` 两行固定数据，完全忽略 scenario_replay 类型 run 的真实批次数据；后者仍指向 `SAMPLE` 类型 run。`/flow/snapshot` 的场景下拉混入了 `full_initialization` 类型 run。`/compare` 和 `/governance` 返回 `data_origin=fallback_catalog` 但前端无可见 fallback banner。 |
| **P0 数量** | **4** |
| **P1 数量** | **3** |
| **P2 数量** | **3** |
| **P3 数量** | **2** |
| **是否允许进入下一阶段实施** | ❌ 否，P0 问题阻断 |
| **当前基线是否足够稳定** | 部分稳定（`/flow/snapshot` 的 batch_snapshot 机制已真实写入，为本次评估最大亮点）|

---

## 第二部分：阶段性交付检查

### Phase 0：资料盘点与真相源分级基线 ✅ 完成

- 三份 Tier 0 文档已全量读取
- UI_v2 所有页面文档已纳入（27 个文件）
- 数据库实际 run 数量：4 个，分布如下：
  - `RUN-FULL-20251201-20251207-V1`（full_initialization，1 批）
  - `RUN-SCN-SMOKE_INIT1D_STEP2H-20260405095741106`（scenario_replay，7 批）
  - `RUN-SCN-INIT1D_STEP2H-20260405100310813`（scenario_replay，73 批）
  - `RUN-SCN-INIT2D_STEP2H-20260405101143177`（scenario_replay，61 批）
- 存在 scenario_replay 类型 run ✅

### Phase 1：原始文档与设计文档对齐基线 ✅ 完成

- 对象主语统一为 Cell/BS/LAC ✅
- 生命周期与健康状态严格分离 ✅（`lifecycle_state` 6值、`health_state` 7值，schema 已确认）
- 三类资格作为独立概念定义 ✅（`existence_eligible`, `anchorable`, `baseline_eligible` 均为显式列）
- `/flow/snapshot` 设计：初始化后 + 时间点A + 时间点B ✅（实现符合）
- 未发现 Tier 0 与 Tier 1 之间存在结构性冲突

### Phase 2：数据流程与快照机制基线 ✅ 完成（核心机制正常，但有混用风险）

- `batch_snapshot` 每批次真实写入 11 条指标（1562 条总计 / 142 个 batch），非合成估算 ✅
- 百分比基底：`fact_governed/pending/rejected` 均以 `fact_standardized` 为分母 ✅（未发现分母混用）
- 不同 run 类型批次数据相互隔离 ✅
- **警告**：`_run_catalog()` 的 HAVING 过滤（`completed_batch_count > 0`）会把 `full_initialization` run 也纳入场景下拉（该 run 有 1 个 completed batch）

### Phase 3：页面语义合约基线 ⚠️ 部分通过（见 P0 问题）

见第五部分逐页对齐结论。

### Phase 4：API / 字段 / 边界基线 ⚠️ 部分通过

见第四部分字段确认表。

### Phase 5：真实运行验证基线 ✅ 完成

- 9 个页面全部截图完成，保存至 `docs1/claude_reaudit/`
- 关键发现已记录（见第三部分）

### Phase 6：偏差登记、优先级与实施基线 ✅ 完成（见第三部分）

---

## 第三部分：严重问题清单

---

### 🔴 P0-01：`/runs` 批次中心主语错误——硬编码 FULL_BATCH + SAMPLE_BATCH，完全忽略 scenario_replay 批次

**级别**：P0  
**页面/接口/代码位置**：  
- `rebuild3/backend/app/api/run.py`，第 154-198 行，`GET /api/v1/runs/batches`  
- `rebuild3/frontend/src/pages/RunBatchCenterPage.vue`

**证据链**：  
```python
# run.py L158-160
for schema, batch_id, scope in (
    ('rebuild3_meta', FULL_BATCH_ID, 'full'),
    ('rebuild3_sample_meta', SAMPLE_BATCH_ID, 'sample'),
):
```
`FULL_BATCH_ID = 'BATCH-FULL-20251201-20251207-V1'`（run_shared.py L14）  
`SAMPLE_BATCH_ID = 'BATCH-SAMPLE-20251201-20251207-V1'`（run_shared.py L15）

实际数据库中 scenario_replay 三个 run 共有 141 个已完成批次，全部不显示。

**截图证据**：`docs1/claude_reaudit/runs.png`——页面仅显示固定两行（全量/样本）。

**设计文档要求**（UI_v2 `02_run_batch_center_doc.md`）：运行中心应展示所有 run 和批次，围绕 run/batch/version 组织，不是固定两行。

**影响**：`/runs` 的页面主语是「2个固定批次」而非「系统所有运行批次」，完全不反映 scenario_replay 的 134 个真实批次，用户无法理解系统真实运行状态。

**修复建议**：`/api/v1/runs/batches` 改为从 `rebuild3_meta.run` 和 `rebuild3_meta.batch` 全量读取，按 `run_type` 分组展示。  
**是否阻塞下一轮实施**：✅ 是

---

### 🔴 P0-02：`/initialization` 页主语错误——指向 `SAMPLE` 类型 run，而非真正的初始化 run

**级别**：P0  
**页面/接口/代码位置**：  
- `rebuild3/backend/app/api/run.py`，第 241-281 行，`GET /api/v1/runs/initialization`

**证据链**：  
```python
# run.py L244-245
context = _batch_context('rebuild3_sample_meta', SAMPLE_BATCH_ID)
snapshot = _snapshot_map('rebuild3_sample_meta', SAMPLE_BATCH_ID)
```
`context['run_id']` 返回 `RUN-SAMPLE-20251201-20251207-V1`（而不是任何 `full_initialization` 或 `scenario_replay` 的初始化 batch）。

**截图证据**：`docs1/claude_reaudit/initialization.png`——context bar 显示 `run_id: RUN-SAMPLE-20251201-20251207-V1`，不是 scenario_replay 的初始化批次。

**设计文档要求**（Tier 0 文档第6节、UI_v2 `12_initialization_doc.md`）：初始化页面应表达"初始化入口"，即某个 `full_initialization` run 或 scenario 的 init batch，不是 sample validation。

**影响**：用户看到的初始化页描述的是「样本双跑」而非「真正的冷启动初始化过程」，语义完全错位。代码注释中已写 `'初始化页当前接的是 sample validation 结果'`，说明开发者知晓但未修正。

**修复建议**：初始化页应读取 `full_initialization` 类型 run 的 init batch，或提供 scenario 选择，让用户明确选择哪个初始化场景。  
**是否阻塞下一轮实施**：✅ 是

---

### 🔴 P0-03：`/flow/snapshot` 场景下拉混入 `full_initialization` 类型 run

**级别**：P0  
**页面/接口/代码位置**：  
- `rebuild3/backend/app/api/run_snapshot.py`，第 89-153 行，`_run_catalog()`

**证据链**：  
```sql
HAVING count(*) FILTER (WHERE b.status = 'completed') > 0
```
`RUN-FULL-20251201-20251207-V1`（run_type=`full_initialization`）有 1 个 completed batch，因此进入场景下拉。

**截图证据**：`docs1/claude_reaudit/flow-snapshot.png`——下拉可见「full initialization using rebuild2 l0_lac fast path」选项（即 `full_initialization` 类型 run）。  

**设计文档要求**（Prompt 第 A 节）：`/flow/snapshot` 场景下拉仅应包含 scenario_replay 类型 run，`full_initialization` 不是「时间轴快照场景」。

**影响**：用户选择 `full_initialization` 场景后，左侧「初始化完成后」列可能是整个 7 天批次结束数据，不是真正的按 2 小时增量的初始化节点，时间轴语义混乱。

**修复建议**：`_run_catalog()` 中增加 `WHERE r.run_type = 'scenario_replay'` 过滤。  
**是否阻塞下一轮实施**：✅ 是

---

### 🔴 P0-04：`/compare` 和 `/governance` 使用 fallback 硬编码数据但前端无可见提示 banner

**级别**：P0  
**页面/接口/代码位置**：  
- `rebuild3/backend/app/api/compare.py`，第 95-113 行：`data_origin='report_fallback'`、`data_origin='report_fallback'`  
- `rebuild3/backend/app/api/governance.py`，第 79-141 行：所有接口均返回 `data_origin='fallback_catalog'`  
- `rebuild3/frontend/src/pages/ValidationComparePage.vue`：未消费 `data_origin` 字段，无 banner  
- `rebuild3/frontend/src/pages/GovernancePage.vue`：未消费 `data_origin` 字段，无 banner

**证据链**：  
```python
# compare.py L100-101
return {
    'data_origin': 'report_fallback',
    'scopes': [SAMPLE_OVERVIEW, FULL_OVERVIEW],  # 全部为硬编码常量
}
```
```python
# governance.py L79-84
return {
    'data_origin': 'fallback_catalog',
    'overview': OVERVIEW,  # 全部为硬编码常量
}
```
前端 `ValidationComparePage.vue`、`GovernancePage.vue` 均未读取 `data_origin` 字段，无任何 fallback 提示逻辑。

**截图证据**：`docs1/claude_reaudit/compare.png`、`docs1/claude_reaudit/governance.png`——两个页面首屏均无任何 fallback banner 或标签。

**设计文档要求**（Prompt 第 D 节）：fallback 数据必须显式标识，不能占据主语位置且静默展示。

**影响**：`/compare` 展示的是硬编码 rebuild2 vs rebuild3 比对数字（不是实时查询），`/governance` 展示的是硬编码字段/表目录，用户无法区分这是实时数据还是固化报告，违反「fallback 必须显式标识」原则。

**修复建议**：  
(1) 前端消费 `data_origin` 字段，当值为 `report_fallback`/`fallback_catalog` 时显示黄色 banner「当前展示内容为历史报告数据，非实时查询」；  
(2) 或将后端升级为从 `rebuild3_meta.compare_result` 等表动态读取（当前该表为空，说明对比管道尚未产出数据）。  
**是否阻塞下一轮实施**：✅ 是

---

### 🟠 P1-01：`/flow/overview` 的 API 硬编码 `FULL_BATCH_ID`，无法切换 scenario

**级别**：P1  
**代码位置**：`rebuild3/backend/app/api/run.py`，L38-136，`get_flow_overview()`  

**证据链**：  
```python
context = _batch_context('rebuild3_meta', FULL_BATCH_ID)  # 硬编码
full_flow = _flow_rows('rebuild3_meta', FULL_BATCH_ID)
```
`delta` 计算：`current_value - sample_snapshot.get(metric_name, 0)`，使用 `SAMPLE_BATCH_ID` 作为 delta 基准（注释中已说明：`'当前只有 1 个 full batch，因此 delta 采用 sample validation 作为参考基线'`）。

**截图证据**：`docs1/claude_reaudit/flow-overview.png`——context bar 显示 `run_id: RUN-FULL-20251201-20251207-V1`，是 full_initialization 类型，与系统已有 scenario_replay run 无关。

**设计文档要求**（UI_v2 `01_flow_overview_doc.md`）：流转总览应展示当前选择 run/batch 的数据，支持场景切换。

**影响**：当用户在 `/flow/snapshot` 切换到某个 scenario_replay 场景后，切回 `/flow/overview` 仍然显示 full_initialization 批次数据，上下文不一致，造成语义漂移。delta 标注里 `vs sample validation` 对 scenario_replay 数据毫无意义。

**修复建议**：`/flow/overview` 应接受 `run_id` 参数，从对应 run 的最新 batch 读取数据；或至少与 `/flow/snapshot` 的场景选择联动。  
**是否阻塞下一轮实施**：✅ 是

---

### 🟠 P1-02：`obj_cell` 的 `centroid_lon/centroid_lat` 与 API 返回的 `center_lon/center_lat` 字段名不一致

**级别**：P1  
**代码位置**：  
- `rebuild3/backend/app/api/object_common.py`，L157：`p.bs_gps_quality AS gps_quality`（从 stg_cell_profile 读取）  
- `rebuild3` schema 中 `obj_cell` 表列名为 `centroid_lon`/`centroid_lat`  
- stg_cell_profile 中的列名为 `center_lon`/`center_lat`（供 Cell 用）

**证据链**：  
数据库实际 `obj_cell` 列：`centroid_lon`, `centroid_lat`（通过 information_schema 确认）  
API select_fields(cell) 中读取 `p.center_lon, p.center_lat`（来自 stg_cell_profile 的 p 别名），不是直接读 `o.centroid_lon`。

**影响**：Cell 自身的 GPS 质心坐标来自 profile 表，不来自对象快照本身，如果 profile 表未更新，centroid 数据会与对象状态快照脱节。

**修复建议**：确认 `center_lon/center_lat` 还是 `centroid_lon/centroid_lat` 是 Cell GPS 质心的唯一真相来源，统一命名并确保 API 直接从对象快照读取。

---

### 🟠 P1-03：`region_quality_label` 直接存储技术码（`issue_present`、`coverage_insufficient`），UI 未做人类标签映射

**级别**：P1  
**代码位置**：  
- `rebuild3.obj_lac` 表，`region_quality_label` 列，实际值为 `'issue_present'`、`'coverage_insufficient'`（数据库查询确认）  
- `rebuild3/backend/app/api/object_common.py`，L160：API 直接返回 `region_quality_label` 原值  
- `rebuild3/frontend/src/pages/LacProfilePage.vue`：需查看是否有映射

**证据链**：  
```sql
SELECT DISTINCT region_quality_label FROM rebuild3.obj_lac WHERE region_quality_label IS NOT NULL;
-- 结果: 'issue_present', 'coverage_insufficient'
```

**截图证据**：`docs1/claude_reaudit/profiles-lac.png`（需确认页面显示内容）

**影响**：用户在 LAC 画像页看到的是技术枚举码而非人类可读标签（如「区域有问题」、「覆盖不足」），不符合 UI_v2 对人类可读表达的要求。

**修复建议**：  
- 后端或前端增加映射：`coverage_insufficient` → `覆盖不足`，`issue_present` → `区域存在问题`  
- 或后端接口统一返回 `display_label` 字段

---

### 🟡 P2-01：Cell 对象的 `gps_quality` 字段含义模糊

**级别**：P2  
**代码位置**：`rebuild3/backend/app/api/object_common.py`，L157、L198-199

**证据链**：  
```python
# select_fields(cell)
p.bs_gps_quality AS gps_quality  # 从 stg_bs_profile 而非 Cell 自身读取，命名为 "gps_quality"

# serialize_row(cell)，L198-199
'legacy_gps_quality': row.get('gps_quality'),
'gps_quality': row.get('gps_quality'),
```
Cell API 返回 `gps_quality` 字段，但其值来自 BS 的 `bs_gps_quality`，不是 Cell 自身的 GPS 质量评估。字段含义存在混淆。

**影响**：前端显示「GPS 质量」时，实际显示的是 Cell 所属 BS 的 GPS 质量，非 Cell 个体的，存在误导风险。

**修复建议**：改名为 `bs_gps_quality` 或 `parent_bs_gps_quality`，明确来源层级。

---

### 🟡 P2-02：`/flow/overview` 中的 `compare_callout` 与 `key_metrics` delta 数据为硬编码

**级别**：P2  
**代码位置**：`rebuild3/backend/app/api/run.py`，L121-129

**证据链**：  
```python
'compare_callout': {
    'title': '当前差异仍以语义差异为主',
    'metrics': [
        {'label': 'fact_pending_issue 增量', 'value': 2036318},  # 硬编码
        {'label': 'fact_pending_observation 残余差', 'value': 116201},  # 硬编码
        ...
    ],
},
```

**影响**：`compare_callout` 的具体数字（2036318、116201、2274）是历史快照硬编码值，随着 scenario_replay 数据更新后会出现 context bar 与 callout 数字不一致的情况。

**修复建议**：从实际数据动态计算，或标注为「历史参考数据」。

---

### 🟡 P2-03：`/runs/current` 接口的 `rebuild3_sample_meta` schema 不在文档定义范围内

**级别**：P2  
**代码位置**：`rebuild3/backend/app/api/run.py`，L25-33

**证据链**：  
```python
validation = _batch_context('rebuild3_sample_meta', SAMPLE_BATCH_ID)
```
Tier 0 技术栈文档（03 文档 4.1 节）中的 schema 分类为：`rebuild3`、`rebuild3_meta`、`rebuild2`、`rebuild2_meta`、`legacy`，**无 `rebuild3_sample_meta`**。

**影响**：`rebuild3_sample_meta` 是一个非文档化的 schema，其存在说明当前有两套元数据 schema 在并行使用（sample validation 用了独立的 sample_meta），增加维护复杂度，且未在 Tier 0 文档中明确定义。

**修复建议**：在 `rebuild3_meta` 内用 `run_type='sample_validation'` 区分，或在 Tier 0 文档中显式记录 `rebuild3_sample_meta` 的存在和用途。

---

### 🔵 P3-01：`gps_confidence` / `signal_confidence` 字段在 live schema 中不存在

**级别**：P3  
**代码位置**：数据库 schema 查询

**证据链**：  
```sql
SELECT table_name, column_name FROM information_schema.columns 
WHERE table_schema = 'rebuild3' 
  AND column_name IN ('gps_confidence','signal_confidence','gps_quality','region_quality_label');
-- 结果：只有 obj_lac.region_quality_label 和 stg_bs_profile.gps_quality，无 gps_confidence/signal_confidence
```

**影响**：如果任何 UI 页面或文档引用了 `gps_confidence`/`signal_confidence` 字段名，将无法在 live schema 中找到对应字段。当前后端 API 中未直接返回这两个字段名（已确认 object_common.py），风险为中性。

**修复建议**：在技术文档中明确声明这两个字段当前不存在，并用 `gps_original_ratio`（GPS 原始占比）替代 GPS 数据质量的语义表达。

---

### 🔵 P3-02：`/flow/snapshot` 的 `_run_catalog` 使用 TTL 缓存 30s 可能造成场景数据滞后

**级别**：P3（非阻塞，但需登记）

**代码位置**：`run_snapshot.py` L88, L156, L361  

**影响**：新 scenario run 创建后，最多延迟 30s 才出现在场景下拉中，对实时监控场景有轻微干扰。  

**修复建议**：可接受，但建议在 UI 中提供手动刷新按钮，或将运行场景相关的 TTL 缩短至 10s。

---

## 第四部分：字段与边界确认表

详细字段基线见 `docs1/Claude_field_baseline.md`。

核心字段快速确认：

| 字段 | 文档定义 | live schema 存在 | API 字段名 | 层级 | fallback | 当前一致性 |
|---|---|---|---|---|---|---|
| `lifecycle_state` | Tier 0 冻结 6 值 | ✅ obj_cell/bs/lac | lifecycle_state | 主状态 | 无 | ✅ 一致 |
| `health_state` | Tier 0 冻结 7 值 | ✅ obj_cell/bs/lac | health_state | 主状态 | 无 | ✅ 一致 |
| `existence_eligible` | 三层资格之一 | ✅ obj_cell/bs/lac | existence_eligible | 资格层 | 无 | ✅ 一致 |
| `anchorable` | 三层资格之一 | ✅ obj_cell/bs/lac | anchorable | 资格层 | 无 | ✅ 一致 |
| `baseline_eligible` | 三层资格之一 | ✅ obj_cell/bs/lac | baseline_eligible | 资格层 | 无 | ✅ 一致 |
| `region_quality_label` | LAC 对象质量标签 | ✅ obj_lac | region_quality_label | 解释层 | 无 | ⚠️ 返回技术码，无人类标签（P1-03）|
| `classification_v2` | BS 分类（r2 参考层）| ✅ r2_full_profile_bs | classification_v2 | 参考层 | 无 | ✅ 来源正确（r2_full_profile_bs）|
| `gps_confidence` | 文档中提及 | ❌ **不存在于 rebuild3 schema** | — | — | — | ❌ 字段缺失（P3-01）|
| `signal_confidence` | 文档中提及 | ❌ **不存在于 rebuild3 schema** | — | — | — | ❌ 字段缺失（P3-01）|
| `gps_quality` | 非正式命名 | ✅ stg_bs_profile | gps_quality（bs page）| 解释层 | 无 | ⚠️ Cell API 中以 bs_gps_quality 混名（P2-01）|
| `compare_membership` | 对比参考，非 baseline diff | 计算产出 | compare_membership | 参考层 | 无 | ✅ 正确（r2 vs r3 baseline 资格对比）|
| `data_origin` | fallback 标识字段 | backend 返回 | data_origin | 元数据 | 当值为 fallback 时应显示 | ❌ 前端未消费（P0-04）|
| 四分流字段 | 来自 rebuild3.fact_* 表 | ✅ 四张 fact 表存在 | 通过 batch_flow_summary/batch_snapshot 读取 | 事实层 | 无 | ✅ 来自真实治理链路 |

---

## 第五部分：页面逐页对齐结论

| 路由 | 页面主语正确 | 语义漂移 | 数据链路 | fallback 问题 | 建议动作 |
|---|---|---|---|---|---|
| `/flow/overview` | ⚠️ 仅 full_initialization run | delta 以 sample_batch 为基准没有意义（对用户不透明） | 硬编码 FULL_BATCH_ID | 无 | P1-01：支持 run_id 参数化 |
| `/flow/snapshot` | ✅（场景选择后正确） | 场景下拉混入 full_initialization | batch_snapshot 真实写入 ✅ | 无 | P0-03：过滤下拉为 scenario_replay |
| `/runs` | ❌ 仅固定 2 行 | 主语应为所有 run/batch | 硬编码 2 个 batch_id | 无 | P0-01：全量从 DB 读取 |
| `/objects` | ✅ | 无明显漂移 | 查 obj_cell/bs/lac ✅ | 无 | 字段命名统一（P2-01）|
| `/observation` | ✅ | — | fact_pending_observation ✅ | 无 | 无阻塞问题 |
| `/anomalies` | ✅ | — | batch_anomaly_summary ✅ | 无 | 无阻塞问题 |
| `/baseline` | ✅ | — | baseline_cell/bs/lac ✅ | 无 | 无阻塞问题 |
| `/compare` | ❌ 硬编码报告 | 表达为「实时查询」但实为固定数据 | 硬编码常量，非 DB 查询 | ❌ 无 banner | P0-04：增加 fallback banner |
| `/profiles/lac` | ✅ | region_quality_label 显示技术码 | obj_lac ✅ | 无 | P1-03：增加人类标签映射 |
| `/profiles/bs` | ✅ | gps_quality 命名混淆 | obj_bs + r2_full_profile_bs ✅ | 无 | P2-01：命名统一 |
| `/profiles/cell` | ✅ | gps_quality 命名混淆 | obj_cell + stg_cell_profile ✅ | 无 | P2-01 |
| `/initialization` | ❌ 指向 SAMPLE run | 应指向初始化 run，实为 sample validation | 硬编码 SAMPLE_BATCH_ID | 无 | P0-02：修正 run_id 主语 |
| `/governance` | ❌ 硬编码目录 | 展示内容为固化快照非实时 | 硬编码常量 | ❌ 无 banner | P0-04 |

---

## 第六部分：基线产物清单

| 产物 | 状态 | 路径/内容 |
|---|---|---|
| 文档清单与分级表 | ✅ | 本报告 Phase 0 |
| 路由清单（13 路由） | ✅ | 本报告第五部分 |
| 页面→API→表映射表 | ✅ | 本报告第五部分 + Claude_field_baseline.md |
| 字段与边界确认表 | ✅ | 本报告第四部分 |
| batch_snapshot 真实性核查 | ✅ | 每 batch 11 条，1562 条总计，逐批真实写入 |
| scenario/timepoint 模型核查 | ✅ | 3 个 scenario_replay run，共 141 批次 |
| 页面主语偏差清单 | ✅ | P0-01/02/03；/runs、/initialization、/flow/overview、/compare、/governance |
| 截图（9 页） | ✅ | docs1/claude_reaudit/*.png |

---

## 第七部分：剩余工作队列

### 必须立刻修（P0 + P1）

1. **P0-01**：`/runs` — `get_batches()` 改为全量从 `rebuild3_meta.run + batch` 读取，支持所有 run_type
2. **P0-02**：`/initialization` — `get_initialization()` 改为读取 `full_initialization` 类型 run 的 init batch，或支持 scenario 选择
3. **P0-03**：`/flow/snapshot` — `_run_catalog()` 增加 `WHERE r.run_type = 'scenario_replay'` 过滤
4. **P0-04**：`/compare` + `/governance` — 前端增加 fallback banner 组件（消费 `data_origin` 字段）
5. **P1-01**：`/flow/overview` — 支持 `run_id` 参数，切换到对应 scenario 的最新 batch 数据
6. **P1-02**：Cell 对象质心字段命名统一（`centroid_lon/lat` vs `center_lon/lat`）
7. **P1-03**：`region_quality_label` 增加人类标签映射

### 本轮可延后但需登记（P2）

8. **P2-01**：Cell 的 `gps_quality` 字段重命名为 `parent_bs_gps_quality` 或同等明确命名
9. **P2-02**：`/flow/overview` 的 `compare_callout` 数字动态化或标注历史数据
10. **P2-03**：`rebuild3_sample_meta` schema 在 Tier 0 文档中显式登记

### 可以后续优化（P3）

11. **P3-01**：文档中明确声明 `gps_confidence`/`signal_confidence` 字段当前用 `gps_original_ratio` 替代
12. **P3-02**：`_run_catalog` TTL 缩短，或 UI 提供手动刷新

---

## 禁止再次默认假设清单

1. **禁止默认 `/runs` 只需要 sample+full 两行**：batch 中心必须按 run 层级展开所有 scenario 批次
2. **禁止默认 `/initialization` 展示 sample validation 结果等同于展示初始化数据**：两者语义完全不同
3. **禁止默认 `_run_catalog()` 过滤 completed>0 即为场景下拉的正确过滤条件**：必须加 run_type='scenario_replay'
4. **禁止默认 fallback 数据展示无需在 UI 说明**：所有 `data_origin=fallback_*` 的接口响应，前端必须显示 banner
5. **禁止用 `gps_quality`（来自 BS profile）冒充 Cell 自身的 GPS 质量**：必须明确字段来源层级
6. **禁止把 `region_quality_label` 的技术码（`issue_present`）直接透传给用户**：必须映射为人类可读标签
7. **禁止用 sample_batch delta 作为 full_initialization run 的对比基准**：delta 基准必须与 run 类型匹配

---

*报告生成于 2026-04-05，基于代码独立阅读、数据库实时查询和页面截图审计，未参考任何已有审计结论文档。*
