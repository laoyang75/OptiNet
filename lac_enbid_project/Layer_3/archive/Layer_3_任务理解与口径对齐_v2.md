# Layer_3 任务理解与口径对齐 v2（2025-12-18）

> v2 在 v1 的基础上补齐两件事：  
> 1) 中文友好（人类不看 SQL 也能理解字段与枚举）；  
> 2) 可快速验收（每步跑完能一眼拍板 PASS/FAIL/WARN）。

底稿（v1，不换思路，只做增强）：

- `lac_enbid_project/Layer_3/Layer_3_任务理解与口径对齐_v1.md`
- `lac_enbid_project/Layer_3/Layer_3_执行计划_RUNBOOK_v1.md`
- `lac_enbid_project/Layer_3/Layer_3_Data_Dictionary_v1.md`

---

## 1) 本轮硬性问题与修订目标（必须）

### 1.1 中文友好不足（硬伤）

v1 主要是字段清单，缺少逐字段中文含义、取值范围、示例、来源与生成逻辑。  
v2 目标：做到“人类不看 SQL 也能理解每个字段”。

落地方式：

- v2 字段字典：`lac_enbid_project/Layer_3/archive/Layer_3_Data_Dictionary_v2.md`
- 数据库 COMMENT：`lac_enbid_project/Layer_3/sql/99_layer3_comments.sql`（覆盖所有输出表/字段）

### 1.2 每步结果不可快速判断是否满足条件

v1 提供 Summary Queries，但缺“验收条件→实际值→PASS/FAIL/WARN”。  
v2 目标：每步全量跑完必须生成可读报告。

落地方式：

- 报告模板：`lac_enbid_project/Layer_3/archive/Layer_3_验收报告模板_v2.md`
- 报告产出目录：`lac_enbid_project/Layer_3/reports/`

---

## 2) 输入依赖冻结（不变）

Layer_3 只依赖 Layer_2 的以下对象（冻结）：

- Step02：`public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（可信 GPS 点样本：`is_compliant=true AND has_gps=true`）
- Step04：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（可信 LAC 白名单）
- Step05：`public."Y_codex_Layer2_Step05_CellId_Stats_DB"` + `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`（映射证据 + 哨兵）
- Step06：`public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（必须是 TABLE，Layer_3 主输入明细）

---

## 3) 决策口径冻结（A~F，不变）

与 v1 完全一致（此处只复述结论，不再展开争议）：

- A：`bs_id` 优先用已解析字段；缺失才按 4G/5G 回退派生（4G/256, 5G/4096）
- B：共建两视角；物理分桶键字段固定 `wuli_fentong_bs_key=tech_norm|bs_id|lac_dec_final`
- C：有效 GPS 分级：`gps_valid_cell_cnt=0 Unusable, =1 Risk, >1 Usable`，且 Risk 可定位
- D：中心点简单鲁棒：N>=3 时最多剔 1 个最大偏移点；离散仍大则标 `is_collision_suspect=1`
- E：Step31 必须保留 `gps_source/gps_status` 与回溯字段
- F：信号补齐本轮做摸底 + 简单补齐，并输出来源分布

---

## 4) 输出对象冻结（不变）

- Step30：`public."Y_codex_Layer3_Step30_Master_BS_Library"`
- Step30 统计：`public."Y_codex_Layer3_Step30_Gps_Level_Stats"`
- Step31：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`
- Step32：`public."Y_codex_Layer3_Step32_Compare"`
- Step33：`public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`
- Step34：`public."Y_codex_Layer3_Step34_Signal_Compare"`

---

## 5) gps_status 的兜底方案（v2 明确写死）

由于 Step02 没有显式 `gps_status=Verified/Drift/Missing`，本项目在 Step31 计算：

- Missing：`has_gps=false`
- Drift：`has_gps=true` 且 `gps_dist_to_bs_m > drift_threshold_m`
- Verified：其余情况

并输出：

- `gps_status`（原始判定）
- `gps_status_final`（修正后：Verified/Missing）

阈值：`drift_threshold_m` 作为 Step31 顶部 `params`（可调参数，后续评估迭代）。

---

## 6) v2 验收机制（强制）

每次全量跑完后必须生成：

- `lac_enbid_project/Layer_3/reports/Step30_Report_YYYYMMDD.md`
- `lac_enbid_project/Layer_3/reports/Step31_Report_YYYYMMDD.md`
- `lac_enbid_project/Layer_3/reports/Step32_Report_YYYYMMDD.md`
- `lac_enbid_project/Layer_3/reports/Step33_Report_YYYYMMDD.md`
- `lac_enbid_project/Layer_3/reports/Step34_Report_YYYYMMDD.md`
- `lac_enbid_project/Layer_3/reports/Layer_3_Summary_YYYYMMDD.md`

报告必须包含：

- 一眼拍板表（预期/实际/PASS-FAIL-WARN/建议）
- 至少 2 个 TopN 可定位样本（Top10）

模板见：`lac_enbid_project/Layer_3/archive/Layer_3_验收报告模板_v2.md`。

---

## 7) 未决项/后续评估项（必须留下）

- `gps_valid_cell_cnt >= 30` 的策略升级：记录为未来评估，不作为本轮阻断
- 离散度阈值（outlier_remove/collision/drift）：默认值先给出，通过分布评估迭代
- 信号字段来源不足时：本轮允许 `signal_fill_source=none`，并把“下一步需要扩展的 L0 解析字段清单”写入报告
