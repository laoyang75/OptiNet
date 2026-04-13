# Rebuild5 Runbook V5

时间：2026-04-13  
适用范围：Fix4 最终整合版样例验证通过后的执行基线  
当前状态：共享样例 `batch1-3` 已按当前有效逻辑重验证；`batch4-7` 为历史整合结果，后续如需严格口径一致，应在当前代码上重新补跑

> **阅读前置**：本文件是操作手册，建议先阅读 [README.md](./README.md)（项目交接说明）了解状态机全貌，再进行操作。

## 1. 目标

本 runbook 固化的是已经在样例库真实验证通过的执行路径：

1. 共享样例 `2025-12-01 ~ 2025-12-07`
2. 主链完整流程 `Step2 -> Step3 -> Step4 -> Step5`
3. 当前代码基线：
   - Step2 核心点过滤
   - Step5 核心点过滤
   - Step4 donor gate 修复
   - Step5 地理碰撞替代旧绝对碰撞
   - Step5 PostGIS 分阶段物化
   - 多质心候选扩大到 `raw_p90 / max_spread / core_outlier_ratio / gps_anomaly`

## 2. 环境

### 2.1 前置条件（跑通前必检）

| 项目 | 要求 | 检查方式 |
|---|---|---|
| Python 版本 | Python 3.9+ | `python3 --version` |
| 依赖库 | 已安装 | `pip show psycopg` |
| PostgreSQL | 17，地址可访问 | `pg_isready -h 192.168.200.217 -p 5433` |
| PostGIS 扩展 | 已启用 | `select postgis_version();`（在数据库内执行） |
| 工作样例表 | 已就绪 | 见下方 2.3 节 |

> **注意：** 本 runbook 的执行命令准备跟踪 Step2-5。Step1 ETL 已按共享样例预先跑完（产出 `etl_cleaned_shared_sample_local` 表），不需要重新执行 Step1。

### 2.2 环境变量

样例验证库：

```bash
export REBUILD5_PG_DSN='postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_fix4_codex'
```

### 2.3 工作目录

**以下所有命令均在仓库根目录下执行：**

```bash
cd /path/to/WangYou_Data   # 替换为实际仓库路径
```

### 2.4 共享样例工作表

共享样例本地工作表（应已就绪，如没有请找擈手初始化）：

- `rebuild5_fix4_work.raw_gps_shared_sample_local`
- `rebuild5_fix4_work.etl_cleaned_shared_sample_local`
- `rebuild5_fix4_work.focus_cells_shared_local`

当前已核对行数：

| 表 | 行数 |
|---|---:|
| `raw_gps_shared_sample_local` | 1,232,037 |
| `etl_cleaned_shared_sample_local` | 1,937,395 |
| `focus_cells_shared_local` | 40 |

## 3. 重置

> 在仓库根目录下执行：

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable \
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

重置后应满足：

```sql
select count(*) from rebuild5_meta.step2_run_stats;
select count(*) from rebuild5_meta.step3_run_stats;
select count(*) from rebuild5_meta.step4_run_stats;
select count(*) from rebuild5_meta.step5_run_stats;
select count(*) from rebuild5.trusted_cell_library;
```

全部为 `0`。

## 4. 样例完整执行

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-01 \
  --end-day 2025-12-07
```

## 5. 样例验证结果

以下结果为 2026-04-13 在 `ip_loc2_fix4_codex` 的真实落表结果。

### 5.1 Step2

| batch | pathA | pathB | pathB_cell | pathC |
|---|---:|---:|---:|---:|
| 1 | 0 | 292,872 | 13,490 | 334 |
| 2 | 235,711 | 57,905 | 7,672 | 184 |
| 3 | 247,441 | 23,953 | 4,748 | 210 |
| 4 | 250,959 | 14,592 | 3,563 | 174 |
| 5 | 252,886 | 11,135 | 2,902 | 166 |
| 6 | 263,345 | 9,242 | 2,397 | 117 |
| 7 | 269,129 | 6,959 | 2,006 | 81 |

### 5.2 Step3

| batch | waiting | qualified | excellent | anchor_eligible |
|---|---:|---:|---:|---:|
| 1 | 3,275 | 3,807 | 1,939 | 0 |
| 2 | 2,816 | 6,337 | 2,084 | 1,976 |
| 3 | 2,536 | 7,674 | 2,120 | 2,886 |
| 4 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 |
| 5 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 |
| 6 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 |
| 7 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 | 历史结果待重验 |

> **历史结果待重验说明：** batch4-7 由旧版代码跑出，不代表当前逻辑结果。
> - 如果云端团队需要全量口径一致，应先执行第 3 节全量重置，再对 batch1-7 全量重跑第 4 节命令。
> - 如果只需验证主链闭环，batch1-3 已足够，暂不需要重跑 batch4-7。

### 5.3 Step4

| batch | total_path_a | donor_matched | gps_filled | gps_anomaly |
|---|---:|---:|---:|---:|
| 1 | 0 | 0 | 0 | 0 |
| 2 | 235,711 | 235,711 | 14,362 | 6,450 |
| 3 | 247,441 | 247,441 | 15,161 | 7,108 |
| 4 | 250,959 | 250,959 | 15,987 | 6,120 |
| 5 | 252,886 | 252,886 | 16,252 | 6,201 |
| 6 | 263,345 | 263,345 | 15,413 | 5,232 |
| 7 | 269,129 | 269,129 | 15,483 | 4,948 |

### 5.4 Step5

| batch | published_cell | published_bs | published_lac | collision | multi_centroid | dynamic | anomaly_bs |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5,746 | 3,124 | 18 | 0 | 0 | 0 | 13 |
| 2 | 8,421 | 4,115 | 21 | 0 | 0 | 0 | 20 |
| 3 | 9,794 | 4,563 | 21 | 0 | 113 | 0 | 12 |
| 4 | 10,710 | 4,816 | 21 | 0 | 163 | 18 | 16 |
| 5 | 11,356 | 4,979 | 22 | 0 | 210 | 50 | 16 |
| 6 | 11,897 | 5,093 | 22 | 0 | 236 | 86 | 12 |
| 7 | 12,364 | 5,203 | 22 | 0 | 257 | 92 | 13 |

### 5.5 batch7 多质心分布

| centroid_pattern | count |
|---|---:|
| `<null>` | 12,107 |
| `dual_cluster` | 136 |
| `moving` | 92 |
| `multi_cluster` | 24 |
| `migration` | 5 |

这说明：

1. 多质心不再只停留在 `dual_cluster`
2. `moving / multi_cluster / migration` 已开始在样例上分化
3. 当前没有看到程序性异常或分类塌缩

### 5.6 batch7 focus cells

| bucket | cell_count | avg_cell_p90_m | avg_cell_area_km2 | multi_centroid_cells | patterned_cells | avg_bs_p90_m | avg_bs_area_km2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| high_obs | 10 | 143.4 | 0.1096 | 0 | 0 | 131.1 | 0.0880 |
| high_p90 | 10 | 228.7 | 0.2104 | 0 | 0 | 138.3 | 0.1347 |
| moving | 10 | 728.9 | 2.5039 | 7 | 7 | 612.0 | 2.3739 |
| multi_cluster | 10 | 711.2 | 1.6178 | 5 | 5 | 548.8 | 1.4597 |

判断：

- 极端面积问题已明显收敛
- 动态/多簇 bucket 仍保留合理展布，没有被硬裁剪成过小半径

## 6. 必查 SQL

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

select batch_id, published_cell_count, published_bs_count, published_lac_count,
       collision_cell_count, multi_centroid_cell_count, dynamic_cell_count, anomaly_bs_count
from rebuild5_meta.step5_run_stats
order by batch_id;

select coalesce(centroid_pattern, '<null>') as centroid_pattern, count(*)
from rebuild5.trusted_cell_library
where batch_id = 7
group by 1
order by 2 desc, 1;
```

## 7. 代码测试

### 7.1 测试前置说明

| 项目 | 说明 |
|---|---|
| 是否需要 DB 连接 | 部分测试是纯单元测试，无需 DB；`test_enrichment_queries.py` 等需要 `REBUILD5_PG_DSN` 已设置 |
| 是否需要先重置 | 不需要；单测不依赖生产数据状态 |
| 工作目录 | 仓库根目录 `WangYou_Data/` |

### 7.2 测试命令

本次与 Fix4 整合直接相关的测试命令：

```bash
pytest rebuild5/tests/test_pipeline_version_guards.py rebuild5/tests/test_publish_bs_lac.py
pytest rebuild5/tests/test_profile_logic.py rebuild5/tests/test_publish_cell.py rebuild5/tests/test_enrichment_queries.py rebuild5/tests/test_maintenance_queries.py
```

本次实际结果：

- `33 passed`
- `0 failed`

### 7.3 如果测试失败

| 错误类型 | 可能原因 | 排查方向 |
|---|---|---|
| `ImportError` | 依赖未安装 | 重新 `pip install -r rebuild5/backend/requirements.txt` |
| `psycopg.OperationalError` | DB 无法连接 | 检查 `REBUILD5_PG_DSN` 环境变量和网络连通性 |
| 逻辑断言失败 | 代码边界没对齐 | 对照失败函数所属文件，比对 [处理流程总览.md](./处理流程总览.md) 相山 |

## 8. 放行结论

当前可以放行到下一阶段，但放行方式应是：

1. 进入服务器上的真实 7 天数据运行
2. 优先在服务器上的独立库或受控环境执行
3. 不建议第一步就直接覆盖正式在线库

当前不再阻塞放行的原因：

- 共享样例 `batch1-3` 已在当前有效逻辑下重新跑通
- Step2/3/4/5 主链闭环已验证
- donor 闭环稳定
- 面积收敛稳定
- 多质心分类在既有样例结果中已开始正常分化
- 相关单测已通过
