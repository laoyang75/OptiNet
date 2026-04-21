# 28 全链路重跑（先样例 7 天预跑，再全量 7 天正式跑；pipelined：Step1 独立顺序 ∥ Step2-5 消费者流水线）

> **日期**：2026-04-20
> **前置**：代码已应用 ETL 过滤（ODS-005a/006a/006b）、BS/LAC v1、`snapshot_seed` 索引与 `MATERIALIZED` 优化（来自 `docs/fix4/snapshot_seed_sql_optimization.md`）
> **DB**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **目标**：先用 `rebuild5_fix4.raw_gps_shared_sample` 完整预跑 2025-12-01 ~ 2025-12-07 的 batch 1-7，验证 Step1 producer + Step2-5 consumer 的 7 天流水线；样例通过后，先做逐阶段耗时分析与索引/SQL 优化，再用全量数据正式重跑 batch 1-7，产出 prompt 27 研究用的干净 batch 7

---

## 0. 执行模式

- **阶段 A：样例预跑**：`rebuild5_fix4.raw_gps_shared_sample` 已覆盖 **7 天**，必须按天切成 **7 个 batch**，跑完整个 pipelined 脚本；**禁止**用“样例表手工跑 1 次 Step1 + 1 次 Step2-5”代替
- **阶段 B：性能审查与优化**：样例 7 天跑通后，只做一轮 baseline 测速 + 最多 2 轮优化复验；优化范围只盯 `Step 1` 和 `Step 2-5` 两大块
- **阶段 C：正式全量**：只有样例 7 天预跑全部通过、性能审查完成、环境 reset 完成、原始全量 `raw_gps_full_backup` 已恢复后，才开始正式全量 7 天重跑
- **Step 1**（producer）：day 1 → 7 **顺序**跑，与 Step 2-5 无依赖
- **Step 2-5**（consumer）：每跑 day N 前检查 Step 1 day N 已完成；未完成就等
- **现成脚本**：`rebuild5/scripts/run_step1_step25_pipelined_temp.py` 就是这个模式，直接用
- **样例/正式都用 `--skip-prepare`**：此 prompt 里不再调用 `prepare_current_dataset()`；脚本直接复用当前挂载到 `rebuild5.raw_gps_full_backup` 的数据源
- **原始全量保护原则**：样例阶段不能覆盖或丢失原始全量 `rebuild5.raw_gps_full_backup`；先把它改名暂存，再把样例挂到同名表上，样例结束后恢复

### 禁区

- 不改代码；发现 bug 先停下汇报
- SQL 单条单用途；禁 ≥3 层 CTE / 复杂自 JOIN
- 进度监测用 §4 的短 SQL，不要跑自造的长查询
- 不追日志文件；用数据库查状态
- 不允许把 §2.5 简化成“单批手工冒烟”

---

## 1. 冒烟（≤ 5 分钟，任何一条失败停下）

### 1.1 Python 语法
```bash
cd /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend
python3 -c "
import ast
for f in ['app/etl/clean.py','app/etl/pipeline.py','app/profile/pipeline.py',
         'app/evaluation/pipeline.py','app/enrichment/pipeline.py',
         'app/enrichment/schema.py','app/maintenance/pipeline.py']:
    ast.parse(open(f).read())
print('OK')
"
```

### 1.2 ETL 过滤 + fix4 优化已在代码里

```bash
# ODS 三条新规则
python3 -c "
from app.etl.clean import ODS_RULES
ids = {r['id'] for r in ODS_RULES}
assert {'ODS-005a','ODS-006a','ODS-006b'}.issubset(ids)
print('ODS ok')
"

# fix4 三处优化（应能全部 grep 到）
grep -n 'idx_enriched_batch_record_cell' app/enrichment/schema.py
grep -n 'idx_csh_join_batch' app/enrichment/pipeline.py
grep -n 'new_snapshot_cells AS MATERIALIZED' app/enrichment/pipeline.py
```

### 1.3 源头数据规模（MCP PG17 查）

```sql
-- 北京时间语义：12-01 ~ 12-07 共 7 天
SELECT ts::date AS day, COUNT(*) AS rows
FROM rebuild5.raw_gps_full_backup
WHERE ts >= '2025-12-01' AND ts < '2025-12-08'
GROUP BY ts::date ORDER BY day;
```

应返回 **7 行**；每天 340-390 万；7 天合计 ~2500 万。行数 ≠ 7 或任一天 < 200 万停下汇报。

---

## 2. 启动检测 + 环境重置

### 2.0 启动检测（任一项不过停下汇报）

```sql
-- 原始备份必须完好（红线：永远不能动这张表）
SELECT COUNT(*) AS rows FROM rebuild5.raw_gps_full_backup;
-- 应 >= 25,000,000；低于此值立即停，原始备份已损坏

-- 没有外部活跃会话在写 rebuild5（防止被其他 agent 清表）
SELECT pid, client_addr, state,
       LEFT(regexp_replace(query,'\s+',' ','g'), 150) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active';
-- 若有 UPDATE/INSERT/TRUNCATE/DROP 相关 query 出现，立即停，先查是谁

-- 样本表存在（冒烟要用）
SELECT COUNT(*) FROM rebuild5_fix4.raw_gps_shared_sample;
-- 应返回约 1,231,704 行，差距大于 ±5% 停下汇报

-- 样本表必须覆盖 7 天（北京时间 12-01 ~ 12-07）
SELECT ts::date AS day, COUNT(*) AS rows
FROM rebuild5_fix4.raw_gps_shared_sample
WHERE ts >= '2025-12-01' AND ts < '2025-12-08'
GROUP BY ts::date
ORDER BY day;
-- 应返回 7 行；每天约 16.8-18.6 万；总计约 1,232,037 行

-- 样例切换保护位必须为空；若存在说明上次样例挂载没恢复干净
SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold');
-- 应为 NULL；非 NULL 立即停下汇报
```

### 2.1 环境重置

```bash
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -f /Users/yangcongan/cursor/WangYou_Data/rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

清理后确认：

```sql
SELECT 'trusted_cell' AS t, COUNT(*) FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'trusted_bs', COUNT(*) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'trusted_lac', COUNT(*) FROM rebuild5.trusted_lac_library
UNION ALL SELECT 'step1_stats', COUNT(*) FROM rebuild5_meta.step1_run_stats
UNION ALL SELECT 'step5_stats', COUNT(*) FROM rebuild5_meta.step5_run_stats
UNION ALL SELECT 'cell_sliding_window', COUNT(*) FROM rebuild5.cell_sliding_window
UNION ALL SELECT 'cell_centroid_detail', COUNT(*) FROM rebuild5.cell_centroid_detail
UNION ALL SELECT 'raw_gps_full_backup', COUNT(*) FROM rebuild5.raw_gps_full_backup;
-- 前 7 行都应 = 0；raw_gps_full_backup 必须保持 >= 25,000,000（未被 reset 脚本影响）
```

---

## 2.5 样例 7 天全链路预跑（必须完整跑 batch 1-7）

目的：用 `rebuild5_fix4.raw_gps_shared_sample` **完整验证 7 天切日 + Step1/Step2-5 流水线编排**。这一段不是“单批冒烟”，而是正式跑前的 **7 天小样例演练**。

### 2.5.1 挂载样例到 `raw_gps_full_backup`（先保护原始全量）

```sql
-- 绝不直接覆盖原始全量；先把原始 full_backup 暂存
ALTER TABLE rebuild5.raw_gps_full_backup RENAME TO raw_gps_full_backup_prod_hold;

-- 样例挂到脚本默认读取的位置
CREATE TABLE rebuild5.raw_gps_full_backup AS
SELECT * FROM rebuild5_fix4.raw_gps_shared_sample;

CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_full_backup_record_id
ON rebuild5.raw_gps_full_backup ("记录数唯一标识");

CREATE INDEX IF NOT EXISTS idx_rebuild5_raw_gps_full_backup_ts
ON rebuild5.raw_gps_full_backup (ts);

ANALYZE rebuild5.raw_gps_full_backup;

-- 验证：样例 full_backup 已经是 7 天数据
SELECT COUNT(*) AS rows FROM rebuild5.raw_gps_full_backup;
SELECT ts::date AS day, COUNT(*) AS rows
FROM rebuild5.raw_gps_full_backup
WHERE ts >= '2025-12-01' AND ts < '2025-12-08'
GROUP BY ts::date
ORDER BY day;
-- 应为约 1,232,037 行；7 行；每天约 16.8-18.6 万
```

### 2.5.2 用同一个 pipelined 脚本跑样例 7 天

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

### 2.5.3 样例预跑监控

Step 1 统计：

```sql
SELECT run_id, status, started_at, finished_at,
       raw_record_count, cleaned_record_count, clean_pass_rate
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at DESC LIMIT 10;
```

样例批次进度：

```sql
SELECT 'cell' AS t, batch_id, COUNT(*) AS rows FROM rebuild5.trusted_cell_library GROUP BY batch_id
UNION ALL SELECT 'bs', batch_id, COUNT(*) FROM rebuild5.trusted_bs_library GROUP BY batch_id
UNION ALL SELECT 'lac', batch_id, COUNT(*) FROM rebuild5.trusted_lac_library GROUP BY batch_id
ORDER BY t, batch_id;
```

样例运行时要求：
- `step1_run_stats` 最终应有 **7 行**
- 每行 `raw_record_count` 应约 **16.8-18.6 万**
- 三层 `trusted_*_library` 最终都应有 **7 个 batch_id**
- 任一单 SQL > 15 分钟未完成，或任一 batch 缺失，立即停下汇报

### 2.5.4 样例预跑验收

```sql
-- 三层都应跑出 7 批
SELECT 'cell' AS t, COUNT(DISTINCT batch_id) AS b FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_lac_library;

-- 垃圾 cell 仍应全 0
SELECT batch_id,
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm='4G') AS g4g,
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm='5G') AS g5g,
  COUNT(*) FILTER (WHERE lac < 100) AS glac
FROM rebuild5.trusted_cell_library
GROUP BY batch_id
ORDER BY batch_id;
```

**验收口径**：这里只验证“7 天流水线能完整跑完，且没有明显 ETL 过滤回退”；不要求样例 batch 7 满足全量的 drift/classification 分布。

### 2.5.5 样例后性能分析（跑通后必须做）

目的：样例阶段除了验证“能跑通”，还要利用小样本定位瓶颈；但性能优化流程保持简单，只做 baseline 对比和最多 2 轮优化，然后决定是否进入全量。

先记录 Step 1 / Step 5 元数据耗时：

```sql
SELECT run_id, status, raw_record_count, cleaned_record_count, clean_pass_rate,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;

SELECT run_id, batch_id, status,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step5_run_stats
ORDER BY batch_id;
```

检查三层产物规模，判断是否某个阶段异常膨胀：

```sql
SELECT 'cell' AS t, batch_id, COUNT(*) AS rows FROM rebuild5.trusted_cell_library GROUP BY batch_id
UNION ALL SELECT 'bs', batch_id, COUNT(*) FROM rebuild5.trusted_bs_library GROUP BY batch_id
UNION ALL SELECT 'lac', batch_id, COUNT(*) FROM rebuild5.trusted_lac_library GROUP BY batch_id
ORDER BY t, batch_id;
```

运行中或复跑时，用短查询抓最慢 SQL：

```sql
SELECT pid, client_addr, state,
       EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       LEFT(regexp_replace(query,'\s+',' ','g'), 200) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active'
ORDER BY query_start LIMIT 5;
```

性能审查要求：
- 只看两个大块：`Step 1`、`Step 2-5`
- 先记录 **baseline**：样例第一次完整跑通后的耗时与慢 SQL
- 最多做 **2 轮优化**：`baseline -> round1 -> round2`；若 round1 已满足预期，可不做 round2
- 每轮都要和 baseline 对比，明确是否变快、快了多少、代价是什么
- 优化手段优先级：现有索引复核 > 补充必要索引 > 小幅代码/SQL 调整
- 若怀疑索引不足，必须进一步用 `EXPLAIN (ANALYZE, BUFFERS)` 对对应 SQL 做点查
- 若样例速度已经合理，也要在汇报中明确写出“检查过，无需新增索引”的结论，不能省略
- `Step 2-5` 的优化**禁止**演化成复杂 SQL；保持单条单用途，禁 ≥3 层 CTE、复杂自 JOIN、难维护的大串联改写

建议的排查重点：
- `Step 1`：`rebuild5.etl_cleaned` 及其阶段表上的时间列、`record_id`、路径查找列
- `Step 2-5`：enrichment 的 `snapshot_seed`、candidate/snapshot/history 相关 join，以及 trusted library / sliding window / centroid detail 在 `batch_id` 维度上的过滤
- 任意运行时间明显高于其他 batch 的 SQL

### 2.5.6 样例后清理 + 恢复原始全量 full_backup

```bash
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -f /Users/yangcongan/cursor/WangYou_Data/rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

```sql
-- 样例跑完后，脚本会把当前 full_backup 还原成 raw_gps；这里统一清掉样例残留
DROP TABLE IF EXISTS rebuild5.raw_gps;
DROP TABLE IF EXISTS rebuild5.raw_gps_full_backup;

-- 恢复原始全量备份
ALTER TABLE rebuild5.raw_gps_full_backup_prod_hold RENAME TO raw_gps_full_backup;

-- 再次确认：原始全量已恢复，trusted_* 全空
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup;  -- 仍应 >= 25,000,000
SELECT 'cell' AS t, COUNT(*) FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs', COUNT(*) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(*) FROM rebuild5.trusted_lac_library;
-- trusted_* 都应 = 0
```

---

## 3. 启动流水线（正式 7 天全量）

**前提**：§2.5 已通过，§2.5.5 性能审查已完成，必要优化已落地并复验通过，且 `rebuild5.raw_gps_full_backup` 已恢复成原始全量。

```bash
cd /Users/yangcongan/cursor/WangYou_Data
LOG=rebuild5/runtime/logs/rerun_$(date +%Y%m%d_%H%M%S).log
nohup python3 rebuild5/scripts/run_step1_step25_pipelined_temp.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  --skip-prepare \
  > $LOG 2>&1 &
echo $! > rebuild5/runtime/rerun.pid
echo "PID=$(cat rebuild5/runtime/rerun.pid)  LOG=$LOG"
```

**预计总耗时 60-150 分钟**。Step 1 快，Step 2-5 慢，通常 Step 2-5 是瓶颈，Step 1 会先跑完 7 天后 Step 2-5 继续。这里显式用 `--skip-prepare`，避免再次调用 `prepare_current_dataset()` 去改写数据源准备态。

---

## 4. 进度监测（MCP PG17，短查询）

### 4.1 Step 1 每天完成情况

```sql
SELECT run_id, status, started_at, finished_at,
       raw_record_count, cleaned_record_count, clean_pass_rate
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at DESC LIMIT 10;
```

**防白跑下限**：每行 `cleaned_record_count > 2_000_000`。低于下限立即停下汇报。

### 4.2 Step 2-5 批次进度

```sql
SELECT 'cell' AS t, batch_id, COUNT(*) AS rows FROM rebuild5.trusted_cell_library GROUP BY batch_id
UNION ALL SELECT 'bs', batch_id, COUNT(*) FROM rebuild5.trusted_bs_library GROUP BY batch_id
UNION ALL SELECT 'lac', batch_id, COUNT(*) FROM rebuild5.trusted_lac_library GROUP BY batch_id
ORDER BY t, batch_id;
```

### 4.3 当前活跃 SQL（发现卡住用）

```sql
SELECT pid, client_addr, state, EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       LEFT(regexp_replace(query,'\s+',' ','g'), 200) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active'
ORDER BY query_start LIMIT 3;
```

单 SQL > 30 分钟未完成停下汇报（不要自己杀，先报）。

### 4.4 进程存活

```bash
ps -p $(cat rebuild5/runtime/rerun.pid) && echo alive || echo exited
```

---

## 5. 验证（7 批全部完成后）

### 5.1 三层都有 7 批
```sql
SELECT 'cell' AS t, COUNT(DISTINCT batch_id) AS b FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_lac_library;
-- 都应 = 7
```

### 5.2 垃圾 cell = 0（硬要求）
```sql
SELECT batch_id,
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm='4G') AS g4g,
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm='5G') AS g5g,
  COUNT(*) FILTER (WHERE lac < 100) AS glac
FROM rebuild5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
-- g4g/g5g/glac 每批都应 = 0；任一项 > 0 停下汇报
```

### 5.3 batch 7 drift 分布
```sql
SELECT drift_pattern, COUNT(*) AS cnt,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(), 2) AS pct
FROM rebuild5.trusted_cell_library WHERE batch_id = 7
GROUP BY drift_pattern ORDER BY cnt DESC;
```
期望：stable 93-96% / insufficient 2-4% / 其他合计 < 1%。严重偏离记录到汇报里。

### 5.4 BS classification（batch 7）
```sql
SELECT classification, COUNT(*) AS cnt
FROM rebuild5.trusted_bs_library WHERE batch_id = 7
GROUP BY classification ORDER BY cnt DESC;
```
期望：`normal` 95%+、`insufficient` 3-5%、其他为少量（个位数到百位数）。

---

## 6. 清理（仅在 §5 全部通过后做）

```sql
DROP TABLE IF EXISTS rebuild5._snapshot_before_etl_filter_cell;
DROP TABLE IF EXISTS rebuild5._snapshot_before_etl_filter_bs;
DROP TABLE IF EXISTS rebuild5._snapshot_before_etl_filter_lac;
DROP TABLE IF EXISTS rebuild5._drift_before_etl_filter;
```

---

## 7. 汇报

写到 `rebuild5/docs/rerun_delivery_2026-04-20_pipelined.md`，包含：

1. 样例 7 天预跑是否通过（含每个 day 的 `raw_record_count` / 7 批是否齐全）
2. baseline 耗时：`Step 1`、`Step 2-5` 两大块分别用了多久
3. round1 / round2 优化内容、是否加了索引、优化前后效果对比
4. 对 `Step 2-5` 的 SQL 复杂度约束是否保持住（明确说明没有引入复杂 SQL）
5. 正式总耗时 + 每天 Step 1 起止 / 每批 Step 2-5 起止
6. 每天 `cleaned_record_count`（确认全部 > 200 万）
7. 批次 1-7 trusted_cell/bs/lac_library 行数
8. batch 7 的 drift 分布 + BS classification 分布
9. 垃圾 cell 检查（全 0 确认）
10. 任何异常 / 遇到的问题 / 卡死 SQL

---

## 8. 失败处理

### 8.1 进程退出但 §5 没通过

```bash
# 查退出原因
tail -100 $(ls -t rebuild5/runtime/logs/rerun_*.log | head -1)
```

根据日志定位到哪一天/哪一步失败，汇报原因给用户决策，**不要**自己发起二次重跑。

### 8.2 DB 卡住 > 30 分钟

先 §4.3 短查询看卡在什么 SQL，报给用户，不自己 `pg_terminate_backend`。

---

## 附：关键文件索引（只读参考）

- 流水线脚本：`rebuild5/scripts/run_step1_step25_pipelined_temp.py`
- Reset 脚本：`rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql`
- ETL 清洗：`rebuild5/backend/app/etl/clean.py`（ODS_RULES）
- Step 1 入口：`rebuild5/backend/app/etl/pipeline.py::run_step1_pipeline`
- Step 2-5 批次入口：见脚本内部调用链
- fix4 优化定位：`rebuild5/docs/fix4/snapshot_seed_sql_optimization.md`
