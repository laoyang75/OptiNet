# Layer_3 任务理解与口径对齐 v1（2025-12-18）

> 本文件用于“对齐口径 + 冻结输入依赖 + 写死决策（A~F）”，确保 Layer_3 可执行、可验收、可迭代。

---

## 0) 背景与目标（必须）

Layer_2 已交付：严格过滤（行级合规）+ 可信库（LAC/映射证据/异常哨兵）+ 反哺后的可信明细库（Step06）。

Layer_3 的目标：把 Layer_2 的资产升级为**以基站（ENBID/gNB，即 `bs_id`）为索引的可画像数据集**，并产出：

1) **基站主库**：站级画像 + 共建标记 + 基站中心点/GPS质量 + 碰撞疑似标记  
2) **按基站回填/纠偏后的明细库**：保留回溯字段与来源标记（gps_source/gps_status）  
3) **对比报表**：GPS 修正收益、风险规模、碰撞疑似规模  
4) **信号字段补齐摸底**：本轮先做“能补多少/补不齐多少”的统计 + 简单补齐（不追求最优）

---

## 1) 输入依赖冻结（Layer_3 开始前写死）

Layer_3 只依赖 Layer_2 的以下对象（表名/用途冻结，不再改名）：

- Step02：`public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`
  - 用途：提供“可信 GPS 点”样本（本项目以 `is_compliant=true AND has_gps=true` 作为 Verified 等价口径）
- Step04：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`
  - 用途：可信 LAC 白名单（用于 `lac_dec_final` 的可信约束）
- Step05：`public."Y_codex_Layer2_Step05_CellId_Stats_DB"` + `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`
  - 用途：cell→lac 映射证据底座 + 碰撞/错归并风险哨兵
- Step06：`public."Y_codex_Layer2_Step06_L0_Lac_Filtered"`（必须是 TABLE）
  - 用途：可信明细库（LAC 路反哺后明细；Layer_3 的“主输入明细”）

---

## 2) 决策定稿（A~F，写死）

### A) bs_id 生成规则（选项 1）

- 优先使用 Layer_0/Layer_2 已解析字段 `bs_id`（若存在）
- 若缺失：按 `tech_norm` 回退派生
  - 4G：`bs_id = floor(cell_id_dec / 256)`
  - 5G：`bs_id = floor(cell_id_dec / 4096)`
- 规则必须可版本化：通过 SQL 顶部 `params` 或文档声明可替换

### B) 共建标记 + 物理分桶键

- 站级共建统计保留两种视角：
  1) 运营商视角：`(operator_id_raw, tech_norm, bs_id)`
  2) 物理站视角：引入 `lac_dec_final` 防止跨 LAC 错配后误判共建
- 物理分桶键字段名固定：
  - 字段名：`wuli_fentong_bs_key`
  - 含义：`tech_norm|bs_id|lac_dec_final`

### C) 基站 GPS 可用性分级（先统计评估，再用于回填决策）

仅统计“有效合法 GPS 值”，本项目 v1 口径为：

- Verified 等价：`is_compliant=true AND has_gps=true`（来自 Step02）
- 经纬度合法：`lon/lat` 合法且非 `(0,0)`（在 Step00/Step02 的 `has_gps` 已封装）

分级规则（按 `gps_valid_cell_cnt`）：

- `0` → Unusable（不可用）
- `1` → Risk（风险）
- `>1` → Usable（可用）

并要求能定位 Risk（可查询 bs_id / cell 列表）。

### D) 基站中心点与离散度（简单鲁棒 v1）

- 先把点按 `cell_id_dec` 聚合成 cell 代表点（lon/lat 中位数）
- `N=0/1/≥2` 分别处理（Unusable/Risk/Usable）
- 当 `N>=3` 且 `gps_max_dist_m` 超过阈值：
  - 剔除 1 个最大偏移 cell 点（最多剔除 1 个）
  - 重算中心点与离散度，并记录 `outlier_removed_cnt`
- 碰撞疑似标记：
  - 若重算后 `gps_p90_dist_m` 仍过大，或命中 Step05 多 LAC 哨兵 → `is_collision_suspect=1`

未来升级点（不阻断本轮）：

- `gps_valid_cell_cnt >= 30` 时启用更严策略（阈值/算法后续评估）

### E) Step31 回填/纠偏字段与来源标记（必须）

必须保留：

- `gps_source`：Original_Verified / Augmented_from_BS / Augmented_from_Risk_BS / Not_Filled
- `gps_status`：Verified / Drift / Missing（本项目 v1 由 Layer_3 计算，见下）
- 必须可回溯：`src_seq_id` / `src_record_id`

### F) 信号补齐（摸底版）

- 先盘点现有信号字段（以库里真实存在的字段为准）：本项目当前使用 `sig_rsrp/sig_rsrq/sig_sinr/sig_rssi/sig_dbm/sig_asu_level/sig_level/sig_ss`
- 简单补齐策略：
  - 先按 cell 聚合（中位数）补齐
  - 再回退到 bs 聚合（中位数）补齐
  - 写入 `signal_fill_source`：cell_agg / bs_agg / none

---

## 3) Layer_3 输出对象（命名冻结）

- Step30：`public."Y_codex_Layer3_Step30_Master_BS_Library"`
- Step30 统计：`public."Y_codex_Layer3_Step30_Gps_Level_Stats"`
- Step31：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`
- Step32：`public."Y_codex_Layer3_Step32_Compare"`
- Step33：`public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`
- Step34：`public."Y_codex_Layer3_Step34_Signal_Compare"`

---

## 4) gps_status 的“兜底映射方案”（对应 Layer_2 字段差异）

对齐要求指出 Step02 可能没有显式 `gps_status=Verified/Drift/Missing`。

本项目 v1 在 Step31 计算 `gps_status`（原始判定）：

- Missing：`has_gps=false`
- Drift：`has_gps=true` 且距离基站中心点 `gps_dist_to_bs_m > drift_threshold_m`
- Verified：其余情况（不覆盖）

并额外输出 `gps_status_final`（修正后状态）用于 Step32 对比统计。

---

## 5) 未决项/后续评估项（必须留下）

- 离散度阈值（outlier_remove / collision / drift）：当前提供默认值，后续通过 Step30/32 分布评估迭代
- `gps_valid_cell_cnt >= 30` 的策略升级：只记录为未来评估，不作为本轮阻断
- 信号字段策略升级：本轮仅做聚合补齐与摸底统计；“同 cell 最近时间”的时序补齐可作为后续增强

