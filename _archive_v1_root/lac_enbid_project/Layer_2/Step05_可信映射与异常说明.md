# Step05 可信映射与异常说明（Trusted Mapping + Anomalies）

## 1. 一句话摘要（TL;DR）

在 **可信 LAC（Step04）** 白名单内，基于 **合规明细（Step02）** 构建映射统计底座：`运营商id_细粒度（operator_id_raw） + 制式_标准化（tech_norm） + LAC十进制（lac_dec） + Cell十进制（cell_id_dec）`，并计算 `总上报次数（record_count）/有效GPS次数（valid_gps_count）/活跃天数（active_days）/first_seen/last_seen`；同时必须产出异常监测清单 `Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac`（同一 cell 对应多个 LAC）。

---

## 2. 输入（Input）

- 输入对象：
  - `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`（只取 `is_compliant=true`）
  - `public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（可信 LAC 白名单）
- 输入依赖：Step02 + Step04
- 输入关键字段（中文（English））：
  - 运营商id_细粒度（operator_id_raw）
  - 运营商组_提示（operator_group_hint）
  - 制式_标准化（tech_norm）
  - LAC十进制（lac_dec）
  - Cell十进制（cell_id_dec）
  - 设备ID（device_id）
  - 上报日期（report_date）
  - 报文时间（ts_std）
  - 是否有gps（has_gps）
  - 经纬度（lon/lat）

---

## 3. 输出（Output）

### 3.1 可信映射统计底座

-- 输出对象：`public."Y_codex_Layer2_Step05_CellId_Stats_DB"`（TABLE）
- 主键粒度：`operator_id_raw + tech_norm + lac_dec + cell_id_dec`
- 输出关键字段（中文（English））：
  - 统计字段（Stats，必须实现）：
    - 总上报次数（record_count）
    - 有效GPS次数（valid_gps_count）
    - 活跃天数（active_days）
    - 首次出现时间/日期（first_seen_ts/first_seen_date）
    - 最后出现时间/日期（last_seen_ts/last_seen_date）
    - 关联设备数（distinct_device_count）
  - 派生字段（Derived，当前版为简化）：
    - GPS中心经度/纬度（gps_center_lon/gps_center_lat）：对 `has_gps=true` 的点做均值（后续可升级为中位数/聚类）

> 本轮明确不做 share/top1 等“映射强度指标”，但上述指标必须产出并可解释。

### 3.2 异常监测清单：同一 Cell 多个 LAC

-- 输出对象：`public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"`（VIEW）
- 主键粒度：`operator_id_raw + tech_norm + cell_id_dec`
- 触发规则：`count(distinct lac_dec) > 1`
- 输出关键字段（中文（English））：
  - 关联LAC去重数（lac_distinct_cnt）
  - LAC列表（lac_list）
  - 总上报次数（record_count）
  - 首次/末次时间（first_seen_ts/last_seen_ts）

---

## 4. 本步骤“核心指标”解释（Human-readable）

### 4.1 总上报次数（record_count）

- 口径：该映射主键组合下的记录行数（仅合规 + 仅可信 LAC）。
- 为什么要看：衡量映射是否有足够样本；也能发现异常刷量组合。
- 正常情况下：长尾分布；极少数组合高频，多数组合低频。

### 4.2 有效GPS次数（valid_gps_count）

- 口径：`has_gps=true` 的计数。
- 为什么要看：后续阶段二/三需要 GPS 来做纠偏与基站中心点；没有 GPS 的映射只能做“关系候选”，难以做空间校验。
- 正常情况下：`valid_gps_count <= record_count`；很多组合可能为 0，但不应全部为 0。

### 4.3 活跃天数（active_days）

- 口径：`count(distinct report_date)`。
- 为什么要看：比 `record_count` 更能刻画“是否稳定出现”；也为未来可信策略升级预留。
- 正常情况下：在 7 天窗口内 `<=7`；高活跃映射通常更可信。

### 4.4 异常监测清单（Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac）

- 口径：同一 `operator_id_raw+tech_norm+cell_id_dec` 下出现多个 `lac_dec`。
- 为什么要看：你明确要求输出该报表；它能直接暴露“同一个 cell 绑定多个 LAC”的异常关系（理论上应接近 0）。
- 正常情况下：应非常少；若不为 0，需要逐条样例排查（可能是数据污染、默认值未剔除、或真实复用/切换导致）。

---

## 5. 摘要信息（Summary Queries）

1) 看映射底座规模（有多少条映射组合）：
```sql
select count(*) as mapping_cnt
from public."Y_codex_Layer2_Step05_CellId_Stats_DB";
```

2) 看 valid_gps_count 是否合理（不应超过 record_count）：
```sql
select count(*) as bad_rows
from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
where valid_gps_count > record_count;
```

3) 看每个运营商/制式下映射数量：
```sql
select operator_group_hint, tech_norm, count(*) as mapping_cnt
from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
group by 1,2
order by mapping_cnt desc;
```

4) 看 Top 映射（按 record_count）：
```sql
select operator_id_raw, tech_norm, lac_dec, cell_id_dec, record_count, active_days, distinct_device_count
from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
order by record_count desc
limit 50;
```

5) 看异常监测清单是否出现（总数）：
```sql
select count(*) as anomaly_cell_cnt
from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac";
```

6) anomaly 样例（必须提供，可直接复制）：
```sql
select *
from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"
order by lac_distinct_cnt desc, record_count desc
limit 100;
```

7) 主键重复检查（应为 0 行）：
```sql
select operator_id_raw, tech_norm, lac_dec, cell_id_dec, count(*) as dup_cnt
from public."Y_codex_Layer2_Step05_CellId_Stats_DB"
group by 1,2,3,4
having count(*) > 1;
```

---

## 6. 详细解释信息（Deep-dive / Debug Guide）

### 6.1 定位用查询（3~6 条）

1) 如果 anomaly 不为 0：回到明细看该 cell 的 LAC 明细（抽样）：
```sql
select m.operator_id_raw, m.tech_norm, m.cell_id_dec, m.lac_dec, count(*) as row_cnt
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked" m
where m.is_compliant
  and (m.operator_id_raw, m.tech_norm, m.cell_id_dec) in (
    select operator_id_raw, tech_norm, cell_id_dec
    from public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"
    order by lac_distinct_cnt desc, record_count desc
    limit 10
  )
group by 1,2,3,4
order by row_cnt desc;
```

2) 检查是否是“同一天/同设备”造成的短期多 LAC（辅助判断是否真实切换）：
```sql
select operator_id_raw, tech_norm, cell_id_dec,
       count(distinct lac_dec) as lac_cnt,
       count(distinct device_id) as device_cnt,
       count(distinct report_date) as days_cnt
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
where is_compliant
group by 1,2,3
having count(distinct lac_dec) > 1
order by lac_cnt desc, device_cnt desc
limit 50;
```

3) 如果映射数量异常偏小：确认 Step04 的可信 LAC 是否过少：
```sql
select count(*) as trusted_lac_cnt
from public."Y_codex_Layer2_Step04_Master_Lac_Lib";
```

### 6.2 常见异常 → 可能原因 → 建议处理

| 异常现象 | 可能原因 | 建议处理 |
|---|---|---|
| `Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac` 不为 0 | cell 真实复用/切换；或数据污染导致同 cell 多 LAC | 先输出 10 条样例，回溯到明细看是否集中在少数设备/少数日期 |
| 映射规模偏小 | Step04 可信规则过严（满天集合太小） | 可做对比实验：临时把 Step04 规则放宽到 `active_days>=6` 看映射是否更合理（仅实验，不替代正式口径） |
| `valid_gps_count` 大面积为 0 | GPS 缺失/越界/为 0 | 先接受并记录；未来阶段二会引入 gps_status 与补齐策略 |

---

## 7. 执行说明（How to Run）

- 全量模式：执行 `sql/05_step5_cellid_stats_and_anomalies.sql`
  - 耗时等级：XL（大规模聚合 + join 可信 LAC）
  - 是否建议物化：是（脚本已落表并建索引）
- 最小可跑模式（冒烟）：
  - 不落表：先看 Step04 的可信 LAC 数量是否合理，再用第 5 节摘要查询抽样验证 anomaly 是否触发。
  - 若要落小表：建议先按 `operator_id_raw` 或 `report_date` 做范围限制（用于白天验证口径）。
- 索引建议：脚本已为映射表建立主键索引与 `cell` 维度索引；一般无需额外索引。
- MCP 自检结果：见 `RUNBOOK_执行手册.md` 附录 A（含 anomaly 样例 10 条）。

---

## 8. 验收标准（Acceptance Criteria）

至少满足以下 5 条：

1. `public."Y_codex_Layer2_Step05_CellId_Stats_DB"` 成功生成且可查询。
2. 主键 `operator_id_raw+tech_norm+lac_dec+cell_id_dec` 无重复（重复检查返回 0 行）。
3. `valid_gps_count <= record_count` 对所有行成立（bad_rows=0）。
4. `public."Y_codex_Layer2_Step05_Anomaly_Cell_Multi_Lac"` 必须存在，且只包含 `lac_distinct_cnt>1` 的 cell。
5. anomaly 默认应接近 0；若不为 0，必须能输出至少 10 条样例并可回溯到明细定位原因。
