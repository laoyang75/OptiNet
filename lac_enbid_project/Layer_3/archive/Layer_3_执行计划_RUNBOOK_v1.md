# Layer_3 执行计划 RUNBOOK v1（2025-12-18）

> 执行模型：人类在数据库后台执行大 SQL；我用 MCP 做冒烟、自检与审计推进（沿用 Layer_2 协作方式）。

---

## 0) 执行前检查（必须）

### 0.1 输入对象存在性（至少这些）

- `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`
- `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`
- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`
- `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`
- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE）

### 0.2 会话级调优（建议）

参考 `lac_enbid_project/服务器配置与SQL调优建议.md`；Layer_3 的每个 SQL 文件顶部已内嵌推荐 `SET`。

---

## 1) 执行顺序（必须按顺序）

1. Step30：`lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`
2. Step31：`lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql`
3. Step32：`lac_enbid_project/Layer_3/sql/32_step32_compare.sql`
4. Step33：`lac_enbid_project/Layer_3/sql/33_step33_signal_fill_simple.sql`
5. Step34：`lac_enbid_project/Layer_3/sql/34_step34_signal_compare.sql`
6. 统一注释：`lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`

---

## 2) 冒烟模式（强制先跑）

每个 Step SQL 顶部都有 `params` CTE：

- `is_smoke`：改为 `true`
- `smoke_report_date`：设置一个日期
- `smoke_operator_id_raw`：设置一个运营商（例如 `46000`）

冒烟验收通过后，再把 `is_smoke=false` 跑全量（后台执行）。

---

## 3) 每步验收（Summary Queries 清单）

### Step30（基站主库）

对象：
- `public."Y_codex_Layer3_Step30_Master_BS_Library"`
- `public."Y_codex_Layer3_Step30_Gps_Level_Stats"`

验收：
```sql
-- 1) 行数
select count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library";

-- 2) 主键唯一（tech_norm, bs_id, wuli_fentong_bs_key）
select tech_norm, bs_id, wuli_fentong_bs_key, count(*)
from public."Y_codex_Layer3_Step30_Master_BS_Library"
group by 1,2,3
having count(*)>1;

-- 3) gps_valid_level 分布
select gps_valid_level, count(*) from public."Y_codex_Layer3_Step30_Master_BS_Library" group by 1 order by 2 desc;

-- 4) Risk/Collision 数量
select
  count(*) filter (where gps_valid_level='Risk') as risk_bs_cnt,
  count(*) filter (where is_collision_suspect=1) as collision_bs_cnt
from public."Y_codex_Layer3_Step30_Master_BS_Library";

-- 5) Step30 统计表是否产出
select * from public."Y_codex_Layer3_Step30_Gps_Level_Stats" order by bs_cnt desc limit 50;

-- 6) Risk 可定位样例（bs_id/cell 列表）：按需改 where 条件
select operator_id_raw, tech_norm, bs_id, lac_dec_final, cell_id_dec
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
where is_compliant and has_gps and tech_norm in ('4G','5G')
limit 50;
```

### Step31（明细 GPS 修正/补齐）

对象：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`

验收：
```sql
-- 1) 行数
select count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

-- 2) 追溯字段非空（抽样）
select count(*) filter (where src_seq_id is null or src_record_id is null) as bad
from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed";

-- 3) gps_status/gps_source 分布
select gps_status, gps_source, count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
group by 1,2 order by 3 desc;

-- 4) 风险基站回填规模
select count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
where gps_source='Augmented_from_Risk_BS' and is_from_risk_bs=1;

-- 5) 纠偏样例（Drift→Corrected）
select * from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"
where gps_status='Drift' and gps_status_final='Verified'
limit 50;
```

### Step32（对比报表）

对象：`public."Y_codex_Layer3_Step32_Compare"`

验收：
```sql
select report_section, count(*) from public."Y_codex_Layer3_Step32_Compare" group by 1;
select * from public."Y_codex_Layer3_Step32_Compare" where report_section='GPS_GAIN' order by report_date desc nulls last limit 50;
select * from public."Y_codex_Layer3_Step32_Compare" where report_section='BS_RISK' order by bs_cnt desc nulls last limit 50;
```

### Step33/34（信号补齐摸底）

对象：
- `public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`
- `public."Y_codex_Layer3_Step34_Signal_Compare"`

验收：
```sql
-- Step33 行数 & 补齐来源
select count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple";
select signal_fill_source, count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple" group by 1 order by 2 desc;

-- Step34 摸底报表
select report_section, count(*) from public."Y_codex_Layer3_Step34_Signal_Compare" group by 1;
select * from public."Y_codex_Layer3_Step34_Signal_Compare" where report_section='OVERALL' order by row_cnt desc;
```

---

## 4) 审计推进（RUNLOG 要求）

人类跑完每步全量 SQL 后，我将：

- 用 MCP 执行本 RUNBOOK 的 Summary Queries（每步至少 5 条）
- 写入 `lac_enbid_project/Layer_3/RUNLOG_YYYYMMDD.md`：记录结果 + 异常样本（TopN）

