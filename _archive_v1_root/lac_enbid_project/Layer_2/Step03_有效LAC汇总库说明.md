# Step03 有效 LAC 汇总库说明（Effective LAC Rollup）

## 1. 一句话摘要（TL;DR）

只基于 Step02 的合规数据（`is_compliant=true`），按 `运营商id_细粒度（operator_id_raw） + 制式_标准化（tech_norm） + LAC十进制（lac_dec）` 聚合，生成“有效 LAC 统计主表”：包含 `总上报次数（record_count）/有效GPS次数（valid_gps_count）/活跃天数（active_days）/首次出现（first_seen）/最后出现（last_seen）/关联小区数/关联设备数`，为 Step04 可信 LAC 过滤提供输入。

---

## 2. 输入（Input）

-- 输入对象：`public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"`
- 输入依赖：Step02（合规标记必须先完成）
- 输入筛选口径：仅取 `是否合规（is_compliant）= true`
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

---

## 3. 输出（Output）

-- 输出对象：`public."Y_codex_Layer2_Step03_Lac_Stats_DB"`（TABLE）
- 主键粒度：`operator_id_raw + tech_norm + lac_dec`
- 输出关键字段（中文（English））：
  - 统计字段（Stats）：
    - 总上报次数（record_count）
    - 有效GPS次数（valid_gps_count）
    - 关联小区数（distinct_cellid_count）
    - 关联设备数（distinct_device_count）
    - 首次出现时间（first_seen_ts）/最后出现时间（last_seen_ts）
    - 首次出现日期（first_seen_date）/最后出现日期（last_seen_date）
    - 活跃天数（active_days）
  - 派生/透传字段（Derived/Pass-through）：
    - 运营商组_提示（operator_group_hint）（仅报表视角）

---

## 4. 本步骤“核心指标”解释（Human-readable）

### 4.1 总上报次数（record_count）

- 口径：该 LAC 主键组合下的合规记录行数。
- 为什么要看：衡量这个 LAC 的“样本量”；也用于发现刷量或异常高频 LAC。
- 正常情况下：长尾分布明显；极少数 LAC 很高频，多数 LAC 低频。

### 4.2 有效GPS次数（valid_gps_count）

- 口径：`是否有gps（has_gps）= true` 的记录计数。
- 为什么要看：未来阶段二/三需要 GPS 来做聚类/中心点；`valid_gps_count` 过低的 LAC 虽然活跃但可能难以定位。
- 正常情况下：小于等于 `record_count`；如果几乎为 0，说明 GPS 质量或上报场景限制明显。

### 4.3 活跃天数（active_days）

- 口径：`count(distinct 上报日期（report_date）)`。
- 为什么要看：Step04 的“可信 LAC”当前版就用它做过滤（满天优先）；也能发现“只活跃一天的偶发 LAC”。
- 正常情况下：在 7 天窗口内应 `<=7`；若出现 `>7`，通常是 `report_date` 解析异常或数据跨周期。

### 4.4 首次/最后出现（first_seen / last_seen）

- 口径：以 `报文时间（ts_std）` 的 min/max（并同时给出 date 版本）。
- 为什么要看：判断 LAC 是否贯穿周期、是否集中爆发，以及是否存在“时间异常倒序”。
- 正常情况下：`first_seen <= last_seen`；且应落在本周期附近。

### 4.5 关联小区数/关联设备数（distinct_*）

- 口径：分别对 `cell_id_dec` 与 `device_id` 做去重计数。
- 为什么要看：帮助判断 LAC 是“少量设备集中”还是“多设备共同出现”；也为后续可信策略升级留接口。
- 正常情况下：`distinct_cellid_count` 通常明显小于 `record_count`；`distinct_device_count` 取决于样本规模。

---

## 5. 摘要信息（Summary Queries）

1) 看 LAC 主表规模（多少条 LAC 组合）：
```sql
select count(*) as lac_key_cnt
from public."Y_codex_Layer2_Step03_Lac_Stats_DB";
```

2) 看 `active_days` 分布（是否有 >7 的异常）：
```sql
select active_days, count(*) as lac_cnt
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
group by 1
order by active_days;
```

3) 看每个运营商组/制式下 LAC 数量：
```sql
select operator_group_hint, tech_norm, count(*) as lac_cnt
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
group by 1,2
order by lac_cnt desc;
```

4) 看 Top LAC（按 record_count）：
```sql
select operator_id_raw, tech_norm, lac_dec, record_count, active_days, distinct_device_count
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
order by record_count desc
limit 50;
```

5) 看 GPS 可用性（valid_gps_count 的整体比例）：
```sql
select
  sum(valid_gps_count) as valid_gps_count,
  sum(record_count) as record_count,
  round(sum(valid_gps_count)::numeric / nullif(sum(record_count),0), 8) as valid_gps_pct
from public."Y_codex_Layer2_Step03_Lac_Stats_DB";
```

6) 主键重复检查（应为 0 行）：
```sql
select operator_id_raw, tech_norm, lac_dec, count(*) as dup_cnt
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
group by 1,2,3
having count(*) > 1;
```

---

## 6. 详细解释信息（Deep-dive / Debug Guide）

### 6.1 定位用查询（3~6 条）

1) 如果出现 `active_days > 7`：先定位异常 LAC 的日期范围：
```sql
select operator_id_raw, tech_norm, lac_dec, active_days, first_seen_date, last_seen_date
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
where active_days > 7
order by active_days desc
limit 50;
```

2) 如果某个运营商/制式 LAC 数量异常：看该维度下 `record_count` 分布：
```sql
select operator_id_raw, tech_norm,
       percentile_disc(0.5) within group (order by record_count) as p50_record_count,
       percentile_disc(0.9) within group (order by record_count) as p90_record_count
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
group by 1,2
order by 1,2;
```

3) 抽样查看某个高频 LAC 的原始明细（回溯到 Step02）：
```sql
select seq_id, "记录id", ts_std, operator_id_raw, tech_norm, lac_dec, cell_id_dec, device_id, has_gps
from public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"
where is_compliant
  and operator_id_raw = '46000'
order by ts_std
limit 50;
```

### 6.2 常见异常 → 可能原因 → 建议处理

| 异常现象 | 可能原因 | 建议处理 |
|---|---|---|
| `active_days > 7` | `report_date` 解析异常或数据跨周期混入 | 先按 `report_date` 切片确认；必要时在全量跑时做日期过滤 |
| Top LAC 过度集中 | 真实热点 / 刷量 / 默认值污染 | 结合 `distinct_device_count` 与 Step05 anomaly 看是否为异常 |
| `valid_gps_pct` 接近 0 | GPS 长期缺失或经纬度异常 | 未来阶段二会引入 `gps_status`；本阶段先记录即可 |

---

## 7. 执行说明（How to Run）

- 全量模式：执行 `sql/03_step3_lac_stats_db.sql`
  - 耗时等级：XL（大规模聚合）
  - 是否建议物化：是（脚本已落表 + PK 索引 + ANALYZE）
- 最小可跑模式（冒烟）：
  - 不落表：直接对 `public."Y_codex_Layer2_Step02_Gps_Compliance_Marked"` 加 `report_date` 限制 + `limit`，用第 5 节摘要查询跑通口径。
  - 或者：只在某一个 `运营商id_细粒度（operator_id_raw）` 上跑一遍（快速验证）。
- 索引建议：本表脚本自带主键唯一索引；一般不需要额外索引。
- MCP 自检结果：见 `RUNBOOK_执行手册.md` 附录 A（含 active_days 分布）。

---

## 8. 验收标准（Acceptance Criteria）

至少满足以下 5 条：

1. `public."Y_codex_Layer2_Step03_Lac_Stats_DB"` 成功生成且可查询。
2. 主键 `operator_id_raw+tech_norm+lac_dec` 无重复（重复检查返回 0 行）。
3. `sum(record_count)` 等于 Step02 合规有效行数（口径一致）。
4. `active_days` 不应超过 7（本周期窗口）；若超过必须解释并给出处理方式（通常是日期范围过滤）。
5. `valid_gps_count <= record_count` 恒成立（若不成立说明 has_gps 口径或聚合写法错误）。
