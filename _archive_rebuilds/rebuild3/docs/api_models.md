# API / 读模型约定

## 最小接口范围

### `GET /api/v1/runs/current`
- 返回当前 run / batch / baseline 上下文
- 关键字段：`run_id`、`batch_id`、`contract_version`、`rule_set_version`、`baseline_version`

### `GET /api/v1/objects/{object_type}`
- 返回对象列表
- 支持：`lifecycle_state`、`health_state`、`anchorable`、`baseline_eligible` 筛选

### `GET /api/v1/compare/sample`
- 返回样本 compare 汇总
- 关键字段：维度、rebuild2 值、rebuild3 值、差异分类、阻塞判断

### `GET /api/v1/governance/overview`
- 返回基础数据治理概览
- 关键字段：表数、字段数、实际使用数、迁移决策分布

## 统一类型约束

- 生命周期：`waiting / observing / active / dormant / retired / rejected`
- 健康状态：`healthy / insufficient / gps_bias / collision_suspect / collision_confirmed / dynamic / migration_suspect`
- 事实层：`fact_governed / fact_pending_observation / fact_pending_issue / fact_rejected`
- 迁移决策：`reuse / reshape / reference_only / retire`
