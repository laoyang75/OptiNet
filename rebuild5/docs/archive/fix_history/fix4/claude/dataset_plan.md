# Fix4 Claude 数据集计划

## 使用的共享原始表

| 表 | 用途 |
|----|------|
| `rebuild5_fix4.etl_cleaned_shared_sample` | 主输入，7 天 ETL 清洗后数据（1,937,395 行） |
| `rebuild5_fix4.focus_cells_shared` | 40 个重点 Cell，用于深度分析 |
| `rebuild5_fix4.raw_gps_shared_sample` | 未使用（本轮直接从 etl_cleaned 开始） |

## 派生工作集

### 1. 滑动窗口 `c_window`

- 来源：`etl_cleaned_shared_sample` 按天切片
- 目标：模拟 Step 5.0 的 `cell_sliding_window`，累积 7 天数据
- 最终大小：1,937,395 行

### 2. Core Position Filter 中间表

每批重建，用于模拟 `window.py:build_cell_core_gps_stats()` 的两阶段过滤：

| 表 | 行数（batch 7） | 目标 |
|----|----------------|------|
| `c_seed_grid` | ~68k | 200m 网格聚合 |
| `c_primary_seed` | ~18k | 每 Cell 最密网格点 |
| `c_seed_dist` | ~1.74M | GPS 点到 seed 距离 |
| `c_cutoff` | ~18k | 自适应裁剪半径 |
| `c_core_pts` | ~1.65M | 过滤后核心点 |
| `c_core_stats` | ~18k | 核心点质心统计 |
| `c_radius` | ~18k | core p50/p90 |
| `c_raw_radius` | ~18k | raw p90 对比 |

### 3. Cell Library `c_cell_lib`

- 累积所有 7 批结果
- 最终大小：7 × ~16k = 117,595 行
- 用途：lifecycle 趋势分析、面积变化分析、focus cell 对比

## 构建逻辑复现

所有派生表的构建 SQL 在以下文件中：

- `rebuild5/scripts/fix4_claude_batch4to7.sh` — 完整的批处理脚本
- `rebuild5/scripts/fix4_claude_pipeline.py` — Python 版（未实际使用，MCP 兼容性问题）

## 补样建议

当前 40 个 focus cells 覆盖了 4 种典型场景：

1. **high_p90**: 极端 p90 膨胀（10 个）
2. **high_obs**: 高观测量（10 个）
3. **moving**: 动态/移动小区（10 个）
4. **multi_cluster**: 多质心嫌疑（10 个）

建议补充：

- **collision_confirmed**: 已确认跨城碰撞的 Cell（如 cell 5694439426，单设备持续远端上报）
- **stable_large**: p90 在 1-3km 但确实是大覆盖（非噪声）的 Cell
- **low_obs_dirty**: 观测量少但 GPS 极度分散的 Cell
