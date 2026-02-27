# Layer_1 / Cell：L1-CELL 合规规则与当前筛选方案（格式阶段）

> 作用：在 L1-LAC 合规数据的基础上，对 `cell_id` 做 **格式 + 已知无效值** 的第一轮筛选，得到一个“格式基本合规、剔除明显默认值/溢出值”的 L1-CELL 子集，为后续范围/模式/GPS 等更严格的规则打基础。  
> 同时，本目录也明确约定：**所有 ENBID / 基站 研究必须以 L1-CELL 合规视图为输入，并放在 `Layer_1/Enbid/` 目录中沉淀规则**，避免再把 ENBID 相关 SQL 散落在 `Agent_Workspace` 或根目录。

本文件是本次 `cell_id` 筛选的**唯一说明文档**，可以独立阅读：  
包含视图定义、规则说明以及具体操作步骤。  
后续所有基于 `cell_id` 推导 ENBID / 基站 ID 的研究，**统一遵守以下目录与主键约定**：

- 目录根：`Layer_1/Enbid/`（或 `Layer_1/基站/`，二者择一）；  
- 主键约定：以 `(运营商id, 原始lac, cell_id)` 作为 Cell 级别的基础键，ENBID 只作为派生聚合字段，不单独用作唯一标识。

---

## 1. 数据范围与基本视角

### 1.1 关注的运营商与输入表

- 源表：`public."网优cell项目_清洗补齐库_v1"`
- 本阶段只关注 **5 个核心 PLMN**：
  - `46000`：中国移动  
  - `46001`：中国联通  
  - `46011`：中国电信  
  - `46015`：中国广电  
  - `46020`：中国移动铁路专网

在 Cell 阶段，我们只在 **L1-LAC 数值合规** 的范围内研究 `cell_id`：

- 仅保留 `原始lac` 为非空且纯数字的记录（等价于 L1-LAC 中的 `NUMERIC_OK`）。

### 1.2 运营商分组与制式拆分

为方便对比不同运营商系的行为，我们引入“运营商组”和“制式类别”两个派生字段：

- 运营商组 `op_group`：
  - 组 A（移动系）：`46000` + `46015` + `46020` → `'GROUP_A_CMCC_FAMILY'`
  - 组 B（联通+电信）：`46001` + `46011` → `'GROUP_B_CU_CT'`
- 制式类别 `tech_class`：
  - `2G_3G`：`tech` 为 2G 或 3G（统一为小写后在 `('2g','3g')` 内）
  - `4G`：`tech_norm = '4g'`
  - `5G`：`tech_norm = '5g'`
  - `OTHER`：其它写法统一归为 `OTHER`

> 说明：  
> - **合规与否主要由制式决定，与运营商本身关系不大**；  
> - 把运营商拆成两组只是为了互相验证：同一制式在两组中应呈现类似的长度/格式分布。

---

## 2. 核心视图定义：`public.v_cell_core_cellonly`

### 2.1 设计目标

在不改变原始表结构的前提下，建立一个只面向 Cell 的分析视图，完成：

- 限定在 5 个核心 PLMN + LAC 数值合规范围内；
- 衍生：
  - 运营商组：`op_group`；
  - 制式类别：`tech_class`；
  - `cell_id` 的原始字符串：`cell_raw`；
  - `cell_status_fmt`：cell 的格式标签（空、0/-1、非数字、纯数字）；
  - `cell_dec` / `cell_dec_len`：十进制数值及十进制位数。

### 2.2 视图 SQL（需要在数据库中执行一次）

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

  -- LAC 原始字段，后面可以用来做 (运营商id, LAC, cell_id) 组合分析
  t."原始lac" AS lac_raw,

  -- 统一的 cell_id 文本形式
  t.cell_id::text AS cell_raw,

  -- cell_id 格式标签
  CASE
    WHEN t.cell_id IS NULL OR btrim(t.cell_id::text) = '' THEN 'NULL_OR_EMPTY'
    WHEN btrim(t.cell_id::text) IN ('0','-1')             THEN 'EXPLICIT_INVALID_0_-1'
    WHEN btrim(t.cell_id::text) !~ '^[0-9]+$'             THEN 'NON_NUMERIC'
    ELSE 'NUMERIC_OK'
  END AS cell_status_fmt,

  -- 纯数字 cell 的十进制值
  CASE
    WHEN t.cell_id IS NOT NULL
     AND btrim(t.cell_id::text) <> ''
     AND btrim(t.cell_id::text) ~ '^[0-9]+$'
    THEN t.cell_id::bigint
    ELSE NULL
  END AS cell_dec,

  -- 十进制位数
  CASE
    WHEN t.cell_id IS NOT NULL
     AND btrim(t.cell_id::text) <> ''
     AND btrim(t.cell_id::text) ~ '^[0-9]+$'
    THEN char_length(btrim(t.cell_id::text))
    ELSE NULL
  END AS cell_dec_len

FROM public."网优cell项目_清洗补齐库_v1" t
WHERE t."运营商id" IN ('46000','46001','46011','46015','46020')
  -- 只在 L1-LAC 数值合规范围内研究 cell（原始 LAC 必须是纯数字）
  AND t."原始lac" IS NOT NULL
  AND btrim(t."原始lac") <> ''
  AND btrim(t."原始lac") ~ '^[0-9]+$';
```

执行完上述 SQL 后，所有后续 Cell 规则都基于 `public.v_cell_core_cellonly` 这一视图展开。

---

## 3. 格式层面的实际结论（基于 `v_cell_core_cellonly`）

在 5 个 PLMN + LAC 数值合规范围内，格式统计给出的真实结论为：

1. **2G/3G：cell_id 完全不可用**
   - 两大运营商组中，`tech_class = '2G_3G'` 的记录里，`cell_id` 全部是 `0` 或 `-1`：  
     - `cell_status_fmt = 'EXPLICIT_INVALID_0_-1'`；  
     - 没有一条 `NUMERIC_OK`。
   - 结论：本轮 Cell 合规中，2G/3G 的 `cell_id` 可整体视为“无效占位值”，不参与 L1-CELL 合规子集的构建。

2. **4G/5G：格式基本全合规**
   - 在 4G/5G 下，大约 99.99% 的 `cell_id` 都是：
     - 非 NULL / 非空字符串；
     - 纯数字；
     - 正数。
   - 仅有极少量 `0/-1`：
     - 移动系：4G 中 58 条，5G 中 542 条；
     - 联通+电信：4G 中 56 条，5G 中 201 条。
   - 长度分布也符合常识：
     - 4G：`cell_dec_len` 主要集中在 7–9 位；
     - 5G：`cell_dec_len` 主要集中在 9–11 位（移动系以 10 位为主，联通/电信 9–10 位为主）。

因此，本轮 Cell 筛选的重点不是“4G/5G 的格式本身”，而是：

- 剔除明确的无效/默认值；
- 为后续的“数值范围 + (运营商id, LAC, cell_id) 组合 + GPS”留出干净的基础。

---

## 4. 已知无效值：溢出默认 cell_id（2147483647）

在 5G 的 `NUMERIC_OK` 记录中，发现一个典型的“溢出型默认值”：

- `cell_dec = 2147483647`，即十六进制 `0x7FFFFFFF`（32 位有符号整型最大值）。

这个值有两个明显特征：

1. **出现频次极高**
   - 移动系 5G：57,778 条；
   - 联通+电信 5G：4,022 条。

2. **同运营商内，一个 cell_id 对应大量 LAC**
   - 以 1% 抽样（`TABLESAMPLE SYSTEM (1)`）在原始表上检查 `(运营商id, cell_id, 原始lac)`：
     - `46000`（移动）：样本中 583 条，覆盖约 204 个不同 `原始lac`；
     - `46001`（联通）：样本中 24 条，覆盖约 6 个不同 `原始lac`；
     - `46011`（电信）：样本中 10 条，覆盖约 3 个不同 `原始lac`。
   - 同一运营商内，一个 `cell_id` 对应几十乃至上百个 LAC，和“物理 cell 不应跨多个 LAC”的常识矛盾，极有可能是核心/网管侧的“默认/错误上报值”。

基于上述两点，**本轮 L1-CELL 筛选中，明确把 5G 且 `cell_dec = 2147483647` 视为无效 cell**。

---

## 5. 本次 cell_id 筛选的操作方案（应如何实际使用）

本次在 L1-CELL 阶段，只做“格式 + 已知无效值”的第一轮筛选，目标是得到一个“格式基本合规、排除明显默认/溢出”的 Cell 子集，供后续分析使用。

### 5.1 定义格式合规基础视图：`public.v_cell_L1_format_ok`

第一步，只保留 4G/5G 中格式合规的 cell（不含 2G/3G，也不含 0/-1）：

```sql
CREATE OR REPLACE VIEW public.v_cell_L1_format_ok AS
SELECT *
FROM public.v_cell_core_cellonly
WHERE tech_class IN ('4G','5G')
  AND cell_status_fmt = 'NUMERIC_OK'
  AND cell_dec > 0;
```

说明：

- 这一步已经：
  - 完全剔除了 2G/3G（因为 `tech_class IN ('4G','5G')`）；
  - 剔除了 `NULL_OR_EMPTY` / `EXPLICIT_INVALID_0_-1` / `NON_NUMERIC` 的 `cell_id`；
  - 剔除了 `cell_dec <= 0`（包含 0）。
- 但还没有专门剔除“溢出型默认值 2147483647”。

### 5.2 在本轮任务中建议使用的 L1-CELL 筛选视图：`public.v_cell_L1_stage1`

在格式合规的基础上，进一步过滤掉已知的溢出默认值：

```sql
CREATE OR REPLACE VIEW public.v_cell_L1_stage1 AS
SELECT *
FROM public.v_cell_L1_format_ok
WHERE cell_dec <> 2147483647;
```

> **本轮 Cell 筛选的核心输出就是 `public.v_cell_L1_stage1`：**
>
> - 输入范围：5 个核心运营商 + LAC 数值合规；
> - 仅保留 4G/5G；
> - cell 格式必须是：非空、纯数字、正数；
> - 明确剔除 `cell_dec = 2147483647`（0x7FFFFFFF）这一已知溢出默认值。

### 5.3 在实际分析中的使用建议

在本轮工作中，关于 `cell_id` 的使用和过滤建议如下：

1. **所有后续 Cell 相关分析（包括“TOP cell 研究”、“cell_id vs LAC 关系”等），统一以 `public.v_cell_L1_stage1` 为输入**，而不是直接用原始表。
2. 本轮明确剔除的无效情况：
   - 2G/3G 的所有 cell_id（全部是 0/-1，占位值）；  
   - 所有 `cell_status_fmt` ≠ `NUMERIC_OK` 的记录（NULL/空、0/-1、含非数字字符等）；  
   - `cell_dec <= 0` 的记录；  
   - `cell_dec = 2147483647`（5G 溢出默认值）。
3. 本轮暂时 **保留** 的“可疑但未定性”情况：
   - 那些 10–11 位的大数、但在同运营商内样本中只对应 1 个或极少数 LAC 的 cell_id（更像是运营商内部编码），后续会在：
     - `(运营商id, LAC, cell_id)` 全量分布；
     - GPS 稳定性等维度上进一步研究是否需要拉黑。

后续如果在 “TOP cell 研究 / cell 对多个 LAC 的全量统计 / GPS 分布” 中发现新的明确无效 cell_id，将在本文件中追加黑名单规则，并同步更新 `v_cell_L1_stage1` 或新增更严格的视图（例如 `v_cell_L1_compliant`）。 
