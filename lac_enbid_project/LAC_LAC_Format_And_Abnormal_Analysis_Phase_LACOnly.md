# LAC 正常 / 异常格式分析（核心 5 个 PLMN，LAC 专用库设计）

> 目标：在前一阶段“运营商过滤（5 个核心 PLMN）”的基础上，构建一个**只处理 LAC 的简单分析库**，完成：
> - 统一为每条记录生成 LAC 的 10 进制与 16 进制两个版本；
> - 明确并剔除异常 LAC（0 / NULL / 非数字等）；
> - 分析 4G / 5G / 2G/3G / 其他的占比结构（重点看 46000 / 46001 / 46011 三个运营商）；
> - 找出“异常大流量”的 LAC，为后续黑名单和可信库筛选提供依据。

## 0. 作用范围与输入

- 源表：`public."网优cell项目_清洗补齐库_v1"`
- 这一阶段只看 **5 个核心 PLMN**：
  - `46000`（中国移动）
  - `46001`（中国联通）
  - `46011`（中国电信）
  - `46015`（中国广电）
  - `46020`（中国移动铁路专网）
- 关键字段：
  - `运营商id`：PLMN
  - `原始lac`：十进制表示的 LAC/TAC；需要派生出 16 进制形式
  - `tech`：制式标签（2G/3G/4G/5G）

> 后续步骤（北京位置过滤、时间/访问量过滤）不在本文件中展开，本文件只聚焦 LAC 格式与异常。

---

## 1. 构建“LAC 专用库”视图（含 10 进制 / 16 进制版本）

### 1.1 设计目标

从源表中抽取 5 个核心 PLMN，并对每行生成：

- `lac_dec`：LAC 的十进制整型；
- `lac_hex`：LAC 的 16 进制字符串（大写）；
- `hex_len`：16 进制长度（判断 4G / 5G / 其他用途）；
- `tech_norm` / `tech_bucket`：统一后的制式分类（4G/5G，2G/3G，其他）；
- `lac_status`：LAC 正常 / 异常标签。

### 1.2 视图定义（建议）

```sql
CREATE OR REPLACE VIEW public.v_lac_core_laconly AS
SELECT
  t."运营商id",
  t.tech,
  lower(t.tech) AS tech_norm,
  CASE
    WHEN lower(t.tech) IN ('4g','5g') THEN '4G_5G'
    WHEN lower(t.tech) IN ('2g','3g') THEN '2G_3G'
    ELSE 'OTHER'
  END AS tech_bucket,

  t."原始lac"        AS lac_raw,

  CASE
    WHEN t."原始lac" IS NULL OR btrim(t."原始lac") = '' THEN 'NULL_OR_EMPTY'
    WHEN btrim(t."原始lac") IN ('0','-1')              THEN 'EXPLICIT_INVALID_0_-1'
    WHEN btrim(t."原始lac") !~ '^[0-9]+$'              THEN 'NON_NUMERIC'
    ELSE 'NUMERIC_OK'
  END AS lac_status,

  -- 十进制 LAC（仅对 NUMERIC_OK 的行有效）
  CASE
    WHEN t."原始lac" IS NOT NULL
     AND btrim(t."原始lac") <> ''
     AND btrim(t."原始lac") ~ '^[0-9]+$'
    THEN t."原始lac"::bigint
    ELSE NULL
  END AS lac_dec,

  -- 十六进制 LAC（大写）
  CASE
    WHEN t."原始lac" IS NOT NULL
     AND btrim(t."原始lac") <> ''
     AND btrim(t."原始lac") ~ '^[0-9]+$'
    THEN upper(to_hex(t."原始lac"::bigint))
    ELSE NULL
  END AS lac_hex,

  CASE
    WHEN t."原始lac" IS NOT NULL
     AND btrim(t."原始lac") <> ''
     AND btrim(t."原始lac") ~ '^[0-9]+$'
    THEN char_length(to_hex(t."原始lac"::bigint))
    ELSE NULL
  END AS hex_len

FROM public."网优cell项目_清洗补齐库_v1" t
WHERE t."运营商id" IN ('46000','46001','46011','46015','46020');
```

> 有了这个视图，就可以在不改动原始表的前提下，对 LAC 做统一格式化、异常标注、制式分类。

---

## 2. 异常 LAC 检测结果（在 5 个核心 PLMN 内）

### 2.1 异常规则说明

当前阶段将以下情况视为“异常 LAC”：

- `NULL_OR_EMPTY`：`原始lac` 为 NULL 或空字符串；
- `EXPLICIT_INVALID_0_-1`：显式异常标记，如 `0` / `-1`；
- `NON_NUMERIC`：包含非数字字符（如字母、符号等）。

在 5 个核心 PLMN 内实际统计结果：

```sql
WITH core AS (
  SELECT "运营商id", tech, "原始lac"
  FROM public."网优cell项目_清洗补齐库_v1"
  WHERE "运营商id" IN ('46000','46001','46011','46015','46020')
)
SELECT
  CASE
    WHEN "原始lac" IS NULL OR btrim("原始lac") = '' THEN 'NULL_OR_EMPTY'
    WHEN btrim("原始lac") IN ('0','-1')            THEN 'EXPLICIT_INVALID_0_-1'
    WHEN btrim("原始lac") !~ '^[0-9]+$'            THEN 'NON_NUMERIC'
    ELSE 'NUMERIC_OK'
  END AS lac_status,
  COUNT(*) AS cnt
FROM core
GROUP BY lac_status
ORDER BY cnt DESC;
```

统计结果（5 个 PLMN 合并）：

- `NUMERIC_OK`：75,400,766 行
- `NULL_OR_EMPTY`：350,108 行
- `EXPLICIT_INVALID_0_-1`：0 行
- `NON_NUMERIC`：0 行

> 结论：在核心 5 个 PLMN 中，LAC 的问题主要是“缺失 / 为空（约 35 万行）”，几乎没有 `0` / `-1` / 非数字情况。  
> 下一步可以直接从分析中剔除 `lac_status <> 'NUMERIC_OK'` 的记录。

---

## 3. LAC 16 进制长度分布（区分 4G / 5G / 其他）

根据行业规范：

- **4G LAC/TAC**：通常为 **4 位 16 进制**（16 bit）；
- **5G TAC**：通常为 **6 位 16 进制**（24 bit）。

我们对 `NUMERIC_OK` 的记录，统计 `hex_len` 分布：

```sql
WITH core AS (
  SELECT "运营商id", "原始lac"
  FROM public."网优cell项目_清洗补齐库_v1"
  WHERE "运营商id" IN ('46000','46001','46011','46015','46020')
    AND "原始lac" IS NOT NULL
    AND btrim("原始lac") <> ''
)
SELECT "运营商id",
       char_length(to_hex("原始lac"::bigint)) AS hex_len,
       COUNT(*) AS cnt
FROM core
GROUP BY "运营商id", hex_len
ORDER BY "运营商id", hex_len;
```

关键结果（按 PLMN 拆分）：

- `46000`（移动）
  - hex_len = 3：865 行（极少）
  - hex_len = 4：17,803,247 行（主要是 4G / 2G/3G 传统 LAC）
  - hex_len = 5：98,991 行
  - hex_len = 6：24,408,382 行（典型 5G TAC）
- `46001`（联通）
  - hex_len = 3：243,387 行
  - hex_len = 4：8,291,907 行
  - hex_len = 5：11,509,117 行
  - hex_len = 6：1,900,443 行
- `46011`（电信）
  - hex_len = 3：51,391 行
  - hex_len = 4：5,339,600 行
  - hex_len = 5：4,821,826 行
  - hex_len = 6：646,755 行
- `46015`（广电）
  - hex_len = 3：1 行
  - hex_len = 4：165,568 行
  - hex_len = 5：1,508 行
  - hex_len = 6：117,700 行
- `46020`（铁路专网）
  - hex_len = 3：2 行
  - hex_len = 4：76 行

> 初步建议：  
> - `hex_len = 4` → 归为 **4G/传统 LAC 段**；  
> - `hex_len = 6` → 归为 **5G TAC 段**；  
> - `hex_len IN (3,5)` → 归为 **OTHER_LEN**（格式上可疑，后续重点排查）。  
> 可以在 `v_lac_core_laconly` 上再加一列 `len_bucket`，做三类划分。

**运营商差异小结（重要）：**

- 对 **中国移动 46000** 来说，数据基本符合“4 位 hex 为 4G 段、6 位 hex 为 5G 段”的直觉规律：  
  - 4 位 hex 主要对应 4G/传统 LAC；  
  - 6 位 hex 主要对应 5G TAC；  
  - 3/5 位数量很少，可视为异常或特殊编码。
- 对 **中国联通 46001** 和 **中国电信 46011** 来说，大量 LAC 在 **5 位 hex**，长度分布与移动明显不同，**不能简单套用“4=4G、6=5G”的规则**，需要单独为联通/电信设计判断逻辑。

---

## 4. 4G/5G vs 2G/3G vs 其他：按 tech 归类（重点看 46000 / 46001 / 46011）

在视图中，我们按 `tech` 做了归一化：

- `tech_bucket = '4G_5G'`：`tech` 为 4G 或 5G；
- `tech_bucket = '2G_3G'`：`tech` 为 2G 或 3G（含大小写差异，如 `3g`）；
- `tech_bucket = 'OTHER'`：其它值（当前 5 个 PLMN 内实际统计结果中几乎不存在）。

统计 SQL（只看 46000 / 46001 / 46011）：

```sql
WITH core AS (
  SELECT "运营商id", tech
  FROM public."网优cell项目_清洗补齐库_v1"
  WHERE "运营商id" IN ('46000','46001','46011')
), norm AS (
  SELECT "运营商id", lower(tech) AS tech_low FROM core
), bucket AS (
  SELECT
    "运营商id",
    CASE
      WHEN tech_low IN ('4g','5g') THEN '4G_5G'
      WHEN tech_low IN ('2g','3g') THEN '2G_3G'
      ELSE 'OTHER'
    END AS tech_bucket,
    COUNT(*) AS cnt
  FROM norm
  GROUP BY "运营商id", tech_bucket
)
SELECT
  b."运营商id",
  b.tech_bucket,
  b.cnt,
  ROUND(100.0 * b.cnt / SUM(b.cnt) OVER (PARTITION BY b.\"运营商id\"), 4) AS pct
FROM bucket b
ORDER BY b.\"运营商id\", b.tech_bucket;
```

结果（核心 3 个 PLMN）：

- `46000`（移动）
  - `4G_5G`：42,462,777 行，占 **99.9186%**
  - `2G_3G`：34,572 行，占 **0.0814%**
- `46001`（联通）
  - `4G_5G`：22,015,756 行，占 **99.8603%**
  - `2G_3G`：30,788 行，占 **0.1397%**
- `46011`（电信）
  - `4G_5G`：10,910,334 行，占 **99.8980%**
  - `2G_3G`：11,141 行，占 **0.1020%**

> 结论：对 46000 / 46001 / 46011 而言，**当前数据几乎完全是 4G/5G（约 99.9%）**，2G/3G 占比极低（约 0.1%）。  
> 因此后续可以把 2G/3G 统一视为“边缘补充数据”，重点放在 4G/5G 的 LAC/TAC 分布上。

---

## 5. 异常“大流量 LAC”识别

在剔除 `NULL_OR_EMPTY` 后，我们对 5 个核心 PLMN 的数据，按 `(运营商id, lac_dec/lac_hex)` 统计访问量，并取 TOP N：

```sql
WITH base AS (
  SELECT "运营商id", "原始lac"
  FROM public."网优cell项目_清洗补齐库_v1"
  WHERE "运营商id" IN ('46000','46001','46011','46015','46020')
    AND "原始lac" IS NOT NULL
    AND btrim("原始lac") <> ''
)
SELECT
  "运营商id",
  "原始lac"::bigint AS lac_dec,
  upper(to_hex("原始lac"::bigint)) AS lac_hex,
  char_length(to_hex("原始lac"::bigint)) AS hex_len,
  COUNT(*) AS cnt
FROM base
GROUP BY "运营商id", lac_dec, lac_hex, hex_len
ORDER BY cnt DESC
LIMIT 20;
```

TOP 20 结果示例（全部来自 5 个核心 PLMN，且 `hex_len = 6`，典型 5G TAC 段）：

| 运营商 | lac_dec  | lac_hex | hex_len | 记录数 cnt |
|--------|----------|---------|---------|-----------|
| 46000  | 2097287  | 200087  | 6       | 378,816   |
| 46000  | 2097179  | 20001B  | 6       | 369,544   |
| 46001  | 2336002  | 23A502  | 6       | 363,833   |
| 46000  | 2097226  | 20004A  | 6       | 356,024   |
| 46000  | 2097237  | 200055  | 6       | 329,092   |
| 46000  | 2408465  | 24C011  | 6       | 328,870   |
| 46000  | 2097249  | 200061  | 6       | 328,631   |
| 46000  | 2097239  | 200057  | 6       | 322,165   |
| 46000  | 2229519  | 22050F  | 6       | 315,409   |
| 46000  | 2097164  | 20000C  | 6       | 314,489   |
| ...    | ...      | ...     | ...     | ...       |

> 这些 LAC/TAC 的访问量远高于平均水平，且多为 6 位 16 进制（5G 段），与之前识别的“2G+5G 异常组中的 514 个 LAC ID”（如 `2336002`, `2097287`, `2097179` 等）高度重合，**极有可能是虚拟/默认值**。  
> 建议：在后续的“可信库”构建中，把这类 TOP 高流量 LAC 列入重点审查 / 黑名单候选。

---

## 6. 总结：本阶段输出与下一步

1. 已基于 5 个核心 PLMN 设计了 `v_lac_core_laconly` 视图：
   - 为每条记录生成 `lac_dec` / `lac_hex` / `hex_len`；
   - 标注 `lac_status`（正常 / 异常）；
   - 按 `tech` 归类为 `4G_5G`、`2G_3G`、`OTHER`。
2. 异常 LAC 情况：
   - 核心 PLMN 内主要问题是 **NULL/空值（约 35 万行）**；
   - 基本不存在 `0`、`-1`、非数字 LAC（这些更多出现在非核心 PLMN 中）。
3. 长度与制式（注意运营商差异）：
   - **仅对 46000（移动）**，可以用 `hex_len = 4` 近似表示 **4G/传统 LAC**，`hex_len = 6` 近似表示 **5G TAC**，`hex_len IN (3,5)` 归为 **Other/可疑长度段**；
   - 对 **46001（联通）/46011（电信）**，由于存在大量 5 位 hex 的 LAC，**不能简单用长度直接对应制式**，长度只能作为辅助特征，需要结合运营商自身规则单独建模；
   - 从 `tech` 维度看，对 46000/46001/46011 而言，`4G_5G` 占比约 **99.9%**，`2G_3G` 仅约 **0.1%**。
4. 异常高流量 LAC：
   - TOP LAC 几乎都是 6 位 16 进制，访问量几十万级；
   - 与之前识别的“虚拟/黑洞” LAC 高度重合，应列为后续重点排查对象。
5. 4G/5G 跨运营商 LAC 重合情况（基于去重 LAC）：
   - 4G：将移动+广电+铁路（46000/46015/46020）作为一组，联通+电信（46001/46011）作为一组时，4G 去重 LAC 分别为 7,742 和 8,646 个，交集为 1,774 个；约占移动组 22.9%、联通电信组 20.5%。这不是“共网”，而是因为 4 位 16 进制 LAC 空间有限，不同系统间编码自然大量碰撞。
   - 5G：同样两组在 5G 上去重 LAC 为 2,416 和 1,032 个，交集仅 71 个；约占移动组 2.9%、联通电信组 6.9%。由于 5G TAC 扩展到 6 位 16 进制，不同系统间可以采用各自编码，碰撞概率显著降低。

下一步（你下一次要做的）：

- 在此 LAC 专用库基础上，继续细化：
  - LAC 格式与异常值的更细分类（如专门列出 3 位 / 5 位 hex 段的黑名单规则）；
  - 结合北京 GPS 范围过滤、时间窗口与访问量阈值，构建真正的“LAC 可信库 v1”。 
