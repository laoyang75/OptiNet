# Phase 3 Prompt：数据补齐与修正

> 用途：Phase 2 可信库完成后，启动新会话读取此 prompt 开始数据补齐
> 阶段：BS 中心点精算 → GPS 修正 → 信号补齐 → 异常检测 → 完整回归
> 注意：画像（Profile）不在本阶段，是 Phase 4

---

## 1. 环境信息

- **数据库**：PostgreSQL 17 @ 192.168.200.217:5433/ip_loc2（用户 postgres，密码 123456）
- **SSH**：root@192.168.200.217，密码 111111
- **SSH 连接**：`sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217`
- **后端**：FastAPI 端口 8100（rebuild2/backend），venv 路径 `rebuild2/backend/.venv/bin/python`
- **启动器**：端口 9100（rebuild2/launcher_web.py）
- **大表操作**：先用 MCP（mcp__PG17__execute_sql）小规模测试，再 SSH 到服务器用 psql 全量执行

---

## 2. 前置条件 — Phase 2 产出

| 表 | 行数 | 说明 |
|----|------|------|
| `rebuild2.l0_gps` | **3843 万** | GPS 定位源表 |
| `rebuild2.l0_lac` | **4377 万** | LAC 定位源表（本阶段主要数据源） |
| `rebuild2.dim_lac_trusted` | **1,057** | 可信 LAC（7天满窗口 + 日均门槛） |
| `rebuild2.dim_cell_stats` | **573,561** | Cell 统计（从 l0_lac 聚合，含简单 GPS 中位数） |
| `rebuild2.dim_bs_stats` | **193,036** | BS 统计（从 Cell 聚合，GPS 为 Cell 中位数的中位数） |

**注意**：Phase 2 的 dim_cell_stats / dim_bs_stats 的 GPS 中心点是**简单中位数**，没有做信号加权、异常剔除、设备去重。Phase 3 第一步就是重新精算这些中心点。

### 可信库规则摘要

- **LAC**：4G/5G，四运营商(46000/46001/46011/46015)，active_days=7，LAC ID 合规(4G:256~65533, 5G:256~16777213)，日均上报量以移动3500为基准按占比换算，广电全量
- **Cell**：可信 LAC 范围内 l0_lac 聚合，CellID 合规(4G:1~268435455, 5G:1~68719476735)
- **BS_ID**：4G = cell_id / 256，5G = cell_id / 4096

### L0 数据质量（l0_lac, 4G+5G 可信 LAC 范围，约 3008 万行）

| 字段 | 覆盖率 |
|------|--------|
| GPS 有效 | 84.2%（无值约 500 万行） |
| RSRP | 88.9% |
| RSRQ | 80.5% |
| SINR | 57.0% |
| Dbm | 57.9% |

### dim_cell_stats 字段
```
operator_code, operator_cn, tech_norm, lac, cell_id, bs_id, sector_id,
record_count, distinct_device_count, active_days, first_seen, last_seen,
gps_center_lon, gps_center_lat, valid_gps_count
```

### dim_bs_stats 字段
```
operator_code, operator_cn, tech_norm, lac, bs_id,
cell_count, record_count, distinct_device_count, max_active_days,
first_seen, last_seen, gps_center_lon, gps_center_lat, valid_gps_count
```

---

## 3. 必须先读取的文件

### 上下文
1. `rebuild2/prompts/phase1_field_governance.md` — Phase 1 规则
2. `rebuild2/prompts/phase2_trusted_library.md` — Phase 2 规则
3. `docs/data_warehouse/00_业务逻辑与设计原则.md` — 四个核心业务原则

### 上一轮参考实现（重要）
4. `lac_enbid_project/Layer_3/Layer_3_Technical_Manual.md` — BS 库构建技术手册
5. `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql` — BS 中心点精算 + 碰撞检测
6. `lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql` — Cell GPS 修正
7. `lac_enbid_project/Layer_4/Layer_4_Technical_Manual.md` — Cell 补齐技术手册
8. `lac_enbid_project/Layer_4/sql/40_step40_cell_gps_filter_fill.sql` — GPS 过滤与回填
9. `lac_enbid_project/Layer_4/sql/41_step41_cell_signal_fill.sql` — 信号两阶段补齐

### 数据库
10. `rebuild2.dim_cell_stats` / `dim_bs_stats` / `dim_lac_trusted` — 查看结构
11. `rebuild2.l0_lac` — 查看字段（`SELECT * FROM rebuild2.l0_lac LIMIT 3`）

### 代码文件
12. `rebuild2/backend/app/api/trusted.py` — Phase 2 API
13. `rebuild2/frontend/js/pages/trusted.js` — Phase 2 前端

---

## 4. 业务原则

1. **有效 cell_id = 有效记录** — 不因 GPS 漂移丢弃记录
2. **修正优于丢弃** — 优先修正、补齐、标记；不能修正的标记风险，不删除
3. **层层收敛、互相印证** — 正向 Cell→BS，反向 BS→Cell
4. **止损优先** — 碰撞/异常区域宁可不回填，也不传播错误

---

## 5. Phase 3 处理链路

**总体原则：先处理正常数据，确认后再处理异常。异常检测需要与用户互动确认。**

### Part A：正常数据处理（先做这部分）

#### Step 1：BS 中心点精算

Phase 2 的 dim_bs_stats GPS 是简单中位数，本步重新精算。

**1a. GPS 计算优化：设备去重**

当一个 Cell 下数据量较大时（例如 >100 条 GPS），同一台设备可能多次上报相近位置，导致 GPS 中心点被该设备拉偏。优化策略：
- **数据量 > 100 GPS 点时**：先按设备 ID（设备标识）去重，每台设备取一个代表点（GPS 中位数或首次上报点），再用设备级代表点计算中心
- **数据量 ≤ 100 GPS 点时**：直接用全量计算，设备去重反而可能损失信息
- 这确保 GPS 中心点反映"不同位置的设备分布"而非"某设备的重复上报"

**1b. 信号加权选种**

上一轮经验：RSRP 信号越强的点离基站越近，GPS 越可信。

处理流程：
1. 从 l0_lac 中取可信 LAC 范围内、GPS 有效、RSRP 有效的记录
2. 按 BS 分组 `(运营商, 制式, LAC, bs_id)`
3. 信号加权选种：
   - GPS 点 ≥ 50：取 RSRP 最强的 top 50 个点（先按设备去重）
   - GPS 点 20~49：取 RSRP 最强的 top 20
   - GPS 点 5~19：取 RSRP 最强的 top 80%
   - GPS 点 < 5：全部使用
4. 用选中的种子点计算 GPS 中位数中心点（分箱直方图法，精度 ≈11m）
5. 异常剔除：最远点 > 2500m → 去掉 >2500m 的点 → 重新计算中心
6. 计算距离指标：`gps_p50_dist_m`, `gps_p90_dist_m`, `gps_max_dist_m`

**1c. GPS 质量分级**
- `Usable`：≥2 个 Cell 有 GPS → 中心点可信，可用于回填
- `Risk`：仅 1 个 Cell 有 GPS → 中心点可用但带风险标记
- `Unusable`：0 个 Cell 有 GPS → 不可用于回填

**产出**：`rebuild2.dim_bs_refined`

#### Step 2：Cell GPS 校验与修正

1. 对每个 Cell，同样做设备去重 + GPS 中位数计算
2. 计算 Cell 中心到所属 BS 中心的距离
3. 距离 > 阈值（4G: 2000m, 5G: 1000m） → 标记 GPS 异常
4. 正常 Cell 保留计算的 GPS 中心点

**产出**：`rebuild2.dim_cell_refined`

#### Step 3：明细行 GPS 修正

对 l0_lac 中可信 LAC 范围内的 3008 万行进行 GPS 修正：

1. 每行通过 (运营商, 制式, LAC, CellID) 关联 Cell
2. 判定逻辑：
   - 原始 GPS 有效且到 Cell 中心距离 ≤ 阈值(4G:1000m, 5G:500m) → `gps_source = 'original'`
   - 原始 GPS 有效但超阈值（漂移） → 用 Cell 中心覆盖 → `gps_source = 'cell_center'`
   - 原始 GPS 缺失 → 回填 Cell 中心 → `gps_source = 'cell_center'`
   - Cell 无 GPS 但 BS 质量 Usable → 回填 BS 中心 → `gps_source = 'bs_center'`
   - Cell 无 GPS 且 BS 质量 Risk → 回填并标记 → `gps_source = 'bs_center_risk'`
   - BS 质量 Unusable → 不回填 → `gps_source = 'not_filled'`
3. **止损**：碰撞/异常 BS 下的记录标记 `is_collision_suspect`，由 Part B 处理后决定是否回填

**产出**：中间表或在最终表中新增 GPS 修正列

#### Step 4：信号补齐

**二阶段策略**（用窗口函数实现）：

1. **同 Cell 补齐**
   - 在同一个 (运营商, 制式, LAC, CellID) 内，按上报时间排序
   - 用 `LAG/LEAD` 窗口函数找前后最近的有值记录
   - 取时间距离更近的一方作为 donor
   - 逐字段 COALESCE：RSRP、RSRQ、SINR、Dbm
   - 记录：`signal_fill_source = 'cell_nearest'`，donor 时间差

2. **同 BS 退化补齐**
   - 如果同 Cell 内完全无 donor（该 Cell 所有记录某字段全空）
   - 退化到同 BS 下记录数最多的 Cell，取其时间最近有值记录
   - 记录：`signal_fill_source = 'bs_top_cell_nearest'`

#### Step 5：回算

用修正后的 GPS 重新计算 Cell 中心点 → 重新计算 BS 中心点。更新 dim_cell_refined / dim_bs_refined。

---

### Part B：异常检测（需要与用户互动确认）

**先完成 Part A 后再做这部分。异常检测的阈值和策略需要看数据后确认。**

#### Step 6：碰撞检测

碰撞 = 不同物理基站被映射到同一个 bs_id（编码碰撞）。

检测信号：
- `gps_p90_dist_m > 1500m`（BS 下 GPS 点散布太大）
- `anomaly_cell`（同一个 CellID 出现在多个 LAC 下 — Phase 2 的 dim_cell_stats 可检查）
- 碰撞分级：`碰撞嫌疑` vs `严重碰撞`（嫌疑 + 点数多 + p50 > 5km）
- 严重碰撞 → **止损：不做 GPS 回填**

#### Step 7：动态 BS / Cell 识别

动态基站特征（高铁/公交/移动基站车）：
- **BS 和 Cell 大概率 1:1**（`cell_count = 1`）— 正常固定基站通常有多个扇区
- **覆盖范围异常大**（gps_max_dist_m 远超正常值）
- **多质心**：GPS 点在空间上呈线状或多簇分布，不聚拢
- **时间相关移动**：不同时段 GPS 位置不同（如沿高铁线路移动）

检测方法（由简到复杂，逐步确认）：
1. 先筛 `cell_count = 1` 的 BS
2. 在其中找 `gps_max_dist_m > 阈值`（如 5000m）的
3. 对嫌疑 BS 做多质心检测（简化 DBSCAN 或距离聚类）
4. 标记 `is_dynamic_bs`、`dynamic_reason`

#### Step 8：BS 反向纯化 Cell

闭环验证：
- 碰撞 BS → 下属 Cell 标记碰撞
- Cell GPS 与 BS 画像严重不一致 → 标记为可疑
- 风险等级：`normal` / `suspicious` / `collision`
- **不删除，只标记**

---

### Part C：完整回归

#### Step 9：全量重新处理

Part A + B 确认后，用最终规则从 l0_lac 全量重新处理一遍：
- 统一应用 GPS 修正（含止损）
- 统一应用信号补齐
- 统一标记碰撞/动态
- 确保所有记录用同一套规则

**产出**：`rebuild2.dwd_fact_enriched`（补齐后的全局明细表）

---

## 6. 工作方式

**与 Phase 1/2 相同**：定义规则 → UI 审核 → 确认执行 → 查看结果。

你需要：
1. 在 `rebuild2/backend/app/api/` 下创建新路由（建议 `enrich.py`）
2. 在 `rebuild2/frontend/js/pages/` 下创建新页面（建议 `enrich.js`）
3. 每一步的参数（阈值）在 UI 上展示，用户确认后执行
4. **大表操作用 SSH psql**，结果写入中间表，页面读中间表
5. 前端侧栏 "L3 BS+GPS+信号" 对应本阶段

**重要执行顺序**：
1. 先完成 Part A（Step 1~5），让用户在 UI 上查看正常数据的修正效果
2. Part A 确认后再做 Part B（Step 6~8），异常检测阈值需要看数据后与用户讨论
3. Part B 确认后执行 Part C（Step 9 完整回归）

**不要一次性做完。** 每一步用户确认后再做下一步。

---

## 7. 数据库 schema 规划

| Schema | 表 | 说明 |
|--------|-----|------|
| `rebuild2` | `dim_bs_refined` | BS 精算维表（信号加权 GPS、碰撞标记、动态标记、质量分级） |
| `rebuild2` | `dim_cell_refined` | Cell 精算维表（GPS 校验、风险等级） |
| `rebuild2` | `dwd_fact_enriched` | GPS/信号补齐后的全局明细（最终产出） |
| `rebuild2_meta` | `enrich_rule` | 补齐规则参数（阈值等） |
| `rebuild2_meta` | `enrich_result` | 补齐执行统计（各步骤前后对比） |

---

## 8. 性能优化要点

### GPS 计算优化
- **设备去重**：GPS 点多（>100）时先按设备 ID 去重取代表点，避免同设备多次上报拉偏中心
- **分箱直方图中位数**：用 `round(lon * 10000)` 分箱（精度≈11m）代替 `percentile_cont`，大数据量下快 10x+
- **Haversine 简化**：北京地区可用线性近似（1° 经度 ≈ 85.3km，1° 纬度 ≈ 111km），距离计算用 `sqrt(dx² + dy²)` 代替三角函数

### 大表操作
- l0_lac 可信 LAC 范围内有 **3008 万行**
- GPS 修正和信号补齐是行级操作，建议：
  - 用 `CREATE TABLE ... AS SELECT ...` 生成新表，而非 UPDATE 原表
  - 信号补齐用窗口函数（`LAG/LEAD`），需在 `(cell_id, 上报时间)` 上有索引
  - 分批处理可按运营商或 LAC 切分
- `SET statement_timeout = 0; SET work_mem = '512MB';`

### 异常检测优化
- 碰撞检测只需在 dim_bs_refined 上操作（19 万行），不需要回原表
- 动态 BS 先用简单条件（cell_count=1 + 距离大）快速筛选候选，再对候选做复杂检测

---

## 9. 上一轮参考实现关键点

上一轮（lac_enbid_project/Layer_3~5）的设计经验，本次应参考但不必照搬：

### BS 中心点（Layer 3 Step 30）
- 信号优先选种：RSRP 最强的 N 个点作为种子
- 两轮计算：种子中位数 → 剔除 >2500m → 重算
- GPS 质量三级：Usable / Risk / Unusable

### GPS 回填止损（Layer 4 Step 40）
- 严重碰撞判定：`is_collision_suspect=1 AND anomaly_cell_cnt=0 AND 有效点>=50 AND p50>=5km`
- 严重碰撞 → **不做 GPS 回填**（`gps_source = 'Not_Filled'`）
- 普通碰撞嫌疑 → 仍回填但标记

### 信号补齐（Layer 4 Step 41）
- 窗口函数 LAG/LEAD 找前后 donor
- 二阶段：同 Cell 最近 → 同 BS 最大 Cell 最近
- 追溯：记录 donor ID + 时间差

### 本次与上一轮的差异
- 数据源：本次用 l0_lac（含 ss1 行），上一轮仅 cell_infos
- 数据量：Cell 57 万 vs 50 万，BS 19 万 vs 14 万
- GPS 中心点需要重算（Phase 2 是简单中位数）
- 动态 BS 检测：上一轮有 28 天数据窗口做时序分析，本次只有 7 天，策略需调整
