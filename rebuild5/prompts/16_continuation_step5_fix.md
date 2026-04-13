# Step 5 继续修复 — 接力 Prompt

> 上一轮工作已完成 Step 1-4 的主流程修复和二轮数据运行。Step 5 仍有若干问题未完全解决。
> 本 prompt 用于新窗口接力，请先完整阅读再开始。

## 当前数据状态

数据库 192.168.200.217:5433, schema `rebuild5`, 数据集 `beijing_7d`

| 表 | 状态 |
|---|------|
| raw_gps | 25,442,069 行 ✅ |
| etl_cleaned | 45,314,465 行 ✅ |
| path_a_records (batch_id=2) | ~35,809,850 行 ✅（携带 donor_* 列） |
| enriched_records (batch_id=2) | 35,809,850 行 ✅ |
| trusted_snapshot_cell (batch_id=2) | 704,176 行 ✅ |
| candidate_cell_pool | 704,176 行 ✅（waiting + observing） |
| trusted_cell_library (batch_id=1) | 538,104 行 ✅（首轮） |
| trusted_cell_library (batch_id=2) | **需要重跑 Step 5** |
| trusted_bs_library (batch_id=2) | **需要重跑 Step 5** |
| trusted_lac_library (batch_id=2) | **需要重跑 Step 5** |
| cell_sliding_window | **需要重跑 Step 5（batch_id=2 数据已被清理）** |

## 需要修复的问题

### 问题 1：publish_bs_lac.py 参数数量不匹配（当前阻塞）

**文件**：`rebuild5/backend/app/maintenance/publish_bs_lac.py`
**错误**：`psycopg.ProgrammingError: the query has 8 placeholders but 7 parameters were passed`
**位置**：`publish_lac_library()` 函数

**原因**：上一轮把 LAC 发布从 `trusted_snapshot_lac` 改为从 `bs_agg` CTE 直接读时，去掉了 FROM 子句中的 `s.batch_id` 过滤参数，但 SQL 中其他地方可能还有残留的 `%s` 占位符。

**修复方式**：仔细数 SQL 中的 `%s` 数量和参数 tuple 的长度，确保一致。同时检查所有 `s.` 引用是否都已替换。

### 问题 2：Step 5 各子步骤耗时不透明

**现象**：Step 5 总耗时 1109 秒（18.5 分钟），不知道哪个子步骤最慢。

**已做**：在 `maintenance/pipeline.py` 中加了 `_tick()` / `_report()` 计时代码，但因为 BS/LAC 报错还没看到结果。

**下一步**：修完 BS/LAC 后跑一次，看每个子步骤的耗时分布。

### 问题 3：Step 5 产出表可能缺索引

**怀疑**：`trusted_cell_library`、`cell_sliding_window` 等表在被下游查询 JOIN 前没有索引，导致后续步骤（drift metrics、publish、collision）全部退化为全表扫描。

**需要检查**：
- `trusted_cell_library` 在 publish 完成后、collision 之前是否有索引（pipeline.py 第 103-104 行有，确认是否生效）
- `cell_sliding_window` 在 INSERT 完成后、daily_centroids 之前是否有索引（pipeline.py 第 81 行有）
- `enriched_records` 是否有 batch_id 索引（Step 4 之后没有显式建索引）

**修复方式**：确认每个 CTAS/INSERT 后都有对应索引，并在下次跑时验证索引被使用（EXPLAIN）。

### 问题 4：多进程并行的实际效果需要验证

**已做**：
- `core/parallel.py` 已重写为 multiprocessing + f-string 内联（解决了 psycopg `%` 转义问题）
- `enrichment/pipeline.py` 已改为 12 进程并行 INSERT
- `maintenance/window.py` 的 `refresh_sliding_window` 已改为 12 进程并行
- `build_daily_centroids` 和 `recalculate_cell_metrics` 改为利用 PG 内置并行 worker（CTAS/INSERT INTO SELECT）

**需要验证**：
- 跑 Step 5 时观察 `pg_stat_activity` 确认多连接同时活跃
- 对比有/无并行的耗时
- 确认 `recalculate_cell_metrics` 的半径 UPDATE 是否也用了并行

### 问题 5：BS/LAC 发布从 snapshot 改为从 library 读

**已做的修改**（可能不完整）：
- `publish_bs_library` 的 FROM 从 `trusted_snapshot_bs` 改为 `cell_agg`（从 `trusted_cell_library` 聚合）
- `publish_lac_library` 的 FROM 从 `trusted_snapshot_lac` 改为 `bs_agg`（从 `trusted_bs_library` 聚合）
- SELECT 列中的 `s.` 引用需要全部改为 `c.` 或 `ba.`

**为什么要改**：Step 3 snapshot 现在只含本轮候选（waiting/observing），qualified/excellent 走了 carry-forward 直接进 library。BS/LAC snapshot 看不到足够的 qualified cell，lifecycle_state 全是 observing，发布 count=0。

**修复方式**：彻底检查 `publish_bs_lac.py`，确保：
1. BS 从 `trusted_cell_library` 聚合，不依赖 `trusted_snapshot_bs`
2. LAC 从 `trusted_bs_library` 聚合，不依赖 `trusted_snapshot_lac`
3. 所有列引用正确，参数数量匹配

## 已完成的修复（不需要再做）

| # | 修复 | 文件 |
|---|------|------|
| 1 | 全局禁用并行已移除 | core/database.py |
| 2 | Docker shm-size=8GB | 远程服务器 |
| 3 | PG 配置优化（64GB shared_buffers, 16 parallel workers） | 远程服务器 |
| 4 | Step 2 Layer 3 碰撞压缩修复 | profile/pipeline.py |
| 5 | Step 2 bs_id 移除主键 | profile/pipeline.py |
| 6 | Step 3 候选池 + snapshot 语义修复 | evaluation/pipeline.py |
| 7 | Step 4 简单补数器（不 re-JOIN） | enrichment/pipeline.py + profile/pipeline.py |
| 8 | Step 5 连续窗口（不再 DROP） | maintenance/pipeline.py + window.py |
| 9 | Step 5 数据驱动时间基准（非 NOW()） | maintenance/window.py |
| 10 | Step 5 A 类碰撞补 tech_norm | maintenance/collision.py |
| 11 | Step 5 碰撞检测 multi_bs 预筛 + count=0 直接 return | maintenance/collision.py |
| 12 | Step 5 临时表索引策略 | maintenance/pipeline.py |
| 13 | ETL fill 三池模型 | etl/fill.py |
| 14 | 单源化收口 | etl/parse.py + source_prep.py + queries.py |
| 15 | 并行化框架（multiprocessing + f-string） | core/parallel.py |
| 16 | pressure 安全转换 | enrichment/pipeline.py |
| 17 | schema lac NOT NULL 修复 | maintenance/schema.py |
| 18 | cell_anomaly_summary PK NOT NULL 修复 | maintenance/cell_maintain.py |

## 执行建议

1. **先修 publish_bs_lac.py 的参数问题**（问题 1+5），让 Step 5 能跑通
2. **跑一次完整 Step 5**，看子步骤计时报告（问题 2）
3. **根据计时报告确认索引是否生效**（问题 3）
4. **验证并行效果**（问题 4）
5. 如果某个子步骤仍然很慢，按 `rebuild5/prompts/15_parallel_optimization.md` 的策略优化

## 相关文件

- `rebuild5/backend/app/maintenance/pipeline.py` — Step 5 编排（含计时代码）
- `rebuild5/backend/app/maintenance/publish_bs_lac.py` — BS/LAC 发布（**当前有 bug**）
- `rebuild5/backend/app/maintenance/window.py` — 窗口计算（已并行化）
- `rebuild5/backend/app/maintenance/collision.py` — 碰撞检测（已优化）
- `rebuild5/backend/app/maintenance/publish_cell.py` — Cell 发布
- `rebuild5/backend/app/core/parallel.py` — 并行执行器
- `rebuild5/docs/dev/runbook_execution_issues.md` — 性能问题记录
- `rebuild5/docs/fix/step4_step5_parallel_optimization.md` — 并行优化测试报告
- `rebuild5/prompts/15_parallel_optimization.md` — 并行优化探索需求
- `rebuild5/scripts/runbook_beijing_7d.md` — 运行手册

## 环境检查

```sql
-- 确认 PG 配置
SELECT name, setting FROM pg_settings 
WHERE name IN ('shared_buffers', 'max_parallel_workers_per_gather', 'work_mem', 'jit');

-- 确认 Docker
-- ssh root@192.168.200.217 (密码 111111)
-- docker inspect pg17-test --format '{{.HostConfig.ShmSize}}'
```
