# rebuild3 字段基线表 & 冲突登记（Claude 独立复评版）

> 来源：代码阅读 + 数据库实时查询（PG17 MCP）  
> 更新时间：2026-04-05  
> 此文档由 Claude 从第一手证据独立生成，未参考任何已有审计结论

---

## 一、核心对象表字段基线

### 1. `rebuild3.obj_cell`（28 列）

| 列名 | 数据类型 | 来源 | 说明 |
|---|---|---|---|
| object_id | text | 治理系统写入 | Cell 唯一标识 |
| operator_code | text | 事实层派生 | 运营商代码 |
| tech_norm | text | 事实层派生 | 制式（标准化） |
| lac | text | 事实层派生 | LAC 编码 |
| bs_id | bigint | 事实层派生 | 基站ID |
| cell_id | bigint | 事实层派生 | 小区ID |
| lifecycle_state | text | 治理决策写入 | 生命周期状态（6值）|
| health_state | text | 治理决策写入 | 健康状态（7值）|
| existence_eligible | boolean | 治理决策写入 | 存在资格 |
| anchorable | boolean | 治理决策写入 | 锚定资格 |
| baseline_eligible | boolean | 治理决策写入 | 基线资格 |
| record_count | bigint | 统计聚合 | 记录数 |
| gps_count | bigint | 统计聚合 | GPS 记录数 |
| device_count | bigint | 统计聚合 | 设备数 |
| active_days | integer | 统计聚合 | 活跃天数 |
| **centroid_lon** | double precision | 统计聚合 | GPS质心经度（注意：API 从 profile 表读，非此列）|
| **centroid_lat** | double precision | 统计聚合 | GPS质心纬度（注意：API 从 profile 表读，非此列）|
| gps_p50_dist_m | numeric | 统计聚合 | GPS P50 距离（米）|
| gps_p90_dist_m | numeric | 统计聚合 | GPS P90 距离（米）|
| gps_original_ratio | numeric | 统计聚合 | GPS 原始占比（≈ gps_confidence 代用）|
| signal_original_ratio | numeric | 统计聚合 | 信号原始占比（≈ signal_confidence 代用）|
| anomaly_tags | ARRAY | 治理标签 | 异常标签数组 |
| parent_bs_object_id | text | 关系链接 | 父 BS 对象ID |
| run_id | text | 元数据 | 所属 run |
| batch_id | text | 元数据 | 所属 batch |
| baseline_version | text | 元数据 | 基线版本（写入时的基线）|
| sample_scope_tag | text | 元数据 | 样本范围标签 |
| created_at | timestamptz | 系统时间 | 写入时间 |

**⚠️ 字段名冲突注册**：
- API `select_fields(cell)` 中读取 `p.center_lon, p.center_lat`（来自 stg_cell_profile），`o.centroid_lon/lat` 不被直接 SELECT
- 这意味着 `/profiles/cell` 和 `/objects` 接口返回的 `center_lon/center_lat` 来自 **profile 表**，不是 obj_cell 快照
- 建议与产品确认：单一真相来源应该是哪个表的哪个字段

### 2. `rebuild3.obj_bs`（29 列）

关键字段（仅列不同于 obj_cell 的部分）：

| 列名 | 数据类型 | 说明 |
|---|---|---|
| cell_count | bigint | 该 BS 下的 Cell 数量 |
| active_cell_count | bigint | 活跃 Cell 数量 |
| center_lon | double precision | GPS 质心经度（命名与 Cell 表不同，此处直接在 obj_bs 中）|
| center_lat | double precision | GPS 质心纬度（同上）|
| parent_lac_object_id | text | 父 LAC 对象ID |

**注意**：obj_bs 的质心列命名为 `center_lon/lat`（与 obj_cell 的 `centroid_lon/lat` 不同），API 直接从 `o.center_lon` 读取。

### 3. `rebuild3.obj_lac`（26 列）

关键字段（仅列不同的部分）：

| 列名 | 数据类型 | 说明 |
|---|---|---|
| bs_count | bigint | LAC 下的 BS 数量 |
| active_bs_count | bigint | 活跃 BS 数量 |
| region_quality_label | text | 区域质量标签（当前值：`issue_present`、`coverage_insufficient`）|

**⚠️ 字段值警告**：`region_quality_label` 存储技术码，需在 UI 层或 API 层映射为人类可读标签。

---

## 二、核心元数据表字段冲突

### `rebuild3_meta.run`（实测 4 行）

| run_id | run_type | status | 说明 |
|---|---|---|---|
| RUN-FULL-20251201-20251207-V1 | full_initialization | completed | 全量初始化 run，1个batch |
| RUN-SCN-SMOKE_INIT1D_STEP2H-... | scenario_replay | completed | 7批 |
| RUN-SCN-INIT1D_STEP2H-... | scenario_replay | completed | 73批 |
| RUN-SCN-INIT2D_STEP2H-... | scenario_replay | completed | 61批 |

**问题**：`FULL_BATCH_ID`（硬编码在 run_shared.py L14）指向 `full_initialization` run，`SAMPLE_BATCH_ID`（L15）指向 `rebuild3_sample_meta` schema（未在 Tier 0 文档中登记）。

### `rebuild3_meta.batch_snapshot`（实测 1562 行）

每个 batch 有 11 条 stage-level 指标，无例外，批次级写入机制正常。

**当前覆盖 batch 数**：1562 / 11 = 142 个 batch（含 full_initialization 的 1 个 + scenario_replay 的 141 个）。

---

## 三、API 字段命名偏差登记

| 问题 | API 返回字段 | DB 实际字段 | 偏差类型 | 严重级别 |
|---|---|---|---|---|
| Cell 质心坐标来源混淆 | center_lon/center_lat | obj_cell.centroid_lon/lat（obj_cell），profile.center_lon/lat（profile） | 字段来源层不一致 | P1 |
| Cell GPS 质量混名 | gps_quality | stg_cell_profile.bs_gps_quality | alias 掩盖来源层级 | P2 |
| LAC 质量标签未翻译 | region_quality_label → 'issue_present' | obj_lac.region_quality_label | 技术码透传给用户 | P1 |
| data_origin 未被前端消费 | data_origin='fallback_catalog' | 纯后端元数据，前端未读 | fallback 无 UI 标识 | P0 |

---

## 四、字段别名安全白名单（当前允许的 alias）

以下字段 alias 已经确认无歧义，审计通过：

- `compare_membership`：基于 `r2_baseline_eligible` 与 `baseline_eligible` 计算，语义明确
- `watch`：基于 lifecycle_state + health_state 计算，前端用于高亮，无歧义
- `r2_health_state`：来自 `rebuild3_meta.r2_full_cell_state.health_state`，标注来源层级正确
- `r2_baseline_eligible`：来自 `rebuild3_meta.r2_full_*(cell/bs/lac)_state.baseline_eligible`，来源正确

---

## 五、禁止在下一实施轮次使用的硬编码值

| 硬编码值 | 位置 | 禁止原因 |
|---|---|---|
| `BATCH-FULL-20251201-20251207-V1` | run_shared.py L14 | 特定日期批次，不应作为全局默认 |
| `BATCH-SAMPLE-20251201-20251207-V1` | run_shared.py L15 | 同上 |
| `compare_callout.metrics` 中的数字 2036318、116201 | run.py L121-128 | 历史快照数字，非实时查询 |
| SAMPLE_OVERVIEW、FULL_OVERVIEW 常量 | compare.py 上部 | 硬编码 rebuild2 vs rebuild3 比对结果 |
| OVERVIEW、FIELDS、TABLES 等常量 | governance.py 上部 | 硬编码字段/表目录快照 |

---

*字段基线由 Claude 通过 information_schema 查询和代码分析独立生成，2026-04-05*

---

## 六、第二轮 repair 后的实现一致性结论（2026-04-05 更新）

以下结论用于同步 `docs1/rebuild3_round2_repair_task_doc.md` 的实施结果；前文基线表仍保留 2026-04-05 初次复评时的原始证据。

### 已完成回正

1. Cell 坐标来源合同已拆开
   - API 现输出 `center_lon / center_lat`（来自 `obj_cell.centroid_*`）
   - 同时输出 `profile_center_lon / profile_center_lat` 作为画像参考坐标
   - 不再把两套来源静默混成同名字段

2. Cell GPS 质量混名已修正
   - 原来由 `stg_cell_profile.bs_gps_quality` 透传为 `gps_quality`
   - 现在改为 `bs_gps_quality_reference`
   - 前端页面文案同步改为 `BS侧GPS质量(参考)`

3. BS 参考字段文案已回正
   - API 输出 `gps_quality_reference`
   - 前端主表列名改为 `GPS质量(参考)`
   - `signal_confidence` 未再被伪造为正式字段，BS 页对应空假列已移除

4. LAC 区域质量标签已中文化
   - API 保留原始技术码：`region_quality_code`
   - API 展示字段：`region_quality_label`
   - 当前映射已冻结为：
     - `issue_present -> 存在问题`
     - `coverage_insufficient -> 覆盖不足`

### 仍然成立的事实

1. `obj_lac.region_quality_label` 在库内仍存技术码
   - 本轮修的是 API / UI 表达层
   - 并未修改底层表结构或历史存量值

2. compare / governance 仍非真实注册结果
   - 这两组接口当前仍属于 fallback
   - 但本轮已补齐来源合同与页面首屏 banner

3. scenario / initialization 快照仍未成为真实时间点证据
   - `scenario_replay` 仍归类为 `synthetic`
   - `full_initialization` 汇总快照当前也仍归类为 `synthetic`
   - 因此 `/flow/snapshot` 与 `/flow/overview` 现在会优先进入诚实空状态，而不是继续伪造主语

### 结论

与字段表达直接相关的 P1/P2 偏差里，本轮已经完成以下“说真话”修复：

- LAC 标签不再把技术码直接暴露给用户
- BS / Cell 不再把 `gps_quality` 冒充成旧可信度字段
- Cell 不再混淆对象质心与画像参考中心
- 无真实来源但看起来像正式字段的 BS 假列已移除

仍待下一轮单独立项解决的，不是字段命名问题，而是更上游的真实 scenario replay / compare / governance 数据链建设。
