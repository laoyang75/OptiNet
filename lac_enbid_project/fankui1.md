# A. 总体原则（给 agent 的工程约束）

## A1. 三段式总流程（对应你的长期路线）

你上传的整体思路里，流程被明确拆成 3 个核心阶段：**统计建库 → 清洗纠偏 → 层级修正**。
你当前做的 Layer_2（Step1~6）属于第一阶段“统计建库”的落地子集；未来 3 个大步骤就是阶段二+阶段三：逐条补数纠偏、构建 enbid/基站库并回填 GPS。

## A2. “最细粒度 + 保留组逻辑”的运营商字段方案

* **运营商id_细粒度（operator_id_raw）**：直接来自 `运营商id`
* **运营商组_提示（operator_group_hint）**：保留组逻辑，但不改变主流程主键

  * 至少要支持：`46000/46015/46020` → 同一组（你已确认）
  * CU/CT 是否混合：暂时**不强行合并**，先留给后续全国大样本再调口径

> 结论：所有“主库/汇总主键”用 `operator_id_raw`；所有报表同时给出 `operator_group_hint` 视角。

## A3. 统一标准化视图（建议作为 Layer_2 的 Step0）

为了让后续每一步 SQL 不重复造轮子，建议先做一个标准化视图（不改变原表，只派生字段）：

**输入**：`public."Y_codex_Layer0_Gps_base"`
**输出**：`v_layer2_gps_std`（视图）

派生字段建议最少包含：

* 制式_标准化（tech_norm）：`4G/5G/2_3G/其他`
* 运营商id_细粒度（operator_id_raw）
* 运营商组_提示（operator_group_hint）
* 上报日期（report_date）：`date(ts_std)`（你已确认以 ts_std 为准）
* lac长度（lac_len）、cell长度（cell_len）用于 4G/5G 辅助判别（你说不能改字段名，只能辅助标注）
* 是否有cell（has_cellid）、是否有lac（has_lac）、是否有gps（has_gps）——专门用来解决你说的“抽取到了但无值也被统计”的问题（后续补数阶段要用）

---

# B. Layer_2（当前 Step1~6）每一步的合理输入/输出 + 核心统计字段

下面每一步都按：**目的 / 输入 / 输出 / 主键粒度 / 必做指标（核心字段）/ 必看异常** 来写，agent 可以直接照着落表或落视图。

---

## Step1：Layer_2 基础统计（Raw + ValidCell 两套）

**目的**：把输入数据“形态”锚定，作为后续所有对比基线。

**输入**：`v_layer2_gps_std`

**输出（建议两张统计表或两个 view）**

1. `rpt_step1_base_stats_raw`：完全 Raw，不引用 Layer_1 合规
2. `rpt_step1_base_stats_valid_cell`：仅应用 “cell_id 正常值规则”（来自 Layer_1 Cell_Filter_Rules），不做其它合规

**核心指标（两套都要）**

* 行数（row_cnt）
* 去重小区数（cell_cnt = count distinct cell_id_dec，排除 null）
* 去重 lac 数（lac_cnt = count distinct lac_dec，排除 null）
* 设备数（device_cnt：优先 did，其次 oaid；用哪个要固定）
* 结构分布：

  * 制式_标准化（tech_norm）
  * 运营商id_细粒度（operator_id_raw）+ 运营商组_提示（operator_group_hint）
  * parsed_from（cell_infos / ss1）
* “无值统计”（你特别关心）：

  * has_cellid=false 占比
  * has_lac=false 占比
  * has_gps=false 占比

**必看异常**

* `ss1` 是否几乎全是 unmatched（否则上游解析可能有问题）
* `tech_norm=其他` 的比例（用来判断 tech 解析质量）

---

## Step2：合规标记（行级绝对合规）+ 合规前后对比

**目的**：按 Layer_1 规则做“行级绝对合规”标注；并输出合规过滤前后结构变化。

**输入**：`v_layer2_gps_std` + Layer_1 两份规则（Cell/LAC）

**输出**

1. `d_step2_gps_compliance_marked`（视图/表）：全量保留，但带标记

   * 是否合规（is_compliant）
   * 不合规原因（non_compliant_reason，多原因可拼接）
2. `rpt_step2_compliance_diff`：合规前后对比报表

**主键粒度**：行级（seq_id 或 记录id）

**核心指标**

* 合规保留行数/剔除行数/剔除占比
* 按维度的结构变化（前后都要）：

  * tech_norm
  * operator_id_raw / operator_group_hint
  * parsed_from
* 不合规原因 TopN（帮助你快速定位规则是否过严/过松）

---

## Step3：有效 LAC 汇总库（你要的“LAC 维度统计主表”）

你文档里对 LAC 统计库的定义非常清楚：按 (network_group, tech, lac) 聚合，统计 record_count、distinct_cellid_count、distinct_device_count、first/last、active_days。
我们这里把 network_group 换成你当前的 operator_id_raw + operator_group_hint（同时保留）。

**输入**：`d_step2_gps_compliance_marked`（只取 is_compliant=true）

**输出**：`d_step3_lac_stats_db`（表/物化视图）

**主键粒度（你已确认）**

* 运营商id_细粒度（operator_id_raw） + 制式_标准化（tech_norm） + lac_dec

**核心字段/指标（建议至少这些）**

* 总上报次数（record_count）
* 关联小区数（distinct_cellid_count）
* 关联设备数（distinct_device_count）
* 首次出现（first_seen_dt / first_seen_date）
* 最后出现（last_seen_dt / last_seen_date）
* 活跃天数（active_days = count distinct report_date）
* （可选但建议）“无值污染监控”：该 LAC 下 has_cellid=false 的占比、has_gps=false 的占比（方便你判断是不是“空值堆出来的假活跃”）

---

## Step4：可信 LAC（先用 active_days 规则跑通）

**目的**：从 Step3 的 LAC 统计库中过滤出“可信集合”。

**输入**：`d_step3_lac_stats_db`

**输出**：`d_step4_master_lac_lib`（可信 LAC 库）

**规则（你当前要求）**

* active_days 取本周期最大天数（7天窗口就等价看满天）

**核心字段**

* 主键三元组：operator_id_raw + tech_norm + lac_dec
* 透传 Step3 的指标列（record_count / distinct_cellid_count / distinct_device_count / first/last / active_days）
* 是否可信LAC（is_trusted_lac=true）

---

## Step5：可信映射（LAC + Cell + operator + tech）+ “异常记录”

你现在强调：先跑通“关系”，不做 share/top1 强度指标；但要把“一个 cell 多个 lac”的异常记录出来给你研究。

从整体流程文档看，CellID 统计库本来就是按 (network_group, tech, lac, cellid) 聚合，并包含 record_count、valid_gps_count、gps_cluster_center/radius。
为了后续补数阶段能用（阶段二需要 Master_CellID_Lib），我建议 Step5 至少把 **record_count + valid_gps_count + 基础中心点**保留下来；聚类算法先用“简化版（中位数中心 + 半径统计）”即可，后续全国数据再升级。

**输入**

* `d_step2_gps_compliance_marked`（is_compliant=true）
* `d_step4_master_lac_lib`（可选：如果你要求“映射只在可信 LAC 内生成”，就 join 一下）

**输出（建议两张表）**

1. `d_step5_cellid_stats_db`（也就是你的可信映射统计底座）

   * 主键：operator_id_raw + tech_norm + lac_dec + cell_id_dec
   * 指标：

     * 总上报次数（record_count）
     * 有效GPS次数（valid_gps_count：has_gps=true 的计数，先不做漂移）
     * 首次/末次/活跃天数（first/last/active_days）
     * GPS中心（gps_center_lon/lat：对有效GPS取中位数/均值）
     * GPS半径（gps_radius：对中心距离的 P95 或 max，先跑通即可）
2. `rpt_step5_anomaly_cell_multi_lac`

   * 粒度：operator_id_raw + tech_norm + cell_id_dec
   * 指标：lac_distinct_cnt、lac_list、first_seen、last_seen、record_count
   * 规则：count(distinct lac_dec) > 1（出现就报给你）

> 你说“几乎不会出现异常”，那这个报表就是你的自动哨兵：一旦出现就能精确定位到具体 cell。

---

## Step6：反哺 L0_Lac + 与 GPS 对比报表

**目的**：用可信映射集合去过滤/重建 `Y_codex_Layer0_Lac`，再和 GPS 路做“结构对比”。

**输入**

* `public."Y_codex_Layer0_Lac"`
* `d_step5_cellid_stats_db`（可信映射集合）
* `public."Y_codex_Layer0_Gps_base"`（用于对比基线，也可用 Step2/Step1 的报表结果）

**输出**

1. `d_step6_l0_lac_filtered`：L0_Lac 过滤后版本（只保留落在映射集合内的记录）
2. `rpt_step6_gps_vs_lac_compare`：对比报表（全维度）

**核心对比指标（你说“都要、而且还要追加”，先把底盘打全）**

* 行数（row_cnt）
* 去重 cell 数（cell_cnt）
* 去重 lac 数（lac_cnt）
* 按 tech_norm、operator_id_raw、operator_group_hint 的分布对比
* （可选）parsed_from 对比：GPS 路有 parsed_from，LAC 路可能没有；但可以在报表里把 parsed_from 当作 GPS 的解释维度

---

# C. 未来 3 个“大步骤”的注释版说明（给 agent 预埋接口）

你提到的未来三步，本质上就是你整体思路里的“阶段二 + 阶段三”，文档里已经把 I/O 和关键状态打标逻辑写出来了。

下面按你说的 3 个大步骤，用“可落地表结构/关键字段”再解释一遍（agent 需要提前在 Layer_2 里把 Step5 的产物设计得能承接这些）。

---

## 大步骤 1：更严的补数/纠偏（从“抽取统计”升级为“逐条验证与回填”）

**目标**：解决你说的“抽取到的 cell_id 无值也被统计，但还是无值”的问题：进入补数阶段后，要对每条记录打状态、纠错、必要时剔除或留作观察。

文档里的阶段二定义了 4 类 case，并要求对每条记录打 status，同时在 Case B 下修正 lac。

**输入**

* 原始全量数据流（GPS 路、LAC 路、ss1、第三方……你后续会扩）
* `Master_LAC_Lib`（大步骤0的可信 LAC）
* `Master_CellID_Lib`（由 Step5 的 cellid_stats_db 进一步筛选得到）

**处理（核心字段/状态）**

* 处理状态（status）至少要支持：Verified / Corrected_LAC / New_CellID_Candidate / Unverified_Omitted
* 原始LAC（original_lac）与 修正LAC（corrected_lac）
* 数据来源（data_source：APP/SS1/第三方）
* GPS 状态（gps_status）：Verified / Drift（漂移检测后打标）

**输出**

* `Cleaned_Augmented_DB`（清洗补齐库）：只保留 status != Unverified_Omitted 的记录，并带全套标记字段。

**必须观察的报表**

* status 分布（Verified/Corrected/New/Unverified 各占比）
* 按 data_source 交叉：不同来源质量差异（这对你后面全国数据非常关键）

---

## 大步骤 2：enbid（基站库）生成 + 基站 GPS 计算

这一步就是你说的“补数完了时 enbid 的生成和 gps 计算”。文档阶段三给出了明确规则：先把 CellID 转成基站ID（bs_id / sector_id），再用 Verified GPS 聚合求基站中心点。

**输入**

* `Cleaned_Augmented_DB`（来自大步骤1）

**处理**

1. 基站ID转换（bs_id, sector_id）

   * 4G eNodeB：bs_id = floor(cellid/256), sector_id = cellid % 256
   * 5G gNodeB：规则可能更复杂，但先按你现有 cell_id 长度/tech_norm 做一个“可替换函数接口”
2. 基站中心 GPS（bs_gps_center）

   * 只用 gps_status=Verified 的点聚合（建议先中位数）

**输出**

* `Master_BS_Library`：包含 bs_id、bs_gps_center、associated_lac、cellid_count 等。

---

## 大步骤 3：利用 enbid 完成最终修正（回填 CellID 空 GPS / 修正 LAC GPS）

这一步就是你说的“最后利用 enbid 完成最终修正”，文档阶段三给出两条路径：

* 可选：用基站中心再修正 LAC 的中心 GPS（lac_gps_center_refined）
* 必选：回填 CellID 的空 GPS 或 Drift GPS，并标记 gps_source=Augmented_from_BS，产出最终主库 Final_Master_DB。

**输入**

* `Cleaned_Augmented_DB`
* `Master_BS_Library`

**输出**

* `Final_Master_DB`（最终 GPS 完整的主库）
* GPS补齐报告：gps_source 分布（原始 Verified vs Augmented_from_BS）

---

