# Fix4 当前阶段 Runbook

范围：当前阶段只验证 `2025-12-01 ~ 2025-12-03`

## 共享输入

共享原始样例基底：

- `rebuild5_fix4.raw_gps_shared_sample`
- `rebuild5_fix4.etl_cleaned_shared_sample`
- `rebuild5_fix4.focus_cells_shared`

当前阶段实际运行使用的本地工作表：

- `rebuild5_fix4_work.raw_gps_shared_sample_local`
- `rebuild5_fix4_work.etl_cleaned_shared_sample_local`
- `rebuild5_fix4_work.focus_cells_shared_local`

## 环境

- 数据库：`ip_loc2_fix4_codex`
- 运行变量：`REBUILD5_PG_DSN=postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_fix4_codex`

## 重置

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable \
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

## 重跑 batch1-3

```bash
REBUILD5_PG_DSN='postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_fix4_codex' \
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-01 \
  --end-day 2025-12-03
```

## 当前阶段验收

### 分流

- `batch2 pathA > 0`
- `batch3 pathA > 0`

### donor 闭环

- `batch2 donor_matched_count > 0`
- `batch3 donor_matched_count > 0`

### Step5

- `batch1-3` 都能完成
- `batch3 Step5` 应维持在秒级到十几秒级，不应再出现分钟级 `_cell_centroid_valid_clusters`

### 状态

- `waiting_cell_count = 0` 不是阻塞项
- `excellent_cell_count` 连续存在
- `published_cell_count` 随批次增加

## 查询建议

### Step2/3/4/5 核心统计

```sql
select batch_id, path_a_record_count, path_b_record_count, path_b_cell_count, path_c_drop_count
from rebuild5_meta.step2_run_stats
order by batch_id;

select batch_id, waiting_cell_count, qualified_cell_count, excellent_cell_count, anchor_eligible_cell_count
from rebuild5_meta.step3_run_stats
order by batch_id;

select batch_id, total_path_a, donor_matched_count, gps_filled, gps_anomaly_count
from rebuild5_meta.step4_run_stats
order by batch_id;

select batch_id, published_cell_count, multi_centroid_cell_count, dynamic_cell_count, anomaly_bs_count
from rebuild5_meta.step5_run_stats
order by batch_id;
```

### batch3 多质心分布

```sql
select coalesce(centroid_pattern, '<null>') as centroid_pattern, count(*)
from rebuild5.trusted_cell_library
where batch_id = 3
group by 1
order by 2 desc, 1;
```

## 当前阶段不做

- 不宣称已完成 `2025-12-01 ~ 2025-12-07`
- 不直接覆盖正式库 `ip_loc2`
- 不把这份 `batch1-3` 验证当作最终 7 天报告
