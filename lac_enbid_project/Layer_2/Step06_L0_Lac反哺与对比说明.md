# Step06 L0_Lac 反哺与对比说明（Supplement LAC + Compare）

## 1. 一句话摘要（TL;DR）

用 Step05 输出的“可信 cell 映射统计底座”构建 `(operator+tech+cell)->lac` 的映射（默认仅在映射唯一时使用；若同一 cell 命中多个 LAC，则进入多 LAC 收敛策略选主 LAC），在 LAC 路 Layer_0 明细中对缺失/不可信的 `lac_dec` 做 **补齐/纠偏**，得到“最终可信 LAC”（`lac_dec_final`）的明细库；同时输出对比报表，用于评估：

- GPS 路：Raw → Step02 合规的收敛效果；
- LAC 路：Raw → “满足反哺条件的候选集” → “反哺后可信库”的覆盖与补齐效果；
- “只有 cell_id 没有运营商信息”的规模（用于决定是否需要做“忽略运营商”的二阶段补齐策略）。

> 性能注意（PG15）：`public."Y_codex_Layer2_Step00_Lac_Std"` 是 VIEW 且输入极大时，直接在 VIEW 上 join 很容易触发 merge join / sort / hash spill，造成 TB 级 `temp_bytes/temp_files`。  
> 当前 `lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql` 已改为“两段式”：先把 Step04/05 预处理成小 TEMP 表，再把 Step00 的必要范围物化成 TEMP 表后做 hash join 回填，并默认关闭并行/mergejoin 来避免你这次遇到的 `MessageQueueSend + 巨大 temp`。

---

## 2. 输入（Input）

- 输入对象：
  - `public."Y_codex_Layer2_Step00_Lac_Std"`（来自 Step00）
  - `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（来自 Step05）
  - `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（来自 Step04：可信 LAC 白名单）
  - `public."Y_codex_Layer2_Step00_Gps_Std"`（来自 Step00，用于对比）
  - `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（来自 Step02，用于对比）
- 输入依赖：Step00 + Step02 + Step05
- 输入关键字段（中文（English））：
  - 运营商id_细粒度（operator_id_raw）
  - 制式_标准化（tech_norm）
  - LAC十进制（lac_dec）
  - Cell十进制（cell_id_dec）
  - 设备ID（device_id）

---

## 3. 输出（Output）

- 输出对象：
  - `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE：LAC 路反哺后可信明细库；包含 `lac_dec_final` 等派生列）
  - `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`（TABLE：对比报表，含反哺候选/反哺后/无运营商信息规模）
- 主键粒度：
  - 反哺后明细：行级（seq_id）
  - 对比报表：`dataset + tech_norm + operator_id_raw + operator_group_hint`
- 输出关键字段（中文（English））：
  - 反哺后明细（Pass-through + Derived）：继承 `Y_codex_Layer2_Step00_Lac_Std` 全字段，并新增：
    - `lac_dec_from_map`：映射得到的 lac（仅映射唯一时有值）
    - `lac_dec_final`：最终用于反哺的可信 lac（保证落在 Step04 白名单）
    - `lac_choice_cnt`：同一 `(operator,tech,cell)` 命中 lac 的候选数（>1 表示多 LAC；本步骤会进入 `MULTI_LAC_*` 收敛策略，必要时覆盖原始 LAC）
    - `is_original_lac_trusted`：原始 lac 是否已在 Step04 白名单内
    - `is_final_lac_trusted`：最终 lac 是否在 Step04 白名单内（视图已强制为 true）
    - `is_lac_changed_by_mapping`：是否发生了补齐/纠偏
    - `best_lac_dec`：当 `lac_choice_cnt>1` 时的“收敛目标 LAC”（由证据优先级选出）
    - `lac_enrich_status`：补齐/纠偏状态枚举（`MULTI_LAC_OVERRIDE/MULTI_LAC_KEEP/KEEP_TRUSTED_LAC/BACKFILL_NULL_LAC/REPLACE_UNTRUSTED_LAC/...`）

> 重要提示：`lac_dec_final` 才是“最终可信 LAC”（强制命中 Step04 白名单）。  
> 为避免评估时误用原始透传字段，本项目在 Step06 落表后会执行一次“输出口径归一”：
> - 对 `lac_dec/lac_hex` 为明显异常（`NULL/0/FFFF/FFFE/FFFFFE/FFFFFF/7FFFFFFF/7FFFFFFF`）的行，把它们改写为最终值（= `lac_dec_final`）；  
> - 原始值会保留到 `lac_dec_raw/lac_hex_raw`（仅对被修正行写入）；  
> - 因此在最终交付表里，`lac_dec/lac_hex` 可以直接作为“最终可信 LAC”使用，`lac_dec_raw/lac_hex_raw` 用于追溯原始异常。
  - 对比报表（Stats）：
    - 行数（row_cnt）
    - 去重cell数（cell_cnt）
    - 去重lac数（lac_cnt）
    - 设备数（device_cnt）
    - 数据集（dataset）至少包含：
      - `GPS_RAW`
      - `GPS_COMPLIANT`
      - `LAC_RAW`
      - `LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL`（具备反哺条件的候选集）
      - `LAC_SUPPLEMENTED_TRUSTED`（反哺后可信库）
      - `LAC_SUPPLEMENTED_BACKFILLED`（反哺后中“发生补齐/纠偏”的子集）
      - `LAC_RAW_HAS_CELL_NO_OPERATOR`（只有 cell_id 没运营商信息）

---

## 4. 本步骤“核心指标”解释（Human-readable）

### 4.1 反哺后可信库规模（LAC_SUPPLEMENTED_TRUSTED）

- 口径：在 `5PLMN + 4G/5G + has_cell` 范围内，最终 `lac_dec_final` 落在 Step04 白名单的 LAC 路明细行数。
- 为什么要看：它刻画“合规库→映射→反哺”对 LAC 路的有效覆盖；越大说明反哺能输出更完整的可信 LAC 明细库。
- 正常情况下：应明显小于等于 `LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL`；但不应接近 0（除非 Step04/05 过严或 key 不一致）。

### 4.2 GPS_RAW vs GPS_COMPLIANT

- 口径：同一 GPS 路数据在 Raw 与 Step02 合规后的对比。
- 为什么要看：保证合规过滤没有“结构性误伤”（例如某运营商/制式被全删）。
- 正常情况下：GPS_COMPLIANT 行数减少，但主流运营商与 4G/5G 仍应存在。

### 4.3 反哺增量（LAC_SUPPLEMENTED_BACKFILLED）

- 口径：在反哺后可信库中，`lac_enrich_status ∈ {BACKFILL_NULL_LAC, REPLACE_UNTRUSTED_LAC}` 的记录规模。
- 为什么要看：它直接回答“反哺找回了多少原先因为 lac 缺失/不可信而丢掉的 LAC 路记录”。

### 4.4 只有 cell_id 没有运营商信息（LAC_RAW_HAS_CELL_NO_OPERATOR）

- 口径：`tech_norm in (4G,5G) AND cell_id_dec is not null AND operator_id_raw is null` 的 LAC 路记录规模。
- 为什么要看：这部分如果规模很大，才值得评估二阶段策略（忽略运营商做补齐）；但该策略会引入跨运营商碰撞风险，需要额外机制处理。

---

## 5. 摘要信息（Summary Queries）

1) 看反哺后可信库行数（只看数量级）：
```sql
select count(*) as lac_supplemented_row_cnt
from public."Y_codex_Layer2_Step06_L0_Lac_Filtered";
```

2) 确认反哺后最终 LAC 全部落在 Step04 白名单内（应为 0）：
```sql
select count(*) as bad_rows
from public."Y_codex_Layer2_Step06_L0_Lac_Filtered" f
left join public."Y_codex_Layer2_Step04_Master_Lac_Lib" t
  on f.operator_id_raw=t.operator_id_raw
 and f.tech_norm=t.tech_norm
 and f.lac_dec_final=t.lac_dec
where t.lac_dec is null;
```

3) 看对比报表的数据集是否都有输出（至少 7 类）：
```sql
select dataset, sum(row_cnt) as row_cnt
from public."Y_codex_Layer2_Step06_GpsVsLac_Compare"
group by 1
order by 1;
```

4) 看同维度下 LAC 的“候选→反哺→回填增量”差异（按运营商组/制式）：
```sql
select dataset, operator_group_hint, tech_norm,
       sum(row_cnt) as row_cnt,
       sum(cell_cnt) as cell_cnt,
       sum(lac_cnt) as lac_cnt
from public."Y_codex_Layer2_Step06_GpsVsLac_Compare"
where dataset in ('LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL','LAC_SUPPLEMENTED_TRUSTED','LAC_SUPPLEMENTED_BACKFILLED')
group by 1,2,3
order by operator_group_hint, tech_norm, dataset;
```

5) 看反哺后 Top 映射键（辅助判断是否“过于集中”）：
```sql
select operator_id_raw, tech_norm, lac_dec_final, cell_id_dec, count(*) as row_cnt
from public."Y_codex_Layer2_Step06_L0_Lac_Filtered"
group by 1,2,3,4
order by row_cnt desc
limit 50;
```

---

## 6. 详细解释信息（Deep-dive / Debug Guide）

### 6.1 定位用查询（3~6 条）

1) 如果 `lac_supplemented_row_cnt` 很小：先确认 Step05 映射规模是否太小：
```sql
select count(*) as mapping_cnt
from public."Y_codex_Layer2_Step05_CellId_Stats_DB";
```

2) 如果映射规模正常但反哺后仍很小：检查 LAC 路关键字段缺失情况（尤其 operator_id_raw / cell_id_dec）：
```sql
select
  count(*) as lac_rows,
  count(*) filter (where operator_id_raw is null) as null_operator_rows,
  count(*) filter (where tech_norm = '其他') as tech_other_rows,
  count(*) filter (where lac_dec is null or cell_id_dec is null) as null_key_rows
from public."Y_codex_Layer2_Step00_Lac_Std";
```

3) 如果怀疑 join 慢：先用小样本验证 join 正确性（不跑全量）：
```sql
select count(*) as matched_cell_keys_in_sample
from (
  select *
  from public."Y_codex_Layer2_Step00_Lac_Std"
  where tech_norm in ('4G','5G')
    and operator_id_raw in ('46000','46001','46011','46015','46020')
    and cell_id_dec is not null
  limit 100000
) l
join (
  select distinct operator_id_raw, tech_norm, cell_id_dec
  from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
) m
  on l.operator_id_raw=m.operator_id_raw
 and l.tech_norm=m.tech_norm
 and l.cell_id_dec=m.cell_id_dec;
```

### 6.2 常见异常 → 可能原因 → 建议处理

| 异常现象 | 可能原因 | 建议处理 |
|---|---|---|
| LAC_SUPPLEMENTED_TRUSTED 行数接近 0 | Step04 白名单过小 / Step05 映射过小 / LAC 路 operator/cell 缺失多 | 先看 Step04/05 规模；再看 `Y_codex_Layer2_Step00_Lac_Std` 的 operator_id_raw/cell_id_dec 缺失情况 |
| Step06 join 非常慢 | L0_Lac 大表无 join key 索引 | 评估在 `Y_codex_Layer0_Lac` 上加复合索引（见 RUNBOOK §4.2）或先物化标准化表 |
| GPS_COMPLIANT 与 LAC_SUPPLEMENTED_TRUSTED 结构完全不一致 | LAC 路数据质量问题或采集逻辑差异（或 operator 缺失导致无法反哺） | 先按 operator+tech 分维度对比；再看 `LAC_RAW_HAS_CELL_NO_OPERATOR` 规模；必要时回到 Layer_0 排查 LAC 源解析 |

---

## 7. 执行说明（How to Run）

- 全量模式：执行 `sql/06_step6_apply_mapping_and_compare.sql`
  - 耗时等级：XL（尤其是 LAC 路反哺 join）
  - 是否建议物化：
    - 本轮脚本默认落表（`Y_codex_Layer2_Step06_L0_Lac_Filtered` 为 TABLE），便于后续评估与复用；若反复按 key 查询，建议额外对常用过滤列建索引。
- 最小可跑模式（冒烟）：
  - 先跑第 5 节摘要查询中的“小样本 join”（`limit 100000`）确认逻辑；
  - 对比报表可在样本范围内先算出趋势，再决定是否跑全量。
- 索引建议（强烈）：
  - 在 `public."Y_codex_Layer0_Lac"` 上建复合索引：`("运营商id", tech, lac_dec, cell_id_dec)`，用于加速映射过滤。
- MCP 自检结果：见 `RUNBOOK_执行手册.md` 附录 A（对比表输出样例）。

---

## 8. 验收标准（Acceptance Criteria）

至少满足以下 5 条：

1. `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"` 可查询，且能输出行级明细字段（来自 LAC 路标准化视图）。
2. `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"` 成功生成，且至少包含 7 类数据集：`GPS_RAW/GPS_COMPLIANT/LAC_RAW/LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL/LAC_SUPPLEMENTED_TRUSTED/LAC_SUPPLEMENTED_BACKFILLED/LAC_RAW_HAS_CELL_NO_OPERATOR`。
3. 反哺后明细的 `lac_dec_final` 必须全部命中 Step04 白名单（第 5 节第 2 条 bad_rows=0）。
4. `LAC_SUPPLEMENTED_TRUSTED` 的 `row_cnt/cell_cnt/lac_cnt` 必须小于等于 `LAC_ELIGIBLE_5PLMN_4G5G_HAS_CELL` 的对应值（不会凭空增多）。
5. GPS_COMPLIANT 与 LAC_SUPPLEMENTED_TRUSTED 的按 `运营商组_提示（operator_group_hint）+制式_标准化（tech_norm）` 分布可解释；若出现“某主流运营商/制式完全缺失”，必须能定位到 Step04/05 上游规模或 LAC 路 operator/cell 缺失原因。
