# Prompt: rebuild5 按天增量语义重对齐

你在 `/Users/yangcongan/cursor/WangYou_Data` 继续 `rebuild5`。

## 0. 当前任务目标

当前目标不是继续沿用“固定全量数据多轮重放”的验证语义，而是**回到正确的产品语义**：

- `Step 1` 首次全量初始化
- 后续按天导入新增原始数据
- `Step 2 ~ Step 5` 以“当天新增数据”为当前批输入
- 只读取上一版已发布正式库 / 冻结快照
- 按天流式维护可信库

## 1. 先阅读这些文件

这些文件是当前事实基线，必须先阅读：

- `rebuild5/docs/human_guide/00_系统全貌.md`
- `rebuild5/docs/human_guide/06_核心约束与设计原则.md`
- `rebuild5/docs/00_全局约定.md`
- `rebuild5/docs/02_基础画像.md`
- `rebuild5/docs/03_流式质量评估.md`
- `rebuild5/docs/04_知识补数.md`
- `rebuild5/docs/05_画像维护.md`
- `rebuild5/docs/09_控制操作_初始化重算与回归.md`
- `rebuild5/scripts/runbook_beijing_7d_daily_standard.md`
- `rebuild5/scripts/runbook_beijing_7d_standard.md`

## 2. 已确认的结论

### 2.1 文档层

- `rebuild5/docs/human_guide/00_系统全貌.md` 没写错
- 它表达的是**产品级按天增量语义**
- 之前的问题不是系统全貌文档错，而是把“验证性重放 batch”误当成了“产品 daily batch”

### 2.2 已修订文档

以下文档已经修过：

- `rebuild5/docs/09_控制操作_初始化重算与回归.md`
  - 已明确区分：
    - 生产日批（标准语义）
    - 验证性重放（仅用于验证链路）
- `rebuild5/scripts/runbook_beijing_7d_daily_standard.md`
  - 当前**生产语义标准 runbook**
- `rebuild5/scripts/runbook_beijing_7d_standard.md`
  - 当前**验证性重放 runbook**

### 2.3 当前数据库状态

当前没有活跃任务。

当前已完成的批次：

- `batch1-6`
  - `step3/step4/step5` 均已完成

但要注意：

- 这些 `batch1-6` 是基于固定 `beijing_7d` 全量数据的**验证性重放结果**
- 它们**不能直接视为产品“按天增量”语义下的正式产物**

### 2.4 当前技术状态

已完成的关键实现修复，不要回滚：

- Step 2 donor 已透传到 `path_a_records`
- Step 2/3 读取 `collision_id_list` 已按上一版 batch 收紧
- Step 3 `step3_run_stats` 已按最终 `trusted_snapshot_*` 统计
- Step 5 `snapshot_version_prev` 已按 `< 当前 batch` 读取
- `publish_bs_library` 已通过 session 级 `enable_nestloop=off` 修正坏执行计划
- `cell_sliding_window` 写入并发已从 12 降到 4
- `enriched_records` 遇到 ENOSPC 时会自动降并发重试
- `build_path_a_records()` 已拆成分阶段中间表
- `run_standard_batch_loop.py` 已改为真实文件脚本，避免 `<stdin>` + multiprocessing 的 spawn 问题

### 2.5 日期索引现状（重要）

已经查过当前库：

- `rebuild5.etl_cleaned` 上**没有** `event_time_std` 相关索引
- `rebuild5.raw_gps` 上**没有**时间相关索引

这意味着：

- 如果接下来按天切分数据跑产品日批
- 日期过滤会缺少基本索引支撑
- 必须优先检查并补齐时间索引

## 3. 你接下来的任务顺序

### Step A: 确认当前产品语义下，现有 batch1-6 是否应废弃

你必须先明确回答：

- 现有 `batch1-6` 是否全部属于“验证性重放结果”
- 它们是否应该从产品语义角度视为无效产物
- 如果无效，应该清理到哪一层：
  - 只清 `Step 2 → Step 5`
  - 还是连 `Step 1` 也要重新组织为按天输入

这里不要拍脑袋，要基于文档与现有实现边界判断。

### Step B: 明确“按天增量”的实际执行方案

必须先回答清楚以下问题：

1. 当前 `beijing_7d` 数据如何映射成 `day1/day2/.../day7`
2. “当天新增数据”的切分基准字段是什么：
   - `etl_cleaned.event_time_std`
   - 或更早层的时间字段
3. Step 1 是否可以保留当前结果后按 `event_time_std` 切分
   - 还是必须重做更早层的按天接入

### Step C: 优先补日期索引

至少检查并评估以下索引是否要补：

```sql
CREATE INDEX IF NOT EXISTS idx_etl_cleaned_event_time_std
ON rebuild5.etl_cleaned (event_time_std);
```

如果按天切分需要在 `raw_gps` 层就做日期过滤，也要明确 `raw_gps` 上的时间索引方案。

注意：

- 不要只加索引，要解释为什么这个索引对应的是产品语义下的切分主键

### Step D: 在正确语义基础上重新修订 runbook

当前生产标准 runbook 已经存在，但你需要继续确认它是否足以支持真正的日批执行。

如果不足：

- 继续修 `runbook_beijing_7d_daily_standard.md`
- 不要再让验证性重放 runbook 混入生产语义

### Step E: 再决定是否清理现有结果

在语义和切分方案确认前，不要直接删。

一旦确认：

- 如果现有 `batch1-6` 与产品语义冲突
- 应先制定清理方案
- 然后再进入真正的按天日批初始化

## 4. 当前禁止事项

- 不要直接继续 `batch7` / `batch8`
- 不要再默认“7天数据应该跑到 batch7/8”
- 不要把验证性重放结果直接当成产品按天结果

## 5. 当前可复用的状态

- 当前没有活跃任务，可安全接手
- 当前代码的执行层修复是有效的，可作为后续按天语义对齐的实现基础
- 当前回归测试通过：

```bash
pytest -q rebuild5/tests/test_publish_bs_lac.py rebuild5/tests/test_pipeline_version_guards.py
```

## 6. 你输出时要先给出的结论

在开始修改代码/文档前，先给出：

1. 现有 `batch1-6` 是否应视为产品语义无效结果
2. 当前按天增量的切分主键应该是什么
3. 是否保留现有 `Step 1` 产物
4. 应补哪些日期索引
5. 生产标准 runbook 还需要改哪里

确认这 5 点后，再进入修改与执行。
