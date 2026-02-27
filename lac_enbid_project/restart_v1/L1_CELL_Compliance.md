# L1-CELL 合规规则（格式阶段 / restart_v1）

> 目的：在 L1-LAC 合规数据的基础上，先专注于 **`cell_id` 的格式合法性**，按“运营商两大组 + 制式 2/3G / 4G / 5G / 其他”的切片，找出明显不合法或可疑的 `cell_id`，为后续范围/模式/GPS 合规打基础。

本文件只覆盖 **格式层面的第一阶段**；范围/数值区间和 `(运营商id, LAC, cell_id)` 组合模式将在后续阶段补充。

---

## 1. 数据范围与视角

### 1.1 关注的 5 个核心运营商（与 L1-LAC 一致）

- `46000`：中国移动  
- `46001`：中国联通  
- `46011`：中国电信  
- `46015`：中国广电  
- `46020`：中国移动（铁路专网）

所有 L1-CELL 分析都只看这 5 个 PLMN。

### 1.2 运营商两大组（用于交叉验证）

按照之前 LAC 的习惯，把 5 个 PLMN 拆成两组，只是为了 **对比/验证**，不直接作为合规规则的一部分：

- **组 A（移动系）**：`46000` + `46015` + `46020`  
- **组 B（联通+电信）**：`46001` + `46011`

> 原则：**`cell_id` 的“合不合规”主要由制式（2/3G / 4G / 5G）决定，而不是运营商本身。**  
> 把运营商拆成两组，只是为了“同一制式在不同运营商系下的分布是否相似”，方便发现特殊/异常情况。

在 SQL 中，可定义运营商组字段 `op_group`：

```sql
CASE
  WHEN t."运营商id" IN ('46000','46015','46020') THEN 'GROUP_A_CMCC_FAMILY'
  WHEN t."运营商id" IN ('46001','46011')        THEN 'GROUP_B_CU_CT'
  ELSE 'OTHER'
END AS op_group
```

### 1.3 制式拆分：2/3G vs 4G vs 5G vs 其他

在 L1-LAC 中，我们使用了 `tech_bucket = '4G_5G' / '2G_3G' / 'OTHER'`。  
在 CELL 阶段，为了更精细地区分格式/范围，建议拆成四类：

```sql
lower(t.tech) AS tech_norm,
CASE
  WHEN tech_norm IN ('2g','3g') THEN '2G_3G'
  WHEN tech_norm = '4g'         THEN '4G'
  WHEN tech_norm = '5g'         THEN '5G'
  ELSE 'OTHER'
END AS tech_class
```

- 后续所有 cell 格式统计都以 `(op_group, tech_class)` 为基本切片；
- 核心目标：**同一 `tech_class` 下，两大运营商组的分布应该“长得类似”，否则需要排查。**

---

## 2. 构建 L1-CELL 格式分析视图 `v_cell_core_cellonly`

### 2.1 设计目标

在不破坏 L1-LAC 结构的前提下，构建一个只面向 cell 的分析视图：

- 仅保留 **L1-LAC 数值合规** 的记录（`原始lac` 为纯数字）；
- 衍生：
  - 运营商组：`op_group`；
  - 制式类别：`tech_class`；
  - `cell_id` 的原始字符串版本：`cell_raw`；
  - `cell_status_fmt`：cell 的 **格式合规标签**（NULL/空、显式无效值、非纯数字、纯数字 OK）；
  - `cell_dec` / `cell_dec_len`：纯数字 cell 的十进制数值及长度。

### 2.2 视图定义（建议）

```sql
CREATE OR REPLACE VIEW public.v_cell_core_cellonly AS
SELECT
  t."运营商id",
  CASE
    WHEN t."运营商id" IN ('46000','46015','46020') THEN 'GROUP_A_CMCC_FAMILY'
    WHEN t."运营商id" IN ('46001','46011')        THEN 'GROUP_B_CU_CT'
    ELSE 'OTHER'
  END AS op_group,

  t.tech,
  lower(t.tech) AS tech_norm,
  CASE
    WHEN lower(t.tech) IN ('2g','3g') THEN '2G_3G'
    WHEN lower(t.tech) = '4g'         THEN '4G'
    WHEN lower(t.tech) = '5g'         THEN '5G'
    ELSE 'OTHER'
  END AS tech_class,

  -- 保留与 L1-LAC 一致的 LAC 字段（方便后续做 (运营商id, LAC, cell_id) 组合分析）
  t."原始lac" AS lac_raw,

  -- cell_id 原始值统一转成文本，避免类型差异
  t.cell_id::text AS cell_raw,

  -- cell_id 的“格式合法性”标签（只看是否为纯数字/缺失/明显无效）
  CASE
    WHEN t.cell_id IS NULL OR btrim(t.cell_id::text) = '' THEN 'NULL_OR_EMPTY'
    WHEN btrim(t.cell_id::text) IN ('0','-1')             THEN 'EXPLICIT_INVALID_0_-1'
    WHEN btrim(t.cell_id::text) !~ '^[0-9]+$'             THEN 'NON_NUMERIC'
    ELSE 'NUMERIC_OK'
  END AS cell_status_fmt,

  -- 十进制 cell_id（仅对 NUMERIC_OK 的行有效）
  CASE
    WHEN t.cell_id IS NOT NULL
     AND btrim(t.cell_id::text) <> ''
     AND btrim(t.cell_id::text) ~ '^[0-9]+$'
    THEN t.cell_id::bigint
    ELSE NULL
  END AS cell_dec,

  -- 十进制位数（只看去掉前后空格后的长度）
  CASE
    WHEN t.cell_id IS NOT NULL
     AND btrim(t.cell_id::text) <> ''
     AND btrim(t.cell_id::text) ~ '^[0-9]+$'
    THEN char_length(btrim(t.cell_id::text))
    ELSE NULL
  END AS cell_dec_len

FROM public."网优cell项目_清洗补齐库_v1" t
WHERE t."运营商id" IN ('46000','46001','46011','46015','46020')
  -- 只在 L1-LAC “数值合规”范围内做 CELL 研究：原始 LAC 必须是纯数字
  AND t."原始lac" IS NOT NULL
  AND btrim(t."原始lac") <> ''
  AND btrim(t."原始lac") ~ '^[0-9]+$';
```

> 说明：  
> - 这个视图在逻辑上等价于“在 `v_lac_L1_compliant` 的输入范围上，额外附加 `cell_id` 的格式信息”；  
> - 暂时 **不在视图里做 cell 范围/长度的硬过滤**，只标记格式状态，方便后续多轮迭代。

---

## 3. 合规规则一：cell_id 基本格式合法性（数值/缺失）

### 3.1 格式规则定义

在本阶段，我们只区分以下几类：

- `NULL_OR_EMPTY`：`cell_id` 为 NULL 或空字符串；
- `EXPLICIT_INVALID_0_-1`：显式无效值，如 `0` / `-1`（可后续扩展更多默认值，如 `999999` 等）；
- `NON_NUMERIC`：包含非数字字符（字母、点号、分隔符等），即不满足 `^[0-9]+$`；
- `NUMERIC_OK`：去掉空格后是纯数字。

其中：

- **“明显不合法”** = `NULL_OR_EMPTY` + `EXPLICIT_INVALID_0_-1` + `NON_NUMERIC`；  
- **“格式层面合规候选”** = `NUMERIC_OK`。

对应统计 SQL 示例：

```sql
SELECT
  op_group,
  tech_class,
  cell_status_fmt,
  COUNT(*) AS cnt,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY op_group, tech_class), 4) AS pct
FROM public.v_cell_core_cellonly
GROUP BY op_group, tech_class, cell_status_fmt
ORDER BY op_group, tech_class, cell_status_fmt;
```

期望使用方式：

- 对每个 `(op_group, tech_class)`，观察 `cell_status_fmt` 的分布；  
- 如果某个制式在某一运营商组下出现异常多的 `NON_NUMERIC` / `EXPLICIT_INVALID_0_-1`，而在另一组下几乎全是 `NUMERIC_OK`，则该部分 `cell_id` 需要重点排查。

### 3.2 建议的“格式合规子集”视图（可选）

在只看格式的阶段，可以先定义一个 **L1-CELL-Format 合规子集**：

```sql
CREATE OR REPLACE VIEW public.v_cell_L1_format_ok AS
SELECT *
FROM public.v_cell_core_cellonly
WHERE cell_status_fmt = 'NUMERIC_OK'
  AND cell_dec > 0;
```

> 注意：  
> - 这里仍然只是“**格式合规**”（纯数字且 >0），不对数值上限、长度是否合理做判断；  
> - 后续 L1-CELL 的“范围合规”“组合合规”都会在 `v_cell_L1_format_ok` 的基础上继续筛选。

---

## 4. 合规规则二：按运营商组 + 制式的长度分布

### 4.1 统计长度分布（按 `(op_group, tech_class)` 切片）

在只保留 `NUMERIC_OK` 的前提下，统计十进制长度分布：

```sql
SELECT
  op_group,
  tech_class,
  cell_dec_len,
  COUNT(*) AS cnt,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY op_group, tech_class), 4) AS pct
FROM public.v_cell_core_cellonly
WHERE cell_status_fmt = 'NUMERIC_OK'
GROUP BY op_group, tech_class, cell_dec_len
ORDER BY op_group, tech_class, cell_dec_len;
```

分析要点：

- 对每个 `tech_class`（2G_3G / 4G / 5G / OTHER），看两大运营商组在 `cell_dec_len` 上的主流区间；  
- 如果同一制式在两组上的主流位数高度一致，可以认为“**位数分布主要由制式决定，与运营商无关**”，符合预期；  
- 若某组在某个制式下出现大量极短（如 1–2 位）或极长（>15 位）的 `cell_id`，而另一组没有，则可作为异常候选。

### 4.2 后续可引入的长度合规标签（暂不落地）

在明确实际分布后，可以为每个 `tech_class` 定义一个“主流长度区间”，例如（仅为示意，具体区间需根据真实数据调整）：

- `2G_3G`：期望 `cell_dec_len` ∈ [1,5]；  
- `4G`：期望 `cell_dec_len` 主要集中在 7–9 位；  
- `5G`：期望 `cell_dec_len` 主要集中在 9–11 位。

可在视图上增加一个长度标签：

```sql
CASE
  WHEN cell_status_fmt <> 'NUMERIC_OK' THEN 'FMT_INVALID'
  WHEN tech_class = '2G_3G' AND cell_dec_len BETWEEN 1 AND 5 THEN 'LEN_OK'
  WHEN tech_class = '4G'    AND cell_dec_len BETWEEN 6 AND 10 THEN 'LEN_OK'
  WHEN tech_class = '5G'    AND cell_dec_len BETWEEN 8 AND 12 THEN 'LEN_OK'
  ELSE 'LEN_SUSPECT'
END AS cell_len_flag
```

> 说明：  
> - 上述区间只是“示意占位”，需要在真实分布统计完成后再精细调整；  
> - 真正落地前，建议先在 SQL 里只做统计，不写入视图，避免过早锁死规则。

---

## 5. 当前阶段的结论与下一步

### 5.1 已完成的设计（格式阶段）

1. 明确了 L1-CELL 格式阶段的 **数据范围与视角**：
   - 只使用 5 个核心 PLMN；  
   - 运营商拆成两大组 A/B 仅用于对比验证；  
   - 制式拆分为 `2G_3G` / `4G` / `5G` / `OTHER`。
2. 设计并给出了建议视图 `v_cell_core_cellonly`：
   - 在 L1-LAC 数值合规范围内，引入 `op_group` / `tech_class`；  
   - 为每条记录生成 `cell_status_fmt` / `cell_dec` / `cell_dec_len` 等格式特征。
3. 定义了 cell 的 **格式合法性规则**：
   - 把 `cell_id` 划分为 `NULL_OR_EMPTY` / `EXPLICIT_INVALID_0_-1` / `NON_NUMERIC` / `NUMERIC_OK`；  
   - 给出按 `(op_group, tech_class)` 统计格式分布的 SQL；  
   - 提出格式合规子视图 `v_cell_L1_format_ok`（只保留 `NUMERIC_OK` 且 `cell_dec>0`）。
4. 给出了按 `(op_group, tech_class)` 统计 **十进制长度分布** 的方法，为后续长度/范围规则提供依据。

### 5.2 建议的下一步（还未在本文件中展开）

1. 在数据库中实际跑通：
   - 创建 `v_cell_core_cellonly` 和 `v_cell_L1_format_ok`；  
   - 跑一遍格式分布和长度分布 SQL，把每个 `(op_group, tech_class)` 的结果记录下来。
2. 基于真实分布，补充 **L1-CELL 范围与模式规则**：
   - 为每个制式（2/3G、4G、5G）设定合理的 `cell_dec` 区间和典型长度；  
   - 识别明显超范围或“默认值”型的 cell（类似 LAC 阶段的 514 个黑洞 LAC）；  
   - 结合 `(运营商id, lac_raw, cell_id)` 的组合分布，找出“跨 LAC / 跨运营商大量重复”的可疑 cell_id。
3. 在上述基础上，进一步定义 “`v_cell_L1_compliant`”（格式 + 范围 + 组合都合规）的视图，为 L1-GPS 和 L2 分析提供输入。

本文件到此为止，完成了 L1-CELL 的“格式阶段”设计。后续每轮新的发现/规则，可以继续在本文件中追加章节。 

---

## 6. 当前实际规则与异常 cell 候选（v1 记录）

> 本小节用于记录当前在数据库中实际跑出来的结论，方便后续迭代时对照。

### 6.1 当前格式规则（实际数据验证）

在 `public.v_cell_core_cellonly` 视图上（5 个核心 PLMN + LAC 数值合规）实际统计结果：

- 对 4G / 5G：
  - 几乎所有 `cell_id` 都是 `NUMERIC_OK`（非空、纯数字、>0）；
  - 仅有极少量 `EXPLICIT_INVALID_0_-1`（0 或 -1）：  
    - 组 A（移动系：46000/46015/46020）  
      - 4G：`NUMERIC_OK` ≈ 17,969,701 行；`EXPLICIT_INVALID_0_-1` = 58 行；  
      - 5G：`NUMERIC_OK` ≈ 24,606,296 行；`EXPLICIT_INVALID_0_-1` = 542 行。  
    - 组 B（联通+电信：46001/46011）  
      - 4G：`NUMERIC_OK` ≈ 13,926,229 行；`EXPLICIT_INVALID_0_-1` = 56 行；  
      - 5G：`NUMERIC_OK` ≈ 18,860,000 行；`EXPLICIT_INVALID_0_-1` = 201 行。
  - 在当前数据范围内，4G/5G 没有出现 `NULL_OR_EMPTY` 或 `NON_NUMERIC` 的 `cell_id`。
- 对 2G/3G：
  - 两大运营商组中，2G/3G 的 `cell_id` **全部是 0 或 -1**（`EXPLICIT_INVALID_0_-1`），没有一条是 `NUMERIC_OK`；
  - 这印证了：当前数据里 2/3G 的 cell_id 在格式层面完全不可用，可以统一视为“无效占位值”。

结合前面的长度分布统计：

- 4G：`cell_dec_len` 主体集中在 7–9 位（两组都如此，比例略有差别）；
- 5G：`cell_dec_len` 主体集中在 9–11 位：  
  - 移动系：10 位为绝对主力，少量 9/11 位；  
  - 联通+电信：9/10 位都大量存在，11 位较少。

**当前可以记录的“格式规则 v1”是：**

- 2G/3G：`cell_id` 几乎全部为 `0/-1`，视为格式无效；  
- 4G/5G：只要 `cell_status_fmt = 'NUMERIC_OK' AND cell_dec > 0`，在格式和位数上基本都合规；
- 真正的异常主要来自：
  - 个别特定数值（如溢出型默认值）；  
  - 以及后续在“范围 + 组合”层面发现的异常模式。

### 6.2 典型溢出型 cell_id：2147483647（0x7FFFFFFF）

在 5G 的 `NUMERIC_OK` cell 中，发现一个非常典型的“十六进制 -1 / 溢出”型值：

- `cell_dec = 2147483647`（十进制），即 `0x7FFFFFFF`。
- 在 5G 下，该值的频次非常高（全表统计）：  
  - 组 A（移动系）5G：57,778 条；  
  - 组 B（联通+电信）5G：4,022 条。

使用对原始表的 1% 抽样（`TABLESAMPLE SYSTEM (1)`）做 `(运营商id, cell_id, 原始lac)` 组合检查：

- 对 5G 且 `cell_id = 2147483647` 的样本：
  - `46000`（移动）：样本中 583 条记录，覆盖约 **204 个不同 LAC**；  
  - `46001`（联通）：样本中 24 条记录，覆盖约 **6 个不同 LAC**；  
  - `46011`（电信）：样本中 10 条记录，覆盖约 **3 个不同 LAC**。

在同一运营商内，**同一个 cell_id 对应大量不同 LAC**，与“一个物理小区不会跨多个 LAC”的常识严重矛盾。结合其数值刚好是 32 位整型最大值，可以合理地把：

- `tech_class = '5G' AND cell_dec = 2147483647`

视为 **“溢出/默认 cell_id”**，在后续 L1-CELL 合规规则中列入黑名单（例如打标 `CELL_OVERFLOW_DEFAULT`，并从合规子集中剔除）。

### 6.3 其它 5G 大数 TOP cell_id 的初步观察

对 5G 的 TOP 高频 `cell_id`（10–11 位大数，例如 `5839671298`, `47261081712`, `9548546067` 等），在 1% 抽样下检查 `(运营商id, cell_id, 原始lac)` 组合：

- 大部分值在同一运营商内只对应 **1 个 LAC**（样本中的 `sample_lac_cnt = 1`），例如：
  - 移动系：`5839671298`, `47261081712`, `5751177217`, `5719080961`, `5668331524` 等；  
  - 联通/电信：`551542785`, `9548546066`, `9548546067`, `13562122242` 等。
- 个别值在样本中已出现 **跨多个 LAC** 的迹象（`sample_lac_cnt > 1`），例如：
  - `5668331524` 在 `46000` 下样本中覆盖 2 个 LAC；  
  - `571379714` 在 `46001` 下样本中覆盖 2 个 LAC；  
  - `9562177557` 在 `46001` 下样本中覆盖 2 个 LAC。

由于上述分析基于 1% 抽样，这些 `sample_lac_cnt = 1` 的值在全量数据中是否也严格“一 cell 对一 LAC”仍需后续在数据库中跑全量检查；但可以初步判断：

- **2147483647 明显是无效值**（跨大量 LAC 的溢出默认值）；  
- 其它大数 TOP cell_id 更像是运营商内部编码（如 gNB ID + 小区号 拼接）产生的合法取值：
  - 其数值大，但在同运营商内多数只绑定一个 LAC；  
  - 在不同运营商间出现碰撞是可以接受的（不同系统的编码空间相互独立）。

因此在当前阶段，我们只把 `2147483647` 明确纳入 L1-CELL 异常列表；  
其它大数 TOP cell_id 先作为“关注名单”，后续在做 **“cell_id 是否跨多个 LAC（同运营商内）”的全量统计** 和 GPS 分布验证后再决定是否加入黑名单。 

