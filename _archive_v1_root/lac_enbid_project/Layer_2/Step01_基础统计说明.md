# Step01 基础统计说明（Base Stats）

## 1. 一句话摘要（TL;DR）

给 `public."Y_codex_Layer2_Step00_Gps_Std"` 做两套基线统计：  
**Raw（完全不引用合规）** 与 **ValidCell（只应用 cell_id 正常值规则）**，输出“行数/去重小区/去重 LAC/设备数/缺值结构/来源结构”，用于后续 Step02 合规前后对比与异常快速定位。

---

## 2. 输入（Input）

-- 输入对象：`public."Y_codex_Layer2_Step00_Gps_Std"`
- 输入依赖：Step00（标准化视图必须先建好）
- 输入关键字段（中文（English））：
  - 制式_标准化（tech_norm）
  - 运营商id_细粒度（operator_id_raw）
  - 运营商组_提示（operator_group_hint）
  - 解析来源（parsed_from）
  - Cell十进制（cell_id_dec）
  - LAC十进制（lac_dec）
  - 设备ID（device_id）
  - 是否有cell（has_cellid）/是否有lac（has_lac）/是否有gps（has_gps）
  - 上报日期（report_date）

---

## 3. 输出（Output）

- 输出对象（schema.table）：
  - `public."Y_codex_Layer2_Step01_BaseStats_Raw"`
  - `public."Y_codex_Layer2_Step01_BaseStats_ValidCell"`
- 主键粒度：聚合粒度（`tech_norm + operator_id_raw + operator_group_hint + parsed_from`）
- 输出关键字段（中文（English））：
  - 统计字段（Stats）：
    - 行数（row_cnt）
    - 行占比（row_pct）
    - 去重小区数（cell_cnt）
    - 去重LAC数（lac_cnt）
    - 设备数（device_cnt）
    - 无cell行数/占比（no_cellid_rows/no_cellid_pct）
    - 无lac行数/占比（no_lac_rows/no_lac_pct）
    - 无gps行数/占比（no_gps_rows/no_gps_pct）

说明：

- Raw：不做任何合规过滤；只统计“现状结构”。
- ValidCell：仅应用“cell_id 正常值规则”（来自 Layer_1 Cell 规则的核心子集），不做其它规则（例如不做可信映射）。
  - 当前实现的具体过滤条件（中文（English））：运营商范围（operator_id_raw ∈ 5PLMN）+ 制式范围（tech_norm ∈ {4G,5G}）+ LAC数值合规（lac_dec 非空且 >0）+ Cell数值合规（cell_id_dec 非空且 >0 且 ≠2147483647）。

---

## 4. 本步骤“核心指标”解释（Human-readable）

### 4.1 行数（row_cnt）

- 口径：该维度组合下的记录行数。
- 为什么要看：确定数据规模与结构分布的基线；后续所有“减少/增加”都要对着它解释。
- 正常情况下：Raw 的 `row_cnt` 汇总应覆盖输入全量；ValidCell 汇总应小于等于 Raw。

### 4.2 去重小区数（cell_cnt）

- 口径：`cell_id_dec` 去重计数（排除 NULL）。
- 为什么要看：回答“到底有多少 cell_id”，并观察不同运营商/制式的结构差异。
- 正常情况下：与 `row_cnt` 同向但更稳定；如果 `row_cnt` 很大但 `cell_cnt` 很小，可能存在重复上报或异常默认值。

### 4.3 去重LAC数（lac_cnt）

- 口径：`lac_dec` 去重计数（排除 NULL）。
- 为什么要看：判断 LAC 覆盖面；为 Step03 的 LAC 汇总库提供预期规模。
- 正常情况下：同一运营商+制式下 `lac_cnt` 通常比 `cell_cnt` 小很多。

### 4.4 设备数（device_cnt）

- 口径：`device_id=coalesce(did,oaid)` 去重。
- 为什么要看：衡量“数据是来自多少设备”以及样本代表性；也能定位“单设备异常刷量”。
- 正常情况下：与 `row_cnt` 同向增长，但不会接近 `row_cnt`（除非每条记录都来自不同设备）。

### 4.5 缺值结构（no_*_pct）

- 口径：`has_*` 的反向占比（无 cell / 无 lac / 无 gps）。
- 为什么要看：你关注的“抽取到了但无值也被统计”会体现在缺值比例；后续合规会明显改变这些结构。
- 正常情况下：Raw 的缺值比例可能偏高；ValidCell 里 `no_cellid_pct` 应接近 0（因为已应用 cell 正常值过滤）。

---

## 5. 摘要信息（Summary Queries）

1) 看 Raw 表是否生成，以及总行数是否等于输入行数（验收基线）：
```sql
select
  (select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_Raw") as raw_sum_row_cnt,
  (select count(*) from public."Y_codex_Layer2_Step00_Gps_Std") as input_row_cnt;
```

2) 看 ValidCell 汇总行数是否小于等于 Raw：
```sql
select
  (select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_ValidCell") as valid_cell_sum_row_cnt,
  (select sum(row_cnt) from public."Y_codex_Layer2_Step01_BaseStats_Raw") as raw_sum_row_cnt;
```

3) 看解析来源（parsed_from）结构（Raw）：
```sql
select parsed_from, sum(row_cnt) as row_cnt
from public."Y_codex_Layer2_Step01_BaseStats_Raw"
group by 1
order by row_cnt desc;
```

4) 看制式结构（Raw，按 tech_norm）：
```sql
select tech_norm, sum(row_cnt) as row_cnt
from public."Y_codex_Layer2_Step01_BaseStats_Raw"
group by 1
order by row_cnt desc;
```

5) 看运营商细粒度结构（Raw，Top20）：
```sql
select operator_id_raw, sum(row_cnt) as row_cnt
from public."Y_codex_Layer2_Step01_BaseStats_Raw"
group by 1
order by row_cnt desc
limit 20;
```

6) 看缺值占比（Raw vs ValidCell 对比一眼）：
```sql
select 'RAW' as dataset,
       round(sum(no_cellid_rows)::numeric / nullif(sum(row_cnt),0), 8) as no_cellid_pct,
       round(sum(no_lac_rows)::numeric / nullif(sum(row_cnt),0), 8) as no_lac_pct,
       round(sum(no_gps_rows)::numeric / nullif(sum(row_cnt),0), 8) as no_gps_pct
from public."Y_codex_Layer2_Step01_BaseStats_Raw"
union all
select 'VALID_CELL' as dataset,
       round(sum(no_cellid_rows)::numeric / nullif(sum(row_cnt),0), 8) as no_cellid_pct,
       round(sum(no_lac_rows)::numeric / nullif(sum(row_cnt),0), 8) as no_lac_pct,
       round(sum(no_gps_rows)::numeric / nullif(sum(row_cnt),0), 8) as no_gps_pct
from public."Y_codex_Layer2_Step01_BaseStats_ValidCell";
```

7) 看“同维度下”去重规模（cell_cnt/lac_cnt/device_cnt）：
```sql
select tech_norm, operator_group_hint,
       sum(row_cnt) as row_cnt,
       sum(cell_cnt) as cell_cnt,
       sum(lac_cnt) as lac_cnt,
       sum(device_cnt) as device_cnt
from public."Y_codex_Layer2_Step01_BaseStats_Raw"
group by 1,2
order by row_cnt desc;
```

---

## 6. 详细解释信息（Deep-dive / Debug Guide）

### 6.1 定位用查询（3~6 条）

1) 如果 `parsed_from='ss1'` 占比异常：确认是否基本都来自 `match_status='SS1_UNMATCHED'`（预期是）：
```sql
select parsed_from, match_status, count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1,2
order by row_cnt desc;
```

2) 如果 Raw 的 `no_cellid_pct` 很高：按制式/运营商拆开看是哪里缺值：
```sql
select tech_norm, operator_group_hint,
       count(*) as row_cnt,
       count(*) filter (where not has_cellid) as no_cellid_rows
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1,2
order by no_cellid_rows desc
limit 30;
```

3) 如果 ValidCell 的行数非常小：抽样看被过滤掉的典型 cell 值：
```sql
select cell_id, cell_id_dec, tech, "运营商id", "原始lac"
from public."Y_codex_Layer2_Step00_Gps_Std"
where operator_id_raw in ('46000','46001','46011','46015','46020')
  and tech_norm in ('4G','5G')
  and (cell_id_dec is null or cell_id_dec <= 0 or cell_id_dec = 2147483647)
limit 30;
```

### 6.2 常见异常 → 可能原因 → 建议处理

| 异常现象 | 可能原因 | 建议处理 |
|---|---|---|
| `VALID_CELL` 行数远小于 `RAW` | `cell_id_dec` 缺失/非数/默认值 2147483647 多 | 回看 Layer_0 解析来源（cell_infos/ss1），重点排查 5G 默认值 |
| `parsed_from='ss1'` 比例很高 | cell_infos 侧匹配率低 | 排查 Layer_0 ss1↔cell_infos 匹配键（record_id+cell_id_dec）是否一致 |
| `no_gps_pct` 很高 | 上报场景 GPS 缺失或经纬度异常 | 后续 Step05 只统计 `有效GPS次数（valid_gps_count）`，不强依赖 GPS 全量 |

---

## 7. 执行说明（How to Run）

- 全量模式：执行 `sql/01_step1_base_stats.sql`
  - 耗时等级：L（可能接近 XL，取决于数据库资源与并行）
  - 是否建议物化：是（脚本已落表并 `ANALYZE`）
- 最小可跑模式（冒烟）：
  - 不落表：直接跑本文件第 5 节 `摘要信息（Summary Queries）`，并在 `public."Y_codex_Layer2_Step00_Gps_Std"` 上加 `report_date` 过滤 + `limit`。
  - 适用：白天验证口径/看趋势，不占用长时间资源。
- 索引建议：
  - Step01 自身是全表聚合，索引收益有限；
  - 若你经常按日期查 Raw/ValidCell 的变化，可考虑对 Layer_0 表的 `ts_std` 建 BRIN 索引辅助范围查询（见 RUNBOOK）。
- MCP 自检结果：见 `RUNBOOK_执行手册.md` 附录 A。

---

## 8. 验收标准（Acceptance Criteria）

至少满足以下 5 条：

1. `public."Y_codex_Layer2_Step01_BaseStats_Raw"` / `public."Y_codex_Layer2_Step01_BaseStats_ValidCell"` 两表均成功生成，且可查询。
2. Raw：`sum(row_cnt)` 等于 `public."Y_codex_Layer2_Step00_Gps_Std"` 的行数（口径一致）。
3. ValidCell：`sum(row_cnt) <= Raw sum(row_cnt)`（过滤后不可能增多）。
4. Raw：`parsed_from` 维度至少包含 `cell_infos`（如有 `ss1` 更好），且分布可解释。
5. ValidCell：`无cell占比（no_cellid_pct）` 应接近 0（因为已应用 cell 正常值过滤）。
