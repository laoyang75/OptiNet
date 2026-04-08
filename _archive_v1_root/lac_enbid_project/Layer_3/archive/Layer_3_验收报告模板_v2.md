# Layer_3 验收报告模板 v2（2025-12-18）

> 用途：每次“全量跑完 Step30~34”后，用本模板生成一组 Markdown 报告，做到“一眼拍板”。

你需要产出并保存到 `lac_enbid_project/Layer_3/reports/`：

- `Step30_Report_YYYYMMDD.md`
- `Step31_Report_YYYYMMDD.md`
- `Step32_Report_YYYYMMDD.md`
- `Step33_Report_YYYYMMDD.md`
- `Step34_Report_YYYYMMDD.md`
- `Layer_3_Summary_YYYYMMDD.md`

---

## 通用：一眼拍板表（强制）

每份 Step 报告必须包含：

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| （示例）主键是否唯一 | 重复数=0 | 0 | PASS | - |

---

## Step30 报告模板

文件：`Step30_Report_YYYYMMDD.md`

### 1) 产出对象

- `public."Y_codex_Layer3_Step30_Master_BS_Library"`
- `public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

### 2) 一眼拍板表（Step30 必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| 主键是否唯一（tech_norm, bs_id, wuli_fentong_bs_key） | 重复数=0 | （填） | （填） | FAIL 直接阻断，排查 Step06 键或聚合粒度 |
| gps_valid_level 分布 | 不可全部 Unusable | （填） | （填） | 若全 Unusable：检查 Verified 点口径/Step02 has_gps |
| Usable/Risk 中心点合法 | 不为 NULL，不为(0,0)，经纬度合法 | （填） | （填） | FAIL：检查中心点计算/输入点过滤 |
| 碰撞疑似规模 | 输出数量 + Top10 | （填） | WARN/OK | 若过大：评估阈值与 Step05 哨兵影响 |
| Risk 基站可定位 | 可查询 bs_id/cell 列表 | （填） | PASS/FAIL | FAIL：补齐定位查询 |

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

-- Risk Top10（按 active_days）
select tech_norm, bs_id, wuli_fentong_bs_key, shared_operator_list, gps_valid_cell_cnt, active_days
from public."Y_codex_Layer3_Step30_Master_BS_Library"
where gps_valid_level='Risk'
order by active_days desc nulls last
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
| 回溯字段空值数 | 0 | （填） | （填） | FAIL：检查 Step06 字段透传 |
| gps_status × gps_source 组合 | 组合关系合理 | （填） | （填） | FAIL：修正规则或阈值 |
| Augmented 之后 final=Missing | 应为 0 | （填） | （填） | FAIL：回填逻辑错误 |
| 风险基站回填规模 | 输出数量 + Top10 | （填） | WARN/OK | 过大：评估 Step30 Risk 判定与阈值 |

### 3) 核心查询

```sql
-- 回溯字段空值
select count(*) filter (where src_seq_id is null or src_record_id is null) as bad_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

-- 组合分布
select gps_status, gps_source, gps_status_final, count(*) as row_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
group by 1,2,3
order by row_cnt desc
limit 50;

-- Augmented 后不应仍 Missing
select count(*) as bad_cnt
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
where gps_source in ('Augmented_from_BS','Augmented_from_Risk_BS')
  and gps_status_final <> 'Verified';

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

## Step32 报告模板（对比表）

文件：`Step32_Report_YYYYMMDD.md`

### 1) 产出对象

- `public."Y_codex_Layer3_Step32_Compare"`（v2：含 metric_code/中文指标/Pass 标记）

### 2) 一眼拍板表（Step32 必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| has_gps_after >= has_gps_before | 必须 | （填） | （填） | FAIL：回填逻辑或状态判定有错 |
| Missing→Filled / Drift→Corrected | 输出分布可解释 | （填） | （填） | 若异常：回看 Step31 组合分布 |
| Risk/Collision 基站规模 | 输出 + TopN | （填） | WARN/OK | 若过大：调整阈值与策略升级点 |

### 3) 核心查询

```sql
select metric_code, metric_name_cn, expected_rule_cn,
       sum(actual_value_num) as actual_value_sum,
       min(pass_flag) as min_pass_flag
from public."Y_codex_Layer3_Step32_Compare"
group by 1,2,3
order by metric_code;

-- FAIL/WARN 明细
select *
from public."Y_codex_Layer3_Step32_Compare"
where pass_flag in ('FAIL','WARN')
order by report_section, metric_code, actual_value_num desc nulls last
limit 200;
```

---

## Step33/34 报告模板（信号补齐摸底）

Step33 文件：`Step33_Report_YYYYMMDD.md`  
Step34 文件：`Step34_Report_YYYYMMDD.md`

### Step33 一眼拍板表（必含）

| 检查项（中文） | 预期/阈值（中文） | 实际值（从SQL取） | 结论（PASS/FAIL/WARN） | 处理建议 |
|---|---|---:|---|---|
| signal_fill_source 分布 | 输出 none/cell_agg/bs_agg | （填） | PASS/WARN | none 过高：信号字段源不足/解析缺失 |
| 补齐后缺失不应增加 | after <= before | （填） | FAIL/WARN | FAIL：补齐逻辑错误 |

### Step33 TopN（必含）

```sql
-- bs_agg Top10（便于判断是否 “只能回退到基站”）
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

### Step34 一眼拍板表（必含）

Step34 使用 `public."Y_codex_Layer3_Step34_Signal_Compare"`（v2：含 Pass 标记）：

```sql
select metric_code, metric_name_cn, expected_rule_cn,
       sum(actual_value_num) as actual_value_sum,
       min(pass_flag) as min_pass_flag
from public."Y_codex_Layer3_Step34_Signal_Compare"
group by 1,2,3
order by metric_code;

select *
from public."Y_codex_Layer3_Step34_Signal_Compare"
where pass_flag in ('FAIL','WARN')
order by metric_code, actual_value_num desc nulls last
limit 200;
```

---

## 总览报告模板

文件：`Layer_3_Summary_YYYYMMDD.md`

必须包含：

- 本次执行窗口（日期范围、是否冒烟/全量）
- Step30~34 的 Pass/Fail/Warn 汇总（每步一行）
- 主要风险 Top3（碰撞疑似、Risk 回填、信号 none 规模）
- 下一轮需要调整的参数（阈值、策略升级点）

