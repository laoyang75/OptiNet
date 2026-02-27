# Layer_3 任务理解与口径对齐 v3（2025-12-18）

> v3 不改决策 A~F（冻结），只把“中文友好 + 人类可快速拍板验收”做成闭环：  
> - Gate-0：DB COMMENT 双语覆盖=100%（硬阻断）；  
> - Step32 汇总不吞 WARN（FAIL > WARN > PASS）；  
> - Step34 口径统一：本轮采用方案 A，Step34 指标表 `pass_flag` 仅 PASS/FAIL，WARN 只在 Step33。

监督任务单：`lac_enbid_project/Layer_3/notes/fix3.md`

底稿（延续 v2，不换思路）：

- `lac_enbid_project/Layer_3/archive/Layer_3_任务理解与口径对齐_v2.md`
- `lac_enbid_project/Layer_3/archive/Layer_3_执行计划_RUNBOOK_v2.md`
- `lac_enbid_project/Layer_3/archive/Layer_3_Data_Dictionary_v2.md`

---

## 1) v3 核心改动点（与 v2 的差异）

### 1.1 COMMENT 双语覆盖率=100% 变成硬验收（CR-01）

- COMMENT 统一格式（用于机器校验）：
  - TABLE：`CN: ...; EN: ...`
  - COLUMN：`CN: 中文名=...; 说明=...; EN: ...`
- 99 脚本：`lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`
- Gate-0 验收：写入 `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md`

### 1.2 Step32 汇总不吞 WARN（CR-02）

- 禁止 `min(pass_flag)` 之类聚合（会在 PASS/WARN/FAIL 混合时吞 WARN）
- 汇总优先级必须为：FAIL > WARN > PASS
- 落地：`lac_enbid_project/Layer_3/Layer_3_验收报告模板_v3.md` + `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md`

### 1.3 Step34 WARN 口径统一（CR-03，方案 A）

- `public."Y_codex_Layer3_Step34_Signal_Compare".pass_flag` 只允许 PASS/FAIL（保持表结构不变）
- “signal_fill_source='none' 占比异常高”的 WARN 只在 Step33 报告中呈现
- Step34 报告只查 FAIL（不再查 WARN）

---

## 2) 输入依赖冻结（不变）

Layer_3 只依赖 Layer_2 的以下对象（冻结）：

- Step02：`public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`
- Step04：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`
- Step05：`public."Y_codex_Layer2_Step05_CellId_Stats_DB"` + `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`
- Step06：`public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（必须 TABLE）

---

## 3) 决策口径冻结（A~F，不变）

与 v2 一致，详见：`lac_enbid_project/Layer_3/archive/Layer_3_任务理解与口径对齐_v2.md`

---

## 4) v3 额外强调：跨步一致性（SR-02，推荐 FAIL）

在 v3 中，我们明确把以下事故类型视为“应优先阻断”的工程事故（除非明确写入允许比例）：

1. 行数丢失：Step31_cnt != Step06_cnt，或 Step33_cnt != Step31_cnt  
2. join 失败：Step31 中 `gps_valid_level/is_collision_suspect/is_multi_operator_shared` 出现 NULL  
3. key 不一致：`wuli_fentong_bs_key != concat_ws('|', tech_norm, bs_id, lac_dec_final)`  
4. 枚举脏值：gps/source/status、signal_fill_source、pass_flag 出现非法取值

对应 SQL 已写入 `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v3.md`。
