# RUNREPORT：Layer_2 Step06 反哺改版（现状检查 + 评估口径）

更新时间：2025-12-16  
数据窗口：北京明细 20251201_20251207  
说明：本报告的“数值结果”来自 MCP/DBHub 快查询；由于 Step06 反哺版需要落大表，本报告同时给出你在服务器侧一键重跑后的验收与对比口径。

---

## 0) 结论摘要（先看这个）

- **你库里当前的 Step06 还是旧版**：`Y_codex_Layer2_Step06_L0_Lac_Filtered` 仍是 **VIEW**，对比表仍是 `GPS_RAW/GPS_COMPLIANT/LAC_RAW/LAC_FILTERED` 的旧 4 类数据集；**未体现“用 Step05 映射反哺 LAC”的逻辑**。
- **Step05 映射唯一性非常高**（按 `operator_group_hint+tech_norm`）：绝大多数 `(operator,tech,cell)` 只对应 1 个 `lac`；因此 Step06 采用“仅 `lac_choice_cnt=1` 才回填”的策略，整体风险很低。
- **`cell_id_dec=1` 之所以会出现在 Step05**：Step05 只是对“Step02 合规 + Step04 可信 LAC”内的数据做映射聚合，不负责判定 cell 是否业务有效；要让 `cell_id=1` 被识别为无效，需要先把 `Layer_1/Cell` 的规则与 Step02 的 cell 合规判定修清楚，然后从 Step02 起重跑。

---

## 1) 当前数据库对象状态（关键：Step06 还是旧逻辑）

对象类型（`relkind`：`r`=TABLE, `v`=VIEW）：

| relname | relkind | 说明 |
|---|---:|---|
| `Y_codex_Layer2_Step05_CellId_Stats_DB` | `r` | Step05 映射统计底座（TABLE） |
| `Y_codex_Layer2_Step06_L0_Lac_Filtered` | `v` | **当前仍是 VIEW（旧版）** |
| `Y_codex_Layer2_Step06_GpsVsLac_Compare` | `r` | 对比表（TABLE，但数据集仍是旧版 4 类） |

---

## 2) Step05 的设计目的（我对 Step05 的理解）

Step05 的唯一职责是：**从“GPS 合规集”里抽取“可信的映射证据”**，为 Step06 提供 `(operator + tech + cell) -> lac` 的候选映射与质量统计。

- 输入来自 `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"` 且 `is_compliant=true`。
- 再用 `public."Y_codex_Layer2_Step04_Master_Lac_Lib"` 把样本限定在“可信 LAC 白名单”内（避免用噪声 LAC 生成映射）。
- 产出：
  - `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`：按 `operator+tech+lac+cell` 聚合的映射统计（上报、GPS、设备、活跃天数…）。
  - `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`：同一 `operator+tech+cell` 命中多个 `lac` 的异常哨兵（用于 Step06 回填时的碰撞保护）。

因此：**Step05 里出现 `cell_id_dec=1` 并不代表 Step05 逻辑错误**；它只说明“在当前 Step02 的 cell 合规规则下，`cell_id_dec=1` 被允许进入合规集”，这需要在“cell 合规规则”层面修订。

---

## 3) Step04（可信 LAC 白名单）规模（当前已按 active_days=7+阈值策略落地）

> 统计口径：`public."Y_codex_Layer2_Step04_Master_Lac_Lib" where is_trusted_lac`

| operator_group_hint | tech_norm | trusted_lac_cnt | rpt_cnt | gps_cnt | device_cnt |
|---|---:|---:|---:|---:|---:|
| CMCC | 4G | 224 | 3,511,682 | 3,468,825 | 402,855 |
| CMCC | 5G | 257 | 11,458,937 | 11,379,204 | 963,237 |
| CUCC | 4G | 101 | 1,332,652 | 1,317,057 | 185,028 |
| CUCC | 5G | 118 | 4,766,282 | 4,728,399 | 471,951 |
| CTCC | 4G | 95 | 742,018 | 732,516 | 107,832 |
| CTCC | 5G | 88 | 2,162,060 | 2,145,099 | 243,716 |

---

## 4) Step05 映射“唯一性/碰撞”画像（用于评估 Step06 回填风险）

> 统计口径：对 Step05 按 `(operator_group_hint, tech_norm, cell_id_dec)` 聚合，计算每个 cell key 命中的 `lac_cnt`。

| operator_group_hint | tech_norm | cell_key_cnt | unique_lac_keys | multi_lac_keys | unique_key_share | rpt_cnt | unique_rpt_share |
|---|---:|---:|---:|---:|---:|---:|---:|
| CMCC | 4G | 136,942 | 136,939 | 3 | 1.0000 | 3,511,682 | 1.0000 |
| CMCC | 5G | 140,377 | 140,328 | 49 | 0.9997 | 11,458,937 | 0.9990 |
| CUCC | 4G | 63,036 | 63,035 | 1 | 1.0000 | 1,332,652 | 1.0000 |
| CUCC | 5G | 74,920 | 74,915 | 5 | 0.9999 | 4,766,282 | 0.9998 |
| CTCC | 4G | 48,033 | 48,027 | 6 | 0.9999 | 742,018 | 0.9998 |
| CTCC | 5G | 39,963 | 39,948 | 15 | 0.9996 | 2,162,060 | 0.9984 |

解读：

- **可用于安全回填的 key（`lac_choice_cnt=1`）占比几乎是 100%**；碰撞 key 的数量与上报占比都极低。
- 因此 Step06 的默认策略：“仅对 `lac_choice_cnt=1` 的映射做回填/纠偏”是合理的保护网。

---

## 5) Step06 当前对比结果（旧版：只做过滤，未做反哺）

> 当前 `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"` 仍是旧版 4 数据集（包含 `LAC_FILTERED`）。

| dataset | row_cnt | cell_cnt | lac_cnt | device_cnt |
|---|---:|---:|---:|---:|
| GPS_RAW | 132,688,948 | 859,511 | 22,198 | 3,516,322 |
| GPS_COMPLIANT | 30,549,420 | 837,254 | 11,626 | 1,966,792 |
| LAC_RAW | 118,519,386 | 1,738,395 | 122,790 | 4,254,154 |
| LAC_FILTERED | 21,647,155 | 493,161 | 879 | 1,490,597 |

旧版“覆盖率”（仅供历史参考）：`LAC_FILTERED / LAC_RAW = 0.182647`。

---

## 6) 你需要重跑的 Step06（反哺版）与验收要点

你期望的 Step06 是：

- 先生成 **反哺后的明细表（TABLE）**：`public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`
  - 在 `5PLMN + 4G/5G + has_cell` 范围内
  - 原始 `lac_dec` 若已可信则保留；否则在 `lac_choice_cnt=1` 时用 Step05 映射回填/纠偏得到 `lac_dec_final`
  - **最终只保留 `lac_dec_final` 命中 Step04 白名单的记录**
- 再生成对比表：`public."Y_codex_Layer2_Step06_GpsVsLac_Compare`（至少 7 个数据集）

一键重跑文件：

- `lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`

重跑后验收（建议至少跑这 3 条）：

```sql
-- 1) Step06 L0 明细对象必须是 TABLE（relkind='r'）
select relkind, relname
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and relname='Y_codex_Layer2_Step06_L0_Lac_Filtered';

-- 2) 对比表必须包含 7 类数据集
select dataset, sum(row_cnt) from public."Y_codex_Layer2_Step06_GpsVsLac_Compare"
group by 1 order by 1;

-- 3) 反哺后最终 LAC 必须全部命中 Step04 白名单（应为 0）
select count(*) as not_in_master
from public."Y_codex_Layer2_Step06_L0_Lac_Filtered" f
left join public."Y_codex_Layer2_Step04_Master_Lac_Lib" t
  on f.operator_id_raw=t.operator_id_raw and f.tech_norm=t.tech_norm and f.lac_dec_final=t.lac_dec
where t.lac_dec is null;
```

关于“有 cell 无 operator 的尾巴”：

- MCP 全量统计 `Step00_Lac_Std where operator_id_raw is null and cell_id_dec is not null` 会超时；反哺版 Step06 已把它做成 `dataset='LAC_RAW_HAS_CELL_NO_OPERATOR'` 写入对比表，**重跑后直接从对比表读取即可**。

---

## 7) 你问到的例子：`lac_dec=2097208` 且 `cell_id_dec=1`

在当前库里，Step05 的确存在该行：

- `operator_id_raw='46000'`, `tech_norm='5G'`, `lac_dec=2097208`, `cell_id_dec=1`
- `record_count=16`, `distinct_device_count=2`, `active_days=5`

它没有出现在 `Step05_Anomaly_Cell_Multi_Lac`，是因为 **同一 `(operator,tech,cell)` 并未命中多个 lac**（不是碰撞异常）。

如果你的业务口径认定 `cell_id_dec=1` 必为无效值，那么需要修订：

- `lac_enbid_project/Layer_1/Cell/Cell_Filter_Rules_v1.md`（把“十进制长度/溢出值/-1”解释清楚，避免歧义）
- Layer_2 Step02 的 `is_l1_cell_ok` 与 reason code（把 `cell_id=1` 这类值归入明确的非合规原因）

完成后从 Step02 起重跑（Step02→Step06），再看 Step05/Step06 的映射与反哺效果。

---

## 附录：本报告用到的查询（可复现）

```sql
-- A1) Step06 是否还是旧版（对象类型）
select relkind, relname
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public'
  and relname in ('Y_codex_Layer2_Step06_L0_Lac_Filtered','Y_codex_Layer2_Step06_GpsVsLac_Compare')
order by relname;

-- A2) Step06 对比总览（旧版 4 数据集）
select dataset, sum(row_cnt)::bigint as row_cnt, sum(cell_cnt)::bigint as cell_cnt, sum(lac_cnt)::bigint as lac_cnt, sum(device_cnt)::bigint as device_cnt
from public."Y_codex_Layer2_Step06_GpsVsLac_Compare"
group by 1 order by 1;

-- A3) Step04 可信 LAC 库规模
select operator_group_hint, tech_norm,
       count(*)::bigint as trusted_lac_cnt,
       sum(record_count)::bigint as rpt_cnt,
       sum(valid_gps_count)::bigint as gps_cnt,
       sum(distinct_device_count)::bigint as device_cnt
from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
where is_trusted_lac
group by 1,2
order by 1,2;

-- A4) Step05 映射唯一性
with cell_keys as (
  select operator_group_hint, operator_id_raw, tech_norm, cell_id_dec,
         count(distinct lac_dec)::int as lac_cnt,
         sum(record_count)::bigint as rpt_cnt
  from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
  group by 1,2,3,4
)
select operator_group_hint, tech_norm,
       count(*)::bigint as cell_key_cnt,
       count(*) filter (where lac_cnt=1)::bigint as unique_lac_keys,
       count(*) filter (where lac_cnt>1)::bigint as multi_lac_keys,
       round( (count(*) filter (where lac_cnt=1))::numeric / nullif(count(*),0), 4) as unique_key_share,
       sum(rpt_cnt)::bigint as rpt_cnt,
       round( (sum(rpt_cnt) filter (where lac_cnt=1))::numeric / nullif(sum(rpt_cnt),0), 4) as unique_rpt_share
from cell_keys
group by 1,2
order by 1,2;

-- A5) 例子：lac=2097208 & cell=1
select operator_id_raw, operator_group_hint, tech_norm, lac_dec, cell_id_dec, record_count, valid_gps_count, distinct_device_count, active_days
from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
where lac_dec=2097208 and cell_id_dec=1;
```

