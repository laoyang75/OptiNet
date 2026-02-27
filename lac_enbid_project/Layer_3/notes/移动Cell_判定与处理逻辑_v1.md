# 移动 Cell：判定与处理逻辑 v1（草案，待你确认数据口径）

背景：在 `cell_id=5694423043` 这类样本上，短窗口（7天）会呈现“多质心 + 时间重叠”的碰撞表象；但长窗口（28天）出现“主导质心随时间切换”的结构，疑似 **移动 Cell / 动态迁移**。若不单独识别，这类 cell 会显著拉高 BS 桶的 `gps_p90/max`，进而影响 Step30/Step31 的风险判定与回填策略。

本草案目标：

- 给出一个 **可落地的判定口径**：把“移动 cell”从“碰撞/混桶”中分离出来（两者对下游处理完全不同）。
- 给出一个 **Layer_3 可接入的处理策略**：输出可解释字段 + 下游止损策略（不改历史，仅新增画像/标记即可）。

---

## 0) 关键前提（请你先确认）

同一份数据里可能同时存在两套坐标：

- “设备GPS/原始GPS”（点级、会随用户移动、通常更分散）
- “cell/bs 推断位置或回填位置”（可能被回填/聚合/服务更新，因此会出现大量重复坐标）

在 `lac_enbid_project/Layer_3/20251225_cellid_28.xlsx` 中同时存在：

- `lgt/ltt`
- `primordial_gps`

后续判定逻辑必须明确“哪一列代表我们要判断的对象位置”：

1) 如果我们要判定 **cell/bs 的真实物理位置是否迁移** → 应优先用“与站址强相关”的坐标来源（例如：高信号子集的设备GPS、或已证实等价于站址的回填坐标）。
2) 如果我们要判定 **设备群体活动区域是否迁移** → 用全量设备GPS即可，但这很容易把“用户群体变化”误判成“基站迁移”。

> 你确认之后，我再把阈值和 SQL 落点完全写死。

---

## 1) 输出对象（建议新增，不改历史）

### 1.1 移动 Cell 画像表（建议）

表：`public."Y_codex_Layer3_Mobile_Cell_Profile"`（新增 TABLE）

主键建议：`(operator_id_raw, tech_norm, cell_id_dec)`（必要时再加 `lac_dec_final` 分裂）

核心字段（最小集）：

- `operator_id_raw, tech_norm, cell_id_dec, cell_id_hex`
- `window_days`（例如 28）
- `point_cnt, device_cnt, active_days`
- `state_cnt`：位置状态数量（聚类后的“站址状态”）
- `state_top1_share`：top1 状态点占比
- `state_top2_dist_km`：top1/top2 站址中心距离
- `state_switch_cnt`：状态切换次数（按日主导状态序列）
- `state_overlap_days_top2`：top1/top2 同日共存天数（用于区分碰撞）
- `is_mobile_cell`（bool）
- `mobile_cell_mode`（枚举：`MOBILE_RELOCATION` / `COLLISION_LIKE` / `UNSURE`）
- `mobile_confidence`（0~1）
- `first_seen_ts, last_seen_ts`

站址状态明细（两种实现二选一）：

- A) 宽表：`state1_lon/lat/days/points`、`state2_...`（最多保留 top3，简单但不灵活）
- B) 子表：`public."Y_codex_Layer3_Mobile_Cell_State_Profile"`：一行一个 state（推荐）

### 1.2 移动 Cell 对 BS 的影响标记（可选）

如果你希望把“移动 cell”同步到 BS 桶画像里（不改变中心点算法，只做标记）：

- 在最终 BS 表（如 `Y_codex_Layer3_Final_BS_Profile`）增加：
  - `mobile_cell_cnt`
  - `has_mobile_cell`（bool）
  - `mobile_cell_list_topN`（text）

---

## 2) 判定流程（工程化、可并行、避免重计算）

### Step A：构建按日“候选站址点”样本（降噪 + 降规模）

对每个 `(operator, tech, cell_id)`，在 `window_days=28` 内：

- 每天只取 top-N 条“最可信/最接近站址”的点来代表当天（推荐 N=200 或 500，依据数据量调）
- 可信/接近站址的排序建议（从强到弱）：
  1) `rsrp DESC`（信号更强通常更靠近站址；你已确认“按 ts_std DESC 取最近 N”也可）
  2) 再按 `ts DESC`（取最近）

对选中的点计算当天的鲁棒中心：

- `day_lon = percentile_cont(0.5) ORDER BY lon`（中位数）
- `day_lat = percentile_cont(0.5) ORDER BY lat`
- 同时输出 `day_cnt`（入样点数）

产物（可做 TEMP/CTAS）：

- `cell_day_center(operator_id_raw, tech_norm, cell_id_dec, day, day_lon, day_lat, day_cnt)`

### Step B：把 `cell_day_center` 聚类为“站址状态”（state）

目标：把 28 个日中心聚成若干个“站址状态”（每个状态应是一个相对稳定的站址）。

不使用 PostGIS 的推荐做法（两种二选一）：

**B1. 栅格聚类（最便宜，推荐）**

- 把 `day_lon/day_lat` 映射到 ~200m 或 ~500m 网格：
  - `gx = floor(day_lon * K)`
  - `gy = floor(day_lat * K)`
  - K=500（约 200m）或 K=200（约 500m）
- `(gx,gy)` 作为粗 state key，统计每个 state 的天数/点数
- 对相邻网格再做一次合并（可选）：把距离 < 500m 的 state 合并（解决边界分裂）

**B2. 距离阈值贪心聚类（更直观）**

- 按天排序，每个 day_center 依次匹配到“距离 < R”的已有 state（R=2km/5km）
- 否则开新 state

### Step C：计算“移动 vs 碰撞”判别特征

核心特征（建议都输出，方便你肉眼验收）：

- `state_cnt`
- `top1_points_share` / `top1_days_share`
- `top1_top2_dist_km`
- `switch_cnt`：按天主导 state（当天 day_center 属于哪个 state）形成序列，统计切换次数
- `overlap_days_top2`：
  - 定义：同一天内存在两组“足够多点”的状态同时活跃
  - 简化做法：如果每天只保留一个 day_center，则 overlap 只能通过“当天 topN 点”内部再聚类得到；否则可先按点聚类再按天统计

> 经验上：移动迁移是“分段主导 + 少量回波”；碰撞是“长期并行 + 双峰同日共存”。

---

## 3) 判定规则（建议 v1 阈值）

先给一套可跑的起步阈值（你确认口径后可直接固化到 SQL）：

### 3.1 进入判定的前提

- `active_days >= 7`
- `point_cnt >= 200`（或按你的数据规模调整）

### 3.2 移动 cell（MOBILE_RELOCATION）

满足：

- `state_cnt >= 2`
- `top1_top2_dist_km >= 10`（站址间距够大）
- 存在“主导状态切换”：在时间轴上，top1/top2 的主导区间能明显分段（例如用 14 天窗口比较或用滑窗 7 天比较）
- “并行度不高”：`overlap_days_top2` 不应长期高占比（允许过渡期有重叠）

建议输出：

- `mobile_confidence`：可以由（切换清晰度、距离、top1_share、重叠天数）加权得到

### 3.3 碰撞/混桶（COLLISION_LIKE）

满足：

- `state_cnt >= 2`
- `top1_top2_dist_km >= 10`
- 且 `overlap_days_top2` 高（例如 >= 30% 的活跃天数）或长期同日双峰

### 3.4 不确定（UNSURE）

- 样本不足或距离不够大或状态过多但都很弱（可能是噪声）

---

## 4) Layer_3 处理策略（止损建议）

### 4.1 对 Step30（BS 中心点）如何处理

1) `COLLISION_LIKE`：
   - 不要用其点参与 BS 中心计算（或只做风险标记，中心置 NULL/保持 Risk）
2) `MOBILE_RELOCATION`：
   - BS 画像如果要求“本期位置”，建议只用 **最近窗口（例如最近 7 天）** 的状态作为中心
   - 同时输出 `mobile_cell_mode`，避免后续把其当成稳定站址

### 4.2 对 Step31（按 BS 回填）如何处理

移动 cell 的 BS 中心是动态的：

- 对 `MOBILE_RELOCATION` 的桶，回填策略要么：
  - 使用“当日/当周的 BS 中心”（时间分段回填）
  - 要么对该类桶直接 `gps_source='Not_Filled'`，避免回填把真实迁移信息抹掉

---

## 5) 你确认后我会做什么（下一步交付）

你只需要确认两点：

1) 移动 cell 判定应基于哪一套经纬度（例如：设备GPS、或信号优先子集的设备GPS、或回填后的坐标）
2) 判定对象粒度：只做 `cell_id`，还是做 `operator+tech+cell_id`（建议至少带 operator+tech）

确认后我会补齐：

- SQL 版本（PG15 纯 SQL、无 PostGIS）实现 `cell_day_center` + `mobile_cell_profile`
- 把字段接入到 Layer_3 的最终交付表（只新增字段，不重算历史）

