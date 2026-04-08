# rebuild3 时间快照重跑计划

## 目标

为 `/flow/snapshot`、`/runs`、`/flow/overview` 等场景感知页面提供真实时间线数据，而不是伪造环境对照或单一批次对照。

本计划服务两个目的：

1. 让系统真实产出“初始化后 + 后续每 2 小时快照”的时间点数据
2. 让不同初始化策略成为可切换、可比较的正式场景，而不是后台隐式运行参数

## 场景模型

时间快照不是单纯的“批次列表”，而是两层选择模型：

1. 场景选择（不同初始化策略）
2. 场景内时间点选择（初始化后与后续 rolling timepoints）

因此，评估与实现都必须明确区分：

- 不同场景之间的差异
- 同一场景内部不同时间点的差异

禁止把不同场景的数据混成一条时间线。

## 标准场景

### 场景 A
- `init_days = 1`
- `step_hours = 2`
- 语义：`1 天初始化 + 每 2 小时快照`

### 场景 B
- `init_days = 2`
- `step_hours = 2`
- 语义：`2 天初始化 + 每 2 小时快照`

这两个场景都必须：

- 写入 `rebuild3_meta.run`
- 形成独立 `run_id`
- 形成各自的 init 批次与 rolling 批次
- 形成各自的 `batch_snapshot`
- 在 UI 中可被明确选择

## 当前已验证的存储结构

### 主表

#### `rebuild3_meta.run`
至少承载以下语义：
- `run_id`
- `run_type`
- `status`
- `window_start`
- `window_end`
- `baseline_version`
- `scenario_key`
- `scenario_label`
- `init_days`
- `step_hours`
- `snapshot_source`
- `note`

#### `rebuild3_meta.batch`
至少承载以下语义：
- `batch_id`
- `run_id`
- `batch_type`
- `status`
- `window_start`
- `window_end`
- `input_rows`
- `output_rows`
- `is_rerun`
- `rerun_source_batch`
- `scenario_key`
- `timepoint_role`
- `batch_seq`
- `snapshot_at`

#### `rebuild3_meta.batch_snapshot`
至少承载以下语义：
- `batch_id`
- `stage_name`
- `metric_name`
- `metric_value`
- `created_at`

### 辅助元数据
- `rebuild3_meta.batch_flow_summary`
- `rebuild3_meta.batch_anomaly_summary`
- `rebuild3_meta.batch_baseline_refresh_log`
- `rebuild3_meta.baseline_version`
- `rebuild3_meta.v_flow_snapshot_timepoints`

## 已完成 smoke 验证

已验证 run：
- `RUN-SCN-SMOKE_INIT1D_STEP2H-20260405095741106`

已验证事实：
- `scenario_label = init_1d_step_2h`
- `init_days = 1`
- `step_hours = 2`
- `1` 个 init 批次 + `6` 个 rolling 2h 批次
- 可从该 run 内选任意两个后续时间点

已验证时间点示例：
- init：`BATCH-SCN-SMOKE_INIT1D_STEP2H-20260405095741106-INIT`
- t1：`BATCH-SCN-SMOKE_INIT1D_STEP2H-20260405095741106-R2H-002`
- t2：`BATCH-SCN-SMOKE_INIT1D_STEP2H-20260405095741106-R2H-006`

## 长时场景执行策略

### 原则
- 不等待长时任务全部结束再继续开发
- 先跑 smoke，确认 SQL / procedure / runner 正常
- smoke 通过后立即启动两套长时场景
- 长任务后台继续跑，前端/API/Prompt/复评准备同时推进

### Runner
当前 runner：
- `rebuild3/backend/scripts/run_timepoint_snapshot_scenarios.py`

支持：
- `--mode smoke`
- `--mode scenarios`

### 当前长任务状态
已启动命令：
- `python3 rebuild3/backend/scripts/run_timepoint_snapshot_scenarios.py --mode scenarios`

说明：
- 当前 CLI 环境下 `nohup` 式彻底脱离后台并不稳定，子进程可能被回收
- 当前采用“保持 exec session 存活”的方式执行长任务
- 不需要等待长任务结束再继续修复与复评准备

## 页面/API联调要求

### 对 `/flow/snapshot`
必须按以下顺序取数：

1. 从 `rebuild3_meta.run` 读取可选场景列表
2. 由用户选择一个场景
3. 从 `rebuild3_meta.batch` 读取该场景下的 init 与 rolling timepoints
4. 由用户在该场景内选择时间点 A / B
5. 从 `rebuild3_meta.batch_snapshot` 读取时间点快照指标
6. 从 `batch_flow_summary` / `batch_anomaly_summary` / `baseline_version` 等辅助元数据补上下文

### 对其他页面
以下页面也必须重新确认是否需要接入场景上下文：

- `/runs`
- `/flow/overview`
- `/observation`
- `/anomalies`
- `/compare`
- `/governance`

原则：

- 如果页面展示的是批次级、时间线级或 baseline 演进级信息，就必须明确它是否依赖场景上下文
- 不允许继续默认“当前唯一 run”或“当前 full batch”就是全局真相

## 与彻底复评的关系

彻底复评必须把本重跑计划视为正式输入之一，并明确检查：

1. 两套场景是否真实存在
2. 两套场景是否都可选
3. 场景与时间点是否被 UI 和 API 明确区分
4. `batch_snapshot` 是否真的是时间快照底座
5. 数据不足时页面是否诚实提示，而不是回退为别的比较逻辑

## 下一步核对项

1. 持续观察两套长时场景是否稳定出数
2. 用长时场景补做 `/flow/snapshot`、`/runs`、`/flow/overview` 联调
3. 在彻底复评里重新核对 scenario / timepoint 相关字段、边界与空状态
4. 如出现新的慢点，优先考虑 summary 表、索引、预聚合，而不是继续增加运行时复杂 SQL
