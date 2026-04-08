# L1-ENBID / 基站：规则与视图设计 v1（约定稿）

> 目标：在 L1-LAC / L1-CELL 合规数据的基础上，给出 ENBID / 基站层面的统一规则约定，明确主键、派生逻辑以及共建 / 碰撞的处理方式。  
> 本文件作为 v1 设计稿，后续在具体 ENBID 可信库实现时可以迭代补充 SQL 与统计结果。

---

## 1. 数据输入与基础视图

- 源表：`public."网优cell项目_清洗补齐库_v1"`
- L1-LAC 合规视图：`public.v_lac_L1_stage1`
- L1-CELL 合规视图：`public.v_cell_L1_stage1`

后续 ENBID / 基站视图统一以 `public.v_cell_L1_stage1` 作为输入，不再直接在原始表上做 LAC/CELL 合规判断。

---

## 2. Cell 级主键与 ENBID 派生规则

### 2.1 Cell 级主键

在本项目中，Cell 粒度的基础键统一记为：

```text
(运营商id, 原始lac, cell_id)
```

说明：

- `cell_id` 在不同运营商之间存在数值复用 / 共建现象；  
- `原始lac` 仍然是重要的寻址/分桶维度；  
- 后续所有基于 Cell 的视图、可信库、回填逻辑，都必须在键中包含这三项。

### 2.2 ENBID / 基站 ID 派生

从 `cell_id` 派生 ENBID / 基站 ID：

- 对 4G：

```sql
bs_id_dec      = cell_id::bigint / 256;
cell_local_id  = cell_id::bigint % 256;
```

- 对 5G：

```sql
bs_id_dec      = cell_id::bigint / 4096;
cell_local_id  = cell_id::bigint % 4096;
```

统一命名：

- `bs_id_dec` / `bs_id_hex`：站级 ID（4G ENBID 或 5G gNB）。  
- `cell_local_id`：站内小区号。

**ENBID / 基站 ID 不单独作为唯一键使用，所有分析均需带运营商维度。**

---

## 3. 共建 / 碰撞处理逻辑

### 3.1 跨运营商的数值复用（共建场景）

在 L1-CELL 的 TOP Cell 分析中，观察到以下模式：

- 同一 `cell_id` 在多个 PLMN 中出现，并且：
  - `原始lac` 相同；  
  - 按规则推导的 `bs_id_dec`（ENBID / gNB）相同；
  - 站内 `bs_cell_cnt` 在正常范围（1–6 个 cell）。

此类情况解释为“跨运营商共建/共用编码”，处理规则：

- 数据层面仍保留为不同记录：

```text
(46001, 原始lac, cell_id)
(46011, 原始lac, cell_id)
```

- 在 ENBID / 基站的统计视图中，可以按 `(bs_id_dec, 原始lac)` 作为“物理站”分组，再带上 `运营商id` 作为维度字段，从而既能看到共建，又不会混淆运营商。

特别说明（联通 + 电信）：

- 若 `cell_id` 在 `46001` 与 `46011` 中出现，且 `原始lac` 相同 → 视为共建站；  
- 若 `cell_id` 在两家中对应的 `原始lac` 不同 → 视为独立站点，不做共建合并。

### 3.2 同运营商内 `cell_id` 跨 LAC（异常场景）

在对 `cell_id = 5918736` 的检查中，发现：

- `46001` 下：只出现在 `LAC=29024`；  
- `46011` 下：出现在 `LAC=9853` 和 `LAC=29024` 两个 LAC。

一般规则：

- 若同一 `运营商id + cell_id` 在多个 `原始lac` 中出现，则视为**异常模式**，不是“共建”；  
- 建议在单独的“碰撞/异常”视图中记录，例如：

```sql
CREATE VIEW v_cell_id_collision_suspect AS
SELECT
  "运营商id",
  cell_id::bigint AS cell_id_dec,
  COUNT(DISTINCT "原始lac") AS lac_cnt
FROM public.v_cell_L1_stage1
GROUP BY "运营商id", cell_id_dec
HAVING COUNT(DISTINCT "原始lac") > 1;
```

这类记录在 ENBID 可信库中需要降权或人工复核。

### 3.3 非中国 PLMN 的污染数据

- 原始表中存在 `运营商id` 不在 `{46000,46001,46011,46015,46020}` 范围内的记录（例如 `405871`、`28601` 等）。  
- 这些记录在 L1-LAC/L1-CELL 规则中全部被判为不合规，不会出现在 `v_lac_L1_stage1` / `v_cell_L1_stage1` 中。  
- ENBID / 基站分析统一在 L1 视图上进行，无需额外对全局 PLMN 做黑名单过滤。

### 3.4 ENBID / gNB 编码长度异常（仅标记，不拦截）

背景：正常情况下，`bs_id_dec` 对应 **4 位 hex** 的 ENBID / gNB（例如 `0x1A2B`），因此十进制应满足：

- `bs_id_dec >= 256`（即 `0x0100`）  

异常定义（本轮先“标记”）：若 `bs_id_dec BETWEEN 1 AND 255`，则认为存在编码异常/污染风险（例如 `bs_id` 不是 4 位 hex，或来源字段被错误写入），后续在更大数据与更多 LAC 场景下再决定是否拦截。

实现建议：

- 在明细或画像表中增加标记字段：`is_bs_id_lt_256`（bool）  
- 在指标表中统计：`bs_id_lt_256_row_cnt`（行数）

---

## 4. 补数与回填的 Join 约定

在后续的 L2 或业务回填中，从 ENBID / Cell 可信库向主表或其他业务表补数据时，Join 条件**必须**包含：

- `运营商id`
- `原始lac`
- `cell_id`

示意：

```sql
UPDATE t
SET    xxx = c.xxx
FROM   某个_cell_可信库 c
WHERE  t."运营商id" = c."运营商id"
  AND  t."原始lac"  = c."原始lac"
  AND  t.cell_id    = c.cell_id;
```

禁止的做法：

- 只使用 `cell_id` 作为 Join 条件；  
- 仅用 `bs_id_dec + cell_local_id` 作为 Join 条件；

否则会在共建 / 碰撞场景下把联通的值补到电信，或跨 LAC 错配。

---

## 5. 后续 L1-ENBID 视图设计（预留）

在上述规则基础上，预期会逐步增加以下视图（名称仅作示例）：

- `public.v_enbid_L1_basic`  
  - 以 `v_cell_L1_stage1` 为输入，派生 `bs_id_dec` / `bs_id_hex` / `cell_local_id`，并按 `(运营商id, 原始lac, bs_id_dec)` 做汇总。
- `public.v_enbid_L1_collision_suspect`  
  - 记录同一 `(运营商id, cell_id)` 跨多个 LAC，或同一 `(运营商id, bs_id_dec)` 下 `bs_cell_cnt` 异常大的站点，用于后续质量控制。
- `public.v_enbid_L1_trusted`（可选）  
  - 基于 GPS / 时间稳定性等加入更多过滤，形成 ENBID 可信库的 L1 版本。

具体 SQL 将在明确研究目标后补充到本文件或新增的 v1 文档中。
