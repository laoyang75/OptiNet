# 样例速度优化评估 Prompt

你在 `/Users/yangcongan/cursor/WangYou_Data` 中执行一轮 **rebuild5 样例速度优化评估**。

这是一轮独立优化工作，目标是：

1. 先在样例库上跑出**当前代码**的真实基线
2. 找出真正的性能热点
3. 对各个热点都可以尝试优化
4. 优化后必须重新跑样例并和基线结果对比
5. 最终判断是继续做持续优化，还是转向结构性重构

## 一、任务边界

本轮只在**样例数据**上工作，不直接动正式全量库。

### 明确不做

1. 不直接跑正式全量数据
2. 不把未经验证的优化直接带入正式库

### 可以做

1. 可以优化任意热点步骤
2. 可以同时优化多个步骤
3. 可以尝试 SQL 结构调整、索引、分阶段物化、减少重复计算、并行策略、临时中间表方案
4. 可以使用 **MCP PG17** 直接做数据库对象检查、统计和 SQL 试验
5. 如果确实需要轻微改动实现结构，也可以做，但必须保住当前业务结果

### 结果底线

优化可以很激进，但必须满足：

1. 不把业务语义改坏
2. 样例结果必须和当前基线对齐，或能明确解释差异且确认差异不是回归

补充原则：

1. **工程问题和研究问题必须分开处理。**
2. 本轮以工程问题为主：
   - 慢在哪
   - 为什么慢
   - 怎么把它变快
3. 如果在优化过程中发现新的研究问题（例如分类边界、业务口径、对象语义），必须单独记录，不要混进本轮工程优化结论。

## 二、必须先掌握的背景

### 1. 总流程文档

先读：

- `rebuild5/docs/处理流程总览.md`
- `rebuild5/docs/runbook_v5.md`

这两份文档决定：

1. Step1-5 的职责边界
2. 当前有效的业务主线
3. 当前样例验证口径

### 2. 当前已确认的业务前提

这些逻辑视为已确认，优化时默认不能改坏：

1. Step3 生命周期：
   - `waiting`: `independent_obs < 3`
   - `observing`: `3 <= independent_obs < 10`
   - `qualified`: `independent_obs >= 10`
   - `excellent`: `independent_obs >= 30`
2. Step4 donor：
   - donor 由 Step2 确认
   - Step4 不再对 `anchor_eligible` 做 donor 二次门槛
3. GPS / 质心：
   - 保留当前主热点 seed + 核心点过滤逻辑
   - Step2 和 Step5 都已接入

说明：
- 你不是不能碰代码，而是不能把这些业务结论改坏。
- 如果某个优化会导致结果变化，必须单独证明这是正确变化而不是性能回归带来的行为偏差。

## 三、样例数据、数据库与运行方式

### 样例库

- 数据库：`ip_loc2_fix4_codex`
- 输入表：`rebuild5_fix4_work.etl_cleaned_shared_sample_local`
- 日期范围：`2025-12-01 ~ 2025-12-03`

### 环境变量

```bash
export REBUILD5_PG_DSN='postgresql://postgres:123456@192.168.200.217:5433/ip_loc2_fix4_codex'
```

### 推荐数据库评估工具

本轮推荐优先使用：

- MCP `PG17`

推荐用途：

1. 查表结构
2. 查索引
3. 查行数
4. 查阶段表规模
5. 跑小而清晰的 SQL 评估语句

不推荐用途：

1. 一次性拼很长的超大 SQL
2. 把多个热点混在一个复杂查询里一起评估
3. 写一个不易调试的大 CTE 来“顺便”证明多个问题

原则：

- **SQL 要小、清晰、可调试、可重复。**
- 一次只回答一个问题。
- 如果一个大 SQL 难以解释执行代价或难以定位瓶颈，就应该拆开。

### 步骤 0：先验证环境连通性

```bash
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex -c "SELECT 1"
```

如果无法连接，优化工作只能停留在代码审查层，不能继续跑样例。

### 步骤 1：判断当前数据库状态

先执行：

```sql
SELECT COALESCE(MAX(batch_id), 0) AS max_batch FROM rebuild5_meta.step5_run_stats;
```

### 当前状态解释

| 结果 | 当前状态 | 正确动作 |
|---|---|---|
| `max_batch = 3` | 库里已有历史落表结果 | **只能作为参考值，不能直接当当前基线** |
| `max_batch < 3` 或 `0` | 空库或不完整 | 必须先跑一遍当前基线 |

补充要求：

1. 即使 `max_batch = 3`，如果当前工作区代码已经变化，历史 `step*_run_stats` 也只能视为旧参考。
2. 当前优化前的**有效基线**，应该由当前代码重新在样例库跑出来。

### 样例运行入口

重置：

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable \
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

重跑：

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-01 \
  --end-day 2025-12-03
```

## 四、当前历史参考基线

以下基线是**历史参考值**，作用是帮助你快速识别热点，不应默认视为当前代码的真实基线。

当前代码如果已经有新的改动，必须先按本 prompt 重新跑出“当前基线”。

### 1. 历史参考耗时

| batch | 输入记录 | Step2 | Step3 | Step4 | Step5 | batch_total |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 293,206 | 15.182s | 6.933s | 0.642s | 14.055s | 48.114s |
| 2 | 293,800 | 13.434s | 6.640s | 5.010s | 28.472s | 64.902s |
| 3 | 271,604 | 12.442s | 6.676s | 5.116s | 65.737s | 102.620s |

### 2. 当前结果基线

当前应以这组结果作为样例正确性的基线：

`batch1`
- Step2: `pathA=0`, `pathB=292,872`, `pathB_cell=13,490`, `pathC=334`
- Step3: `waiting=3,275`, `qualified=3,807`, `excellent=1,939`, `anchor=0`
- Step4: `pathA=0`, `donor_matched=0`, `gps_filled=0`, `gps_anomaly=0`
- Step5: `published_cell=5,746`, `published_bs=3,124`, `published_lac=18`, `multi_centroid=0`, `dynamic=0`

`batch2`
- Step2: `pathA=235,711`, `pathB=57,905`, `pathB_cell=7,672`, `pathC=184`
- Step3: `waiting=2,816`, `qualified=6,337`, `excellent=2,084`, `anchor=1,976`
- Step4: `pathA=235,711`, `donor_matched=235,711`, `gps_filled=14,362`, `gps_anomaly=6,450`
- Step5: `published_cell=8,421`, `published_bs=4,115`, `published_lac=21`, `multi_centroid=0`, `dynamic=0`

`batch3`
- Step2: `pathA=247,441`, `pathB=23,953`, `pathB_cell=4,748`, `pathC=210`
- Step3: `waiting=2,536`, `qualified=7,674`, `excellent=2,120`, `anchor=2,886`
- Step4: `pathA=247,441`, `donor_matched=247,441`, `gps_filled=15,161`, `gps_anomaly=7,108`
- Step5: `published_cell=9,794`, `published_bs=4,563`, `published_lac=21`, `multi_centroid=113`, `dynamic=0`

## 五、当前已知热点

当前已知热点只是起点，不是限制。

### 已观察热点

1. `batch3 Step5` 明显偏高
2. `collision` 阶段在某些轮次会跳高
3. `metrics_radius` 也是稳定热点

### 历史上最强的一条线索

历史参考里，`batch3 Step5 = 65.737s`，比 `batch2` 的 `28.472s` 几乎翻倍。

已知相关事实：

- batch3 首次出现 `multi_centroid=113`
- batch3 `published_cell` 从 `8,421` 增加到 `9,794`

优先检查：

- `rebuild5/backend/app/maintenance/collision.py`
- `rebuild5/backend/app/maintenance/window.py`
  - `build_cell_radius_stats()`
  - `build_daily_centroids()`
- `rebuild5/backend/app/maintenance/publish_bs_lac.py`

注意：
- 这只是历史线索，不是定论。
- 优化前必须用当前代码跑出基线并验证热点是否仍然存在。

## 六、推荐工作方式

### 阶段 A：先跑当前基线

你必须先在样例库跑一次**当前代码下的完整基线**，不要直接开改。

至少拿到：

1. 每轮总时长
2. Step2 / Step3 / Step4 / Step5 时长
3. Step5 子步骤时长
4. 当前结果是否与预期业务结果一致

#### 获取 Step5 子步骤时长

优先方式：

- 如果当前日志已经输出 `Step 5 子步骤耗时`，直接读日志

备选方式：

- 在 `rebuild5/backend/app/maintenance/pipeline.py` 各子步骤调用处临时加 `time.perf_counter()` 计时
- 记录后还原

### 阶段 B：定位热点

对每个热点分别判断：

1. 是 SQL 结构问题
2. 是缺索引
3. 是重复扫描
4. 是重复排序
5. 是不必要的字段计算
6. 是并行策略问题
7. 是数据规模放大后设计本身不适合

补充要求：

- 这一阶段优先解决工程问题。
- 如果发现是业务研究问题（例如“多质心分类边界可能不合理”），单列到“研究问题”章节，不要把它当作当前性能结论的一部分。

### 阶段 C：逐项优化

可以尝试：

1. 删除无消费字段
2. 合并重复 `PERCENTILE_CONT`
3. 将大 CTE 拆阶段表
4. 将重复距离表达式前置
5. 加索引
6. 改并行度
7. 先做候选收缩再重算
8. 针对特定热点做临时中间表

注意：

- 候选收缩如果会改变业务口径，先视为研究问题，不要直接和工程优化混做。
- 当前更优先的是：
  - 拆 SQL
  - 减重复算
  - 减重复扫
  - 降排序成本
  - 用阶段表替代超大单 SQL

### 阶段 D：重新跑样例并完整验证

优化后必须执行以下完整验证流程：

**第一步：重置数据库**

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable \
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2_fix4_codex \
  -f rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
```

**第二步：运行单元测试**

```bash
pytest rebuild5/tests/test_pipeline_version_guards.py \
       rebuild5/tests/test_profile_logic.py \
       rebuild5/tests/test_publish_bs_lac.py \
       rebuild5/tests/test_publish_cell.py \
       rebuild5/tests/test_maintenance_queries.py \
       rebuild5/tests/test_enrichment_queries.py
```

**第三步：重跑样例 batch1-3**

```bash
python3 rebuild5/scripts/run_daily_increment_batch_loop.py \
  --input-relation rebuild5_fix4_work.etl_cleaned_shared_sample_local \
  --start-day 2025-12-01 \
  --end-day 2025-12-03
```

**第四步：对比结果**

对比：

1. 每轮总时长
2. Step2-5 分段时长
3. Step5 子步骤时长
4. 关键结果数字

### 阶段 E：形成优化结论

优化后你必须回答：

1. 当前热点是否已被压下去
2. 新的最重热点在哪
3. 这轮优化属于：
   - 持续性小优化
   - 还是已经逼近结构性改造边界

## 七、结果对比要求

速度优化不是只看“变快了”，必须同时看“结果有没有变”。

### 至少对比这些结果

1. Step2
   - `pathA`
   - `pathB`
   - `pathB_cell`
   - `pathC`
2. Step3
   - `waiting`
   - `qualified`
   - `excellent`
   - `anchor`
3. Step4
   - `donor_matched`
   - `gps_filled`
   - `gps_anomaly`
4. Step5
   - `published_cell`
   - `published_bs`
   - `published_lac`
   - `multi_centroid`
   - `dynamic`

### 结果容差定义

| 字段类型 | 容差 | 说明 |
|---|---|---|
| 整数计数类（`pathA/B/C`、`waiting/qualified/excellent/anchor`、`donor_matched`、`published_cell/bs/lac`、`multi_centroid`、`dynamic`） | **严格一致，偏差视为回归** | 核心业务计数，不允许误差 |
| GPS 相关（`gps_filled`、`gps_anomaly`） | ±0.1% 以内可接受 | 仅允许因浮点计算顺序导致的极微量差异，必须说明原因 |

### 结果判定

| 情况 | 结论 |
|---|---|
| 时长下降，所有计数类字段严格一致 | 可接受优化 |
| 时长下降，GPS 类字段有 ±0.1% 内偏差，且有明确解释 | 需要在产出文档中单独说明 |
| 时长下降，但计数类字段对不上，且无法解释 | 视为回归，不得合入 |
| 时长下降，结果差异经分析确认是业务更合理的修正 | 需要单独证明并在产出文档中说明 |

补充要求：

- 如果优化改变了结果分布，必须在报告中单列“行为变化说明”。
- 如果做了多个优化，必须说明是哪个优化导致了结果变化。

## 八、必须产出

至少产出到：

- `rebuild5/docs/速度优化评估_claude.md`

内容至少包括：

1. 当前代码基线
2. 热点排序
3. 每个热点的根因判断
4. 尝试过的优化
5. 优化后的时长对比
6. 优化后的结果对比
7. 单独列出“研究问题（不在本轮解决）”
8. 结论：继续做持续优化，还是转向结构性重构

## 九、最终判断标准

本轮优化工作的结论必须回答：

1. 当前代码是不是还能继续做小步优化
2. 还有没有明显低风险收益点
3. 如果收益已经接近极限，是否应转向：
   - 分表
   - 中间结果持久化
   - 热点表结构重构
   - 更明确的离线维护表设计

## 十、优先起手顺序

建议起手顺序：

1. 先跑当前基线
2. 先看 Step5
3. 再看 Step2/3/4
4. 优化后重新跑样例
5. 再决定要不要进入结构性重构

## 十一、规模放大测试（双倍数据集 · 从 Step1 起跑）

> 进入时机：必须在前十节的现有样例优化全部完成、产出文档落地后，才进入本节。

本节是复合验证阶段，目标是：

1. 从原始库补充数据，构建双倍规模的新测试数据集
2. 新数据集从 Step1 开始完整跑全链路（Step1 → Step5）
3. 评估当前优化在放大规模下是否依然有效，还是出现性能退化

### 11.1 前提条件

- 现有样例优化已完成，`rebuild5/docs/速度优化评估_claude.md` 已落地
- 原始 raw_gps 库可访问
- 新数据集必须使用独立数据库，不能覆盖现有 `ip_loc2_fix4_codex`
