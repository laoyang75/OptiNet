# Layer_3 验收报告模板 v3（2025-12-18）

> 用途：每次“全量跑完 Step30~34”后，用本模板生成一组 Markdown 报告，做到“一眼拍板”。  
> v3 重点：Gate-0 COMMENT 双语覆盖硬验收 + 指标汇总不吞 WARN + Step34 口径统一（本轮仅 PASS/FAIL）。

你需要产出并保存到 `lac_enbid_project/Layer_3/reports/`：

- `Step30_Report_YYYYMMDD.md`
- `Step31_Report_YYYYMMDD.md`
- `Step32_Report_YYYYMMDD.md`
- `Step33_Report_YYYYMMDD.md`
- `Step34_Report_YYYYMMDD.md`
- `Layer_3_Summary_YYYYMMDD.md`

---

## Gate-0：DB COMMENT 双语覆盖（CR-01，硬阻断）

前置条件：必须已执行 `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`（COMMENT 格式：`CN: ...; EN: ...`）。

执行并粘贴结果（逐表）：

```sql
with target as (
  select * from (values
    ('public','Y_codex_Layer3_Step30_Master_BS_Library'),
    ('public','Y_codex_Layer3_Step30_Gps_Level_Stats'),
    ('public','Y_codex_Layer3_Step31_Cell_Gps_Fixed'),
    ('public','Y_codex_Layer3_Step32_Compare_Raw'),
    ('public','Y_codex_Layer3_Step32_Compare'),
    ('public','Y_codex_Layer3_Step33_Signal_Fill_Simple'),
    ('public','Y_codex_Layer3_Step34_Signal_Compare_Raw'),
    ('public','Y_codex_Layer3_Step34_Signal_Compare')
  ) as t(table_schema, table_name)
),
tbl as (
  select
    t.table_schema,
    t.table_name,
    c.oid as table_oid,
    obj_description(c.oid, 'pg_class') as table_comment
  from target t
  join pg_namespace n on n.nspname=t.table_schema
  join pg_class c on c.relnamespace=n.oid and c.relname=t.table_name
),
col as (
  select
    t.table_schema,
    t.table_name,
    a.attname as column_name,
    col_description(c.oid, a.attnum) as column_comment
  from target t
  join pg_namespace n on n.nspname=t.table_schema
  join pg_class c on c.relnamespace=n.oid and c.relname=t.table_name
  join pg_attribute a on a.attrelid=c.oid and a.attnum>0 and not a.attisdropped
)
select
  c.table_schema || '.' || quote_ident(c.table_name) as table_full_name,
  count(*) as total_cols,
  count(*) filter (where c.column_comment is null or btrim(c.column_comment)='') as missing_comment_cols,
  count(*) filter (where c.column_comment is not null and not (c.column_comment ~ 'CN:' and c.column_comment ~ 'EN:')) as not_bilingual_cols,
  max(case when t.table_comment is null or btrim(t.table_comment)='' then 1 else 0 end) as missing_table_comment,
  max(case when t.table_comment is not null and not (t.table_comment ~ 'CN:' and t.table_comment ~ 'EN:') then 1 else 0 end) as not_bilingual_table_comment
from col c
join tbl t
  on t.table_schema=c.table_schema and t.table_name=c.table_name
group by 1
order by 1;
```

判定：

- 任一 missing_comment_cols>0 / not_bilingual_cols>0 / missing_table_comment=1 / not_bilingual_table_comment=1 ⇒ FAIL 阻断

---

## 通用：一眼拍板表（强制）

每份 Step 报告必须包含：

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| DB COMMENT 双语覆盖 | missing=0 且 not_bilingual=0 | （填：Gate-0 输出） | PASS/FAIL | FAIL 先修 `99_layer3_comments.sql` |

---

## Step30 报告模板

文件：`Step30_Report_YYYYMMDD.md`

### 1) 产出对象

- `public."Y_codex_Layer3_Step30_Master_BS_Library"`
- `public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

### 2) 一眼拍板表（Step30 必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| DB COMMENT 双语覆盖 | missing=0 且 not_bilingual=0 | （填：Gate-0） | PASS/FAIL | FAIL 阻断 |
| 主键是否唯一（tech_norm, bs_id, wuli_fentong_bs_key） | 重复数=0 | （填） | PASS/FAIL | FAIL 直接阻断，排查 Step06 键或聚合粒度 |
| gps_valid_level 分布 | 不可全部 Unusable | （填） | PASS/FAIL | 若全 Unusable：检查 Verified 点口径/Step02 has_gps |
| Usable/Risk 中心点合法 | 不为 NULL，不为(0,0)，经纬度合法 | （填） | PASS/FAIL | FAIL：检查中心点计算/输入点过滤 |
| Unusable 占比 | <= 0.80（默认阈值，可调） | （填） | WARN/OK | 过高：优先检查 Step02 可信点口径 |
| 碰撞疑似占比 | <= 0.05（默认阈值，可调） | （填） | WARN/OK | 过高：评估阈值与 Step05 多LAC监测清单影响 |

### 3) 核心查询（复制执行并粘贴结果）

```sql
-- 主键重复
select count(*) as dup_cnt
from (
  select tech_norm, bs_id, wuli_fentong_bs_key, count(*) as cnt
  from public."Y_codex_Layer3_Step30_Master_BS_Library"
  group by 1,2,3
  having count(*)>1
) t;

-- gps_valid_level 分布
select gps_valid_level, count(*) as bs_cnt
from public."Y_codex_Layer3_Step30_Master_BS_Library"
group by 1 order by 2 desc;

-- Unusable/Collision 占比（用于 WARN 量化）
with b as (
  select
    count(*)::numeric as total_cnt,
    count(*) filter (where gps_valid_level='Unusable')::numeric as unusable_cnt,
    count(*) filter (where is_collision_suspect=1)::numeric as collision_cnt
  from public."Y_codex_Layer3_Step30_Master_BS_Library"
)
select
  total_cnt,
  unusable_cnt,
  round(unusable_cnt/nullif(total_cnt,0), 6) as unusable_ratio,
  collision_cnt,
  round(collision_cnt/nullif(total_cnt,0), 6) as collision_ratio
from b;

-- 中心点合法性（Usable/Risk 必须有中心点且合法）
select
  count(*) filter (where gps_valid_level in ('Usable','Risk')
                   and (bs_center_lon is null or bs_center_lat is null)) as center_null_cnt,
  count(*) filter (where gps_valid_level in ('Usable','Risk')
                   and (bs_center_lon=0 and bs_center_lat=0)) as center_zero_cnt,
  count(*) filter (where gps_valid_level in ('Usable','Risk')
                   and not (bs_center_lon between -180 and 180 and bs_center_lat between -90 and 90)) as center_out_of_range_cnt
from public."Y_codex_Layer3_Step30_Master_BS_Library";

-- 碰撞疑似 Top10（按 p90）
select tech_norm, bs_id, wuli_fentong_bs_key, shared_operator_list, gps_valid_cell_cnt,
       gps_p90_dist_m, gps_max_dist_m, anomaly_cell_cnt, collision_reason
from public."Y_codex_Layer3_Step30_Master_BS_Library"
where is_collision_suspect=1
order by gps_p90_dist_m desc nulls last
limit 10;
```

---

## Step31 报告模板

文件：`Step31_Report_YYYYMMDD.md`

### 1) 产出对象

- `public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`

### 2) 一眼拍板表（Step31 必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| DB COMMENT 双语覆盖 | missing=0 且 not_bilingual=0 | （填：Gate-0） | PASS/FAIL | FAIL 阻断 |
| 回溯字段空值数 | 0 | （填） | PASS/FAIL | FAIL：检查 Step06 字段透传 |
| Augmented 之后 final=Missing | 应为 0 | （填） | PASS/FAIL | FAIL：回填逻辑错误 |
| Risk 回填占比 | <= 0.20（默认阈值，可调） | （填） | WARN/OK | 过大：评估 Step30 Risk 判定与阈值 |
| Drift 占比 | <= 0.20（默认阈值，可调） | （填） | WARN/OK | 过大：评估 drift 阈值与输入 GPS 质量 |

### 3) 解释口径（冻结决策 E 的“业务一句话”）

- `Original_Verified`：原始 GPS 可信，保持原值（不覆盖）
- `Augmented_from_BS`：原始 Missing/Drift，被 Usable 基站中心点回填/纠偏
- `Augmented_from_Risk_BS`：来自 Risk 基站中心点回填/纠偏（只有 1 个 cell 来源，风险必须显式标记）
- `Not_Filled`：基站桶 Unusable 或中心点缺失，无法回填

### 4) 核心查询

```sql
-- 回溯字段空值
select count(*) filter (where src_seq_id is null or src_record_id is null) as bad_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

-- Augmented 后不应仍 Missing
select count(*) as bad_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
where gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS')
  and gps_status_final <> 'Verified';

-- Risk 回填占比 & Drift 占比（用于 WARN 量化）
with b as (
  select
    count(*)::numeric as total_cnt,
    count(*) filter (where gps_source='Augmented_from_Risk_BS')::numeric as risk_fill_cnt,
    count(*) filter (where gps_status='Drift')::numeric as drift_cnt
  from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
)
select
  total_cnt,
  risk_fill_cnt,
  round(risk_fill_cnt/nullif(total_cnt,0), 6) as risk_fill_ratio,
  drift_cnt,
  round(drift_cnt/nullif(total_cnt,0), 6) as drift_ratio
from b;

-- 组合分布（用于解释）
select gps_status, gps_source, gps_status_final, count(*) as row_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
group by 1,2,3
order by row_cnt desc
limit 50;

-- Drift→Corrected Top10
select operator_id_raw, tech_norm, bs_id, cell_id_dec, gps_dist_to_bs_m, lon_raw, lat_raw, lon_final, lat_final
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
where gps_status='Drift' and gps_status_final='Verified'
order by gps_dist_to_bs_m desc nulls last
limit 10;

-- Risk 回填 Top10
select operator_id_raw, tech_norm, bs_id, cell_id_dec, gps_source, is_from_risk_bs, lon_final, lat_final
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
where gps_source='Augmented_from_Risk_BS'
order by report_date desc nulls last
limit 10;
```

---

## Step32 报告模板（对比表，CR-02：不吞 WARN）

文件：`Step32_Report_YYYYMMDD.md`

### 1) 产出对象

- `public."Y_codex_Layer3_Step32_Compare"`（v2：含 metric_code/中文指标/Pass 标记）

### 2) 一眼拍板表（Step32 必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| DB COMMENT 双语覆盖 | missing=0 且 not_bilingual=0 | （填：Gate-0） | PASS/FAIL | FAIL 阻断 |
| 指标是否存在 FAIL | 0 行 | （填） | PASS/FAIL | FAIL：回填/纠偏逻辑或统计口径错误 |
| 指标是否存在 WARN | 可接受或需解释 | （填） | WARN/OK | 必须解释 + TopN |

### 3) 核心查询（汇总：FAIL > WARN > PASS）

```sql
select
  metric_code,
  metric_name_cn,
  expected_rule_cn,
  sum(actual_value_num) as actual_value_sum,
  case
    when bool_or(pass_flag='FAIL') then 'FAIL'
    when bool_or(pass_flag='WARN') then 'WARN'
    else 'PASS'
  end as overall_flag
from public."Y_codex_Layer3_Step32_Compare"
group by 1,2,3
order by metric_code;

select pass_flag, count(*) as metric_rows
from public."Y_codex_Layer3_Step32_Compare"
group by 1
order by 1;

select *
from public."Y_codex_Layer3_Step32_Compare"
where pass_flag in ('FAIL','WARN')
order by report_section, metric_code, actual_value_num desc nulls last
limit 200;
```

---

## Step33 报告模板（信号补齐：WARN 只在本步）

文件：`Step33_Report_YYYYMMDD.md`

### 1) 产出对象

- `public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`

### 2) 一眼拍板表（Step33 必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| DB COMMENT 双语覆盖 | missing=0 且 not_bilingual=0 | （填：Gate-0） | PASS/FAIL | FAIL 阻断 |
| 补齐后缺失不应增加 | after<=before（bad_cnt=0） | （填） | PASS/FAIL | FAIL：补齐逻辑错误 |
| none 占比 | <= 0.80（默认阈值，可调） | （填） | WARN/OK | 过高：信号字段源不足/解析缺失 |
| bs_agg 占比 | <= 0.50（默认阈值，可调） | （填） | WARN/OK | 过高：cell 画像不足，需策略升级 |

### 3) 核心查询

```sql
-- after>before 的异常行数（应为 0）
select count(*) as bad_cnt
from public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
where signal_missing_after_cnt > signal_missing_before_cnt;

-- signal_fill_source 分布（含占比，用于 WARN 量化）
with b as (
  select signal_fill_source, count(*)::numeric as row_cnt
  from public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
  group by 1
),
t as (
  select sum(row_cnt) as total_cnt from b
)
select
  b.signal_fill_source,
  b.row_cnt,
  round(b.row_cnt/nullif(t.total_cnt,0), 6) as row_ratio
from b cross join t
order by b.row_cnt desc;
```

### 4) TopN 样本（必含）

```sql
-- bs_agg Top10（便于判断是否“只能回退到基站”）
select operator_id_raw, tech_norm, bs_id, cell_id_dec, signal_fill_source,
       signal_missing_before_cnt, signal_missing_after_cnt
from public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
where signal_fill_source='bs_agg'
order by signal_missing_before_cnt desc, signal_missing_after_cnt asc
limit 10;

-- none Top10（后续策略准备）
select operator_id_raw, tech_norm, bs_id, cell_id_dec, signal_fill_source,
       signal_missing_before_cnt, signal_missing_after_cnt
from public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
where signal_fill_source='none'
order by signal_missing_after_cnt desc, report_date desc nulls last
limit 10;
```

---

## Step34 报告模板（信号补齐对比：本轮仅 PASS/FAIL）

文件：`Step34_Report_YYYYMMDD.md`

### 1) 产出对象

- `public."Y_codex_Layer3_Step34_Signal_Compare"`（v2：指标表，pass_flag 仅 PASS/FAIL）

### 2) 一眼拍板表（Step34 必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| DB COMMENT 双语覆盖 | missing=0 且 not_bilingual=0 | （填：Gate-0） | PASS/FAIL | FAIL 阻断 |
| 指标是否存在 FAIL | 0 行 | （填） | PASS/FAIL | FAIL：检查 Step33 补齐逻辑/字段映射 |

### 3) 核心查询（仅查 FAIL）

```sql
select
  metric_code,
  metric_name_cn,
  expected_rule_cn,
  sum(actual_value_num) as actual_value_sum,
  case when bool_or(pass_flag='FAIL') then 'FAIL' else 'PASS' end as overall_flag
from public."Y_codex_Layer3_Step34_Signal_Compare"
group by 1,2,3
order by metric_code;

select pass_flag, count(*) as metric_rows
from public."Y_codex_Layer3_Step34_Signal_Compare"
group by 1
order by 1;

select *
from public."Y_codex_Layer3_Step34_Signal_Compare"
where pass_flag = 'FAIL'
order by metric_code, actual_value_num desc nulls last
limit 200;
```

---

## 总览报告模板（建议：不要吞 WARN）

文件：`Layer_3_Summary_YYYYMMDD.md`

必须包含：

- Gate-0 COMMENT 结果摘要（是否 100% 覆盖）
- Step30~34 的 PASS/FAIL/WARN 汇总（每步一行）
- Top3 风险（collision、Risk 回填、signal none）
- 参数变更记录（阈值、漂移阈值等）
