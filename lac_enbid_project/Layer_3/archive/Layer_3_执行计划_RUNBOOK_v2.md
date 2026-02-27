# Layer_3 执行计划 RUNBOOK v2（2025-12-18）

> v2 在 v1 基础上补齐：验收条件（阈值/判定标准）+ 报告产出机制。  
> v1 底稿：`lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v1.md`

---

## 0) 执行模型（不变）

- 人类：后台执行全量 SQL（Step30~34）
- 我（assistant）：冒烟跑通 + MCP 自检 + 生成验收报告 + 写 RUNLOG

---

## 1) 执行前检查（必须）

### 1.1 输入对象存在性（冻结）

- `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`
- `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`
- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`
- `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`
- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE）

### 1.2 会话级调优

参考 `lac_enbid_project/服务器配置与SQL调优建议.md`；Layer_3 每个 SQL 文件顶部已内嵌推荐 `SET`。

---

## 2) 执行顺序（必须按顺序）

1. `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`
2. `lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql`
3. `lac_enbid_project/Layer_3/sql/32_step32_compare.sql`
4. `lac_enbid_project/Layer_3/sql/33_step33_signal_fill_simple.sql`
5. `lac_enbid_project/Layer_3/sql/34_step34_signal_compare.sql`
6. `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`

---

## 3) 冒烟模式（强制先跑）

每个 Step SQL 顶部都有 `params` CTE：

- `is_smoke=true`
- `smoke_report_date=某天`
- `smoke_operator_id_raw=某运营商`（例如 46000）

冒烟通过后再跑全量（后台执行）。

---

## 4) 每步验收（v2：判定标准 + 结果记录）

> 产出报告：按 `lac_enbid_project/Layer_3/archive/Layer_3_验收报告模板_v2.md` 填写并保存到 `lac_enbid_project/Layer_3/reports/`。

### Step30（基站主库）

对象：

- `public."Y_codex_Layer3_Step30_Master_BS_Library"`
- `public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

判定标准（用于报告 PASS/FAIL/WARN）：

- FAIL（阻断）：
  - 主键重复数 > 0
  - `gps_valid_level in ('Usable','Risk')` 的中心点出现 NULL / (0,0) / 越界
- WARN（不阻断，但必须记录 TopN）：
  - `gps_valid_level='Unusable'` 占比异常高
  - `is_collision_suspect=1` 数量异常高（给出 Top10）

核心查询（执行并把结果粘贴到报告）：

```sql
-- 主键重复数（必须=0）
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

-- 中心点合法性（Usable/Risk 必须合法）
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

### Step31（明细 GPS 修正/补齐）

对象：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`

判定标准：

- FAIL（阻断）：
  - `src_seq_id/src_record_id` 空值数 > 0
  - `gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS')` 但 `gps_status_final <> 'Verified'`
- WARN：
  - `Augmented_from_Risk_BS` 规模异常（给出 Top10）

核心查询：

```sql
select count(*) filter (where src_seq_id is null or src_record_id is null) as bad_trace_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

select count(*) as bad_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
where gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS')
  and gps_status_final <> 'Verified';

select gps_status, gps_source, gps_status_final, count(*) as row_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
group by 1,2,3
order by row_cnt desc
limit 50;
```

### Step32（对比报表：v2 可读指标）

对象：`public."Y_codex_Layer3_Step32_Compare"`

判定标准：

- FAIL（阻断）：存在 `pass_flag='FAIL'`
- WARN：存在 `pass_flag='WARN'`（需解释原因与是否调参）

核心查询：

```sql
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

### Step33/34（信号补齐摸底）

对象：

- `public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`
- `public."Y_codex_Layer3_Step34_Signal_Compare"`

判定标准：

- FAIL：存在 “补齐后缺失 > 补齐前缺失” 的 PASS=FAIL 指标
- WARN：`signal_fill_source='none'` 占比异常高

核心查询：

```sql
select signal_fill_source, count(*) as row_cnt
from public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
group by 1
order by row_cnt desc;

select pass_flag, count(*) as metric_rows
from public."Y_codex_Layer3_Step34_Signal_Compare"
group by 1
order by 1;

select *
from public."Y_codex_Layer3_Step34_Signal_Compare"
where pass_flag in ('FAIL','WARN')
order by metric_code, actual_value_num desc nulls last
limit 200;
```

---

## 5) RUNLOG（不变）

全量执行后生成/更新：

- `lac_enbid_project/Layer_3/RUNLOG_YYYYMMDD.md`

要求：每步至少 5 条 Summary Query 结果 + TopN 样本（满足快速定位）。
