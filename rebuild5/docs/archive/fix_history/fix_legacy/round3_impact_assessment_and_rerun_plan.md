# Round 3 影响评估与重跑建议

更新时间：2026-04-11

## 结论摘要

- `Step 1` 可以保留，不需要因为本轮发现的问题回滚或重跑。
- 建议的 clean rerun 起点是 `Step 2`，不是 `Step 1`。
- 需要明确重跑的范围是 `Step 2 → Step 5`，并且要按轮次顺序重放，不建议只补跑单个表。
- 这次发现的问题里，既有纯性能问题，也有会影响“多轮数据设计流程正确性”的问题；后者必须在文档和重跑计划里单独说明。

## Step 1 是否需要重跑

当前判断：`不需要`。

依据：

- 最新 `Step 1` 产物稳定存在：
  - `raw_gps = 25,442,069`
  - `etl_cleaned = 45,314,465`
- 本轮修复和定位的问题全部发生在 `Step 2/3`、`Step 4`、`Step 5` 的路由、候选池、补数、维护与发布阶段。
- 当前没有发现 `Step 1` 输入、解析、清洗、填充逻辑会导致后续 bug 的证据。
- 因此后续 clean rerun 可以直接复用现有 `Step 1` 产物，避免重复耗时。

只有在以下情况才建议重跑 `Step 1`：

- 需要做一次“从原始输入到最终发布”的全链路冷启动验收
- `etl_cleaned` 或 `raw_gps` 被人工改写
- 后续又发现 `Step 1` 规则本身存在数据质量问题

在当前证据下，不需要为了这次修复去优化或重跑 `Step 1`。

## 数据正确性影响评估

## 设计归类

本轮发现的问题，按“逻辑设计 vs 实现偏离”分类如下：

### A. Step 3 snapshot 缺少已发布域 carry-forward

归类：`实现偏离设计`

依据：

- 设计文档要求 Step 3 的 `trusted_snapshot_t` 是“候选域评估结果 + 已发布域继承展示”的完整冻结视图
- 进一步澄清后，正确口径是：
  - Cell：对已发布域做 carry-forward 展示
  - BS / LAC：基于“最终 Cell 视图”重新上卷，而不是各自逐行继承上一版发布状态
- 见 `rebuild5/docs/03_流式质量评估.md`
  - Step 3 仅对候选域重评估，但“已发布对象仅做继承展示”：第 3-5 行
  - `trusted_snapshot_t` 需要保持当前批次完整一致视图：第 44-46 行
  - `trusted_snapshot_t` 的表定义粒度是 `Cell / BS / LAC`：第 617-620 行
- 当前实现的 `build_current_cell_snapshot()` 只合并了 `profile_base + candidate_cell_pool + collision_id_list`
- 见 `rebuild5/backend/app/evaluation/pipeline.py`
- `all_candidates` 只来自 `profile_base` 和 `candidate_cell_pool`：第 96-135 行

结论：

- 这不是文档逻辑缺失，而是代码没有把“已发布域继承展示”实现进去。

### B. Step 5 BS/LAC 直接依赖 snapshot

归类：`实现偏离设计`

依据：

- Step 5 文档明确规定 BS 维护建立在下属 Cell 的维护结果之上，LAC 维护建立在 BS 级聚合结果之上
- 见 `rebuild5/docs/05_画像维护.md`
  - BS 维护完全建立在下属 Cell 维护结果之上：第 487-499 行
  - LAC 维护输入窗口是 BS 级单条聚合记录：第 577-597 行
  - Step 5 输出到自身的是更新后的 `trusted_*_library`：第 813-845 行
- 当前错误实现曾沿用旧 snapshot 口径做 BS/LAC 发布，导致看不到 carry-forward 进入的 published cell

结论：

- 这里的问题不是 Step 5 逻辑设计错了，而是代码仍按旧实现路线取数。

### C. `collision_id_list` 多批重复导致 candidate pool upsert 失败

归类：`纯实现 bug`

依据：

- 文档把 `collision_id_list` 定义为 Step 3 的 `cell_id` 级只读参考表
- 见 `rebuild5/docs/03_流式质量评估.md`
  - 参考输入是 `collision_id_list`：第 17 行
  - 表粒度是 `cell_id` 级：第 617-618 行
- 逻辑上它在 Step 3 中应当被当作“冲突 cell_id 集合”消费
- 当前实现没有去重，导致跨 batch 同一个 `cell_id` 扩张成重复输入

结论：

- 这是 SQL 实现细节错误，不是架构或规则定义错误。

### D. Step 2/3、Step 4、Step 5 的慢 SQL

归类：`执行/物理设计问题`

说明：

- 这些问题主要体现在：
  - logged 大表写入产生 WAL / extend 锁
  - 中间表构建阶段 autovacuum 抢占资源
  - `INSERT + UPDATE + UPDATE` 比一次性 `CTAS` 更重
- 它们影响吞吐和稳定性，但不改变业务逻辑定义

结论：

- 这类问题需要优化，但不属于“逻辑设计错了”。

### 1. Step 5 BS/LAC 发布逻辑错误

影响级别：`高`

类型：`影响数据设计流程`

问题：

- `rebuild5/backend/app/maintenance/publish_bs_lac.py`
- BS/LAC 发布仍然沿用旧的 `snapshot` 语义，但 Step 3 的 snapshot 现在只保存“本轮候选评估结果”，大量已发布 cell 通过 carry-forward 直接进入 `trusted_cell_library`
- 结果是 BS/LAC 从 snapshot 读时，看不到完整的 qualified cell / BS 集合

影响：

- `batch_id=2` 的 `trusted_bs_library` / `trusted_lac_library` 结果不可信
- 这不是单纯的程序报错，而是“设计流转点已变、下游仍按旧语义取数”的问题
- 必须在重跑说明里明确标注为“影响多轮数据设计流程”

修复：

- BS 改为从 `trusted_cell_library` 聚合
- LAC 改为从 `trusted_bs_library` 聚合
- 同时修掉了 LAC SQL 参数数量不匹配的阻塞 bug

### 2. Step 3 候选池 upsert 在多轮运行时会失败

影响级别：`高`

类型：`影响数据设计流程`

问题：

- `rebuild5/backend/app/evaluation/pipeline.py`
- `_snapshot_current_cell` 构建时，`collision_flags` 从整张 `collision_id_list` 读取 `cell_id`
- `collision_id_list` 是跨批次累积的，同一个 `cell_id` 在多个 batch 中会重复出现
- 原实现没有 `DISTINCT`，导致 `_snapshot_current_cell` 在多轮运行里产生重复 key
- 进一步导致 `candidate_cell_pool` 的 `ON CONFLICT DO UPDATE` 触发二次命中并直接失败

影响：

- 第三轮最初就是在这里失败
- 问题只在“第二轮以后”才暴露，因此它是典型的“多轮设计流程 bug”
- 这类 bug 不一定会污染已完成批次，但会阻断后续轮次运行

修复：

- `collision_flags` 改为 `SELECT DISTINCT cell_id`

### 3. 第三轮 Step 5 首次尝试被人工终止

影响级别：`中`

类型：`影响当前批次完整性`

问题：

- 第三轮第一次 Step 5 尝试在 `trusted_bs_library` 发布阶段长时间运行
- 由于本地执行链断开，数据库端留下了失控后台查询，后续已被终止

影响：

- `batch_id=3` 的 `trusted_cell_library` 已经写入
- 但当时的 `trusted_bs_library` / `trusted_lac_library` 没有完整收口
- 该次 Step 5 尝试不能视为完整结果

处理：

- 已终止失控后台进程
- 需要重新执行修复后的 `Step 5`

## 纯性能问题评估

这些问题不会改变业务含义，但会显著拉长耗时，进而提高中途失败和部分结果残留的风险。

### 1. Step 5 `daily_centroids` / `cell_metrics` 执行方式偏慢

问题：

- 原实现是 `INSERT INTO ... SELECT`，随后再对 `cell_metrics_window` 做半径和活跃度回写
- 对大表来说，这意味着更多 WAL、更多回写、更多阶段性扫描

已实施优化：

- `rebuild5/backend/app/maintenance/window.py`
- `cell_daily_centroid` 改为 `UNLOGGED CTAS`
- `cell_metrics_window` 改为一次性 `UNLOGGED CTAS`
- 将主聚合、半径计算、活跃度计算合并进一次建表流程

验证：

- 小样本 `Step 5` 全链路可跑通
- 1% bench 样本上，`CTAS` 在 `5b/5c` 上稳定优于当前分片插入方案

### 2. Step 2/3 中间表 WAL 和 autovacuum 压力偏大

问题：

- `path_a_records`、`_profile_path_a_candidates`、`_profile_path_b_cells`、`profile_obs`、`profile_base` 等都是可重算中间表
- 但原实现使用普通 logged table，CTAS 和索引阶段会产生较重 WAL / autovacuum 压力

已实施优化：

- `rebuild5/backend/app/profile/pipeline.py`
- 上述中间表统一改为 `UNLOGGED TABLE AS`
- 对这些中间表显式关闭 `autovacuum_enabled`

### 3. Step 4 并行写入存在 extend 锁竞争

问题：

- 第三轮 `Step 4` 运行时，多个并行 `INSERT INTO rebuild5.enriched_records` backend 出现明显 `extend` 锁等待
- 这说明高并发写入同一 logged 表时，文件扩展和 WAL 成本明显

已实施优化：

- `rebuild5/backend/app/enrichment/schema.py`
- `enriched_records` / `gps_anomaly_log` 改为 `UNLOGGED`
- 对 `enriched_records` / `gps_anomaly_log` 显式关闭 `autovacuum_enabled`

### 4. 中间表构建过程中 autovacuum 会抢占资源

问题：

- 实际运行中多次观察到 `autovacuum: VACUUM ANALYZE rebuild5.path_a_records`
- 以及 `autovacuum: VACUUM ANALYZE rebuild5.cell_sliding_window`
- 其中前者属于典型“临时大表刚建好就被 autovacuum 介入”，会干扰当前轮次执行

处理策略：

- 对 `Step 2/3`、`Step 4`、`Step 5` 中会整轮重建的中间表，关闭 autovacuum
- `cell_sliding_window` 仍保持默认 autovacuum，因为它是跨轮次持久窗口，不属于一次性中间表

备注：

- 当前没有把 `cell_sliding_window` 改成 `UNLOGGED`
- 原因是它是跨轮次持久窗口，不是纯临时表；若数据库异常重启，`UNLOGGED` 会直接丢窗口历史
- 因此这里优先保留正确性和恢复语义

## 已完成修复/优化清单

- `rebuild5/backend/app/maintenance/publish_bs_lac.py`
  - 修复 LAC 参数数不匹配
  - BS/LAC 改为从 library 聚合
- `rebuild5/backend/app/evaluation/pipeline.py`
  - `collision_flags` 改为 `DISTINCT cell_id`
  - `_snapshot_current_cell`、`_snapshot_bs_*`、`_snapshot_current_*` 改为 `UNLOGGED`
- `rebuild5/backend/app/profile/pipeline.py`
  - `path_a_records`、`profile_base` 等大中间表改为 `UNLOGGED`
  - 对重建型中间表关闭 autovacuum
- `rebuild5/backend/app/enrichment/schema.py`
  - `enriched_records`、`gps_anomaly_log` 改为 `UNLOGGED`
  - 对中间输出表关闭 autovacuum
- `rebuild5/backend/app/maintenance/window.py`
  - `cell_daily_centroid` 改为 `UNLOGGED CTAS`
  - `cell_metrics_window` 改为一次性 `UNLOGGED CTAS`
  - 对 `cell_daily_centroid` / `cell_metrics_window` 关闭 autovacuum
- `rebuild5/tests/test_publish_bs_lac.py`
  - 增加 BS/LAC SQL 参数与数据源回归测试
- `rebuild5/scripts/test_step5_small_sample.py`
  - 增加 Step 5 隔离小样本集成验证脚本

## 当前批次状态

### Step 1

- 当前产物可保留

### Batch 2

- `trusted_cell_library(batch_id=2)` 存在
- `trusted_bs_library(batch_id=2)` / `trusted_lac_library(batch_id=2)` 不能作为最终可信结果使用
- 原因是发布逻辑错误属于设计流转问题

### Batch 3

- `Step 2/3` 已在修复后重新跑通
- `Step 4` 已完成
- `Step 5` 首次尝试无效，因为中途失控并被终止
- 需要重新执行修复后的 `Step 5`

## 推荐重跑策略

推荐方案：`保留 Step 1，清空 Step 2 → Step 5 产物后，按轮次顺序 clean rerun`

原因：

- `Step 1` 当前没有证据显示结果有问题
- 本轮数据正确性问题集中在 `Step 2/3` 和 `Step 5`
- 这些阶段又都带有跨轮次状态（`candidate_cell_pool`、`trusted_*_library`、`collision_id_list`、`cell_sliding_window`）
- 因此不建议只补单个表，更不建议在现有批次状态上“局部拼补”

建议清理对象：

- `candidate_cell_pool`
- `trusted_snapshot_cell` / `trusted_snapshot_bs` / `trusted_snapshot_lac`
- `snapshot_diff_cell` / `snapshot_diff_bs` / `snapshot_diff_lac`
- `path_a_records`
- `profile_obs` / `profile_base` 及 `_profile_*` 中间表
- `enriched_records` / `gps_anomaly_log`
- `trusted_cell_library` / `trusted_bs_library` / `trusted_lac_library`
- `collision_id_list`
- `cell_sliding_window` / `cell_daily_centroid` / `cell_metrics_window` / `cell_anomaly_summary`
- `step2_run_stats` / `step3_run_stats` / `step4_run_stats` / `step5_run_stats`

保留对象：

- `raw_gps`
- `raw_lac`
- `etl_cleaned`
- `step1_run_stats`

## 审查后建议执行顺序

在你审查完本文件并确认后，建议按以下顺序执行：

1. 保留 `Step 1` 产物
2. 清空 `Step 2 → Step 5` 产物
3. 从 `Step 2/3` 开始跑首轮
4. 接着跑 `Step 4`
5. 跑 `Step 5`
6. 再跑第二轮 `Step 2 → Step 5`
7. 最后跑第三轮 `Step 2 → Step 5`

## 审查关注点

建议重点审查以下两类问题：

- 是否属于“影响设计流程”的问题
  - `publish_bs_lac.py` 的 library/snapshot 语义错位
  - `collision_flags` 跨批次重复导致的 Step 3 upsert 失败
- 是否只属于性能问题
  - `window.py` 的建表方式
  - `UNLOGGED` 带来的 WAL 压力下降

如果你确认这两类划分成立，那么后续就不需要回头优化 `Step 1`。
