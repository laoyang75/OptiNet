
你是一个 PostgreSQL 性能评估与 SQL 调优 agent。现在需要对一段 Postgres 15.13 的长耗时 SQL（Step30：`CREATE TABLE ... AS WITH ...`，包含多层 CTE、`percentile_cont` 中位数/P90 计算、距离计算、最后输出 `Y_codex_Layer3_Step30_Master_BS_Library` 和统计表 `Y_codex_Layer3_Step30_Gps_Level_Stats`）做**可复现的性能评估与改动建议**。

### 关键约束（必须遵守）

1. 你必须先完成评估与测试，并把结果**先汇报给我**（用户），由我决定是否修改 SQL 或改执行方式。
2. 你不得直接在生产环境做不可逆改动（比如改全局参数、删除业务表、改业务表结构）。若需要改动，先提出方案并等待我确认。
3. 评估优先在“冒烟/分片/只读方式”进行；如需创建临时/UNLOGGED/临时表用于测试，必须说明用途与清理方式。
4. 输出必须包含：证据（EXPLAIN/统计/观察）、结论、风险、推荐选项（不改 SQL / 小改 SQL / 改执行编排），并给出我可选择的“决策建议”。

---

# A. 评估目标

请回答并用证据支撑以下问题：

1. 这条 Step30 SQL 为什么没有用到并行 worker？（确认是否确实串行）
2. 性能瓶颈主要在什么节点/CTE？（percentile_cont 排序、CTE 重复执行、JOIN/Hash、temp spill、或锁等待等）
3. 加 `CTE MATERIALIZED` 是否能明显减少重复计算并提速？（不改变口径）
4. 若 SQL 结构本身很难自动并行，采用“按 `mod(bs_id, N)` 分片，多会话并行 INSERT”的执行编排是否可行、能否显著缩短墙钟时间、且不改变口径？
5. 给出明确建议：是否值得修改 SQL（例如 MATERIALIZED、拆中间表、参数调整）或仅调整执行方式（分片并行/串行稳定跑）。

---

# B. 环境背景（你可引用）

* PostgreSQL 15.13，硬件：40 核、约 264GB RAM、SSD，当前系统负载低
* 现象：Step30 查询在跑时**单核满载**，系统 CPU 大量 idle；查询会话 `pg_stat_activity` 未看到 `parallel worker`
* Step30 中包含多处 `percentile_cont(..) WITHIN GROUP (ORDER BY ..)`

---

# C. 执行步骤（必须按顺序做，并收集证据）

## C1. 运行态验证（无需改 SQL）

在 Step30 正在跑或复现跑的时候，执行并记录输出：

1. 该查询 leader/worker 情况（是否有并行 worker）

```sql
SELECT pid, leader_pid, backend_type, state,
       wait_event_type, wait_event,
       now()-query_start AS running_for
FROM pg_stat_activity
WHERE pid = <STEP30_PID> OR leader_pid = <STEP30_PID>
ORDER BY backend_type, pid;
```

2. temp spill 证据（前后两次，间隔 1-2 分钟，对比 temp_bytes 增量）

```sql
SELECT temp_files, temp_bytes
FROM pg_stat_database
WHERE datname = current_database();
```

3. 如果可用，查 CTAS 进度

```sql
SELECT * FROM pg_stat_progress_create_table;
```

**输出要求**：把这三组结果截图或原文贴在报告里，并给出解读：是否锁等待、是否大量 temp、是否纯串行。

---

## C2. 计划与瓶颈定位（冒烟/分片方式，避免全量）

在不改变口径的前提下，构造一个小样本执行（任选一种，优先 1 或 2）：

* 方式 1：启用 Step30 内 params 的 `is_smoke=true`（只跑单日/单运营商）
* 方式 2：在最终 `FROM bucket_base b ...` 处加 `WHERE mod(b.bs_id, 16)=0`（只跑 1/16 分片）
* 方式 3：两者同时用（最小）

对小样本执行：

* `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)`（如果耗时太长，可先只 `EXPLAIN` 再决定是否 ANALYZE）
* 重点查看：`Workers Planned/Launched`、Sort/Hash/CTE Scan、Buffers、temp read/write、最耗时节点

**输出要求**：报告中列出最耗时的 3-5 个 plan 节点（含耗时、rows、buffers、temp），并判断瓶颈类型（排序/分位数、CTE 重算、JOIN、I/O spill）。

---

## C3. MATERIALIZED 评估（小改 SQL，不改口径）

在 **小样本** 上做对照实验（必须前后对比，其他参数不变）：

* 版本 A：原始 SQL（小样本）
* 版本 B：仅对以下 CTE 加 `AS MATERIALIZED`（或你根据计划证据选择等价的“被多次引用且昂贵”的 CTE）

  * `bucket_universe`
  * `cell_points`
  * `bucket_base`

对比：

* 执行时间
* temp_bytes 增量
* plan 是否减少重复扫描/重复聚合
* CPU 使用变化（如你能采集）

**输出要求**：用表格列出 A vs B 的关键指标，并给出结论：是否建议在全量上采用 MATERIALIZED（含风险：磁盘占用/一次性物化开销）。

---

## C4. “手工分片并行执行”可行性评估（不改口径，改执行编排）

目标：验证自动并行不足时，是否可通过多会话并行分片，把 1 核扩展到 N 核，缩短墙钟时间。

在 **不影响生产** 的前提下，优先在测试 schema 或临时表进行。步骤：

1. 先只跑 1/16 分片，记录单片耗时 T1（用 `mod(b.bs_id,16)=k`）
2. 开 4 或 8 个会话并行跑不同 k 分片（仅小样本/单日更好），记录并行墙钟时间 Tp、CPU 利用率变化
3. 校验不重不漏：并行写入结果行数 = 分片逐一汇总行数；并检查主键/桶键（`wuli_fentong_bs_key`）无重复冲突
4. 如果需要创建“空壳目标表 + INSERT”，必须说明如何创建与清理

**输出要求**：报告中给出“并行分片吞吐提升倍数”（T1 与 Tp 的对比），以及口径正确性校验结果（行数、桶键唯一性抽样检查）。

---

# D. 最终报告格式（必须按此结构输出）

1. **结论摘要（给决策用）**：一句话说明是否需要改 SQL/改执行方式
2. **证据**：C1~C4 的关键输出与解读
3. **根因判断**：并行缺失原因（例如 ordered-set aggregate/percentile_cont 限制、CTE 内联导致重复算、temp spill 等）
4. **可选方案（按侵入性排序）**：

   * 方案 0：不改 SQL，继续串行等待（适用条件/预计风险）
   * 方案 1：小改 SQL（MATERIALIZED）
   * 方案 2：改执行编排（按 bs_id 分片并行）
   * 方案 3：结构性改造（落盘中间表/近似分位数替代 percentile_cont 等）
5. **风险与回滚**：每个方案的风险、如何回滚/恢复
6. **建议我如何选择**：结合你测到的数据量级，给出推荐优先级，但最终由我决定

---

# E. 沟通要求

完成上述评估后，你必须先把报告发给我，并明确询问我选择哪一个方案再执行任何涉及修改 SQL/执行方式的下一步动作。

