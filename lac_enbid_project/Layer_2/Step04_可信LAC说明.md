# Step04 可信 LAC 说明（Trusted LAC）

## 1. 一句话摘要（TL;DR）

从 Step03 的“有效 LAC 汇总库”里筛出 **可信 LAC 集合**：当前版用最简单、可解释的规则——`活跃天数（active_days）= 本周期最大值`（7 天窗口即“满天优先”）。输出的可信 LAC（Step04）会作为 Step05 建映射的“LAC 白名单”。

---

## 2. 输入（Input）

-- 输入对象：`public."Y_codex_Layer2_Step03_Lac_Stats_DB"`
- 输入依赖：Step03
- 输入关键字段（中文（English））：
  - 运营商id_细粒度（operator_id_raw）
  - 制式_标准化（tech_norm）
  - LAC十进制（lac_dec）
  - 活跃天数（active_days）
  - 总上报次数（record_count）
  - 有效GPS次数（valid_gps_count）
  - 首次/最后出现（first_seen_ts / last_seen_ts）

---

## 3. 输出（Output）

-- 输出对象：`public."Y_codex_Layer2_Step04_Master_Lac_Lib"`（TABLE）
- 主键粒度：`operator_id_raw + tech_norm + lac_dec`
- 输出关键字段（中文（English））：
  - 标记字段（Flags）：
    - 是否可信LAC（is_trusted_lac）：当前版恒为 true（已按规则筛选）
  - 统计字段（Stats）：透传 Step03 的全部指标（`record_count/valid_gps_count/active_days/first_seen/last_seen/distinct_*`）

---

## 4. 本步骤“核心指标”解释（Human-readable）

### 4.1 可信规则：稳定性 + 规模门槛（本轮窗口的临时策略）

- 口径（本轮确认）：
  1) **稳定性硬条件**：只保留 `active_days = 7` 的 LAC；
  2) **规模门槛（默认）**：同时满足
     - `distinct_device_count >= 5`
     - `record_count >= P80(record_count)`（在 `active_days=7` 的同组同制式 LAC 内计算 80 分位；脚本落地用 `ceil(P80)` 做整数门槛）
  3) **特殊处理 A（46015/46020）**：数据量偏小但仍需要保留 → 仅要求 `active_days=7`，免除规模门槛；
  4) **特殊处理 B（CU/CT 的 5G）**：怀疑共建共享导致设备数口径偏小 → 设备门槛按 `/2`：`5/2=2.5`，实际落地为 `distinct_device_count >= 3`（向上取整），仍需满足 `record_count >= P80(record_count)`。
- 为什么要这样做：
  - `active_days=7` 提供“时间稳定性”强信号；
  - 规模门槛用于剔除稳定但极稀疏的 LAC，避免 Step05 映射底座被噪声拖累；
  - 两个特殊处理用来避免结构性误伤（46015/46020）并在 5G 口径不确定时保守放宽（CU/CT）。
- 重要说明：这是基于“当前 7 天窗口”统计画像制定的 **临时策略**；当窗口变化（天数/城市/采集源结构）时，需要重新跑分位与门槛敏感性，再调整阈值。

### 4.2 可信 LAC 数量（trusted_lac_cnt）

- 口径：`count(*)`。
- 为什么要看：太少会导致 Step05 映射规模过小；太多则说明“满天”规则过松（或窗口不完整导致 max_active_days 很小）。
- 正常情况下：数量与样本覆盖、运营商/制式有关；更重要的是“能支撑 Step05 映射”和“异常可解释”。

---

## 5. 摘要信息（Summary Queries）

1) 看 Step03 的 `active_days` 分布（确认窗口完整性）：
```sql
select active_days, count(*) as lac_cnt
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
group by 1
order by active_days;
```

2) 看可信 LAC 数量：
```sql
select count(*) as trusted_lac_cnt
from public."Y_codex_Layer2_Step04_Master_Lac_Lib";
```

3) 看可信 LAC 的运营商/制式分布：
```sql
select operator_group_hint, tech_norm, count(*) as trusted_lac_cnt
from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
group by 1,2
order by trusted_lac_cnt desc;
```

4) 确认可信集合内 `active_days` 都为 7（应为 0）：
```sql
select count(*) as bad_rows
from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
where active_days <> 7;
```

5) 主键重复检查（应为 0 行）：
```sql
select operator_id_raw, tech_norm, lac_dec, count(*) as dup_cnt
from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
group by 1,2,3
having count(*) > 1;
```

---

## 6. 详细解释信息（Deep-dive / Debug Guide）

### 6.1 定位用查询（3~6 条）

1) 如果 `active_days=7` 的 LAC 数量异常：查看 `active_days` 分布，判断是否窗口不完整：
```sql
select active_days, count(*) as lac_cnt
from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
group by 1
order by active_days;
```

2) 如果可信 LAC 数量过少：看是否被某些运营商/制式“全灭”：
```sql
select operator_id_raw, tech_norm, count(*) as trusted_lac_cnt
from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
group by 1,2
order by trusted_lac_cnt asc
limit 20;
```

3) 用 Step03 复算 P80 门槛（便于解释为什么某些 LAC 被筛掉）：
```sql
with base as (
  select
    case
      when operator_id_raw in ('46000','46015','46020') then 'CMCC_FAMILY'
      when operator_id_raw='46001' then 'CUCC'
      when operator_id_raw='46011' then 'CTCC'
      else 'OTHER'
    end as op_group,
    tech_norm,
    record_count
  from public."Y_codex_Layer2_Step03_Lac_Stats_DB"
  where active_days=7
)
select op_group, tech_norm,
       ceil(percentile_cont(0.8) within group (order by record_count))::bigint as p80_reports_min
from base
group by 1,2
order by 1,2;
```

4) 抽样查看可信 LAC 的 `record_count/valid_gps_count/distinct_device_count`（是否极端稀疏）：
```sql
select operator_id_raw, tech_norm, lac_dec, record_count, valid_gps_count, distinct_device_count
from public."Y_codex_Layer2_Step04_Master_Lac_Lib"
order by record_count desc
limit 50;
```

### 6.2 常见异常 → 可能原因 → 建议处理

| 异常现象 | 可能原因 | 建议处理 |
|---|---|---|
| `active_days=7` 的 LAC 很少 | 数据没覆盖满 7 天 / report_date 有断层 | 先确认 Step00 的 report_date 覆盖；必要时按日期分段跑 |
| 可信 LAC 数量极少 | 规模门槛过严（P80 太高）或设备门槛过严 | 用第 3 条查询复算 P80；在画像报告中做 P{70,80,90} 与设备门槛敏感性对比后再调参 |
| 可信 LAC 数量过多 | 规模门槛过松或 46015/46020 免门槛导致量膨胀 | 先按运营商拆分看结构；必要时对 46015/46020 加更弱门槛（例如 dev>=3 或 rpt>=P50） |

---

## 7. 执行说明（How to Run）

- 全量模式：执行 `sql/04_step4_master_lac_lib.sql`
  - 耗时等级：S（基于 Step03 小表筛选）
  - 是否建议物化：是（脚本已落表并建 PK 索引）
- 最小可跑模式（冒烟）：即使只做 Step03 的局部样本聚合，也可直接跑 Step04（逻辑可验证）。
- MCP 自检结果：见 `RUNBOOK_执行手册.md` 附录 A。

---

## 8. 验收标准（Acceptance Criteria）

至少满足以下 5 条：

1. `public."Y_codex_Layer2_Step04_Master_Lac_Lib"` 成功生成且可查询。
2. 主键 `operator_id_raw+tech_norm+lac_dec` 无重复（重复检查返回 0 行）。
3. 可信集合内 `active_days` 全部等于 7（bad_rows=0）。
4. `is_trusted_lac` 恒为 true（作为下游 join 的显式标记）。
5. 可信 LAC 数量与结构（按运营商/制式）可解释；若极端偏小/偏大，必须能回溯到 Step03/Step00 的窗口覆盖或合规率问题。
