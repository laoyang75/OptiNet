# Step00 标准化视图说明（Standardized Views）

## 1. 一句话摘要（TL;DR）

把 Layer_0 明细统一映射出一套 **可复用的标准字段**（例如：`制式_标准化（tech_norm）/运营商id_细粒度（operator_id_raw）/运营商组_提示（operator_group_hint）/上报日期（report_date）/是否有值（has_*）`），后续 Step01~Step06 **只读这些字段**做统计、合规与建库。

---

## 2. 输入（Input）

- 输入对象（schema.table）：
  - `public."Y_codex_Layer0_Gps_base"`
  - `public."Y_codex_Layer0_Lac"`
- 输入依赖：无（Step00 是全流程起点）
- 输入关键字段（中文（English））：
  - 顺序ID（seq_id）
  - 报文时间（ts_std）
  - 制式（tech）
  - 运营商ID（"运营商id"）
  - LAC十进制（lac_dec）
  - Cell十进制（cell_id_dec）
  - 解析来源（parsed_from）
  - 设备DID（did）/设备OAID（oaid）
  - 经度（lon）/纬度（lat）

---

## 3. 输出（Output）

- 输出对象（schema.view）：
  - `public."Y_codex_Layer2_Step00_Gps_Std"`
  - `public."Y_codex_Layer2_Step00_Lac_Std"`
- 主键粒度：行级（建议使用 `顺序ID（seq_id）` 作为行级标识）
- 输出关键字段（中文（English））：
  - 派生字段（Derived）：
    - 制式_标准化（tech_norm）：`4G/5G/2_3G/其他`
    - 运营商id_细粒度（operator_id_raw）
    - 运营商组_提示（operator_group_hint）
    - 上报日期（report_date）：`date(ts_std)`
    - 设备ID（device_id）：`coalesce(did, oaid)`
    - lac长度（lac_len）、cell长度（cell_len）（仅用于理解/排查，不用于硬过滤）
  - 标记字段（Flags）：
    - 是否有cell（has_cellid）：`cell_id_dec is not null`
    - 是否有lac（has_lac）：`lac_dec is not null`
    - 是否有gps（has_gps）：`lon/lat` 合法且不为 (0,0)
  - 透传字段（Pass-through）：Layer_0 原字段全部保留（便于回溯）

> 字段含义与生成逻辑详见：`Data_Dictionary.md`。

---

## 4. 本步骤“核心指标”解释（Human-readable）

> Step00 本身不产出统计表，但它派生的字段决定后续所有统计的“口径一致性”。建议把下面这些当作 Step00 的核心检查指标。

### 4.1 制式_标准化（tech_norm）

- 计算口径：由原始 `制式（tech）` 归一为四类：`4G/5G/2_3G/其他`
- 为什么要看它：后续合规（Step02）只会保留 `4G/5G`，`2_3G/其他` 的占比过高通常意味着上游解析/写法不一致。
- 正常情况下大致应该是什么样：`4G/5G` 为主；`其他` 不应长期占比很高（除非源数据确实有大量脏值）。

### 4.2 运营商id_细粒度（operator_id_raw）与 运营商组_提示（operator_group_hint）

- 计算口径：`operator_id_raw` 直接来自 `"运营商id"`；`operator_group_hint` 仅做分组提示（不改变主键粒度）。
- 为什么要看它：同一个组里可能包含多个 PLMN（如移动系 `46000/46015/46020`），统计口径要能同时支持“细粒度”和“组视角”。
- 正常情况下大致应该是什么样：北京样本中以 5 个核心 PLMN 为主；出现大量 `OTHER` 时建议先确认源数据范围。

### 4.3 是否有值（has_cellid / has_lac / has_gps）

- 计算口径：
  - `has_cellid`：是否存在 `cell_id_dec`
  - `has_lac`：是否存在 `lac_dec`
  - `has_gps`：经纬度是否为空/越界/为 0
- 为什么要看它：你明确关心“抽取到了但无值也被统计”的问题；Step00 通过 `has_*` 让后续统计能区分“缺值导致的假活跃”。
- 正常情况下大致应该是什么样：
  - `has_cellid/has_lac` 不应长期很低（否则合规数据会大幅缩水）
  - `has_gps` 可能偏低（与上报场景有关），但应能解释且可被 Step05 的 `valid_gps_count` 捕捉

---

## 5. 摘要信息（Summary Queries）

> 下面每条都是“短小可复制”的 SELECT，用于人工快速扫一眼 Step00 是否健康（不创建对象）。

1) 看标准化视图是否能正常读取（冒烟）：
```sql
select * from public."Y_codex_Layer2_Step00_Gps_Std" limit 5;
```

2) 看 `制式_标准化（tech_norm）` 分布（是否异常偏“其他”）：
```sql
select tech_norm, count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1
order by row_cnt desc;
```

3) 看 `运营商组_提示（operator_group_hint）` 分布：
```sql
select operator_group_hint, count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1
order by row_cnt desc;
```

4) 看核心 5 个运营商覆盖情况（`运营商id_细粒度（operator_id_raw）`）：
```sql
select operator_id_raw, count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1
order by row_cnt desc
limit 20;
```

5) 看缺值结构（`是否有值（has_*）`）：
```sql
select
  count(*) as row_cnt,
  count(*) filter (where not has_cellid) as no_cellid_rows,
  count(*) filter (where not has_lac) as no_lac_rows,
  count(*) filter (where not has_gps) as no_gps_rows
from public."Y_codex_Layer2_Step00_Gps_Std";
```

6) 看 `上报日期（report_date）` 覆盖（是否落在 7 天窗口）：
```sql
select report_date, count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1
order by report_date;
```

7) 看 `解析来源（parsed_from）` 分布（ss1 是否存在）：
```sql
select parsed_from, count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1
order by row_cnt desc;
```

---

## 6. 详细解释信息（Deep-dive / Debug Guide）

### 6.1 定位用查询（3~6 条）

1) 如果 `tech_norm='其他'` 占比高：看原始 `制式（tech）` 的写法有哪些：
```sql
select tech, count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
where tech_norm = '其他'
group by 1
order by row_cnt desc
limit 30;
```

2) 如果 `operator_id_raw is null` 很多：查看原始 `"运营商id"` 是否为空/空格：
```sql
select "运营商id", count(*) as row_cnt
from public."Y_codex_Layer2_Step00_Gps_Std"
where operator_id_raw is null
group by 1
order by row_cnt desc
limit 20;
```

3) 如果 `has_gps=false` 很多：看经纬度空值与越界是否集中在某些来源：
```sql
select parsed_from,
       count(*) as row_cnt,
       count(*) filter (where not has_gps) as no_gps_rows
from public."Y_codex_Layer2_Step00_Gps_Std"
group by 1
order by row_cnt desc;
```

4) 抽样查看缺值行（用于人工判读原始字段）：
```sql
select seq_id, "记录id", ts_std, tech, "运营商id", "原始lac", cell_id, lon, lat, parsed_from
from public."Y_codex_Layer2_Step00_Gps_Std"
where (not has_cellid) or (not has_lac)
limit 20;
```

### 6.2 常见异常 → 可能原因 → 建议处理

| 异常现象 | 可能原因 | 建议处理 |
|---|---|---|
| `tech_norm='其他'` 比例高 | 上游 `tech` 写法不统一/为空 | 优先补充 `tech` 映射表（先记录，不硬过滤） |
| `operator_group_hint='OTHER'` 很多 | `"运营商id"` 不在 5 个核心 PLMN | 先核对数据范围；若是新运营商，补充分组映射 |
| `has_cellid=false` 很多 | cell_id 解析失败/非数字/缺失 | Step02 会剔除；建议回到 Layer_0 解析排查来源字段 |
| `has_lac=false` 很多 | lac 解析失败/非数字/缺失 | Step02 会剔除；建议回到 Layer_0 解析排查 Tac/Lac 键 |
| `report_date` 超出窗口 | `ts_std` 解析异常或源数据跨周期 | Step01/02 可按 `report_date` 拆分跑并记录异常日期 |

---

## 7. 执行说明（How to Run）

- 推荐执行方式：直接执行 `sql/00_step0_std_views.sql`
- 耗时等级：S
- 是否建议物化：默认不需要；如果后续多次重复全表扫描，可考虑把标准化视图物化为表并加索引（仅性能优化，不改变口径）。
- 可选时间范围限制方式（用于冒烟/调试）：在所有查询上增加 `where report_date between '2025-12-01' and '2025-12-07'` 并配合 `limit`。
- MCP 自检结果：见 `RUNBOOK_执行手册.md` 附录 A（将记录 count/重复等）。

---

## 8. 验收标准（Acceptance Criteria）

至少满足以下 5 条：

1. `public."Y_codex_Layer2_Step00_Gps_Std"` 与 `public."Y_codex_Layer0_Gps_base"` 字段可正常读取（冒烟 `limit 5` 通过）。
2. `制式_标准化（tech_norm）` 仅出现 `4G/5G/2_3G/其他` 四类。
3. `上报日期（report_date）` 能派生且可用于按天聚合（`group by report_date` 可跑通）。
4. `运营商id_细粒度（operator_id_raw）` 与 `运营商组_提示（operator_group_hint）` 输出稳定；核心 5 个 PLMN 能识别为 `CMCC/CUCC/CTCC` 组。
5. `是否有值（has_cellid/has_lac/has_gps）` 三个布尔字段可用，且能区分缺值行（抽样查询可定位到具体记录）。
