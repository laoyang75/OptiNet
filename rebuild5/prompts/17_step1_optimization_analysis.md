# Step 1 ETL 性能优化分析 — 只出报告，不改代码

> 目标：分析 Step 1 的每个子步骤耗时，找出瓶颈，评估可行的优化策略。
> 约束：**只输出分析报告，不修改任何代码文件。**
> 报告输出到：`rebuild5/docs/dev/step1_optimization_report.md`

## 背景

Step 1 是一次性 ETL（后续不需要重跑），但当前全量耗时 **6768 秒（113 分钟）**，是整个流程中最慢的步骤。虽然一次性，但如果需要因数据修正或规则变更重跑，113 分钟的代价太高。而且 Step 1 的优化经验可以直接应用到 Step 4/5 的类似操作。

## 当前环境

- PG 17（192.168.200.217:5433，Docker `--shm-size=8g`）
- 40 核 E5-2660 v2 / 251GB RAM / 6.7TB RAID
- PG 配置：shared_buffers=64GB, max_parallel_workers_per_gather=16, work_mem=512MB, jit=off
- 数据集：beijing_7d, raw_gps 25,442,069 行
- 连接：psycopg 3, autocommit=True
- 连接入口：`rebuild5/backend/app/core/database.py` 的 `get_conn()`

## Step 1 流程和代码位置

Step 1 由 `rebuild5/backend/app/etl/pipeline.py` 的 `run_step1_pipeline()` 编排，依次执行：

### 1. Parse（解析）—— `rebuild5/backend/app/etl/parse.py`

```
raw_gps (25M 行)
  → _parse_cell_infos() → etl_ci (28.8M 行)    # CTAS: JSONB 展开 + 列提取
  → _parse_ss1()        → etl_ss1 (16.6M 行)   # CTAS: 字符串拆分 + 多阶段展开
  → UNION ALL           → etl_parsed (45.4M 行) # CTAS
```

- `_parse_cell_infos()`（parse.py:44-146）：对 raw_gps 的 `cell_infos` JSONB 字段做 `jsonb_each()` 展开，提取 30+ 列。每条原始记录可能展开成多行。整个操作是一个巨大的 CTAS。
- `_parse_ss1()`（parse.py:149-312）：对 raw_gps 的 `ss1` 字符串字段做三阶段处理：
  - 阶段 1（`_groups`）：按 `;` 拆分 + ORDINALITY
  - 阶段 2（`_carry`）：窗口函数 carry forward cell_block
  - 阶段 3（最终表）：CTE 拆解 cell/signal 块 + JOIN
- UNION ALL：简单合并 etl_ci + etl_ss1

### 2. Clean（清洗）—— `rebuild5/backend/app/etl/clean.py`

```
etl_parsed (45.4M 行)
  → CREATE TABLE etl_clean_stage AS SELECT * FROM etl_parsed  # 全表复制
  → 18 条 ODS 规则：逐条 COUNT + UPDATE                        # 18 次全表扫描
  → ALTER TABLE 加 9 列                                         # DDL
  → 4 次 UPDATE（bs_id/operator_cn/时间戳/event_time）          # 4 次全表扫描
  → DELETE 无效行                                               # 全表扫描
  → etl_clean_stage (45.3M 行)
```

- clean.py:40：`CREATE TABLE etl_clean_stage AS SELECT * FROM etl_parsed` — 45.4M 行全表复制
- clean.py:43-60：18 条清洗规则，每条都做 `COUNT(*) WHERE condition` + `UPDATE SET field=NULL WHERE condition` — 共 36 次全表扫描
- clean.py:76-108：4 次 `UPDATE SET` 计算派生字段（bs_id、operator_cn、时间戳、event_time）— 4 次全表扫描
- 总计：clean 阶段对 45.4M 行表做了 **至少 40 次全表扫描/更新**

### 3. Fill（补齐）—— `rebuild5/backend/app/etl/fill.py`

```
etl_clean_stage (45.3M 行)
  → CTAS with 3 CTE pools:
      stable_pool:  GROUP BY record_id, cell_id → array_agg
      ci_pool:      GROUP BY record_id, cell_id (cell_infos only) → array_agg
      ss1_pool:     GROUP BY record_id, cell_id (ss1 only) → array_agg + per-field timestamp
  → 3 路 LEFT JOIN → etl_cleaned (45.3M 行)
```

- fill.py:31-108：一个巨大的 CTAS，包含 3 个 CTE（每个都对 45.3M 行做 GROUP BY + array_agg），然后 3 路 LEFT JOIN 回原表
- 这是 Step 1 中最重的单个查询

### 4. 收尾 —— `pipeline.py`

```
→ calculate_field_coverage (2 次全表扫描)
→ DROP etl_clean_stage, etl_ci, etl_ss1
→ 写 stats
```

## 你需要做的分析

### 分析 1：各子步骤耗时测量

在 `rebuild5_bench` schema 中用 10% 抽样数据（`cell_id % 10 = 0` 或 `record_id` 哈希取样），分别测量每个子步骤的耗时：

```sql
CREATE SCHEMA IF NOT EXISTS rebuild5_bench;
CREATE TABLE rebuild5_bench.raw_gps AS
SELECT * FROM rebuild5.raw_gps WHERE "记录数唯一标识" LIKE '%0';
-- 或用其他方式抽约 250 万行
```

需要单独测量的操作：
1. `_parse_cell_infos` CTAS
2. `_parse_ss1` 三阶段（groups → carry → final）
3. UNION ALL CTAS
4. `CREATE TABLE etl_clean_stage AS SELECT *` 全表复制
5. 18 条 ODS 规则的总耗时
6. 4 次 UPDATE（bs_id / operator_cn / 时间戳 / event_time）的总耗时
7. DELETE 无效行
8. fill CTAS（3 CTE + 3 LEFT JOIN）

### 分析 2：瓶颈定位

根据测量结果，确定：
- 哪个子步骤占比最大？
- 是 CPU bound（排序/聚合/字符串解析）还是 IO bound（大表扫描/写入）？
- 哪些操作可以合并减少全表扫描次数？

### 分析 3：优化策略评估

对每个瓶颈，评估以下策略的可行性和预期收益（**不需要实现，只评估**）：

#### 策略 A：减少全表扫描次数

clean 阶段做了 40+ 次全表扫描。能否：
- 把 18 条 ODS 规则合并为 1 次 UPDATE（CASE WHEN 组合）？
- 把 4 次派生字段 UPDATE 也合并进去？
- 甚至把 clean 和 fill 合并为一个 CTAS，跳过 etl_clean_stage 中间表？

评估：合并后的 SQL 复杂度是否可控？PG 优化器能否处理？

#### 策略 B：CTAS 利用 PG 并行 worker

当前的 CTAS（parse、fill）能否自动利用 PG 的 max_parallel_workers_per_gather=16？
- 检查 EXPLAIN 看 PG 是否为这些 CTAS 分配了并行 worker
- 如果没有，是否因为表太新没有统计信息（需要先 ANALYZE）？
- 或者因为 JSONB 操作/字符串函数被标记为 PARALLEL UNSAFE？

#### 策略 C：多进程分片

哪些操作适合用 `rebuild5/backend/app/core/parallel.py` 的多进程分片？
- parse 的 CTAS 能按 `record_id` 分片吗？
- fill 的 CTAS 能按 `record_id` 或 `cell_id` 分片吗？（注意 fill 的 GROUP BY 是 `record_id + cell_id`）
- clean 的多次 UPDATE 能按 `ctid` 范围分片吗？

#### 策略 D：UNLOGGED TABLE

所有中间表（etl_ci、etl_ss1、etl_parsed、etl_clean_stage）都可以用 UNLOGGED TABLE（跳过 WAL）。
- 单独测试 UNLOGGED 对 CTAS 和 UPDATE 的加速效果

#### 策略 E：跳过中间表

当前流程建了 5 张中间表（etl_ci、etl_ss1、etl_parsed、etl_clean_stage、etl_cleaned）。能否减少？
- 能否直接 `etl_ci UNION ALL etl_ss1 → etl_clean_stage`（跳过 etl_parsed）？
- 能否把 clean 的 UPDATE 操作变成 CTAS 中的 CASE WHEN 表达式，避免单独的 UPDATE 步骤？

#### 策略 F：SQL 优化

- `_parse_cell_infos` 的 `jsonb_each()` 展开是否有更高效的写法？
- `_parse_ss1` 的 3 阶段拆分能否合并？
- fill 的 3 个 CTE（stable_pool、ci_pool、ss1_pool）能否合并为 1 个（减少对 etl_clean_stage 的扫描次数）？
- array_agg + [1] 取第一个值是否可以用 `FIRST_VALUE` 窗口函数替代？

### 分析 4：组合策略评估

评估最有前途的策略组合，例如：
- UNLOGGED + 合并 UPDATE + 跳过 etl_parsed
- CTAS 并行 + UNLOGGED
- 多进程分片 + UNLOGGED

## 输出要求

输出一份完整的分析报告到 `rebuild5/docs/dev/step1_optimization_report.md`，包含：

1. **各子步骤耗时表**（10% 抽样实测）
2. **瓶颈排名**（占比最大的前 3 个操作）
3. **每种策略的可行性评估**（可行/不可行/有风险，以及预期加速比）
4. **推荐优化方案**（按优先级排序，标注预期总加速比）
5. **不建议做的优化**（以及原因）

## 注意事项

1. **不要修改任何代码文件** — 只出报告
2. **在 rebuild5_bench schema 中测试** — 不动生产数据
3. **测试完成后 DROP SCHEMA rebuild5_bench CASCADE**
4. **如果需要看 EXPLAIN，用 EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)**
5. **记录每次测试的 SQL 和结果**，方便后续复现

## 相关代码文件

- `rebuild5/backend/app/etl/pipeline.py` — Step 1 编排
- `rebuild5/backend/app/etl/parse.py` — 解析（JSONB 展开 + ss1 拆分）
- `rebuild5/backend/app/etl/clean.py` — 清洗（18 规则 + 派生字段）
- `rebuild5/backend/app/etl/fill.py` — 补齐（3 池模型）
- `rebuild5/backend/app/core/database.py` — 数据库连接
- `rebuild5/backend/app/core/parallel.py` — 并行执行器（参考，不要求用）
