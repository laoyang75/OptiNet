# 实体字段接口与 Gate 细化

状态：round2 Claude 独立输出  
更新时间：2026-04-06  
数据库事实：全部通过 `PG17 MCP execute_sql` / `search_objects` 验证（2026-04-06）  
本轮页面规则：未访问页面。

---

## 1. 实体完整字段定义

### 1.1 `rebuild4_meta.run`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `run_id` | BIGSERIAL | PK | |
| `run_type` | TEXT | NOT NULL, CHECK IN ('full_initialization', 'rolling', 'scenario_replay') | 不可扩展枚举 |
| `data_origin` | TEXT | NOT NULL, CHECK IN ('real', 'synthetic') | `scenario_replay` 强制为 `synthetic` |
| `input_source` | TEXT | | 输入源描述 |
| `contract_version_id` | BIGINT | FK → contract_version | |
| `rule_set_version_id` | BIGINT | FK → rule_set_version | |
| `status` | TEXT | NOT NULL, CHECK IN ('pending', 'running', 'completed', 'failed') | |
| `config` | JSONB | | 运行参数 |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `started_at` | TIMESTAMPTZ | | |
| `completed_at` | TIMESTAMPTZ | | |
| `error_message` | TEXT | | 失败时的错误信息 |

**约束补充**：

- `run_type = 'scenario_replay'` 时 `data_origin` 必须为 `'synthetic'`（CHECK 约束或 trigger）
- `full_initialization` 在 `data_origin = 'real'` 下最多存在 1 个 `completed` run（业务约束，建议 partial unique index）

### 1.2 `rebuild4_meta.batch`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `batch_id` | BIGSERIAL | PK | |
| `run_id` | BIGINT | FK → run, NOT NULL | |
| `batch_seq` | INT | NOT NULL | run 内序号，从 1 递增 |
| `window_start` | TIMESTAMPTZ | | 时间窗口起点 |
| `window_end` | TIMESTAMPTZ | | 时间窗口终点 |
| `status` | TEXT | NOT NULL, CHECK IN ('pending', 'processing', 'completed', 'failed') | |
| `is_rerun` | BOOLEAN | NOT NULL, DEFAULT false | |
| `rerun_source_batch_id` | BIGINT | FK → batch, nullable | 重跑来源 |
| `input_count` | BIGINT | | 输入记录数 |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `started_at` | TIMESTAMPTZ | | |
| `completed_at` | TIMESTAMPTZ | | |

**约束补充**：

- `(run_id, batch_seq)` UNIQUE
- `full_initialization` run 下只允许 1 个 batch（`batch_seq = 1`）
- `is_rerun = true` 时 `rerun_source_batch_id` NOT NULL

### 1.3 `rebuild4_meta.batch_snapshot`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PK | |
| `batch_id` | BIGINT | FK → batch, NOT NULL | |
| `stage_name` | TEXT | NOT NULL, CHECK IN ('input', 'routing', 'objects', 'baseline') | 4 个枚举值 |
| `metric_name` | TEXT | NOT NULL | |
| `metric_value` | NUMERIC | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**约束补充**：

- `(batch_id, stage_name, metric_name)` UNIQUE
- 只有 `status = 'completed'` 的 batch 才写入 snapshot

**当前 rebuild3 参考**（PG17）：

- 4 个 stage：`input` / `routing` / `objects` / `baseline`
- 11 个 metric（rebuild4 可继承或扩展，但变更必须更新合同）

### 1.4 `rebuild4_meta.baseline_version`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `version_id` | BIGSERIAL | PK | |
| `run_id` | BIGINT | FK → run | 产出该版本的 run |
| `batch_id` | BIGINT | FK → batch | 产出该版本的 batch |
| `rule_set_version_id` | BIGINT | FK → rule_set_version | |
| `data_origin` | TEXT | NOT NULL, CHECK IN ('real', 'synthetic') | |
| `object_coverage` | JSONB | | `{"cell": N, "bs": N, "lac": N}` |
| `is_current` | BOOLEAN | NOT NULL, DEFAULT false | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**约束补充**：

- `is_current = true` 最多 1 行（partial unique index: `WHERE is_current = true`）
- 创建新版本时，旧版本的 `is_current` 必须在同一事务中置为 `false`

### 1.5 `rebuild4_meta.contract_version`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `version_id` | BIGSERIAL | PK | |
| `version_label` | TEXT | NOT NULL, UNIQUE | 人类可读标签 |
| `content_hash` | TEXT | NOT NULL | 合同内容哈希 |
| `description` | TEXT | | 变更说明 |
| `is_current` | BOOLEAN | NOT NULL, DEFAULT false | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 1.6 `rebuild4_meta.rule_set_version`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `version_id` | BIGSERIAL | PK | |
| `version_label` | TEXT | NOT NULL, UNIQUE | |
| `content_hash` | TEXT | NOT NULL | |
| `description` | TEXT | | |
| `is_current` | BOOLEAN | NOT NULL, DEFAULT false | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 1.7 `rebuild4_meta.parse_rule`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `rule_id` | SERIAL | PK | |
| `source_field` | TEXT | NOT NULL | 原始字段名 |
| `target_fields` | TEXT[] | NOT NULL | 解析产出字段列表 |
| `parse_logic` | TEXT | NOT NULL | 解析逻辑描述/SQL 片段 |
| `applies_to` | TEXT | | `cell_infos` / `ss1` / `all` |
| `source_reference` | TEXT | | 来源文档/脚本路径 |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 1.8 `rebuild4_meta.compliance_rule`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `rule_id` | SERIAL | PK | |
| `rule_code` | TEXT | NOT NULL, UNIQUE | 规则编码 |
| `check_field` | TEXT | NOT NULL | 检查字段 |
| `check_condition` | TEXT | NOT NULL | 检查条件 SQL 表达式 |
| `fail_action` | TEXT | NOT NULL, CHECK IN ('reject', 'flag', 'warn') | |
| `severity` | TEXT | NOT NULL, CHECK IN ('critical', 'high', 'medium', 'low') | |
| `description` | TEXT | | |
| `source_reference` | TEXT | | |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 1.9 元数据快照表（从 rebuild2_meta 冻结）

以下表在 Phase 1 创建，通过 `INSERT INTO ... SELECT FROM rebuild2_meta.*` 一次性填充，之后不可变更。

#### `rebuild4_meta.field_audit_snapshot`

结构与 `rebuild2_meta.field_audit` 完全一致，额外增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| `snapshot_at` | TIMESTAMPTZ | 快照时间 |
| `source_schema` | TEXT | 固定值 `'rebuild2_meta'` |

预期行数：27（与源一致）

#### `rebuild4_meta.target_field_snapshot`

结构与 `rebuild2_meta.target_field` 一致 + `snapshot_at` / `source_schema`。

预期行数：55

#### `rebuild4_meta.ods_rule_snapshot`

结构与 `rebuild2_meta.ods_clean_rule` 一致 + `snapshot_at` / `source_schema`。

预期行数：26

#### `rebuild4_meta.ods_result_snapshot`

结构与 `rebuild2_meta.ods_clean_result` 一致 + `snapshot_at` / `source_schema`。

预期行数：48

#### `rebuild4_meta.trusted_filter_snapshot`

新建表，记录 trusted 过滤的汇总快照：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | SERIAL | PK |
| `total_l0_lac` | BIGINT | 43,771,306 |
| `trusted_hit` | BIGINT | 30,082,381 |
| `filtered_out` | BIGINT | 13,688,925 |
| `filtered_pct` | NUMERIC(5,2) | 31.27 |
| `breakdown` | JSONB | 按来源/制式/GPS/信号的损耗明细 |
| `snapshot_at` | TIMESTAMPTZ | |
| `source_schema` | TEXT | `'rebuild2'` |

---

## 2. 核心数据表（rebuild4 schema）

### 2.1 对象表

#### `rebuild4.obj_cell`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `cell_key` | TEXT | PK | 唯一标识 |
| `operator_code` | TEXT | NOT NULL | 运营商编码 |
| `tech_norm` | TEXT | NOT NULL | 标准制式 |
| `lac` | BIGINT | NOT NULL | |
| `cell_id` | BIGINT | NOT NULL | |
| `bs_id` | TEXT | NOT NULL | 所属 BS |
| `sector_id` | TEXT | | 扇区 |
| `lifecycle_state` | TEXT | NOT NULL, CHECK IN ('waiting', 'observing', 'active', 'dormant', 'retired', 'rejected') | |
| `health_state` | TEXT | NOT NULL, CHECK IN ('healthy', 'insufficient', 'gps_bias', 'collision_suspect', 'collision_confirmed', 'dynamic', 'migration_suspect') | |
| `existence_eligible` | BOOLEAN | NOT NULL, DEFAULT false | L1 |
| `anchorable` | BOOLEAN | NOT NULL, DEFAULT false | L2 |
| `baseline_eligible` | BOOLEAN | NOT NULL, DEFAULT false | L3 |
| `sample_count` | INT | DEFAULT 0 | GPS 采样点数 |
| `device_count` | INT | DEFAULT 0 | 设备数 |
| `active_days` | INT | DEFAULT 0 | 活跃天数 |
| `centroid_lon` | DOUBLE PRECISION | | 质心经度 |
| `centroid_lat` | DOUBLE PRECISION | | 质心纬度 |
| `radius_p50` | DOUBLE PRECISION | | P50 半径（米） |
| `radius_p90` | DOUBLE PRECISION | | P90 半径（米） |
| `first_seen_batch` | BIGINT | FK → batch | |
| `last_active_batch` | BIGINT | FK → batch | |
| `current_baseline_version` | BIGINT | FK → baseline_version | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**语义说明**：

- `lifecycle_state` 和 `health_state` 枚举值冻结自 Tier 0，不可在实现时扩展
- `watch` 不是持久化字段，是前端派生态：`lifecycle_state = 'active' AND health_state != 'healthy'`
- 旧分类字段（`classification_v2` / `gps_confidence` / `signal_confidence`）**不进入** rebuild4 核心表；若需展示，从 rebuild3 只读引用

#### `rebuild4.obj_bs`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `bs_key` | TEXT | PK | |
| `operator_code` | TEXT | NOT NULL | |
| `tech_norm` | TEXT | NOT NULL | |
| `lac` | BIGINT | NOT NULL | |
| `bs_id` | TEXT | NOT NULL | |
| `lifecycle_state` | TEXT | NOT NULL | 同 Cell 枚举 |
| `health_state` | TEXT | NOT NULL | 同 Cell 枚举 |
| `anchorable` | BOOLEAN | NOT NULL, DEFAULT false | |
| `baseline_eligible` | BOOLEAN | NOT NULL, DEFAULT false | |
| `child_cell_count` | INT | DEFAULT 0 | 下辖 Cell 数 |
| `centroid_lon` | DOUBLE PRECISION | | |
| `centroid_lat` | DOUBLE PRECISION | | |
| `radius_p50` | DOUBLE PRECISION | | |
| `radius_p90` | DOUBLE PRECISION | | |
| `area_km2` | DOUBLE PRECISION | | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

#### `rebuild4.obj_lac`

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `lac_key` | TEXT | PK | |
| `operator_code` | TEXT | NOT NULL | |
| `tech_norm` | TEXT | NOT NULL | |
| `lac` | BIGINT | NOT NULL | |
| `lifecycle_state` | TEXT | NOT NULL | |
| `health_state` | TEXT | NOT NULL | |
| `anchorable` | BOOLEAN | NOT NULL, DEFAULT false | |
| `child_bs_count` | INT | DEFAULT 0 | |
| `child_cell_count` | INT | DEFAULT 0 | |
| `anomaly_bs_ratio` | NUMERIC(5,2) | | 异常 BS 占比 |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

### 2.2 事实表

四分流表结构统一：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `fact_id` | BIGSERIAL | PK | |
| `batch_id` | BIGINT | FK → batch, NOT NULL | |
| `cell_key` | TEXT | FK → obj_cell, NOT NULL | |
| `record_time` | TIMESTAMPTZ | | 原始记录时间 |
| `lon` | DOUBLE PRECISION | | |
| `lat` | DOUBLE PRECISION | | |
| `rsrp` | DOUBLE PRECISION | | |
| `rsrq` | DOUBLE PRECISION | | |
| `sinr` | DOUBLE PRECISION | | |
| `routing_reason` | TEXT | | 分流原因 |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

四张表：

- `rebuild4.fact_governed`
- `rebuild4.fact_pending_observation`
- `rebuild4.fact_pending_issue`
- `rebuild4.fact_rejected`

**必须使用全称**，不允许缩写。

---

## 3. API 接口细化

### 3.1 通用响应包装

所有核心 API 响应必须在顶层包含来源元数据：

```json
{
  "data_origin": "real",
  "origin_detail": "run_id=1, batch_id=5",
  "subject_scope": "full",
  "subject_note": null,
  "data": { ... }
}
```

`data_origin` 必须在响应 JSON 的**顶层**，不允许嵌套在 `data` 内部。

**为什么必须冻结位置**：如果有的 API 放顶层、有的放嵌套，前端消费逻辑会不一致，后续维护成本高。

### 3.2 主流程 API

#### `GET /api/flow-overview`

```
请求参数：无（自动取当前 real run 的最新 completed batch）
响应：
{
  "data_origin": "real",
  "origin_detail": "run_id=1, batch_id=5",
  "subject_scope": "full",
  "data": {
    "context": {
      "run_id": 1,
      "batch_id": 5,
      "window_start": "...",
      "window_end": "...",
      "baseline_version": 2,
      "rule_set_version": "v1.0"
    },
    "current_batch_flow": {
      "input_count": 43771306,
      "governed": 24855605,
      "pending_observation": 10590738,
      "pending_issue": 3825562,
      "rejected": 4499401
    },
    "delta_vs_previous": {
      "governed_delta": 120,
      "pending_observation_delta": -15,
      "pending_issue_delta": 3,
      "rejected_delta": 0,
      "health_distribution_change": { ... },
      "anchorable_change": { "gained": 5, "lost": 2 },
      "baseline_eligible_change": { "gained": 3, "lost": 1 }
    },
    "promotions": { "promoted_count": 8, "demoted_count": 2, "cascade_updates": 3 },
    "baseline_refresh": { "triggered": false, "reason": null },
    "top_changes": [ ... ],
    "priority_issues": [ ... ]
  }
}
```

#### `GET /api/flow-snapshot?batch_id=xxx`

```
响应：从 batch_snapshot 表读取该 batch 的所有 stage/metric
{
  "data_origin": "real",
  "data": {
    "batch_id": 5,
    "snapshots": [
      { "stage_name": "input", "metric_name": "total_records", "metric_value": 43771306 },
      { "stage_name": "routing", "metric_name": "governed_count", "metric_value": 24855605 },
      ...
    ]
  }
}
```

#### `GET /api/batches?run_id=xxx`

```
响应：该 run 下所有 batch 列表
{
  "data_origin": "real",
  "data": {
    "run_id": 1,
    "batches": [
      {
        "batch_id": 1,
        "batch_seq": 1,
        "window_start": "...",
        "window_end": "...",
        "status": "completed",
        "is_rerun": false,
        "input_count": 43771306,
        "flow_distribution": { "governed": ..., "pending_observation": ..., "pending_issue": ..., "rejected": ... },
        "delta_vs_previous": { ... },
        "baseline_refresh_triggered": false
      },
      ...
    ]
  }
}
```

#### `GET /api/objects?type=cell&lifecycle=active&health=healthy&page=1&page_size=50`

```
响应：对象列表（分页）
{
  "data_origin": "real",
  "data": {
    "items": [ ... ],
    "total": 573561,
    "page": 1,
    "page_size": 50
  }
}
```

#### `GET /api/objects/:key/detail`

```
响应：单对象详情
{
  "data_origin": "real",
  "data": {
    "snapshot": { ... },
    "profile_summary": { "centroid_lon": ..., "centroid_lat": ..., "radius_p90": ..., ... },
    "state_history": [ ... ],
    "recent_facts": [ ... ],
    "qualification_reasons": { "anchorable_reason": "...", "baseline_eligible_reason": "..." },
    "related_anomalies": [ ... ],
    "downstream_impact": { ... }
  }
}
```

#### `GET /api/observation-workspace?sort=progress_desc&page=1`

```
响应：等待/观察工作台
{
  "data_origin": "real",
  "data": {
    "summary": { "waiting_count": ..., "observing_count": ..., "promoted_this_batch": ..., "to_issue_this_batch": ... },
    "items": [
      {
        "cell_key": "...",
        "lifecycle_state": "observing",
        "l1_progress": { "gps_points": { "current": 8, "required": 10, "pct": 80 }, "devices": { ... }, "days": { ... } },
        "l2_progress": { "gps_points": { ... }, "devices": { ... }, "p90": { ... } },
        "l3_progress": { ... },
        "trend_direction": "advancing",
        "suggested_action": "continue",
        "stall_batches": 0
      },
      ...
    ],
    "total": ...,
    "page": 1
  }
}
```

#### `GET /api/anomaly-workspace?view=object_level&page=1`

```
响应：异常工作台（双视角通过 view 参数切换）
view = "object_level" | "record_level"
```

#### `GET /api/baseline/current`

```
响应：当前 baseline 版本
{
  "data_origin": "real",
  "subject_scope": "single_version",
  "subject_note": "暂无上一版可比",  // 当只有 1 个版本时
  "data": {
    "version_id": 1,
    "rule_set_version": "v1.0",
    "object_coverage": { "cell": 573561, "bs": 193036, "lac": 50153 },
    "created_at": "...",
    "diff_vs_previous": null,  // 无上一版时为 null
    "stability_risk": { ... }
  }
}
```

#### `GET /api/initialization/summary`

```
响应：初始化流程摘要（纯展示）
```

### 3.3 画像 API

#### `GET /api/profiles/lac?search=xxx&page=1&page_size=50`
#### `GET /api/profiles/bs?search=xxx&health=healthy&page=1`
#### `GET /api/profiles/cell?search=xxx&lifecycle=active&page=1`

画像 API 均返回列表 + 行展开详情所需字段。旧分类字段（classification_v2 等）以 `legacy_ref` 嵌套返回，前端以灰色样式展示。

### 3.4 治理 API（D-003 裁决细化）

#### `GET /api/governance/field_audit`

```
响应：27 行字段审计
{ "data_origin": "real", "data": { "total": 27, "items": [ { "field_name": "...", "decision": "keep", ... } ] } }
```

#### `GET /api/governance/target_fields`

```
响应：55 行目标字段
```

#### `GET /api/governance/ods_rules`

```
响应：26 条规则定义（含 NULL_WIFI_MAC_INVALID / NULL_WIFI_NAME_INVALID）
```

#### `GET /api/governance/ods_executions`

```
响应：24 条有执行统计的规则（不含上述 2 条）
每条包含：rule_code, run_label, affected_rows, affected_pct
```

**关键**：这两个端点**必须分离**（D-003 裁决），不允许合并为一个 API。

#### `GET /api/governance/parse_rules`

```
响应：parse_rule 列表
```

#### `GET /api/governance/compliance_rules`

```
响应：compliance_rule 列表
```

#### `GET /api/governance/trusted_filter`

```
响应：trusted 过滤损耗摘要
{
  "data_origin": "real",
  "data": {
    "total_l0_lac": 43771306,
    "trusted_hit": 30082381,
    "filtered_out": 13688925,
    "filtered_pct": 31.27,
    "by_tech": { "4G": 10004716, "5G": 3357500, "2G": 233772, "3G": 92937 },
    "by_source": [
      { "source": "sdk / daa / cell_infos", "count": 7015342 },
      { "source": "sdk / daa / ss1", "count": 5951068 },
      { "source": "sdk / dna / cell_infos", "count": 722515 }
    ],
    "filtered_with_rsrp": 12017352,
    "filtered_with_gps": 11350552
  }
}
```

### 3.5 对照 API

#### `GET /api/validation/compare?run_a=xxx&run_b=yyy`

```
响应：对比结果
{
  "data_origin": "synthetic",  // 或 "real"，取决于 run 来源
  "subject_scope": "full",
  "data": { ... }
}
```

当不足 2 个可对比 run 时：

```
{
  "data_origin": "fallback",
  "subject_scope": "empty",
  "subject_note": "至少需要两次运行才能对比",
  "data": null
}
```

---

## 4. Gate 独立规范

### 4.1 Gate 文件格式

每个 Gate 必须是独立文件，格式如下：

```markdown
# Gate X：名称

## 前置输入
- [列出必须先完成的 Gate 和前置条件]

## 通过条件
- [每条可校验]

## SQL 校验项
- [可直接执行的 SQL]

## API 校验项
- [可直接请求的 API 验证]

## 页面校验项（若适用）
- [Playwright 验证]

## 未通过时的停机规则
- [明确写出：不得做什么]
```

### 4.2 Gate 依赖链

```
Gate 0 (合同冻结)
  ↓
Gate A (元数据底座)
  ↓
Gate B (初始化完成)
  ↓
Gate C (滚动批次完成)
  ↓
Gate D (API 就绪)
  ↓
Gate E (前端验收)
```

每个 Gate 的详细内容见 `01_细化设计总稿.md` §5。

### 4.3 Gate 与 Phase 的映射

| Phase | 产出 | 通过 Gate |
|---|---|---|
| Phase 0 | 冻结任务书、矩阵、Gate | Gate 0 |
| Phase 1 | schema + 元数据底座 | Gate A |
| Phase 2a | full_initialization | Gate B |
| Phase 2b | rolling run | Gate C |
| Phase 3 | 读模型 API | Gate D |
| Phase 4 | 前端工作台 | Gate E |

---

## 5. 字段质量真相基线（冻结快照）

以下数据基于 PG17 2026-04-06 查询，作为 rebuild4 元数据快照的冻结基线。

### 5.1 `field_audit` 真相基线

| 指标 | 值 | 来源 |
|---|---:|---|
| 总字段数 | 27 | `SELECT count(*) FROM rebuild2_meta.field_audit` |
| keep | 17 | `WHERE decision = 'keep'` |
| parse | 3 | `WHERE decision = 'parse'` |
| drop | 7 | `WHERE decision = 'drop'` |

**文档旧口径**：`keep 19 / parse 3 / drop 5`  
**冻结结论**：以数据库为准（`17 / 3 / 7`），旧文档口径仅作历史说明

### 5.2 `target_field` 真相基线

| 指标 | 值 |
|---|---:|
| 总字段数 | 55 |

**文档旧口径**："约 60 个字段"  
**冻结结论**：以数据库为准（55），不再使用"约 60"

### 5.3 ODS 规则真相基线

| 指标 | 值 |
|---|---:|
| 规则定义总数 | 26 |
| rule_type = nullify | 22 |
| rule_type = convert | 3 |
| rule_type = delete | 1 |
| 执行统计覆盖 rule_code（每个 run_label） | 24 |
| 缺失执行统计的规则 | `NULL_WIFI_MAC_INVALID`, `NULL_WIFI_NAME_INVALID` |

**冻结结论**：定义层 26 条，执行层 24 条，差集 2 条必须显式标注

### 5.4 trusted 过滤真相基线

| 指标 | 值 |
|---|---:|
| `l0_lac` 总行数 | 43,771,306 |
| trusted 命中（`dwd_fact_enriched`） | 30,082,381 |
| 被过滤 | 13,688,925 |
| 被过滤比例 | 31.27% |

### 5.5 rebuild3 当前状态（只读参考）

| 指标 | 值 |
|---|---:|
| `fact_standardized` | 43,771,306 |
| `fact_governed` | 24,855,605 |
| `fact_pending_observation` | 10,590,738 |
| `fact_pending_issue` | 3,825,562 |
| `fact_rejected` | 4,499,401 |
| `obj_cell` | 573,561 |
| `obj_bs` | 193,036 |
| `obj_lac` | 50,153 |
| `run` | 4（1 full_initialization + 3 scenario_replay） |
| `batch_snapshot` | 1,562（142 batch × 4 stage × 11 metric） |
| `baseline_version` | 4 |

### 5.6 rebuild4 schema 当前状态

**PG17 验证**：`rebuild4` / `rebuild4_meta` schema 尚未创建。Phase 1 首步必须创建。

---

## 6. 校验方式

| 校验类型 | 方法 |
|---|---|
| 实体定义 | 与 Tier 0 文档交叉比对 lifecycle/health/资格枚举值 |
| 字段类型 | 与 rebuild3 现有表结构对比合理性 |
| API 响应 | 逐个 API 检查 `data_origin` 位置和必返回字段 |
| Gate SQL | 所有 SQL 可在 PG17 直接执行（schema 创建后） |
| 矩阵一致性 | 与 `01_细化设计总稿.md` §4 矩阵交叉引用 |
