# 25 重跑 rebuild5 全链路（方案 7.4 + GPS 硬过滤）

> **创建日期**：2026-04-20
> **仓库**：`/Users/yangcongan/cursor/WangYou_Data`
> **数据库**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **前置**：必须先完成 `prompts/24_ui_label_alignment_and_refinement.md` 的 §1.1 / §1.2 / §1.3 / §1.4 研究工作，对应代码与文档修改已落地（详见 §2 清单）

本 prompt 用于从独立新对话启动，不需要回看历史。所有必要上下文都在本文件里。

---

## 0. 你的任务

1. **先做冒烟测试**（§4）：用小样本跑通代码路径，确认无 Python / SQL 异常
2. **正式全量重跑**（§5）：Step 2 → 3 → 5 按顺序重跑 batch 7
3. **验证结果**（§6）：对比方案 7.4 期望分布，UI 正常显示
4. **汇报**（§8）：简短报告 + 遗留风险

---

## 1. 改动的原因与核心逻辑

本次重跑是因为落地两条互相配合的修复：

### 1.1 Step 2 profile_obs 加"每观察点必有 GPS"硬约束
- **原问题**：`_profile_path_b_records` 里包含 cell 内无 GPS 的信号记录；`profile_obs` 按分钟聚合**不区分**是否 GPS 有效；`independent_obs = COUNT(*) FROM profile_obs` 因此包含了无 GPS 的分钟，导致大量"只有 1 条 GPS + 13 条信号"的 cell 凭 `independent_obs=14 >= 10` 虚假晋级 qualified
- **设计原则**（`docs/03_流式质量评估.md` §GPS 有效性）：每个 `profile_obs` 记录必须 GPS 有效
- **修复**：`build_profile_obs` 查询加 `WHERE lon_raw IS NOT NULL AND lat_raw IS NOT NULL AND gps_valid`，`independent_obs` 天然只数 GPS 有效分钟

### 1.2 Step 5 label_engine 方案 7.4
核心思想：
- **规则 1**：`p90 < 1300m → stable`（Step 3 晋级已保证数据量；整体紧凑无需多质心分析）
- **规则 2a**：`p90 >= 1300m` 才入多质心；多质心层做稀疏保护（`dedup_pts<8 OR devs<3 OR days<3 → insufficient`）
- **规则 2b**：按 `k_eff` 判 large_cov / dual_cluster / migration / collision / uncertain

**成本优化**：候选池从全量过滤为 `p90>=1300m`，只有 ~1.7% 的 cell 进入 DBSCAN / 聚类自 join，其余 98.3% 在最后 CASE WHEN 里 O(1) 判 stable。

### 1.3 用户核心原则
- **精度优先不是覆盖率优先**：宁可说"不知道"（insufficient），不乱贴 stable
- **状态机**：Step 5 信任 Step 3 的晋级决策，不重新质疑
- **每观察点必须有 GPS** 是基本设计原则

---

## 2. 已修改的文件清单

### 代码（必看 diff）
| 文件 | 关键位置 |
|---|---|
| `rebuild5/backend/app/profile/pipeline.py` | `build_profile_obs` 函数（约 1050-1080 行）加 GPS 硬过滤 |
| `rebuild5/backend/app/profile/logic.py` | `load_multi_centroid_v2_params`（约 92-107 行）暴露 4 个新参数 |
| `rebuild5/backend/app/maintenance/label_engine.py` | `_label_candidates` 简化为 `p90>=1300`；新增 `_label_cell_stats` 子表；重构 `_label_results_stage` CASE WHEN |

### 配置
| 文件 | 关键位置 |
|---|---|
| `rebuild5/config/antitoxin_params.yaml` | `multi_centroid_v2` 段：`min_cluster_dev_day_pts` 10→4，新增 `multi_centroid_entry_p90_m=1300` / `min_total_dedup_pts=8` / `min_total_devs=3` / `min_total_active_days=3` |

### 文档
| 文件 | 内容 |
|---|---|
| `rebuild5/docs/03_流式质量评估.md` | §GPS 有效性 改为硬约束；§生命周期判定规则 补充说明三项非门槛；§三层资格判定 简化 anchor_eligible；§Cell 晋升进度展示 精简 |
| `rebuild5/docs/gps研究/09_标签规则重构方案7_4.md` | 方案 7.4 背景、规则、落地清单 |
| `rebuild5/docs/gps研究/10_异常数据研究_方案7_4后.md` | 研究结论 |

---

## 3. 运行环境

```bash
export PG_DSN='postgresql://postgres:123456@192.168.200.217:5433/ip_loc2'
cd /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend
```

Python 入口（全部在 `rebuild5/backend/app/` 下）：
- Step 2: `app.profile.pipeline.run_profile_pipeline()`（如有；查阅代码找到正确入口）
- Step 3: `app.evaluation.pipeline.run_evaluation_pipeline()`（同上）
- Step 5: `app.maintenance.pipeline.run_maintenance_pipeline_for_batch(batch_id=7)`

**提示**：先 `grep -rn "def run_" app/profile/pipeline.py app/evaluation/pipeline.py` 找入口。也可以直接用 CLI 脚本 / 已有 runbook（见 `rebuild5/docs/runbook_v5.md`）。

---

## 4. 冒烟测试（必做）

**目的**：确认代码语法 + 小样本跑通，避免正式跑时才发现问题。

### 4.1 Python 语法检查

```bash
python3 -c "
import ast
for f in [
    'app/profile/pipeline.py',
    'app/profile/logic.py',
    'app/maintenance/label_engine.py',
]:
    ast.parse(open(f).read()); print(f'OK {f}')
"
```

### 4.2 参数加载检查

```bash
python3 -c "
from app.profile.logic import load_multi_centroid_v2_params, load_antitoxin_params
mc = load_multi_centroid_v2_params(load_antitoxin_params())
assert mc['min_cluster_dev_day_pts'] == 4
assert mc['multi_centroid_entry_p90_m'] == 1300.0
assert mc['min_total_dedup_pts'] == 8
assert mc['min_total_devs'] == 3
assert mc['min_total_active_days'] == 3
print('params OK')
"
```

### 4.3 小样本测试（关键）

只跑 Step 5 的 label_engine，不重跑 Step 2/3（那个涉及大表，成本高）：

```bash
python3 -c "
import os, time
os.environ.setdefault('PG_DSN', 'postgresql://postgres:123456@192.168.200.217:5433/ip_loc2')
from app.maintenance.label_engine import run_label_engine
t = time.time()
run_label_engine(batch_id=7, snapshot_version='v7')
print(f'label_engine done in {time.time()-t:.1f}s')
"
```

**预期**：60-120 秒完成（因为候选池只有 ~7k cell，DBSCAN 工作量小）。

**若超过 300 秒仍未完成**：用 `SELECT ... FROM pg_stat_activity` 查看卡在哪一步（见 §7.1），kill 并汇报。

### 4.4 验证冒烟测试结果

```sql
-- label_results 有数据
SELECT COUNT(*) FROM rebuild5.label_results WHERE batch_id = 7;
-- 应 > 0

-- trusted_cell_library.drift_pattern 分布合理
SELECT drift_pattern, COUNT(*) FROM rebuild5.trusted_cell_library
WHERE batch_id = 7 GROUP BY 1 ORDER BY 2 DESC;
-- 应看到 stable 占大多数（> 90%），insufficient 少量

-- 多簇命中（应该不多，因为候选池小）
SELECT drift_pattern, COUNT(*) FROM rebuild5.trusted_cell_library
WHERE batch_id = 7 AND drift_pattern IN ('dual_cluster','uncertain','migration','collision')
GROUP BY 1;
```

**冒烟测试通过标准**：label_engine 无异常退出 + drift_pattern 分布符合方案 7.4 期望（stable 93-96%、insufficient 1-5%、其他合计 <1%）。

---

## 5. 正式全量重跑

**⚠️ 注意**：因为 Step 2 的 `profile_obs` 改了，严格来说所有批次（1-7）都应该重跑。但为节省时间，可以只重跑最新批（batch 7）先看效果，后续批次由业务安排。

### 5.1 决策点（与用户确认）

- 选项 A：只重跑 batch 7（快，1-2 小时）
- 选项 B：全部 7 批重跑（慢，可能 4-8 小时）

**默认执行选项 A**，如果业务要求重建所有历史数据再执行选项 B。

### 5.2 执行顺序（batch 7）

按顺序执行，每一步完成后 `SELECT` 验证：

```
Step 2 profile → Step 3 evaluation → Step 4 enrichment → Step 5 maintenance
```

**Step 2**：
```python
# 入口需要你找准；示意
from app.profile.pipeline import run_profile_pipeline
run_profile_pipeline(batch_id=7)
```

验证：
```sql
SELECT COUNT(*), SUM(independent_obs) FROM rebuild5.profile_base
WHERE run_id = (SELECT MAX(run_id) FROM rebuild5.profile_base);
-- independent_obs 总量应该比旧数据少（因为过滤掉无 GPS 分钟）
```

**Step 3**：
```python
from app.evaluation.pipeline import run_evaluation_pipeline
run_evaluation_pipeline(batch_id=7)
```

验证：
```sql
SELECT lifecycle_state, COUNT(*) FROM rebuild5.trusted_snapshot_cell
WHERE batch_id = 7 GROUP BY 1;
-- qualified 数量应该减少（过滤掉凭信号记录虚假晋级的）
```

**Step 4**（如需）：
```python
from app.enrichment.pipeline import run_enrichment_pipeline
run_enrichment_pipeline(batch_id=7)
```

**Step 5**：
```python
from app.maintenance.pipeline import run_maintenance_pipeline_for_batch
run_maintenance_pipeline_for_batch(batch_id=7)
```

验证：见 §6。

---

## 6. 验证

### 6.1 drift_pattern 分布（核心）

```sql
SELECT drift_pattern,
  COUNT(*) AS cnt,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(), 2) AS pct
FROM rebuild5.trusted_cell_library
WHERE batch_id = 7
GROUP BY 1 ORDER BY 2 DESC;
```

**期望（方案 7.4 + GPS 硬过滤）**：

| 标签 | 占比 | 说明 |
|---|---|---|
| stable | **93-96%** | 主体，真实反映整体紧凑 cell |
| insufficient | **1-3%** | 仅剩真稀疏（p90≥1300 多质心稀疏）|
| large_coverage | < 1% | 真实大覆盖 |
| dual_cluster | < 0.2% | 真双簇 |
| uncertain | < 0.1% | 多簇 |
| oversize_single | < 0.1% | 需人工审查 |
| collision | 个位数 | cell_id 跨区复用 |
| migration | 个位数 | 真实搬迁 |

### 6.2 与旧分布对比

```sql
-- 记录旧分布到临时表（已执行过的话跳过）
SELECT 'before_7_4' AS tag, drift_pattern, COUNT(*) FROM rebuild5.trusted_cell_library
WHERE batch_id = 7 AND snapshot_version = 'v7' GROUP BY 1,2;
```

### 6.3 UI 验证

启动前端页面（Cell 画像维护），确认：
- SummaryCard 10 张卡都显示且数字合理
- 分布条主要是绿色 stable
- 筛选 tab "碰撞"/"动态"/"单簇超大"/"多质心"/"双质心" 点进去都能看到真实命中
- 点开行详情，"多质心簇"表展示两个质心坐标

### 6.4 异常告警

如果出现以下情况，**立即停止并汇报**：

- `drift_pattern = insufficient` 占比 > 10%（预期 < 3%）
- `dual_cluster` 占比 > 1%（预期 < 0.2%）
- `stable` 占比 < 85%（预期 > 93%）
- `trusted_cell_library` 总行数 ≠ Step 3 snapshot 行数（一致性违规）
- 任一步骤 SQL 运行超过 20 分钟

---

## 7. 安全约束

### 7.1 SQL 不能复杂

每条 SQL 只做一件事，避免以下模式：
- ≥3 层 CTE
- 自 join 超过 3 张表
- 大表 EXISTS (SELECT ...) 子查询

**若要观察 pipeline 进度**，用：
```sql
SELECT pid, EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       LEFT(regexp_replace(query,'\s+',' ','g'), 200) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND state='active' AND pid != pg_backend_pid()
ORDER BY query_start LIMIT 3;
```

### 7.2 避免长事务

pipeline 内部用 `autocommit=True`（见 `app/core/database.py`），无需手动 commit。不要用 `BEGIN...COMMIT` 包裹大块修改。

### 7.3 可 kill 性

如 pipeline 卡住超过 20 分钟：
```bash
# 查进程
ps aux | grep -E 'run_(profile|evaluation|maintenance)' | grep -v grep
# kill python 进程
kill <pid>
# 同时终止 pg 残留
# psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
#          WHERE datname='ip_loc2' AND state='active' AND pid != pg_backend_pid()"
```

### 7.4 不要改代码

只跑现有代码。如果发现 bug 需要改代码，先停下汇报，由用户决定是否动代码。

---

## 8. 汇报格式

完成后写一份简短报告（放到 `rebuild5/docs/rerun_delivery_2026-04-20.md` 或对应日期文件），包含：

1. **执行步骤**：哪些步骤跑了、各用时多少
2. **drift_pattern 分布**（新 vs 旧对比表）
3. **Step 3 lifecycle 分布**（新 vs 旧对比）
4. **性能**：整体耗时、最慢步骤
5. **异常**：有无告警项触发
6. **遗留风险**：有无其他批次需要重跑、有无未处理的边缘 case
7. **UI 截图或链接**（如能访问前端）

---

## 9. 回滚方案

如果新规则出问题，回滚需要：
1. `git diff` 查看改动
2. `git checkout -- rebuild5/config/antitoxin_params.yaml rebuild5/backend/app/profile/pipeline.py rebuild5/backend/app/profile/logic.py rebuild5/backend/app/maintenance/label_engine.py` 恢复代码
3. 重跑 Step 2 → 3 → 5，trusted_cell_library 会按旧规则重写

---

## 10. 不要做的事

1. 不要改 Step 3 晋级逻辑（已登记为独立工单，本次不改）
2. 不要改 candidate_trigger_config / postgis_centroid 段 yaml 参数
3. 不要同时跑多个 batch
4. 不要并发启动 pipeline（会产生锁冲突）
5. 不要提交 git commit（代码改动已完成，测试通过后由用户手动 commit）

---

## 附录 A. 关键 pg_stat_activity 查询模板

```sql
-- 当前所有活跃后端
SELECT pid, state, EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       wait_event_type, wait_event,
       LEFT(regexp_replace(query,'\s+',' ','g'), 300) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state != 'idle'
ORDER BY query_start NULLS LAST LIMIT 10;

-- 检查表行数
SELECT 'trusted_cell_library' AS tbl, COUNT(*) FROM rebuild5.trusted_cell_library WHERE batch_id = 7
UNION ALL SELECT 'label_results', COUNT(*) FROM rebuild5.label_results WHERE batch_id = 7
UNION ALL SELECT 'profile_base', COUNT(*) FROM rebuild5.profile_base
UNION ALL SELECT 'trusted_snapshot_cell', COUNT(*) FROM rebuild5.trusted_snapshot_cell WHERE batch_id = 7;
```

## 附录 B. 紧急联系

如遇无法解决的问题：
1. `git status` 看本次新增文件（prompts/、docs/gps研究/）
2. 完整 prompt 见 `rebuild5/prompts/24_ui_label_alignment_and_refinement.md`（本次原始任务）
3. 调研细节见 `rebuild5/docs/gps研究/09_标签规则重构方案7_4.md`
