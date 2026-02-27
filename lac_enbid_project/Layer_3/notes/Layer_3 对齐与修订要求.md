# Layer_3 对齐与修订要求v1（2025-12-18）

> 你的任务：基于 Layer_2 已交付资产，按本对齐文档修订 Layer_3 计划，并输出可执行的 RUNBOOK + SQL（含冒烟与验收），支持“人工提交后台执行大 SQL、你负责 MCP 自检与审计推进”的协作模式。

---

## 0) 背景与目标（必须写进《任务理解文档》）

* Layer_3 目标：把 Layer_2 的“严格过滤 + 可信库 + 反哺明细库”升级为**以基站（ENBID/gNB）为索引的可画像数据集**，并产生：

  1. **基站主库**（站级画像 + 共建标记 + 基站中心点/GPS质量）
  2. **按基站回填/纠偏后的明细库**（保留回溯字段与来源标记）
  3. **对比报表**（修正收益、风险规模、碰撞疑似规模）
  4. **信号字段补齐摸底**（本轮做“能补多少/补不齐多少”的统计 + 简单补齐，不追求最优策略）

> 重要：本轮 Layer_3 允许“简单鲁棒方案先跑通”，但必须把**可升级点**（如样本≥30后更严策略）写进文档，且不破坏口径。

---

## 1) 输入依赖冻结（Layer_3 开始前必须确认/写死）

Layer_3 输入依赖来自 Layer_2（请在文档中列清楚表名与用途）：

* Step02：`Y_codex_Layer2_Step02_Gps_Compliance_Marked`
  用途：提供 `gps_status`（Verified/Drift/Missing 或等价字段）与“合法有效 GPS 点”样本。
* Step04：`Y_codex_Layer2_Step04_Master_Lac_Lib`
  用途：可信 LAC 白名单（用于物理分桶、碰撞辅助判断等）。
* Step05：`Y_codex_Layer2_Step05_CellId_Stats_DB` + `Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac`
  用途：映射证据底座 + 异常哨兵（碰撞/错归并风险信号）。
* Step06：`Y_codex_Layer2_Step06_L0_Lac_Filtered`（必须是 TABLE）
  用途：可信明细库（LAC 路反哺后明细）。

执行约束（沿用 Layer_2 协作规范）：

* 列名保持英文/ASCII；**必须用 `COMMENT ON TABLE/COLUMN` 写“中文标签 + English description”**（满足“中文友好”要求）。
* 每步：先冒烟（限定 `report_date` 或 `operator_id_raw`）再全量。
* 你负责：冒烟 SQL + MCP 自检 + RUNLOG 记录；人类负责：后台执行大 SQL。

---

## 2) 本次讨论的决策定稿（A~F，必须写死，不要再发散）

### A) bs_id 生成规则（选项 1）

* **优先使用 Layer_0 已解析字段 `bs_id`**（如果存在且覆盖足够）。
* 若缺失：才按 `tech_norm` 回退派生

  * 4G：`bs_id = floor(cell_id_dec / 256)`
  * 5G：`bs_id = floor(cell_id_dec / 4096)`
* 文档要求：规则必须“可替换/可版本化”。

### B) 共建标记 + 物理分桶键（中文友好字段名）

* 站级共建统计保留两种视角：

  1. 运营商视角：`(operator_id_raw, tech_norm, bs_id)`
  2. 物理站视角：引入 `lac_dec_final` 防止跨 LAC 错配后误判共建
* **物理分桶键字段名：用中文友好（pinyin）**

  * 字段名：`wuli_fentong_bs_key`
  * COMMENT（必须）：`物理分桶基站键 / Physical BS bucket key`
  * 建议取值：`tech_norm|bs_id|lac_dec_final`（字符串拼接）

> 如你坚持纯英文列名也可，但本轮按讨论定稿：列名用 `wuli_fentong_bs_key`，并通过 COMMENT 保证可读性与一致性。

### C) 基站 GPS 可用性分级（先统计评估，再用于回填决策）

仅统计“有效合法 GPS 值”，定义为：

* `gps_status=Verified`（或等价合规标记）
* 经纬度合法：`lon between [-180,180]` 且 `lat between [-90,90]`
* 且不为 `(0,0)`

分级规则（按“基站下有效 GPS 的来源数量”分）：

* `gps_valid_cell_cnt = 0` → **不可用（Unusable）**
* `gps_valid_cell_cnt = 1` → **风险（Risk）**（必须标记）
* `gps_valid_cell_cnt > 1` → **可用（Usable）**

要求：

* Step30 必须输出一张统计（各等级数量、占比、按运营商/tech 分组）。
* 风险类必须可定位：能查到对应 bs_id / cell 列表。

### D) 基站中心点与离散度（本轮用“简单鲁棒”，未来可升级）

本轮方案要求：

* 小样本先跑通：采用**“找最大偏移点 → 剔除 1 个 → 重算”**的鲁棒策略。
* 若离散度明显过大：认为可能**碰撞/错归并**，必须 `is_collision_suspect=1` 标记（而不是继续硬算）。

未来升级点必须写在文档里（先不阻断）：

* 当 `gps_valid_cell_cnt >= 30` 时，可启用更严格/更稳定策略（阈值与算法未来评估）。

### E) Step31 回填/纠偏字段中文友好（含义必须中文或中文备注）

* 必须保留来源字段：`gps_source`（Original / Augmented_from_BS 等）
* 必须保留状态字段：`gps_status`（Verified/Drift/Missing）
* 所有新增枚举字段必须有中文解释（COMMENT + 文档字典），必要时在报表里加 `*_cn` 展示列（可选但推荐）。

### F) 信号补齐本轮就做（摸底版）

* 本轮目标：**统计可补齐 vs 不可补齐**，并做“简单补齐”输出，不追求最优策略。
* 必须先做：信号字段盘点（确认 Layer_0 / Layer_2 明细里是否存在信号列；若不存在，要在结果里体现“无法补齐=100%”并写清原因与下一步需要扩展 L0 解析）。

---

## 3) Layer_3 输出对象（必须按此生成，表名统一 `public."Y_codex_Layer3_StepXX_*"`）

### Step30：`public."Y_codex_Layer3_Step30_Master_BS_Library"`（TABLE）

定位：基站主库（站级画像、共建标记、中心点、离散度、风险标记）

至少包含字段（列名可调整，但含义不可缺）：

* 主键与分桶：

  * `tech_norm`, `bs_id`
  * `wuli_fentong_bs_key`（见 B）
* 共建：

  * `is_multi_operator_shared`（0/1）
  * `shared_operator_list`（如 `46000,46001`）
  * `shared_operator_cnt`
* GPS 有效性：

  * `gps_valid_cell_cnt`（distinct cell 计数）
  * `gps_valid_point_cnt`（点行数）
  * `gps_valid_level`（Unusable/Risk/Usable）+ COMMENT 中文
* 中心点与离散度（当 Risk/Usable 才允许有中心点；Unusable 置空）：

  * `bs_center_lon`, `bs_center_lat`
  * `gps_p50_dist_m`, `gps_p90_dist_m`, `gps_max_dist_m`
  * `outlier_removed_cnt`（本轮最多 0 或 1）
* 风险/碰撞：

  * `is_collision_suspect`（0/1）
  * （可选）`collision_reason`（短文本，建议也写 COMMENT）
* 覆盖时间画像：

  * `first_seen_ts`, `last_seen_ts`, `active_days`

### Step31：`public."Y_codex_Layer3_Step31_Cell_Gps_Fixed"`（TABLE）

定位：按基站中心点回填/纠偏后的明细库（保留回溯字段）

强制要求：

* 保留回溯：`src_seq_id` / `src_record_id`（或等价可追溯字段）
* 必须包含：

  * 原始经纬度（如 `lon_raw/lat_raw`）与最终经纬度（如 `lon_final/lat_final`）
  * `gps_status`（Verified/Drift/Missing）
  * `gps_source`（Original_Verified / Augmented_from_BS / Not_Filled…）
  * 风险标记：来自 Risk 基站回填要有显式标记（例如 `is_from_risk_bs=1`）

回填原则（写进文档，并在 SQL 实现）：

* `gps_status=Verified`：不覆盖原值（`gps_source=Original_Verified`）
* `gps_status in (Missing,Drift)`：

  * 若 Step30 中该基站 `gps_valid_level=Usable`：允许回填中心点
  * 若 `gps_valid_level=Risk`：允许回填，但必须 `is_from_risk_bs=1`
  * 若 `Unusable` 或中心点为空：不回填（`gps_source=Not_Filled`）

### Step32：`public."Y_codex_Layer3_Step32_Compare"`（TABLE）

定位：修正前后对比报表（收益、风险规模、碰撞疑似）

最少包含指标：

* GPS 修正收益：

  * Missing→Filled 数量
  * Drift→Corrected 数量
  * has_gps 提升（前/后）
* 风险规模：

  * Risk 基站数、Collision_suspect 基站数
* 分组：按 `operator_id_raw`、`tech_norm`、（可选）`report_date`

### Step33：`public."Y_codex_Layer3_Step33_Signal_Fill_Simple"`（TABLE）

定位：信号字段“简单补齐”明细输出（摸底版）

实现要求：

1. 先做“信号字段盘点”：

   * 明确本项目本轮要摸底的信号字段清单（如 RSRP/RSRQ/SINR 等，具体以你在库里实际存在的字段为准）
2. 简单补齐策略（推荐聚合补齐，轻量且可统计）：

   * 先按 cell 聚合（如 avg/median）得到 `cell_signal_profile`
   * cell 无法补齐则回退到 bs 聚合得到 `bs_signal_profile`
   * 写入 `signal_fill_source`：`cell_agg / bs_agg / none`
3. 本轮不追求最优，只保证可跑通、可统计。

### Step34：`public."Y_codex_Layer3_Step34_Signal_Compare"`（TABLE）

定位：信号补齐摸底报表

* 缺失量（补齐前/后）
* 可补齐 vs 不可补齐
* 按 `signal_fill_source` 分布

---

## 4) Step30 核心算法要求（必须在《任务理解》写清楚）

### 4.1 输入点集

* 仅使用 Verified + 合法经纬度 + 非(0,0) 点

### 4.2 “简单鲁棒中心点 v1”（按 `wuli_fentong_bs_key` 聚合）

建议实现（SQL 可落地）：

1. 先把点按 `cell_id_dec` 聚合成 cell 代表点（推荐中位数 lon/lat）
2. 得到 N 个 cell 点：

   * N=0：Unusable，中心点为空
   * N=1：Risk，中心点=该点，打风险标记
   * N>=2：中心点=cell 点 lon/lat 中位数
3. 当 N>=3：

   * 计算每个 cell 点到中心点距离（米）
   * 若 `gps_max_dist_m` 超过阈值（阈值写成参数/配置，不要散落在 SQL 里）：

     * 剔除 1 个最大偏移点（仅 1 个），重算中心点与离散度
     * `outlier_removed_cnt=1`
4. 碰撞疑似标记：

   * 若重算后 `gps_p90_dist_m` 仍明显过大，或关联到 Step05 哨兵风险很高 → `is_collision_suspect=1`

> 阈值要求：先给默认值，但必须声明“可调参数、未来评估”；并在 Compare 里输出分布，方便后续把阈值调准。
> （不要把“>=30 才计算”写成强阻断，本轮先产出 `gps_valid_cell_cnt` 与离散度，让后续评估。）

---

## 5) 执行与协作流程（RUNBOOK 必须照此写）

### 5.1 交付文件（你必须输出）

至少两份文档（必须）：

1. `Layer_3_任务理解与口径对齐_v1.md`
2. `Layer_3_执行计划_RUNBOOK_v1.md`

强烈建议（可选但推荐）：
3) `Layer_3_Data_Dictionary_v1.md`（把新增字段/枚举逐条写中文解释与示例）

### 5.2 SQL 文件交付（必须可冒烟、可全量）

* 每个 Step 至少提供：

  * 冒烟 SQL（限制 `report_date` 或 `operator_id_raw`，保证 3~10 分钟内可跑出结果）
  * 全量 SQL（供人工后台执行）
* 建议目录结构：

  * `Layer_3/sql/30_step30_master_bs_library.sql`
  * `Layer_3/sql/31_step31_cell_gps_fixed.sql`
  * `Layer_3/sql/32_step32_compare.sql`
  * `Layer_3/sql/33_step33_signal_fill_simple.sql`
  * `Layer_3/sql/34_step34_signal_compare.sql`
  * `Layer_3/sql/99_layer3_comments.sql`（集中写 COMMENT）

### 5.3 每步验收（你必须提供 Summary Queries 清单）

每步至少包含：

* `count(*)`
* 主键重复检查（Step30 的 `(tech_norm, bs_id, wuli_fentong_bs_key)` 或你定义的主键必须唯一）
* 关键分布（gps_valid_level 分布、risk/collision 数量、回填来源分布、signal_fill_source 分布）
* 对比步（Step32/34）必须能直接回答：提升多少、风险多少、不可用多少

### 5.4 审计与推进（你负责）

* 人类执行全量 SQL 后：

  * 你用 MCP 跑验收查询
  * 更新 `RUNLOG_YYYYMMDD.md`：每步至少记录 5 条 Summary Query 的结果 + 异常点样本（TopN）
* 注意：避免 `DO $$ ... $$` 这类容易被执行器按 `;` 拆坏的语句；尽量用纯 SQL。

---

## 6) 对上一轮（Layer_2）需要补的“文字修订”（你要在文档里顺带说明）

* Layer_3 消费 Layer_2 的哪些表、哪些字段（写清依赖与字段口径，避免后续“字段不存在/含义不一致”）
* 明确：列名英文/ASCII + COMMENT 双语，是跨层统一规范（满足中文友好诉求）
* 若 Step02 当前没有显式 `gps_status`（Verified/Drift/Missing）或等价字段：需要在 Layer_3 文档里声明“依赖字段要求”，并提供兜底映射方案（如果字段名不同）。

---

## 7) 你必须在文档里留下的“未决项/后续评估项”

* `gps_valid_cell_cnt >= 30` 的策略升级：只作为未来评估，不作为本轮阻断
* 离散度阈值（剔除阈值、collision 阈值）：默认值先给出，后续通过分布评估迭代
* 信号字段来源：若 L0/L2 无信号字段，本轮输出“无法补齐”并列出下一步需要扩展的 L0 解析字段清单

---

**交付完成标准（你自检后再交付给人类评审）：**

* 两份文档齐全（任务理解 + RUNBOOK）
* Step30~34 的 SQL 都能冒烟跑通并产出对象
* Compare 表能回答：GPS 修正收益、风险规模、信号补齐摸底结果
* 所有新增字段都有 COMMENT（中文标签 + English description）
