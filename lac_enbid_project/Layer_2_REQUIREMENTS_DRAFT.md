# Layer_2 需求梳理（北京明细 20251201_20251207）

本文用于在开始构建 `Layer_2` 之前，确认目标、输入表、字段口径、输出物与关键疑问点；待你确认后，我将创建 `lac_enbid_project/Layer_2/` 目录结构与对应 SQL/文档任务清单。

## 1. 背景与输入数据

### 1.1 Layer_0 已就绪的两张服务器表

当前服务器端 Layer_0 最终表为（字段结构一致，均 34 列，含 `seq_id`）：

- `public."Y_codex_Layer0_Gps_base"`（你口中 “`Y_codex_Layer0_GPS` 原始表” 对应这张）
- `public."Y_codex_Layer0_Lac"`

其来源原表分别为：

- `public."网优项目_gps定位北京明细数据_20251201_20251207"`
- `public."网优项目_lac定位北京明细数据_20251201_20251207"`

### 1.2 Layer_0 关键字段（用于 Layer_2）

两张 Layer_0 表字段相同（以下为字段名与含义，按当前表中实际列名）：

- 标识/排序：`seq_id`（bigint）、`记录id`（varchar）
- 时间：
  - `ts_std`（timestamp without time zone）：报文墙钟标准时间（由原表 `ts` 解析）
  - `cell_ts_std`（timestamptz）：基站侧时间（对 `cell_infos` 的 `timeStamp`/对 `ss1` 的 unix 秒做范围保护后派生）
  - `cell_ts`（text）：基站时间原始值（raw）
- 制式与运营商：`tech`（text，期望 `4G/5G` 为主）、`运营商id`（text）
- 小区与 LAC：
  - `cell_id`（text 原始）、`cell_id_dec`（bigint）、`cell_id_hex`（text）
  - `原始lac`（text 原始）、`lac_dec`（bigint）、`lac_hex`（text）
  - `bs_id`（bigint）、`sector_id`（bigint）
- 来源与匹配：`parsed_from`（text：`cell_infos` / `ss1`）、`match_status`（text：ss1 unmatched 标记）、`is_connected`（boolean）
- 设备与定位：`did`、`oaid`、`ip`、`sdk_ver`、`brand`、`model`、`gps_*`、`lon/lat`

### 1.3 Layer_1 合规规则（待复用）

你希望在 Layer_2 的第二步“利用 Layer_1 的合规要求”进行标记与过滤。当前仓库中已有规则文档（后续我会按文档落地为 SQL 视图/表）：

- `lac_enbid_project/Layer_1/Lac/Lac_Filter_Rules_v1.md`
- `lac_enbid_project/Layer_1/Cell/Cell_Filter_Rules_v1.md`

## 2. 我对你需求的完整复述（按标准流程）

你希望在 `Layer_2` 建立一套从 “原始 L0（GPS）→ 合规 → 有效 LAC 汇总 → 可信 LAC → 可信映射（LAC+Cell+运营商+制式）→ 反哺 L0（LAC）并与 GPS 对比” 的标准流程，分为以下阶段：

### Step 1：Layer_2 基础统计（以 `Y_codex_Layer0_GPS` 为输入）

输入：`public."Y_codex_Layer0_Gps_base"`

产出：一组统计表/视图（或一份固定 SQL 的统计结果），核心指标包括：

- `cell_id`（或 `cell_id_dec`）的数量（你需要明确口径：去重后数量 vs 行数）
- 按 `tech`（4G/5G）与 `运营商id` 维度的数量、占比
- `parsed_from='cell_infos'` 与 `parsed_from='ss1'` 的数量、占比（其中 `ss1` 理论上仅包含 unmatched）

### Step 2：合规标记与合规前后对比统计（复用 Layer_1 规则）

输入：Step 1 同一张 `public."Y_codex_Layer0_Gps_base"`

处理：基于 Layer_1 合规规则，为每行/每个实体打标（例如 `is_compliant` + `non_compliant_reason`），并基于合规过滤得到“有效数据集”。

产出：

- 合规标记后的数据集（视图/表）
- 合规过滤前后变化统计：保留/剔除行数、剔除占比；以及按 `tech/运营商id/parsed_from` 的结构性变化

### Step 3：构建“有效 LAC 库”的去重维度汇总表（仅取有效数据）

输入：Step 2 的“合规有效数据集”（来自 GPS L0）

目标：抽取有效数据中的 LAC，形成 LAC 维度的汇总表，并做你提到的统计：

- 上报时间（通常需要 `first_seen` / `last_seen`）
- 上报次数（`report_cnt`）
- 累计上报天数（`active_days`，通常为 `count(distinct date)`）
- 设备与上报量占比（例如 `device_cnt`、`device_share`、`report_share`）

说明：该汇总表字段需要你我进一步确认（你也提到这部分可能需要多轮交互）。

### Step 4：基于有效 LAC 汇总表，构建“可信 LAC 表”（二次过滤）

输入：Step 3 的 LAC 汇总表

处理：用一套“可信”过滤规则（阈值/覆盖度/稳定性等）筛出可信 LAC 集合。

产出：可信 LAC 维表（或集合表/视图）。

### Step 5：构建可信映射表（`LAC + Cell_id + 运营商id + 制式`）

输入：可信 LAC 表 + Step 2 的有效数据（或其它你指定的数据集）

目标：得到一张你认为“可信”的映射表，用于后续反哺校验；映射维度明确包含：

- `lac_dec`
- `cell_id_dec`
- `运营商id`
- `tech`（4G/5G）

（通常还会需要：映射强度指标，如支持该映射的上报次数/设备数/天数等，以支撑“可信”。）

### Step 6：用可信映射反哺 `Y_codex_Layer0_Lac`，并与 GPS 结果对比

输入：

- Step 5 的可信映射表
- `public."Y_codex_Layer0_Lac"`
- `public."Y_codex_Layer0_Gps_base"`（用于对比）

处理：用可信映射从 `Y_codex_Layer0_Lac` 重新筛出/重建一份数据集（例如只保留落在可信映射集合内的记录），然后对比 GPS 与 LAC 两路数据量/结构变化（你关心“数据量变化”与结构差异）。

产出：

- `Y_codex_Layer0_Lac` 的“可信重建/过滤后”版本（视图/表）
- 与 GPS 的对比统计结果（行数、去重 cell/lac 数、按运营商/制式分布等）

## 3. 我需要你确认/补充的关键疑问（决定 SQL 落地方式）

1. 你说的 “`Y_codex_Layer0_GPS` 原始表” 是否统一指 `public."Y_codex_Layer0_Gps_base"`（目前服务器真实表名）？后续 Layer_2 文档/SQL 我按哪个命名写死？
2. Step 1 中 “有多少 cell_id” 的口径是：
   - `count(distinct cell_id_dec)`（推荐，且需排除 `cell_id_dec is null`）？
   - 还是 `count(distinct cell_id)`（raw 文本，可能脏）？
   - 还是需要同时给 “行数/去重数” 两套？
3. `tech` 维度统计是否只看 `4G/5G`，还是把 `NULL/2G/3G` 也作为单独类别输出（目前非 4G/5G 的比例不低）？
4. Step 1/2/3 统计用哪个时间作为 “上报时间/天数” 的口径：
   - `ts_std`（报文墙钟，推荐做天数/覆盖）？
   - `cell_ts_std`（基站侧时间，可能存在缺失/异常但更贴近信号）？
5. Step 2 合规规则的“实体粒度”是按 **行级**（每条基站明细记录）打标，还是按 **小区级/基站级/LAC级** 汇总后回写打标？
6. Step 3 “有效 LAC 汇总表” 的主键/粒度你期望是：
   - `lac_dec` 单独一列（不区分运营商/制式）；
   - 还是 `运营商id + tech + lac_dec`（更符合你提到“和运营商以及制式相关”）；
   - 或者 `运营商id + lac_dec`（不分 4G/5G）？
7. Step 4 “可信 LAC” 的过滤准则：你期望先用哪些硬阈值（例如 `active_days >= ?`、`device_cnt >= ?`、`report_cnt >= ?`、`report_share >= ?`）？还是先把候选指标都算齐，再由你选阈值？
8. Step 6 “对比数据量变化” 的对比口径：
   - 对比 “过滤后行数/去重 cell 数/去重 lac 数”；
   - 以及是否需要在相同维度（`运营商id + tech`）下对比？

## 4. 你确认后我会创建的 Layer_2 交付物（预告）

在你确认上述口径后，我会在 `lac_enbid_project/Layer_2/` 下创建：

- `README.md`：流程说明 + 表清单 + 运行顺序
- `00_inputs.md`：输入表/字段说明（含本文件确认内容）
- `01_base_stats.sql`：Step 1 统计 SQL
- `02_compliance_mark.sql`：Step 2 合规标记与对比统计 SQL
- `03_effective_lac_rollup.sql`：Step 3 LAC 汇总表构建 SQL
- `04_trusted_lac.sql`：Step 4 可信 LAC 过滤 SQL
- `05_trusted_mapping.sql`：Step 5 可信映射构建 SQL
- `06_apply_to_l0_lac_and_compare.sql`：Step 6 反哺与对比 SQL

