# Step02 合规标记说明（Compliance Marking）

## 1. 一句话摘要（TL;DR）

把 GPS 路标准化明细按 Layer_1 规则做 **行级绝对合规** 打标：产出 `是否合规（is_compliant）` 与 `不合规原因（non_compliant_reason）`；并输出“合规前后结构对比 + Top 非合规原因”，为 Step03+ 的“只用有效数据建库”提供入口。

---

## 2. 输入（Input）

-- 输入对象：`public."Y_codex_Layer2_Step00_Gps_Std"`
- 输入依赖：Step00（标准化视图）
- 输入关键字段（中文（English））：
  - 运营商id_细粒度（operator_id_raw）
  - 制式_标准化（tech_norm）
  - LAC十进制（lac_dec）
  - Cell十进制（cell_id_dec）
  - 解析来源（parsed_from）
  - 是否有gps（has_gps）
  - 上报日期（report_date）

合规规则来源（文档）：

- `lac_enbid_project/Layer_1/Lac/Lac_Filter_Rules_v1.md`
- `lac_enbid_project/Layer_1/Cell/Cell_Filter_Rules_v1.md`

> 本 Step 落地的是“行级绝对合规”的核心子集：先保证运营商/制式/LAC/Cell 数值合规；更复杂规则留到未来阶段二（纠偏/补数）处理。

---

## 3. 输出（Output）

- 输出对象：
  - `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（VIEW：全量明细 + 合规标记）
  - `public."Y_codex_Layer2_Step02_Compliance_Diff"`（TABLE：合规前后对比 + Top 原因）
- 主键粒度：
  - 合规明细：行级（seq_id）
  - 对比报表：报表粒度（按 `tech_norm/operator_id_raw/operator_group_hint/parsed_from/is_compliant` 聚合；另含 Top 原因）
- 输出关键字段（中文（English））：
  - 标记字段（Flags）：
    - 是否L1_LAC合规（is_l1_lac_ok）
    - 是否L1_CELL合规（is_l1_cell_ok）
    - 是否合规（is_compliant）：当前口径等同于 `is_l1_cell_ok`
      - 说明：`is_compliant = is_l1_cell_ok`，而 `is_l1_cell_ok` 的判断本身建立在 `is_l1_lac_ok` 之上，因此等价于（运营商+制式+LAC+Cell）四项同时合规的“行级绝对合规”口径。
    - 不合规原因（non_compliant_reason）：多原因用 `;` 拼接

---

## 4. 本步骤“核心指标”解释（Human-readable）

### 4.1 是否合规（is_compliant）

- 口径（当前版）：同时满足以下条件即为合规：
  - 运营商在范围内：`operator_id_raw ∈ {46000,46001,46011,46015,46020}`
  - 制式合规：`tech_norm ∈ {4G,5G}`
  - LAC 数值合规：`lac_dec is not null and lac_dec > 0`
  - LAC 溢出/占位值剔除（硬约束）：`upper(to_hex(lac_dec)) NOT IN ('FFFF','FFFE','FFFFFE','FFFFFF','7FFFFFFF')`
  - LAC 十六进制位数合规（基于 `char_length(to_hex(lac_dec))`）：
    - 移动系（`46000/46015/46020`）：`hex_len ∈ {4,6}`
    - 联通/电信（`46001/46011`）：`hex_len ∈ [4,6]`
  - Cell 数值合规：`cell_id_dec is not null and cell_id_dec > 0 and cell_id_dec != 2147483647`
  - Cell 范围合规（硬约束）：
    - 4G：`cell_id_dec ∈ [1,268435455]`（28-bit ECI）
    - 5G：`cell_id_dec ∈ [1,68719476735]`（36-bit NCI）
- 为什么要看它：它定义了“进入 Step03+ 的有效数据集合”；合规率过低会导致后续库规模过小。
- 正常情况下：合规率应明显低于 Raw，但不应极端接近 0；若极低，通常是上游缺值或字段解析失败。

### 4.2 不合规原因（non_compliant_reason）

- 口径：对不满足条件的记录给出原因枚举（可多项）。
- 为什么要看它：帮助判断规则是否过严/过松，以及定位主要数据质量问题来源（例如 cell 默认值、lac 缺失等）。
- 正常情况下：Top 原因通常集中在少数几类；如果原因非常分散，可能需要补充更多可解释的原因枚举。

### 4.3 合规前后结构变化（按 tech/operator/parsed_from）

- 口径：对 `is_compliant=true/false` 分别按维度聚合对比。
- 为什么要看：避免“合规过滤把某个运营商/某个制式全删没了”这种结构性问题。
- 正常情况下：合规后分布应仍覆盖主要运营商与主要制式。

---

## 5. 摘要信息（Summary Queries）

1) 看合规/不合规行数与占比：
```sql
select is_compliant,
       count(*) as row_cnt,
       round(count(*)::numeric / nullif(sum(count(*)) over (),0), 8) as row_pct
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
group by 1
order by 1 desc;
```

2) 看 Top 非合规原因（Top20）：
```sql
select non_compliant_reason, count(*) as row_cnt
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
where not is_compliant
group by 1
order by row_cnt desc
limit 20;
```

3) 看合规后是否只剩 4G/5G（结构正确性）：
```sql
select tech_norm, count(*) as row_cnt
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
where is_compliant
group by 1
order by row_cnt desc;
```

4) 看合规前后按运营商组的变化（是否被“过滤偏置”）：
```sql
select operator_group_hint,
       sum(case when is_compliant then 1 else 0 end) as compliant_rows,
       sum(case when not is_compliant then 1 else 0 end) as noncompliant_rows
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
group by 1
order by compliant_rows desc;
```

5) 看合规前后按解析来源的变化（ss1 是否被大量剔除）：
```sql
select parsed_from,
       sum(case when is_compliant then 1 else 0 end) as compliant_rows,
       sum(case when not is_compliant then 1 else 0 end) as noncompliant_rows
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
group by 1
order by compliant_rows desc;
```

6) 合规数据里不应出现关键字段缺失（强一致性检查）：
```sql
select count(*) as bad_rows
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
where is_compliant
  and (operator_id_raw is null or tech_norm not in ('4G','5G') or lac_dec is null or cell_id_dec is null);
```

---

## 6. 详细解释信息（Deep-dive / Debug Guide）

### 6.1 定位用查询（3~6 条）

1) 针对某个 Top 原因抽样看原始字段（用于判断规则是否误伤）：
```sql
select seq_id, "记录id", ts_std, tech, "运营商id", "原始lac", cell_id, lac_dec, cell_id_dec, parsed_from
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
where non_compliant_reason = 'CELLID_OVERFLOW_2147483647'
limit 50;
```

2) 如果某个运营商合规率极低：拆到细粒度 operator 看：
```sql
select operator_id_raw,
       count(*) filter (where is_compliant) as compliant_rows,
       count(*) as total_rows,
       round(count(*) filter (where is_compliant)::numeric / nullif(count(*),0), 8) as compliant_pct
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
group by 1
order by compliant_pct asc
limit 20;
```

3) 如果怀疑是 LAC 缺失导致：看 `lac_dec is null` 的规模与来源：
```sql
select parsed_from, tech_norm,
       count(*) as row_cnt,
       count(*) filter (where lac_dec is null) as lac_null_rows
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
group by 1,2
order by lac_null_rows desc
limit 30;
```

### 6.2 常见异常 → 可能原因 → 建议处理

| 异常现象 | 可能原因 | 建议处理 |
|---|---|---|
| 合规率很低 | 上游 `cell_id_dec/lac_dec` 缺失或解析失败 | 回看 Step00 的 `has_*`；必要时回到 Layer_0 解析排查 |
| Top 原因为 `CELLID_OVERFLOW_2147483647` | 5G 默认溢出值大量出现 | Step02 已剔除；后续可对该值做单独异常分析（不进入主库） |
| 合规后某运营商几乎没数据 | 原始 `"运营商id"` 异常/写法非标准 | 优先检查 `operator_id_raw` 归一逻辑与源表范围 |

---

## 7. 执行说明（How to Run）

- 全量模式：执行 `sql/02_step2_compliance_mark.sql`
  - 耗时等级：M~L（合规明细是 VIEW，主要耗时来自生成对比表/Top 原因报表的聚合）
  - 是否建议物化：默认不物化（VIEW 便于快速迭代规则）；若频繁使用可物化成表（需额外空间）。
- 最小可跑模式（冒烟）：只跑第 5 节摘要查询，并在输入视图上加日期过滤（例如 `report_date`）+ `limit`。
- 索引建议（可选）：
  - 如果你要反复按日期/运营商切片看原因分布，可考虑在 Layer_0 表上对 `ts_std` 建 BRIN 索引辅助范围过滤。
- MCP 自检结果：见 `RUNBOOK_执行手册.md` 附录 A（含 Top 原因样例）。

---

## 8. 验收标准（Acceptance Criteria）

至少满足以下 5 条：

1. `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"` 可查询，且包含 `是否合规（is_compliant）/不合规原因（non_compliant_reason）`。
2. `public."Y_codex_Layer2_Step02_Compliance_Diff"` 成功生成，能看到“按维度的合规/不合规行数”与“Top 原因”。
3. 合规数据中 `制式_标准化（tech_norm）` 只包含 `4G/5G`（不应出现 `2_3G/其他`）。
4. 合规数据中不应出现 `lac_dec is null` 或 `cell_id_dec is null`（强一致性检查为 0）。
5. 合规后总行数必须小于等于合规前（不可能增多）；若发现增多，说明统计口径写错或对象引用错。
