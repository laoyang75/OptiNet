# Step30 流程重构方案（Stage 0~9，评估草案）

更新时间：2025-12-24  
目标：把 Step30 从“点级大 CTAS”改为“先分桶/准入/降级 + 桶级并行”的可控流水线，显著降低 2700 万点级计算的重复扫描与重算成本。

> 本文基于你提供的 Stage 0~9 方案整理，并补充了我认为需要评估/拍板的关键口径点与工程实现注意事项。

---

## 对齐说明：本方案仍然是“先构建 BS（Step30）→ 再用 BS 处理 cell（Step31）”

Layer_3 现有设计里：

- Step30 输出 `Y_codex_Layer3_Step30_Master_BS_Library`：**bs_id 级**中心点/离散度/风险标签
- Step31 输出 `Y_codex_Layer3_Step31_Cell_Gps_Fixed`：以 Step30 的 bs 中心点为依据，对 Step06 明细（cell 级）进行补齐/纠偏/过滤

本重构方案不改变这个“BS-first”的业务结构。文中出现的 `step30_cell_points` 仅作为 **Step30 内部计算加速的中间表**（可选），用于把“点级计算压力”压缩后再反推出 BS 级中心点；它不是新的“先做 cell 再做 bs”的业务分层。

## 背景：为什么要重构

当前 `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql` 的计算链路对“点数”极其敏感（直方图+窗口累计+两轮距离计算），且分片并发方案存在“底座重复扫大表”的风险（Step02/Step05 在每个 shard 会话里可能被重复扫描/聚合）。

重构核心思路：

1) **先分桶（semi-join 到 bucket_universe）**，尽早裁剪“落不进桶全集”的点。  
2) **先做桶准入与降级（FULL/SIMPLE/COLLISION/UNUSABLE）**，只让少量桶走重链路。  
3) **在 cell 级（或 tile 级）压缩后再跑 FULL**，把点级压力压到可控范围。  
4) 并行策略围绕“桶键”分片，避免每个 shard 重复扫 Step02/Step05。

---

## Stage 0：准备维表（一次/每次运行可重建）

### 输出 0.1：桶全集 `step30_bucket_universe`

来源：Layer2 Step06  
至少字段：

- `wuli_fentong_bs_key`（`tech_norm|bs_id|lac_dec_final`）
- `tech_norm, bs_id, lac_dec_final`
- `first_seen_ts, last_seen_ts, active_days`
- `shared_operator_cnt, shared_operator_list`

说明：最终 Step30 输出必须覆盖 bucket_universe 全集（即使没有 GPS 点也要出 1 行）。

### 输出 0.2：唯一映射维表 `step30_map_unique`

来源：Layer2 Step05 `CellId_Stats_DB`  
逻辑：只保留 `(operator_id_raw, tech_norm, cell_id_dec)` 的唯一 lac 映射（`min(lac)=max(lac)`）。  
字段：`operator_id_raw, tech_norm, cell_id_dec, lac_dec_from_map`

说明：这是“能补的 lac”的可靠来源之一；需要维表化，否则 NEED_FIX 难以实施。

---

## Stage 1：构建“规范点窄表”并完成落桶（只做便宜运算）

### 输出：`step30_points_norm`（建议 HASH 分区 32 份）

来源：Layer2 Step02

#### 1) 输入过滤（只做硬过滤）

- `is_compliant=true`
- `has_gps=true`
- 经纬度合法（中国粗框）：`lon BETWEEN 73 AND 135 AND lat BETWEEN 3 AND 54`

#### 2) 补齐 `bs_id`

- 优先用 `m.bs_id`
- 否则从 `cell_id_dec` 推导：
  - 4G：`floor(cell_id_dec/256)`
  - 5G：`floor(cell_id_dec/4096)`

#### 3) LAC 归一得到 `lac_dec_final`

- 若 `lac_dec` 在 Step04 白名单：用原 `lac_dec`
- 否则：用 `step30_map_unique.lac_dec_from_map`
- 仍为空：`lac_fixable=false`（进入 NEED_FIX 或进入失败点统计）

#### 4) 生成桶键（必须在这里完成）

- `wuli_fentong_bs_key = tech_norm || '|' || bs_id || '|' || lac_dec_final`

#### 5) 关键：semi-join 到 bucket_universe

- 只保留能落入 `step30_bucket_universe` 的点（否则后面再算都是浪费）
- 同时把“落不进桶全集”的点计数入质量画像（不要静默丢）

#### 6) 信号清洗（字段级）

- 生成 `sig_rsrp_clean`：异常/占位值置 `NULL`

#### 7) 质量画像 flag（建议保存在 `step30_points_norm`）

至少包含：

- `flag_out_of_cn_bbox`
- `flag_missing_bs_id`
- `flag_missing_lac_final`
- `flag_not_in_bucket_universe`
- `flag_sig_invalid`
- （可选）`flag_gps_bad_precision` 等

#### 分区建议

- `PARTITION BY HASH(wuli_fentong_bs_key)` 分 32 份（或与 shard_count 对齐）
- 索引建议：`(wuli_fentong_bs_key)`、`(tech_norm, bs_id, lac_dec_final)`、`(operator_id_raw, tech_norm, cell_id_dec)`（视查询路径而定）

---

## Stage 2：点级限量（每桶最多取最近 N=1000 点进入重链路）

### 输出：`step30_points_calc`

输入：`step30_points_norm`  
逻辑：对每个 `wuli_fentong_bs_key` 按 `ts_std DESC` 排序，仅保留最近 `N=1000` 个点作为“计算点集”。

推荐字段（从 `step30_points_norm` 透传即可）：

- `wuli_fentong_bs_key, tech_norm, bs_id, lac_dec_final`
- `operator_id_raw, cell_id_dec`
- `ts_std, lon, lat, sig_rsrp_clean`

目的：

- 保持 Step30 的核心口径为“点级等权”计算（避免 cell 等权带来的偏差）
- 对极端大桶（例如某些 BS 下点数过多）做硬止损：把最坏情况从“1 万点”截断到“最多 1000 点”
- 通过“按 `ts_std DESC` 取最近 N”实现可解释性：使用最新数据估计中心点，更符合工程直觉

口径说明（需要写死，避免误解）：

- **重链路（中心点/离群剔除/p50-p90-max）基于 `step30_points_calc` 计算**。
- **桶级规模统计（例如 gps_valid_cell_cnt / gps_valid_point_cnt）建议仍基于 `step30_points_norm`（未截断）计算**，否则可能把“历史有效 cell”低估成 Risk/Unusable，影响 Step31 的回填决策。

---

## Stage 3：桶准入统计（只允许便宜聚合）

### 输出 3.1：`step30_bucket_stats`

从 `step30_points_norm`（未截断点集）聚合桶级统计：

推荐统计项：

- `gps_valid_cell_cnt` = `count(distinct (operator_id_raw, cell_id_dec))`
- `gps_valid_point_cnt` = `count(*)`
- `sig_valid_point_cnt` = `count(*) filter (where sig_rsrp_clean is not null)`

空间粗尺度（重要且便宜）：

- `lon_min/max, lat_min/max`
- `diag_est_m`：用 bbox 粗估尺度（不用 haversine），用于 outlier/碰撞短路判定

---

## Stage 4：桶模式分类（UNUSABLE / COLLISION / FULL / SIMPLE / NEED_FIX）

### 输出：`step30_bucket_mode`

输入：`step30_bucket_universe` left join `step30_bucket_stats` + 风险哨兵（`anomaly_cell_cnt`）  
输出：每桶 `compute_mode`（以及解释字段/阈值命中原因）

阈值建议（起步值，后续用分布校准）：

- `MIN_CELL_CENTER = 1`
- `MIN_CELL_SIMPLE = 2`
- `MIN_CELL_FULL = 5`
- `MIN_SIG_CELL_FULL = 3`
- `MIN_POINT_FULL = 30`
- `OUTLIER_TRIGGER_DIAG_M = 2500`
- `COLLISION_DIAG_M = 5000`

模式规则（推荐顺序）：

1) `UNUSABLE`
- `cell_cnt < MIN_CELL_CENTER` 或 `point_cnt=0`

2) `COLLISION`
- `anomaly_cell_cnt>0`
- OR `diag_est_m >= COLLISION_DIAG_M`
- （可选）共建运营商很高且 diag 很大

3) `FULL`
- `cell_cnt >= MIN_CELL_FULL`
- AND `point_cnt >= MIN_POINT_FULL`
- AND `sig_valid_cell_cnt >= MIN_SIG_CELL_FULL`
- AND 非 COLLISION

4) `SIMPLE`
- 非 UNUSABLE / 非 COLLISION，且满足 `MIN_CELL_SIMPLE`

5) `NEED_FIX`
- 主要用于“lac_dec_final 缺失但可补”的桶/点的回收修复路径（见 Stage 8）

---

## Stage 5：SIMPLE 桶计算（轻量、稳定、可解释）

### 输出：`step30_result_simple`

输入：`step30_points_calc` join `step30_bucket_mode(mode='SIMPLE')`

做什么：

- 中心点：按“点级等权”算一次中心（建议 `percentile_cont(0.5)` 或 bin-median 近似）
- 距离统计：
  - 建议至少 `max`；`p90` 建议置 `NULL` 或只给 `p50`（避免口径争议）
- 输出质量解释字段：`cell_cnt/point_cnt/sig_valid_cell_cnt/diag_est_m` 等

距离计算建议：

- 若 `diag_est_m` 不大（<2500m），可用平面近似替代 haversine（省 CPU）：
  - `dx = (lon-lon0)*cos(lat0)*111320`
  - `dy = (lat-lat0)*110540`
  - `dist = sqrt(dx^2+dy^2)`
- 若 diag 很大（已是 COLLISION 候选），无需在 SIMPLE 路径精算距离。

---

## Stage 6：FULL 桶计算（重链路，但只跑在少量桶 + cell 级）

### 输出：`step30_result_full`

输入：`step30_points_calc` join `step30_bucket_mode(mode='FULL')`

建议链路：

1) 信号优先种子（按点级 `sig_rsrp_clean`）
- Top50/Top20/Top80% 的策略保留，但在 cell 层计算直方图与阈值

2) 初始中心点 `center_init`
- 点级 lon/lat 中位数（或 bin-median）

3) outlier removal（只在必要时触发）
- 用 `diag_est_m` 或 `gps_max_dist_m_init` 触发 outlier 逻辑；否则短路
- 剔除 `dist_init > 2500m` 的 cell 点
- 重算 `center_final`

4) 距离分位数与 max
- 在 `center_final` 上计算距离分布并输出：
  - `gps_p50_dist_m, gps_p90_dist_m, gps_max_dist_m`

---

## Stage 7：COLLISION 桶专用流程（避免 FULL 产生“夹在两团中间的假中心”）

### 输出：`step30_result_collision`

目标：

- 给一个“尽可能不骗人的中心” + “碰撞解释指标”
- 不强行输出 FULL 的 p90 等指标（容易误导）

推荐最小可行做法（省算）：

1) 点级（`step30_points_calc`）做粗网格聚类（无 PostGIS）
- 映射到 ~200m 网格，例如：
  - `gx=floor(lon*500)`，`gy=floor(lat*500)`（系数可调）
- 每格权重用 `count(*)`（点级等权）

2) 输出“权重最大格”的重心作为中心（或最大格的中位数）
- 并输出：
  - top1/top2 网格权重占比
  - 网格数、离散网格面积粗估
  - `collision_reason`（哨兵命中/diag 过大等）

---

## Stage 8：NEED_FIX 修复流（只跑在少量桶/点）

### 输出：`step30_result_fix` + `step30_fix_fail_stats`

输入：`step30_points_norm` 中 `lac_fixable=false` 或 `flag_missing_lac_final=true` 的子集

修复策略（示例）：

- 尝试更多证据补 lac（如果有其它证据表可用）
- 补完后重新计算桶键并重新落桶
- 只对涉及的桶重跑 Stage2/Stage3（局部增量）

必须输出：

- `fix_applied_flags`（补了啥）
- `post_fix_mode`（补完后归类）
- `fix_fail_reason` 的统计（治理源数据用）

---

## Stage 9：汇总最终 Step30 输出（全桶覆盖）

### 输出：`public."Y_codex_Layer3_Step30_Master_BS_Library"`

以 `step30_bucket_universe` 为主表 left join：

- `step30_result_full`
- `step30_result_simple`
- `step30_result_collision`
- `step30_result_fix`（补完后归类的结果）
- `step30_bucket_stats`（质量画像、规模、diag）
- `risk_sentinel`（`anomaly_cell_cnt`）

并统一生成最终字段（示例）：

- `compute_mode`
- `is_usable`（UNUSABLE=0，其余=1 或按需定义）
- `is_collision_suspect`（COLLISION=1；FULL/SIMPLE 可补充规则）
- `gps_center_lon/lat`
- `gps_p50/p90/max`（按 mode 置 NULL 或填值，口径写死）
- 质量画像与解释字段

---

## 并行/分片执行注意事项（必须避免资源打架）

1) 不允许“会话内并行 + 外层 32 分片并行”叠加，否则 MQ/IO 会互相打架。  
2) 若仍用 `mod(hashtextextended(...), shard_count)`，务必用非负余数写法避免漏桶：

```
((h % n) + n) % n
```

3) 建议把“底座物化”（Stage0/Stage1/Stage2）做成单次运行；之后 FULL/SIMPLE/COLLISION 才做 shard 并行。

---

## 需要你拍板/评估的关键口径点（建议优先决策）

1) **cell 级压缩后是否接受“等 cell 权重”**？  
   - 接受：实现最简单，收益最大  
   - 不接受：需要加权分位数/加权距离分布（复杂度上升）

2) SIMPLE 桶的 `gps_p90_dist_m` 是否置 NULL？  
   - 置 NULL：口径更干净、减少争议  
   - 计算 p90：需要定义 SIMPLE 的稳定性下限

3) COLLISION 桶的中心点是否允许“网格 top1 重心”作为输出？  
   - 允许：更贴近“不要骗人”的目标  
   - 不允许：需要更复杂聚类/或外部算法支持
