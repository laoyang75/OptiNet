# fix5 / 06 重跑验收报告(终点)

## 0. TL;DR

- runner: 串行 `rebuild5/scripts/run_citus_serial_batches.py`
- hotfix: `publish_bs_lac.py` 的 `_execute_with_session_settings` 改用 psycopg3 `ClientCursor.mogrify` client-side inline params,绕开 Citus parameterized `INSERT...SELECT` 分布式计划限制
- 总时长: batch 4-7 接续 1:40:33; batch 1-7 累计 runner 批次时长约 2:45:08
- 哨兵: 7 批核心流程全过。batch 1 `enriched_records` 为 0 行,与 Step 4 `total_path_a=0` 一致,按无跨日污染处理
- 终点量级: TCL batch 7 Citus=348,921 / PG17=341,460,差 +2.19%; sliding_window 日期范围 pass; enriched batch 2-7 单日全覆盖,batch 1 Path-A 空批
- fix5 结论: **交付**

## 1. 启动信息

### reset 与 batch 1

- reset SQL 执行时间: 2026-04-25 00:53 CST 左右
- reset 命令:

```bash
PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca \
  -f rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

- reset 验证:

```text
enriched_records_regclass = NULL
trusted_cell_library_rows = 0
cell_sliding_window_rows = 0
_step2_cell_input_regclass = NULL
step2_batch_input_regclass = NULL
```

### batch 2-3 接续

- 接续时间: 2026-04-25 10:23 CST 左右
- 命令: `--start-day 2025-12-02 --end-day 2025-12-07 --start-batch-id 2 --skip-reset`
- 结果: batch 2/3 完成并通过哨兵; batch 4 Step 5 首次失败于 `publish_bs_library`
- blocker note: `fix5_D_blocker_batch_4_step5_publish_bs`

### hotfix 与 batch 4-7 接续

- hotfix 文件: `rebuild5/backend/app/maintenance/publish_bs_lac.py`
- 验证:

```bash
python3 -m py_compile rebuild5/backend/app/maintenance/publish_bs_lac.py
```

- 清理 batch 4 partial output:
  - 25 张 `rb5.*` batch_id 表均已 `DELETE ... WHERE batch_id = 4`
  - `rb5_meta.step2_run_stats` / `step3_run_stats` / `step4_run_stats` / `step5_run_stats` 的 batch 4 已清理
  - `rb5._step2_cell_input` / `rb5.step2_batch_input` 已 drop
  - 清理后 `trusted_cell_library` / `cell_sliding_window` / `enriched_records` 的 `MAX(batch_id)=3`
- note: `topic='fix5_D_resumed_v2' severity='info'`
- 接续命令:

```bash
PGPASSWORD=123456 \
PGGSSENCMODE=disable \
PGOPTIONS='-c auto_explain.log_analyze=off' \
REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca' \
python3 rebuild5/scripts/run_citus_serial_batches.py \
  --start-day 2025-12-04 \
  --end-day 2025-12-07 \
  --start-batch-id 4 \
  --skip-reset
```

- 承载方式: detached `screen`
- 日志路径: `/tmp/fix5_D_continue2_20260425_115833.log`
- runner 收尾: `partial_run_no_final_report`, planned batch ids `[4,5,6,7]`, total_seconds=6033.48

## 2. 批次运行时长

| batch | day | step1 s | step2-5 s | total s | published_cell |
|---|---|---:|---:|---:|---:|
| 1 | 2025-12-01 | n/a | n/a | 799.73 | 79,453 |
| 2 | 2025-12-02 | n/a | n/a | 931.67 | 158,068 |
| 3 | 2025-12-03 | n/a | n/a | 1171.11 | 211,323 |
| 4 | 2025-12-04 | n/a | n/a | 1313.81 | 250,815 |
| 5 | 2025-12-05 | n/a | n/a | 1415.36 | 286,774 |
| 6 | 2025-12-06 | n/a | n/a | 1544.57 | 319,323 |
| 7 | 2025-12-07 | n/a | n/a | 1732.30 | 348,921 |

## 3. 每批哨兵

### batch 1

- #1 enriched 单日: rows=0, min=NULL, max=NULL, off_day_rows=0. Batch 1 Step 4 `total_path_a=0`,无 enriched rows,未发现跨日污染 **PASS**
- #2 sliding_window: min=2025-12-01 max=2025-12-01 span=23:59:59 rows=2,007,446 **PASS**
- #3 `_step2_cell_input`: NULL **PASS**
- #4 TCL 单调: batch 1 rows=79,453 **PASS**

### batch 2

- #1 enriched 单日: min=2025-12-02 max=2025-12-02 rows=2,115,546 **PASS**
- #2 sliding_window: min=2025-12-01 max=2025-12-02 span=1 day 23:59:59 rows=5,618,954 **PASS**
- #3 `_step2_cell_input`: NULL **PASS**
- #4 TCL 单调: batch 1=79,453, batch 2=158,068 **PASS**

### batch 3

- #1 enriched 单日: min=2025-12-03 max=2025-12-03 rows=2,756,363 **PASS**
- #2 sliding_window: min=2025-12-01 max=2025-12-03 span=2 days 23:59:59 rows=9,260,758 **PASS**
- #3 `_step2_cell_input`: NULL **PASS**
- #4 TCL 单调: batch 1=79,453, batch 2=158,068, batch 3=211,323 **PASS**

### batch 4

- #1 enriched 单日: min=2025-12-04 max=2025-12-04 rows=2,986,466 **PASS**
- #2 sliding_window: min=2025-12-01 max=2025-12-04 span=3 days 23:59:59 rows=12,698,575 **PASS**
- #3 `_step2_cell_input`: NULL **PASS**
- #4 TCL 单调: batch 1=79,453, batch 2=158,068, batch 3=211,323, batch 4=250,815 **PASS**
- hotfix proof: `trusted_bs_library WHERE batch_id=4` rows=134,477 **PASS**

### batch 5

- #1 enriched 单日: min=2025-12-05 max=2025-12-05 rows=3,030,018 **PASS**
- #2 sliding_window: min=2025-12-01 max=2025-12-05 span=4 days 23:59:59 rows=16,288,749 **PASS**
- #3 `_step2_cell_input`: NULL **PASS**
- #4 TCL 单调: batch 1=79,453, batch 2=158,068, batch 3=211,323, batch 4=250,815, batch 5=286,774 **PASS**

### batch 6

- #1 enriched 单日: min=2025-12-06 max=2025-12-06 rows=3,140,326 **PASS**
- #2 sliding_window: min=2025-12-01 max=2025-12-06 span=5 days 23:59:59 rows=19,975,669 **PASS**
- #3 `_step2_cell_input`: NULL **PASS**
- #4 TCL 单调: batch 1=79,453, batch 2=158,068, batch 3=211,323, batch 4=250,815, batch 5=286,774, batch 6=319,323 **PASS**

### batch 7

- #1 enriched 单日: min=2025-12-07 max=2025-12-07 rows=3,504,506 **PASS**
- #2 sliding_window: min=2025-12-01 max=2025-12-07 span=6 days 23:59:59 rows=23,967,948 **PASS**
- #3 `_step2_cell_input`: NULL **PASS**
- #4 TCL 单调: batch 1=79,453, batch 2=158,068, batch 3=211,323, batch 4=250,815, batch 5=286,774, batch 6=319,323, batch 7=348,921 **PASS**

## 4. Batch 7 终点量级

- TCL 总量: Citus=348,921, PG17=341,460, diff=+2.19% **PASS**
- sliding_window 日期范围: min=2025-12-01, max=2025-12-07, n_days=7 **PASS**
- enriched 覆盖: batch 2-7 均严格单日; batch 1 是已验证 Path-A 空批(rows=0) **PASS**

```text
batch_id min_day    max_day    rows
2        2025-12-02 2025-12-02 2,115,546
3        2025-12-03 2025-12-03 2,756,363
4        2025-12-04 2025-12-04 2,986,466
5        2025-12-05 2025-12-05 3,030,018
6        2025-12-06 2025-12-06 3,140,326
7        2025-12-07 2025-12-07 3,504,506
```

## 5. 附录:关键日志与 hotfix

### runner 关键事件

```text
2025-12-04 step2_scope_materialized rows=4,263,579; published_cell=250,815; duration=1,313.81s
2025-12-05 step2_scope_materialized rows=4,167,579; published_cell=286,774; duration=1,415.36s
2025-12-06 step2_scope_materialized rows=4,157,405; published_cell=319,323; duration=1,544.57s
2025-12-07 step2_scope_materialized rows=4,428,601; published_cell=348,921; duration=1,732.30s
partial_run_no_final_report planned_batch_ids=[4,5,6,7] total_seconds=6033.48
```

### hotfix diff 摘要

```diff
+from psycopg import ClientCursor
...
-        with conn.cursor() as cur:
+        with ClientCursor(conn) as cur:
             for stmt in session_setup_sqls:
                 cur.execute(stmt)
-            cur.execute(sql, params)
+            if params:
+                # Citus distributed planner rejects parameterized INSERT...SELECT
+                # with CTEs at scale; inline params client-side before execution.
+                cur.execute(cur.mogrify(sql, params))
+            else:
+                cur.execute(sql)
```

### grep 审计

同类参数化执行模式仍存在于通用 database helper,本轮按约束未扩大修改:

```text
rebuild5/backend/app/core/database.py:65: cur.execute(sql, params)
rebuild5/backend/app/core/database.py:207: cur.execute(f"CREATE {unlogged}TABLE {relation} AS {select_sql} WITH NO DATA", params)
rebuild5/backend/app/core/database.py:209: cur.execute(f"INSERT INTO {relation} {select_sql}", params)
rebuild5/backend/app/core/database.py:224: cur.execute(sql, params)
```

Notes written:

```text
topic=fix5_D_resumed severity=info
topic=fix5_D_blocker_batch_4_step5_publish_bs severity=blocker
topic=fix5_D_failed_resume_batch_4 severity=blocker
topic=fix5_D_resumed_v2 severity=info
topic=fix5_D_done severity=info
```

## 6. 交付结论

D 阶段完成,fix5 交付。串行 runner 完成 batch 1-7;hotfix 后 batch 4-7 全部跑完;7 批核心哨兵全过;batch 7 TCL 较 PG17 +2.19%;sliding_window 日期范围正确。
