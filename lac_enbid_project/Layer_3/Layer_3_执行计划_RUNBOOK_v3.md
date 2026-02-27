# Layer_3 执行计划 RUNBOOK v3（2025-12-18）

> v3 在 v2 基础上补齐“可读性闭环”：  
> - Gate-0：DB COMMENT 双语覆盖率=100%（硬阻断）；  
> - 指标汇总不吞 WARN（FAIL > WARN > PASS）；  
> - Step34 WARN 口径统一（本轮采用方案 A：Step34 仅 PASS/FAIL；WARN 只在 Step33）。  
> 监督任务单：`lac_enbid_project/Layer_3/notes/fix3.md`

---

## 0) 执行模型（不变）

- 人类：后台执行全量 SQL（Step30~34 + 99）
- 我（assistant）：冒烟跑通 + MCP 自检 + 生成验收报告 + 写 RUNLOG

---

## 1) 执行前检查（必须）

### 1.1 输入对象存在性（冻结）

- `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`
- `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`
- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`
- `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`
- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（必须 TABLE）

### 1.2 会话级调优

参考 `lac_enbid_project/服务器配置与SQL调优建议.md`；Layer_3 每个 SQL 文件顶部已内嵌推荐 `SET`。

---

## 2) Gate-0：DB COMMENT 双语覆盖（CR-01，硬阻断）

目的：把“中文友好”变成可机器校验的硬验收。

前置要求：

- 必须先执行 `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`
- COMMENT 格式必须满足：`CN: ...; EN: ...`

验收 SQL（输出每表 total_cols/missing_comment_cols/not_bilingual_cols）：

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

判定（硬阻断）：

- 任一表 `missing_comment_cols>0` 或 `not_bilingual_cols>0` ⇒ FAIL
- 任一表 `missing_table_comment=1` 或 `not_bilingual_table_comment=1` ⇒ FAIL

建议附加汇总（可直接拍板）：

```sql
with per_table as (
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
  ),
  per as (
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
  )
  select * from per
)
select
  count(*) filter (
    where missing_comment_cols>0
       or not_bilingual_cols>0
       or missing_table_comment=1
       or not_bilingual_table_comment=1
  ) as fail_table_cnt,
  count(*) as total_table_cnt
from per_table;
```

---

## 3) 执行顺序（必须按顺序）

1. `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`
2. `lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql`
3. `lac_enbid_project/Layer_3/sql/32_step32_compare.sql`
4. `lac_enbid_project/Layer_3/sql/33_step33_signal_fill_simple.sql`
5. `lac_enbid_project/Layer_3/sql/34_step34_signal_compare.sql`
6. `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`
7. Gate-0：COMMENT 覆盖检查（本文件第 2 节；必须先过 Gate-0 再开始填写任何 Step 报告）
8. 逐步验收并填写报告：`lac_enbid_project/Layer_3/Layer_3_验收报告模板_v3.md`

> 可选附加（异常数据剥离，不影响 Gate-0）：  
> 若 Step30 仍有 `is_collision_suspect=1` 且你怀疑是“动态/移动 cell（时间-质心相关）”而非混桶，执行：  
> `lac_enbid_project/Layer_3/sql/35_step35_dynamic_cell_bs_detection.sql`  
> 该步骤会输出动态 cell/BS 标记与“排除动态 cell 后的 p90 回落”对比表，用于决定是否继续按“混桶路径”深挖。

> 可选附加（28 天外部验证，不影响 Gate-0）：  
> 若你已准备 28 天原始明细表（例如 `public.cell_id_375_28d_data_20251225`），并希望直接验证 “scoped cell 是否存在时间相关多质心切换”，执行：  
> `lac_enbid_project/Layer_3/sql/35_step35_dynamic_cell_28d_validation.sql`  
> 该步骤会输出 `public."Y_codex_Layer3_Step35_28D_Dynamic_Cell_Profile"`，用于把“动态/移动 cell”从疑似混桶样本中先剥离。

> 可选附加（异常标注，不影响 Gate-0）：  
> - `lac_enbid_project/Layer_3/sql/36_step36_bs_id_anomaly_mark.sql`：标注疑似异常 BS ID（bs_id=0/1/过短 hex 等）  
> - `lac_enbid_project/Layer_3/sql/37_step37_collision_data_insufficient_mark.sql`：标注“低样本导致波动”的碰撞疑似桶（7 天内不强结论）

---

## 4) 默认阈值表（SR-01，建议落地为可调参数）

说明：

- 这些阈值用于 WARN 量化，不作为本轮业务“唯一正确答案”。
- 你应在报告中同时给：实际占比、阈值、Top10 样本、建议动作。

| Step | 检查项（中文） | 默认阈值（可调） | 结论类型 |
|---:|---|---|---|
| 30 | Unusable 占比 | `unusable_ratio_warn = 0.80` | WARN |
| 30 | 碰撞疑似占比 | `collision_ratio_warn = 0.05` | WARN |
| 31 | Risk 回填占比（Augmented_from_Risk_BS / 总行数） | `risk_fill_ratio_warn = 0.20` | WARN |
| 31 | Drift 占比（gps_status=Drift / 总行数） | `drift_ratio_warn = 0.20` | WARN |
| 33 | none 占比（signal_fill_source='none' / 总行数） | `none_ratio_warn = 0.80` | WARN |
| 33 | bs_agg 占比（signal_fill_source='bs_agg' / 总行数） | `bs_agg_ratio_warn = 0.50` | WARN |

---

## 5) 跨步一致性检查（SR-02，推荐 FAIL）

目的：拦截“行数丢失/键不一致/join 失败/枚举脏值”类事故。

### 5.1 行数一致（建议 FAIL）

```sql
select
  (select count(*) from public."Y_codex_Layer2_Step06_L0_Lac_Filtered") as step06_cnt,
  (select count(*) from public."Y_codex_Layer2_Step06_L0_Lac_Filtered" where bs_id=0 or cell_id_dec=0) as step06_invalid_placeholder_cnt,
  (select count(*) from public."Y_codex_Layer2_Step06_L0_Lac_Filtered" where bs_id<>0 and cell_id_dec<>0) as step06_valid_cnt,
  (select count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed") as step31_cnt,
  (select count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple") as step33_cnt;
```

判定建议：

- Step31_cnt != Step06_valid_cnt ⇒ FAIL（说明 Step31 异常丢行，或仍混入非法占位数据）
- Step33_cnt != Step31_cnt ⇒ FAIL（说明 Step33 丢行或过滤）

### 5.2 Step31 join Step30 覆盖率（建议 FAIL）

```sql
select
  count(*) filter (where gps_valid_level is null) as gps_valid_level_null_cnt,
  count(*) filter (where is_collision_suspect is null) as is_collision_suspect_null_cnt,
  count(*) filter (where is_multi_operator_shared is null) as is_multi_operator_shared_null_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";
```

判定建议：任一 *_null_cnt > 0 ⇒ FAIL（说明 Step31 未完整命中 Step30，桶全集不一致或键拼接不一致）

### 5.3 wuli_fentong_bs_key 键一致性（建议 FAIL）

```sql
select
  count(*) filter (where wuli_fentong_bs_key is null) as null_cnt,
  count(*) filter (where wuli_fentong_bs_key <> concat_ws('|', tech_norm, bs_id::text, lac_dec_final::text)) as bad_cnt
from public."Y_codex_Layer3_Step30_Master_BS_Library";

select
  count(*) filter (where wuli_fentong_bs_key is null) as null_cnt,
  count(*) filter (where wuli_fentong_bs_key <> concat_ws('|', tech_norm, bs_id::text, lac_dec_final::text)) as bad_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";
```

判定建议：任一 bad_cnt>0 或 null_cnt>0 ⇒ FAIL

### 5.4 枚举集合校验（建议 FAIL）

```sql
-- Step30 gps_valid_level
select count(*) as bad_cnt
from public."Y_codex_Layer3_Step30_Master_BS_Library"
where gps_valid_level not in ('Unusable','Risk','Usable');

-- Step31 gps_status / gps_status_final / gps_source
select
  count(*) filter (where gps_status not in ('Verified','Missing','Drift')) as gps_status_bad_cnt,
  count(*) filter (where gps_status_final not in ('Verified','Missing')) as gps_status_final_bad_cnt,
  count(*) filter (where gps_source not in ('Original_Verified','Augmented_from_BS','Augmented_from_Risk_BS','Not_Filled')) as gps_source_bad_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

-- Step33 signal_fill_source
select count(*) as bad_cnt
from public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
where signal_fill_source not in ('none','cell_agg','bs_agg');

-- Step32 pass_flag（允许 PASS/FAIL/WARN）
select count(*) as bad_cnt
from public."Y_codex_Layer3_Step32_Compare"
where pass_flag not in ('PASS','FAIL','WARN');

-- Step34 pass_flag（本轮仅 PASS/FAIL）
select count(*) as bad_cnt
from public."Y_codex_Layer3_Step34_Signal_Compare"
where pass_flag not in ('PASS','FAIL');
```

判定建议：任一 bad_cnt>0 ⇒ FAIL

---

## 6) 每步验收（v3：判定标准 + 结果记录）

> 报告模板：`lac_enbid_project/Layer_3/Layer_3_验收报告模板_v3.md`

### Step30（基站主库）

对象：

- `public."Y_codex_Layer3_Step30_Master_BS_Library"`
- `public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

FAIL（阻断）：

- 主键重复数 > 0
- `gps_valid_level in ('Usable','Risk')` 的中心点出现 NULL / (0,0) / 越界

WARN（量化阈值见第 4 节）：

- Unusable 占比 > unusable_ratio_warn
- `is_collision_suspect=1` 占比 > collision_ratio_warn（并给出 Top10）

核心查询：沿用 v2（见模板）。

### Step31（明细 GPS 修正/补齐）

FAIL（阻断）：

- `src_seq_id/src_record_id` 空值数 > 0
- `gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS')` 但 `gps_status_final <> 'Verified'`

WARN（量化阈值见第 4 节）：

- Risk 回填占比 > risk_fill_ratio_warn
- Drift 占比 > drift_ratio_warn

### Step32（对比报表：v2 可读指标）

FAIL（阻断）：存在 `pass_flag='FAIL'`

WARN：存在 `pass_flag='WARN'`（必须解释并给 TopN）

核心查询（注意：汇总不吞 WARN）：

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

select *
from public."Y_codex_Layer3_Step32_Compare"
where pass_flag in ('FAIL','WARN')
order by report_section, metric_code, actual_value_num desc nulls last
limit 200;
```

### Step33（信号补齐：WARN 在本步输出）

FAIL（阻断）：

- “补齐后缺失 > 补齐前缺失”的行数 > 0

WARN（量化阈值见第 4 节）：

- none 占比 > none_ratio_warn
- bs_agg 占比 > bs_agg_ratio_warn

### Step34（信号补齐对比：本轮仅 PASS/FAIL）

FAIL（阻断）：存在 `pass_flag='FAIL'`

说明：Step34 不再输出 WARN；WARN 只在 Step33（方案 A）。

核心查询：

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

select *
from public."Y_codex_Layer3_Step34_Signal_Compare"
where pass_flag = 'FAIL'
order by metric_code, actual_value_num desc nulls last
limit 200;
```

---

## 7) 最终拍板口径（CR 规则写死）

- FAIL（阻断）：
  - CR-01/02/03 任一不满足
  - 或任一“建议 FAIL”的验收 SQL bad_cnt>0
- WARN（可继续）：
  - 仅触发被定义为 WARN 的项，且报告包含：占比、阈值、Top10 样本、解释、后续动作
- PASS：
  - 无 FAIL、无 WARN（或 WARN 已被明确接受并记录）
