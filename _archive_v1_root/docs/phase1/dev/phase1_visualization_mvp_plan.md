# Phase1 可视化 MVP 交付说明

更新时间：`2026-02-26`

## 1. 已交付能力（代码 + 文档 + 测试）
1. 观测层 SQL：
- `sql/phase1_obs/01_obs_ddl.sql`
- `sql/phase1_obs/02_obs_build.sql`
- `sql/phase1_obs/03_obs_gate_checks.sql`
2. 观测层运行脚本：
- `scripts/run_phase1_obs_pipeline.sh`（一键执行 DDL/Build/Gate，输出日志与报告）
- `scripts/check_phase1_obs_consistency.sh`（按 run_id 出一致性报告）
3. 运行配置与启动器：
- `scripts/phase1_env.sh`（默认数据库与服务环境）
- `launcher.py`（启动/关闭服务，打开页面）
 - `launcher.py console`（可点击控制台）
4. API 文档与实现：
- `docs/phase1/dev/phase1_api_spec.md`
- `apps/phase1_api/server.py`
5. API 启动脚本：
- `scripts/run_phase1_api.sh`
6. 自动化测试：
- `tests/phase1_api_smoke_test.py`
- `tests/phase1_api_contract_test.py`
7. 前端页面：
- `apps/phase1_ui/dashboard.html`（总览）
- `apps/phase1_ui/layer.html`（分层剖面）
- `apps/phase1_ui/reconciliation.html`（对账）
- `apps/phase1_ui/exposure.html`（异常暴露）
- `apps/phase1_ui/issues.html`（问题闭环）
- `apps/phase1_ui/patches.html`（补丁日志）
- `apps/phase1_ui/glossary.html`（术语与缩写独立页）
- `apps/phase1_ui/ui_base.css` + `apps/phase1_ui/ui_common.js`
8. 快照数据与截图：
- `apps/phase1_ui/dashboard_data.json`
- `apps/phase1_ui/dashboard_home_v5.png`
- `apps/phase1_ui/glossary_page_v1.png`
- `apps/phase1_ui/layer_page_v3.png`
- `apps/phase1_ui/reconciliation_page_v2.png`
- `apps/phase1_ui/exposure_page_v2.png`
- `apps/phase1_ui/issues_page_v3.png`
- `apps/phase1_ui/patches_page_v1.png`

## 2. MVP 覆盖范围
1. 总览、分层、对账、异常暴露、问题、补丁六类研究场景都可视化落地。
2. 问题单支持创建/更新，且新增状态机流转约束（非法流转返回 409）。
3. 补丁日志支持查询/创建，可与问题单按 `issue_id` 关联。
4. 列表型 API 与页面均支持分页（`page/page_size`）。
5. 页面支持 `run_id` 链路透传，支持 API 不可达时快照兜底。

## 3. 本地运行方式
在仓库根目录执行：

```bash
python3 launcher.py start
python3 launcher.py open dashboard
```

浏览器打开：
- `file:///Users/yangcongan/cursor/WangYou_Data/apps/phase1_ui/dashboard.html`
- `file:///Users/yangcongan/cursor/WangYou_Data/apps/phase1_ui/glossary.html`

## 4. 观测层构建与一致性检查
### 4.1 一键构建 obs
```bash
export PHASE1_DB_DSN='postgresql://user:pass@host:5432/ip_loc2'
scripts/run_phase1_obs_pipeline.sh
```

输出：
- `docs/phase1/dev/run_logs/phase1_obs_*.log`
- `docs/phase1/dev/run_logs/phase1_obs_pipeline_*.md`

### 4.2 一致性检查
```bash
export PHASE1_DB_DSN='postgresql://user:pass@host:5432/ip_loc2'
scripts/check_phase1_obs_consistency.sh              # 默认最新 run_id
scripts/check_phase1_obs_consistency.sh <run_id>     # 指定 run_id
```

输出：
- `docs/phase1/dev/run_logs/phase1_obs_consistency_<run_id>_*.md`

## 5. API 冒烟与合同测试
```bash
python3 tests/phase1_api_smoke_test.py
python3 tests/phase1_api_contract_test.py
```

当前基线：以上两项测试已通过（2026-02-26）。

## 6. 剩余工作（非阻塞）
1. 接入真实生产周期调度（cron/CI）并固化失败告警。
2. 为页面增加更多跨页联动（点击门禁项自动带过滤跳转）。
3. 补充真实案例的“问题-补丁-验证-回滚”演练记录。
