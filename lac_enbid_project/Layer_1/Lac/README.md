# Layer_1 / Lac：L1-LAC 合规规则与结论

> 作用：在第 0 层原始数据解析的基础上，为第 1 层构建一套 **“LAC 合规规则”**，从原始数据中抽取“尽量合规”的 LAC 子集，为后续 CELL/GPS 合规和 Layer_2 分析提供稳定基础。

本文件是 L1-LAC 节点的完整说明，不依赖其他文档即可理解和使用。

---

## 1. 数据范围与视图定义

### 1.1 关注的 5 个核心运营商

在 L1-LAC 阶段，只关注以下 5 个国内 PLMN：

- `46000`：中国移动  
- `46001`：中国联通  
- `46011`：中国电信  
- `46015`：中国广电  
- `46020`：中国移动（铁路专网）

后续所有合规规则，都以这 5 个运营商的记录为对象。

### 1.2 LAC 专用视图 `v_lac_core_laconly`

在原始表 `public."网优cell项目_清洗补齐库_v1"` 的基础上，定义一个只针对 LAC 的视图，用于派生必要字段并标记异常：

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

  CASE
    WHEN t."原始lac" IS NOT NULL
     AND btrim(t."原始lac") <> ''
     AND btrim(t."原始lac") ~ '^[0-9]+$'
    THEN t."原始lac"::bigint
    ELSE NULL
  END AS lac_dec,

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

L1-LAC 的所有统计与规则皆基于此视图。

---

## 2. 合规规则一：运营商 + 制式切片

### 2.1 制式归一化

通过 `tech_norm` 和 `tech_bucket`，把制式分成三个大类：

- `4G_5G`：`tech` 为 4G 或 5G；
- `2G_3G`：`tech` 为 2G 或 3G（含 `3g` 等大小写变体）；
- `OTHER`：其他写法或缺失。

对三个主运营商（46000/46001/46011）统计结果：

- 46000（移动）：  
  - `4G_5G` ≈ 42,462,777 行，占 **99.9186%**  
  - `2G_3G` ≈ 34,572 行，占 **0.0814%**
- 46001（联通）：  
  - `4G_5G` ≈ 22,015,756 行，占 **99.8603%**  
  - `2G_3G` ≈ 30,788 行，占 **0.1397%**
- 46011（电信）：  
  - `4G_5G` ≈ 10,910,334 行，占 **99.8980%**  
  - `2G_3G` ≈ 11,141 行，占 **0.1020%**

**L1 决策：**

- 主分析对象为 `4G_5G`，2G/3G 视为“边缘补充数据”，保留但不作为主要权重；
- `OTHER`（如有）默认视为“不合规”或“需单独分析”。

---

## 3. 合规规则二：LAC 基本合法性（数值/缺失）

在 5 个核心 PLMN 中，基于 `lac_status` 的统计结果：

- `NUMERIC_OK`：75,400,766 行  
- `NULL_OR_EMPTY`：350,108 行  
- `EXPLICIT_INVALID_0_-1`：0 行  
- `NON_NUMERIC`：0 行

**L1 决策：**

- `NUMERIC_OK` 视为“基本合规”的 LAC；  
- `NULL_OR_EMPTY` 视为“不合规”，从 L1-LAC 合规子集中统一剔除；  
- `0` / `-1` / 非数字在核心 PLMN 内几乎没有，如在扩展 PLMN 中出现，直接按“不合规”处理。

在此基础上，定义“L1-LAC 合规子集”视图：

```sql
CREATE OR REPLACE VIEW public.v_lac_L1_compliant AS
SELECT *
FROM public.v_lac_core_laconly
WHERE lac_status = 'NUMERIC_OK';
```

后续 L1-CELL / L1-GPS 合规则在 `v_lac_L1_compliant` 基础上继续筛选。

---

## 4. 合规规则三：LAC 十六进制长度与运营商差异

### 4.1 长度分布（hex_len）的关键结论

对 5 个 PLMN 的 `hex_len` 分布（只看 `NUMERIC_OK`）：

- 46000（移动）
  - 3 位：865 行  
  - 4 位：17,803,247 行  
  - 5 位：98,991 行  
  - 6 位：24,408,382 行
- 46001（联通）
  - 3 位：243,387 行  
  - 4 位：8,291,907 行  
  - 5 位：11,509,117 行  
  - 6 位：1,900,443 行
- 46011（电信）
  - 3 位：51,391 行  
  - 4 位：5,339,600 行  
  - 5 位：4,821,826 行  
  - 6 位：646,755 行
- 46015（广电）
  - 3 位：1 行  
  - 4 位：165,568 行  
  - 5 位：1,508 行  
  - 6 位：117,700 行
- 46020（铁路专网）
  - 3 位：2 行  
  - 4 位：76 行

### 4.2 运营商差异解读

- 对 **移动系（46000，含 46015/46020）**：
  - 4 位和 6 位 hex LAC 占绝大多数，3/5 位极少；  
  - 可以“近似”认为：  
    - 4 位 hex 对应 4G/传统 LAC 段；  
    - 6 位 hex 对应 5G TAC 段；  
    - 3/5 位为异常/特殊长度段（后续重点排查）。

- 对 **联通 46001 / 电信 46011**：
  - 5 位 hex LAC 数量巨大，长度分布明显不同于移动；  
  - **不能**简单用“4=4G、6=5G”的规则推断制式，`hex_len` 只能作为辅助特征，真正的制式判断仍依赖 `tech` 字段。

**L1 决策：**

- 在 L1 阶段，长度不作为硬性“合/不合规”标准，而是：  
  - 对移动系可用 `hex_len` 做强约束（优先选 4/6 位，标记 3/5 位为可疑）；  
  - 对联通/电信仅做“极端长度异常”检查（如 1 位、2 位、>6 位），当前数据中未见极端情况。

---

## 5. 4G/5G 跨运营商 LAC 重合的解释

为理解 LAC 共享/碰撞的背景，将运营商分成两组：

- **组 A（移动系）**：46000（移动） + 46015（广电） + 46020（铁路）  
- **组 B（联通+电信）**：46001（联通） + 46011（电信）

只看 `tech='4G'` 时（去重后的十进制 LAC）：

- 组 A：7,742 个不同 4G LAC  
- 组 B：8,646 个不同 4G LAC  
- 交集：1,774 个  
  - 占组 A：**22.9%**  
  - 占组 B：**20.5%**

只看 `tech='5G'` 时：

- 组 A：2,416 个不同 5G LAC/TAC  
- 组 B：1,032 个不同 5G LAC/TAC  
- 交集：71 个  
  - 占组 A：**2.94%**  
  - 占组 B：**6.88%**

**解释：**

- 4G 时代的 LAC（通常对应 4 位 16 进制）编码空间较小，不同运营商在全国范围内会用到相同的十进制 LAC 值，**自然会有约 20% 的“值重合”**，这不等于共网；  
- 5G 时代 TAC 扩展到 6 位 16 进制，可用空间大很多，各运营商可以采用独立编码，跨系统碰撞比例下降到个位数；  
- 因此：**不能用“LAC 是否共享”来判断运营商是否共用或位置是否可信，后续必须结合 `network_group`、`cell_id` 和 GPS 来判断真实小区。**

在 L1-LAC 阶段，这个结论主要用于提醒：  
**更关注制式、位置和时间维度，不以“共享 LAC 本身”作为数据质量好坏的唯一标准。**

---

## 6. L1-LAC 合规层的输出与后续衔接

### 6.1 当前 L1-LAC 输出视图

推荐的 L1-LAC 合规数据视图（起点版本）：

```sql
CREATE OR REPLACE VIEW public.v_lac_L1_compliant AS
SELECT *
FROM public.v_lac_core_laconly
WHERE lac_status = 'NUMERIC_OK';
```

若希望对移动系增加长度约束，可在此基础上定义一个更严格的视图：

```sql
CREATE OR REPLACE VIEW public.v_lac_L1_compliant_strict AS
SELECT *
FROM public.v_lac_core_laconly
WHERE lac_status = 'NUMERIC_OK'
  AND (
    -- 对移动系：优先保留 4/6 位，标记 3/5 位为可疑
    ("运营商id" IN ('46000','46015','46020') AND hex_len IN (4,6))
    OR
    -- 对联通/电信：先不以长度做硬约束，只要是 3~6 位都保留
    ("运营商id" IN ('46001','46011') AND hex_len BETWEEN 3 AND 6)
  );
```

后续 L1-CELL / L1-GPS 合规则可以直接在 `v_lac_L1_compliant` 或 `v_lac_L1_compliant_strict` 上继续做筛选。

### 6.2 与后续 L1-CELL / L1-GPS 的关系

- **L1-CELL 合规**：  
  - 在 L1-LAC 合规数据上，按 `(运营商id, LAC, cell_id)` 组合检查 cell_id 的范围和模式；  
  - 剔除明显异常的 cell_id 后，得到 “L1-LAC + L1-CELL” 双重合规子集。

- **L1-GPS 合规**：  
  - 再在“双重合规子集”上，用 GPS 分布规则（北京范围、飘移半径等）筛出位置稳定的 LAC/Cell；  
  - 得到 L1 三重合规数据，为 Layer_2 分析提供高质量样本。

到这里，L1-LAC 部分的合规规则与关键结论已经记录完毕，  
重启分析时，只需在数据库里重建上述视图，从 `v_lac_L1_compliant` / `v_lac_L1_compliant_strict` 开始继续向下做 CELL/GPS 和 Layer_2 即可。

