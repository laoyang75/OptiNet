# fix5 / 02 Agent 代码审计(回滚后报告)

## 0. TL;DR

本轮审计了 working tree 中 63 个已跟踪改动文件和 22 个未跟踪路径。按 `01_quality_diagnosis.md` 的结论,只回滚/清理直接命中质量异常或审计提示明确禁止的片段:

- B 类已回滚 4 段: `window.py` trim 快捷返回/跳过逻辑、`label_engine.py` 的新增 `dev_count` 聚类阈值、`label_engine.py` 的 k_eff/dynamic 简化判定、`run_citus_serial_batches.py` 的 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM=1`。
- C 类已清理 4 段: `core/database.py` 全局 session SET、`window.py` trim session SET、`label_engine.py` label input session SET、`gate3_cleanup.sql` 硬编码清库脚本。
- A 类保留: `rb5.*`/`rb5_meta.*` schema 迁移、Citus CTAS 分布化 helper、PK/分布键兼容、`_step2_cell_input` 与 `_snapshot_seed_new_cells` 中转表、immutable timestamptz helper、PostGIS DBSCAN 基础语法。

未做 pipeline 重跑、未 commit/push、未 DROP/TRUNCATE 数据库对象、未修改数据库参数。C 阶段仍需按 01 执行真正修复: runner 在 Step 1 后物化 per-batch `step2_batch_input`。

## 1. 审计总览

| 文件/范围 | 原 diff 行数 | A 保留 | B 回滚 | C 清理 | 回滚后剩余改动行数 |
|---|---:|---:|---:|---:|---:|
| `backend/app/core/database.py` | 178 | CTAS -> 分布式建表 helper、Citus layout 推断 | 0 | 1: 删除全局 `SET auto_explain...` / `SET citus.max_intermediate_result_size=-1` | 170 |
| `maintenance/window.py` | 496 | `rb5.*`, 新 schema 字段传递, Step 5 中间表迁移 | 1: trim span 快捷返回 + env skip + `DELETE USING` 改写 | 1: 删除 trim 内 session SET | 447 |
| `maintenance/label_engine.py` | 207 | `rb5.*`, `_label_input_points` 预建 + INSERT, PostGIS 分区保持 | 2: `dev_count` 聚类阈值、k_eff/dynamic 判定改写 | 1: 删除 label input session SET | 176 |
| `enrichment/pipeline.py` | 164 | `rb5.*`, `_snapshot_seed_new_cells` 中转表 | 0 | 0 | 164 |
| `profile/pipeline.py` | 541 | `rb5.*`, `_step2_cell_input` fallback 中转表, 分布键相关 PK | 0 | 0 | 541 |
| `etl/clean.py` / `etl/parse.py` / `etl/fill.py` | 544 | `rb5.*`, immutable timestamptz helper | 0 | 0 | 544 |
| `evaluation/pipeline.py` | 428 | `rb5.*`, searched CASE 风格、Citus CTAS 迁移 | 0 | 0 | 428 |
| `scripts/run_citus_serial_batches.py` | 904(未跟踪原文件) | Citus DSN、串行 runner 框架 | 1: 删除强制跳过 sliding_window trim | 0 | 903 |
| `scripts/gate3_cleanup.sql` | 25(未跟踪原文件) | 0 | 0 | 1: 替换为 no-op, 移除硬编码 TRUNCATE/DROP/SET | 4 |
| 其他已跟踪 55 文件 | 3005 | 以 `rb5.*`/`rb5_meta.*`、脚本/文档同步为主 | 0 | 0 | 3005 |

## 2. 逐文件详情

### 2.1 `rebuild5/backend/app/maintenance/window.py`

**A 类(保留)**

- 行 60-68: `rebuild5.*` -> `rb5.*`, 保留 Citus 目标 schema。
- 行 72-117: `cell_origin` / `timing_advance` / `freq_channel` 字段随 Step 4 进入 sliding window。该字段链路超出 01 根因,未在本轮回滚,列入待确认。
- 行 128-158: trim 业务语义恢复为按 per-cell latest event time + latest N obs 保留; schema 仍为 `rb5.cell_sliding_window`。

**B 类(已回滚)**

- 原 diff 在 trim 前新增全局 span 检查,当全窗口跨度小于 14 天时直接 return。该逻辑会跳过 per-cell retention,属于 `refresh_sliding_window` 时间窗口语义改动,已删除。
- 原 diff 在 trim 前读取 `REBUILD5_SKIP_SLIDING_WINDOW_TRIM` 并 return。01 已指认为 2023/2024 脏时间戳永不清理的共振原因,已删除。
- 原 diff 将 trim 从 `ctid` keep_rows 改成 `DELETE USING (batch_id, source_row_uid, cell_id)`。审计提示将 `DELETE USING` / retention day 相关改动列为 B 类,已恢复原 retention 语义并保留 `rb5.*`。

**C 类(已清理)**

- 原 diff 在 trim 中执行 `SET citus.max_intermediate_result_size = -1`,违反本轮不改数据库参数约束,已删除。

### 2.2 `rebuild5/backend/app/maintenance/label_engine.py`

**A 类(保留)**

- 全文件 `rb5.*` schema 迁移保留。
- 行 84-159: `_label_input_points` 由 CTAS 改成预建表 + `INSERT INTO`,属于 Citus CTAS 兼容改造;移除 session SET 后保留。
- 行 207-211: `ST_ClusterDBSCAN(...) OVER (PARTITION BY operator_code,lac,bs_id,cell_id,tech_norm)` 分区范围未改,保留。

**B 类(已回滚)**

- 行 328: 删除新增 `AND c.dev_count >= min_cluster_dev_count`。这是 label 候选簇筛选阈值变动,01 明确说 label_engine 产出率低是 stale input 下游症状,不应调阈值。
- 行 398-403: `k_eff` 恢复为只按 `dev_day_pts >= min_cluster_dev_day_pts` 统计,删除新增 `dev_count` 条件。
- 行 674-686: dynamic 判定恢复为原 `max_span_m` / `line_ratio` / `distance_cv` / `avg_dwell_days` 组合阈值,删除 `k_eff>=5 => dynamic` 的语义简化。

**C 类(已清理)**

- 原 diff 在 `_label_input_points` 插入前执行 `SET citus.max_intermediate_result_size=-1`,已删除。

### 2.3 `rebuild5/backend/app/core/database.py`

**A 类(保留)**

- 行 15-38, 72-214: CTAS SQL 识别、`CREATE TABLE AS ... WITH NO DATA` + `create_distributed_table` / `create_reference_table` + `INSERT INTO` 的 Citus 兼容 helper 保留。

**C 类(已清理)**

- 行 41-49: `get_conn()` 恢复为只建连接/关闭连接。原先每次连接都执行 `SET auto_explain...` 和 `SET citus.max_intermediate_result_size=-1`,已清理。

### 2.4 `rebuild5/scripts/run_citus_serial_batches.py`

**A 类(保留)**

- 行 20-23: Citus `REBUILD5_PG_DSN` 默认值保留。
- 串行 runner 框架保留。本轮不新增 `materialize_step2_scope`,因为这是 C 阶段 bugfix,不属于本轮审计回滚。

**B 类(已回滚)**

- 原行 24: `os.environ.setdefault("REBUILD5_SKIP_SLIDING_WINDOW_TRIM", "1")` 已删除。01 明确指认为 sliding_window trim 被关闭的直接原因。

### 2.5 `rebuild5/scripts/gate3_cleanup.sql`

**C 类(已清理)**

- 原文件包含 `SET statement_timeout`、多条 `TRUNCATE rb5.*` 和 `DROP TABLE IF EXISTS rb5.*`。按审计提示清理一次性 hard-code 清库脚本,现替换为 no-op `\echo`,避免误执行破坏诊断现场。

### 2.6 `rebuild5/backend/app/enrichment/pipeline.py`

**A 类(保留)**

- `rb5.*` schema 迁移保留。
- 行 374-487: `_snapshot_seed_new_cells` 中转表保留,符合审计提示 A 类"跨 colocation group JOIN 中转表"。

**待确认(已保留)**

- `_insert_snapshot_seed_records` 中 `SELECT DISTINCT ON (e.record_id, e.cell_id, e.cell_origin)` 未回滚。理由:01 §2.3 明确说该去重逻辑语义正确,不是污染源。它不是纯 Citus 必需改动,但本轮按"模糊项先保留并写待确认清单"处理。

### 2.7 `rebuild5/backend/app/profile/pipeline.py`

**A 类(保留)**

- `rb5.*` / `rb5_meta.*` schema 迁移保留。
- `STEP2_FALLBACK_CELL_RELATION = 'rb5._step2_cell_input'` 及其建表/index/analyze 逻辑保留。审计提示将 `_step2_cell_input` 归为 Citus colocation 中转表 A 类。

**交接提醒**

- 01 已证明当前 Citus runner 不物化 per-batch scope 时,该 fallback 会 stale 并导致 batch 2-7 重跑 batch 1 输入。本轮不修 bug,所以未改此处;C 阶段必须在 runner 中物化 `rb5.step2_batch_input`,并可在每批前 drop stale `_step2_cell_input` 做兜底。

### 2.8 其他文件

**A 类为主(保留)**

- `etl/clean.py`: immutable timestamptz helper 保留,解决 Citus 对时间转换函数 volatility 的限制。
- `evaluation/pipeline.py`: searched CASE / schema 迁移 / Citus CTAS 拆分保留。
- `maintenance/schema.py`, `enrichment/schema.py`: PK 扩展包含分布键、`cell_id NOT NULL`、`rb5.*` schema 保留。
- `scripts/reset_step1_to_step5_for_full_rerun_v3.sql`: reset 脚本中的 `step2_batch_input` / `_step2_cell_input` cleanup 保留,01 §4 也建议 full rerun 时使用该 reset SQL。

**待确认(已保留)**

- TA 字段链路、TA 研究脚本、device-weighted p90、ODS-020/021/022/023/024b 等数据治理改动均不在 01 指出的直接根因内。本轮没有扩大回滚范围,但这些属于非纯 Citus 语义改动,如下一阶段要求"只保留 Citus migration 最小集",需要单独产品/算法确认后再拆。

## 3. 回滚后 git status

`git status --short`:

```text
 M .gemini/settings.json
 M rebuild5/backend/app/core/__init__.py
 M rebuild5/backend/app/core/database.py
 M rebuild5/backend/app/core/parallel.py
 M rebuild5/backend/app/core/settings.py
 M rebuild5/backend/app/enrichment/pipeline.py
 M rebuild5/backend/app/enrichment/queries.py
 M rebuild5/backend/app/enrichment/schema.py
 M rebuild5/backend/app/etl/__init__.py
 M rebuild5/backend/app/etl/clean.py
 M rebuild5/backend/app/etl/fill.py
 M rebuild5/backend/app/etl/parse.py
 M rebuild5/backend/app/etl/pipeline.py
 M rebuild5/backend/app/etl/queries.py
 M rebuild5/backend/app/etl/source_prep.py
 M rebuild5/backend/app/evaluation/__init__.py
 M rebuild5/backend/app/evaluation/pipeline.py
 M rebuild5/backend/app/evaluation/queries.py
 M rebuild5/backend/app/maintenance/cell_maintain.py
 M rebuild5/backend/app/maintenance/collision.py
 M rebuild5/backend/app/maintenance/label_engine.py
 M rebuild5/backend/app/maintenance/pipeline.py
 M rebuild5/backend/app/maintenance/publish_bs_lac.py
 M rebuild5/backend/app/maintenance/publish_cell.py
 M rebuild5/backend/app/maintenance/queries.py
 M rebuild5/backend/app/maintenance/schema.py
 M rebuild5/backend/app/maintenance/window.py
 M rebuild5/backend/app/maintenance/writers.py
 M rebuild5/backend/app/profile/__init__.py
 M rebuild5/backend/app/profile/logic.py
 M rebuild5/backend/app/profile/pipeline.py
 M rebuild5/backend/app/profile/queries.py
 M rebuild5/backend/app/routers/etl.py
 M rebuild5/backend/app/routers/evaluation.py
 M rebuild5/backend/app/routers/profile.py
 M rebuild5/backend/app/routers/system.py
 M rebuild5/backend/app/service_query/queries.py
 M rebuild5/backend/app/services/__init__.py
 M rebuild5/backend/app/services/system.py
 M rebuild5/config/antitoxin_params.yaml
 M "rebuild5/docs/01b_\346\225\260\346\215\256\346\272\220\346\216\245\345\205\245_\345\244\204\347\220\206\350\247\204\345\210\231.md"
 M "rebuild5/docs/03_\346\265\201\345\274\217\350\264\250\351\207\217\350\257\204\344\274\260.md"
 M "rebuild5/docs/05_\347\224\273\345\203\217\347\273\264\346\212\244.md"
 M "rebuild5/docs/gps\347\240\224\347\251\266/cell\346\274\202\347\247\273\351\227\256\351\242\230\345\210\206\346\236\220.md"
 M rebuild5/frontend/design/src/api/maintenance.ts
 M rebuild5/frontend/design/src/views/governance/CellMaintain.vue
 M rebuild5/prompts/28_rerun_full_chain_pipelined.md
 M rebuild5/run_beijing_7d.py
 M rebuild5/scripts/archive/pre_v3/run_standard_batch_loop.py
 M rebuild5/scripts/bench_parallel.py
 M rebuild5/scripts/bench_parallel_scan.py
 M rebuild5/scripts/build_daily_sample_etl_input.py
 M rebuild5/scripts/fix4_claude_pipeline.py
 M rebuild5/scripts/rerun_step5_only.py
 M rebuild5/scripts/research_multicentroid_batch7.py
 M rebuild5/scripts/research_postgis_multicentroid_batch7.py
 M rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
 M rebuild5/scripts/reset_step2_to_step5_for_daily_rebaseline.sql
 M rebuild5/scripts/resume_full_rerun_from_batch6_step4.py
 M rebuild5/scripts/run_daily_increment_batch_loop.py
 M rebuild5/scripts/run_step1_step25_pipelined_temp.py
 M rebuild5/scripts/run_step1_to_step5_daily_loop.py
 M rebuild5/scripts/test_step5_small_sample.py
?? docs/
?? optinet_rebuild5_citus_benchmark_20260423.md
?? optinet_rebuild5_citus_fullrun_20260424.md
?? optinet_rebuild5_citus_round2_20260423.md
?? rebuild5/docs/fix5/
?? "rebuild5/docs/gps\347\240\224\347\251\266/11_TA\345\255\227\346\256\265\345\272\224\347\224\250\345\217\257\350\241\214\346\200\247\347\240\224\347\251\266.md"
?? "rebuild5/docs/gps\347\240\224\347\251\266/12_\345\215\225\350\256\276\345\244\207\346\261\241\346\237\223\344\270\216\345\212\240\346\235\203p90\346\226\271\346\241\210.md"
?? rebuild5/docs/rerun_delivery_2026-04-22_full.md
?? rebuild5/docs/rerun_delivery_2026-04-23_full.md
?? rebuild5/prompts/29_continue_anomaly_research.md
?? rebuild5/prompts/30_citus_cluster_tuning.md
?? rebuild5/prompts/30b_citus_autonomous_round2.md
?? rebuild5/prompts/30c_citus_cpu_tuning_matrix.md
?? rebuild5/prompts/31_citus_full_migration_and_rerun.md
?? rebuild5/prompts/jixu.md
?? rebuild5/scripts/gate3_cleanup.sql
?? rebuild5/scripts/run_citus_serial_batches.py
?? rebuild5/scripts/run_current_raw_batch.py
?? rebuild5/scripts/ta_trilateration_eval.py
```

`git diff --stat`:

```text
63 tracked files changed, 3566 insertions(+), 1548 deletions(-)
Largest tracked diffs:
- rebuild5/backend/app/profile/pipeline.py: 301 insertions, 240 deletions
- rebuild5/backend/app/evaluation/pipeline.py: 265 insertions, 163 deletions
- rebuild5/backend/app/maintenance/window.py: 328 insertions, 119 deletions
- rebuild5/backend/app/maintenance/publish_bs_lac.py: 122 insertions, 122 deletions
- rebuild5/backend/app/etl/parse.py: 214 insertions, 36 deletions
- rebuild5/prompts/28_rerun_full_chain_pipelined.md: 294 insertions, 7 deletions
```

未跟踪文件不在 `git diff --stat` 中;其中 `run_citus_serial_batches.py` 当前 903 行,`gate3_cleanup.sql` 当前 4 行 no-op。

## 4. 验证

- `python3 -m py_compile rebuild5/backend/app/maintenance/window.py rebuild5/backend/app/enrichment/pipeline.py rebuild5/backend/app/maintenance/label_engine.py rebuild5/backend/app/etl/parse.py rebuild5/backend/app/etl/clean.py rebuild5/backend/app/evaluation/pipeline.py rebuild5/scripts/run_citus_serial_batches.py` 通过。
- 关键 A 类保留检查通过:
  - `window.py` 仍使用 `rb5.enriched_records` / `rb5.snapshot_seed_records` / `rb5.cell_sliding_window`。
  - `etl/clean.py` 仍有 `rb5._immutable_text_to_utc_timestamptz` 和 `rb5._immutable_epoch_seconds_to_timestamptz`。
  - `core/database.py` 仍有 `create_distributed_table`。
  - `profile/pipeline.py` 仍有 `rb5._step2_cell_input`。
  - `enrichment/pipeline.py` 仍有 `rb5._snapshot_seed_new_cells`。
- 关键 C 类残留检查: `rg "max_intermediate_result_size|REBUILD5_SKIP_SLIDING_WINDOW_TRIM|SET\\s+citus|SET\\s+auto_explain|SET\\s+statement_timeout" rebuild5/backend rebuild5/scripts` 无命中。
- `rb5_bench.notes` 已通过 PG_Citus MCP 插入 `topic='fix5_audit_complete'` 完工信号。本地 `psql` 直连被沙箱网络拦截(`Operation not permitted`),未使用直连写入。

## 5. 对 C 阶段 agent 的交接

- 我回滚的 B 类改动集中在 Step 5 trim 和 label 判定,这些曾经的尝试不要直接恢复。
- A 类 Citus 基线不要回退,尤其是 `rb5.*` schema、CTAS 分布化 helper、分布键相关 PK、`_step2_cell_input` / `_snapshot_seed_new_cells`。
- C 阶段最小修复仍按 01:在 Citus runner 的 Step 1 完成后、`run_profile_pipeline()` 前调用 `materialize_step2_scope(day, input_relation='rb5.etl_cleaned')`,并删除/兜底 stale `_step2_cell_input`。
- C 阶段若要调 `citus.max_intermediate_result_size`,应按用户已批准的 C 阶段范围走全局配置/运维路径,不要在业务代码里散落 session SET。
