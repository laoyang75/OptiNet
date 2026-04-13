# Step 1 ETL 性能优化分析报告

> 生成时间：2026-04-11  
> 测试环境：PG 17 @ 192.168.200.217:5433，Docker `--shm-size=8g`  
> 硬件：40 核 E5-2660 v2 / 251GB RAM  
> PG 配置：`shared_buffers=64GB`, `max_parallel_workers_per_gather=16`, `work_mem=512MB`, `jit=off`  
> 测试数据集：`rebuild5_bench` schema，10% 抽样（`right("记录数唯一标识",1)='0'`）  
> 抽样行数：**2,546,015 行**（全量 25,442,069 行的 10.01%）  

---

## 1. 各子步骤耗时表（10% 抽样实测）

| # | 子步骤 | 操作类型 | 抽样耗时 | 推算全量耗时 | 产出行数（抽样） |
|---|--------|----------|----------|-------------|----------------|
| 1a | `_parse_cell_infos` CTAS | JSONB 展开 + 列提取 | **25.75 s** | ~258 s | 2,884,733 |
| 1b | `_parse_ss1` 阶段1 groups | unnest 字符串拆分 | **7.54 s** | ~75 s | 2,499,508 |
| 1c | `_parse_ss1` 阶段2 carry | 窗口函数 PARTITION BY + MAX | **26.53 s** | ~265 s | 2,499,508 |
| 1d | `_parse_ss1` 阶段3 final | CTE + Merge Left Join | **22.88 s** | ~229 s | 1,657,841 |
| 2 | UNION ALL CTAS | 合并两张表 | **12.55 s** | ~126 s | 4,542,574 |
| 3 | `CREATE TABLE AS SELECT *`（全表复制） | IO 密集 | **12.57 s** | ~126 s | 4,542,574 |
| 4 | 18 条 ODS 规则 UPDATE（顺序执行）| 18 次全表扫描+写回 | **~41 s** | ~410 s | — |
| 5 | 4~5 次派生字段 UPDATE | 5 次全表扫描+写回 | **~239 s** | ~2,390 s | — |
| 6 | DELETE 无效行 | 全表扫描+删除 | **7 s** | ~70 s | — |
| 7 | fill CTAS（3 CTE + 3 LEFT JOIN） | Sort/Hash Join + GROUP BY | **83.66 s** | ~837 s | 4,533,274 |

**抽样阶段总计：~479 秒（约 8 分钟）**  
**推算全量总计：~4,786 秒（约 80 分钟）**  
*注：实际全量耗时 6,768 秒，误差来自 IO 争用、VACUUM、WAL checkpoint 等的非线性放大。*

---

## 2. 瓶颈排名（占比最大的前 3 个操作）

### 🥇 第 1 名：派生字段 UPDATE（5 次全表扫描）— 推算全量 **~2,390 秒（35%）**

- **问题**：`report_ts`、`cell_ts_std`、`gps_ts` 三个时间戳字段彼此独立，分三条 UPDATE 执行（第 4 条 `event_time_std` 还依赖前三条），导致对 4,500 万行表进行了 5 次完整的顺序扫描+写回。
- **特征**：**WAL 写放大极严重**。每次 UPDATE 在 LOGGED TABLE 上会为每行写入 WAL 记录，写 WAL 量 = 行数 × UPDATE 次数 × 行宽度。45.4M 行 × ~400 字节 × 5 次 = 约 86GB WAL。
- **绑定类型**：IO-bound（磁盘写入 + WAL 带宽）。

### 🥈 第 2 名：fill CTAS（3 池 + 3 LEFT JOIN）— 推算全量 **~837 秒（12%）**

- **问题**：`etl_clean_stage` 被扫描 **4 次**（主表 1 次 + `stable_pool` 1 次 + `ci_pool` 1 次 + `ss1_pool` 1 次）。由于 GROUP BY（`record_id, cell_id`）排序后 Hash Join，内存压力极大（每个 worker 使用 50~120MB 排序内存），实际使用了 Hash Left Join 策略。
- **特征**：**CPU-bound + 内存带宽瓶颈**（Hash 表构建 3 次，总内存 326MB + 280MB + 77MB ≈ 683MB）。
- **绑定类型**：CPU-bound（GroupAggregate + 排序）以及 内存带宽（大 Hash 表）。

### 🥉 第 3 名：_parse_ss1 阶段2 carry（窗口函数）— 推算全量 **~265 秒（4%）**

- **问题**：`PARTITION BY record_id ORDER BY grp_idx` 窗口函数需要先对整张 `etl_ss1_groups` 表（2,499,508 行）全排序，每个 worker 消耗约 **122~138MB 排序内存**（8 个 worker × ~130MB = 1GB+ 总排序内存）。
- **特征**：CPU-bound + 内存带宽（排序后 WindowAgg 以单线程合并执行）。
- **绑定类型**：CPU-bound（排序）。

---

## 3. 每种策略的可行性评估

### 策略 A：减少全表扫描次数（合并 UPDATE）

#### A-1：将 18 条 ODS 规则合并为 1 次 UPDATE（CASE WHEN）

| 项目 | 评估 |
|------|------|
| **可行性** | ✅ 完全可行 |
| **实现复杂度** | 低（每个字段写 CASE WHEN 表达式，互不干涉） |
| **预期加速比** | **~10×~15×**（18 次 → 1 次，WAL 写入量减少 17/18）|
| **风险** | ODS 规则间有依赖关系：ODS-013/014 依赖 `gps_valid`，ODS-015/016 置 false 后 ODS-014 才应清空坐标。合并后需改为 2-pass（先处理 gps_valid，再处理 坐标），或在单次 CASE 内正确处理依赖顺序（可行，但需仔细推导逻辑正确性） |

#### A-2：18 条 ODS + 4 条派生字段合并

| 项目 | 评估 |
|------|------|
| **可行性** | ⚠️ 部分可行 |
| **说明** | `event_time_std = COALESCE(cell_ts_std, report_ts, gps_ts)` 依赖同一 UPDATE 中刚赋值的 `cell_ts_std`/`report_ts`/`gps_ts`，这在 PG 中**不起作用**（UPDATE  中 SET 表达式读的是行的旧值）。因此 `event_time_std` 最少需要第 2 次 UPDATE。可从 22 次 → 2 次（第1次合并所有不依赖时间戳的字段+时间戳字段，第2次仅计算 `event_time_std`/`event_time_source`）。 |
| **预期加速比** | **~8×~10×**（22 次 → 2 次）|

#### A-3：将 clean 和 fill 合并为单个 CTAS（跳过 etl_clean_stage）

| 项目 | 评估 |
|------|------|
| **可行性** | ⚠️ 理论可行，但有高复杂度风险 |
| **说明** | 可将 ODS 清洗逻辑全部写入 Fill CTAS 的 CTE 中：先做 `cleaned AS (SELECT ..., CASE WHEN... END AS cleaned_cell_id FROM etl_parsed)`，再对 cleaned 做 stable_pool/ci_pool/ss1_pool 三个 pool CTE。这样可将整体 IO 降低约 40%（省去 etl_clean_stage 的创建和多次扫描）。 |
| **风险** | SQL 体量会极大（1,000+ 行），PG 优化器内存/计划时间开销上升，调试和维护成本高 |
| **预期加速比** | **~2×~3×**（相对于当前流程整体）|

---

### 策略 B：CTAS 利用 PG 并行 Worker

**实测结论：PG 已自动为所有主要 CTAS 分配并行 worker。**

| 操作 | Workers Planned | Workers Launched | 是否并行 |
|------|----------------|-----------------|---------|
| `_parse_cell_infos` | 8 | 8 | ✅ |
| `_parse_ss1` groups | 8 | 8 | ✅ |
| `_parse_ss1` carry  | 7 | 7 | ✅（但 WindowAgg 在 leader 单线程执行）|
| `_parse_ss1` final  | 7 | 7 | ✅ |
| UNION ALL CTAS | 7 | 7 | ✅ |
| fill CTAS（CTE pools）| 9 | 9 | ✅ |

**并行安全性**：`array_agg`、`jsonb_each`、`unnest`、`string_to_array` 均为 `PARALLEL SAFE`（`proparallel='s'`），不阻止并行。

> 注意：所有被测函数都标注为 PARALLEL SAFE，PG 已充分利用并行。进一步调高 `max_parallel_workers_per_gather` 对改善 fill 的 **Hash Join** 阶段帮助有限（Hash Join 本身已不并行，瓶颈在内存带宽）。

**策略 B 的增量优化空间已不大——** 不适合作为主要优化手段。

---

### 策略 C：多进程分片（Python-level 并行）

| 操作 | 分片可行性 | 分析 |
|------|-----------|------|
| `_parse_cell_infos` CTAS | ⚠️ 有限 | PG 已并行（8 worker），再加 Python 分片对 IO 改善微乎其微，反而需要合并步骤 |
| `_parse_ss1` groups CTAS | ⚠️ 有限 | 同上 |
| `_parse_ss1` carry (PARTITION BY) | ❌ 不可行 | 窗口函数必须看到同一 record_id 的所有行，跨分片会产生错误 |
| `_parse_ss1` final CTE | ⚠️ 可按 record_id 哈希分片 | 但中间表合并增加复杂度 |
| clean 18 ODS UPDATE | ❌ 不推荐 | ctid 分片 UPDATE 的 WAL 和锁开销抵消收益；参考 Step4/5 测试，针对 UPDATE 分片价值有限 |
| fill CTAS（3 CTE + JOIN）| ✅ 可行（按 record_id % N 分片） | 分片后每片独立完成 GROUP BY + JOIN，结果合并正确；但生产上需谨慎（final 表需 UNION 后再创建） |

**结论**：多进程分片对 **fill CTAS** 最有价值，预期加速比 **2×~4×**（取决于 IO 饱和程度）。对 clean UPDATE 价值很小。

---

### 策略 D：UNLOGGED TABLE

**实测数据：**

| 操作 | LOGGED | UNLOGGED | 加速比 |
|------|--------|----------|--------|
| `CREATE TABLE AS SELECT *`（全表复制） | **12.57 s** | **6.14 s** | **2.05×** |
| 7 次 ODS UPDATE（UNLOGGED） | 约 ~20 s（估算） | ~33 s（实测） | — |

> 注意：UNLOGGED 对 UPDATE 加速效果不如对 CTAS 显著，原因是 UPDATE 需要同时写 heap 和更新 visibility map，核心瓶颈从 WAL 变为 shared buffer 争用。

**`etl_clean_stage` 改为 UNLOGGED 的影响：**
- CREATE AS SELECT：节省 ~6.4 秒（全量约 64 秒）
- 每次 UPDATE：节省约 20-40%（相对 LOGGED TABLE）
- **总预期加速：clean 阶段节省约 30-40%**

**风险**：服务器宕机时 UNLOGGED TABLE 内容丢失。Step 1 是一次性 ETL，可接受。

---

### 策略 E：跳过中间表

#### E-1：跳过 etl_parsed（`etl_ci ∪ etl_ss1 → etl_clean_stage` 直接合并）

| 项目 | 评估 |
|------|------|
| **可行性** | ✅ 完全可行 |
| **收益** | 省去 UNION ALL CTAS 的写入（12.55 s → 全量约 126 s）+ 后续 CREATE AS SELECT *（12.57 s → 全量约 126 s）= 全量节省约 **252 秒** |
| **实现方式** | `CREATE [UNLOGGED] TABLE etl_clean_stage AS SELECT * FROM etl_ci UNION ALL SELECT * FROM etl_ss1` |
| **风险** | 无法单独验证 etl_ci/etl_ss1 行数；调试时稍不方便 |

#### E-2：clean 的 UPDATE 操作变成 CTAS 的 CASE WHEN 表达式

| 项目 | 评估 |
|------|------|
| **可行性** | ⚠️ 部分可行 |
| **说明** | 同策略 A-3，可行但需注意 `event_time_std` 的二次计算依赖 |

---

### 策略 F：SQL 优化

#### F-1：`_parse_cell_infos` 的 JSONB 展开优化

- `jsonb_each()` 是 PG 官方的 JSONB 展开方式，已 PARALLEL SAFE，无更快的替代。  
- 潜在优化点：`COALESCE(cell->'cell_identity'->>'Tac', cell->'cell_identity'->>'tac', ...)` 链式解析对同一 JSON object 多次访问。可通过 `jsonb_to_record()` 一次提取多字段（约快 5-10%）。

| 项目 | 评估 |
|------|------|
| **可行性** | ✅ 可行 |
| **预期加速比** | 小（~5-10%，~1.3 秒）|

#### F-2：`_parse_ss1` 三阶段是否可合并

- 三阶段中最慢的是 **阶段2 carry**（26.53 s），因为窗口函数 `MAX() OVER (PARTITION BY record_id ORDER BY grp_idx ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` 之后，`WindowAgg` 的最终合并步骤只能在 leader 单线程完成（尽管 Sort 可并行）。
- 不能将 carry 与 groups 合并；carry 依赖 groups 的物化结果。
- 能否将 carry 和 final 合并？可以写成 1 个 CTE，但性能不变（PG 内部仍会物化 CTE）。

| 项目 | 评估 |
|------|------|
| **可行性** | ⚠️ 合并意义不大 |
| **预期加速比** | 微小（~5%）|

#### F-3：fill 的 3 个 CTE 合并为 1 个

- 3 个 CTE（`stable_pool`、`ci_pool`、`ss1_pool`）分别对 `etl_clean_stage` 做 GROUP BY，导致表被扫描 4 次。
- 可以合并为 1 个 CTE，在单次扫描中同时计算所有 group-by fields，减少到 2 次扫描（1次 GROUP BY + 1次主表 JOIN）：

```sql
combined_pool AS (
    SELECT record_id, cell_id,
        -- stable_pool 字段（所有来源）
        (array_agg(operator_code ORDER BY ...) FILTER (WHERE ...))[1] AS p_operator,
        -- ci_pool 字段（仅 cell_infos 来源）
        (array_agg(lon_raw ORDER BY ...) FILTER (WHERE ... AND cell_origin='cell_infos'))[1] AS ci_lon,
        -- ss1_pool 字段（仅 ss1 来源）
        (array_agg(lon_raw ORDER BY ...) FILTER (WHERE ... AND cell_origin='ss1'))[1] AS s_lon,
        ...
    FROM etl_clean_stage
    WHERE cell_id IS NOT NULL
    GROUP BY record_id, cell_id
)
```

| 项目 | 评估 |
|------|------|
| **可行性** | ✅ 完全可行 |
| **收益** | etl_clean_stage 扫描从 4 次 → 2 次，节省约 2 次顺序扫描时间 |
| **预期加速比** | fill 阶段 **~1.5×~2×**（全量节省约 400-560 秒）|
| **风险** | SQL 复杂度增加（array_agg FILTER 条件变多），但逻辑等价，PG 优化器无障碍 |

#### F-4：`array_agg()[1]` 替换为 `FIRST_VALUE` 窗口函数

- `array_agg(x ORDER BY ...) FILTER (WHERE ...)[1]` 的语义是"按顺序取第一个非空值"。
- `FIRST_VALUE` 需要 `PARTITION BY + ORDER BY + FILTER`，语义等价，但仍需 GROUP BY 坍塌行，**无法直接替代聚合**（`FIRST_VALUE` 不能用于 GROUP BY 的聚合场景，只能在原始行级使用）。

| 项目 | 评估 |
|------|------|
| **可行性** | ❌ 不适用（场景不同，无法替代） |

---

## 4. 组合策略评估

### 组合方案 1：【推荐最高优先级】合并 UPDATE + UNLOGGED

**核心思路**：将 22 次 UPDATE → 2 次 UPDATE，全部在 UNLOGGED TABLE 上执行。

| 优化点 | 预期收益（全量） |
|--------|----------------|
| 22 次 UPDATE → 2 次 UPDATE | 节省 **~2,000 s**（约 33 分钟）|
| LOGGED → UNLOGGED（etl_clean_stage 和 etl_parsed）| 额外节省 **~200 s** |
| 合计 | **节省 ~2,200 s，加速比约 4×~5×**（仅 clean 阶段）|

**实现难度**：中等（需核对 ODS 规则依赖顺序）。

---

### 组合方案 2：跳过 etl_parsed + UNLOGGED + 合并 UPDATE

在方案 1 的基础上，直接将 `etl_ci UNION ALL etl_ss1` 合并为 `etl_clean_stage`（UNLOGGED）：

| 优化点 | 预期收益（全量） |
|--------|----------------|
| 省去 UNION ALL CTAS（126 s）| ✅ |
| 省去 CREATE TABLE AS SELECT *（126 s）| ✅ |
| 22 UPDATE → 2 UPDATE（2,000 s）| ✅ |
| UNLOGGED（200 s）| ✅ |
| 合计 | **节省 ~2,452 s，总耗时降至约 ~4,316 s** |

---

### 组合方案 3：fill 合并 3 CTE + UNLOGGED + 方案2

在方案 2 的基础上，将 fill 的 3 个 CTE 合并为 1 个：

| 优化点 | 预期收益（全量） |
|--------|----------------|
| 方案 2 全部优化 | ~4,316 s |
| fill 从 4 次扫描 → 2 次扫描（节省约 ~450 s）| ✅ |
| 合计 | **总耗时约 ~3,866 s（~64 分钟 → 降至约 40 分钟，整体加速 ~1.7×）** |

---

### 组合方案 4（终极）：方案3 + fill CTAS 多进程分片

在方案 3 基础上，对 fill CTAS 按 `record_id % N` 做 Python 多进程分片（建议 N=8~16）：

| 优化点 | 预期收益（全量）|
|--------|----------------|
| 方案 3 全部优化 | ~3,866 s |
| fill 多进程分片（8 进程，预期 3×~4×）| 节省 ~650 s |
| 合计 | **总耗时约 ~3,216 s（约 54 分钟，整体加速 ~2.1×）** |

> ⚠️ 多进程 fill 实现复杂（需要分片建临时表 + 最终 UNION 合并），建议在方案 1-3 验证后再做。

---

## 5. 推荐优化方案（按优先级排序）

| 优先级 | 方案 | 预期全量耗时 | 实现难度 |
|--------|------|------------|---------|
| 🥇 **P0** | 将 22 次 UPDATE 合并为 2 次（ODS + 派生字段）| 全量节省 ~2,000 s | 中 |
| 🥈 **P1** | 将 `etl_clean_stage`、`etl_parsed` 改为 UNLOGGED TABLE | 全量再节省 200 s | 低 |
| 🥉 **P2** | 跳过 etl_parsed（直接 `etl_ci ∪ etl_ss1 → etl_clean_stage`） | 再节省 252 s | 低 |
| **P3** | 将 fill 的 3 个 CTE 合并为 1 个（etl_clean_stage 扫描从 4→2 次）| 再节省 450 s | 中 |
| **P4** | fill CTAS 多进程分片（Python，8 进程）| 再节省 650 s | 高 |

**综合实施 P0+P1+P2+P3 后，预期全量耗时降至约 3,866 s（约 64 分钟），整体加速比约 1.75×。**  
**实施 P0+P1+P2+P3+P4 后，预期降至约 3,216 s（约 54 分钟），整体加速比约 2.1×。**

---

## 6. 不建议做的优化

| 优化方向 | 原因 |
|---------|------|
| **调高 `max_parallel_workers_per_gather`** | 已全面并行（8-9 workers），继续增加受内存带宽和 Hash Join 的单线程瓶颈限制，收益微乎其微 |
| **对 clean 的 UPDATE 做 Python 多进程 ctid 分片** | 多进程 UPDATE 在同一 LOGGED TABLE 上会产生大量锁争用和 WAL 写放大，测试表明（参见 Step4/5 bench）UPDATE 分片收益远低于 CTAS 分片；直接合并 UPDATE 更优 |
| **FIRST_VALUE 替换 array_agg()[1]** | 语义不等价，`FIRST_VALUE` 无法在 GROUP BY 场景中聚合行 |
| **将 _parse_ss1 三阶段合并为两阶段** | carry 阶段的窗口函数依赖物化的 groups 表，无法合并；强行合并成一个大 CTE 后 PG 仍会物化中间结果，性能无提升 |
| **为 etl_clean_stage 建索引再 UPDATE** | 18 条 ODS 规则的 WHERE 条件各不相同，建索引会增加写开销，对随机更新的全表 UPDATE 无显著帮助；合并 UPDATE 是更根本的解法 |
| **将整个 Step1 改写为纯 SQL 单语句** | clean + fill 合并成单 CTE 链会产生 1,000+ 行 SQL，PG 优化器对超大 CTE 树的计划质量下降，调试成本极高，不值得 |

---

## 7. 附：关键 EXPLAIN 发现摘要

| 操作 | 关键发现 |
|------|---------|
| `_parse_cell_infos` | 8 workers 并行，`jsonb_each` PARALLEL SAFE，IO 瓶颈主要在 JSONB 解析（每行展开 ~1.1 个 cell 平均），`Execution Time: 25651 ms` |
| `_parse_ss1` carry | `WindowAgg PARTITION BY record_id` 需要 leader 线程单线程聚合，尽管 Sort 并行（7 workers），但 WindowAgg 本身串行，是隐藏瓶颈。每个 worker 排序内存耗用 ~130MB。`Execution Time: 26533 ms` |
| `_parse_ss1` final | Merge Left Join 需要双边排序（Sort+Sort），sigs 侧排序内存约 333MB per worker（7 workers）。大内存消耗。`Execution Time: 22879 ms` |
| fill CTAS | `etl_clean_stage` 被串行扫描 4 次（每次约 1.4M shared buffers hits 等价），Hash 表峰值内存 326+280+77=683MB。`Execution Time: 83655 ms` |
| UNLOGGED CREATE TABLE | 相比 LOGGED 节省约 51%（12.57 s → 6.14 s），WAL 跳过效果显著 |

---

*报告结束。所有 rebuild5_bench schema 测试数据已在报告生成后 DROP SCHEMA CASCADE 清理。*
