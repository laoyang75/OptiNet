# Phase 4 Prompt：画像基线

> 用途：Phase 3 数据补齐 + 异常研究完成后，启动新会话读取此 prompt 构建画像基线
> 阶段：LAC 画像（最简单）→ BS 画像 → Cell 画像
> 前置：Phase 3 的 dwd_fact_enriched、dim_cell_refined、dim_bs_refined 已就绪
> 异常标记：`_research_bs_classification_v2` 已完成，第一轮画像只标记不处理

---

## 1. 环境信息

- **数据库**：PostgreSQL 17 @ 192.168.200.217:5433/ip_loc2（用户 postgres，密码 123456）
- **SSH**：`sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217`
- **后端**：FastAPI（rebuild2/backend），venv 路径 `rebuild2/backend/.venv/bin/python`
- **前端**：rebuild2/frontend，侧栏 "L4 画像基线" 对应本阶段
- **大表操作**：SSH psql 执行，SET max_parallel_workers_per_gather = 0
- **MCP 工具**：`mcp__PG17__execute_sql`（查询和小规模分析）

---

## 2. 前置条件 — Phase 3 产出

### 核心数据表

| 表 | 行数 | 说明 |
|----|------|------|
| `rebuild2.dwd_fact_enriched` | ~3008 万 | GPS+信号补齐后的全局明细表 |
| `rebuild2.dim_cell_refined` | 573,561 | 小区(Cell)精算维表 |
| `rebuild2.dim_bs_refined` | 193,036 | 基站(BS)精算维表 |
| `rebuild2.dim_lac_trusted` | 1,057 | 可信 LAC 白名单 |

### 异常标记表（Phase 3 Part B 产出）

| 表 | 行数 | 说明 |
|----|------|------|
| `rebuild2._research_bs_classification_v2` | 9,591 | **BS 异常分类（Cell 质心法 v2）** |
| `rebuild2._research_cell_centroid_v2` | 44,157 | Cell 质心 + 空间跨度 |

### BS 异常分类标记（classification_v2 字段）

| 分类 | BS 数 | 记录数 | 第一轮处理 | 第二轮处理 |
|------|-------|--------|-----------|-----------|
| dynamic_bs | 5,124 | 983,153 | 标记 | 具体分析 |
| collision_confirmed | 2,013 | 726,109 | 标记 | 拆分重算 |
| collision_suspected | 173 | 77,567 | 标记 | 拆分重算 |
| single_large | 1,360 | 429,450 | 标记低精度 | — |
| normal_spread | 908 | 265,621 | 正常 | — |
| collision_uncertain | 13 | 2,415 | 标记 | — |

**算法详情参见**：`rebuild2/prompts/phase3_anomaly_bs_research_result.md`

### dwd_fact_enriched 关键字段

```
operator_code, tech_norm, lac, cell_id, bs_id,
lon_final, lat_final, gps_source,           -- GPS 修正后坐标 + 来源标记
report_time, dev_id,                         -- 上报时间、设备标识
rsrp_final, rsrq_final, sinr_final, dbm_final,  -- 信号补齐后值
signal_fill_source                           -- 信号来源（original / cell_fill / unfilled）
```

---

## 3. 必须先读取的文件

### 上下文
1. `rebuild2/prompts/phase3_anomaly_bs_research_result.md` — **异常研究完整报告（算法逻辑）**
2. `rebuild2/prompts/phase3_enrich_and_baseline.md` — Phase 3 规则
3. `docs/data_warehouse/00_业务逻辑与设计原则.md` — 核心业务原则

### 代码文件
4. `rebuild2/backend/app/api/anomaly.py` — 异常研究 API（了解分类逻辑）
5. `rebuild2/frontend/js/pages/anomaly.js` — 异常研究 UI（了解漏斗展示）

### 数据库
6. `rebuild2.dwd_fact_enriched` — 查看字段
7. `rebuild2._research_bs_classification_v2` — 查看分类标记

---

## 4. 业务原则

1. **画像 = 基线快照**：冷启动时用全量数据建立基线
2. **先正常后异常**：第一轮全量画像不做特殊处理，异常 BS 只标记不拆分
3. **异常标记传递**：Phase 3 的碰撞/动态/噪声标记需在画像中体现
4. **止损标记不影响画像生成**：即使 BS 有异常标记，仍然生成画像，但附带可信度

---

## 5. 执行计划

### 第一轮：正常画像（本阶段核心）

按从简到复杂的顺序，每一级都是独立步骤，用户确认后再进入下一级。

#### Step 1：LAC 画像 — `rebuild2.profile_lac`

**最简单**，从 dwd_fact_enriched 按 (operator_code, tech_norm, lac) 聚合。

| 指标分类 | 字段 | 计算方式 |
|----------|------|---------|
| **基本信息** | operator_code, tech_norm, lac | 维度键 |
| **规模** | bs_count, cell_count, record_count, device_count | COUNT DISTINCT |
| **覆盖** | center_lon, center_lat, coverage_radius_km | 加权中心 + 覆盖半径 |
| **信号** | rsrp_avg, rsrp_p10, rsrp_p50, rsrp_p90 | 聚合信号 |
| **时间** | active_days, first_seen, last_seen, peak_hour | 时间特征 |
| **质量标记** | usable_bs_ratio, collision_bs_count, dynamic_bs_count | 从异常分类汇总 |
| **GPS** | gps_original_ratio, gps_filled_ratio | GPS 来源比例 |

#### Step 2：BS 画像 — `rebuild2.profile_bs`

从 dwd_fact_enriched + dim_bs_refined 聚合到 BS 维度。

| 指标分类 | 字段 | 计算方式 |
|----------|------|---------|
| **基本信息** | operator_code, tech_norm, lac, bs_id | 维度键 |
| **规模** | cell_count, record_count, device_count | 规模指标 |
| **GPS** | gps_center_lon, gps_center_lat, gps_quality | 精算中心点 + 质量 |
| **覆盖** | gps_p50_dist_m, gps_p90_dist_m | 距离指标 |
| **信号** | rsrp_avg, rsrp_p10, rsrp_p90 | 聚合信号 |
| **异常标记** | classification_v2, device_cross_rate | 从 _research_bs_classification_v2 关联 |
| **可信度** | gps_confidence, signal_confidence | 综合可信度 |

#### Step 3：Cell 画像 — `rebuild2.profile_cell`

最细粒度，从 dwd_fact_enriched 按 Cell 聚合。

| 指标分类 | 字段 | 计算方式 |
|----------|------|---------|
| **基本信息** | operator_code, tech_norm, lac, cell_id, bs_id | 维度键 |
| **数据量** | record_count, device_count, active_days | 规模 |
| **GPS** | gps_center_lon, gps_center_lat, valid_gps_ratio | 中心点 + GPS 有效率 |
| **信号** | rsrp_avg, rsrp_p10, rsrp_p50, rsrp_p90 | 信号指标 |
| **异常标记** | is_gps_anomaly, bs_classification_v2 | 关联标记 |

### 第二轮：异常处理（后续单独进行）

第一轮画像完成后，单独处理异常 BS：

1. **碰撞 BS（2,186 个）**：
   - 从 `_research_cell_centroid_v2` 读取固定 Cell 质心
   - 按空间聚类将 Cell 分组，每组 = 一个虚拟 BS
   - 用正常算法对虚拟 BS 重新计算画像
   - 替换原碰撞 BS 的画像记录

2. **动态 BS（5,124 个）**：具体分析后决定
3. **面积大（1,360 个）**：标记低精度即可

---

## 6. 可信度标注

每条画像记录包含可信度评估：

### gps_confidence
| 等级 | 条件 |
|------|------|
| high | GPS 点 ≥ 10 且无异常标记 |
| medium | GPS 点 4-9，或有异常标记（动态/面积大） |
| low | GPS 点 1-3 |
| none | GPS 点 = 0 |

### signal_confidence
| 等级 | 条件 |
|------|------|
| high | > 80% 原始信号 |
| medium | 50-80% 原始信号 |
| low | < 50% 原始信号或大量补齐 |

### bs_anomaly_type
直接从 `_research_bs_classification_v2.classification_v2` 映射：
- `NULL` 或不在分类表中 → 正常
- `collision_confirmed` / `collision_suspected` → 碰撞（第二轮处理）
- `dynamic_bs` → 动态
- `single_large` → 面积大
- `normal_spread` → 正常（GPS 噪声已消除）

---

## 7. 工作方式

**与前面阶段相同**：定义规则 → UI 审核 → 确认执行 → 查看结果。

需要：
1. 在 `rebuild2/backend/app/api/` 下创建新路由（建议 `profile.py`）
2. 在 `rebuild2/frontend/js/pages/` 下创建新页面（建议 `profile.js`）
3. 侧栏 "L4 画像基线" 对应本阶段
4. 每一级画像在 UI 上展示指标，用户确认后执行

**执行顺序**：
1. LAC 画像 → 用户审核
2. BS 画像 → 用户审核
3. Cell 画像 → 用户审核
4. 全量画像汇总展示

**不要一次性做完。** 每一步用户确认后再做下一步。

---

## 8. 数据库 schema

| Schema | 表 | 说明 |
|--------|-----|------|
| `rebuild2` | `profile_lac` | LAC 画像 |
| `rebuild2` | `profile_bs` | BS 画像 |
| `rebuild2` | `profile_cell` | Cell 画像 |

---

## 9. 性能要点

- LAC 画像最快，直接 GROUP BY (operator_code, tech_norm, lac)
- BS 画像需 LEFT JOIN _research_bs_classification_v2 关联异常标记
- Cell 画像从 3008 万行聚合，用 SSH psql 执行
- 信号分位数用 `PERCENTILE_CONT` 或分箱近似
- SET max_parallel_workers_per_gather = 0（服务器共享内存限制）
