# Layer_2 效果评估报告（北京明细 20251201_20251207）

生成时间：2025-12-16  
范围：Step00~Step06（已按最新 Step02/Step04 规则重跑）  
核心目标：构建“依赖 运营商+制式+LAC+Cell 的合规库”，并用合规库构建映射，反哺/补充 LAC 路数据。

> 说明（非常重要）：本报告的“行数（row_cnt）”以 Step06 产出的对比表 `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"` 为准。  
> 其中 `cell_cnt/lac_cnt/device_cnt` 是在 `(operator_id_raw, tech_norm, dataset)` 维度内做的去重计数，**再做 SUM 时会产生重复计数**，因此本报告把它们作为“结构参考”，不把 SUM 后的去重值当作全局真实去重。

---

## 1) 你说“没看到对比数据”的定位

Step06 的对比表对象名是（注意双引号）：

- `public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`（TABLE）

可以用下面的 SQL 直接看：

```sql
select * from public."Y_codex_Layer2_Step06_GpsVsLac_Compare" order by dataset, row_cnt desc limit 50;
```

---

## 2) 四路对比总览（GPS_RAW / GPS_COMPLIANT / LAC_RAW / LAC_FILTERED）

数据来自：`public."Y_codex_Layer2_Step06_GpsVsLac_Compare"`

| dataset | row_cnt | row_cnt 说明 |
|---|---:|---|
| GPS_RAW | 132,688,948 | Step00 GPS 路全量（含非4/5G、含不在 5PLMN、含字段异常） |
| GPS_COMPLIANT | 30,549,420 | Step02 合规子集（4G/5G + LAC/Cell 合规 + 新增范围/位数规则） |
| LAC_RAW | 118,519,386 | Step00 LAC 路全量（含非4/5G、含不在 5PLMN、含字段异常） |
| LAC_FILTERED | 21,647,155 | Step06 过滤后的 LAC 路（命中 Step05 映射键：operator+tech+lac+cell） |

总体比率：

- GPS 合规率（`GPS_COMPLIANT / GPS_RAW`）：**23.0233%**
- LAC 反哺覆盖率（`LAC_FILTERED / LAC_RAW`）：**18.2647%**

直观解读：

- GPS 路：约 23% 的行进入“严格合规库”；这部分是后续 Step03~05 的唯一输入。
- LAC 路：约 18% 的行能通过 Step05 映射键过滤，进入“可反哺/可对齐”的 LAC 子集（用于补充 LAC 路字段或做对比分析）。

---

## 3) 按运营商组（CMCC_FAMILY/CUCC/CTCC）× 制式（4G/5G）的效果

口径：

- `CMCC_FAMILY`：`46000/46015/46020`
- `CUCC`：`46001`
- `CTCC`：`46011`
- `OTHER`：不在 5PLMN（因此不可能合规）

### 3.1 GPS 合规率（同组同制式）

| op_group | tech | GPS_RAW | GPS_COMPLIANT | 合规率 |
|---|---:|---:|---:|---:|
| CMCC_FAMILY | 4G | 31,383,766 | 4,538,256 | 14.4605% |
| CMCC_FAMILY | 5G | 17,419,775 | 12,526,608 | 71.9103% |
| CUCC | 4G | 6,882,402 | 2,685,714 | 39.0229% |
| CUCC | 5G | 8,879,119 | 6,583,026 | 74.1405% |
| CTCC | 4G | 6,918,517 | 1,501,333 | 21.7002% |
| CTCC | 5G | 3,985,316 | 2,714,483 | 68.1121% |

补充观察：

- 2G/3G 与 “其他” 在 Step02 里全部被判为不合规（符合设计）。
- `OTHER`（非 5PLMN）在 Step02 中全不合规（符合设计）；这类数据在 RAW 中占比不低，会拉低“全体 raw 的合规率”，但这是预期现象。

### 3.2 LAC 反哺覆盖率（同组同制式）

| op_group | tech | LAC_RAW | LAC_FILTERED | 覆盖率 |
|---|---:|---:|---:|---:|
| CMCC_FAMILY | 4G | 10,842,008 | 3,529,687 | 32.5557% |
| CMCC_FAMILY | 5G | 16,017,745 | 10,173,948 | 63.5167% |
| CUCC | 4G | 6,300,196 | 1,138,478 | 18.0705% |
| CUCC | 5G | 8,509,606 | 4,235,331 | 49.7712% |
| CTCC | 4G | 3,667,779 | 602,628 | 16.4303% |
| CTCC | 5G | 3,791,347 | 1,967,083 | 51.8835% |

直观解读：

- 5G 的映射覆盖显著高于 4G（各运营商都是），说明“合规库→映射键→反哺”链路在 5G 上更容易闭环。
- 4G 覆盖偏低，通常对应 Step02 里大量 `LAC_INVALID / CELLID_*` 导致 GPS 合规集较小、进而映射键覆盖不足。

---

## 4) Step04（可信 LAC 白名单）的筛选效果（新策略）

Step04 当前策略（已落地到 `sql/04_step4_master_lac_lib.sql`）：

- 必须：`active_days = 7`
- 默认门槛：`distinct_device_count >= 5` 且 `record_count >= ceil(P80(record_count))`
- 46015/46020：仅要求 `active_days = 7`（免门槛）
- CUCC/CTCC 的 5G：设备门槛按 `/2`，落地为 `distinct_device_count >= 3`，仍需满足 `record_count >= P80`

### 4.1 本窗口计算得到的 P80 上报门槛（用于落地）

| op_group | tech | p80_reports_min（ceil后） |
|---|---:|---:|
| CMCC_FAMILY | 4G | 26,700 |
| CMCC_FAMILY | 5G | 44,805 |
| CUCC | 4G | 8,993 |
| CUCC | 5G | 21,260 |
| CTCC | 4G | 5,027 |
| CTCC | 5G | 8,565 |

### 4.2 `active_days=7` 候选集中，Step04 留存与“承载”占比

对比对象：

- 候选全集：`public."Y_codex_Layer2_Step03_Lac_Stats_DB" WHERE active_days=7`
- 可信白名单：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`

| op_group | tech | active7_LAC数 | trusted_LAC数 | trusted占比 | active7上报量 | trusted上报量 | 上报覆盖 | active7设备数 | trusted设备数 | 设备覆盖 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CMCC_FAMILY | 4G | 402 | 224 | 55.72% | 4,528,487 | 3,511,682 | 77.5465% | 550,937 | 402,855 | 73.1218% |
| CMCC_FAMILY | 5G | 528 | 257 | 48.67% | 12,513,226 | 11,458,937 | 91.5746% | 1,111,665 | 963,237 | 86.6481% |
| CUCC | 4G | 502 | 101 | 20.12% | 2,679,624 | 1,332,652 | 49.7328% | 410,268 | 185,028 | 45.0993% |
| CUCC | 5G | 589 | 118 | 20.03% | 6,570,458 | 4,766,282 | 72.5411% | 717,096 | 471,951 | 65.8142% |
| CTCC | 4G | 472 | 95 | 20.13% | 1,496,920 | 742,018 | 49.5696% | 244,891 | 107,832 | 44.0327% |
| CTCC | 5G | 440 | 88 | 20.00% | 2,707,674 | 2,162,060 | 79.8493% | 326,559 | 243,716 | 74.6315% |

解读要点：

- 该策略对 CUCC/CTCC 的 4G 过滤力度很大（只保留约 20% 的 LAC），但其“上报覆盖”约 50%，属于“用少量高频 LAC 承载主要流量”的典型形态。
- 对 CMCC_FAMILY 5G：LAC 数保留约 49%，但上报覆盖 91.6%，符合“去稀疏尾巴、保主干”的意图。

---

## 5) Step05（映射底座）与异常哨兵

映射底座（主键粒度 `operator_id_raw+tech_norm+lac_dec+cell_id_dec`）：

- `public."Y_codex_Layer2_Step05_CellId_Stats_DB"`：**503,358 行（映射键数）**

异常哨兵（同一 operator+tech+cell 对应多个 lac）：

- `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`：**79 行**
- `lac_distinct_cnt` 最大值：**4**
- 按制式分布：
  - 4G：10 个异常 cell（`max lac_distinct_cnt = 2`）
  - 5G：69 个异常 cell（`max lac_distinct_cnt = 4`）

解读要点：

- 当前 Step04 策略下，映射键规模约 50 万，属于可控范围（对 Step06 join 友好）。
- 异常 cell 数很少（79），说明“同 cell 多 LAC”的结构性问题在当前白名单下已较收敛；后续若要进一步提高可信度，可把 anomaly 作为黑名单或降权信号（但本轮先不做复杂口径）。

---

## 6) Step02 不合规原因 Top（用于解释合规率）

数据来自：`public."Y_codex_Layer2_Step02_Compliance_Diff" WHERE report_section='TOP_REASON'`

Top 现象（截取前若干）：

- `LAC_INVALID;CELLID_NONPOSITIVE`：31,804,629
- `OPERATOR_OUT_OF_SCOPE;LAC_INVALID`：24,517,351
- `OPERATOR_OUT_OF_SCOPE;LAC_INVALID;CELLID_NULL_OR_NONNUMERIC`：13,574,606
- `LAC_INVALID;CELLID_NULL_OR_NONNUMERIC`：12,994,290
- `OPERATOR_OUT_OF_SCOPE;TECH_NOT_4G_5G;LAC_INVALID;CELLID_NULL_OR_NONNUMERIC`：6,122,528
- `OPERATOR_OUT_OF_SCOPE`：5,123,739

解读要点：

- “不在 5PLMN（OPERATOR_OUT_OF_SCOPE）”贡献了很大的 raw→compliant 收敛量，这是预期（范围裁剪）。
- “LAC_INVALID / CELLID_*”是 4G 合规率偏低的主要原因（和你之前观察的 LAC 位数/Cell 异常相一致）。

---

## 7) 结论：合规库与补充链路的“效果”

你要的核心效果，可以用两句话概括：

1) **合规库规模（GPS 合规集）**：`30,549,420` 行（占 GPS_RAW 的 23.02%），并且在 5G 上合规率显著更高（约 68%~74%），在 4G 上合规率明显偏低（约 14%~39%），不合规主要来自 `LAC_INVALID / CELLID_*`。  
2) **反哺覆盖（LAC_FILTERED）**：`21,647,155` 行（占 LAC_RAW 的 18.26%）能命中映射键，5G 覆盖显著更好（约 49%~64%），说明“合规→映射→补充”在 5G 上已经具备可用闭环。

下一步如果要“让 4G 的补充效果更强”，通常要回到两处调参：

- Step02：减少 4G 的 `LAC_INVALID / CELLID_*`（前提是不破坏口径）
- Step04：把阈值从“P80 强筛”做成可扫描策略（报告 `Step04_修订参考_ActiveDays7_画像_20251216.md` 已给出重评方案），以便在“保真”与“覆盖”之间选一个更合适的点。

