# Step 00: ETL 验证（样本模式）

## 前置条件
- 阅读 `99_系统上下文.md` 了解数据库结构、连接信息和样本 LAC 定义
- 阅读 `VERSION_SCHEME.md` 了解版本体系

## 工具要求
- 你必须使用 `PG17 MCP` 执行所有 SQL
- 你必须使用 Playwright 或 chrome-devtools 检查页面
- **启动前**：先用浏览器 MCP 工具打开 `http://localhost:47132`，确认 MCP 可用

## 服务说明
- rebuild2 和 rebuild4 的前后端服务由用户手动启动，不要在 prompt 中启动
- rebuild2: `http://localhost:8100`
- rebuild4 前端: `http://localhost:47132`，后端: `http://localhost:47131`

## 背景

ETL（Extract-Transform-Load）是数据流转的通用基础设施。rebuild2 完成了从原始 SDK 上报数据（27 列）到结构化 L0 表（55 列）的全流程解析和清洗。

**本步骤的核心目标**：确认 ETL 有效——验证原始数据经过解析、清洗、可信过滤后的产出与 rebuild2 对齐。

对标 rebuild2 的前 4 层（`http://localhost:8100`）：
1. 原始数据 · 字段挑选（#raw）— 27 列 SDK 原始字段
2. L0 字段审计 + L0 数据概览（#audit, #l0data）— 解析后 55 列结构化数据
3. L1 ODS 清洗规则（#ods）— 26 条清洗规则
4. L2 可信库（#trusted）— 可信 LAC/Cell 过滤

> **注意**：维度精算和数据补齐不在本步骤范围内，归入 Step 01a/01b。

## 样本范围
6 个样本 LAC。数据来源为样本表 `sample_l0_gps`（214,865 行）和 `sample_l0_lac`（206,097 行），而非 `fact_standardized`。

---

## 0.1 验证原始数据层（对标 rebuild2 #raw）

### 目标
确认 SDK 原始上报数据的 27 列字段结构和决策分类。

### 内容
- 两张源表（GPS 表 + LAC 表）的行数统计
- 27 列原始字段的分类和处置决策（保留/解析/丢弃等）
- 字段空值率概览

### 数据来源
rebuild2 的字段审计结果存储在 `rebuild2_meta.field_audit`，原始表为 legacy schema。
rebuild4 的样本表 `sample_l0_gps` / `sample_l0_lac` 是从 L0 解析后的数据。

### 验证方法

```sql
-- rebuild2 原始表行数
SELECT
    (SELECT COUNT(*) FROM rebuild2.l0_gps) as r2_gps_count,
    (SELECT COUNT(*) FROM rebuild2.l0_lac) as r2_lac_count;

-- rebuild4 样本表行数
SELECT
    (SELECT COUNT(*) FROM rebuild4.sample_l0_gps) as sample_gps_count,
    (SELECT COUNT(*) FROM rebuild4.sample_l0_lac) as sample_lac_count;
```

---

## 0.2 验证 L0 解析层（对标 rebuild2 #audit + #l0data）

### 目标
确认 JSON 解析规则正确，sample_l0_gps/lac 的 55 列字段与 rebuild2 一致。

### JSON 解析规则（参考）
- `cell_infos` JSONB → 只保留 `isConnected=1` 的主服务基站
- 制式映射：`lte→4G, nr→5G, gsm→2G, wcdma→3G`
- operator_code：`cell_identity.mno` 或 `mccString+mncString`
- LAC：`cell_identity.Tac/tac/lac/Lac`（bigint）
- CellID：`cell_identity.Ci/Nci/nci/cid`（bigint）
- BS_ID 推算：4G → cell_id/256，5G → cell_id/4096
- 信号：`signal_strength` 下的 `rsrp/SsRsrp`, `rsrq/SsRsrq`, `rssnr/SsSinr`

### 验证方法

```sql
-- 样本 L0 来源/制式/运营商分布
SELECT "制式" as tech_norm, COUNT(*) as cnt,
    ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER (), 4) as ratio
FROM rebuild4.sample_l0_gps
GROUP BY "制式" ORDER BY cnt DESC;

-- 运营商分布
SELECT "运营商编码" as operator_code, COUNT(*) as cnt
FROM rebuild4.sample_l0_gps
GROUP BY "运营商编码" ORDER BY cnt DESC;

-- 字段空值率（关键字段）
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE "CellID" IS NULL OR "CellID"::text = '0') as cellid_null,
    COUNT(*) FILTER (WHERE "LAC" IS NULL) as lac_null,
    COUNT(*) FILTER (WHERE "经度" IS NULL) as lon_null,
    COUNT(*) FILTER (WHERE "纬度" IS NULL) as lat_null,
    COUNT(*) FILTER (WHERE "RSRP" IS NULL) as rsrp_null
FROM rebuild4.sample_l0_gps;
```

**预期**：制式分布以 4G/5G 为主，运营商为 46000/46001/46011。

---

## 0.3 验证 ODS 清洗层（对标 rebuild2 #ods）

### rebuild2 的 26 条 ODS 规则
来源文件：`rebuild2/sql/exec_l0_gps.sql` L214-L278

**运营商清洗**：
- 排除：`'00000','0','000000','(null)(null)',''`
- 有效白名单：`46000,46001,46002,46003,46005,46006,46007,46009,46011,46015,46020`

**LAC 清洗**：
- 排除：`lac=0`、`(lac IN (65534,65535) AND tech='4G')`、`lac=268435455`

**CellID 清洗**：
- 排除：`cell_id=0`、`(cell_id=268435455 AND tech='5G')`

**位置清洗**：经度 `73~135`，纬度 `3~54`

### 验证方法

```sql
-- 在样本 L0 表上检查 ODS 规则违规
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE "运营商编码" NOT IN ('46000','46001','46002','46003','46005','46006','46007','46009','46011','46015','46020')) as bad_operator,
    COUNT(*) FILTER (WHERE "LAC"::text = '0') as bad_lac_zero,
    COUNT(*) FILTER (WHERE "LAC" IN (65534, 65535) AND "制式" = '4G') as bad_lac_reserved_4g,
    COUNT(*) FILTER (WHERE "LAC" = 268435455) as bad_lac_max,
    COUNT(*) FILTER (WHERE "CellID" = 0) as bad_cell_zero,
    COUNT(*) FILTER (WHERE "CellID" = 268435455 AND "制式" = '5G') as bad_cell_max_5g,
    COUNT(*) FILTER (WHERE "经度" IS NOT NULL AND ("经度" < 73 OR "经度" > 135)) as bad_lon,
    COUNT(*) FILTER (WHERE "纬度" IS NOT NULL AND ("纬度" < 3 OR "纬度" > 54)) as bad_lat
FROM rebuild4.sample_l0_gps;

-- 同样检查 sample_l0_lac
```

**预期**：样本数据已经经过 L0 解析，应该极少违规。位置类违规如果存在，应标记为 `GPS有效=false`。

---

## 0.4 验证可信库层（对标 rebuild2 #trusted）

### 验证方法

```sql
-- 6 个样本 LAC 是否在 rebuild2 可信库中
SELECT lt.operator_code, lt.lac, lt.record_count, lt.active_days, lt.cv
FROM rebuild2.dim_lac_trusted lt
WHERE (lt.operator_code = '46000' AND lt.lac IN ('4176','2097233'))
   OR (lt.operator_code = '46001' AND lt.lac IN ('6402','73733'))
   OR (lt.operator_code = '46011' AND lt.lac IN ('6411','405512'));

-- rebuild4 的 obj_lac 是否与可信库一致
SELECT l.operator_code, l.lac, l.record_count as r4_records,
    lt.record_count as r2_trusted_records,
    l.lifecycle_state, l.health_state
FROM rebuild4.obj_lac l
LEFT JOIN rebuild2.dim_lac_trusted lt
    ON l.operator_code = lt.operator_code AND l.lac = lt.lac
WHERE (l.operator_code = '46000' AND l.lac IN ('4176','2097233'))
   OR (l.operator_code = '46001' AND l.lac IN ('6402','73733'))
   OR (l.operator_code = '46011' AND l.lac IN ('6411','405512'));
```

**预期**：6 个样本 LAC 全部 active/healthy，active_days=7。

---

## 0.5 新增 UI：ETL 验证页面

在 rebuild4 前端"支撑治理层"导航组内新增折叠子菜单"ETL 验证"，包含 5 个子页面。

### 页面清单

| 页面 | 路由 | 对标 rebuild2 | 主要内容 |
|------|------|--------------|----------|
| 原始数据 · 字段挑选 | `/governance/raw-overview` | #raw | 纯配置页：27 列字段决策，不查数据库 |
| L0 字段审计 | `/governance/l0-audit` | #audit | 解析后 55 列目标字段定义、来源类型、分类 |
| L0 数据概览 | `/governance/l0-overview` | #l0data | 版本相关：sample 表统计、制式/运营商分布 |
| ODS 清洗规则 | `/governance/ods-rules` | #ods | 规则列表 + 执行结果（分 gps/lac 两表） |
| 可信库 | `/governance/trusted-library` | #trusted | LAC 过滤漏斗、可信 LAC 列表 |

### 后端 API

```
GET /api/governance/foundation/raw-overview      → 27 列字段配置（不查数据库）
GET /api/governance/foundation/l0-audit          → L0 目标字段（查 rebuild2_meta.target_field）
GET /api/governance/foundation/l0-overview        → L0 数据统计（查 sample 表）
GET /api/governance/foundation/ods-rules          → ODS 规则 + 结果（查 sample 表）
GET /api/governance/foundation/trusted-summary    → 可信库漏斗
```

### 性能要求
- raw-overview 不查数据库，瞬间返回
- l0-audit 查元数据小表，瞬间返回
- l0-overview 和 ods-rules 查 **样本表**（sample_l0_gps/sample_l0_lac），不扫 fact_standardized
- 页面加载应在 2 秒内完成

### 导航层级

```
支撑治理层
├─ 初始化
├─ 基础数据治理
└─ ETL 验证（折叠）
   ├─ 原始数据 · 字段挑选
   ├─ L0 字段审计
   ├─ L0 数据概览
   ├─ ODS 清洗规则
   └─ 可信库
```

---

## 0.6 与 rebuild2 对比验证清单

| 验证项 | rebuild4 数据 | rebuild2 参考 | 对比方法 |
|--------|-------------|-------------|----------|
| 原始字段 | 27 列决策 | field_audit | 分类一致 |
| L0 记录数 | sample_l0_gps + sample_l0_lac | l0_gps + l0_lac | 样本范围 COUNT 对比 |
| 制式分布 | sample 表统计 | l0data 页面 | 比例接近 |
| ODS 过滤 | sample 表无脏数据 | ODS 规则 | 反向检查违规记录 |
| 可信 LAC | obj_lac | dim_lac_trusted | LAC 列表比对 |

## 完成标志
- [ ] 原始数据 27 列字段决策与 rebuild2 一致
- [ ] L0 解析结果正确（制式/运营商/来源分布合理）
- [ ] ODS 清洗规则有效（无违规记录，或已标记 GPS有效=false）
- [ ] 可信 LAC 列表与 rebuild2 一致
- [ ] ETL 验证 UI 4 个页面已实现，加载速度 < 2 秒
- [ ] 新页面用浏览器 MCP 截图确认展示正确

## 完成后
继续执行 `01a_修复Cell数据维度.md`
