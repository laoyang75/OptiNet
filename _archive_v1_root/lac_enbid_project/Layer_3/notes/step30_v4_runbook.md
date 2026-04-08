# Step30 v4 运行手册（PG15 / 40C / 256G / SSD）

本手册对应 v4 脚本集：

- `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_v4_prepare.sql`
- `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_v4_metrics_shard_psql.sql`
- `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_v4_merge_psql.sql`
- `lac_enbid_project/Layer_3/sql/run_step30_v4_sharded_32.sh`

## 1. v4 的核心变化（相对旧 Step30）

- 先构建桶全集（Step06），再把 Step02 点“归一 + 落桶（semi-join）”，避免后面做无效计算。
- 将 Step05 唯一映射、点落桶等底座计算物化一次，避免“分片会话重复扫大表”的 N 倍放大。
- 重链路（中心点/离群剔除/p50-p90-max）只在 `points_calc` 上跑：每桶最多取最近 `N=1000` 点（按 `ts_std DESC`）。
- `gps_valid_cell_cnt / gps_valid_point_cnt / gps_valid_level` 仍基于 `points_norm` 的全量统计（不受 1000 截断影响）。

## 2. 一键执行（推荐）

```bash
export DATABASE_URL='postgresql://...'
bash lac_enbid_project/Layer_3/sql/run_step30_v4_sharded_32.sh
```

### 只重跑 METRICS/MERGE（不重跑 PREPARE）

用于修正算法参数或脚本 BUG（底座中间表已存在时）：

```bash
export DATABASE_URL='postgresql://...'
export SHARD_COUNT=32
export SKIP_PREPARE=1
bash lac_enbid_project/Layer_3/sql/run_step30_v4_sharded_32.sh
```

### 只重跑 MERGE（不重跑 PREPARE/METRICS）

用于仅修改 merge 逻辑或输出表名：

```bash
export DATABASE_URL='postgresql://...'
export SHARD_COUNT=32
export SKIP_PREPARE=1
export SKIP_METRICS=1
bash lac_enbid_project/Layer_3/sql/run_step30_v4_sharded_32.sh
```

### 并发分片数建议

- 默认：`SHARD_COUNT=32`（适配 40 核机器，留出余量给系统/其它会话）
- 可调：`SHARD_COUNT=24~36`

示例：

```bash
export DATABASE_URL='postgresql://...'
export SHARD_COUNT=28
bash lac_enbid_project/Layer_3/sql/run_step30_v4_sharded_32.sh
```

## 3. Smoke（可选）

v4 支持在 PREPARE 阶段注入 smoke 参数（注意：脚本会启多个 psql 会话；因此 smoke 必须通过脚本参数注入，而不是手工 `SET`）。

示例（只跑一个日期/一个运营商）：

```bash
psql "$DATABASE_URL" \
  -v is_smoke=true \
  -v smoke_report_date='2025-12-01' \
  -v smoke_operator_id_raw='46015' \
  -f lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_v4_prepare.sql
```

之后再跑分片 metrics 与 merge（同一 smoke 口径下的数据已在 PREPARE 物化）。

## 4. 监控与排障

### 4.1 监控会话

- PREPARE：
  - `application_name = 'codex_step30v4|mode=prepare'`
- METRICS shard：
  - `application_name LIKE 'codex_step30v4|mode=metrics_shard|%'`
- MERGE：
  - `application_name = 'codex_step30v4|mode=merge'`

示例：

```sql
SELECT pid, application_name, state, wait_event_type, wait_event, now()-query_start AS q_age
FROM pg_stat_activity
WHERE application_name LIKE 'codex_step30v4|%'
ORDER BY application_name, pid;
```

### 4.2 中间表

v4 会创建/覆盖以下 UNLOGGED 中间表（用于复盘与避免重复扫表）：

- `public."Y_codex_Layer3_Step30__v4_bucket_universe"`
- `public."Y_codex_Layer3_Step30__v4_map_unique"`
- `public."Y_codex_Layer3_Step30__v4_points_norm"`
- `public."Y_codex_Layer3_Step30__v4_points_calc"`
- `public."Y_codex_Layer3_Step30__v4_bucket_stats"`
- `public."Y_codex_Layer3_Step30__v4_anomaly_cell_cnt"`
- `public."Y_codex_Layer3_Step30__v4_metrics"` 及 `__shard_XX`

如果需要清理，可手工 drop（建议等验收通过后再清理）。

## 5. 输出表

- 主表：`public."Y_codex_Layer3_Step30_Master_BS_Library"`
- 统计：`public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

执行完成后可继续 Step31：

- `lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql`
