# 执行顺序与验收清单（工程执行版）

> Date: 2025-12-19  
> 目标：让工程人员按这张清单“照着跑”，并能快速判断是否成功。

## 0) 不需要执行的文件

- `lac_enbid_project/Layer_3/sql/00_layer3_placeholders.sql`：no-op 占位文件

## 1) Layer_2 执行顺序（Step00~Step06）

按顺序执行：

1. `lac_enbid_project/Layer_2/sql/00_step0_std_views.sql`
2. `lac_enbid_project/Layer_2/sql/01_step1_base_stats.sql`
3. `lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql`
4. `lac_enbid_project/Layer_2/sql/03_step3_lac_stats_db.sql`
5. `lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql`
6. `lac_enbid_project/Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql`
7. `lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`

完成后必须存在（且 Step06 必须为 TABLE）：
- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE）
- `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（VIEW）
- `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（TABLE）
- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（TABLE）

## 2) Layer_3 执行顺序（Step30~34 + 99）

按顺序执行：

1. `lac_enbid_project/Layer_3/sql/30_step30_master_bs_library.sql`
2. `lac_enbid_project/Layer_3/sql/31_step31_cell_gps_fixed.sql`
3. `lac_enbid_project/Layer_3/sql/32_step32_compare.sql`
4. `lac_enbid_project/Layer_3/sql/33_step33_signal_fill_simple.sql`
5. `lac_enbid_project/Layer_3/sql/34_step34_signal_compare.sql`
6. `lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`

## 3) 最低验收（跑完必须检查）

### 3.1 对象存在性（最先看）

```sql
select
  to_regclass('public."Y_codex_Layer3_Step30_Master_BS_Library"') as step30,
  to_regclass('public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"') as step31,
  to_regclass('public."Y_codex_Layer3_Step32_Compare"') as step32,
  to_regclass('public."Y_codex_Layer3_Step33_Signal_Fill_Simple"') as step33,
  to_regclass('public."Y_codex_Layer3_Step34_Signal_Compare"') as step34;
```

### 3.2 Step30 主键唯一

```sql
select count(*) - count(distinct (tech_norm, bs_id, lac_dec_final, wuli_fentong_bs_key)) as dup_cnt
from public."Y_codex_Layer3_Step30_Master_BS_Library";
```

### 3.3 Step31/33 行数一致（SR-02）

```sql
select
  (select count(*) from public."Y_codex_Layer2_Step06_L0_Lac_Filtered") as step06_cnt,
  (select count(*) from public."Y_codex_Layer3_Step31_Cell_Gps_Fixed") as step31_cnt,
  (select count(*) from public."Y_codex_Layer3_Step33_Signal_Fill_Simple") as step33_cnt;
```

### 3.4 Step32 必须 FAIL=0（允许 WARN）

```sql
select count(*) as fail_cnt
from public."Y_codex_Layer3_Step32_Compare"
where pass_flag='FAIL';
```

### 3.5 Step33 不允许补齐后反向变差

```sql
select count(*) as after_gt_before_cnt
from public."Y_codex_Layer3_Step33_Signal_Fill_Simple"
where signal_missing_after_cnt > signal_missing_before_cnt;
```

### 3.6 Gate-0 COMMENT 双语覆盖（硬阻断）

按 `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md` 第 2 节的 Gate-0 SQL 执行；任一表缺 COMMENT 或不含 `CN:`/`EN:` 即 FAIL。

## 4) 工程手册（推荐阅读）

- Layer_2：`lac_enbid_project/Layer_2/Layer_2_Technical_Manual.md`
- Layer_3：`lac_enbid_project/Layer_3/Layer_3_Technical_Manual.md`

