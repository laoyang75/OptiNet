# 28 全链路重跑（Step 1-5 pipelined）

> **数据库**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **仓库**：`/Users/yangcongan/cursor/WangYou_Data`
> **脚本**：`rebuild5/scripts/run_step1_step25_pipelined_temp.py`

---

## 0. 任务

完成 Step 1-5 全链路重跑 `dataset_key = beijing_7d`（日期范围 **2025-12-01 ~ 2025-12-07**），最终产出：

- `rebuild5.trusted_cell_library`、`rebuild5.trusted_bs_library`、`rebuild5.trusted_lac_library` 各 7 批（`batch_id = 1..7`）
- `rebuild5_meta.step1_run_stats / step5_run_stats` 有完整记录

### 执行模式（pipelined）

- **Step 1（producer）**：day 1 → day 7 **顺序跑**
- **Step 2-5（consumer）**：流水线跟进；每跑 day N 前检查 day N 的 Step 1 已完成，未完成则等
- **脚本自带该流水线语义**，`--skip-prepare` 表示不调 `prepare_current_dataset()`，数据源直接取挂载到 `rebuild5.raw_gps_full_backup` 的内容

### 执行顺序

1. **§1 冒烟** — 代码、配置、索引、源头数据健康检查
2. **§2 启动检测 + 环境重置** — 确认 DB 干净、无外部写入、跑 reset 脚本
3. **§3 测试集 7 天预跑 + 性能评估** — 用约 150 万行样本完整跑 7 批，验证流程通 + 测耗时 + 最多 2 轮优化
4. **§4 环境恢复 + 正式全量重跑** — 清测试挂载，恢复原始数据源，跑正式 7 天
5. **§5 正式验收** — 批次齐、垃圾 cell 为 0、drift/classification 分布合理
6. **§6 汇报**

### 禁区（贯穿全程）

- **不改代码业务逻辑**；§3.6 性能优化阶段仅允许：建索引 / SQL 调 `MATERIALIZED` / 补 `ANALYZE`
- **不能损坏 `rebuild5.raw_gps_full_backup` 的内容**；允许 RENAME 暂存，但最终必须恢复（§4.1 硬校验）
- **单条 SQL 单任务**，禁 ≥ 3 层 CTE / 复杂自 JOIN
- **不追日志文件**；进度监测只用本文档给的短 SQL
- **卡住 > 30 分钟先停下汇报**，不自行 `pg_terminate_backend` / `kill pid`

---

## 1. 冒烟（≤ 5 分钟，任一失败停下）

### 1.1 Python 语法

```bash
cd /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend
python3 -c "
import ast
for f in ['app/etl/clean.py','app/etl/parse.py','app/etl/pipeline.py',
         'app/profile/pipeline.py','app/evaluation/pipeline.py',
         'app/enrichment/pipeline.py','app/enrichment/schema.py',
         'app/maintenance/pipeline.py']:
    ast.parse(open(f).read())
print('OK')
"
```

### 1.2 ODS 清洗规则到位

```bash
# 主清洗规则（ODS-001 ~ ODS-018 + 005a / 006a / 006b）
python3 -c "
from app.etl.clean import ODS_RULES
ids = {r['id'] for r in ODS_RULES}
assert {'ODS-005a','ODS-006a','ODS-006b'}.issubset(ids)
print('ODS clean rules ok:', sorted(ids))
"

# ODS-019 (cell_infos 陈旧缓存过滤) 配置 + SQL 注释
python3 -c "
from app.etl.parse import _load_cell_infos_cfg
cfg = _load_cell_infos_cfg()
assert cfg.get('max_age_sec', 0) >= 1, f'max_age_sec 异常: {cfg}'
print('ODS-019 config ok:', cfg)
"
grep -n 'ODS-019' app/etl/parse.py               # WHERE 子句应带该注释
grep -n '^etl_cell_infos:' ../config/antitoxin_params.yaml
```

### 1.3 下游 SQL 优化到位（fix4 三处）

```bash
grep -n 'idx_enriched_batch_record_cell' app/enrichment/schema.py
grep -n 'idx_csh_join_batch' app/enrichment/pipeline.py
grep -n 'new_snapshot_cells AS MATERIALIZED' app/enrichment/pipeline.py
# 三行都应 grep 到
```

### 1.4 源头数据规模（MCP PG17）

```sql
SELECT COUNT(*) AS rows FROM rebuild5.raw_gps_full_backup;
-- 应 >= 25,000,000，低于此值说明源头数据异常，停下汇报
```

```sql
-- 北京时间语义：12-01 ~ 12-07 共 7 天
SELECT ts::date AS day, COUNT(*) AS rows
FROM rebuild5.raw_gps_full_backup
WHERE ts >= '2025-12-01' AND ts < '2025-12-08'
GROUP BY ts::date ORDER BY day;
-- 应返回 7 行；每天 340-390 万；任一天 < 200 万停下汇报
```

---

## 2. 启动检测 + 环境重置

### 2.0 启动检测（任一不过停下）

```sql
-- 无外部活跃写入（防止重跑过程中被第三方会话干扰）
SELECT pid, client_addr, state,
       LEFT(regexp_replace(query,'\s+',' ','g'), 150) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active';
-- 若有 UPDATE / INSERT / TRUNCATE / DROP / ALTER 出现，停下汇报

-- 样例挂载保护位必须为空；非空说明上次测试集未恢复干净
SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold');
-- 应返回 NULL；非 NULL 停下汇报
```

### 2.1 环境重置

```bash
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -f /Users/yangcongan/cursor/WangYou_Data/rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

确认清理生效：

```sql
SELECT 'trusted_cell' AS t, COUNT(*) FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'trusted_bs', COUNT(*) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'trusted_lac', COUNT(*) FROM rebuild5.trusted_lac_library
UNION ALL SELECT 'step1_stats', COUNT(*) FROM rebuild5_meta.step1_run_stats
UNION ALL SELECT 'step5_stats', COUNT(*) FROM rebuild5_meta.step5_run_stats
UNION ALL SELECT 'cell_sliding_window', COUNT(*) FROM rebuild5.cell_sliding_window
UNION ALL SELECT 'cell_centroid_detail', COUNT(*) FROM rebuild5.cell_centroid_detail
UNION ALL SELECT 'raw_gps_full_backup', COUNT(*) FROM rebuild5.raw_gps_full_backup;
-- 前 7 行应全为 0；raw_gps_full_backup 必须 >= 25,000,000
```

---

## 3. 测试集 7 天预跑 + 性能评估

**目的**：用小数据集（~150 万行 × 7 天每天都有）完整跑通 pipelined 流水线，**只验证流程畅通 + 各阶段耗时合理**。**不要求与全量数据对数，不验证业务正确性**。

### 3.1 准备测试集（表：`rebuild5_stage.raw_gps_sample_7d`）

先检查现有表是否可复用：

```sql
-- 若已存在且合规则复用
SELECT COUNT(*) AS rows,
       COUNT(DISTINCT ts::date) AS days,
       MIN(ts::date) AS min_day,
       MAX(ts::date) AS max_day
FROM rebuild5_stage.raw_gps_sample_7d;
```

**复用条件**：`rows ∈ [1,200,000, 1,800,000]` **且** `days >= 7` **且** `min_day <= '2025-12-01'` **且** `max_day >= '2025-12-07'`。满足 → 跳到 §3.2。

否则重建：

```sql
CREATE SCHEMA IF NOT EXISTS rebuild5_stage;
DROP TABLE IF EXISTS rebuild5_stage.raw_gps_sample_7d;

-- 每天按随机抽样取 ~21.5 万行，7 天合计 ~150 万
CREATE TABLE rebuild5_stage.raw_gps_sample_7d AS
SELECT r.* FROM (
  SELECT r.*,
         ROW_NUMBER() OVER (PARTITION BY r.ts::date ORDER BY random()) AS rn
  FROM rebuild5.raw_gps_full_backup r
  WHERE r.ts >= '2025-12-01' AND r.ts < '2025-12-08'
) r
WHERE r.rn <= 215000;

-- 验收：应约 150 万行 + 7 行（每天）
SELECT COUNT(*) AS rows FROM rebuild5_stage.raw_gps_sample_7d;
SELECT ts::date AS day, COUNT(*) AS rows
FROM rebuild5_stage.raw_gps_sample_7d
GROUP BY ts::date ORDER BY day;
-- rows ∈ [1,200,000, 1,800,000]；7 行，每天 15-22 万
```

### 3.2 挂载测试集（保护原始表）

```sql
-- 把原始 full_backup 暂存到保护位
ALTER TABLE rebuild5.raw_gps_full_backup RENAME TO raw_gps_full_backup_prod_hold;

-- 把测试集复制到脚本默认读的位置
CREATE TABLE rebuild5.raw_gps_full_backup AS
SELECT * FROM rebuild5_stage.raw_gps_sample_7d;

CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_uid
  ON rebuild5.raw_gps_full_backup ("记录数唯一标识");
CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_ts
  ON rebuild5.raw_gps_full_backup (ts);

ANALYZE rebuild5.raw_gps_full_backup;

-- 验证挂载
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup;  -- 约 150 万
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup_prod_hold;  -- 原始，>= 2500 万
```

### 3.3 启动预跑

```bash
cd /Users/yangcongan/cursor/WangYou_Data
LOG=rebuild5/runtime/logs/sample_rerun_$(date +%Y%m%d_%H%M%S).log
nohup python3 rebuild5/scripts/run_step1_step25_pipelined_temp.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  --skip-prepare \
  > $LOG 2>&1 &
echo $! > rebuild5/runtime/sample_rerun.pid
echo "PID=$(cat rebuild5/runtime/sample_rerun.pid)  LOG=$LOG"
```

### 3.4 监控（短 SQL 轮询）

**Step 1 每天进度**：

```sql
SELECT run_id, status, started_at, finished_at,
       raw_record_count, cleaned_record_count, clean_pass_rate,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at DESC LIMIT 10;
```

**Step 2-5 批次进度**：

```sql
SELECT 'cell' AS t, batch_id, COUNT(*) AS rows FROM rebuild5.trusted_cell_library GROUP BY batch_id
UNION ALL SELECT 'bs',  batch_id, COUNT(*) FROM rebuild5.trusted_bs_library  GROUP BY batch_id
UNION ALL SELECT 'lac', batch_id, COUNT(*) FROM rebuild5.trusted_lac_library GROUP BY batch_id
ORDER BY t, batch_id;
```

**卡住排查**（单 SQL > 30 分钟未完成停下汇报）：

```sql
SELECT pid, client_addr, state,
       EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       LEFT(regexp_replace(query,'\s+',' ','g'), 200) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active'
ORDER BY query_start LIMIT 3;
```

**进程存活**：

```bash
ps -p $(cat rebuild5/runtime/sample_rerun.pid) && echo alive || echo exited
```

### 3.5 预跑验收（只验"流程通"）

```sql
-- 三层都应有 7 批
SELECT 'cell' AS t, COUNT(DISTINCT batch_id) AS b FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs',  COUNT(DISTINCT batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_lac_library;
-- 三行都应 = 7

-- 垃圾 cell 全为 0（ETL 过滤规则生效）
SELECT batch_id,
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm='4G') AS g4g,
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm='5G') AS g5g,
  COUNT(*) FILTER (WHERE lac < 100) AS glac
FROM rebuild5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
-- g4g / g5g / glac 每批都应 = 0

-- ODS-019（cell_infos 陈旧缓存）drop 量 > 0
SELECT run_id,
       (parse_details->'ods_019'->>'dropped_stale_count')::bigint AS dropped,
       (parse_details->'ods_019'->>'drop_rate')::float AS drop_rate
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;
-- 每行 dropped > 0；drop_rate 小数据集波动允许（不硬要求区间）
```

任一项未通过停下汇报。

### 3.6 性能评估（样本跑通后必做）

**目的**：发现瓶颈、决定是否优化。**仅允许**加索引 / 把 CTE 改 `MATERIALIZED` / 补 `ANALYZE`。**不改业务逻辑**。

记录每阶段耗时基线：

```sql
SELECT run_id, batch_id,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step5_run_stats ORDER BY batch_id;

SELECT run_id,
       raw_record_count, cleaned_record_count,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step1_run_stats ORDER BY started_at;
```

**判定标准**：
- 若各批 Step 5 耗时 ≤ 120 秒 **且** 各日 Step 1 耗时 ≤ 180 秒 → 流程健康，直接进 §3.7
- 若有阶段超出 2×基线（如某批 Step 5 > 240 秒）→ 取最耗时那条 SQL 的 EXPLAIN，定位瓶颈；加一个索引 / 改一处 MATERIALIZED；**再跑一次 §3.3** 复验
- 最多 2 轮优化复验；仍超标 → 停下汇报，不自行继续

### 3.7 清理测试挂载 + 恢复原始数据源

```bash
# 再跑 reset 清除测试产出的 Step 1-5 状态
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -f /Users/yangcongan/cursor/WangYou_Data/rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

```sql
-- 丢弃测试挂载，把保护位的原始表改回默认名
DROP TABLE IF EXISTS rebuild5.raw_gps_full_backup;
ALTER TABLE rebuild5.raw_gps_full_backup_prod_hold RENAME TO raw_gps_full_backup;

-- 重建原始表索引（保护位 RENAME 过来后索引名可能带 prod_hold 前缀，以旧名重建）
CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_uid
  ON rebuild5.raw_gps_full_backup ("记录数唯一标识");
CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_ts
  ON rebuild5.raw_gps_full_backup (ts);
ANALYZE rebuild5.raw_gps_full_backup;

-- 强制硬校验
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup;
-- 应 >= 25,000,000；低于此值立即停下汇报（原始数据疑似受损）

SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold');
-- 应 NULL（保护位已清）
```

**§3.7 任一校验未通过，禁止进入 §4**。

---

## 4. 正式全量 7 天重跑

### 4.1 正式启动前再次检测

```sql
-- 原始数据完好
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup;            -- >= 2500 万
SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold'); -- NULL

-- 目标表全空（§3.7 reset 生效）
SELECT 'cell' AS t, COUNT(*) FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs',  COUNT(*) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(*) FROM rebuild5.trusted_lac_library
UNION ALL SELECT 'step1_stats', COUNT(*) FROM rebuild5_meta.step1_run_stats
UNION ALL SELECT 'step5_stats', COUNT(*) FROM rebuild5_meta.step5_run_stats;
-- 前 5 项都应 = 0

-- 无外部活跃写入
SELECT pid, state FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active';
-- 只应看到自己的查询
```

任一项未过停下汇报。

### 4.2 启动正式流水线

```bash
cd /Users/yangcongan/cursor/WangYou_Data
LOG=rebuild5/runtime/logs/full_rerun_$(date +%Y%m%d_%H%M%S).log
nohup python3 rebuild5/scripts/run_step1_step25_pipelined_temp.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  --skip-prepare \
  > $LOG 2>&1 &
echo $! > rebuild5/runtime/full_rerun.pid
echo "PID=$(cat rebuild5/runtime/full_rerun.pid)  LOG=$LOG"
```

**预计耗时**：60-150 分钟（Step 1 先跑完 7 天后 Step 2-5 跟进；具体取决于 §3.6 的基线）。

### 4.3 监控

同 §3.4 的 SQL（换成看 `full_rerun.pid`）。

---

## 5. 正式验收（全部 7 批完成后）

### 5.1 三层都有 7 批

```sql
SELECT 'cell' AS t, COUNT(DISTINCT batch_id) AS b FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs',  COUNT(DISTINCT batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_lac_library;
-- 三行都应 = 7
```

### 5.2 垃圾 cell = 0（硬要求）

```sql
SELECT batch_id,
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm='4G') AS g4g,
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm='5G') AS g5g,
  COUNT(*) FILTER (WHERE lac < 100) AS glac
FROM rebuild5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
-- g4g / g5g / glac 每批都应 = 0；任一项 > 0 停下汇报
```

### 5.3 batch 7 drift 分布

```sql
SELECT drift_pattern, COUNT(*) AS cnt,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(), 2) AS pct
FROM rebuild5.trusted_cell_library WHERE batch_id = 7
GROUP BY drift_pattern ORDER BY cnt DESC;
```

期望：`stable` 93-96% / `insufficient` 2-4% / 其他合计 < 1%。偏离 > 3 个百分点记录到汇报。

### 5.4 BS classification（batch 7）

```sql
SELECT classification, COUNT(*) AS cnt
FROM rebuild5.trusted_bs_library WHERE batch_id = 7
GROUP BY classification ORDER BY cnt DESC;
```

期望：`normal` ≥ 95%、`insufficient` 3-5%、其他合计数量级百位以内。

### 5.5 ODS-019 过滤量分布

```sql
SELECT run_id,
       (parse_details->'ods_019'->>'total_connected_objects')::bigint AS total,
       (parse_details->'ods_019'->>'dropped_stale_count')::bigint AS dropped,
       (parse_details->'ods_019'->>'drop_rate')::float AS drop_rate,
       (parse_details->'ods_019'->>'max_age_sec')::int AS max_age_sec
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;
```

期望：每天 `drop_rate` 在 **10-25%** 之间。若某日 = 0 → 新规则未生效；某日 > 50% → 可能阈值问题。任一异常停下汇报。

**UI 观察**（非必需）：访问前端 `/etl/clean` 页，表格最后一行应是 `ODS-019 / CellInfos 陈旧缓存过滤`，命中/删除数非零。

### 5.6 UI 验收（非必需但推荐）

- **维护页**（Cell / BS / LAC 三 Tab）：SummaryCard 有数、表格无空页
- **评估页**：`/api/evaluation/overview` 返回 `snapshot_version='v7'`，`published_cell_count` 与 §5.1 的 cell batch 7 一致

---

## 6. 汇报

写到 `rebuild5/docs/rerun_delivery_<YYYY-MM-DD>_full.md`：

1. **总耗时**：正式全量起止时间；每天 Step 1 起止；每批 Step 2-5 起止
2. **性能基线**：§3.6 记录的样例耗时、是否有优化轮次、做了什么优化
3. **行数**：每批 trusted_cell / trusted_bs / trusted_lac 行数
4. **drift 分布**：batch 7 的 drift_pattern 分布
5. **BS classification**：batch 7 分布
6. **ODS-019 drop 量**：每日 `drop_rate`（§5.5）
7. **异常告警**：任何停下汇报的节点 / 遇到的问题 / 卡死 SQL

---

## 7. 失败处理

### 7.1 进程异常退出但未通过 §5

```bash
tail -200 $(ls -t rebuild5/runtime/logs/*.log | head -1)
```

根据日志定位卡在哪一天 / 哪一步，**报告给人工裁决**；不自行二次启动。

### 7.2 DB 查询卡住 > 30 分钟

用 §3.4 的卡住排查 SQL 抓取当前 query，报告；不自行 `pg_cancel_backend` / `pg_terminate_backend`。

### 7.3 原始数据疑似受损（`raw_gps_full_backup < 2500 万` 或被意外修改）

**立刻停下**，报告当前状态：

```sql
SELECT COUNT(*) AS rows FROM rebuild5.raw_gps_full_backup;
SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold');
```

等人工评估后再决定下一步（从 `prod_hold` 还原 / 从上游重建 / 其他），**不自行恢复**。

### 7.4 §3.6 优化 2 轮后仍超标

停下汇报。提供：
- 最耗时的单条 SQL（从 §3.4 卡住排查 SQL 捞到的）
- 该 SQL 的 `EXPLAIN ANALYZE` 输出
- 两轮优化做了什么

由人工决定是否放宽阈值或进一步改动。

---

## 附：关键位置索引

| 项 | 路径 |
|---|---|
| Pipelined 脚本 | `rebuild5/scripts/run_step1_step25_pipelined_temp.py` |
| Reset 脚本 | `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql` |
| ETL 过滤规则 | `rebuild5/docs/01b_数据源接入_处理规则.md` |
| ETL clean 主规则列表 | `rebuild5/backend/app/etl/clean.py::ODS_RULES` |
| ETL parse `ODS-019` | `rebuild5/backend/app/etl/parse.py::_parse_cell_infos` |
| 配置 | `rebuild5/config/antitoxin_params.yaml` |
| fix4 优化 | `rebuild5/docs/fix4/snapshot_seed_sql_optimization.md` |
