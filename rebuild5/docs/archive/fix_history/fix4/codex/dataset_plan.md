# Fix4 当前阶段 Dataset Plan

## 共享原始表

当前阶段仍严格基于共享样例表：

- `rebuild5_fix4.raw_gps_shared_sample`
- `rebuild5_fix4.etl_cleaned_shared_sample`
- `rebuild5_fix4.focus_cells_shared`

没有替换原始样例成员，也没有改时间范围。

## 当前阶段派生工作集

### 1. `rebuild5_fix4_work.etl_cleaned_shared_sample_local`

用途：

- 当前 `batch1-3` 整合验证的直接输入
- 避免每次测试都跨库走 FDW

构造方式：

```sql
create schema if not exists rebuild5_fix4_work;
drop table if exists rebuild5_fix4_work.etl_cleaned_shared_sample_local;
create table rebuild5_fix4_work.etl_cleaned_shared_sample_local as
select * from rebuild5_fix4.etl_cleaned_shared_sample;
create index if not exists idx_fix4_work_etl_day
  on rebuild5_fix4_work.etl_cleaned_shared_sample_local (event_time_std);
create index if not exists idx_fix4_work_etl_record
  on rebuild5_fix4_work.etl_cleaned_shared_sample_local (record_id);
analyze rebuild5_fix4_work.etl_cleaned_shared_sample_local;
```

### 2. `rebuild5_fix4_work.focus_cells_shared_local`

用途：

- 当前阶段重点样例观察
- 多质心 / 大半径 focus bucket 分析

构造方式：

```sql
drop table if exists rebuild5_fix4_work.focus_cells_shared_local;
create table rebuild5_fix4_work.focus_cells_shared_local as
select * from rebuild5_fix4.focus_cells_shared;
analyze rebuild5_fix4_work.focus_cells_shared_local;
```

### 3. `rebuild5_fix4_work.raw_gps_shared_sample_local`

用途：

- 原始 GPS 层离群点分析
- 与 ETL 层验证分开保留

构造方式：

```sql
drop table if exists rebuild5_fix4_work.raw_gps_shared_sample_local;
create table rebuild5_fix4_work.raw_gps_shared_sample_local as
select * from rebuild5_fix4.raw_gps_shared_sample;
create index if not exists idx_fix4_work_raw_ts
  on rebuild5_fix4_work.raw_gps_shared_sample_local (ts);
create index if not exists idx_fix4_work_raw_record
  on rebuild5_fix4_work.raw_gps_shared_sample_local ("记录数唯一标识");
analyze rebuild5_fix4_work.raw_gps_shared_sample_local;
```

## 当前阶段核心派生中间表

### Step2 核心点过滤

用途：

- 抗离群点主中心
- 在进入 Step3 前先稳定 `center/p50/p90`

主要中间表：

- `_profile_seed_grid`
- `_profile_primary_seed`
- `_profile_seed_distance`
- `_profile_core_cutoff`
- `_profile_core_points`
- `_profile_core_gps`
- `_profile_counts`

### Step5 核心点过滤

用途：

- 在滑动窗口上重算维护态质心和半径

主要中间表：

- `cell_core_seed_grid`
- `cell_core_primary_seed`
- `cell_core_seed_distance`
- `cell_core_cutoff`
- `cell_core_points`
- `cell_core_gps_stats`

### Step5 PostGIS 多质心

用途：

- 候选 Cell 的稳定簇分析
- 多质心分类

主要中间表：

- `_cell_centroid_candidates`
- `_cell_centroid_points`
- `_cell_centroid_grid_points`
- `_cell_centroid_clustered_grid`
- `_cell_centroid_labelled_points`
- `_cell_centroid_cell_totals`
- `_cell_centroid_cluster_base`
- `_cell_centroid_cluster_centers`
- `_cell_centroid_cluster_radius`
- `_cell_centroid_cluster_stats`
- `_cell_centroid_filtered_clusters`
- `_cell_centroid_ranked_clusters`
- `_cell_centroid_valid_clusters`
- `_cell_centroid_daily_presence`
- `_cell_centroid_classification`

## 当前阶段目标对应

- 工程闭环验证：`etl_cleaned_shared_sample_local`
- donor 修复验证：`step2/3/4/5_run_stats`
- 多质心研究：`focus_cells_shared_local` + `cell_centroid_detail`
- PostGIS 性能拆解：`_cell_centroid_*` 阶段表

## 当前阶段补样意见

当前阶段还没有改共享样例集。

如果后续继续研究，建议补样方向是：

1. `dual_cluster` 但次簇占比刚好在 `0.10 ~ 0.20` 的边界样例
2. `high_p90` 但最终仍被压成单簇的对象
3. `moving / migration` 时间重叠度接近阈值的对象

这些补样建议目前只作为后续研究方向，不应直接混入本阶段结果。
