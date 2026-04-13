# 数据库 Schema

本文件定义 rebuild5 所有数据表的归属、命名和版本策略。具体字段定义随开发逐步冻结。

## Schema 划分

| Schema | 用途 | 示例表 |
|--------|------|--------|
| `rebuild5` | 所有业务数据表 | `raw_lac`, `raw_gps`, `etl_parsed`, `etl_cleaned`, `profile_base`, `trusted_cell_library` |
| `rebuild5_meta` | 运行日志、统计、配置快照 | `etl_run_stats`, `step2_run_stats`, `run_log` |
| `legacy` | 原始数据（只读） | `网优项目_*` |

## 表命名规则

| 前缀 | 所属 Step | 说明 |
|------|-----------|------|
| `raw_*` | 数据准备 | 从 legacy 筛选出的原始数据，不做任何变换 |
| `etl_*` | Step 1 | 解析、清洗、同报文补齐产出 |
| `profile_*` | Step 2 | 基础画像、路由中间结果 |
| `path_a_*` | Step 2 | 命中可信库的记录 |
| `trusted_snapshot_*` | Step 3 | 冻结快照 |
| `snapshot_diff_*` | Step 3 | 快照差分 |
| `enriched_*` | Step 4 | 治理后事实层 |
| `gps_anomaly_*` | Step 4 | GPS 异常标记 |
| `trusted_*_library` | Step 5 | 正式可信库 |
| `collision_*` | Step 5 | 碰撞检测结果 |
| `cell_centroid_*` | Step 5 | 多质心独立记录 |
| `bs_centroid_*` | Step 5 | BS 多质心独立记录 |
| `cell_sliding_*` | Step 5 | 滑动窗口 |

## 枚举值速查表（全局冻结，不可变体拼写）

开发时必须使用以下精确拼写，不允许首字母大写、缩写或变体。完整定义见 `docs/00_全局约定.md`。

| 枚举域 | 合法值 | 备注 |
|--------|--------|------|
| `lifecycle_state` | `waiting`, `observing`, `qualified`, `excellent`, `dormant`, `retired` | 正向晋升 + 退出链路，不允许从 retired 直接回到 qualified |
| `position_grade` | `excellent`, `good`, `qualified`, `unqualified` | 定位质量，不等同于 lifecycle_state |
| `gps_confidence` | `high`, `medium`, `low`, `none` | |
| `signal_confidence` | `high`, `medium`, `low`, `none` | |
| `cell_scale` | `major`, `large`, `medium`, `small`, `micro` | |
| `drift_pattern` | `insufficient`, `stable`, `collision`, `migration`, `large_coverage`, `moderate_drift` | |
| `gps_anomaly_type` | `drift`, `time_cluster`, `migration_suspect` | Step 5 产出 |
| `gps_fill_source` | `raw_gps`, `ss1_own`, `same_cell`, `trusted_cell`, `none` | GPS 来源链路 |
| `gps_evidence_class` | `original`, `structural_fill`, `trusted_fill`, `none` | |
| `event_time_source` | `cell_ts`, `report_ts`, `gps_ts` | Step 1 产出 |
| `data_source` | `sdk` | 当前只有一种 |
| `cell_origin` | `cell_infos`, `ss1` | 解析来源 |
| `route_path` | `path_a`, `path_b`, `path_c` | Step 2 分流路径 |
| `bs_classification` | `collision_bs`, `dynamic_bs`, `large_spread`, `multi_centroid`, `normal_spread` | |
| `snapshot_diff_type` | `new`, `promoted`, `demoted`, `removed`, `eligibility_changed`, `geometry_changed` | |

## 版本策略

首轮实现使用 `batch_id` 做版本隔离，不引入完整的 `release_bundle`：

| 字段 | 说明 |
|------|------|
| `dataset_key` | 数据集标识，如 `sample_6lac` |
| `batch_id` | 批次序号，从 1 开始递增 |

- `trusted_snapshot` 带 `batch_id` 列区分版本
- `trusted_*_library` 始终代表最新已发布版本
- Step 2/3/4 读取的"上一版"通过 `batch_id - 1` 定位

## 主要表清单

### 数据准备

| 表 | 粒度 | 说明 |
|----|------|------|
| `raw_lac` | 原始行 | 6 LAC 样本的 lac 表原始数据 |
| `raw_gps` | 原始行 | 命中 6 LAC cell_id 的 gps 表原始数据 |

### Step 1: 数据源接入

| 表 | 粒度 | 说明 |
|----|------|------|
| `etl_parsed` | 记录 × Cell | 解析后的结构化记录 |
| `etl_cleaned` | 记录 × Cell | 清洗后（含 event_time_std） |
| `etl_filled` | 视图兼容层 | 兼容 rebuild4 的只读别名，实际底表仍是 `etl_cleaned` |

### Step 2: 基础画像 + 路由

| 表 | 粒度 | 说明 |
|----|------|------|
| `path_a_records` | 记录级 | 命中可信库，供 Step 4 |
| `profile_base` | Cell 级 | Path B 基础指标，供 Step 3 |

### Step 3: 流式质量评估

| 表 | 粒度 | 说明 |
|----|------|------|
| `trusted_snapshot` | Cell / BS / LAC | 冻结快照（含 batch_id） |
| `snapshot_diff` | Cell / BS / LAC | 与上一批差分 |

### Step 4: 知识补数

| 表 | 粒度 | 说明 |
|----|------|------|
| `enriched_records` | 记录级 | 治理后事实层 |
| `gps_anomaly_log` | 记录级 | GPS 异常候选 |

### Step 5: 画像维护

| 表 | 粒度 | 说明 |
|----|------|------|
| `trusted_cell_library` | Cell 级 | 可信小区正式库 |
| `trusted_bs_library` | BS 级 | 可信基站正式库 |
| `trusted_lac_library` | LAC 级 | 可信位置区正式库 |
| `collision_id_list` | cell_id 级 | 全局碰撞检测结果 |
| `cell_centroid_detail` | Cell × 簇 | 多质心独立记录 |
| `bs_centroid_detail` | BS × 簇 | BS 多质心独立记录 |
| `cell_sliding_window` | 观测级 | 滑动窗口明细 |

### 日志与统计（rebuild5_meta）

| 表 | 粒度 | 说明 |
|----|------|------|
| `run_log` | 运行级 | 所有 Step 的运行日志 |
| `step1_run_stats` | 运行级 | Step 1 ETL 统计 |
| `step2_run_stats` | 运行级 | Step 2 路由统计 |
| `step3_run_stats` | 运行级 | Step 3 评估统计 |
| `step4_run_stats` | 运行级 | Step 4 补数统计 |
| `step5_run_stats` | 运行级 | Step 5 维护统计 |
