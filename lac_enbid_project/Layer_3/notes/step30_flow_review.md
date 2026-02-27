# Step30（Master BS Library）现状、问题与流程优化建议（评估稿）

更新时间：2025-12-24  
范围：`lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql` + 分片包装 `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_shard_psql.sql`

> 目的：把“当前 SQL 在做什么 / 为什么会跑很久 / 你提出的流程问题是什么 / 我建议怎么改”整理成一份可评估文档。

---

## 1. Step30 当前在做什么（按数据流拆解）

Step30 的输出是一张“站级主库”表：

- `public."Y_codex_Layer3_Step30_Master_BS_Library"`（每个物理桶 1 行）
- 物理桶键：`wuli_fentong_bs_key = tech_norm|bs_id|lac_dec_final`

输入来自 Layer2 冻结表：

- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`：用于定义“桶全集 + 覆盖时间画像 + 共建运营商列表”
- `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`：可信 GPS 点（Verified/合规）来源
- `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`：可信 LAC 白名单
- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`：cell→lac 映射证据底座（Step30 仅取“唯一映射”）
- `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`：多 LAC 异常哨兵（用于碰撞风险标记）

### 1.1 “桶全集”与基础画像

- `bucket_universe`：从 Step06 抽出所有 `(tech_norm, bs_id, lac_dec_final)`，并计算：
  - 共建运营商数量/列表（`shared_operator_cnt/shared_operator_list`）
  - 覆盖时间画像（`first_seen_ts/last_seen_ts/active_days`）

这一步的结果是：即使某个桶没有任何可信 GPS 点，也会在最终输出里出现（并被标记为 Unusable）。

### 1.2 “可信 GPS 点”抽取与 LAC 归一

- `gps_points_raw`：从 Step02 抽取 `is_compliant=true AND has_gps=true` 且经纬度在中国粗框内的点，并补出 `bs_id`（必要时从 `cell_id_dec` 推导）。
- `map_unique`：从 Step05 聚合出每个 `(operator_id_raw, tech_norm, cell_id_dec)` 的“唯一 lac 映射”（`min(lac)=max(lac)` 才保留）。
- `gps_points_lac_final`：LAC 归一逻辑：
  - 若 LAC 在 Step04 白名单中：用原始 `lac_dec`
  - 否则：用 `map_unique.lac_dec_from_map`
  - 无法得到 `lac_dec_final` 的点直接丢弃

### 1.3 “信号优先中心点 + 离群剔除 + 重算”

这部分是 Step30 的计算核心，也是潜在耗时核心：

1) **信号清洗**：将异常/占位 RSRP 置空（`sig_rsrp_clean`）。

2) **信号优先种子选择（Top50/Top20/Top80%）**  
用直方图+窗口累计（`sig_hist/sig_rank`）近似分位数，求阈值 `sig_rsrp_threshold`，得到种子点集合 `is_in_signal_seed`。

3) **中心点估计（初始化）**  
用“经纬度分桶中位数（bin median）”替代 `percentile_cont(0.5)`，分别对：
- 全量点
- 信号种子点
计算中位数中心；若信号点不足（`signal_min_points_for_signal_center`），回退到全量点中心。

4) **点级离群剔除**  
按 haversine 公式计算点到中心距离（`dist_m_init`）。  
若桶内 `gps_max_dist_m_init > 2500m`，则剔除 `dist>2500m` 的点，之后重算中心点（仍遵循“信号优先/不足回退”）。

5) **离散度分布（p50/p90/max）**  
再次计算点到最终中心的距离 `dist_m`，用距离直方图+窗口累计近似计算 `p50/p90`，同时算 `max`。

### 1.4 风险/碰撞标记与最终输出

- `anomaly_cell_cnt`：从 Step06 与 Step05 多 LAC 哨兵表关联，统计每桶命中哨兵的异常 cell 数。
- `is_collision_suspect`：满足以下之一则标记为 1：
  - `anomaly_cell_cnt>0`
  - 或 `gps_p90_dist_m > 1500m`（且桶有足够 cell）

---

## 2. 当前“分片并发”方案的真实效果与风险点

分片执行脚本：`lac_enbid_project/Layer_3/sql/run_step30_sharded_16.sh`  
分片 SQL：`lac_enbid_project/Layer_3/sql/30_step30_master_bs_library_shard_psql.sql`

### 2.1 分片逻辑在哪里生效

分片过滤通过：

```
mod(hashtextextended(wuli_fentong_bs_key, 0), shard_count) = shard_id
```

在 Step30 中主要用于：

- `bucket_universe`（从 Step06 抽桶全集时过滤）
- `gps_points`（在 LAC 归一后，对点按桶键过滤）
- `anomaly_cell_cnt`（哨兵统计时按桶键过滤）

### 2.2 为什么“16 分片跑两天”可能反而更慢

你观察到：数据更新前“单核≈2天”，现在“16 核并行跑两天还没完”，这通常说明并发没有把重负载拆开，反而放大了底座工作量。

关键原因在于：**分片过滤对 Step02/Step05 的“底座扫描与聚合”没有提前生效**，导致“每个分片会话重复做同一份底座工作”：

- `map_unique` 是对 Step05 全表 group by（每个 shard 会话都会做一次）
- `gps_points_raw` 是对 Step02 全表扫描+过滤（每个 shard 会话都会做一次）

结果：所谓 16 分片并发，很可能变成了 **16 次重复扫大表 / 16 次重复聚合** 在抢 IO（尤其是 shared storage / 磁盘 temp spill 场景），从而整体更慢。

另外，分片脚本把 `max_parallel_workers_per_gather=0`（避免查询内并行 MQ 争用）是合理的，但如果底座阶段已被 16 倍放大，关闭查询并行并不能救回来。

---

## 3. 你提出的流程问题（我如何理解）

你主张的“更合理流程”可以概括为：

1) **先分桶（先把点归到桶 / 或先把桶做准入）**  
把 2700 万点尽早裁剪到“真正需要算中心点/离散度”的那部分（你预期裁剪后 <100 万规模）。

2) **分桶阶段顺带做无效数据统计（质量画像）**  
例如：无 GPS、越界、无 bs_id、lac 无法归一、信号无效等，作为运行解释与止损依据。

3) **对可满足计算的桶走常规计算，对“不足/不齐”的桶走降级或跳过**  
例如点数太少/信号点不足/疑似碰撞桶：单独处理，甚至不必做完整的离群剔除与两次距离分布。

4) **并行策略应该围绕“桶”来做**  
每个桶的数据量小，桶与桶之间天然独立；并行应当让每个 worker/shard 只处理自己的桶集合，而不是重复扫全量底座表。

我同意：这套思路的目标是把 Step30 从“单个巨型 CTAS”改造成“分阶段裁剪 + 桶级任务并行”，以避免当前的结构性瓶颈（尤其是重复扫大表、temp spill、leader 汇总等）。

---

## 4. 我建议的解决方案（两种强度）

下面给两档方案：A 为“最小侵入但能止血”，B 为“结构性重构，最符合你说的先分桶”。

### 4.1 方案 A：止血型（让分片真正减少底座成本）

核心思想：**把会被 16 次重复计算的“底座结果”先物化一次**，然后每个 shard 只读自己的分片。

建议新增一个“预处理阶段”（一次性）：

1) 物化 `map_unique`（或改成可复用的中间表）
   - 目标：避免 Step05 在每个 shard 会话重复 group by

2) 物化“已归一的 GPS 点窄表”（建议 UNLOGGED 临时表/中间表）
   - 从 Step02 过滤出合规点，完成 bs_id 补齐、LAC 归一、信号清洗
   - 生成 `wuli_fentong_bs_key`、`lon_bin/lat_bin`
   - **在这里就做 semi-join 到 `bucket_universe`（Step06 桶全集）**：只保留会落入桶全集的点

之后分片会话只做：

- 从“GPS 点窄表”按 hash 过滤自己 shard 的 key
- 跑后续中心点/离群剔除/距离分布计算

优点：
- 改动相对可控，不强行改变口径
- 分片会话的工作量会被真正切开（不会再 16× 重复扫 Step02/Step05）

风险/代价：
- 需要额外的中间表空间（但中间表列更少，通常比原表窄）
- 需要有建表权限（UNLOGGED/临时 schema）

### 4.2 方案 B：结构性重构（真正“先分桶/准入/降级”）

核心思想：把 Step30 拆成“桶准入/轻算”和“桶重算”两层，避免所有桶都走同一条重链路。

建议的分阶段流水线：

**Stage 0：桶全集 + 桶准入指标（轻量）**

- 产出 `bucket_universe`（与现有一致）
- 基于“已归一 GPS 点”（Stage1 产物）做桶级统计：
  - `point_cnt`、`cell_cnt`、`sig_valid_cnt`、`first/last/active_days`（或复用 Step06）
  - 质量统计：越界剔除数、lac 归一失败数、bs_id 缺失数、信号无效数等
- 给每桶打一个 `compute_mode`，例如：
  - `UNUSABLE`：cell_cnt=0（中心点置空）
  - `RISK`：cell_cnt=1（可算中心但标记风险）
  - `FULL`：满足点数/信号点数阈值才跑“离群剔除+距离分位数”
  - `SIMPLE`：不足阈值则只算一次中位数中心，不做 outlier removal / p90 等重指标

**Stage 1：只对 FULL/SIMPLE 桶计算中心点**

- 对 `FULL` 桶走完整链路（信号优先 + outlier + 重算 + dist_p50/p90/max）
- 对 `SIMPLE` 桶走简化链路（少做 1~2 次大窗口/距离直方图）

**Stage 2：并行与合并**

- Stage1 按桶键 hash 分片并行（每个 shard 只读取自己的桶与点）
- 合并后再统一打上哨兵风险、共建信息等

优点：
- 最符合“先分桶→小桶并行→不足降级/跳过”的设计目标
- 把重算只留给“值得算”的桶，整体更可控（可止损）

风险/代价：
- 需要重新设计输出字段的口径细节（例如 SIMPLE 桶的 p90 是否置空还是降级估计）
- 改动更大，需要额外的验证与验收对齐

---

## 5. 为什么我认为“先分桶”会显著改善耗时（直觉解释）

当前重链路包含大量对点集的：

- 直方图聚合（group by key + bin）
- 窗口累计（`sum(cnt) over(partition by key order by bin)`）
- haversine 距离（大量三角函数计算，且至少两轮）

这些算子按点数线性增长，并且对 `temp`/排序/窗口非常敏感。

若能在进入重链路之前：

- 用桶全集做 semi-join，丢掉不会落入任何有效桶的点
- 对点数/信号点不足的桶直接降级或跳过

则整体点数与“需要重算的桶数”都会显著下降，且并行会更有效（不会被底座重复扫放大）。

---

## 6. 评估建议（下一步应该先确认什么）

为了决定选 A 还是 B，建议先回答 3 个问题（均可用 SQL 快速量化）：

1) Step02 全量合规点规模到底是多少？（过滤后剩多少点）
2) 归一后能落入 Step06 桶全集的点比例是多少？（semi-join 能裁剪多少）
3) 桶的点数分布是什么样？（point_cnt/cell_cnt/sig_valid_cnt 的长尾是否严重）

如果 (2) 能裁掉大量点，且 (3) 显示大量桶点数不足，那么方案 B 的收益会很大；  
如果 (2) 裁剪不明显，但 (3) 桶普遍足够，方案 A 先止血会更稳。

---

## 7. 结论（本稿摘要）

- 现 Step30 的业务口径（信号优先中心点 + 离群剔除 + 重算 + 离散度 + 碰撞哨兵）是自洽的，但“计算链路”对点数与窗口/聚合极敏感。
- 当前分片并发的实现方式，存在“底座重复扫大表”的结构性风险：16 分片可能导致 Step02/Step05 被重复计算 16 次，从而整体更慢。
- 你提出的“先分桶/准入/降级/再并行”方向是更合理的工程流程。
- 我建议优先评估：
  - A（一次性物化底座 + shard 只读子集）作为止血
  - 若需要进一步降本控时，则做 B（结构性重构：桶准入 + FULL/SIMPLE 分层）

