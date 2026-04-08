# Phase 3 独立研究：GPS 异常分析

> 身份：**数据分析 Agent**
> 任务：系统性分析 GPS 定位质量问题，产出分类结论供 Phase 4 画像使用
> 产出：三张分类表 + 分析报告
> 前置：Phase 3 全部 5 步已完成，dwd_fact_enriched / dim_bs_refined / dim_cell_refined 已就绪

---

## 环境信息

- **MCP 工具**：`mcp__PG17__execute_sql`（查询和小规模分析）
- **SSH**：`sshpass -p '111111' ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@192.168.200.217`
- **PG17**：`PGPASSWORD=123456 psql -h 127.0.0.1 -p 5433 -U postgres -d ip_loc2`
- 所有 SQL 执行前加 `SET max_parallel_workers_per_gather = 0;`（服务器共享内存限制）

---

## 数据源

| 表 | 行数 | 用途 |
|----|------|------|
| `rebuild2.dim_bs_refined` | 193,036 | 基站(BS)精算维表，含距离指标、质量分级 |
| `rebuild2.dim_cell_refined` | 573,561 | 小区(Cell)精算维表，含 GPS 异常标记 |
| `rebuild2.dwd_fact_enriched` | ~3008 万 | 补齐后明细表，含 gps_source、signal_fill_source |
| `rebuild2.l0_lac` | ~4377 万 | 原始明细表，含上报时间 |
| `rebuild2.dim_lac_trusted` | 1,057 | 可信 LAC 白名单 |

---

## 研究范围：三大类 GPS 问题

### 研究一：异常基站(BS)质心变化分析

**目标**：对高数据量 + 空间散布异常的基站(BS)，通过日级质心变化判定为编码碰撞/搬迁/移动基站。

**候选条件**（只研究数据量大的，小的没有研究价值）：
- `record_count >= 200`（至少 200 条记录）
- 且满足以下任一：
  - `gps_p90_dist_m > 1500`（散布大，碰撞嫌疑）
  - `gps_max_dist_m > 5000`（最远点很远）
  - `had_outlier_removal = true AND gps_p90_dist_m > 1000`（有异常剔除 + 中等散布）

**分析方法**：

1. 提取候选基站(BS)的 GPS 点（从 l0_lac，可信 LAC 范围内）
2. 按天计算每日质心（7 天数据 → 7 个质心）
3. 计算相邻日质心位移
4. 分类判定：

| 模式 | 质心变化特征 | 典型场景 |
|------|-------------|---------|
| **编码碰撞** | 质心每天在 2~3 个固定位置跳动，或同天内多簇 | 不同物理基站(BS)共用编号 |
| **基站搬迁** | 前几天在 A 位置，后几天跳到 B，一次性迁移 | 运营商迁站 |
| **移动基站** | 质心每天在不同位置，呈线性轨迹 | 高铁基站、公交中继 |
| **正常+飘点** | 质心每天基本一致，只是覆盖范围大 | GPS 精度问题 |

**产出表**：`rebuild2._research_bs_classification`

```sql
CREATE TABLE rebuild2._research_bs_classification (
    operator_code TEXT, tech_norm TEXT, lac TEXT, bs_id BIGINT,
    operator_cn TEXT, cell_count INT, record_count BIGINT,
    gps_p90_dist_m NUMERIC, gps_max_dist_m NUMERIC,
    active_days INT,
    avg_daily_move_m NUMERIC,     -- 日均质心移动距离
    max_daily_move_m NUMERIC,     -- 最大单日移动
    lon_span_m NUMERIC,           -- 经度跨度（米）
    lat_span_m NUMERIC,           -- 纬度跨度（米）
    classification TEXT,          -- 编码碰撞/疑似搬迁/移动基站/正常
    reason TEXT,                  -- 判定依据
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 研究二：GPS 补齐异常分析

**目标**：评估 Phase 3 第三步 GPS 修正中标记异常的小区(Cell)，以及补齐来源为"基站(BS)中心点（风险）"的记录。

**分析范围**：
1. **小区(Cell) GPS 异常**（dim_cell_refined.gps_anomaly = true，31,451 个小区）：
   - 这些小区的 GPS 代表点距基站(BS)中心超阈值（4G>2000m, 5G>1000m）
   - 需要分析原因：漫游用户外地上报？小区确实在远处？碰撞？
   - 按偏差距离分档统计，抽样典型案例

2. **风险回填记录**（dwd_fact_enriched.gps_source = 'bs_center_risk'，13,889 行）：
   - 这些记录用"风险"等级的基站(BS)中心点回填
   - 需要评估这些基站(BS)的质量：是否可接受？

3. **未能填充记录**（dwd_fact_enriched.gps_source = 'not_filled'，3,133 行）：
   - 分析为什么无法填充：哪些基站(BS)？什么原因？

**产出表**：`rebuild2._research_gps_fill_quality`

```sql
CREATE TABLE rebuild2._research_gps_fill_quality (
    category TEXT,           -- 'cell_anomaly' / 'risk_fill' / 'not_filled'
    operator_code TEXT, tech_norm TEXT, lac TEXT,
    cell_id BIGINT, bs_id BIGINT,
    record_count BIGINT,
    issue_description TEXT,  -- 问题描述
    recommendation TEXT,     -- 建议（保留/标记/忽略）
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 研究三：低 GPS 样本基站(BS)/小区(Cell)标记

**目标**：标记 GPS 点数 ≤ 3 的基站(BS)和小区(Cell)，这些不应参与 GPS 相关的画像指标计算。

**为什么 ≤ 3 个点不处理**：
- 3 个及以下的 GPS 点无法可靠计算中位数（中位数就是某个点本身）
- 无法判断是否有飘点（没有足够样本做异常检测）
- 中心点的误差可能很大

**分析内容**：

```sql
-- 从 dim_bs_refined 统计
SELECT
    count(*) FILTER (WHERE total_gps_points <= 3 AND total_gps_points > 0) AS bs_le3_gps,
    count(*) FILTER (WHERE total_gps_points = 0) AS bs_no_gps,
    count(*) FILTER (WHERE total_gps_points > 3) AS bs_gt3_gps
FROM rebuild2.dim_bs_refined;

-- 从 dim_cell_refined 统计（如果有 gps_count 列）
SELECT
    count(*) FILTER (WHERE gps_count <= 3 AND gps_count > 0) AS cell_le3_gps,
    count(*) FILTER (WHERE gps_count = 0 OR gps_count IS NULL) AS cell_no_gps,
    count(*) FILTER (WHERE gps_count > 3) AS cell_gt3_gps
FROM rebuild2.dim_cell_refined;
```

**产出表**：`rebuild2._research_low_gps_sample`

```sql
CREATE TABLE rebuild2._research_low_gps_sample (
    level TEXT,              -- 'bs' / 'cell'
    operator_code TEXT, tech_norm TEXT, lac TEXT,
    bs_id BIGINT, cell_id BIGINT,
    gps_count INT,
    record_count BIGINT,
    classification TEXT,     -- 'no_gps' / 'low_sample(1-3)' / 'adequate(>3)'
    gps_confidence TEXT,     -- 'none' / 'low' / 'medium' / 'high'
    created_at TIMESTAMPTZ DEFAULT now()
);
```

**GPS 可信度分级规则**：
| GPS 点数 | 分级 | 说明 |
|----------|------|------|
| 0 | none | 无 GPS 数据，不计算 GPS 画像 |
| 1~3 | low | GPS 样本不足，中心点不可靠 |
| 4~9 | medium | 有一定参考价值，但精度有限 |
| ≥ 10 且无异常 | high | GPS 中心点可靠 |
| ≥ 10 但有异常标记 | medium | 虽然样本够，但有碰撞/飘点嫌疑 |

---

## 执行顺序

1. 先做**研究三**（低 GPS 样本，最快，几分钟）→ 产出分级统计
2. 再做**研究二**（GPS 补齐异常，中等规模）→ 产出异常评估
3. 最后做**研究一**（异常基站质心，最复杂，需 SSH 提取数据）→ 产出分类表

每个研究完成后向用户汇报结论，确认后继续。

---

## 产出要求

### 最终报告格式

向用户汇报以下信息：

1. **低 GPS 样本统计**
   - 基站(BS)：≤3 GPS 点多少个？0 GPS 多少个？占总基站比例？
   - 小区(Cell)：同上
   - 建议：这些在 Phase 4 画像中标注 gps_confidence = 'low' / 'none'

2. **GPS 补齐异常评估**
   - 小区(Cell) GPS 异常 31,451 个的成因分析（漫游/碰撞/真实远距）
   - 风险回填 13,889 行的质量评估
   - 未能填充 3,133 行的原因分析
   - 建议：哪些标记为不可信，哪些可以保留

3. **异常基站(BS)分类**
   - 候选基站数量
   - 各分类数量（碰撞/搬迁/移动/正常/待判定）
   - 每种分类的 3~5 个典型案例（含日级质心轨迹）
   - 建议：碰撞基站在 Phase 4 画像中如何处理

4. **综合建议**
   - Phase 4 画像需要哪些异常标记
   - 哪些基站(BS)/小区(Cell)的 GPS 指标不应该被使用

---

## 注意事项

1. **数据只有 7 天**（12/01~12/07），搬迁判断标记为"疑似"
2. **优先级**：碰撞 > 低 GPS 样本 > 补齐异常 > 移动/搬迁
3. **不删除数据**：只做标记和分类，不修改 dwd_fact_enriched / dim_bs_refined / dim_cell_refined
4. **产出表都用 `_research_` 前缀**，不影响正式数据
5. **SSH psql 必须加** `SET max_parallel_workers_per_gather = 0;`
