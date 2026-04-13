# Step 5 结构优化方案

> 本文档基于当前代码和设计文档，给出 Step 5 的结构性优化建议。
> 完成当前轮修复后，按本文档单独执行。

## 一、当前问题

Step 5 围绕 `cell_metrics_window` 做了 6 次写操作（1 INSERT + 5 UPDATE），全部单线程。这是最大的性能瓶颈，也是最难调试的结构——某个指标出错时，不知道是哪次 UPDATE 造成的。

```
当前写操作链（均为单线程）：
INSERT cell_metrics_window     ← 质心 + 基础统计
UPDATE cell_metrics_window     ← P50/P90 半径
UPDATE cell_metrics_window     ← active_days_30d / consecutive_inactive_days
UPDATE cell_metrics_window     ← max_spread_m
UPDATE cell_metrics_window     ← net_drift_m
UPDATE cell_metrics_window     ← drift_ratio
```

## 二、优化方案：多 CTAS + 最终 JOIN

把"一张表反复 UPDATE"改成"多张独立小表各写一次，最后 JOIN 拼装"。

### 改后的写操作链

```
CTAS cell_metrics_base         ← 质心 + 基础统计（和现在的 INSERT 一样）
CTAS cell_radius_stats         ← P50/P90 半径（和现在的 UPDATE CTE 一样）
CTAS cell_activity_stats       ← active_days_30d / consecutive_inactive_days
CTAS cell_drift_stats          ← max_spread + net_drift + drift_ratio（3合1）
CTAS cell_metrics_window       ← base JOIN radius JOIN activity JOIN drift
```

### 每张表的 SQL 来源

| 新表 | 原来的代码位置 | SQL 基本不变 |
|------|-------------|------------|
| cell_metrics_base | window.py `recalculate_cell_metrics()` 的 INSERT 部分 | 是 |
| cell_radius_stats | window.py `recalculate_cell_metrics()` 的 UPDATE 半径部分的 CTE `radii` | 是 |
| cell_activity_stats | window.py `_update_activity_metrics()` 的 CTE `activity` | 是 |
| cell_drift_stats | cell_maintain.py `compute_drift_metrics()` 的 3 个 CTE 合并 | 合并但每个 CTE 不变 |
| cell_metrics_window | 新增的 JOIN SQL，约 15 行 | 新写 |

### 关键要求

1. **每张中间表都可独立查验**：`SELECT COUNT(*), AVG(center_lon) FROM cell_metrics_base` 对不对？一眼看出。
2. **每张表的 SQL 和现在的基本一样**：只是从 UPDATE 的子查询变成 CTAS 的 SELECT。
3. **drift_ratio 不再单独 UPDATE**：它就是 `net_drift / max_spread`，在 cell_drift_stats 的 SELECT 里直接算。
4. **所有 CTAS 的 SELECT 部分都能用 PG 并行 worker**（最多 16 个）。

### 性能预期

当前 5 次 UPDATE 约 800 秒（单线程）→ 改为 5 个 CTAS 后，每个 SELECT 用 16 并行 worker，预计 **200 秒以内**。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `maintenance/window.py` | `recalculate_cell_metrics()` 拆成 cell_metrics_base + cell_radius_stats 两个 CTAS，`_update_activity_metrics()` 改为 cell_activity_stats CTAS |
| `maintenance/cell_maintain.py` | `compute_drift_metrics()` 的 3 次 UPDATE 合并为 cell_drift_stats 1 个 CTAS |
| `maintenance/pipeline.py` | 在 drift_stats 之后加一步：CTAS cell_metrics_window = 4 表 JOIN |

## 三、publish_cell 拆层

当前 `publish_cell_library` 是 300+ 行的"总装 SQL"，同时做数据准备和规则判定。

### 改为两步

**步骤 1：数据准备**（CTAS `cell_publish_merged`）

合并所有来源，不做业务判定：
```
本轮 snapshot (qualified/excellent)
+ carry-forward (上轮 library 中不在本轮 snapshot 的)
+ LEFT JOIN cell_metrics_window (指标)
+ LEFT JOIN cell_anomaly_summary (异常)
+ LEFT JOIN 上轮 library (防毒化对比字段)
```

**步骤 2：规则判定**（CTAS `trusted_cell_library`）

从 cell_publish_merged 读，只做 CASE 判定：
- 漂移分类（drift_pattern）
- 防毒化（antitoxin_hit）
- 退出管理（dormant/retired）
- 标签完善（is_dynamic / is_multi_centroid / cell_scale）

### 收益

- 数据准备和规则判定可以分别验证
- carry-forward 和本轮 snapshot 共用同一套规则
- 规则变更时不用碰 JOIN 逻辑

### 涉及文件

| 文件 | 改动 |
|------|------|
| `maintenance/publish_cell.py` | 拆成两个 CTAS，原有 SQL 的 CTE/JOIN 保持，只是物理分层 |

## 四、多质心算法集成

### 当前状态

`is_multi_centroid` 仍是阈值判断（P90 >= 触发值），`cell_centroid_detail` 是占位伪数据。需要真正的空间聚类。

### 集成位置

多质心计算应在 **drift_stats 之后、publish 之前** 执行：

```
cell_metrics_base → cell_radius_stats → cell_activity_stats → cell_drift_stats
  → cell_metrics_window (JOIN)
  → ★ 多质心聚类 (cell_multi_centroid_analysis)
  → publish_cell_library
```

### 输入

- `cell_sliding_window` 中 P90 >= 触发阈值的 cell 的原始 GPS 观测点
- 触发范围通过 `cell_radius_stats.p90_radius_m` 筛选

### 输出

- `cell_centroid_detail`：每个 cell 的多个聚类簇（cluster_id, center_lon, center_lat, obs_count, dev_count, radius_m, share_ratio, is_primary）
- `is_multi_centroid` 标记写入 `cell_metrics_window` 或直接在 publish 时判定

### 算法选择

参考 `rebuild5/prompts/09_多质心算法调研.md`，推荐：

1. **DBSCAN**（首选）：自动发现簇数，对噪声鲁棒，适合不规则分布
2. **自定义距离阈值聚类**（备选）：最简单，按距离阈值递归合并

### 实现方式

两种可选：

**方案 A：PG 内计算（SQL + PL/pgSQL）**
- 优点：不离开数据库，无数据搬运
- 缺点：PG 没有原生 DBSCAN，需要写存储过程
- 适合：自定义距离阈值聚类

**方案 B：Python 计算（scikit-learn DBSCAN）**
- 优点：算法成熟，参数调优方便
- 缺点：需要把数据从 PG 拉到 Python，再写回
- 适合：DBSCAN / HDBSCAN

**推荐**：方案 B。因为触发范围的 cell 是少数（P90 >= 800m 的约 4 万个），每个 cell 的观测点不多（窗口 30 天），数据搬运成本可控。scikit-learn 的 DBSCAN 对这个规模的数据秒级完成。

### 执行频率

- 当前阶段：每轮 Step 5 都计算一遍（数据还在调试）
- 未来优化：只对新增/变化的 cell 增量计算

### 与碰撞/迁移的关系

多质心分析的结果需要反向回答：
- 2 个稳定簇 + 距离 >= 20km → `collision`
- 2 个簇 + 单向位移趋势 → `migration`
- 3+ 个簇 / 簇不稳定 → `dynamic`
- 2 个稳定簇 + 距离 < 20km → `is_multi_centroid`（但不是碰撞）

这些判定在 publish 的规则判定层完成，不在聚类算法中完成。

### 涉及文件

| 文件 | 改动 |
|------|------|
| 新增 `maintenance/multi_centroid.py` | DBSCAN 聚类 + 结果写入 cell_centroid_detail |
| `maintenance/pipeline.py` | 在 drift_stats 后调用多质心分析 |
| `maintenance/publish_cell.py` | 规则判定层读取 cell_centroid_detail 判定 is_multi_centroid |
| `maintenance/schema.py` | cell_centroid_detail 表结构确认（已存在） |

## 五、执行顺序

```
第一步：metrics CTAS 化（方案二 P0）
  - window.py: INSERT→CTAS, 2个UPDATE→2个CTAS
  - cell_maintain.py: 3个UPDATE→1个CTAS
  - pipeline.py: 加最终 JOIN CTAS
  - 验证：各中间表行数 + 指标对比

第二步：publish 拆层（方案二 P1）
  - publish_cell.py: 拆成 merge + rules 两步
  - 验证：trusted_cell_library 行数和指标不变

第三步：多质心聚类（方案四）
  - 新增 multi_centroid.py
  - pipeline.py 集成
  - 验证：cell_centroid_detail 产出真实簇数据
  - 验证：is_multi_centroid 标记与手工验证一致
```

## 六、不做的事

| 项 | 原因 |
|----|------|
| 日级层扩展（cell_day_activity 等） | 当前 70 万 cell + 7 天数据，收益不明显 |
| sliding_window 日期分区 | 当前 DELETE 裁剪可控，等数据 > 1 亿行再做 |
| BS/LAC 重构 | 下游小表，不是主瓶颈 |
| detect_collisions 优化 | 已有 multi_bs 预筛 + count=0 短路，秒级 |
