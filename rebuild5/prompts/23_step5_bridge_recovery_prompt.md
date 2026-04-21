# Step5 数据桥修复重启 Prompt

你在仓库：

`/Users/yangcongan/cursor/WangYou_Data`

本次任务不是直接改代码，也不是直接重跑，而是**严格按既定顺序修复 Step3 -> Step5 数据桥问题**，避免再次因为上下文污染或顺序错误导致误改。

---

## 0. 当前目标

目标只有一个：

**修复“当前批首次晋级对象，没有把支撑晋级的累计有效数据带进 Step5”的问题。**

这不是标签调参问题，也不是全局原始数据缺失问题。

本轮要求：

1. 先建立真实数据黄金样本
2. 再做小样本 SQL 验证
3. 再做性能优化
4. 再做 batch1-7 工程化验证
5. 最后才正式完整重跑

### 0.1 batch 与日期映射

本任务默认使用下面这个映射，不要自行猜测：

| batch_id | 日期 |
|----------|------|
| 1 | 2025-12-01 |
| 2 | 2025-12-02 |
| 3 | 2025-12-03 |
| 4 | 2025-12-04 |
| 5 | 2025-12-05 |
| 6 | 2025-12-06 |
| 7 | 2025-12-07 |

---

## 1. 先做环境确认

开始前必须先检查：

1. 是否有残留重跑进程：
- `run_step1_step25_pipelined_temp.py`
- `run_daily_increment_batch_loop.py`
- `--consumer`

2. 是否有数据库长 SQL / 卡死查询：
- 连接 `ip_loc2`
- 查询 `pg_stat_activity`
- 只清理明显的分析类残留查询，不要误杀当前业务主跑链路

数据库连接默认使用：

```text
postgresql://postgres:123456@192.168.200.217:5433/ip_loc2
```

3. 检查 `snapshot_seed_records` 是否存在，以及它当前按 batch 的记录数：
- 这是上一轮修复尝试新增的桥接表
- 上一轮修复尝试中已创建过该表，但它可能因 reset 脚本被清理，因此新会话仍需先用 SQL 确认
- 若不存在，要明确记录
- 若存在，要统计 `batch_id -> row_count`

推荐 SQL：

```sql
SELECT to_regclass('rebuild5.snapshot_seed_records');

SELECT batch_id, COUNT(*)
FROM rebuild5.snapshot_seed_records
GROUP BY batch_id
ORDER BY batch_id;
```

如果有残留，先汇报，再清理。

---

## 2. 必读文档

必须按顺序先读这些文档，读完再动代码：

1. `rebuild5/docs/02_基础画像.md`
2. `rebuild5/docs/03_流式质量评估.md`
3. `rebuild5/docs/05_画像维护.md`
4. `rebuild5/docs/处理流程总览.md`
5. `rebuild5/docs/runbook_v5.md`
6. `rebuild5/docs/gps研究/数据错误问题.md`
7. `rebuild5/docs/gps研究/Step5数据桥问题_复核指引.md`

阅读目标：

- 明确 Step2 Path A / Path B 的设计边界
- 明确 Step3 只负责候选域晋级
- 明确 Step5 维护事实层来自 Step4
- 明确本次要补的是“当前批首次晋级对象 -> Step5 维护事实层”的 bridge

---

## 3. 明确当前已知事实（本节不执行 SQL，执行统一放到第 4 节）

本节只读，不执行 SQL。
所有 SQL 执行统一放到第 4 节黄金样本阶段。

上一轮会话已经确认以下事实，请新会话先复核，不要盲信：

1. `608244101` 在 `batch2` 的 `trusted_snapshot_cell` 中：
- `lifecycle_state = qualified`
- `independent_obs = 18`

2. 这个 `18` 不是假的，它来自前两天累计证据。

3. 当前 bridge 实现虽然已经把一部分“当前批新晋级对象”的数据送进了 Step5，
但只带了**当前批**数据，没有带“支撑晋级的累计候选证据”。

4. 因此当前修复还不完整。

新会话必须先复核这些点，再继续。

### 3.1 第 4 节将执行的 SQL（此处仅供预览，暂不执行）

不要只口头复核，第 4 节阶段至少会执行下面这些 SQL。
⚠️ 本节只预览 SQL，不在这里执行。真正执行统一放到第 4 节。

```sql
-- 608244101 在 Step 3 / snapshot 中的首次晋级事实
SELECT batch_id, lifecycle_state, independent_obs, distinct_dev_id, active_days
FROM rebuild5.trusted_snapshot_cell
WHERE cell_id = 608244101
ORDER BY batch_id;

-- 608244101 在 Step5 维护事实层中的记录
SELECT batch_id, COUNT(*) AS rows
FROM rebuild5.enriched_records
WHERE cell_id = 608244101
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, COUNT(*) AS rows
FROM rebuild5.snapshot_seed_records
WHERE cell_id = 608244101
GROUP BY batch_id
ORDER BY batch_id;

SELECT batch_id, source_type, COUNT(*) AS rows
FROM rebuild5.cell_sliding_window
WHERE cell_id = 608244101
GROUP BY batch_id, source_type
ORDER BY batch_id, source_type;
```

说明：
- `trusted_snapshot_cell`、`enriched_records`、`snapshot_seed_records`、`cell_sliding_window` 都是真实数据库表，不是代码概念。
- 第 3 节的 `608244101` 复核统一合并到第 4 节黄金样本阶段执行，不要重复做两遍。

---

## 4. 第一阶段：建立真实数据黄金样本

### 4.1 原则

不要先改代码。

先从当前真实数据里找“不同批次首次晋级的 cell”作为黄金样本。

至少覆盖：

1. `batch2` 首次晋级样本
2. `batch3` 首次晋级样本
3. 更晚批次首次晋级样本（优先 `batch4` 或 `batch5`）

`608244101` 必查。

### 4.1.1 发现首次晋级样本的 SQL

不要凭感觉选样本，先用 SQL 找出不同批次首次晋级的 cell。

示例：

```sql
-- 找 batch2 中首次晋级的 cell
SELECT cell_id, batch_id, lifecycle_state, independent_obs
FROM rebuild5.trusted_snapshot_cell
WHERE batch_id = 2
  AND lifecycle_state IN ('qualified', 'excellent')
  AND cell_id NOT IN (
    SELECT cell_id
    FROM rebuild5.trusted_snapshot_cell
    WHERE batch_id = 1
      AND lifecycle_state IN ('qualified', 'excellent')
  )
LIMIT 5;

-- 找 batch3 中首次晋级的 cell
SELECT cell_id, batch_id, lifecycle_state, independent_obs
FROM rebuild5.trusted_snapshot_cell
WHERE batch_id = 3
  AND lifecycle_state IN ('qualified', 'excellent')
  AND cell_id NOT IN (
    SELECT cell_id
    FROM rebuild5.trusted_snapshot_cell
    WHERE batch_id IN (1, 2)
      AND lifecycle_state IN ('qualified', 'excellent')
  )
LIMIT 5;
```

执行要求：

- 从 `batch2`、`batch3`、更晚批次（若当前库已有）各选 `3-5` 个首次晋级 cell
- 再加上 `608244101`
- 组成黄金样本集

### 4.2 每个黄金样本都要核对

对每个样本，都要查：

1. Step 3 首次晋级结果
- `trusted_snapshot_cell`
- `lifecycle_state`
- `independent_obs`
- `distinct_dev_id`
- `active_days`

2. 晋级所依赖的累计原始/结构化证据
- `raw_gps`
- `etl_cleaned`
- 按天分布
- 分钟观测数
- 设备数

查询要求：

- 必须带日期 / 批次边界
- 不要对 `raw_gps` / `etl_cleaned` 做无条件全表扫描

示例模板（需按样本实际批次替换）：

```sql
-- etl_cleaned 按天结构化事实
SELECT DATE(event_time_std) AS d,
       COUNT(*) AS rows,
       COUNT(DISTINCT COALESCE(NULLIF(dev_id,''), record_id)) AS devs,
       COUNT(DISTINCT date_trunc('minute', event_time_std)) AS minute_obs
FROM rebuild5.etl_cleaned
WHERE cell_id = :cell_id
  AND DATE(event_time_std) <= :first_qualified_day
GROUP BY 1
ORDER BY 1;

-- raw_gps 原始事实（建议先通过 record_id 回连，避免粗暴扫描）
WITH cell_records AS (
  SELECT DISTINCT record_id
  FROM rebuild5.etl_cleaned
  WHERE cell_id = :cell_id
    AND DATE(event_time_std) <= :first_qualified_day
)
SELECT DATE(r.ts::timestamptz) AS d, COUNT(*) AS raw_rows
FROM rebuild5.raw_gps r
JOIN cell_records c
  -- 注意：\"记录数唯一标识\" 是当前 raw_gps 的真实中文列名
  -- 若新会话环境中列名不同，先检查 raw_gps schema 再替换
  ON c.record_id = r.\"记录数唯一标识\"
GROUP BY 1
ORDER BY 1;
```

3. Step5 维护事实层现在拿到的内容
- `enriched_records`
- `snapshot_seed_records`（注意：这是上一轮修复尝试引入的新表，不是历史原生表，需先确认它是否存在、是否仍被消费）
- `cell_sliding_window`

### 4.3 这一阶段要回答的问题

对每个样本，必须明确回答：

1. 它在首次晋级时，累计证据来自哪些天？
2. 设计上 Step5 在首次发布批次应该拿到哪些数据？
3. 当前实现里 Step5 实际拿到了哪些？
4. 请验证并给出 SQL 证据：
- 是否确实是 **bridge 逻辑缺失**
- 而不是历史数据缺失

---

## 5. 第二阶段：小样本工程化 SQL 验证

在黄金样本明确之后，不要直接全量跑。

必须先做“小样本工程化验证流程”：

1. 只取少量目标 cell 相关数据
2. 覆盖：
- batch2 首次晋级样本
- batch3 首次晋级样本
- 更晚批次首次晋级样本
3. 用小样本反复验证 bridge SQL
4. 直到确认：
- Step5 拿到的是**累计候选证据**
- 不是只拿当前批

### 这一阶段禁止的事

- 不要直接跑 7 天全量
- 不要先调标签算法
- 不要把重心放到 UI 或统计展示

---

## 6. 第三阶段：性能优化

只有在 bridge 逻辑正确后，才做性能优化。

必须遵守：

1. 把重 SQL 拆阶段
2. 每阶段物化中间表
3. 必要索引提前建好
4. 避免窗口级全表重复扫描
5. 优先按 `batch / cell key` 裁剪
6. 若能提前物化“候选晋级 cell + 累计候选证据”，不要临时超大 JOIN
7. 任何已经证明会卡死的 SQL，都不能原样带进正式重跑

物化中间表约束：

- 只允许建在 `rebuild5` schema 下
- 中间表命名前缀统一使用：`rebuild5._tmp_bridge_`
- 在第 7 阶段工程化验证结束前，默认把这些表视为临时物化表
- 在最终方案里必须明确：
  - 哪些表只是验证期临时表，跑完即清理
  - 哪些表需要升级为持久表（如最终确定保留的 bridge 事实表）

并且在第 11 节输出要求里，必须包含一个**临时表清单**：

- 表名
- 所属阶段
- 完整重跑后是否应 DROP
- 由脚本自动清理还是人工执行

目标不是“漂亮”，而是：

**确保 batch1-7 能稳定跑完，不再出现十几个小时卡死。**

---

## 7. 第四阶段：batch1-7 工程化验证

在正式完整重跑前，先验证：

1. batch1-7 都能顺序跑完
2. bridge 数据是对的
3. 没有复杂 SQL 卡死
4. 索引和物化足够支撑

合格标准至少包含：

1. 对每个黄金样本（以第 4 节最终确认的清单为准）：
- 在其首次晋级 batch，Step5 事实层拿到的不是“仅当前批记录”
- 而是“支撑本次晋级的累计候选证据”

2. 对 batch1-7：
- 每个 batch 的 Step2/3/4/5 都能顺序完成
- 不出现长时间卡死 SQL
- `snapshot_seed_records` / `cell_sliding_window` 的批次记录数与黄金样本判断一致

注意：

Step1 七天之前已经确认是好的。依据：
- 之前的完整重跑中 `step1_run_stats` 已达到 7 条
- 7 个 `step1_stage_ready` 都已经出现过

因此重点放在：

- Step2
- Step3
- Step4
- Step5

如果你在复核过程中发现 Step1 也有异常迹象：
- 先汇报
- 不要自行扩大范围去重跑 Step1

---

## 8. 第五阶段：最后才正式完整重跑

只有前四阶段全部通过后，才开始正式完整重跑。

如果需要正式重跑，优先只重跑：

- Step2
- Step3
- Step4
- Step5

不要默认重新动 Step1。

---

## 9. 当前代码重点检查文件

新会话必须优先检查这些文件，不要直接沿用上一轮结论：

- `rebuild5/backend/app/profile/pipeline.py`
- `rebuild5/backend/app/evaluation/pipeline.py`
- `rebuild5/backend/app/enrichment/pipeline.py`
- `rebuild5/backend/app/enrichment/schema.py`
- `rebuild5/backend/app/maintenance/window.py`
- `rebuild5/backend/app/maintenance/publish_cell.py`
- `rebuild5/backend/app/maintenance/label_engine.py`
- `rebuild5/backend/app/maintenance/pipeline.py`
- `rebuild5/scripts/run_daily_increment_batch_loop.py`
- `rebuild5/scripts/run_step1_step25_pipelined_temp.py`
- `rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql`
- `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql`

---

## 10. 当前桥接实现的已知状态

上一轮会话已经做过一次 bridge 修复尝试，但它**只解决了一半**：

### 已做到

- 新增 `snapshot_seed_records`
- Step5 的 `refresh_sliding_window()` 已能同时吃：
  - `enriched_records`
  - `snapshot_seed_records`

### 未做到

- 当前 `snapshot_seed_records` 只带“当前批新晋级对象的当前批数据”
- 没有把“支撑晋级的累计候选证据”一起带进 Step5

### 10.1 当前实现错误形态（伪代码）

当前实现近似于：

```sql
INSERT INTO snapshot_seed_records
SELECT *
FROM step2_batch_input e
JOIN trusted_snapshot_cell s
  ON s.batch_id = :current_batch
 AND s.cell_id = e.cell_id
WHERE e.batch_id = :current_batch;
```

它的问题是：

- 只拿到了 `batch=t` 当前批的记录
- 没有把该 cell 在 `t` 批晋级时依赖的累计候选证据带进来

### 10.2 目标实现应满足的语义（伪代码）

```sql
-- ⚠️ 以下是语义伪代码
-- candidate_evidence_history 与 first_qualified_batch 都是语义占位符
-- 不是真实表名/列名
-- 新会话必须先在第 4 节确认真实映射关系后再落地
```

经上一轮会话讨论，本次修复目标**已明确选择方案 2**：

- 不是“只带当前批”
- 而是“带入支撑晋级的累计候选证据”

如果在第 4 节核实后发现方案 2 有重大风险，必须先汇报，再继续。

目标不是“只取当前批”，而是：

```sql
INSERT INTO snapshot_seed_records
SELECT *
FROM candidate_evidence_history h
WHERE h.cell_id IN (
  SELECT cell_id
  FROM trusted_snapshot_cell
  WHERE batch_id = :current_batch
    AND lifecycle_state IN ('qualified', 'excellent')
    AND first_qualified_batch = :current_batch
);
```

说明：

- `candidate_evidence_history` 是**语义名称**，不是当前库里已经存在的真实表名。
- 新会话必须先根据现有 schema/管道判断：
  - 它应该落在什么真实表上
  - 是 `raw_gps` / `etl_cleaned` / 其它中间表 / 新增物化表
- 不要假设数据库里已经有一张同名表。
- `first_qualified_batch` 也是**语义字段**，不表示数据库里现在已经有这个真实列名。
  新会话必须先在第 3 节和第 4 节的复核过程中确认：
  - 真实列名是什么
  - 或是否需要通过窗口函数 / 中间表先计算“首次晋级批次”

追踪建议：

- 先在第 4 节黄金样本 SQL 中，确认 `608244101` 在 `batch1/2` 期间
  “候选阶段的累计证据”实际存在于哪张真实表
- 再回到这里决定 `candidate_evidence_history` 应映射到：
  - 现有真实表
  - 现有中间表
  - 或新建的物化 bridge 中间表

这里的关键不是表名，而是语义：

- 对于 `batch=t` 首次晋级的 cell
- Step5 应拿到的是**支撑本次晋级的累计候选证据**
- 而不是只拿 `batch=t` 当前批的一部分记录

因此：

> 现在不能直接继续全量重跑。

必须先把 bridge 修正成“累计候选证据 bridge”。

---

## 11. 输出要求

第一轮输出不要改代码，先输出：

1. 你读完设计文档后的理解
2. 黄金样本候选清单
3. `608244101` 的完整复核结果
4. 其它 batch 首次晋级样本的复核结果
5. 当前 bridge 实现和设计差异
6. 你的改法方案（只描述逻辑与依赖的真实表/字段，不写代码）
   - 所有改动只能涉及第 9 节列出的文件范围
   - 若需要超出第 9 节文件清单，必须先说明理由并等待确认
7. 临时表清单（哪些保留、哪些验证后清理、由谁清理）

只有这些确认后，才进入代码修改阶段。
