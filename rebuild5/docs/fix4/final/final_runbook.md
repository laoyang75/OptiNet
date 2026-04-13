# Fix4 最终样例 Runbook

本 runbook 只用于共享样例验证，不用于正式全量。

唯一执行基线：

- 主链整合版
- 样例库：`ip_loc2_fix4_codex`
- 输入表：`rebuild5_fix4_work.etl_cleaned_shared_sample_local`

## 1. 前置准备

### 1.1 环境

```bash
export REBUILD5_PG_DSN='postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_fix4_codex'
```

### 1.2 同步共享样例到本地工作表

```sql
create schema if not exists rebuild5_fix4_work;

drop table if exists rebuild5_fix4_work.etl_cleaned_shared_sample_local;
create table rebuild5_fix4_work.etl_cleaned_shared_sample_local as
select * from rebuild5_fix4.etl_cleaned_shared_sample;

drop table if exists rebuild5_fix4_work.raw_gps_shared_sample_local;
create table rebuild5_fix4_work.raw_gps_shared_sample_local as
select * from rebuild5_fix4.raw_gps_shared_sample;

drop table if exists rebuild5_fix4_work.focus_cells_shared_local;
create table rebuild5_fix4_work.focus_cells_shared_local as
select * from rebuild5_fix4.focus_cells_shared;

analyze rebuild5_fix4_work.etl_cleaned_shared_sample_local;
analyze rebuild5_fix4_work.raw_gps_shared_sample_local;
analyze rebuild5_fix4_work.focus_cells_shared_local;
```

### 1.3 核对样例行数

必须先核对：

| 表 | 期望行数 |
|---|---:|
| `rebuild5_fix4_work.raw_gps_shared_sample_local` | 1,232,037 |
| `rebuild5_fix4_work.etl_cleaned_shared_sample_local` | 1,937,395 |
| `rebuild5_fix4_work.focus_cells_shared_local` | 40 |

### 1.4 重置 Step2-5

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable \
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

## 2. 阶段 A：前三轮前置验证

### 2.1 先跑第 1 轮

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-01 \
  --end-day 2025-12-01
```

验收 SQL：

```sql
select batch_id, path_a_record_count, path_b_record_count, path_b_cell_count, path_c_drop_count
from rebuild5_meta.step2_run_stats
where batch_id = 1;

select batch_id, waiting_cell_count, qualified_cell_count, excellent_cell_count, anchor_eligible_cell_count
from rebuild5_meta.step3_run_stats
where batch_id = 1;

select batch_id, total_path_a, donor_matched_count, gps_filled, gps_anomaly_count
from rebuild5_meta.step4_run_stats
where batch_id = 1;

select batch_id, published_cell_count, published_bs_count, published_lac_count,
       collision_cell_count, multi_centroid_cell_count, dynamic_cell_count, anomaly_bs_count
from rebuild5_meta.step5_run_stats
where batch_id = 1;
```

期望值：

| 指标 | 期望 |
|---|---:|
| `path_a_record_count` | 0 |
| `path_b_record_count` | 292,872 |
| `path_b_cell_count` | 13,490 |
| `path_c_drop_count` | 334 |
| `waiting_cell_count` | 0 |
| `qualified_cell_count` | 3,807 |
| `excellent_cell_count` | 1,939 |
| `anchor_eligible_cell_count` | 0 |
| `donor_matched_count` | 0 |
| `gps_filled` | 0 |
| `published_cell_count` | 5,746 |
| `published_bs_count` | 3,124 |
| `published_lac_count` | 18 |
| `multi_centroid_cell_count` | 0 |

### 2.2 再跑第 2 轮

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-02 \
  --end-day 2025-12-02 \
  --start-batch-id 2
```

期望值：

| 指标 | 期望 |
|---|---:|
| `path_a_record_count` | 235,711 |
| `path_b_record_count` | 57,905 |
| `path_b_cell_count` | 7,672 |
| `path_c_drop_count` | 184 |
| `waiting_cell_count` | 0 |
| `qualified_cell_count` | 6,337 |
| `excellent_cell_count` | 2,084 |
| `anchor_eligible_cell_count` | 1,976 |
| `total_path_a` | 235,711 |
| `donor_matched_count` | 235,711 |
| `gps_filled` | 14,362 |
| `gps_anomaly_count` | 6,450 |
| `published_cell_count` | 8,421 |
| `published_bs_count` | 4,115 |
| `published_lac_count` | 21 |
| `multi_centroid_cell_count` | 0 |

第 2 轮通过条件：

1. `pathA > 0`
2. `donor_matched_count = total_path_a`
3. `gps_filled > 0`

### 2.3 再做第 3 轮前置测试

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-03 \
  --end-day 2025-12-03 \
  --start-batch-id 3
```

期望值：

| 指标 | 期望 |
|---|---:|
| `path_a_record_count` | 247,441 |
| `path_b_record_count` | 23,953 |
| `path_b_cell_count` | 4,748 |
| `path_c_drop_count` | 210 |
| `waiting_cell_count` | 0 |
| `qualified_cell_count` | 7,674 |
| `excellent_cell_count` | 2,120 |
| `anchor_eligible_cell_count` | 2,886 |
| `total_path_a` | 247,441 |
| `donor_matched_count` | 247,441 |
| `gps_filled` | 15,161 |
| `gps_anomaly_count` | 7,108 |
| `published_cell_count` | 9,794 |
| `published_bs_count` | 4,563 |
| `published_lac_count` | 21 |
| `multi_centroid_cell_count` | 113 |
| `dynamic_cell_count` | 0 |
| `anomaly_bs_count` | 12 |

额外检查：

```sql
select coalesce(centroid_pattern, '<null>') as centroid_pattern, count(*)
from rebuild5.trusted_cell_library
where batch_id = 3
group by 1
order by 2 desc, 1;
```

期望：

| centroid_pattern | count |
|---|---:|
| `<null>` | 9,681 |
| `dual_cluster` | 106 |
| `multi_cluster` | 7 |

阶段 A 通过条件：

1. 第 2 轮已经出现有效 `waiting/分流/补数`
2. 第 3 轮程序完整跑通
3. 第 3 轮核心指标与上述样例基线一致

## 3. 阶段 B：7 轮样例验证

只有阶段 A 通过后，才允许扩展到 `batch4-7`。

执行命令：

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-04 \
  --end-day 2025-12-07 \
  --start-batch-id 4
```

### 3.1 必查项

```sql
select batch_id, path_a_record_count, path_b_record_count, path_b_cell_count, path_c_drop_count
from rebuild5_meta.step2_run_stats
where batch_id between 4 and 7
order by batch_id;

select batch_id, waiting_cell_count, qualified_cell_count, excellent_cell_count, anchor_eligible_cell_count
from rebuild5_meta.step3_run_stats
where batch_id between 4 and 7
order by batch_id;

select batch_id, total_path_a, donor_matched_count, gps_filled, gps_anomaly_count
from rebuild5_meta.step4_run_stats
where batch_id between 4 and 7
order by batch_id;

select batch_id, published_cell_count, published_bs_count, published_lac_count,
       collision_cell_count, multi_centroid_cell_count, dynamic_cell_count, anomaly_bs_count
from rebuild5_meta.step5_run_stats
where batch_id between 4 and 7
order by batch_id;
```

### 3.2 Focus cell 对比

```sql
select
    f.source_bucket,
    count(*) as cell_count,
    round(avg(t.p90_radius_m)::numeric, 1) as avg_cell_p90_m,
    round(avg(pi()*power(t.p90_radius_m/1000.0, 2))::numeric, 4) as avg_cell_area_km2,
    round(avg(b.gps_p90_dist_m)::numeric, 1) as avg_bs_p90_m
from rebuild5_fix4_work.focus_cells_shared_local f
join rebuild5.trusted_cell_library t
  on t.operator_code = f.operator_code
 and t.lac = f.lac
 and t.cell_id = f.cell_id
 and t.tech_norm = f.tech_norm
left join rebuild5.trusted_bs_library b
  on b.batch_id = t.batch_id
 and b.operator_code = t.operator_code
 and b.lac = t.lac
 and b.bs_id = t.bs_id
where t.batch_id = 7
group by f.source_bucket
order by f.source_bucket;
```

batch3 参考基线：

| bucket | avg cell p90 | avg cell area | avg bs p90 |
|---|---:|---:|---:|
| high_obs | 129.5m | 0.0780km² | 386.9m |
| high_p90 | 128.6m | 0.1164km² | 897.3m |
| moving | 818.4m | 2.8759km² | 517.1m |
| multi_cluster | 799.2m | 2.3908km² | 420.7m |

### 3.3 阶段 B 通过条件

1. `batch4-7` 四轮都完整产生 Step2/3/4/5 统计
2. 只要 `total_path_a > 0`，就必须满足 `donor_matched_count = total_path_a`
3. Focus cell 不允许回到 km~百 km 级的大半径失真
4. `LAC` 仍只做区域聚合，不引入 LAC 多簇逻辑
5. `dual_cluster` 不能持续一边倒占据几乎全部已分类对象

### 3.4 阻断条件

出现以下任一情况，停止进入主流程：

1. 任一批 `donor_matched_count < total_path_a`
2. 任一批 Step5 未完整落表
3. `high_p90 / high_obs` focus bucket 明显回弹到异常大半径
4. `moving / multi_cluster` bucket 被过度压平成明显不合理的小半径
5. `dual_cluster` 仍长期压倒 `moving / migration / multi_cluster`

## 4. 阶段 C：形成最终主流程变更清单

只有阶段 B 通过后，才允许进入下面动作：

1. 冻结当前主链代码
2. 补齐集成测试
3. 更新正式运行 runbook
4. 再决定正式全量如何重跑

当前阶段明确不做：

- 不直接跑正式全量
- 不把 `claude` 侧路脚本当正式 runbook
- 不跳过 `batch1 -> batch2 -> batch3 前置测试`

