# Step 4 / Step 5 并行化策略探索

> 目标：当前 Step 4 和 Step 5 的关键操作被锁在单核上（PG 的 INSERT/UPDATE 不支持并行 worker）。需要探索不同的并行化策略，找到最优方案，让 40 核服务器真正用起来。
> 
> 不是测核数——是探索"怎么才能并行"。

## 问题本质

PostgreSQL 的 `INSERT INTO ... SELECT ...` 和 `UPDATE ... FROM ...` 语句，即使 SELECT 部分可以用并行 worker，写入部分仍然是单线程的。我们的 5 个瓶颈操作全部卡在这里。

当前服务器 40 核 / 251GB RAM，但这些操作只用了 1 核。

## 当前环境

- PG 17（192.168.200.217:5433，Docker `--shm-size=8g`）
- 40 核 E5-2660 v2 / 251GB RAM / 6.7TB RAID
- PG 配置：shared_buffers=64GB, max_parallel_workers_per_gather=16, work_mem=512MB
- 连接方式：`psycopg.connect(dsn, autocommit=True)`
- 代码入口：`rebuild5/backend/app/core/database.py` 的 `get_conn()`

## 需要并行化的 5 个操作

| # | 操作 | 文件 | 当前耗时 | 数据量 | 特征 |
|---|------|------|---------|--------|------|
| A | Step 4 enriched_records INSERT | enrichment/pipeline.py `_insert_enriched_records()` | 665s | 35.8M 行 | 纯 SELECT→INSERT，无 JOIN |
| B | Step 5 sliding_window INSERT | maintenance/window.py `refresh_sliding_window()` | ~120s | 35.8M 行 | 纯 SELECT→INSERT |
| C | Step 5 daily_centroids INSERT | maintenance/window.py `build_daily_centroids()` | ~60s | 窗口全量 → ~100K 组 | GROUP BY + PERCENTILE_CONT |
| D | Step 5 cell_metrics INSERT | maintenance/window.py `recalculate_cell_metrics()` | ~180s | 窗口全量 → ~100K 组 | GROUP BY + 多 PERCENTILE_CONT + COUNT DISTINCT |
| E | Step 5 cell_metrics UPDATE（半径） | maintenance/window.py `recalculate_cell_metrics()` | 包含在 D 中 | ~100K 行 | JOIN + PERCENTILE_CONT + UPDATE |

操作 A/B 是 IO 密集型（大量行写入），操作 C/D/E 是 CPU 密集型（排序 + 聚合）。最优策略可能不同。

## 需要探索的策略

### 策略 1：多会话并行 INSERT（Python 线程分片）

原理：Python 层开 N 个独立数据库连接，每个连接按 `cell_id % N = shard_id` 处理一个分片。

```python
import threading

def parallel_insert(sql, params, num_workers=8):
    def worker(shard_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql + f" AND cell_id % {num_workers} = {shard_id}", params)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_workers)]
    for t in threads: t.start()
    for t in threads: t.join()
```

- 适用：所有 5 个操作
- 优点：实现简单，每个分片独立
- 风险：表级锁竞争？索引维护瓶颈？需要测

### 策略 2：CTAS 替代 INSERT（利用 PG 并行 SELECT）

原理：`CREATE TABLE AS SELECT ...` 的 SELECT 部分可以用 PG 的并行 worker（最多 16 个）。先 CTAS 到临时表，再 `ALTER TABLE ... RENAME`。

```sql
DROP TABLE IF EXISTS rebuild5.enriched_records_new;
CREATE TABLE rebuild5.enriched_records_new AS
SELECT ... FROM rebuild5.path_a_records p;
-- PG 自动用并行 worker 扫描 path_a_records

DROP TABLE rebuild5.enriched_records;
ALTER TABLE rebuild5.enriched_records_new RENAME TO enriched_records;
```

- 适用：操作 A、B（纯 SELECT→INSERT）
- 优点：零代码改造，PG 原生并行
- 风险：CTAS 不能有索引/约束（需要后加），RENAME 有短暂不可用窗口
- 注意：当前 CTAS 在 PG17 上已验证可用并行（之前 profile_base 就是 CTAS）

### 策略 3：UNLOGGED TABLE 加速写入

原理：`CREATE UNLOGGED TABLE` 不写 WAL 日志，写入速度可提升 2-5 倍。中间表（sliding_window、metrics_window）不需要 crash recovery。

```sql
CREATE UNLOGGED TABLE rebuild5.cell_sliding_window (...);
```

- 适用：所有中间表（sliding_window、daily_centroid、metrics_window）
- 优点：直接提速，无需改逻辑
- 风险：PG crash 后数据丢失（中间表可以重算，可接受）
- 可与其他策略叠加

### 策略 4：PG 原生哈希分区表

原理：把目标表建成 `PARTITION BY HASH (cell_id)` 的分区表，PG 自动把 INSERT 分散到各分区，结合并行 worker 可能提速。

```sql
CREATE TABLE rebuild5.enriched_records (
    ...
) PARTITION BY HASH (cell_id);

CREATE TABLE rebuild5.enriched_records_p0 PARTITION OF rebuild5.enriched_records FOR VALUES WITH (MODULUS 8, REMAINDER 0);
CREATE TABLE rebuild5.enriched_records_p1 PARTITION OF rebuild5.enriched_records FOR VALUES WITH (MODULUS 8, REMAINDER 1);
...
```

- 适用：enriched_records、cell_sliding_window
- 优点：PG 原生支持，分区裁剪对下游查询也有加速
- 风险：分区管理复杂度，JOIN 性能影响？需要测

### 策略 5：COPY 协议批量加载

原理：`COPY ... FROM STDIN` 比 `INSERT INTO ... SELECT` 快得多（跳过 SQL 解析层）。先 SELECT 到 Python 内存/管道，再 COPY 写入。

```python
with get_conn() as conn:
    with conn.cursor() as cur:
        # 读
        cur.execute("SELECT ... FROM path_a_records")
        # 写（用 COPY 协议）
        with cur.copy("COPY enriched_records FROM STDIN") as copy:
            for row in cur:
                copy.write_row(row)
```

- 适用：操作 A、B
- 优点：写入速度最快
- 风险：需要在 Python 层做数据中转，内存消耗大；35M 行可能 OOM
- 变体：分片 + 多线程 COPY（每个线程 COPY 自己分片的数据）

### 策略 6：物化视图 + REFRESH CONCURRENTLY

原理：把 cell_metrics_window 定义为物化视图，用 `REFRESH MATERIALIZED VIEW CONCURRENTLY` 更新。

- 适用：操作 D
- 优点：PG 自动决定刷新策略
- 风险：需要 UNIQUE INDEX，CONCURRENTLY 可能不如直接重算快

---

## 测试方法

### 步骤 1：构建独立测试环境

从生产表抽 10% 数据到 `rebuild5_bench` schema：

```sql
CREATE SCHEMA IF NOT EXISTS rebuild5_bench;

-- 抽 ~358 万行（10%）
CREATE TABLE rebuild5_bench.path_a_records AS
SELECT * FROM rebuild5.path_a_records WHERE cell_id % 10 = 0;

CREATE TABLE rebuild5_bench.enriched_records AS
SELECT * FROM rebuild5.enriched_records WHERE cell_id % 10 = 0;

CREATE TABLE rebuild5_bench.cell_sliding_window AS
SELECT * FROM rebuild5.cell_sliding_window WHERE cell_id % 10 = 0;

-- 验证
SELECT
    (SELECT COUNT(*) FROM rebuild5_bench.path_a_records) AS path_a,
    (SELECT COUNT(*) FROM rebuild5_bench.enriched_records) AS enriched,
    (SELECT COUNT(*) FROM rebuild5_bench.cell_sliding_window) AS sliding;
```

### 步骤 2：每种策略跑基准

对每种策略：
1. 清空目标表
2. 计时执行
3. 验证行数和关键指标（COUNT、AVG）
4. 记录 CPU 利用率（`top` 看 postgres 进程数）

```python
import time

def benchmark(name, setup_fn, execute_fn, verify_fn):
    setup_fn()
    start = time.time()
    execute_fn()
    elapsed = time.time() - start
    correct = verify_fn()
    print(f"{name}: {elapsed:.1f}s {'✓' if correct else '✗ MISMATCH'}")
    return elapsed
```

### 步骤 3：策略对比矩阵

对每个操作（A/B/C/D/E），测试所有适用策略，输出对比表：

```
操作 A（enriched_records INSERT，358 万行样本）：
| 策略 | 耗时 | 加速比 | CPU 利用率 | 正确性 |
|------|------|--------|-----------|--------|
| 基线（单线程 INSERT） | 66s | 1.0x | 1 核 | ✓ |
| 策略 1: 8 线程分片 | ?s | ?x | ? | ? |
| 策略 2: CTAS + RENAME | ?s | ?x | ? | ? |
| 策略 3: UNLOGGED + 单线程 | ?s | ?x | ? | ? |
| 策略 1+3: UNLOGGED + 8 线程 | ?s | ?x | ? | ? |
| 策略 5: COPY 协议 | ?s | ?x | ? | ? |
```

### 步骤 4：最优策略确定后，测试并行度

只对最优策略测试并行度扫描（如果该策略支持并行度调节）：
- 测试 4/8/12/16/20/24 workers
- 找边际收益递减的拐点
- 确定生产推荐值

### 步骤 5：输出最终建议

```markdown
| 操作 | 推荐策略 | 推荐并行度 | 预期加速比 | 实测加速比 |
|------|---------|-----------|-----------|-----------|
| A: enriched INSERT | ? | ? | ? | ? |
| B: sliding_window INSERT | ? | ? | ? | ? |
| C: daily_centroids | ? | ? | ? | ? |
| D: cell_metrics | ? | ? | ? | ? |
| E: metrics UPDATE | ? | ? | ? | ? |
```

---

## 策略组合提示

不同策略可以叠加。例如：
- UNLOGGED + 多会话分片 = 最大化写入吞吐
- CTAS + UNLOGGED = 利用 PG 并行 SELECT + 跳过 WAL
- 分区表 + CTAS = 分区裁剪 + 并行

agent 应该探索这些组合，不要只测单一策略。

## 约束

1. **不改变业务逻辑**，只改执行方式
2. **数据正确性必须和单线程完全一致**（行数 + 关键指标）
3. **在 rebuild5_bench schema 测试**，不动生产数据
4. **测试完成后 `DROP SCHEMA rebuild5_bench CASCADE` 清理**
5. **服务器可用 20-28 核**给并行任务，其余留给 PG 后台和系统

## 相关文件

- `rebuild5/backend/app/core/database.py` — get_conn() 连接管理（psycopg, autocommit=True）
- `rebuild5/backend/app/enrichment/pipeline.py` — Step 4 `_insert_enriched_records()`
- `rebuild5/backend/app/maintenance/window.py` — Step 5 `refresh_sliding_window()`、`build_daily_centroids()`、`recalculate_cell_metrics()`、`_update_activity_metrics()`
- `rebuild5/backend/app/maintenance/pipeline.py` — Step 5 编排顺序
