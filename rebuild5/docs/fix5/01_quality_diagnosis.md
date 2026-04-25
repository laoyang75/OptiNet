# fix5 / 01 质量诊断

> 诊断时间:2026-04-24
> PG17(黄金基线):`ip_loc2.rebuild5` @ 192.168.200.217:5433
> Citus(Gate 3 产出):`yangca.rb5` @ 192.168.200.217:5488
> 诊断范围:只读 SQL + 代码审计,未修改任何对象(除 §7 完工 note)

---

## 0. TL;DR

**一个根因串起 4 个异常:Citus runner 从未给每个 batch 建立"当日输入作用域表"。**
`scripts/run_citus_serial_batches.py` 不调用 `materialize_step2_scope(day)`,
导致 `rb5._step2_cell_input` 在 batch 1 建一次(含 fill.py cell_ts 回退产生的
2023 年脏数据)之后再也没重建(`get_step2_input_relation()` 在 profile/pipeline.py:550
检到表存在就直接 early-return)。

结果:**batch 2~7 全部在对 batch 1 的输入重跑 Step 2/3/4/5**。trusted_cell_library
从 batch 5 起饱和(347,038 行冻结),同一个 cell(如 4134817)的
`cell_sliding_window` 从 batch 2~7 永远是 31 行 day-1 数据。

第二个共振 bug:runner 强制设 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM=1`
(run_citus_serial_batches.py:24),`refresh_sliding_window` 的 trim 分支被关掉,
2023 年垃圾时间戳永不被裁掉。

C 阶段的最小修复只需要:runner 内调 `materialize_step2_scope` + 放开 trim。
不需要改分布键、重写 label_engine、重建 sliding_window 模型。

---

## 1. PG17 vs Citus 关键指标对比(batch 7)

| # | 维度 | PG17(黄金) | Citus | 关键偏差 |
|---|---|---|---|---|
| 1 | `trusted_cell_library` drift_pattern | stable 337,480 / dual_cluster 442 / uncertain 82 / large_coverage 745 / migration 4 / oversize_single 7 / insufficient 2,700 | stable 320,575 / insufficient 26,463 / **其余全部 0** | 多质心链路全崩,insufficient 膨胀 10× |
| 2 | `trusted_cell_library` 行数(batch 1→7) | 79,682 → 158,499 → 211,850 → 253,297 → 286,931 → 315,165 → **341,460**(持续增长) | 87,206 → 175,974 → 211,209 → 262,351 → **347,038 → 347,038 → 347,038**(batch 5 后冻结) | batch 5 起 TCL 整体冻结,和 sliding_window 冻结时刻完全对齐 |
| 3 | `label_results` k_eff 分布 | k=0:340,050 / k=1:882 / k=2:449 / k=3:67 / k=4:8 / k=5:3 / k=6:1 | k=0:346,971 / k=1:61 / k=2:**6** / k≥3:**0** | DBSCAN 产出率差 ~200×,k_eff≥3 完全缺失 |
| 4 | `cell_sliding_window` n_days / 日期范围 | 7 / 2025-11-30 ~ 2025-12-06(每批准确 +1 天) | 46 / **2023-12-29 ~ 2025-12-08**(batch 5~7 完全一致) | Citus 覆盖 46 天,其中 2024/2023 和 2025-12-08 未来时间戳均来自 fill.py 回退;且 batch 6/7 sliding_window **内容与 batch 5 完全相同** |
| 5 | `enriched_records` n_days(当前批 scope) | 每批严格 1 天(batch 7 = 2025-12-06) | batch 2=29 天 / batch 7=46 天 | Citus 每批都把 batch 1 的整批"累计 scope"重新做了一遍 enrichment |
| 6 | 单 cell `cell_id=4134817` 追踪 | batch 7:48 valid pts / k_eff=5 / label=uncertain | batch 2~7:**始终 31 rows / 全部 event_time=2025-11-30 / k_eff=2 label=insufficient** | 同一 cell 的 sliding_window 点数跨 6 批冻结不变,证明"在 batch 1 的输入上反复跑" |

### 关键辅助证据

- Citus **batch 3/5/7 的 6 个 k_eff=2 cell 完全一致**(cell_id、k_raw、k_eff、total_valid_pts、p90、pair_dist 逐字节相等),说明 DBSCAN 的输入没变过。
- Citus `candidate_cell_pool` 所有 195,584 行 `first_seen_batch_id=1, last_evaluated_batch_id=7`,候选池从未做过跨批 evolution。
- Citus `_step2_cell_input` 5,024,333 行 / 54 天,其中 `event_time_source='report_ts'` 的行 `min=max=2025-11-30`(batch 1 对应的 day)—— **直接证明这张表是 batch 1 那天建的,此后从未 refresh**。
- `rb5.raw_gps`(per-batch 载入表)确实是 batch 7 的当天数据(2025-12-07,3,623,955 行),说明 Step 1 的 raw 载入是对的,错位只发生在 Step 2 的输入 scope 处。
- `rb5.raw_gps_full_backup` 干净(2025-12-01 ~ 2025-12-07,7 天,无任何 2023 脏数据)—— **2023 时间戳不是来自上游**,是 fill.py 使用 `cell_ts_std` 回退时被带进来的(PG17 `etl_filled` 也有同样的 45 天 cell_ts 回退污染,但 PG17 runner 通过 `step2_batch_input` 的 `event_time_std BETWEEN day..day+1` 过滤把它挡掉了)。

---

## 2. 异常根因定位

### 2.1【根因】Citus runner 缺少 per-batch scope 物化,`_step2_cell_input` 永远停在 batch 1

**代码位置**
- `rebuild5/scripts/run_citus_serial_batches.py` 主循环 L813-L877:每批依次 `_load_raw_day → run_step1_pipeline → run_profile_pipeline → run_enrichment_pipeline → run_maintenance_pipeline`,**没有任何一步去物化 `rb5.step2_batch_input`**。
- 对比 PG17 使用的 `rebuild5/scripts/run_daily_increment_batch_loop.py` L148-L173:每批进 Step 2 之前先 `materialize_step2_scope(day, input_relation)`,按 `event_time_std >= day AND event_time_std < day+1` 建 `rb5.step2_batch_input`。
- Step 2 入口 `rebuild5/backend/app/profile/pipeline.py::get_step2_input_relation` L542-L568:
  ```python
  if relation_exists(STEP2_INPUT_SCOPE_RELATION):   # rb5.step2_batch_input
      return STEP2_INPUT_SCOPE_RELATION
  if relation_exists(STEP2_FALLBACK_CELL_RELATION): # rb5._step2_cell_input
      return STEP2_FALLBACK_CELL_RELATION           # ← early return,不 rebuild!
  if relation_exists('rb5.etl_cleaned'):
      execute(f'CREATE UNLOGGED TABLE {STEP2_FALLBACK_CELL_RELATION} AS SELECT * FROM rb5.etl_cleaned')
      ...
  ```
  一旦 batch 1 物化了 `_step2_cell_input`,函数就总返回它,后续批次的 `etl_cleaned` 重建(run_step1_pipeline 里做)完全被绕过。

**PG17 行为**:每批重建 `step2_batch_input`,严格 scope 到当天。
**Citus 行为**:batch 1 第一次调用时创建 `_step2_cell_input`,之后所有批次都吃它。

**证据**
- Citus `_step2_cell_input` 的 `event_time_source='report_ts'` 行 min/max 都是 2025-11-30(= batch 1 对应的 day);Citus `raw_gps_full_backup` 根本没这一天以外的 report_ts。
- cell 4134817 的 `cell_sliding_window` 从 batch 2 起永远 31 行,全部 `event_time_std=2025-11-30`。
- `trusted_cell_library` 行数从 batch 5 起冻结在 347,038(= "`_step2_cell_input` 能匹配到 donor 的 cell 上限",饱和后不再变化)。

**直接后果**:异常 ①②④ 全来自这一条。

---

### 2.2【根因】Citus runner 强制关闭 sliding_window trim

**代码位置**
- `rebuild5/scripts/run_citus_serial_batches.py` L24:
  ```python
  os.environ.setdefault("REBUILD5_SKIP_SLIDING_WINDOW_TRIM", "1")
  ```
- `rebuild5/backend/app/maintenance/window.py::refresh_sliding_window` L141-L142:
  ```python
  if os.getenv('REBUILD5_SKIP_SLIDING_WINDOW_TRIM') == '1':
      return
  ```
  trim 分支被无条件跳过 —— 2023 年脏数据进去之后再也没机会被裁掉。

**PG17 行为**:没有这个环境变量,trim 正常跑;`WINDOW_RETENTION_DAYS=14`
+ `WINDOW_MIN_OBS=1000` 会把 14 天以外、且不是当前 cell "最近 1000 点"的行删掉。

**Citus 行为**:trim 永远 return,`enriched_records`(从 stale `_step2_cell_input` 产出,
包含 fill.py cell_ts 回退的 2023 行)全部进入 `cell_sliding_window`,永不清理。

**证据**
- `cell_sliding_window` batch 5~7 的 min=2023-12-29(46 天),46 远大于 `WINDOW_RETENTION_DAYS=14`。
- 即使没有 §2.1 根因,单是 trim 被关也会让旧 batch 的点永远赖在窗口里,与真实数据 7 天 scope 严重不符。

**注意**:2023 年时间戳本身**不是** Citus 独有的 —— 是 `etl/fill.py::fill_event_time_std` 在
`report_ts` 缺失时回退到 `cell_ts_std`(设备自报 cell 时间戳,可能是历史值)产生的。
PG17 `etl_filled` 里有同样的 45 天分布,但 PG17 runner 通过 `step2_batch_input` 的日期窗口
天然把它挡在 Step 2 入口外。所以**修复不应去改 fill.py,只需恢复 scope 过滤 + 放开 trim**。

---

### 2.3【衍生】label_engine 候选池产出率骤降(k_eff≥3 为 0)

**代码位置**
- `rebuild5/backend/app/maintenance/label_engine.py` L404:
  ```sql
  COUNT(*) FILTER (WHERE c.dev_day_pts >= %s AND c.dev_count >= %s) AS k_eff
  ```
- 同文件 L654-L687 的 label CASE 规则 2a(L656-L658):当 `cs.total_dedup_pts`、`cs.dedup_dev_count`、`cs.dedup_day_count` 任一不达阈值就判 `insufficient`。

**根因仍是 §2.1**:候选点来自 stale 的 sliding_window(全是 batch 1 的稀疏观测),
cell 4134817 这类本该 48 点 / 多设备 / 多天的 cell 在 Citus 只有 31 点 / 1 天,
DBSCAN 自然只能切出 ≤2 簇,且 Rule 2a 把它判成 `insufficient`。

所以这里**没有独立的 bug**,只要 §2.1 修好,label_engine 的产出会自动恢复。
无需改候选池筛选阈值,也无需切 postgis fallback。

**反向验证**:Gate 3 diag prompt §2.3 提到的"snapshot_seed_records 跨批桥接去重"
改动(enrichment/pipeline.py::_insert_snapshot_seed_records 的 DISTINCT ON)我审计过,
语义是正确的去重 —— 且 candidate_seed_history 本身对历史批次累积,
不是 §2.1 的污染源。

---

### 2.4【衍生】2023 / 未来 2025-12-08 时间戳出现在 sliding_window

**代码位置与链路**
1. `rebuild5/backend/app/etl/fill.py` 在 `event_time_std` 计算时允许 `cell_ts_std` 回退
   (`event_time_source='cell_ts'`,设备自报时间戳,可能是历史或错位值)。
2. PG17 和 Citus 的 `etl_filled` / `etl_cleaned` 都有这 45 天分布(2023-11-07 ~ 2025-12-07)。
3. PG17 通过 `step2_batch_input` 的严格日期窗口**在 Step 2 入口外**挡掉。
4. Citus 因为 §2.1,从未做日期窗口裁剪;因为 §2.2,sliding_window 也不 trim。

**"未来 2025-12-08" 的出处**:同样是 cell_ts_std 回退,部分设备上报的 cell 时间戳
大于 raw ts(调休 / 补报 / 时钟错位),被 fill.py 当成 event_time 吞进来。

**不需要改 fill.py**:fill.py 的语义是"当 report_ts 缺失时接受低质量 cell_ts"
—— 是产品设计的容错,历史上 PG17 跑通的就是这一份 fill 代码。修复 §2.1/§2.2 后
这些垃圾时间戳会被 Step 2 日期窗口和 Step 5 trim 双重过滤掉,不会流到下游。

---

## 3. 给 C 阶段 agent 的具体修复清单

### 修复 A(必做,最小闭环):给 Citus runner 加 per-batch scope 物化

**文件**:`rebuild5/scripts/run_citus_serial_batches.py`

**改动**:在主循环(约 L816-L828,`_load_raw_day` 之后、`run_step1_pipeline` 之前 —— 注意顺序,
Step 1 写 `etl_cleaned`,step2_scope 必须在 Step 1 完成之后物化)加调用:

```python
# 在 step1 完成后、run_profile_pipeline 之前:
from rebuild5.scripts.run_daily_increment_batch_loop import materialize_step2_scope
...
step1 = run_step1_pipeline()
_log({"event": "step1_done", "day": day.isoformat(), "result": step1})

scope_rows = materialize_step2_scope(day=day, input_relation='rb5.etl_cleaned')
_log({"event": "step2_scope_materialized", "day": day.isoformat(), "rows": scope_rows})

step3 = run_profile_pipeline()
```

或者更干净的做法:把 `materialize_step2_scope` 及其常量提到共享模块(比如
`rebuild5/backend/app/profile/pipeline.py` 旁边的 scripts-level helper),两个 runner 共享。

**同时**:在每批开始处显式 `DROP TABLE IF EXISTS rb5._step2_cell_input` 以兜底
(防御 `etl_cleaned` 里 cell_ts 历史数据通过 fallback 再次污染)。

**验证**:跑 batch 2 后单测 —— `SELECT MIN(event_time_std), MAX(event_time_std) FROM rb5.step2_batch_input;`
应该严格落在 `day..day+1` 之间;`SELECT MIN(event_time_std)::date, MAX(event_time_std)::date
FROM rb5.enriched_records WHERE batch_id=2;` 应该只有 2025-12-01 单天。

### 修复 B(必做):放开 sliding_window trim

**文件**:`rebuild5/scripts/run_citus_serial_batches.py` L24

**改动**:删除这行
```python
os.environ.setdefault("REBUILD5_SKIP_SLIDING_WINDOW_TRIM", "1")
```

或改成显式允许:`os.environ.pop("REBUILD5_SKIP_SLIDING_WINDOW_TRIM", None)`。

**Citus 侧伴随**:window.py L180-L183 的 trim SQL 用到
`citus.max_intermediate_result_size = -1` 的 session SET。用户已决议 C 阶段把
这个值**全局 ALTER SYSTEM 调大**(NEXT_SESSION_PROMPT §5 "C 阶段范围"第 2 条),
所以 session SET 可以保留做双保险,不影响功能。

**验证**:batch 2 跑完后 `SELECT MAX(event_time_std) - MIN(event_time_std) FROM rb5.cell_sliding_window;`
应 ≤ `14 days` 或退化到 per-cell 最近 1000 obs(配置允许);且不应出现 2023/2024 年 min。

### 修复 C(推荐):为 `get_step2_input_relation` 的 fallback 分支加上过期保护

**文件**:`rebuild5/backend/app/profile/pipeline.py` L542-L568

**当前行为**:只要 `_step2_cell_input` 存在就直接返回,不 rebuild。
**推荐改动**:如果检测到 `_step2_cell_input` 的 `event_time_std` 最大值落在
远早于 `etl_cleaned` 的最大值,就 `DROP + rebuild`(或直接让 runner 显式先 drop,
参考修复 A 的兜底)。**但修复 A 已经消除这个路径被触达的需要**,修复 C 属于防御性改进,
可选。

### 不需要改的

- `etl/fill.py`:`cell_ts_std` 回退语义正确,PG17 一直这样跑通。
- `maintenance/label_engine.py`:候选阈值不需要调,k_eff 规则正确,产出率低是 §2.1 的下游症状。
- `enrichment/pipeline.py::_insert_snapshot_seed_records`:DISTINCT ON 去重逻辑正确,不是污染源。
- `candidate_cell_pool` / `candidate_seed_history` 结构:没有 bug,跟 PG17 一致。
- 分布键、sliding_window 表结构:用户已明确 C 阶段不做结构大改。

---

## 4. 重跑策略建议

用户已拍板 C 阶段做三件事(NEXT_SESSION_PROMPT §5):(1) 修 bug;
(2) `citus.max_intermediate_result_size` 全局 ALTER SYSTEM 调大;
(3) Step 1 和 Step 2-5 **pipelined 并行**(`run_step1_step25_pipelined_temp.py` 模式)。

诊断侧对应的重跑动作:

1. **需要整体 reset 全部 rb5.\* 重跑**,不能"从 batch N 接上"。原因:
   - `_step2_cell_input` 从 batch 1 就污染了,所有 7 批产出的 `trusted_cell_library` / `label_results`
     / `cell_sliding_window` 都建立在错误输入上。
   - `trusted_cell_library` batch 1~7 的 cumulative donor 也链式污染
     (batch N 的 donor 来自 batch N-1 的 TCL,batch N-1 错 → batch N 错)。
   - 执行 `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql`
     (已经 drop 了 `step2_batch_input` 和 `_step2_cell_input`,见该 SQL L43-L44),
     确保 scope 表从空开始。

2. **修复落地顺序建议**:
   1. 先合修复 A + B,在单批(比如只跑 2025-12-01 一天)验证:
      - `step2_batch_input` 严格单日
      - `enriched_records` 单日
      - `cell_sliding_window` 严格 7 天滚动(跑到 batch 2 才有第二天进来)
   2. 单批验证通过后,再连跑 7 批 full run。
   3. 用 PG17 `rebuild5.trusted_cell_library` batch 7 的分布(stable 337,480 / insufficient 2,700 /
      large_coverage 745 / dual_cluster 442 / uncertain 82 / oversize_single 7 / migration 4)
      作为**对齐目标**,允许 ±5% 差异,不允许任何 drift_pattern 类别为 0。

3. **Pipelined 并行(C 阶段第 3 项)不要和修复 A/B 同批引入**:先把分布对齐拿到,
   再切 pipelined 模型,防止把 pipelined 特有的问题和 scope bug 混在一起排查。

4. **回归哨兵**(给 C 阶段 agent 加到 runner 内):每批完成后校验
   - `SELECT MIN(event_time_std)::date FROM rb5.enriched_records WHERE batch_id=%s` == 当日
   - `SELECT MAX(event_time_std) - MIN(event_time_std) FROM rb5.cell_sliding_window` ≤ `14 days`
   - `SELECT COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id=%s AND drift_pattern='dual_cluster'` > 0 (从 batch 3 起)
  任意一条挂掉,立刻停 run 并写 blocker note。

---

## 5. 未回答问题 / 给 C 阶段 agent 的判断题

- **修复 A 的最佳 PG17 兼容性**:直接 import `run_daily_increment_batch_loop.materialize_step2_scope`
  最省事,但 Citus 和 PG17 两个 runner 引用同一个函数后要确保在 Citus 环境下
  `execute` 能正常拿到连接(该函数现在用 `execute` 模块级全局连接,跨 import 应 OK)。
- **修复 A 要不要同时砍 `_step2_cell_input` 这个 fallback 分支**:目前倾向保留 —— 它在
  手工临时实验时有价值(直接跑无日期 scope 的全量)。只要 Citus runner 显式物化
  `step2_batch_input`,fallback 就不会被触达。
- **PG17 sliding_window trim 的 span > 14 天检查**(window.py L139)是否在 Citus 环境下
  真的生效:目前因为 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM=1` 在条件之前 return,
  没机会试。修复 B 之后还需要观察一次实际 trim 的 EXPLAIN 看 intermediate-result 大小,
  如果触发 `citus.max_intermediate_result_size` 限制就走 C 阶段 ALTER SYSTEM 路径。

---

## 6. 交付给 C 阶段的一句话

**改 2 个文件,10 行代码 左右**:`run_citus_serial_batches.py` 加一次
`materialize_step2_scope` 调用 + 删除 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM` 的
`setdefault`。配合 reset SQL 全量 rerun,Citus batch 7 的 drift_pattern
分布应能恢复到 PG17 黄金基线的 ±5% 量级。不需要改分布键、label_engine、fill.py。
