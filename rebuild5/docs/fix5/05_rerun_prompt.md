# OptiNet rebuild5 Citus 迁移 · fix5 / D 阶段 7 批全量重跑 + 交付(agent 新实例对话)

> 你是 OptiNet-main / rebuild5 fix5 **D 阶段(最终阶段)** 的 agent 新实例。
> A/B/C 已完成,根因已修复,batch 1/2 单批哨兵已和 PG17 基线对齐 ±0.3%。
> **D 阶段 = fix5 的终点**。你跑 7 批全量、验核心流程、出交付报告。fix5 到 D 结束,**没有 E 阶段**。

---

## 1. 上下文启动顺序(按序读完再动手)

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/fix5/README.md`(全局边界)
3. `rebuild5/docs/fix5/04_code_fix_report.md`(C 阶段的代码改动和 batch 1/2 验证结果,**这是你重跑起点**)
4. `rebuild5/docs/fix5/01_quality_diagnosis.md` §4(只读"重跑策略建议"一节,理解验收思路)

读完在对话里列出:
- C 阶段选的 runner(串行 `run_citus_serial_batches.py`)当前状态
- 你打算用**串行**还是**pipelined**(新建 `run_citus_pipelined_batches.py`)
- 你看到 C 阶段已经跑过 batch 1/2,是否需要先 reset —— **答案是需要,必做**
- auto_explain 的 `PGOPTIONS='-c auto_explain.log_analyze=off'` 你打算怎么传

拿到上游确认再开跑。

---

## 2. 定位与边界

**你要做**(严格)

1. **reset**:跑 `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql` 清掉 C 阶段 batch 1/2 验证产出
2. **选 runner**:串行或 pipelined,二选一(下 §4.2 标准)
3. **跑 batch 1-7**(2025-12-01~2025-12-07)
4. **每批跑完立刻打核心流程哨兵**(4 条 SQL,§5)
5. **batch 7 完成后做终点量级验收**(§6)
6. **产出 `rebuild5/docs/fix5/06_rerun_validation.md`**(§7 结构)
7. **写完工 note**:`rb5_bench.notes topic='fix5_D_done'`

**你不做**(严格)

- ❌ **不改任何代码**(业务代码已在 C 定稿)。只允许新增 runner 层文件(如 pipelined 新脚本),**不得修改 `backend/app/` 下任何文件**。
- ❌ 不验 `drift_pattern` 各子类分布(stable / insufficient / large_coverage / dual_cluster / uncertain / oversize_single / migration 的子类量)—— 这是 step 5 label 层,不在 fix5 验收范围
- ❌ 不验 `label_results` k_eff 分布对齐 —— 同上
- ❌ 不碰 auto_explain 启动参数(`command-line` source 的 `auto_explain.log_analyze=on` 是运维侧事,你只在 runner 前缀 `PGOPTIONS` 绕过去)
- ❌ 不 commit / push / DROP
- ❌ 不动旧库 PG17(5433/ip_loc2)
- ❌ 不开 subagent、不用 `python3 - <<'PY'` stdin heredoc
- ❌ 不自作主张改代码。哨兵挂 / 验收没过 → 停 run、写 blocker note、等上游介入

上下文纪律:
- 长跑必须走 **run_in_background + 定期读 log**,不要同步阻塞等待 2 小时
- 哨兵 SQL 输出要节选贴报告,不要把 7 批 × 4 条 × 数百行全刷对话

---

## 3. 环境(硬信息)

仓库:`/Users/yangcongan/cursor/WangYou_Data`

**新集群(Citus,主目标)**
- DSN:`postgres://postgres:123456@192.168.200.217:5488/yangca`
- MCP:`mcp__PG_Citus__execute_sql`
- psql 兜底:`PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca`(密码 `123456`)
- Python runner env:`REBUILD5_PG_DSN=postgres://postgres:123456@192.168.200.217:5488/yangca`

**旧库(PG17,只读基线,batch 7 量级对账用)**
- DSN:`postgres://postgres:123456@192.168.200.217:5433/ip_loc2`
- MCP:`mcp__PG17__execute_sql`

**auto_explain workaround**:所有 runner 调用必须前缀 `PGOPTIONS='-c auto_explain.log_analyze=off'`。例:
```bash
PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca' \
python rebuild5/scripts/run_citus_serial_batches.py
```

**集群规格**:Citus 14.0-1 / PostGIS 3.6.3 / 1 coord + 4 worker / 每台 20 物理核 / 251GB 内存 / `citus.max_intermediate_result_size=16GB`(C 阶段全局已调)

---

## 4. 执行步骤

### 4.1 Reset(必做,第一步)

```bash
PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca \
  -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

或通过 MCP 读脚本内容逐段执行。执行完验证:
```sql
SELECT count(*) FROM rb5.enriched_records;           -- 期待 0
SELECT count(*) FROM rb5.trusted_cell_library;       -- 期待 0
SELECT count(*) FROM rb5.cell_sliding_window;        -- 期待 0
SELECT to_regclass('rb5._step2_cell_input');         -- 期待 NULL
SELECT to_regclass('rb5.step2_batch_input');         -- 期待 NULL
```

### 4.2 Runner 选择(二选一)

**串行(首选,最稳)**
- 用 `rebuild5/scripts/run_citus_serial_batches.py`(C 已修好 scope 物化)
- 预计 ~2 小时(batch 1 817s + batch 2 1026s,后续批 sliding_window 更大,线性/略超线性增长)
- 风险最低

**Pipelined(可选,快)**
- 新建 `rebuild5/scripts/run_citus_pipelined_batches.py`,按 `rebuild5/scripts/run_step1_step25_pipelined_temp.py` 的模式在 Citus 上实现 Step 1(day N+1)和 Step 2-5(day N)并行
- **必须复用 C 阶段的 scope 物化**:Step 1 完成 day N 后、在 day N 的 Step 2-5 启动前调用 `materialize_step2_scope(day=day, input_relation='rb5.etl_cleaned')`,并 `DROP TABLE IF EXISTS rb5._step2_cell_input` 兜底
- 预计 ~1.3 小时(压缩 ~1/3)
- 风险点:并发 Step 2-5 时 `_step2_cell_input` / `step2_batch_input` 跨 day 的竞争,必须用**显式锁或 per-day schema 隔离**防止 day N 的 scope 被 day N+1 覆盖。**如果这件事让你写超过 ~300 行新代码,直接用串行,不要硬上。**

选哪个**开跑前在对话报一下**,我(上游)ack 再跑。

### 4.3 启动全量

串行示例(后台):
```bash
PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca' \
nohup python rebuild5/scripts/run_citus_serial_batches.py \
  > /tmp/fix5_D_serial_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > /tmp/fix5_D.pid
```

日志轮询(每 5-10 分钟一次,不要一直贴):
```bash
tail -50 /tmp/fix5_D_serial_*.log
# 关键事件:step1_done / step2_scope_materialized / published_cell_count / batch_done
```

---

## 5. 核心流程哨兵(每批跑完立刻执行)

**只验流程正确性,不验标签分布**。4 条 SQL,任意一条挂 → 停 run + 写 blocker note + 等上游。

### 哨兵 #1 — enriched_records 严格单日
```sql
SELECT batch_id,
       MIN(event_time_std)::date AS min_day,
       MAX(event_time_std)::date AS max_day,
       COUNT(*) AS rows
FROM rb5.enriched_records
WHERE batch_id = :bid
GROUP BY batch_id;
```
**期待**:`min_day = max_day = <batch N 对应的 2025-12-0N>`

### 哨兵 #2 — sliding_window 无脏时间戳、跨度 ≤ 14 天
```sql
SELECT MIN(event_time_std)::date AS min_day,
       MAX(event_time_std)::date AS max_day,
       MAX(event_time_std) - MIN(event_time_std) AS span,
       COUNT(*) AS rows
FROM rb5.cell_sliding_window;
```
**期待**:
- `min_day >= 2025-12-01`(**不得出现 2023/2024 任何时间戳**)
- `max_day <= 2025-12-07`(不得出现未来)
- `span <= '14 days'`

### 哨兵 #3 — _step2_cell_input 没 stale
```sql
SELECT to_regclass('rb5._step2_cell_input') AS exists_or_null;
-- 如果非 NULL,再查
SELECT MIN(event_time_std)::date AS min_day,
       MAX(event_time_std)::date AS max_day
FROM rb5._step2_cell_input
WHERE event_time_source = 'report_ts';
```
**期待**:`exists_or_null IS NULL`(runner 每批开头 drop 过);如果非 NULL,`max_day` 必须 = 当前 batch 对应的 day(**不得停留在 batch 1 的 2025-12-01**)

### 哨兵 #4 — TCL 单调增长(证明没冻结)
```sql
SELECT batch_id, COUNT(*) AS tcl_rows
FROM rb5.trusted_cell_library
GROUP BY batch_id
ORDER BY batch_id;
```
**期待**:行数 batch 1 < batch 2 < ... < batch N(允许小波动,但**不得出现连续 2 批完全相同**,那就是 Gate 3 的"batch 5 后冻结"复现)

---

## 6. Batch 7 终点量级验收(软验收)

batch 7 跑完后执行一次,只看量级对齐,**不看子类分布**。

### 6.1 TCL 总量 ±20%

```sql
-- Citus
SELECT COUNT(*) AS citus_tcl_b7 FROM rb5.trusted_cell_library WHERE batch_id = 7;

-- PG17 基线(via mcp__PG17__execute_sql)
SELECT COUNT(*) AS pg17_tcl_b7 FROM rebuild5.trusted_cell_library WHERE batch_id = 7;
-- 期待 pg17 ~ 341,460
```
**判定**:`abs(citus_tcl_b7 - pg17_tcl_b7) / pg17_tcl_b7 <= 0.20`

### 6.2 sliding_window 日期范围正确

```sql
SELECT MIN(event_time_std)::date AS min_day,
       MAX(event_time_std)::date AS max_day,
       COUNT(DISTINCT event_time_std::date) AS n_days
FROM rb5.cell_sliding_window;
```
**期待**:
- `min_day` 在 `2025-11-24 ~ 2025-12-01` 之间(trim 的 14 天窗口)
- `max_day = 2025-12-07`
- 完全没有 2023/2024 年、没有 2025-12-08+

### 6.3 enriched 7 批全覆盖

```sql
SELECT batch_id, MIN(event_time_std)::date, MAX(event_time_std)::date, COUNT(*)
FROM rb5.enriched_records
GROUP BY batch_id ORDER BY batch_id;
```
**期待**:7 行,`batch_id = 1..7`,每行 `min=max=2025-12-0<bid>`

---

## 7. 产出物 `06_rerun_validation.md` 结构

```markdown
# fix5 / 06 重跑验收报告(终点)

## 0. TL;DR
- runner:串行 / pipelined
- 总时长:H 小时 M 分
- 哨兵:7 批 × 4 条 全过 / 第 N 批第 X 条 fail
- 终点量级:TCL ±X.X% / sliding_window 日期范围 pass / enriched 7 批全覆盖 pass
- fix5 结论:**交付** / **失败(blocker = ...)**

## 1. 启动信息
- reset SQL 执行时间 + 验证结果
- runner 选择 + 理由
- 启动命令(带 PGOPTIONS)
- 后台 PID + 日志路径

## 2. 批次运行时长
| batch | day | step1 s | step2-5 s | total s | published_cell |
|---|---|---:|---:|---:|---:|
| 1 | 2025-12-01 | ... | ... | ... | ... |
| ... | | | | | |
| 7 | 2025-12-07 | ... | ... | ... | ... |

## 3. 每批哨兵
### batch 1
- #1 enriched 单日:min=2025-12-01 max=2025-12-01 rows=N **PASS**
- #2 sliding_window:min=... max=... span=... **PASS**
- #3 _step2_cell_input:NULL **PASS**
- #4 TCL 单调:batch_1 rows=N **PASS**
(batch 2~7 同结构)

## 4. Batch 7 终点量级
- TCL 总量 ±X.X% **PASS/FAIL**
- sliding_window 日期范围 **PASS/FAIL**
- enriched 7 批全覆盖 **PASS/FAIL**

## 5. 附录:完整日志关键片段
- runner step2_scope_materialized 的 rows 数值 × 7 批
- 任何 error / warn / suspect

## 6. 交付结论
- 如全 pass:fix5 阶段结束,可切上游做数据应用
- 如有 fail:blocker 明细 + 建议上游下一步(不自作主张修)
```

---

## 8. notes 协议

- 开跑前:`INSERT INTO rb5_bench.notes ... (topic='fix5_D_started', severity='info', message='runner=<serial|pipelined>, expected_duration=..., started_at=...')`
- 每批跑完:可选 `topic='fix5_D_batch_<N>'` 记关键数值
- 哨兵 fail:**必须** `severity='blocker'`,`topic='fix5_D_blocker_batch_<N>_sentinel_<#>'`,附完整 SQL 输出
- 全过完工:`topic='fix5_D_done', severity='info', message='serial/pipelined, total=...s, TCL_b7=..., diff_from_pg17=X.X%'`
- 失败收尾:`topic='fix5_D_failed', severity='blocker', message='blocker summary'`

---

## 9. 你最后一句话

成功:
> "D 阶段完成,fix5 交付。06 在 `rebuild5/docs/fix5/06_rerun_validation.md`。runner=<serial|pipelined> / 总时长=<H:MM:SS> / 7 批哨兵全过 / batch 7 TCL 差 PG17 = <X.X%> / sliding_window 日期范围正确。notes `topic='fix5_D_done'` 已插入。"

失败:
> "D 阶段失败于 batch <N> 哨兵 #<K>。blocker=<一句话>。notes `topic='fix5_D_failed'` 已插入。已停 run,等上游处置。"
