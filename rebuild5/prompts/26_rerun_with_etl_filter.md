# 26 ETL 过滤 + Step 1-5 全量重跑（batch 1-7） + BS/LAC 方案 v1

> **创建日期**：2026-04-20（2026-04-20 更新：加入 BS/LAC 方案 v1；**改为强制全量重跑**）
> **仓库**：`/Users/yangcongan/cursor/WangYou_Data`
> **数据库**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **范围**：**Step 1-5 全链路 × batch 1-7 全量重跑**（单批重跑不足以生效）
> **前置**：prompts/25（方案 7.4 + GPS 硬过滤）重跑过 batch 7；本次 ETL 过滤 + BS/LAC 方案 v1 需要全量重建

本 prompt 可独立新对话启动，不需要回看历史。

---

## 0. 任务概览

1. **冒烟测试**（§3）：确认代码语法、参数加载
2. **跑前快照**（§4）：保存当前 `trusted_cell/bs/lac_library` 副本，供对比
3. **全量重跑**（§5）：**Step 1 → 2 → 3 → 4 → 5，batch 1-7 按顺序**；Step 1 一次性重跑所有原始数据，Step 2-5 按 batch 循环
4. **验证**（§6）：垃圾 cell 剔除、drift 分布、BS/LAC 三分类、**所有 7 批都正确产出**
5. **汇报**（§8）

### 为什么必须全量重跑

ETL 改了过滤规则（`clean.py` 的 ODS_RULES）后：
- `etl_cleaned` 是**共享表跨批次**，改过滤后所有批次的上游输入都不一样了
- `profile_base` / `trusted_snapshot_t` 是**批次链式依赖**（batch N 引用 N-1 做 diff）
- 只重跑 batch 7 会造成："batch 1-6 的 trusted_*_library 是旧规则 + batch 7 是新规则"数据层混乱
- BS/LAC 方案 v1 的 schema 新字段（normal_cells / anomaly_cells / ...）需要在所有批次回填

---

## 1. 背景与本次改动

### 1.1 用户反馈发现的问题
上一轮（prompts/25）重跑后发现 `trusted_cell_library` 里存在 `(lac=1, bs_id=0, cell_id=2)` 这类明显的垃圾数据。根因是 bs_id 是 cell_id 派生值：

```
5G:  bs_id = cell_id / 4096
4G:  bs_id = cell_id / 256
```

cell_id 过小（如 2、10、290）在 5G 下派生出 `bs_id=0`，污染 BS/LAC 层聚合。

### 1.2 本次修复
在 ETL（Step 1）源头加三条过滤规则：

| 规则 ID | 条件 | 动作 |
|---|---|---|
| `ODS-006a` | 4G `cell_id > 0 AND cell_id < 1000` | 删行 |
| `ODS-006b` | 5G `cell_id > 0 AND cell_id < 4096` | 删行 |
| `ODS-005a` | `lac > 0 AND lac < 100` | lac 置空 |

**预估效果**：剔除 cell 级垃圾 300-500 个，对应 ETL 层数千条 records。

### 1.3 BS/LAC 方案 v1（本次新增的 Step 5 层修复）

**原则**：
- cell > bs > lac 精度优先级倒置；BS/LAC 主要是观察层
- cell 三分类：正常（stable/large_coverage/oversize_single）/ 异常（collision/dynamic/dual_cluster/migration/uncertain）/ insufficient
- BS：只用正常 cell 算质心/覆盖半径；全异常时继承异常类型
- LAC：完全不看异常 BS；正常 BS 超 1000 随机采样 1000；无品质分级（仅 active/dormant/retired）

**BS classification 8 类**（替代旧的 `normal_spread/large_spread/multi_centroid/...`）：
- `normal`（有正常 cell 即正常）
- `insufficient`（全 insufficient cell）
- `collision_bs` / `dynamic_bs` / `dual_cluster_bs` / `uncertain_bs` / `migration_bs`（全异常同类）
- `anomaly`（全异常多类）

**LAC 字段简化**：
- 新增 `normal_bs / anomaly_bs / insufficient_bs / center_lon / center_lat`
- `lifecycle_state` 从 `qualified/excellent/...` 简化为 `active / dormant / retired`
- 保留 `qualified_bs / excellent_bs / qualified_bs_ratio / trend / boundary_stability_score` 向后兼容

### 1.4 已修改的文件（本轮全部累计）

**ETL 过滤（Step 1）**：
| 文件 | 改动 |
|---|---|
| `rebuild5/backend/app/etl/clean.py` | `ODS_RULES` 列表加 3 条新规则 |
| `rebuild5/docs/01b_数据源接入_处理规则.md` | 清洗规则文档同步更新 |

**BS/LAC 方案 v1（Step 5）**：
| 文件 | 改动 |
|---|---|
| `rebuild5/backend/app/maintenance/schema.py` | BS 库加 `normal_cells/anomaly_cells/insufficient_cells`；LAC 库加 `normal_bs/anomaly_bs/insufficient_bs/center_lon/center_lat`；全用 `ALTER ADD IF NOT EXISTS` |
| `rebuild5/backend/app/maintenance/publish_bs_lac.py` | `publish_bs_library` / `publish_lac_library` 完全重写（新分类规则 + 三分类计数 + 正常 BS 采样） |
| `rebuild5/backend/app/maintenance/queries.py` | BS 列表/详情、LAC 列表查询加新字段 |
| `rebuild5/frontend/design/src/views/governance/BSMaintain.vue` | SummaryCard 5 卡、分类 8 类、表格三分类列 |
| `rebuild5/frontend/design/src/views/governance/LACMaintain.vue` | SummaryCard active/dormant/retired、表格三分类列 |
| `rebuild5/frontend/design/src/types/index.ts` | LifecycleState 加 `active` |
| `rebuild5/frontend/design/src/mock/data.ts` + `src/views/evaluation/*.vue` | 同步加 `active:0` 占位 |

### 1.5 用户原则（务必遵守）

- **状态机**：Step 5 信任 Step 3 晋级；Step 3 信任 Step 2 Path B；Step 2 信任 Step 1 ETL
- **精度优先**：宁可过滤保守，不让垃圾数据污染下游
- **源头修复**：ETL 层一次过滤，BS/LAC 下游自然干净
- **cell 是核心**：BS/LAC 不做高精度评级，只做区域观察

---

## 2. 环境与入口

### 2.1 环境

```bash
export PG_DSN='postgresql://postgres:123456@192.168.200.217:5433/ip_loc2'
cd /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend
```

### 2.2 各步入口（按执行顺序）

| Step | Python 入口 | 说明 |
|---|---|---|
| 1 ETL | `app.etl.pipeline.run_step1_pipeline()` | 重新清洗所有原始数据（应用新 ODS 规则） |
| 2 Profile | `app.profile.pipeline.run_step2_pipeline(run_id=...)` | Path B 构建 + profile_base |
| 3 Evaluation | `app.evaluation.pipeline.run_step3_pipeline(run_id=...)` | 流式质量评估 + trusted_snapshot |
| 4 Enrichment | `app.enrichment.pipeline.run_enrichment_pipeline()` | 知识补数 |
| 5 Maintenance | `app.maintenance.pipeline.run_maintenance_pipeline_for_batch(batch_id=7)` | 画像维护 + 标签判定 |

### 2.3 scripts 脚本

如果有 `rebuild5/scripts/run_step1_to_step5_daily_loop.py` 类批处理脚本，可优先使用（封装更好）。先 `cat` 看一下确认它是否接受参数 `batch_id=7`。

---

## 3. 冒烟测试（必做，通过才进下一步）

### 3.1 Python 语法

```bash
python3 -c "
import ast
for f in [
    'app/etl/clean.py',
    'app/etl/pipeline.py',
    'app/profile/pipeline.py',
    'app/evaluation/pipeline.py',
    'app/maintenance/label_engine.py',
    'app/maintenance/pipeline.py',
]:
    ast.parse(open(f).read()); print(f'OK {f}')
"
```

### 3.2 参数加载

```bash
python3 -c "
from app.profile.logic import load_multi_centroid_v2_params, load_antitoxin_params
mc = load_multi_centroid_v2_params(load_antitoxin_params())
assert mc['min_cluster_dev_day_pts'] == 4
assert mc['multi_centroid_entry_p90_m'] == 1300.0
assert mc['min_total_dedup_pts'] == 8
print('params OK')
"
```

### 3.3 新 ODS 规则能解析

```bash
python3 -c "
from app.etl.clean import ODS_RULES
ids = {r['id'] for r in ODS_RULES}
for rid in ['ODS-005a', 'ODS-006a', 'ODS-006b']:
    assert rid in ids, f'缺 {rid}'
print(f'found {len(ids)} ODS rules; new filters present')
"
```

### 3.3a BS/LAC schema 字段已就位

```bash
python3 -c "
import os
os.environ.setdefault('PG_DSN', 'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2')
from app.maintenance.schema import ensure_maintenance_schema
ensure_maintenance_schema()
print('schema migration OK')
"
```

```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema='rebuild5' AND table_name='trusted_bs_library'
  AND column_name IN ('normal_cells','anomaly_cells','insufficient_cells');
-- 应返回 3 行

SELECT column_name FROM information_schema.columns
WHERE table_schema='rebuild5' AND table_name='trusted_lac_library'
  AND column_name IN ('normal_bs','anomaly_bs','insufficient_bs','center_lon','center_lat');
-- 应返回 5 行
```

### 3.4 测试 ETL clean 在小集合上能跑

**不要直接跑全量**。先查现有数据里预估会被过滤的量：

```sql
-- 预估垃圾 cell 数量（当前 etl_parsed 或类似源）
SELECT
  COUNT(*) FILTER (WHERE cell_id > 0 AND cell_id < 1000 AND tech_norm = '4G') AS "4G过小",
  COUNT(*) FILTER (WHERE cell_id > 0 AND cell_id < 4096 AND tech_norm = '5G') AS "5G过小",
  COUNT(*) FILTER (WHERE lac > 0 AND lac < 100) AS "lac过小"
FROM rebuild5.etl_parsed;
```

如果预估数字合理（≤ 总数 1%），进 §4。

---

## 4. 跑前快照（关键，供后续 BS/LAC 研究对比）

### 4.1 保存所有 batch 的 cell/bs/lac 当前状态

```sql
-- 保存全量旧版快照（batch 1-7），后续用于 diff
CREATE TABLE IF NOT EXISTS rebuild5._snapshot_before_etl_filter_cell AS
SELECT * FROM rebuild5.trusted_cell_library;

CREATE TABLE IF NOT EXISTS rebuild5._snapshot_before_etl_filter_bs AS
SELECT * FROM rebuild5.trusted_bs_library;

CREATE TABLE IF NOT EXISTS rebuild5._snapshot_before_etl_filter_lac AS
SELECT * FROM rebuild5.trusted_lac_library;

-- 按 batch 汇总行数
SELECT batch_id,
  (SELECT COUNT(*) FROM rebuild5._snapshot_before_etl_filter_cell c WHERE c.batch_id = b.batch_id) AS cell_cnt,
  (SELECT COUNT(*) FROM rebuild5._snapshot_before_etl_filter_bs c WHERE c.batch_id = b.batch_id) AS bs_cnt,
  (SELECT COUNT(*) FROM rebuild5._snapshot_before_etl_filter_lac c WHERE c.batch_id = b.batch_id) AS lac_cnt
FROM (SELECT DISTINCT batch_id FROM rebuild5._snapshot_before_etl_filter_cell) b
ORDER BY batch_id;
```

### 4.2 保存当前 drift 分布（按 batch）

```sql
CREATE TABLE IF NOT EXISTS rebuild5._drift_before_etl_filter AS
SELECT batch_id, drift_pattern, COUNT(*) AS cnt
FROM rebuild5.trusted_cell_library
GROUP BY batch_id, drift_pattern ORDER BY batch_id, cnt DESC;

SELECT * FROM rebuild5._drift_before_etl_filter ORDER BY batch_id, cnt DESC LIMIT 30;
```

### 4.3 记录异常样本数量（当前垃圾 cell 全部要被 ETL 过滤清掉）

```sql
SELECT batch_id,
  COUNT(*) FILTER (WHERE lac <= 10) AS "lac<=10",
  COUNT(*) FILTER (WHERE bs_id <= 10) AS "bs<=10",
  COUNT(*) FILTER (WHERE cell_id <= 10) AS "cell<=10",
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm = '4G'
                OR cell_id < 4096 AND tech_norm = '5G'
                OR lac < 100) AS garbage_total,
  COUNT(*) AS total
FROM rebuild5.trusted_cell_library
GROUP BY batch_id ORDER BY batch_id;
```

---

## 5. 正式重跑（Step 1-5 × batch 1-7 全量重跑）

### 5.0 执行方式（推荐）

使用现有脚本 `rebuild5/scripts/run_step1_to_step5_daily_loop.py`，它封装了完整的 7 天循环：
1. 准备完整原始数据集
2. 按天切片：day 1 → step1 → step2-5；day 2 → step1 → step2-5；...；day 7
3. 每天产出一个 batch（最终 batch 1-7）
4. 结束时恢复 `raw_gps` 和累积 `etl_cleaned` 表

```bash
cd /Users/yangcongan/cursor/WangYou_Data/rebuild5
python3 scripts/run_step1_to_step5_daily_loop.py --start-day 2025-12-01 --end-day 2025-12-07
# （起止日期根据实际数据集调整）
```

**预期总耗时**：**60-180 分钟**（7 天 × 每天 10-25 分钟）。

**关键前提**：
- 脚本会先执行 `scripts/reset_step1_to_step5_for_full_rerun_v3.sql` 清理旧的 step1-5 状态
- 脚本本身会应用 schema migration（新字段会自动 ALTER ADD）

### 5.1 如果脚本不可用或失败，手动按步骤

先手动 reset：

```bash
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

然后按 batch 循环：

```bash
# 先 prepare raw_gps + 跑 step1 一次（etl_cleaned 是全量共享）
python3 -c "
import os
os.environ.setdefault('PG_DSN', 'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2')
from app.etl.source_prep import prepare_current_dataset
from app.etl.pipeline import run_step1_pipeline
prepare_current_dataset()
print(run_step1_pipeline())
"

# 对每一天按顺序跑 step2-5（batch 1..7）
for DAY in 2025-12-01 2025-12-02 2025-12-03 2025-12-04 2025-12-05 2025-12-06 2025-12-07; do
  python3 -c "
import os
os.environ.setdefault('PG_DSN', 'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2')
from app.profile.pipeline import run_step2_pipeline
from app.evaluation.pipeline import run_step3_pipeline
from app.enrichment.pipeline import run_enrichment_pipeline
from app.maintenance.pipeline import run_maintenance_pipeline
run_step2_pipeline()
run_step3_pipeline()
run_enrichment_pipeline()
run_maintenance_pipeline()
print('day $DAY done')
"
done
```

### 5.2 中途各步骤验证（每完成一天检查）

**Step 1（ETL）** 产出 `etl_cleaned` 应无残留小 cell_id/lac：

```sql
SELECT
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm = '4G') AS "残4G过小",
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm = '5G') AS "残5G过小",
  COUNT(*) FILTER (WHERE lac < 100) AS "残lac过小",
  COUNT(*) AS total
FROM rebuild5.etl_cleaned;
-- 所有"残"项应为 0
```

**Step 2-5 每个 batch 完成后**：

```sql
-- 确认该 batch 的 trusted_cell/bs/lac_library 都已生成
SELECT batch_id,
  (SELECT COUNT(*) FROM rebuild5.trusted_cell_library c WHERE c.batch_id = b.batch_id) AS cell_cnt,
  (SELECT COUNT(*) FROM rebuild5.trusted_bs_library c WHERE c.batch_id = b.batch_id) AS bs_cnt,
  (SELECT COUNT(*) FROM rebuild5.trusted_lac_library c WHERE c.batch_id = b.batch_id) AS lac_cnt
FROM (SELECT DISTINCT batch_id FROM rebuild5.trusted_cell_library ORDER BY 1 DESC LIMIT 3) b
ORDER BY batch_id DESC;
```

### 5.4 Step 4 Enrichment

```bash
python3 -c "
import os, time
os.environ.setdefault('PG_DSN', 'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2')
from app.enrichment.pipeline import run_enrichment_pipeline
t = time.time()
result = run_enrichment_pipeline()
print(f'step4 done in {time.time()-t:.1f}s')
"
```

### 5.5 Step 5 Maintenance

```bash
python3 -c "
import os, time
os.environ.setdefault('PG_DSN', 'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2')
from app.maintenance.pipeline import run_maintenance_pipeline_for_batch
t = time.time()
result = run_maintenance_pipeline_for_batch(batch_id=7)
print(f'step5 done in {time.time()-t:.1f}s')
"
```

**预期总耗时**：Step 1-5 全链路约 30-60 分钟（取决于数据量）。

---

## 6. 验证（针对全部 7 批）

### 6.0 所有 7 批都已产出

```sql
-- 三层都应有 batch 1-7 共 7 个 distinct batch_id
SELECT 'cell' AS layer, COUNT(DISTINCT batch_id) AS batches, MIN(batch_id) AS min_b, MAX(batch_id) AS max_b
FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs', COUNT(DISTINCT batch_id), MIN(batch_id), MAX(batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id), MIN(batch_id), MAX(batch_id) FROM rebuild5.trusted_lac_library;
-- batches 都应 = 7
```

如任一层 batches != 7，**立即停下汇报**。

### 6.1 垃圾数据被完全剔除（必须通过，按 batch 检查）

```sql
SELECT batch_id,
  COUNT(*) FILTER (WHERE lac <= 10) AS "lac<=10",
  COUNT(*) FILTER (WHERE bs_id <= 10) AS "bs<=10",
  COUNT(*) FILTER (WHERE cell_id <= 10) AS "cell<=10",
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm = '4G'
                OR cell_id < 4096 AND tech_norm = '5G') AS "cell_id过小",
  COUNT(*) FILTER (WHERE lac < 100) AS "lac过小"
FROM rebuild5.trusted_cell_library
GROUP BY batch_id ORDER BY batch_id;
-- 所有"过小"项在每个 batch 都应为 0
```

如果任何"过小"项非 0，**立即停下汇报**。

### 6.1.1 BS/LAC 方案 v1 三分类合理（所有 batch）

```sql
-- BS classification 分布（按 batch）
SELECT batch_id, classification, COUNT(*) AS cnt
FROM rebuild5.trusted_bs_library
GROUP BY batch_id, classification
ORDER BY batch_id, cnt DESC;
```

**期望**（参考 BS/LAC v1 首次验证结果）：
- `normal`: 95%+
- `insufficient`: 3-5%
- `dual_cluster_bs`: 少量（~100）
- `uncertain_bs`: 少量（~70）
- `collision_bs` / `dynamic_bs` / `migration_bs` / `anomaly`: 个位数

```sql
-- LAC lifecycle 分布（按 batch；应全 active 或极少 dormant）
SELECT batch_id, lifecycle_state, COUNT(*) FROM rebuild5.trusted_lac_library
GROUP BY batch_id, lifecycle_state ORDER BY batch_id, lifecycle_state;

-- 确认 LAC 三分类 BS 字段已填（最近批次抽查）
SELECT batch_id,
  COUNT(*) FILTER (WHERE normal_bs > 0) AS lacs_with_normal,
  COUNT(*) FILTER (WHERE anomaly_bs > 0) AS lacs_with_anomaly,
  COUNT(*) FILTER (WHERE center_lon IS NOT NULL) AS lacs_with_centroid,
  COUNT(*) AS total_lac
FROM rebuild5.trusted_lac_library
GROUP BY batch_id ORDER BY batch_id;
```

**异常检测**：
- 如果 `normal` < 80% → 数据有问题
- 如果 `insufficient` > 10% → 上游 Step 3 晋级问题
- `center_lon IS NOT NULL` 的 LAC 占比应 ≈ `normal_bs > 0` 的 LAC 占比

### 6.2 drift 分布（所有 batch 都应符合方案 7.4 预期）

```sql
SELECT batch_id, drift_pattern, COUNT(*) AS cnt,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (PARTITION BY batch_id), 2) AS pct
FROM rebuild5.trusted_cell_library
GROUP BY batch_id, drift_pattern
ORDER BY batch_id, cnt DESC;
```

**期望**（每个 batch 的分布）：

| 标签 | 预期 |
|---|---|
| stable | **93-96%** |
| insufficient | 2-4% |
| large_coverage | < 1% |
| dual_cluster | < 0.2% |
| uncertain | < 0.1% |
| oversize_single | 个位数 |
| collision / migration | 个位数 |

每个 batch 的 stable / insufficient 比例应相近（±2pp 内）。若某 batch 明显偏离，可能该 batch 数据质量特殊，需记录在汇报里。

### 6.3 前后对比（按 batch 汇总）

```sql
-- 三层前后总行数对比
WITH before_cell AS (SELECT batch_id, COUNT(*) AS cnt FROM rebuild5._snapshot_before_etl_filter_cell GROUP BY batch_id),
     after_cell AS (SELECT batch_id, COUNT(*) AS cnt FROM rebuild5.trusted_cell_library GROUP BY batch_id)
SELECT COALESCE(b.batch_id, a.batch_id) AS batch_id,
  b.cnt AS cell_before, a.cnt AS cell_after,
  COALESCE(a.cnt, 0) - COALESCE(b.cnt, 0) AS delta
FROM before_cell b FULL OUTER JOIN after_cell a USING (batch_id)
ORDER BY batch_id;

-- BS / LAC 类似（替换表名即可）

-- drift 分布前后对比（按 batch）
WITH before_dist AS (
  SELECT batch_id, drift_pattern, cnt FROM rebuild5._drift_before_etl_filter
),
after_dist AS (
  SELECT batch_id, drift_pattern, COUNT(*) AS cnt
  FROM rebuild5.trusted_cell_library GROUP BY batch_id, drift_pattern
)
SELECT COALESCE(b.batch_id, a.batch_id) AS batch_id,
       COALESCE(b.drift_pattern, a.drift_pattern) AS drift,
       COALESCE(b.cnt, 0) AS before_cnt,
       COALESCE(a.cnt, 0) AS after_cnt
FROM before_dist b FULL OUTER JOIN after_dist a
  USING (batch_id, drift_pattern)
WHERE COALESCE(a.cnt, 0) + COALESCE(b.cnt, 0) > 0
ORDER BY batch_id, after_cnt DESC;
```

### 6.4 UI 验证

访问前端：

**Cell 画像维护页**：
- SummaryCard 10 卡都显示
- 随便点个筛选 tab 确认没异常
- 表格里没有再出现 `(lac=1, bs=0, cell=2)` 等怪数据

**BS 维护页**（新版 BS-LAC-v1）：
- SummaryCard 5 卡（总数 / 正常 / 证据不足 / 异常 / 合格）
- 表格列包含：正常 / 异常 / 证据不足 三分类计数
- 分类 tag 8 种：正常 / 证据不足 / 碰撞 / 动态 / 双质心 / 多质心 / 迁移 / 异常混合
- 展开行详情显示 Cell 三分类 + BS 质心（基于正常 cell）

**LAC 维护页**（新版 BS-LAC-v1）：
- SummaryCard 5 卡（总数 / 活跃 / 休眠 / 退出 / 含异常BS）
- 表格列：总BS / 正常 / 异常 / 证据不足 / 质心 / 面积 / 异常BS率
- 状态标签：active（绿）/ dormant / retired

### 6.5 保留快照表（重要）

**不要 DROP** 以下表 —— 它们供下一轮 BS/LAC 研究使用：

- `rebuild5._snapshot_before_etl_filter_cell`
- `rebuild5._snapshot_before_etl_filter_bs`
- `rebuild5._snapshot_before_etl_filter_lac`
- `rebuild5._drift_before_etl_filter`

---

## 7. 安全约束

### 7.1 SQL 不能复杂

- 单条 SQL 只做一件事
- 禁止 ≥3 层 CTE、复杂自 join
- 进度观察用短查询（见 §附录 A）

### 7.2 进度观察

```sql
SELECT pid, EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       LEFT(regexp_replace(query,'\s+',' ','g'), 200) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND state='active' AND pid != pg_backend_pid()
ORDER BY query_start LIMIT 3;
```

### 7.3 异常退出

pipeline 卡住超过 30 分钟（单步）：

```bash
# 查 python 进程
ps aux | grep -E 'run_step|run_maintenance|run_profile|daily_loop' | grep -v grep

# kill
kill <pid>

# 终止 pg 残留查询
# psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
#          WHERE datname='ip_loc2' AND state='active' AND pid != pg_backend_pid()"
```

### 7.4 不要改代码

只跑代码。发现 bug 先停汇报。

### 7.5 失败回滚

如果重跑失败或中途中断：

```bash
# 查看改动
git status
git diff rebuild5/backend/app/etl/clean.py rebuild5/backend/app/maintenance/publish_bs_lac.py

# 完整回滚（代码）:
# git checkout -- rebuild5/backend/app/etl/clean.py \
#                 rebuild5/backend/app/maintenance/publish_bs_lac.py \
#                 rebuild5/backend/app/maintenance/schema.py \
#                 rebuild5/config/antitoxin_params.yaml

# 回滚后重跑完整链路
psql -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
python3 rebuild5/scripts/run_step1_to_step5_daily_loop.py --start-day 2025-12-01 --end-day 2025-12-07
```

### 7.6 断点续跑

`run_step1_to_step5_daily_loop.py` 按天循环，如果跑到某一天卡住：

1. 检查已完成的 batch 数（`SELECT COUNT(DISTINCT batch_id) FROM rebuild5.trusted_cell_library`）
2. 已完成的 batch 数据已入库，不会丢
3. 但安全起见建议**直接重启整个脚本**（用 `--skip-prepare` 跳过 raw 准备）

---

## 8. 汇报格式

完成后写一份报告到 `rebuild5/docs/rerun_delivery_2026-04-20_full_etl_bslac.md`，包含：

1. **总耗时 + 每个 batch 的耗时**（7 天 × 各 step 耗时）
2. **ETL 层垃圾剔除量**：
   - ODS-005a / ODS-006a / ODS-006b 各命中多少行
   - `etl_cleaned` 总行数前后对比
3. **三层数据量前后对比**（按 batch）：
   - trusted_cell_library：每 batch 减少多少 cell
   - trusted_bs_library：每 batch 减少多少 bs
   - trusted_lac_library：每 batch 是否保留一致
4. **drift 分布前后**（所有 7 批）：
   - 每个 batch 的 stable / insufficient / 其他比例
   - 与 `_drift_before_etl_filter` 的 diff
5. **BS/LAC 方案 v1 新分布**（所有 7 批）：
   - BS classification 8 类各 batch 命中量
   - LAC lifecycle 分布 + 三分类 BS 字段填充度
6. **异常告警**：有无触发停止条件
7. **UI 状态**（Cell / BS / LAC 三个维护页的截图或描述）
8. **遗留观察**：有无新发现的异常模式（为下一轮研究留线索）

**特别提示**：如发现任何"看着不对劲"的 cell / bs / lac 样本，在报告里列出。
重点关注：
- 跨 batch 分布是否稳定（某 batch 偏离不应 >2pp）
- BS center_lon/lat 是否合理（在 LAC 地理范围内）
- LAC area_km2 是否接近合理值（市/区级通常 100-1000 km²）

---

## 9. 下一轮要做的事（不在本次范围）

本次重跑完成后，会回到主对话继续：

1. **BS/LAC Step 5 聚合逻辑研究** — 基于 §4 保存的快照做前后 diff，看 BS/LAC 层是否还有结构性问题
2. **标签规则微调（如需）** — 基于干净数据重新审视方案 7.4 的边界 case
3. **生成最终重跑 prompt** — 整合所有修复

本次**不要**尝试解决 BS/LAC 问题或调整标签规则。

---

## 附录 A. 常用观察 SQL

```sql
-- 当前活跃后端（最多返 3 条）
SELECT pid, state, EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       wait_event_type, wait_event,
       LEFT(regexp_replace(query,'\s+',' ','g'), 300) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state != 'idle'
ORDER BY query_start NULLS LAST LIMIT 3;

-- 表行数速查（按 batch）
SELECT 'etl_cleaned' AS tbl, NULL::int AS batch_id, COUNT(*) AS rows FROM rebuild5.etl_cleaned
UNION ALL SELECT 'profile_base', NULL::int, COUNT(*) FROM rebuild5.profile_base
UNION ALL SELECT 'trusted_snapshot_cell', batch_id, COUNT(*) FROM rebuild5.trusted_snapshot_cell GROUP BY batch_id
UNION ALL SELECT 'trusted_cell_library', batch_id, COUNT(*) FROM rebuild5.trusted_cell_library GROUP BY batch_id
UNION ALL SELECT 'trusted_bs_library', batch_id, COUNT(*) FROM rebuild5.trusted_bs_library GROUP BY batch_id
UNION ALL SELECT 'trusted_lac_library', batch_id, COUNT(*) FROM rebuild5.trusted_lac_library GROUP BY batch_id
UNION ALL SELECT 'label_results', batch_id, COUNT(*) FROM rebuild5.label_results GROUP BY batch_id
ORDER BY tbl, batch_id;

-- run_log 最近状态
SELECT run_type, MAX(started_at) AS last_started, MAX(finished_at) AS last_finished, MAX(status) AS status
FROM rebuild5_meta.run_log
WHERE started_at > NOW() - INTERVAL '2 hours'
GROUP BY run_type ORDER BY last_started DESC;
```

## 附录 B. 关键参数

| 参数 | 值 | 位置 |
|---|---|---|
| `multi_centroid_v2.min_cluster_dev_day_pts` | 4 | `config/antitoxin_params.yaml` |
| `multi_centroid_v2.multi_centroid_entry_p90_m` | 1300 | 同上 |
| `multi_centroid_v2.min_total_dedup_pts` | 8 | 同上 |
| `multi_centroid_v2.min_total_devs` | 3 | 同上 |
| `multi_centroid_v2.min_total_active_days` | 3 | 同上 |
| ODS-006a（4G CellID 过小） | `< 1000` | `app/etl/clean.py` ODS_RULES |
| ODS-006b（5G CellID 过小） | `< 4096` | 同上 |
| ODS-005a（LAC 过小） | `< 100` | 同上 |
| BS/LAC 正常 cell 标签集合 | stable/large_coverage/oversize_single | `publish_bs_lac.py` |
| BS/LAC 异常 cell 标签集合 | collision/dynamic/dual_cluster/migration/uncertain | 同上 |
| LAC 正常 BS 采样上限 | 1000（随机取） | 同上 |

## 附录 C. 相关文档

- 方案 7.4：`rebuild5/docs/gps研究/09_标签规则重构方案7_4.md`
- 异常数据研究：`rebuild5/docs/gps研究/10_异常数据研究_方案7_4后.md`
- ETL 处理规则：`rebuild5/docs/01b_数据源接入_处理规则.md`
- Step 3 设计：`rebuild5/docs/03_流式质量评估.md`
- 上一轮 prompt：`rebuild5/prompts/25_rerun_with_7_4_and_gps_hardfilter.md`
- 本轮原始任务：`rebuild5/prompts/24_ui_label_alignment_and_refinement.md`
