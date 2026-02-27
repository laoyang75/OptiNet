# 交付文件：Layer_2（北京明细 20251201_20251207）说明与对象清单

更新时间：2025-12-17  
数据库版本：PostgreSQL 15  
schema：`public`  

本文件用于你进入 Layer_3 前的“交付确认”（中文为主，必要时括号补充英文）。

---

## 0) Layer_2 的目标（我们在这一层做了什么）

Layer_2 的定位是：把 Layer_0 的两路明细（GPS 路 / LAC 路）整理成一套 **可解释、可验收、可复跑、可审计** 的流水线，并产出三类关键资产：

1. **GPS 合规明细（行级）**：给后续“可信库构建 / 映射证据”提供干净样本。  
2. **可信库（库级）**：
   - 可信 LAC 白名单（按 `operator_id_raw + tech_norm + lac_dec`）
   - 可信 cell→lac 映射证据底座（按 `operator_id_raw + tech_norm + cell_id_dec` 聚合）
3. **LAC 路反哺后的可信明细库（行级）**：用可信映射对 LAC 路做 `lac` 的补齐/纠偏，并输出对比报表评估覆盖与增量。

---

## 1) 输入数据（Layer_0）

- GPS 源：`public."Y_codex_Layer0_Gps_base"`
- LAC 源：`public."Y_codex_Layer0_Lac"`

---

## 2) 输出对象清单（Step00~Step06）

命名规范：所有输出对象统一为 `public."Y_codex_Layer2_StepXX_*"`。

### Step00：标准化视图（VIEW）

- `public."Y_codex_Layer2_Step00_Gps_Std"`（VIEW）：GPS 路标准化视图  
- `public."Y_codex_Layer2_Step00_Lac_Std"`（VIEW）：LAC 路标准化视图（注意：是 VIEW，不要指望给它“建索引救性能”）

### Step01：基础统计（TABLE）

- `public."Y_codex_Layer2_Step01_BaseStats_Raw"`（TABLE）：Raw 基础统计（按 tech/operator/parsed_from）  
- `public."Y_codex_Layer2_Step01_BaseStats_ValidCell"`（TABLE）：仅应用 cell 起点过滤后的统计（用于对比）

### Step02：合规标记（VIEW + TABLE）

- `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（VIEW）：GPS 合规标记明细（行级）  
- `public."Y_codex_Layer2_Step02_Compliance_Diff"`（TABLE）：合规前后对比报表（原因 TopN 等）

### Step03：有效 LAC 汇总库（TABLE）

- `public."Y_codex_Layer2_Step03_Lac_Stats_DB"`（TABLE）：按 `operator+tech+lac` 聚合的统计底座

### Step04：可信 LAC 白名单（TABLE）

- `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（TABLE）：可信 LAC 库（白名单）
- 当前策略（临时策略，换窗口需重评）：`active_days=7` 必须，叠加设备/上报分位门槛（详见 `Step04_修订参考_ActiveDays7_画像_20251216.md`）

### Step05：可信映射证据底座 + 异常哨兵（TABLE + VIEW）

- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（TABLE）：在可信 LAC 白名单内，按 `operator+tech+lac+cell` 聚合映射证据  
- `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`（VIEW）：同一 `operator+tech+cell` 命中多个 `lac` 的异常哨兵

### Step06：反哺后可信明细库 + 对比报表（TABLE + TABLE）

- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（TABLE）：LAC 路反哺后可信明细库（交付明细库）  
- `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`（TABLE）：对比报表（含 7 类 dataset）

---

## 3) 执行与重跑（从哪个 SQL 开始、删表依赖怎么处理）

### 3.1 标准执行顺序（全量重跑）

按文件名顺序执行（与 RUNBOOK 一致）：

1. `lac_enbid_project/Layer_2/sql/00_step0_std_views.sql`
2. `lac_enbid_project/Layer_2/sql/01_step1_base_stats.sql`
3. `lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql`
4. `lac_enbid_project/Layer_2/sql/03_step3_lac_stats_db.sql`
5. `lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql`
6. `lac_enbid_project/Layer_2/sql/05_step5_cellid_stats_and_anomalies.sql`
7. `lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`

### 3.2 仅修订 Step06 后的最小重跑（推荐给你这次场景）

如果 Step02/03/04/05 都是正确版本，仅 Step06 逻辑更新：

- 只需要重跑：`lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`

它会自动删除并重建：

- `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（历史遗留可能是 VIEW/当前为 TABLE，脚本会自适应 drop）
- `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`

### 3.3 依赖删除的注意事项（你遇到的 Step05 DROP 失败）

由于 Step06 会依赖 Step05 的映射表：

- 重跑 Step05 前需要先删 Step06 输出对象，否则会出现“删 Step05 表被 Step06 依赖卡住”。  
- 该逻辑已写入 Step05 脚本开头，会先 drop Step06，再 drop Step05（但要求你用 `psql -f` 执行整文件，避免 DO 块被分号拆分）。

---

## 4) 验收口径（你进入 Layer_3 前建议确认的 6 件事）

1. `public."Y_codex_Layer2_Step06_L0_Lac_Filtered"` 必须是 TABLE，且能查到 `lac_dec_final/lac_enrich_status` 等派生列。  
2. `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"` 必须包含 7 类 dataset。  
3. `LAC_SUPPLEMENTED_BACKFILLED` 的规模可解释（补齐/纠偏增量）。  
4. `LAC_RAW_HAS_CELL_NO_OPERATOR` 的规模明确（用于评估是否需要“忽略运营商”的二阶段补齐）。  
5. Step05 的异常哨兵仍可用（用于碰撞保护与定位异常 cell）。  
6. Step04 白名单强度（active_days=7 + 阈值策略）在当前窗口合理；换窗口要重评。

---

## 5) 相关文档导航（建议你后续回看）

- `lac_enbid_project/Layer_2/README_人类可读版.md`
- `lac_enbid_project/Layer_2/RUNBOOK_执行手册.md`
- `lac_enbid_project/Layer_2/Data_Dictionary.md`
- `lac_enbid_project/Layer_2/Step06_L0_Lac反哺与对比说明.md`
- `lac_enbid_project/Layer_2/未来三大步骤_接口与字段说明.md`
- `lac_enbid_project/Layer_2/报告_Step06_反哺明细库与效果评估_20251217.md`

