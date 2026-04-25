# OptiNet rebuild5 / loop_optim / 02b artifact 分布键 hotfix(agent 新实例对话)

## § 1 元目标

**一句话 fix**:`freeze_step2_input_artifact` 把 artifact 表的分布键从 `dev_id` 改成 `cell_id`,与 Step2 下游(`trusted_cell_library` / `cell_sliding_window` / `candidate_seed_history` / `enriched_records`)的 cell colocation group 协调,解锁 03 阶段被 blocker 的 Step2 path-A 分布式 join。

**根因**(03 agent 已诊断 + Claude 已验证):
- 02 实施时 `colocate_with => 'rb5.etl_cleaned'`,etl_cleaned 分布键 = `dev_id`
- artifact 跟着拿到 `dev_id` 分布键
- Step2 path-A 在 `rebuild5/backend/app/profile/pipeline.py:837` 附近按 `cell_id` join 下游 cell colocation group → Citus 抛 "complex joins are only supported when all distributed tables are co-located and joined on their distribution columns"

**正确分布键**:`cell_id`,colocate_with 选 cell colocation group 的代表表(推荐 `rb5.cell_sliding_window`,因为它是 Step2-5 的核心 input)。

## § 2 上下文启动顺序

按序读完直接开干:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/loop_optim/README.md`
3. `rebuild5/docs/fix6_optim/_prompt_template.md` § 11/§ 12
4. `rebuild5/docs/loop_optim/02_artifact_pipelined_report.md` —— 02 实施报告
5. `rebuild5/scripts/run_daily_increment_batch_loop.py` 的 `freeze_step2_input_artifact` 函数(L173-) —— 这是要改的对象
6. `rebuild5/backend/app/core/database.py:_distribution_key` (L139-160) —— 分布键决策函数,02b 应该复用它
7. `rb5_bench.notes` 里 `topic='loop_optim_03_blocker_artifact_distkey'` —— 03 agent 写的 blocker 详情(完整 traceback)
8. 本 prompt

读完直接开干,不需要 ack。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`
- **当前 git 头**:`36fcaa5`(02 已 push 远端,03 因 blocker 没 commit)
- **Citus**:`postgres://postgres:123456@192.168.200.217:5488/yangca`,MCP `mcp__PG_Citus__execute_sql`
- **Git remote**:GitHub HTTPS SSL 抖动严重,push 失败等 60s 重试一次再标 pending

### 03 阶段已写过的状态(不要回滚)

- 03 阶段 reset 已跑过,当前 `rb5.trusted_cell_library` / `cell_sliding_window` / `enriched_records` 应该是空的或部分 batch 1
- `rb5_meta.pipeline_artifacts` 可能有 batch 1 status='failed' 记录(03 consumer 写的)
- `rb5_stage.step2_input_b1_20251201` 可能存在(分布键错的那个),需要 cleanup

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `loop_optim/02_artifact_pipelined_report.md` | 阅读 | 02 实施细节,知道当前怎么写的 |
| `rebuild5/scripts/run_daily_increment_batch_loop.py` | 修改 | `freeze_step2_input_artifact` 改 colocation 逻辑 |
| 本阶段产出 `02b_artifact_dist_fix_report.md` | 新建 | § 7 结构(短报告,~100 行即可) |

**本阶段不修业务代码 / 不动其他文件**,只改这一个函数 + smoke 验证 + 报告。

## § 5 任务清单

### 必做(按顺序)

#### 5.1 先 cleanup 03 阶段残留(非破坏性,只清 02 错产物)

```sql
-- 清掉错分布键的 artifact 表(本次 fix 后会重建)
DROP TABLE IF EXISTS rb5_stage.step2_input_b1_20251201;
DROP TABLE IF EXISTS rb5_stage.step2_input_b2_20251202;
DROP TABLE IF EXISTS rb5_stage.step2_input_b3_20251203;
DROP TABLE IF EXISTS rb5_stage.step2_input_b4_20251204;
DROP TABLE IF EXISTS rb5_stage.step2_input_b5_20251205;
DROP TABLE IF EXISTS rb5_stage.step2_input_b6_20251206;
DROP TABLE IF EXISTS rb5_stage.step2_input_b7_20251207;

-- 清 state 表(03 跑失败的 batch 1 记录)
DELETE FROM rb5_meta.pipeline_artifacts;
```

不动 `rb5.trusted_cell_library` / `cell_sliding_window` / `enriched_records` 等下游表(这些不影响 fix,03 重跑会通过 reset SQL 清)。

#### 5.2 修改 `freeze_step2_input_artifact` 的分布键逻辑

打开 `rebuild5/scripts/run_daily_increment_batch_loop.py:173-`,定位:

```python
distribution = _source_distribution(source_relation)
...
if distribution and distribution.get('partmethod') == 'h':
    distribution_column = distribution.get('distribution_column')
    ...
    execute(
        'SELECT create_distributed_table(%s, %s, colocate_with => %s)',
        (artifact, str(distribution_column), source_relation),
    )
```

**改成**(不再用 source_relation 的分布,而是显式用 cell colocation group):

```python
# Decide artifact distribution: artifact must colocate with Step2-5
# downstream cell-keyed tables (trusted_cell_library / cell_sliding_window /
# candidate_seed_history), NOT with etl_cleaned (dev_id).
# This is the loop_optim 02b fix: the original colocate_with=etl_cleaned
# placed artifact in the device colocation group, breaking Step2 path-A
# joins on cell_id (Citus "complex joins" limitation).
ARTIFACT_DIST_COL = 'cell_id'
ARTIFACT_COLOCATE_WITH = 'rb5.cell_sliding_window'  # cell colocation group

# Verify the colocation target exists and is on cell_id
target_dist = _source_distribution(ARTIFACT_COLOCATE_WITH)
if not target_dist or target_dist.get('partmethod') != 'h' \
        or target_dist.get('distribution_column') != ARTIFACT_DIST_COL:
    raise RuntimeError(
        f'colocation target {ARTIFACT_COLOCATE_WITH} not on {ARTIFACT_DIST_COL} '
        f'(got {target_dist}); 02b assumption violated'
    )

execute(
    'SELECT create_distributed_table(%s, %s, colocate_with => %s)',
    (artifact, ARTIFACT_DIST_COL, ARTIFACT_COLOCATE_WITH),
)
```

**注意细节**:
- 保留对 source_relation 是否存在的检查(`relation_exists` 已在),不删
- 保留索引 / ANALYZE / state 写入逻辑,只改 create_distributed_table 那一段
- 删除原 `distribution = _source_distribution(source_relation)` 调用(因为不再依赖 source 分布键),除非你判断它在其他地方还有用

#### 5.3 fallback:cell_sliding_window 不存在的情况

`cell_sliding_window` 在 reset 后还是 schema 创建好的(空表),所以 `_source_distribution` 应能查到。但保险起见,加 fallback:

```python
# fallback: 如果 cell_sliding_window 不存在(罕见,reset SQL 应保 schema 在),
# 用 trusted_cell_library 兜底
if not relation_exists(ARTIFACT_COLOCATE_WITH):
    ARTIFACT_COLOCATE_WITH = 'rb5.trusted_cell_library'
    if not relation_exists(ARTIFACT_COLOCATE_WITH):
        # 都不存在 → 不 colocate(降级,artifact 仍按 cell_id 分布,只是新 colocation group)
        execute(
            'SELECT create_distributed_table(%s, %s)',
            (artifact, ARTIFACT_DIST_COL),
        )
        return ...  # 跳过 colocate 路径
```

**这段在原代码块外加判断,不是嵌套写**,保持简单。

#### 5.4 Smoke 验证(同 02 阶段)

```python
# 跑一次 freeze on batch 7(2025-12-07),用现有 etl_cleaned(reset 后可能空,如果是空就改 batch 1 day 2025-12-01,先跑 step1 装载)
# 实际 smoke 路径:
# 1. 看 etl_cleaned 当前状态
# 2. 如果有数据,直接 freeze 一个 day(任选 day,batch_id=99 mock)
# 3. 验 artifact 分布键 = cell_id,colocate_with cell_sliding_window
# 4. cleanup smoke artifact
```

**关键验证 SQL**:
```sql
-- 跑完 smoke freeze 之后:
SELECT logicalrelid::regclass::text AS rel,
       a.attname AS dist_col,
       (SELECT colocationid FROM pg_dist_partition WHERE logicalrelid='rb5.cell_sliding_window'::regclass) AS expected_colo,
       p.colocationid AS actual_colo
FROM pg_dist_partition p
LEFT JOIN pg_attribute a
  ON a.attrelid = p.logicalrelid
 AND a.attnum = (regexp_match(p.partkey::text, ':varattno ([0-9]+)'))[1]::int
WHERE p.logicalrelid::regclass::text LIKE 'rb5_stage.step2_input_b99%';
-- 期望:dist_col='cell_id', actual_colo == expected_colo
```

如果 colocationid 不匹配,fix 没生效,blocker。

#### 5.5 cleanup smoke artifact

```sql
DROP TABLE IF EXISTS rb5_stage.step2_input_b99_<YYYYMMDD>;
DELETE FROM rb5_meta.pipeline_artifacts WHERE batch_id = 99;
```

#### 5.6 静态验证

```bash
python3 -m py_compile rebuild5/scripts/run_daily_increment_batch_loop.py
```

#### 5.7 完工流程

`git add`:
- `rebuild5/scripts/run_daily_increment_batch_loop.py`
- `rebuild5/docs/loop_optim/02b_artifact_dist_fix_prompt.md`(本 prompt)
- `rebuild5/docs/loop_optim/02b_artifact_dist_fix_report.md`(产出)
- `rebuild5/docs/loop_optim/README.md`(状态加一行 02b)

一个 commit:
```
fix(rebuild5): loop_optim 02b artifact distribution key (cell_id) for Step2 colocation

- freeze_step2_input_artifact now creates artifact with dist=cell_id colocated
  with rb5.cell_sliding_window (cell colocation group), not etl_cleaned (device)
- Root cause from 03 blocker: Step2 path-A complex joins on cell_id failed
  because artifact was in device colocation group (Citus distributed plan
  rejection: "complex joins are only supported when all distributed tables
  are co-located and joined on their distribution columns")
- Smoke verified: artifact colocationid matches cell_sliding_window
- References loop_optim/02_artifact_pipelined_report.md and 03 blocker note

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

push 撞 SSL 等 60s 重试再标 pending。

写 note `topic='loop_optim_02b_done'`。

### 不做(显式禁止)

- ❌ 不动 freeze_step2_input_artifact 之外的任何代码
- ❌ 不改 etl_cleaned 表 / 分布键
- ❌ 不改 02C 守护(15 个 test 不动,02b 改的是 colocation 实现细节,不破坏接口)
- ❌ 不动 03 prompt(03 重跑用同一份 prompt)
- ❌ 不跑全 7 批(留给 03 重跑)
- ❌ 不删 03 已写的 blocker note(留作历史 trail)
- ❌ 不引入新依赖
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent

## § 6 验证标准

1. **freeze_step2_input_artifact 改完**:grep `cell_sliding_window\|ARTIFACT_DIST_COL\|ARTIFACT_COLOCATE_WITH` 在文件里命中
2. **smoke artifact 分布键 = cell_id**:验证 SQL 显示 `dist_col='cell_id'`
3. **smoke artifact colocationid = cell_sliding_window 的 colocationid**:验证 SQL 显示 `actual_colo == expected_colo`
4. **smoke cleanup 后 rb5_stage 空**:`SELECT count(*) FROM information_schema.tables WHERE table_schema='rb5_stage'` = 0
5. **state 表 cleanup 后**:`SELECT count(*) FROM rb5_meta.pipeline_artifacts` = 0(如果 fix 之前有 03 残留)
6. **py_compile 过**
7. **commit + push**(允许标 pending)
8. **note `loop_optim_02b_done` 已写**

## § 7 产出物 `02b_artifact_dist_fix_report.md`(短)

```markdown
# loop_optim / 02b artifact 分布键 hotfix 报告

## 0. TL;DR
- 修复 freeze_step2_input_artifact 的 colocation:dev_id → cell_id, colocate_with cell_sliding_window
- smoke artifact dist_col=cell_id,colocationid 匹配 cell_sliding_window
- 03 阶段残留 cleanup 完成
- commit SHA + push 状态

## 1. 关键 diff
~10-20 行 freeze_step2_input_artifact 改动

## 2. Smoke 结果
- artifact 分布键查询输出
- colocationid 匹配检查

## 3. 03 阶段残留 cleanup
- 删除的 rb5_stage.* 表
- 清空的 pipeline_artifacts 行

## 4. 给 03 重跑的输入
- 03 prompt(03_rerun_prompt.md)无修改,直接重跑
- reset SQL 已在 02 阶段扩展(drop rb5_stage + truncate state),03 重跑前仍跑一次 reset
```

## § 8 notes 协议

- 完工:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('loop_optim_02b_done', 'info',
    'artifact dist_key fix: cell_id colocate_with cell_sliding_window; smoke verified colocationid match; 03 blocker artifact_distkey resolved; head=<sha>');
  ```
- 失败:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('loop_optim_02b_failed', 'blocker', 'failed at <step>: <reason>');
  ```

## § 9 完工话术

成功:
> "loop_optim 02b 完成。02b_artifact_dist_fix_report.md 已写入。freeze_step2_input_artifact 现在生成 cell_id 分布 + colocate_with cell_sliding_window 的 artifact。smoke 验证 colocationid 匹配。03 残留已 cleanup。commit=<SHA>(push <成功/pending>)。03 重跑可直接用同一份 03_rerun_prompt.md。notes `topic='loop_optim_02b_done'` 已插入。"

失败:
> "loop_optim 02b 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='loop_optim_02b_failed'`。等上游处置。"

## § 10 失败兜底

- **cell_sliding_window 不存在或不是 cell_id 分布**:fallback 用 trusted_cell_library;再不行降级为不 colocate(纯 cell_id 分布,新 colocation group),报告标"未 colocate,可能跨 group join 慢"
- **smoke colocationid 不匹配**:fix 没生效,blocker;不要跑 03 重跑,先排查
- **smoke freeze 失败**(etl_cleaned 空):**这不是 fix 问题**,是 03 阶段 reset 把 etl_cleaned 清了。先跑一次 step1 day 2025-12-01 装载 etl_cleaned 再 smoke;**或者**简化 smoke:只 verify create_distributed_table 返回 + 查 pg_dist_partition,不跑实际 INSERT
- **GitHub HTTPS SSL 抖动**:等 60s 重试,push pending 不算 blocker
- **任何挂** → blocker note + 报告完整 traceback + 不自作主张大改
