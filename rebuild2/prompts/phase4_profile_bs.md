# Phase 4 Prompt：BS 画像

> 用途：LAC 画像完成后，启动新会话读取此 prompt 构建 BS 级画像
> 前置：LAC 画像样本评估已通过，`_sample_lac_profile_v1` 结构已确认
> 工作方式：先用样本 LAC 的 BS 子集构建临时表评估 → 用户确认 → 全量执行

---

## 1. 环境信息

- **数据库**：PostgreSQL 17 @ 192.168.200.217:5433/ip_loc2（用户 postgres，密码 123456）
- **SSH**：`sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217`
- **后端**：FastAPI（rebuild2/backend），venv 路径 `rebuild2/backend/.venv/bin/python`
- **前端**：rebuild2/frontend，侧栏新建 "L4 BS 画像" 页面
- **大表操作**：SSH psql 执行，SET max_parallel_workers_per_gather = 0
- **MCP 工具**：`mcp__PG17__execute_sql`（查询和小规模分析）

---

## 2. 前置条件 — Phase 3 + LAC 画像产出

### 核心数据表

| 表 | 行数 | 说明 |
|----|------|------|
| `rebuild2.dwd_fact_enriched` | ~3008 万 | GPS+信号补齐后的全局明细表 |
| `rebuild2.dim_cell_refined` | 573,561 | 小区(Cell)精算维表 |
| `rebuild2.dim_bs_refined` | 193,036 | 基站(BS)精算维表 |
| `rebuild2._research_bs_classification_v2` | 9,591 | BS 异常分类（Cell 质心法 v2） |
| `rebuild2._research_cell_centroid_v2` | 44,157 | Cell 质心 + 空间跨度 |

### LAC 画像样本表（已确认结构）

| 表 | 行数 | 说明 |
|----|------|------|
| `rebuild2._sample_lac_facts` | 206,097 | 6 个样本 LAC 的明细数据 |
| `rebuild2._sample_lac_profile_v1` | 1,008 | LAC × 天 × 小时 压缩表（6 LAC × 7 天 × 24 小时） |

### BS 异常分类（Phase 3 产出）

| 分类 | BS 数 | 记录数 | 画像处理 |
|------|-------|--------|---------|
| dynamic_bs | 5,124 | 983,153 | **生成画像但标记**，不参与 LAC 聚合 |
| collision_confirmed | 2,013 | 726,109 | **生成画像但标记**，不参与 LAC 聚合 |
| collision_suspected | 173 | 77,567 | **生成画像但标记**，不参与 LAC 聚合 |
| single_large | 1,360 | 429,450 | 生成画像，标记低精度 |
| normal_spread | 908 | 265,621 | 正常，GPS 噪声已消除 |
| collision_uncertain | 13 | 2,415 | 生成画像但标记 |
| 未在分类表中 | ~183,445 | ~27,598,066 | 正常 BS |

### dwd_fact_enriched 关键字段

```
operator_code, tech_norm, lac, cell_id, bs_id,
lon_final, lat_final, gps_source,           -- GPS 修正后坐标 + 来源标记
report_time, dev_id,                         -- 上报时间、设备标识
rsrp_final, rsrq_final, sinr_final, dbm_final,  -- 信号值
signal_fill_source                           -- 信号来源（original / cell_fill / unfilled）
```

### 已知数据质量问题（不影响画像，但需知晓）

1. **5G unfilled 106 万条**：原始 SS原始值 未转入 RSRP，待修复
2. **4G SINR 41% 空**：原始数据特性（终端不上报），非补齐遗漏
3. **signal_fill_source 只跟踪 RSRP**：RSRQ/SINR/DBM 的补齐来源未单独标记

---

## 3. 必须先读取的文件

### 上下文
1. `rebuild2/prompts/phase4_profile_baseline.md` — Phase 4 整体规划
2. `rebuild2/prompts/phase3_anomaly_bs_research_result.md` — 异常研究完整报告
3. `docs/data_warehouse/00_业务逻辑与设计原则.md` — 核心业务原则

### LAC 画像参照
4. `rebuild2/backend/app/api/profile.py` — LAC 画像 API（了解已确认的结构）
5. `rebuild2/frontend/js/pages/profile.js` — LAC 画像前端

### 异常分类逻辑
6. `rebuild2/backend/app/api/anomaly.py` — 异常研究 API

---

## 4. BS 画像 vs LAC 画像的核心区别

| 维度 | LAC 画像 | BS 画像 |
|------|---------|---------|
| 粒度 | 大区域（几百个 BS） | 单个基站（定位单元） |
| 核心 | 时间模式 + 数据健康度 | **空间精度 + 定位能力** |
| 异常 BS | 排除不参与计算 | **全部生成画像，但标记分类** |
| 空间指标 | 覆盖面积（粗略） | **中心点、P50/P90 距离、散布** |
| 用途 | 了解区域数据质量 | **直接评估定位可用性** |

---

## 5. 业务原则

1. **所有 BS 都生成画像**：包括异常 BS，附带分类标记和可信度
2. **BS 画像的核心是空间精度**：中心点坐标、覆盖半径、GPS 散布直接决定定位能力
3. **与 LAC 画像结构对齐**：同样采用 BS × 天 × 小时 压缩表，支持时间聚合
4. **补齐信息必须体现**：GPS 来源和信号来源的比例
5. **样本不足的 BS 标记低可信度**：GPS 点 < 4 或设备数 = 1 的 BS 标记为低可信

---

## 6. 执行计划

### Step 1：构建样本 BS 数据

从 `_sample_lac_facts`（6 个 LAC、206,097 条）中提取 BS 画像样本。
这 6 个 LAC 包含约 1,096 个 BS，足够覆盖各种场景。

### Step 2：设计 BS × 天 × 小时 压缩表

**表名建议**：`_sample_bs_profile_v1`

**粒度**：operator_code × tech_norm × lac × bs_id × report_date × hour_of_day

**关键设计问题**（需要思考的）：

1. **空间指标**：BS 的中心点、P50/P90 距离是空间散布特征，**不随时间变化**（或变化极小）。这些指标是否应该存在另一张 BS 维度表中，而不是重复到每个小时？
   - 方案 A：BS × 天 × 小时 只存 cnt/sum，空间指标单独一张 BS 汇总表
   - 方案 B：空间指标也放到小时级（可以看不同时段的 GPS 漂移）
   - **建议先用方案 A**：小时表 + BS 汇总表，避免过度设计

2. **异常分类标记**：分类是 BS 级的静态属性，直接从 `_research_bs_classification_v2` 关联即可，不需要冗余到小时表

3. **Cell 信息**：每个 BS 下有多少 Cell、Cell 质心位置 — 从 `_research_cell_centroid_v2` 关联

### Step 3：构建 UI 页面

- 侧栏新增 "L4 BS 画像"
- 前端新建 `profile_bs.js` 页面
- 后端新建 API 路由（可复用 `profile.py` 或新建）

### Step 4：样本评估

在 UI 上展示样本 BS 画像，逐步迭代字段定义。

### Step 5：全量执行

确认后在全量 `dwd_fact_enriched` 上执行。

---

## 7. 画像字段参考（初始方案，待评估后调整）

### 表 1：BS 小时级压缩表 `bs_profile_hourly`

与 LAC 画像对齐的结构：

| 字段分类 | 字段 | 说明 |
|----------|------|------|
| **主键** | operator_code, tech_norm, lac, bs_id, report_date, hour_of_day | BS × 天 × 小时 |
| **规模** | record_cnt, cell_cnt, device_cnt | 干净口径（所有 BS 都保留，不排除） |
| **GPS 健康** | gps_valid_cnt, gps_original_cnt, gps_cell_center_cnt, gps_bs_center_cnt, gps_bs_center_risk_cnt | GPS 来源拆分 |
| **信号健康** | signal_valid_cnt, signal_original_cnt, signal_fill_cnt | 信号来源拆分 |
| **信号求和** | signal_cnt, rsrp_sum, rsrq_sum, sinr_sum, dbm_sum | 可聚合信号 |

### 表 2：BS 汇总表 `bs_profile_summary`

BS 级一行一条，包含空间指标和分类标记：

| 字段分类 | 字段 | 说明 |
|----------|------|------|
| **主键** | operator_code, tech_norm, lac, bs_id | BS 维度 |
| **规模汇总** | total_records, total_devices, total_cells, active_days, active_hours | 7 天汇总 |
| **空间精度** | center_lon, center_lat | GPS 加权中心点 |
| **空间散布** | gps_p50_dist_m, gps_p90_dist_m, gps_max_dist_m | 距中心点的距离分位数 |
| **覆盖** | coverage_radius_km, area_km2 | 覆盖范围 |
| **密度** | report_density_per_km2 | 上报密度 |
| **异常分类** | classification_v2 | 从 _research_bs_classification_v2 关联 |
| **Cell 信息** | cell_count, static_cells, dynamic_cells, cell_span_m | 从异常分类表关联 |
| **可信度** | gps_confidence, signal_confidence | 综合评估 |
| **GPS 健康汇总** | gps_original_ratio, gps_valid_ratio | 7 天汇总比例 |
| **信号健康汇总** | signal_original_ratio, rsrp_avg | 7 天汇总 |

---

## 8. 可信度标注

### gps_confidence
| 等级 | 条件 |
|------|------|
| high | GPS 原始点 ≥ 10 且设备 ≥ 2 且无碰撞/动态标记 |
| medium | GPS 原始点 4-9，或设备 = 1，或有 single_large 标记 |
| low | GPS 原始点 1-3 |
| none | 无有效 GPS |

### signal_confidence
| 等级 | 条件 |
|------|------|
| high | 原始信号占比 > 80% |
| medium | 原始信号占比 50-80% |
| low | 原始信号占比 < 50% 或大量补齐 |

---

## 9. 工作方式

**与 LAC 画像相同**：

1. 先用 `_sample_lac_facts` 的 BS 子集做样本表
2. 在 UI 上展示画像，用户评估属性
3. 用户确认后全量执行
4. **不要一次性做完。** 每一步用户确认后再做下一步。

**执行时先自行设计一版画像结构**，构建临时表和 UI，然后等用户反馈调整。参考 LAC 画像的迭代过程。

---

## 10. 性能要点

- 样本 BS ~1,096 个（来自 6 个 LAC），足够快速迭代
- BS 空间指标（P50/P90 距离）需要对每个 BS 的 GPS 点计算距离，用 `PERCENTILE_CONT` 或近似
- 全量执行时 193,036 个 BS 的空间指标计算较重，用 SSH psql
- SET max_parallel_workers_per_gather = 0（服务器共享内存限制）

---

## 11. 页面结构

- 侧栏：新增 "L4 BS 画像"（与 "L4 LAC 画像" 平级）
- 页面内 Tab：
  - **BS 画像**：样本 BS 列表 + 点击展开详情（空间、信号、潮汐）
  - **BS 总览**：全量执行后的汇总统计（后期解锁）
