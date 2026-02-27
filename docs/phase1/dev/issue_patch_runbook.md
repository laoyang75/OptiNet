# Phase1 问题-补丁闭环 Runbook

更新时间：`2026-02-26`

## 1. 目标
建立可执行闭环：`问题发现 -> 问题登记 -> 补丁执行 -> 验证确认 -> 归档回看`。

## 2. 对象与入口
1. 问题单：`Y_codex_obs_issue_log`，页面入口 `apps/phase1_ui/issues.html`
2. 补丁单：`Y_codex_obs_patch_log`，页面入口 `apps/phase1_ui/patches.html`

## 3. 问题状态机
允许状态：
1. `new`（新建）
2. `in_progress`（处理中）
3. `verified`（已验证）
4. `rejected`（驳回）
5. `rolled_back`（已回滚）

允许流转：
1. `new -> in_progress|rejected|rolled_back`
2. `in_progress -> verified|rejected|rolled_back`
3. `verified -> rolled_back`
4. `rejected -> new|in_progress`
5. `rolled_back -> in_progress`

说明：非法流转在 API 层返回 `409 CONFLICT`。

## 4. 标准操作流程
1. 发现问题：在 `issues.html` 或 `POST /api/phase1/issues` 创建问题单（至少填 `severity/layer_id/title`）。
2. 开始处理：将状态更新为 `in_progress`，补充 `owner` 与证据 SQL。
3. 执行补丁：在 `patches.html` 或 `POST /api/phase1/patches` 记录 `change_type/change_summary`。
4. 验证结果：通过门禁/对账验证后，将问题状态更新为 `verified`，并将补丁 `verified_flag=true`。
5. 回滚场景：若验证失败或上线异常，将问题更新为 `rolled_back`，并新增回滚补丁记录。

## 5. 最小字段建议
问题单建议最小字段：
1. `severity`
2. `layer_id`
3. `title`
4. `evidence_sql`
5. `owner`

补丁单建议最小字段：
1. `issue_id`（建议关联）
2. `change_type`（如 `sql_fix` / `code_fix` / `config_change`）
3. `change_summary`
4. `owner`
5. `verified_flag`

## 6. 联合验证清单
1. `scripts/run_phase1_obs_pipeline.sh` 跑通且门禁全绿。
2. `scripts/check_phase1_obs_consistency.sh <run_id>` 报告无关键差值异常。
3. `issues.html` 与 `patches.html` 页面可按 `run_id/issue_id` 查到闭环记录。

