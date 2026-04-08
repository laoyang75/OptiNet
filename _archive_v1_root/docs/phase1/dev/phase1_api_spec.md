# Phase1 API Spec (MVP)

版本：`v0.2`  
更新时间：`2026-02-26`  
范围：对接 `Y_codex_obs_*`（观测层）并支持页面 MVP（总览/分层/对账/异常/问题/补丁/穿透）。

## 1. 设计原则
1. 页面优先查 API，不直接扫 Layer 大表。
2. 所有接口都支持 `run_id` 回放历史结果（适用接口会在 Query 中说明）。
3. 错误响应统一，便于前端稳定处理。
4. DB 不可达时自动回退快照模式（snapshot）。

## 2. 运行模式与环境变量
1. DB 模式：设置 `PHASE1_DB_DSN`，优先读取 `Y_codex_obs_*`。
2. 快照模式：未设置 `PHASE1_DB_DSN` 或 DB 不可用时，读取 `dashboard_data.json` + 本地 store。
3. 关键变量：
- `PHASE1_DB_DSN`
- `PHASE1_SNAPSHOT_FILE`
- `PHASE1_ISSUE_STORE_FILE`
- `PHASE1_PATCH_STORE_FILE`
- `PHASE1_PAGE_SIZE`（默认 100）
- `PHASE1_MAX_PAGE_SIZE`（默认 500）
4. 默认运行配置：`scripts/phase1_env.sh`（可覆盖）。

## 3. 统一约定
1. Base Path：`/api/phase1`
2. 默认 `run_id`：`Y_codex_obs_run_registry.run_started_at` 最新记录。
3. 时间字段：ISO8601 UTC。
4. 列表分页：`page`（默认1）、`page_size`（默认100，最大500）。
5. 统一错误体：

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "run_id not found",
    "details": {}
  }
}
```

## 4. 接口清单

### 4.1 GET `/health`
用途：服务可用性检查。

Response（示例）：

```json
{
  "service": "phase1_api",
  "db_mode_configured": true,
  "db_mode_active": true,
  "db_error": "",
  "snapshot_file": ".../apps/phase1_ui/dashboard_data.json"
}
```

### 4.2 GET `/api/phase1/overview`
用途：总览卡片 + 门禁总状态。

Query：
- `run_id` (optional)
- `operator`/`tech`/`tag` (optional，占位过滤参数，当前回传到 `filters`)

Response（核心字段）：
- `run_id`
- `run_status`
- `run_started_at`
- `run_finished_at`
- `layers[]`：`layer_id/input_rows/output_rows/pass_flag/payload`
- `gate_summary`：`pass_cnt/fail_cnt/total_cnt`
- `filters`

### 4.3 GET `/api/phase1/layer/{layer_id}`
用途：分层页（输入/输出/质量指标/规则命中）。

Path：
- `layer_id`: `L0|L2|L3|L4_Step40|L4_Final|L5_LAC|L5_BS|L5_CELL`

Query：
- `run_id` (optional)
- `metric_like` (optional)
- `rule_like` (optional)
- `page` (optional)
- `page_size` (optional)
- `operator`/`tech`/`tag` (optional，占位过滤)

Response（核心字段）：
- `run_id`
- `layer_id`
- `snapshot`
- `quality_metrics[]`
- `rule_hits[]`
- `page/page_size`
- `quality_metric_total/quality_metric_total_pages`
- `rule_hit_total/rule_hit_total_pages`
- `filters`

### 4.4 GET `/api/phase1/reconciliation`
用途：对账页（指标 vs 事实）。

Query：
- `run_id` (optional)
- `page` (optional)
- `page_size` (optional)
- `operator`/`tech`/`tag` (optional，占位过滤)

Response（核心字段）：
- `run_id`
- `checks[]`：`check_code/lhs_value/rhs_value/diff_value/pass_flag/details`
- `page/page_size/total/total_pages`
- `filters`

### 4.5 GET `/api/phase1/exposure-matrix`
用途：异常字段暴露矩阵页（BS/CELL）。

Query：
- `run_id` (optional)
- `object_level` (optional, `BS|CELL`)
- `page` (optional)
- `page_size` (optional)
- `operator`/`tech`/`tag` (optional，占位过滤)

Response（核心字段）：
- `run_id`
- `rows[]`：`object_level/field_code/exposed_flag/true_obj_cnt/total_obj_cnt/note`
- `page/page_size/total/total_pages`
- `filters`

### 4.6 GET `/api/phase1/issues`
用途：问题闭环页（问题池）。

Query：
- `run_id` (optional)
- `status` (optional: `new|in_progress|verified|rejected|rolled_back`)
- `severity` (optional: `P0|P1|P2`)
- `page` (optional)
- `page_size` (optional)

Response（核心字段）：
- `run_id`
- `items[]`：`issue_id/run_id/severity/layer_id/title/evidence_sql/status/owner/created_at/updated_at`
- `page/page_size/total/total_pages`

### 4.7 POST `/api/phase1/issues`
用途：创建问题单。

Request Body（必填）：
- `severity` (`P0|P1|P2`)
- `layer_id`
- `title`

Request Body（可选）：
- `run_id`
- `evidence_sql`
- `status`（默认 `new`）
- `owner`

Response：
- `item`
- `message`

### 4.8 PATCH `/api/phase1/issues/{issue_id}`
用途：更新问题单字段（状态/责任人/标题等）。

Request Body（至少一个字段）：
- `run_id|severity|layer_id|title|evidence_sql|status|owner`

Response：
- `item`
- `message`

状态流转约束：
1. `new -> in_progress|rejected|rolled_back`
2. `in_progress -> verified|rejected|rolled_back`
3. `verified -> rolled_back`
4. `rejected -> new|in_progress`
5. `rolled_back -> in_progress`

非法状态流转返回 `409 CONFLICT`。

### 4.9 GET `/api/phase1/patches`
用途：补丁日志列表。

Query：
- `run_id` (optional)
- `issue_id` (optional)
- `verified_flag` (optional: `true|false`)
- `page` (optional)
- `page_size` (optional)

Response（核心字段）：
- `run_id`
- `items[]`：`patch_id/issue_id/run_id/change_type/change_summary/owner/verified_flag/created_at`
- `page/page_size/total/total_pages`

### 4.10 POST `/api/phase1/patches`
用途：创建补丁日志记录。

Request Body（必填）：
- `change_type`
- `change_summary`

Request Body（可选）：
- `issue_id`
- `run_id`
- `owner`
- `verified_flag`（默认 `false`）

Response：
- `item`
- `message`

### 4.11 GET `/api/phase1/trace/{trace_key}`
用途：样本穿透（按主键/seq_id 回看前后处理）。

Path：
- `trace_key`: `seq_id` 或约定组合键

Query：
- `run_id` (optional)

Response（核心字段）：
- `run_id`
- `trace_key`
- `match_type`
- `match_count`
- `primary`
- `rows[]`
- `message`

说明：
1. `trace_key` 支持 `seq_id`（如 `118519266` 或 `seq:118519266`）。
2. 非数字 `trace_key` 会尝试按 `记录id`（其次 `did`）匹配。
3. 当 `match_count > 1` 时按 `ts_fill DESC` 返回，并提示“命中多条记录，已按最新时间优先展示”。
4. snapshot 模式下返回 `match_count=0` 与说明消息。

### 4.12 GET `/api/phase1/dashboard-snapshot`
用途：给首页看板返回聚合快照。

Query：
- `run_id` (optional)

Response：与 `apps/phase1_ui/dashboard_data.json` 同结构。

## 5. 数据映射（MVP）
1. `overview` -> `Y_codex_obs_run_registry` + `Y_codex_obs_layer_snapshot` + `Y_codex_obs_gate_result`
2. `layer/{layer_id}` -> `Y_codex_obs_layer_snapshot` + `Y_codex_obs_quality_metric` + `Y_codex_obs_rule_hit`
3. `reconciliation` -> `Y_codex_obs_reconciliation`
4. `exposure-matrix` -> `Y_codex_obs_exposure_matrix`
5. `issues` -> `Y_codex_obs_issue_log`
6. `patches` -> `Y_codex_obs_patch_log`

## 6. 非功能要求（MVP）
1. 列表接口均支持分页：`page/page_size`。
2. 错误响应统一为 `error.code/message/details`。
3. 所有核心查询接口返回 `run_id`，保证可追溯。
