# 数据清洗线 SQL 与验收清单（Codex 草案）

状态：可合并草案  
更新时间：2026-04-06

## 1. 目标

本清单用于把 rebuild2 的字段质量与清洗成果稳定迁入 rebuild4，并保证后续页面/API 的口径不漂移。

## 2. 字段审计校验

### 2.1 `field_audit` 分布校验

```sql
SELECT action, COUNT(*)
FROM rebuild2_meta.field_audit
GROUP BY action
ORDER BY action;
```

通过标准：
- `keep = 17`
- `parse = 3`
- `drop = 7`

未通过处理：
- 停止沿用历史文档数字
- 重新抽取字段审计基线并更新真相表

### 2.2 `drop` 字段清单校验

```sql
SELECT source_field
FROM rebuild2_meta.field_audit
WHERE action = 'drop'
ORDER BY source_field;
```

通过标准：
- 清单与冻结文档一致

未通过处理：
- 记录差异字段
- 更新裁决文档，不得静默忽略

## 3. 目标字段校验

### 3.1 `target_field` 总量校验

```sql
SELECT COUNT(*)
FROM rebuild2_meta.target_field;
```

通过标准：
- 返回 `55`

### 3.2 `target_field` 分类分布校验

```sql
SELECT category, COUNT(*)
FROM rebuild2_meta.target_field
GROUP BY category
ORDER BY category;
```

通过标准：
- 分类分布能与冻结文档对齐

## 4. 解析 / 合规规则现状校验

```sql
SELECT
  (SELECT COUNT(*) FROM rebuild2_meta.parse_rule) AS parse_rule_count,
  (SELECT COUNT(*) FROM rebuild2_meta.compliance_rule) AS compliance_rule_count;
```

通过标准：
- 当前真实结果为 `0 / 0`
- 在 rebuild4 中判定为“待补建”而非“已存在”

未通过处理：
- 若未来有落库结果，需要重新做目录表对齐

## 5. ODS 规则定义与执行校验

### 5.1 定义层总量与分类

```sql
SELECT action, COUNT(*)
FROM rebuild2_meta.ods_clean_rule
GROUP BY action
ORDER BY action;
```

通过标准：
- 总量 `26`
- `delete = 1`
- `nullify = 22`
- `convert = 3`

### 5.2 执行层规则覆盖校验

```sql
SELECT table_name, COUNT(DISTINCT rule_code) AS rule_count
FROM rebuild2_meta.ods_clean_result
GROUP BY table_name
ORDER BY table_name;
```

通过标准：
- `l0_gps = 24`
- `l0_lac = 24`

### 5.3 差异规则校验

```sql
SELECT r.rule_code
FROM rebuild2_meta.ods_clean_rule r
LEFT JOIN (
  SELECT DISTINCT rule_code
  FROM rebuild2_meta.ods_clean_result
) x ON x.rule_code = r.rule_code
WHERE x.rule_code IS NULL
ORDER BY r.rule_code;
```

通过标准：
- 返回 `NULL_WIFI_MAC_INVALID`
- 返回 `NULL_WIFI_NAME_INVALID`

未通过处理：
- 若差异改变，需要同步更新规则差异台账

## 6. trusted 过滤损耗校验

### 6.1 总量/命中/过滤量

```sql
WITH trusted AS (
  SELECT DISTINCT lac, operator
  FROM rebuild2.dim_lac_trusted
), tagged AS (
  SELECT
    CASE WHEN t.lac IS NOT NULL THEN 1 ELSE 0 END AS trusted_hit
  FROM rebuild2.l0_lac l
  LEFT JOIN trusted t
    ON t.lac = l.lac AND t.operator = l.operator
)
SELECT
  COUNT(*) AS total_rows,
  SUM(trusted_hit) AS trusted_rows,
  COUNT(*) - SUM(trusted_hit) AS filtered_rows
FROM tagged;
```

通过标准：
- `total_rows = 43,771,306`
- `trusted_rows = 30,082,381`
- `filtered_rows = 13,688,925`

### 6.2 过滤记录中的有效信息保有量

```sql
WITH trusted AS (
  SELECT DISTINCT lac, operator
  FROM rebuild2.dim_lac_trusted
)
SELECT
  COUNT(*) FILTER (WHERE l.rsrp IS NOT NULL) AS filtered_with_rsrp,
  COUNT(*) FILTER (WHERE l.longitude IS NOT NULL AND l.latitude IS NOT NULL) AS filtered_with_gps
FROM rebuild2.l0_lac l
LEFT JOIN trusted t
  ON t.lac = l.lac AND t.operator = l.operator
WHERE t.lac IS NULL;
```

通过标准：
- `filtered_with_rsrp = 12,017,352`
- `filtered_with_gps = 11,350,552`

## 7. 来源差异校验

### 7.1 按 Cell 来源的 GPS / RSRP 差异

```sql
SELECT
  cell_source,
  COUNT(*) AS rows,
  ROUND(AVG(CASE WHEN longitude IS NULL OR latitude IS NULL THEN 1 ELSE 0 END)::numeric, 4) AS gps_null_rate,
  ROUND(AVG(CASE WHEN rsrp IS NULL THEN 1 ELSE 0 END)::numeric, 4) AS rsrp_null_rate
FROM rebuild2.l0_lac
GROUP BY cell_source
ORDER BY cell_source;
```

通过标准：
- `ss1` 明显差于 `cell_infos`
- 差异被文档和页面说明层显式解释

## 8. 页面/API 映射验收要求

### 8.1 数据治理页

必须校验：
- API 是否返回字段审计、规则统计、trusted 损耗
- 页面是否区分定义层与执行层
- 页面是否展示差异规则与来源损耗

### 8.2 初始化页

必须校验：
- 是否明确显示数据准备状态
- 是否能看到 trusted 与质量基线是否已就绪

### 8.3 Playwright 验收要点

页面相关步骤必须追加：
- 打开治理页，检查字段审计模块可见
- 检查规则统计模块可见且有数字
- 检查 trusted 损耗解释可见
- 如页面支持筛选，切换来源后数字与 API 返回一致
