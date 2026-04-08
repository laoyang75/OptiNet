# 实体字段接口与 Gate 细化

状态：round2 独立输出（Codex）  
更新时间：2026-04-06  
说明：计数事实来自 `PG17 MCP execute_sql`；结构字段来自 `PG17 MCP search_objects`。本文件把 round1 方向细化为可执行表结构、API 合同和 Gate 检查项。

---

## 1. 通用字段与命名合同

### 1.1 所有核心业务表必须统一携带的追溯字段

| 字段 | 适用对象 | 作用 |
|---|---|---|
| `run_id` | 事实、对象、批次级读模型 | 把结果绑定到唯一运行 |
| `batch_id` | 事实、对象、快照、异常、baseline 刷新日志 | 把结果绑定到唯一批次 |
| `contract_version` | run / batch / facts / objects / API context | 把结果绑定到任务合同版本 |
| `rule_set_version` | run / batch / facts / baseline | 把结果绑定到规则集版本 |
| `baseline_version` | governed / issue / objects / baseline | 绑定当前读取或生成的 baseline |
| `data_origin` | run / batch / API envelope / read model | 明示 `real / synthetic / fallback` |
| `origin_detail` | run / batch / API envelope / read model | 记录真实来源说明 |
| `subject_scope` | API envelope / read model | 明示当前响应主语 |
| `created_at` | 全部表 | 审计时间 |

### 1.2 不持久化的 UI 派生字段

以下字段不落业务主表，只允许在 API 或前端派生：

- `watch`
- `delta_color`
- `stability_level_label`
- `empty_state_message`

依据：Tier 0 已明确 `watch` 只能是 UI 派生态；其余同属展示层语义。

---

## 2. 实体合同

### 2.1 核心实体表

| 实体 | 主键 | 必备状态/字段 | 备注 |
|---|---|---|---|
| `contract_version` | `contract_version` | `doc_path` `doc_checksum` `status` `effective_at` | 当前 PG17 中尚无独立表 |
| `rule_set_version` | `rule_set_version` | `contract_version` `status` `published_at` | 当前 PG17 中尚无独立表 |
| `run` | `run_id` | `run_type` `status` `data_origin` `origin_detail` `window_start/end` | 现有 rebuild3 已有雏形 |
| `batch` | `batch_id` | `run_id` `batch_type` `status` `batch_seq` `snapshot_at` | 现有 rebuild3 已有雏形 |
| `standardized_event` | `standardized_event_id` | 来源、事件时间、结构有效性、业务主键 | 对应 `fact_standardized` |
| `routed_fact` | `standardized_event_id` | 去向、原因、对象锚点、资格、异常 | 对应四分流表 |
| `cell` | `object_id` | lifecycle/health/三层资格/画像摘要 | 主治理对象 |
| `bs` | `object_id` | lifecycle/health/三层资格/空间摘要 | 空间锚点 |
| `lac` | `object_id` | lifecycle/health/三层资格/区域摘要 | 区域主语 |
| `baseline_version` | `baseline_version` | `run_id` `batch_id` `refresh_reason` | 已有雏形，但缺历史实体合同 |
| `governance_rule` | `rule_code` | `rule_type` `target_field` `tech_scope` `is_active` | 统一承接 parse/compliance/ODS |
| `gate` | `gate_code` | `phase` `blocking` `pass_condition` | 当前 PG17 无独立 Gate 表 |

### 2.2 实体层风险说明

- `rebuild3_meta.run` / `batch` 已能表达 run/batch，但尚未内建 `data_origin`、`origin_detail`、`subject_scope`。
- `rebuild3_meta.baseline_version` 已有 4 条，但 `baseline_*` 仍只有 1 个物理版本。
- `rebuild3_meta.batch_anomaly_summary` 目前混合了对象状态与记录级异常，不适合作为正式 anomaly 实体。

校验动作：

- SQL：检查实体表主键、追溯字段、版本字段是否齐备
- API：每类实体 endpoint 返回统一 envelope
- 文档：实体职责必须能回指到 page/API/table matrix

---

## 3. `rebuild4_meta` 表设计

### 3.1 版本与运行控制表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `contract_version` | `contract_version` | `doc_path`, `doc_checksum`, `source_round`, `status`, `effective_at`, `created_at` | 把 round2/round3 冻结稿变成可追溯实体 |
| `rule_set_version` | `rule_set_version` | `contract_version`, `rule_bundle_hash`, `status`, `published_at`, `created_at` | 规则与任务合同解耦 |
| `source_adapter` | `source_adapter_code` | `source_schema`, `source_table`, `adapter_type`, `window_grain`, `is_active`, `created_at` | 记录 `l0_gps`、`l0_lac`、后续 rolling 输入适配器 |
| `run` | `run_id` | `run_type`, `status`, `data_origin`, `origin_detail`, `subject_scope`, `window_start`, `window_end`, `contract_version`, `rule_set_version`, `parent_run_id`, `created_at`, `completed_at` | 新增来源合同字段 |
| `batch` | `batch_id` | `run_id`, `batch_type`, `status`, `batch_seq`, `data_origin`, `origin_detail`, `subject_scope`, `window_start`, `window_end`, `input_rows_gps`, `input_rows_lac`, `standardized_rows`, `is_rerun`, `rerun_source_batch_id`, `timepoint_role`, `snapshot_at`, `created_at`, `completed_at` | 比 rebuild3 多输入分量与来源字段 |
| `initialization_step_log` | `(run_id, step_seq)` | `step_code`, `step_name`, `status`, `input_count`, `output_count`, `pass_rate`, `note`, `started_at`, `completed_at` | 支撑初始化页流程区 |
| `initialization_note` | `(run_id, note_type)` | `note_text`, `is_research_period`, `sort_order`, `created_at` | 支撑初始化页“研究期口径说明” |

### 3.2 批次、异常与快照摘要表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `batch_snapshot` | `(batch_id, stage_name, metric_name)` | `metric_value`, `metric_unit`, `created_at` | 沿用 rebuild3 结构，但强制覆盖 real completed batch |
| `batch_flow_summary` | `(batch_id, fact_layer)` | `row_count`, `row_ratio`, `created_at` | 首页/批次中心四分流摘要 |
| `batch_transition_summary` | `(batch_id, object_type, transition_code)` | `object_count`, `delta_count`, `created_at` | 替代当前仅 7 行的 `batch_decision_summary` |
| `batch_anomaly_object_summary` | `(batch_id, object_type, anomaly_name)` | `object_count`, `severity`, `created_at` | 对象级异常汇总 |
| `batch_anomaly_record_summary` | `(batch_id, anomaly_name)` | `fact_count`, `route_target`, `severity`, `created_at` | 记录级异常与拒收汇总 |
| `batch_anomaly_impact_summary` | `(batch_id, object_type, impact_target)` | `impact_count`, `created_at` | 支撑异常工作台“下游影响” |

### 3.3 baseline 版本与 diff 表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `baseline_version` | `baseline_version` | `run_id`, `batch_id`, `data_origin`, `origin_detail`, `rule_set_version`, `refresh_reason`, `object_count`, `created_at` | 比 rebuild3 多来源字段 |
| `baseline_refresh_log` | `(batch_id, baseline_version)` | `refresh_reason`, `triggered`, `created_at` | 追踪为何刷新/未刷新 |
| `baseline_diff_summary` | `(baseline_version_from, baseline_version_to, object_type)` | `added_count`, `removed_count`, `changed_count`, `stable_count`, `stability_score`, `created_at` | baseline 页面概况与稳定性卡片 |
| `baseline_diff_object` | `(baseline_version_from, baseline_version_to, object_type, object_id)` | `diff_type`, `diff_payload_json`, `risk_flag`, `created_at` | 差异对象列表 |

### 3.4 governance 元数据表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `asset_field_catalog` | `(asset_name, field_name)` | `field_label_cn`, `layer_name`, `data_type`, `is_nullable`, `is_core`, `status`, `source_desc`, `semantic_desc`, `created_at` | 对标现有空表 `rebuild3_meta.asset_field_catalog` |
| `asset_table_catalog` | `asset_name` | `table_schema`, `table_name`, `table_type`, `grain_desc`, `primary_key_desc`, `refresh_mode`, `upstream_desc`, `retention_policy`, `owner_domain`, `is_core`, `status`, `created_at` | governance 表目录 |
| `asset_usage_map` | `(asset_type, asset_name, consumer_type, consumer_name)` | `usage_role`, `usage_desc`, `created_at` | 页面/API/任务使用关系 |
| `asset_migration_decision` | `(asset_type, asset_name)` | `decision`, `target_asset`, `decision_reason`, `owner_note`, `created_at` | 迁移状态页 |
| `field_audit` | `id` | 延续 rebuild2 结构 + `rule_set_version` | 可直接承接 `rebuild2_meta.field_audit` |
| `target_field` | `id` | 延续 rebuild2 结构 + `rule_set_version` | 55 个 target field 作为正式目录 |
| `parse_rule` | `rule_code` | `target_field`, `source_origin`, `source_path`, `tech_scope`, `priority`, `transform`, `description`, `is_active`, `rule_set_version`, `created_at` | 解决当前 0 行问题 |
| `parse_execution` | `(run_label, rule_code, executed_at)` | `target_field`, `parsed_rows`, `success_rows`, `failure_rows`, `error_sample`, `created_at` | 让 parse 规则具备执行审计位 |
| `compliance_rule` | `rule_code` | `target_field`, `rule_type`, `rule_config`, `tech_scope`, `severity`, `description`, `is_active`, `rule_set_version`, `created_at` | 解决当前 0 行问题 |
| `compliance_execution` | `(run_label, rule_code, executed_at)` | `target_field`, `checked_rows`, `violation_rows`, `severity`, `created_at` | 让 compliance 规则具备执行审计位 |
| `ods_clean_rule` | `rule_code` | `field_name`, `rule_type`, `condition_sql`, `action`, `severity`, `category`, `is_active`, `rule_set_version`, `created_at` | 承接 26 条定义 |
| `ods_clean_execution` | `(run_label, rule_code, executed_at)` | `total_rows`, `affected_rows`, `affect_rate`, `execution_status`, `note` | 承接 24 条执行统计与缺口说明 |
| `trusted_loss_summary` | `(source_snapshot_id)` | `total_rows`, `trusted_rows`, `filtered_rows`, `filtered_pct`, `filtered_with_rsrp`, `filtered_with_gps`, `created_at` | 固化 trusted 损耗主指标 |
| `trusted_loss_breakdown` | `(source_snapshot_id, breakdown_type, breakdown_key)` | `row_count`, `row_ratio`, `rank_no`, `created_at` | `breakdown_type` 取值 `tech` / `source_combo` |

### 3.5 Gate 元数据表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `gate_definition` | `gate_code` | `gate_name`, `phase_name`, `blocking`, `description`, `owner_domain`, `created_at` | Gate 独立成文的数据库承接 |
| `gate_check_item` | `(gate_code, check_seq)` | `check_type`, `check_target`, `expected_condition`, `severity`, `created_at` | `check_type` 取值 `sql/api/page/doc` |
| `gate_run_result` | `(gate_code, execution_id)` | `run_id`, `batch_id`, `status`, `observed_value`, `message`, `executed_at` | 未通过即停机 |

### 3.6 辅助任务表与读模型视图

| 对象 | 类型 | 必备字段 | 设计说明 |
|---|---|---|---|
| `compare_job` | 表 | `compare_job_id`, `run_id_a`, `run_id_b`, `comparison_mode`, `status`, `data_origin`, `origin_detail`, `created_at`, `completed_at` | compare 页异步任务与来源合同 |
| `compare_result` | 表 | `compare_job_id`, `compare_scope`, `metric_group`, `metric_name`, `value_a`, `value_b`, `diff_value`, `diff_ratio`, `severity`, `is_blocking`, `explanation`, `created_at` | compare 页结果明细；禁止回写主流程表 |
| `v_flow_snapshot_timepoints` | 视图 | `run_id`, `run_type`, `batch_id`, `timepoint_role`, `batch_seq`, `snapshot_at`, `baseline_version`, `is_rerun` | 流转快照页可选时间点 |
| `v_observation_candidate` | 视图 | `object_id`, `lifecycle_state`, `missing_layer`, `progress_exist`, `progress_anchor`, `progress_baseline`, `trend_status`, `suggested_action`, `run_id`, `batch_id` | 等待/观察工作台三层资格进度 |
| `v_anomaly_object` | 视图 | `object_type`, `object_id`, `anomaly_name`, `severity`, `impact_count`, `found_batch_id`, `run_id`, `batch_id` | 对象级异常列表 |
| `v_anomaly_record` | 视图 | `anomaly_name`, `route_target`, `fact_count`, `severity`, `sample_batch_id`, `run_id`, `batch_id` | 记录级异常列表 |
| `v_object_summary` | 视图 | `object_type`, `lifecycle_state`, `health_state`, `object_count`, `delta_count`, `run_id`, `batch_id` | 对象浏览汇总条 |

---

## 4. `rebuild4` 业务表设计

### 4.1 事实层表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `fact_standardized` | `standardized_event_id` | `source_name`, `source_record_id`, `source_detail`, `parsed_from`, `event_time`, `operator_code`, `tech_norm`, `lac`, `bs_id`, `cell_id`, `dev_id`, `raw_lon`, `raw_lat`, `gps_valid`, `rsrp_raw`, `rsrq_raw`, `sinr_raw`, `dbm_raw`, `structural_valid`, `structural_reason`, `run_id`, `batch_id`, `contract_version`, `rule_set_version`, `data_origin`, `origin_detail`, `created_at` | 对标 rebuild3 结构，补足来源合同 |
| `fact_governed` | `standardized_event_id` | `lon_final`, `lat_final`, `gps_source`, `signal_source`, `baseline_eligible`, `anomaly_tags`, `route_reason`, `baseline_version`, `run_id`, `batch_id`, `data_origin`, `origin_detail`, `created_at` | 主流程正式事实 |
| `fact_pending_observation` | `standardized_event_id` | `missing_layer`, `anomaly_tags`, `route_reason`, `baseline_version`, `run_id`, `batch_id`, `data_origin`, `origin_detail`, `created_at` | 等待/观察来源表 |
| `fact_pending_issue` | `standardized_event_id` | `health_state`, `anomaly_tags`, `baseline_eligible`, `issue_severity`, `route_reason`, `baseline_version`, `run_id`, `batch_id`, `data_origin`, `origin_detail`, `created_at` | 异常工作台对象/记录来源表 |
| `fact_rejected` | `standardized_event_id` | `rejection_reason`, `rule_code`, `run_id`, `batch_id`, `data_origin`, `origin_detail`, `created_at` | 结构不合规与拒收事实 |

### 4.2 对象层表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `obj_cell` | `object_id` | `operator_code`, `tech_norm`, `lac`, `bs_id`, `cell_id`, `lifecycle_state`, `health_state`, `existence_eligible`, `anchorable`, `baseline_eligible`, `record_count`, `gps_count`, `device_count`, `active_days`, `centroid_lon`, `centroid_lat`, `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_original_ratio`, `signal_original_ratio`, `anomaly_tags`, `parent_bs_object_id`, `run_id`, `batch_id`, `baseline_version`, `data_origin`, `origin_detail`, `created_at` | 沿用 rebuild3 主字段 |
| `obj_bs` | `object_id` | `operator_code`, `tech_norm`, `lac`, `bs_id`, `lifecycle_state`, `health_state`, `existence_eligible`, `anchorable`, `baseline_eligible`, `cell_count`, `active_cell_count`, `record_count`, `gps_count`, `device_count`, `active_days`, `center_lon`, `center_lat`, `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_original_ratio`, `signal_original_ratio`, `anomaly_tags`, `parent_lac_object_id`, `run_id`, `batch_id`, `baseline_version`, `data_origin`, `origin_detail`, `created_at` | 支撑对象浏览与 BS 画像 |
| `obj_lac` | `object_id` | `operator_code`, `tech_norm`, `lac`, `lifecycle_state`, `health_state`, `existence_eligible`, `anchorable`, `baseline_eligible`, `bs_count`, `active_bs_count`, `cell_count`, `record_count`, `gps_count`, `active_days`, `center_lon`, `center_lat`, `gps_original_ratio`, `signal_original_ratio`, `region_quality_label`, `anomaly_tags`, `run_id`, `batch_id`, `baseline_version`, `data_origin`, `origin_detail`, `created_at` | 保留 `region_quality_label` 但降为派生说明 |
| `obj_state_history` | `history_id` | `object_type`, `object_id`, `lifecycle_state`, `health_state`, `anchorable`, `baseline_eligible`, `changed_reason`, `run_id`, `batch_id`, `changed_at` | 与 rebuild3 一致 |
| `obj_relation_history` | `history_id` | `relation_type`, `parent_object_id`, `child_object_id`, `relation_status`, `changed_reason`, `run_id`, `batch_id`, `changed_at` | 与 rebuild3 一致 |

### 4.3 baseline 与 profile 表

| 表 | 主键 | 必备字段 | 设计说明 |
|---|---|---|---|
| `baseline_cell` | `(baseline_version, object_id)` | `operator_code`, `tech_norm`, `lac`, `bs_id`, `cell_id`, `center_lon`, `center_lat`, `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_original_ratio`, `signal_original_ratio`, `created_at` | 版本化存储；禁止只保留当前 |
| `baseline_bs` | `(baseline_version, object_id)` | `operator_code`, `tech_norm`, `lac`, `bs_id`, `center_lon`, `center_lat`, `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_original_ratio`, `signal_original_ratio`, `created_at` | 同上 |
| `baseline_lac` | `(baseline_version, object_id)` | `operator_code`, `tech_norm`, `lac`, `center_lon`, `center_lat`, `gps_original_ratio`, `signal_original_ratio`, `created_at` | 同上 |
| `profile_cell` | `object_id` | `operator_cn`, `sector_id`, `record_count`, `device_count`, `active_days`, `gps_count`, `center_lon`, `center_lat`, `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_max_dist_m`, `gps_original_ratio`, `signal_original_ratio`, `rsrp_avg`, `gps_anomaly`, `dist_to_bs_m`, `bs_gps_quality`, `run_id`, `batch_id`, `data_origin`, `origin_detail`, `created_at` | 可由 `stg_cell_profile` 迁移/重命名而来 |
| `profile_bs` | `object_id` | `record_count`, `device_count`, `active_days`, `gps_count`, `center_lon`, `center_lat`, `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_max_dist_m`, `gps_quality`, `gps_original_ratio`, `signal_original_ratio`, `rsrp_avg`, `run_id`, `batch_id`, `data_origin`, `origin_detail`, `created_at` | 可由 `stg_bs_profile` 迁移/重命名而来 |
| `profile_lac` | `object_id` | `record_count`, `bs_count`, `cell_count`, `active_days`, `center_lon`, `center_lat`, `gps_original_ratio`, `signal_original_ratio`, `run_id`, `batch_id`, `data_origin`, `origin_detail`, `created_at` | 可由 `stg_lac_profile` 迁移/重命名而来 |

---

## 5. 读模型与 API 合同

### 5.1 API 统一返回 envelope

```json
{
  "data_origin": "real",
  "origin_detail": "rebuild4_meta.batch_flow_summary@BATCH-...",
  "subject_scope": "batch",
  "context": {
    "run_id": "RUN-...",
    "batch_id": "BATCH-...",
    "baseline_version": "BASELINE-...",
    "contract_version": "rebuild4-contract-v1",
    "rule_set_version": "rebuild4-rule-set-v1"
  },
  "data": {}
}
```

### 5.2 流程与批次 API

| API | 主语 | 来源表/视图 | 必返字段 | Gate |
|---|---|---|---|---|
| `GET /api/flow-overview?batch_id=` | batch | `batch` + `batch_flow_summary` + `batch_anomaly_*` | 四分流、delta、问题入口、baseline_version、data_origin | G3/G4 |
| `GET /api/flow-snapshot/timepoints` | timepoint 列表 | `batch` + `batch_snapshot` | `batch_id`, `snapshot_at`, `timepoint_role`, `baseline_version` | G3/G4 |
| `GET /api/flow-snapshot?batch_ids=` | 多 timepoint | `batch_snapshot` | 3 列时间快照所需 11 指标 | G3/G4 |
| `GET /api/runs/current` | run | `run` | 当前 run 上下文、状态、来源合同 | G2/G4 |
| `GET /api/batches?run_id=` | batch 列表 | `batch` + `batch_flow_summary` | 状态、四分流、delta、is_rerun | G3/G4 |
| `GET /api/batches/:id/detail` | 单 batch | `batch_transition_summary` + `batch_anomaly_*` | 晋升/降级/级联/问题摘要 | G3/G4 |
| `GET /api/batches/trend?last=` | 趋势 | `batch` + `batch_flow_summary` | 多批趋势、窗口范围、delta 基准 | G3/G4 |

### 5.3 对象与工作台 API

| API | 主语 | 来源表/视图 | 必返字段 | Gate |
|---|---|---|---|---|
| `GET /api/objects` | 对象列表 | `obj_cell` / `obj_bs` / `obj_lac` | lifecycle、health、三层资格、主键搜索字段 | G3/G4 |
| `GET /api/objects/summary` | 对象汇总 | `obj_*` 聚合视图 | 状态计数、delta、对象类型 | G3/G4 |
| `GET /api/objects/:key/detail` | 单对象 | `obj_*` + `obj_state_history` + `obj_relation_history` + `profile_*` | snapshot、history、facts、anomalies、impact | G3/G4 |
| `GET /api/observation-workspace` | waiting/observing cell | `v_observation_candidate` | 三层资格进度、趋势、建议动作 | G3/G4 |
| `GET /api/anomaly-workspace?view=object` | 对象级异常 | `v_anomaly_object` | anomaly_name、severity、影响对象、发现批次 | G3/G4 |
| `GET /api/anomaly-workspace?view=record` | 记录级异常 | `v_anomaly_record` | anomaly_name、route_target、fact_count、严重度 | G3/G4 |
| `GET /api/anomaly-workspace/summary` | 异常总览 | `batch_anomaly_object_summary` + `batch_anomaly_record_summary` | 两类异常统计与下游影响 | G3/G4 |
| `GET /api/anomaly-workspace/:key/impact` | 影响路径 | `batch_anomaly_impact_summary` + 对象明细 | 受影响 BS/LAC/事实数 | G3/G4 |

### 5.4 baseline、profile、initialization API

| API | 主语 | 来源表/视图 | 必返字段 | Gate |
|---|---|---|---|---|
| `GET /api/baseline/current` | 当前 baseline | `baseline_version` + `baseline_*` 当前视图 | 版本信息、触发原因、覆盖范围 | G6 |
| `GET /api/baseline/current/diff` | 当前 vs 上一版 | `baseline_diff_summary` + `baseline_diff_object` | `previous_available`, 差异汇总、差异对象 | G6 |
| `GET /api/baseline/history` | baseline 历史 | `baseline_version` | 历史版本列表与触发批次 | G6 |
| `GET /api/profiles/lac` | LAC 画像 | `profile_lac` + `obj_lac` + `baseline_lac` | 区域质量、对象统计、来源构成 | G6 |
| `GET /api/profiles/bs` | BS 画像 | `profile_bs` + `obj_bs` + `baseline_bs` | 空间精度、旧分类解释层、来源构成 | G6 |
| `GET /api/profiles/cell` | Cell 画像 | `profile_cell` + `obj_cell` + `baseline_cell` | 空间精度、事实去向、来源构成 | G6 |
| `GET /api/initialization/:run_id` | full init run | `run` + `batch` + `initialization_step_log` + `batch_snapshot` | 流程步骤、完成状态、汇总、口径说明 | G2/G4 |

### 5.5 governance 与 compare API

| API | 主语 | 来源表/视图 | 必返字段 | Gate |
|---|---|---|---|---|
| `GET /api/governance/overview` | 资产概览 | `asset_table_catalog` + `asset_field_catalog` + `asset_usage_map` | 表数、字段数、使用数、待迁移数 | G5 |
| `GET /api/governance/field_audit` | 字段审计 | `field_audit` | keep/parse/drop、字段说明 | G5 |
| `GET /api/governance/target_fields` | 目标字段 | `target_field` | 字段目录、category、source_type | G5 |
| `GET /api/governance/parse_rules` | parse 规则 | `parse_rule` | rule_code、target_field、source_path、priority | G5 |
| `GET /api/governance/compliance_rules` | compliance 规则 | `compliance_rule` | rule_code、target_field、rule_type、severity | G5 |
| `GET /api/governance/ods_rules` | ODS 定义层 | `ods_clean_rule` | 26 条规则定义 | G5 |
| `GET /api/governance/ods_executions` | ODS 执行层 | `ods_clean_execution` | 24 条执行统计 + 缺口状态 | G5 |
| `GET /api/governance/trusted_loss` | trusted 损耗 | `trusted_loss_summary` + `trusted_loss_breakdown` | 总损耗、制式分布、来源组合分布 | G5 |
| `GET /api/governance/tables` | 表目录 | `asset_table_catalog` | 粒度、主键、刷新方式、迁移状态 | G5 |
| `GET /api/governance/usage/:table_name` | 使用关系 | `asset_usage_map` | 上下游、页面/API/任务消费方 | G5 |
| `GET /api/governance/migration` | 迁移状态 | `asset_migration_decision` | 直接复用 / 重组迁移 / 仅参考 / 可淘汰 | G5 |
| `GET /api/validation/compare?run_a=&run_b=` | 对照结果 | `compare_job` / `compare_result` | `data_origin`, `comparison_mode`, `score`, `diff_items` | G7 |

`/api/validation/compare` 的补充约束：

- 若 `data_origin = synthetic`，必须返回 `banner_level = warning`
- 不允许 `fallback`
- 不进入正式完成标准

---

## 6. Gate 细化

### 6.1 Gate 定义表

| Gate | 阶段 | SQL 校验 | API 校验 | 页面校验（round3） | 未通过动作 |
|---|---|---|---|---|---|
| `G0_CONTRACT_FREEZE` | 编码前 | 输出文件齐全 | 无 | 无 | 直接停机 |
| `G1_SCHEMA_META_READY` | Phase 1 | schema 已建；`contract_version`/`rule_set_version`/`parse_rule`/`compliance_rule`/`asset_*` 非空 | `/api/governance/overview` 非空 | governance 页面能加载概览卡 | 禁止进入 full init |
| `G2_REAL_INITIALIZATION_READY` | Phase 2 | 至少 1 条 completed real init run；四分流守恒；baseline 生成 | `/api/initialization/:run_id` 有步骤与汇总 | initialization 页展示流程与四分流 | 禁止进入 rolling/API |
| `G3_REAL_ROLLING_READY` | Phase 2/3 | 至少 1 条 rolling run；completed batch > 1；每批 11 个快照指标 | `/api/flow-overview` `/api/batches` 非空 | 首页、批次中心可联动 | 禁止进入对象/工作台联调 |
| `G4_API_ORIGIN_CONTRACT` | Phase 3 | 核心 read model 均含来源字段 | 核心 API envelope 齐备 | 页面 banner/空状态按来源显示 | 禁止前端联调 |
| `G5_GOVERNANCE_FORMALIZED` | Phase 3/4 | ODS 定义/执行分表；trusted 损耗可重算；资产目录非空 | `/api/governance/*` 非空且可筛选 | governance 页 4 个 Tab 可用 | governance 不计完成 |
| `G6_BASELINE_HONESTY` | Phase 3/4 | baseline 版本可追溯；无上一版时 diff 诚实返回 | `/api/baseline/current/diff` 返回 `previous_available` | baseline 页诚实展示“暂无上一版可比” | baseline/profile 不得上线 |
| `G7_COMPARE_DEGRADED` | Phase 4 | compare 若无 real 数据则仍可为空；若有 synthetic 必有来源标记 | compare API 返回 `comparison_mode` | compare 页显示 banner 且不在首页入口 | compare 不算正式完成 |

### 6.2 推荐固化的 SQL 校验语句

```sql
-- V01: rebuild4 schema 就绪
SELECT COUNT(*)
FROM information_schema.schemata
WHERE schema_name IN ('rebuild4', 'rebuild4_meta');

-- V02: 四分流守恒
SELECT
  COUNT(*) AS standardized_rows,
  (SELECT COUNT(*) FROM rebuild4.fact_governed WHERE batch_id = $1)
+ (SELECT COUNT(*) FROM rebuild4.fact_pending_observation WHERE batch_id = $1)
+ (SELECT COUNT(*) FROM rebuild4.fact_pending_issue WHERE batch_id = $1)
+ (SELECT COUNT(*) FROM rebuild4.fact_rejected WHERE batch_id = $1) AS routed_rows
FROM rebuild4.fact_standardized
WHERE batch_id = $1;

-- V03: completed batch 快照覆盖
SELECT b.batch_id, COUNT(*) AS snapshot_metrics
FROM rebuild4_meta.batch b
LEFT JOIN rebuild4_meta.batch_snapshot s ON s.batch_id = b.batch_id
WHERE b.status = 'completed'
GROUP BY b.batch_id;

-- V04: ODS 定义/执行分层
SELECT COUNT(*) FROM rebuild4_meta.ods_clean_rule WHERE is_active;
SELECT run_label, COUNT(DISTINCT rule_code) FROM rebuild4_meta.ods_clean_execution GROUP BY run_label;

-- V05: baseline 诚实
SELECT baseline_version, COUNT(*)
FROM rebuild4.baseline_cell
GROUP BY baseline_version;
```

### 6.3 推荐固化的 API 校验动作

1. `GET /api/flow-overview?batch_id=...`
   - 断言存在 `data_origin`, `origin_detail`, `subject_scope`
   - 断言 `subject_scope = batch`
   - 断言四分流合计等于 `standardized_rows`

2. `GET /api/governance/ods_rules` + `GET /api/governance/ods_executions`
   - 断言 endpoint 拆分
   - 断言 26 条定义与 24 条执行统计不混在同一 payload

3. `GET /api/baseline/current/diff`
   - 断言仅有一版时 `previous_available = false`
   - 断言 message 明确说明“暂无上一版 real baseline 可比”

4. `GET /api/validation/compare`
   - 断言 `data_origin != fallback`
   - 若 `data_origin = synthetic`，断言存在 banner 字段

---

## 7. 本文件对应的主要风险

1. **表设计仍需 human 对 baseline 历史策略做最后拍板。**
   - 见 `03_候选裁决问题.md` 的 D-201。
2. **governance 元数据填充方式仍需裁决。**
   - 当前空表不能直接支撑页面；需要确认采用“数据库 introspection + 人工补注”还是纯人工维护。
3. **compare 页是否允许 synthetic，需要单独冻结。**
   - 当前 `compare_result = 0`，不宜默认为正式能力。

本文件已把这些问题收敛到可裁决级别，不再是模糊风险。
