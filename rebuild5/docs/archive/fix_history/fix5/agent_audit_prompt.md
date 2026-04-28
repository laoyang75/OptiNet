# OptiNet rebuild5 Citus 迁移 · fix5 / 代码审计(agent 接续对话)

> 你是 OptiNet-main / rebuild5 阶段的 agent 新实例。前一位 agent 刚跑完 Gate 3
> 7 批重跑(2025-12-01~12-07),但**上游 Claude MCP 校验发现严重数据质量异常**。
> 在你上一次工作的上下文里,你改过 4 个业务代码文件,嫌疑很大。
> **本轮你不做任何优化、不做并行、不改 bug** — 只做 **代码审计 + 分类 + 回滚可疑项**。

---

## 1. 定位与边界

**你要做**(严格)
1. `git status` 看 working tree 当前所有未 commit 改动
2. 对每个改过的文件 `git diff` 逐段审计,分类
3. 回滚**可疑累积/语义/去重改动**(B 类),保留**Citus 兼容必须改动**(A 类);模糊项先保留并写入 02 的待确认清单
4. 产出 `rebuild5/docs/fix5/02_agent_change_audit.md`
5. 插 `rb5_bench.notes` 完工信号

**你不做**(严格)
- ❌ 不做任何性能优化(`max_intermediate_result_size` 全局调整、pipelined 并行、shard 调整 — 统统不做)
- ❌ 不修 bug(等 C 阶段,上游 Claude 会先诊断出具体 bug 才动)
- ❌ 不跑 pipeline
- ❌ 不 git commit / push(保留 working tree 让下一阶段审核)
- ❌ 不 DROP rb5.* / rb5_bench.* 任何表(历史诊断要用)
- ❌ 不改数据库参数(包括 `SET` / `ALTER SYSTEM` / `ALTER DATABASE`)
- ❌ 不用 `git reset --hard`、`git checkout -- <file>` 这类整文件/整仓回退

上下文纪律:
- **不开 subagent**
- **不用 `python3 - <<'PY'` stdin heredoc**(以前这样会被 multiprocessing 刷屏)
- 大文件 diff 截关键节选进 md,不要把几百行 diff 全塞对话
- 启动后先读仓库根目录 `AGENTS.md`,再完整读 `rebuild5/docs/fix5/01_quality_diagnosis.md`。

---

## 2. 环境(硬信息)

仓库:   `/Users/yangcongan/cursor/WangYou_Data` (有完整读写权)

不需要 Web/UI 登录账号或 SSH 账号;本轮只读本地 git diff,以及最后向 Citus 的 `rb5_bench.notes` 写一条信号。

Citus 集群(只需要对 `rb5_bench.notes` 写一条完工信号):
- Host:     192.168.200.217
- Port:     5488
- User / Password: postgres / 123456
- Database: yangca
- DSN:      `postgres://postgres:123456@192.168.200.217:5488/yangca`

旧库 PG17(你**不需要动**):
- 5433 / ip_loc2 / postgres / 123456(审计期间不要连)

---

## 3. 上游 Claude 发现的 4 个铁证异常(只读,给你定位上下文)

1. **sliding_window 在 batch 5 后停止累积**:batch 6/7 的 `cell_sliding_window` 内容和 batch 5 完全相同(distinct_cells=340,453 锁死)
2. **k_eff=2 只有 6 个 cell 跨批 3/5/7 永远一样**:候选池从 2,223 涨到 6,452 但 DBSCAN 产出不动
3. **sliding_window 混入 2023/2024 年时间戳**:`min(event_time_std)=2023-12-29`,`WINDOW_RETENTION_DAYS` 没 trim
4. **多质心类分布全崩**:Citus batch 7 large_coverage/dual_cluster/uncertain 全是 0,本地 batch 7 分别是 745/442/82

嫌疑代码文件(你之前改过):
- `rebuild5/backend/app/enrichment/pipeline.py`(snapshot_seed_records 跨批桥接去重)
- `rebuild5/backend/app/maintenance/window.py`(`refresh_sliding_window` 累积/trim)
- `rebuild5/backend/app/maintenance/label_engine.py`(候选池 / postgis DBSCAN)
- `rebuild5/scripts/run_citus_serial_batches.py`(runner,可能不关键)
- `rebuild5/scripts/gate3_cleanup.sql`(清理,可能不关键)
- 其他 Citus 迁移期改动的文件(如 `etl/parse.py` / `etl/clean.py` / `evaluation/pipeline.py` 等,如果有 `git diff` 命中)

---

## 4. 审计方法:三类分法

对每个文件的每段 diff,归入 **A / B / C** 三类:

### A 类 · Citus 兼容必要改动(保留)

这些是迁移到 Citus 的必要基础设施,**保留不动**:

- `rebuild5.` → `rb5.` schema 全局替换
- `rebuild5_meta.` → `rb5_meta.`
- `CREATE TABLE X AS SELECT ...` → 预建 `CREATE TABLE + create_distributed_table + INSERT/SELECT`(避 Citus CTAS 搬运税)
- Simple CASE `CASE col WHEN 'str'` → Searched CASE `CASE WHEN col='str'`(修 Citus 14.0 text=boolean bug)
- `IMMUTABLE` 函数包装(`rb5._immutable_text_to_utc_timestamptz` 等)
- PostGIS `ST_ClusterDBSCAN` 相关的必要语法调整
- PK/UNIQUE 扩展包含分布键(Citus 硬约束)
- `_step2_cell_input` / `_snapshot_seed_new_cells` 这类"跨 colocation group JOIN 中转表"
- DSN 切换(`REBUILD5_PG_DSN` 默认值)

### B 类 · 语义/累积/去重变动(**回滚**,嫌疑在此)

这些**可能改变了业务语义**,直接回滚:

- `refresh_sliding_window` 里累积/trim 逻辑的改动(特别是时间窗口、DELETE USING、retention day 相关)
- `snapshot_seed_records` 生成逻辑的变动,包括 agent 加的跨批"去重/桥接" SQL
- `candidate_seed_history` / `enriched_records` 的填充策略变化
- `label_engine` 的候选池筛选条件变动(`_label_candidates` / `_label_input_points` 的 WHERE)
- `_label_cell_stats` 三阈值相关的改动
- `ST_ClusterDBSCAN` 的 `OVER (PARTITION BY ...)` 范围变化

**怎么回滚**:首选手工 patch / `apply_patch` 做最小修改,只删 B 类和 C 类行,保留 A 类。只有在完全确认单个 hunk 全是 B/C 类时,才可用 `git checkout -p <file>` 选择性回滚。不要用 `git stash` 处理这次审计。

### C 类 · debug / 测试遗留(清理)

- 到处撒的 `SET citus.max_intermediate_result_size=-1`(不管是在 Python 还是 SQL 里),全部清理
- 调试 print / 临时 log / 跳过 ODS-024b 校验 / 绕过 blocker 的 try-except 吞异常
- `gate3_cleanup.sql` 这类一次性脚本如果有 hard-code 的 DELETE/TRUNCATE,清理

---

## 5. 执行步骤

### Step 1 · 列出所有未 commit 改动
```bash
cd /Users/yangcongan/cursor/WangYou_Data
git status
git diff --stat   # 每文件改了多少行
```

### Step 2 · 逐文件 diff 审计

按影响面排序建议:window.py → enrichment/pipeline.py → label_engine.py → 其他。

对每个文件:
```bash
git diff -- rebuild5/backend/app/maintenance/window.py | less
# 或者
git diff -U8 -- <file>    # 多带上下文便于看懂
```

**怎么看一段 diff 属于 A/B/C**:
- 问自己:"如果我**不做**这段改动,pipeline 会不会因为 Citus 不兼容直接报错?"
  - 会报错(语法/分布键/类型/函数限制)→ **A 类,保留**
  - 不会报错,只是"我以为这样改能让跨批正常"→ **B 类,回滚**
  - 是为了绕过某个 blocker 临时加的 → **C 类,清理**

### Step 3 · 逐段回滚 B 类 + 清理 C 类

推荐安全方式:
```bash
# 先看带上下文 diff,再用 apply_patch / 编辑器做最小手工 patch
git diff -U12 -- rebuild5/backend/app/maintenance/window.py
```

仅当单个 hunk 边界清楚、全是 B/C 类时,才可用:
```bash
git checkout -p rebuild5/backend/app/maintenance/window.py
```

复杂 hunk 不要用交互式回滚硬切,改用手工 patch,并在 02 里解释为什么保留或回滚。

### Step 4 · 验证 A 类保留是否完整

回滚完后:
```bash
python3 -m py_compile rebuild5/backend/app/maintenance/window.py \
                      rebuild5/backend/app/enrichment/pipeline.py \
                      rebuild5/backend/app/maintenance/label_engine.py \
                      rebuild5/backend/app/etl/parse.py \
                      rebuild5/backend/app/etl/clean.py \
                      rebuild5/backend/app/evaluation/pipeline.py
```

应 0 SyntaxError。

确认关键 A 类改动还在:
```bash
grep -n "rb5\." rebuild5/backend/app/maintenance/window.py | head -3
grep -n "searched\|CASE WHEN lifecycle_state" rebuild5/backend/app/evaluation/pipeline.py | head -3
grep -n "_immutable_" rebuild5/backend/app/etl/clean.py
grep -n "create_distributed_table\|INSERT INTO" rebuild5/backend/app/maintenance/window.py | head -5
```

### Step 5 · 产出 `fix5/02_agent_change_audit.md`

结构:

```markdown
# fix5 / 02 Agent 代码审计(回滚后报告)

## 0. TL;DR
(总共审计 N 文件,回滚 X 段 B 类 + Y 段 C 类,保留 Z 段 A 类)

## 1. 审计总览
| 文件 | 原 diff 行数 | A 保留 | B 回滚 | C 清理 | 回滚后剩余改动行数 |
|---|---|---|---|---|---|
| maintenance/window.py | 120 | 40 | 60 | 20 | 40 |
| enrichment/pipeline.py | ... |
| ...

## 2. 逐文件详情

### 2.1 maintenance/window.py
**A 类(保留)**
- 行 A-A+N:<描述> — <为什么 Citus 兼容必需>
- ...

**B 类(已回滚)**
- 行 B-B+N:<描述> — <语义变动嫌疑说明>
- ...

**C 类(已清理)**
- 行 C-C+N:<描述> — <debug 遗留说明>
- ...

### 2.2 enrichment/pipeline.py
...

## 3. 回滚后 git status
(贴 `git status` + `git diff --stat` 最终状态)

## 4. 对 C 阶段 agent 的交接
- 你回滚的 B 类改动有 X 段,等上游 Claude 诊断完给出具体 bug 位置,下一位 agent 可以
  直接参考这些"曾经的尝试"做正确实现
- A 类改动是 C 阶段的基线,**不要回退 A 类**
```

### Step 6 · 插完工信号

```sql
-- PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca
INSERT INTO rb5_bench.notes (topic, severity, body) VALUES (
  'fix5_audit_complete', 'info',
  '02_agent_change_audit.md 已输出,B 类改动已回滚,A 类 Citus 必要改动保留。working tree 未 commit,等待 C 阶段。'
);
```

---

## 6. 协作提示(串行,你跑在 A 之后)

- **上游 Claude 已完成 A 阶段**,产出 `rebuild5/docs/fix5/01_quality_diagnosis.md`
- **开始前必须先完整读完 01**,里面包含了:
  - 4 个异常的具体根因定位
  - 可疑代码位置(具体到文件 + 行号)
  - 给你的修复方向(但 C 阶段才修,你本轮只做回滚可疑改动)
- **用 01 来精准判断 B 类**:
  - 如果 01 指出某段改动是导致 sliding_window 断档 / k_eff 锁死 / 时间戳污染的直接原因 → 强 B 类,必回滚
  - 如果 01 没提到的某段改动但语义上可疑 → 弱 B 类,回滚并在 02 标注"基于经验判断,非 01 直接命中"
  - 01 明确指出"这段改动是 Citus 兼容必需" → 标 A 类保留
- 如果你读完 01 有**新疑问**,在 rb5_bench.notes 写 severity='suspect' topic='fix5_audit_uncertain' 记录,但不要停下 — 对有明确定位的 B 类先回滚,对模糊项先保留并写入 02 的待确认清单。

---

## 7. 边界再重申

- 不优化、不并行、不修 bug、不跑 pipeline
- 不 commit / push
- 不改 DB 参数
- 产出 `02_agent_change_audit.md` + 插 `fix5_audit_complete` note = 完工

**有不确定项时,不要硬推、不要整文件回退;写 `rb5_bench.notes` severity='suspect' topic='fix5_audit_uncertain',在 02 标成待确认,然后继续处理其他明确项。**
