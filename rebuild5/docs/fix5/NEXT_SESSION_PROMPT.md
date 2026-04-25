# OptiNet rebuild5 Citus 迁移 · fix5 诊断(Claude 接续对话)

> 你是上游 Claude 接续实例。本消息自包含,读完就能干活。不用读其他上下文历史。

---

## 1. 定位

- 项目:OptiNet-main / 阶段:rebuild5 / 子阶段:**fix5 质量诊断**
- 本轮角色:**诊断型**,不改代码、不重跑 pipeline、不 commit
- 产出:`rebuild5/docs/fix5/01_quality_diagnosis.md`(markdown 报告 + 代码位置清单)
- 启动后先读仓库根目录 `AGENTS.md`,然后执行本 prompt。A 阶段不需要 Web/UI 登录账号或 SSH 账号。

---

## 2. 背景:Gate 3 跑完了,但数据质量严重异常

前一位 Claude 带着一位 agent 跑完了 Gate 3(7 批 Citus 全量 rerun)。
Agent 产出 `rb5.trusted_cell_library` batch_id=1..7,但 MCP 校验发现 **4 个铁证级异常**:

### 异常 ①:sliding_window 在 batch 5 后停止累积

| batch | cell_sliding_window.rows | distinct_cells |
|---|---|---|
| 5 | 4,318,487 | 340,453 |
| 6 | **4,351,230** | **340,453** ← 不变 |
| 7 | **4,351,230** | **340,453** ← 不变 |

batch 6 和 7 `cell_sliding_window` 内容**完全一样**,distinct_cells 从 batch 5 就锁死。

### 异常 ②:k_eff=2 的 6 个 cell 跨批 3/5/7 永远是同一批

batch 3/5/7 的 `k_eff=2` 永远是:
`4134817 / 4170783 / 21479426 / 578838537 / 1693970690 / 12978372614`

候选池(`p90 >= 1300m`)从 batch 3 的 2,223 增长到 batch 7 的 6,452(3 倍),
**但 DBSCAN 产出 k_eff=2 始终 6 个、k_eff≥3 永远 0**。
转化率对比:本地 batch 7 ~27%,Citus 0.1%,**差 200 倍**。

### 异常 ③:sliding_window 混入 2023/2024 年垃圾时间戳

batch 5-7 的 `min(event_time_std) = 2023-12-29`、`n_days = 46`。
实际数据应该只有 **2025-12-01~12-07 共 7 天**,`WINDOW_RETENTION_DAYS` 没 trim 掉远古数据。

### 异常 ④:trusted_cell_library 多质心链路全崩

| drift_pattern | 本地 batch 7 | **Citus batch 7** |
|---|---|---|
| stable | 337,480 | 320,575 |
| insufficient | 2,700 | **26,463** ← 10 倍 |
| large_coverage | 745 | **0** |
| dual_cluster | 442 | **0** |
| uncertain | 82 | **0** |
| oversize_single / migration | 7 / 4 | **0 / 0** |

---

## 3. 嫌疑代码文件(agent 在 Gate 3 改过)

- `rebuild5/backend/app/enrichment/pipeline.py`(改了 snapshot_seed_records 跨批桥接去重)
- `rebuild5/backend/app/maintenance/window.py`(`refresh_sliding_window` 累积/trim 逻辑,嫌疑最大)
- `rebuild5/backend/app/maintenance/label_engine.py`(候选池筛选,postgis fallback 改过一次又切回 DBSCAN)
- `rebuild5/scripts/run_citus_serial_batches.py`(runner 脚本,辅助)
- `rebuild5/scripts/gate3_cleanup.sql`(清理脚本,辅助)

**串行协作**:B 阶段(代码审计 agent)在你完成后接手。你的 `01_quality_diagnosis.md`
产出 = B 阶段的起点(B agent 会基于 01 精准判断哪些代码改动是 bug 相关、哪些无关)。
**所以 01 一定要把"具体哪些代码位置可疑"明确写清楚**,方便 B 精准回滚。

---

## 4. 环境(硬信息)

仓库:       `/Users/yangcongan/cursor/WangYou_Data`

旧库(PG17 本地,完整基线数据,只读):
- Host:     192.168.200.217
- Port:     5433
- User / Password: postgres / 123456
- Database: ip_loc2
- DSN:      `postgres://postgres:123456@192.168.200.217:5433/ip_loc2`
- MCP:      **`mcp__PG17__execute_sql`**
- 核心表:`rebuild5.trusted_cell_library` 341,460 行 batch 7,分类分布完整
  (stable 337,480 / insufficient 2,700 / large_coverage 745 / dual_cluster 442 / uncertain 82 / oversize_single 7 / migration 4)

新集群(Citus,Gate 3 产出):
- Host:     192.168.200.217
- Port:     5488
- User / Password: postgres / 123456
- Database: yangca
- DSN:      `postgres://postgres:123456@192.168.200.217:5488/yangca`
- MCP:      **`mcp__PG_Citus__execute_sql`**
- 核心表:`rb5.trusted_cell_library` batch 1-7 共 1,777,854 行
- 控制面:`rb5_bench.notes` / `rb5_bench.report`(agent 历史)
- 诊断历史:`claude_diag.*`(上一轮诊断 simple CASE bug 留下的测试表)

MCP 激活:初次使用每个 MCP 都要先 `ToolSearch` 载入 schema
```
ToolSearch select:mcp__PG17__execute_sql
ToolSearch select:mcp__PG_Citus__execute_sql
```

如果 MCP 不可用,可用 `psql` 只读查询兜底;写完报告后只允许插入 §7 的完工 note:
```bash
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca
```

---

## 5. 诊断方法(关键:双库对比)

核心思路:**PG17 的 batch 7 是黄金基线**(本地代码产生,逻辑正确)。
Citus 的 batch N **每一步**都应该能和 PG17 对上,对不上的地方就是 bug 位置。

### 诊断维度(至少覆盖这 6 条)

| # | PG17 查询 | Citus 查询 | 对照要点 |
|---|---|---|---|
| 1 | drift_pattern 分布 batch 7 | drift_pattern 分布 batch 7 | 多质心类 745/442/82 vs 0/0/0 |
| 2 | `trusted_cell_library.p90_radius_m` 分布 | 同 | Citus 候选池对比 |
| 3 | `label_results` 的 k_raw/k_eff 分布 | 同 | Citus 只出 k_eff≤2 |
| 4 | `cell_sliding_window` distinct cell / n_days | 同 | **Citus batch 6/7 完全相同 - 核查 PG17 本地是不是同样** |
| 5 | 具体一个本地有 dual_cluster 的 cell,看 Citus 上这 cell 的 sliding_window、label_results 和 trusted_cell_library 产出,逐层对 | — | 找**从什么节点开始偏离** |
| 6 | Citus 上 sliding_window 混入的 2023/2024 时间戳 row,回到 raw_gps_full_backup 反查 | PG17 原表 raw_gps_full_backup 是否也有这批时间戳 | **判断是上游脏数据还是 Citus trim 没生效** |

### 快速上手 SQL(起步用)

```sql
-- PG17:黄金基线
-- drift_pattern 分布
SELECT drift_pattern, COUNT(*) FROM rebuild5.trusted_cell_library WHERE batch_id=7 GROUP BY drift_pattern ORDER BY 2 DESC;
-- k_eff 分布
SELECT COALESCE(k_eff,-1), COUNT(*) FROM rebuild5.label_results WHERE batch_id=7 GROUP BY 1 ORDER BY 1 DESC;
-- sliding_window 覆盖天数
SELECT batch_id, COUNT(DISTINCT DATE(event_time_std)) AS n_days,
       MIN(event_time_std)::date, MAX(event_time_std)::date
FROM rebuild5.cell_sliding_window WHERE batch_id BETWEEN 5 AND 7 GROUP BY 1 ORDER BY 1;

-- Citus(yangca):异常验证
SELECT drift_pattern, COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id=7 GROUP BY drift_pattern ORDER BY 2 DESC;
SELECT COALESCE(k_eff,-1), COUNT(*) FROM rb5.label_results WHERE batch_id=7 GROUP BY 1 ORDER BY 1 DESC;
SELECT batch_id, COUNT(DISTINCT DATE(event_time_std)), MIN(event_time_std)::date, MAX(event_time_std)::date
FROM rb5.cell_sliding_window WHERE batch_id BETWEEN 5 AND 7 GROUP BY 1 ORDER BY 1;
```

### 建议深挖方向(按优先级)

1. **sliding_window 锁死根因**:batch 6/7 为什么不 refresh?看 `maintenance/window.py::refresh_sliding_window` 在 Citus 环境的执行。**最可疑**。
2. **label_engine 候选 → DBSCAN 产出率降 200 倍**:`_label_input_points` 是不是没生成,或者 ST_ClusterDBSCAN 在 distributed 表上 OVER (PARTITION BY cell_id) 跨 shard 失效?
3. **snapshot_seed_records 跨批桥接去重改动**(note #46):看 agent 改动是不是改变了 enriched_records 每批的语义。
4. **2023 年时间戳污染**:是上游 raw_gps_full_backup 就有,还是 Citus 层 trim 失效?

### 不要做的事

- ❌ 不改任何代码(fix5 C 阶段再改)
- ❌ 不跑 pipeline
- ❌ 不 DROP 任何 rb5.* 表(诊断要用)
- ❌ 不 commit / push
- ❌ 不让 agent 开始优化前自己提前给方向(等诊断完整再说)

### C 阶段范围已确定(2026-04-24 用户拍板)

用户已明确:**不做结构大改**(不改分布键、不重写 sliding_window / label_engine 数据模型)。
C 阶段只做:

1. 修 bug(基于你的诊断定位具体根因)
2. `citus.max_intermediate_result_size` **全局 ALTER SYSTEM 调大**(不要 session SET)
3. Step 1 和 Step 2-5 **pipelined 并行**(恢复 `run_step1_step25_pipelined_temp.py` 模式)

**不做**结构重构、不改分布键、不重写 label_engine 候选池模型。

**对你诊断的影响**:§5 "深挖方向" 里你只需要定位 bug 根因和提具体行级修复。
**不用展开**"要不要统一 cell_id 分布""要不要按时间分区"之类的结构级建议 —
那些留到未来新项目重新规划。聚焦:**怎么让 Citus batch 7 分布对齐 PG17 batch 7**。

---

## 6. 产出

文件:`/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/fix5/01_quality_diagnosis.md`

结构建议:

```markdown
# fix5 / 01 质量诊断

## 0. TL;DR
(3-5 行核心结论)

## 1. PG17 vs Citus 关键指标对比
(6 维度表格,每维一行双库对比)

## 2. 异常根因定位
### 2.1 sliding_window 断档
代码位置:window.py:XX ...
PG17 行为:...
Citus 行为:...
根因假说:...
证据:(SQL + 结果)

### 2.2 label_engine 候选池产出率骤降
...

### 2.3 snapshot_seed_records 跨批污染
...

### 2.4 远古时间戳混入
...

## 3. 给 C 阶段 agent 的具体修复清单
- 文件:rebuild5/backend/app/maintenance/window.py
  - 行 XX-YY:<改动描述>
  - 原因:<为什么>
  - 验证方法:<怎么证实修好了>
- ...

## 4. 重跑策略建议
- 是否要 reset 所有 rb5.* 重来?还是从某个 batch 重来?
- ...
```

---

## 7. 完工标志

1. `rebuild5/docs/fix5/01_quality_diagnosis.md` 写完
2. 在 `rb5_bench.notes` 插一条:
   ```sql
   INSERT INTO rb5_bench.notes (topic, severity, body) VALUES (
     'fix5_diagnosis_complete', 'info',
     '01_quality_diagnosis.md 已输出,agent 可据此进入 C 阶段修复。'
   );
   ```

---

## 8. 上下文节约提示

这轮诊断除 §7 的 `rb5_bench.notes` 完工信号外,其余都应是**只读查询**。别把 SQL 结果全贴进对话 — 用 MCP 查完把结论写到文件,让 md 成为"记忆载体"。
遇到大 EXPLAIN 输出,截取关键节点贴到 md,别往对话里灌。

**不要开 agent / subagent**,本轮 Claude 单独做诊断就够。
