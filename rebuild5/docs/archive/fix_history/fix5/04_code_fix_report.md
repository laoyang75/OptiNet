# fix5 / 04 代码修复 + 战术优化报告

## 0. TL;DR

- 已完成: Citus 串行 runner 在 Step 1 后物化 per-batch `rb5.step2_batch_input`,并在物化前 drop stale `rb5._step2_cell_input`。
- 已完成: `cell_sliding_window` trim 保持原 retention 语义,但从 `ctid` 删除改为主键删除,避开 Citus distributed DELETE 对 `ctid` 的限制。
- 已完成: coordinator 全局执行 `ALTER SYSTEM SET citus.max_intermediate_result_size = '16GB'`,并 `pg_reload_conf()`; `SHOW` 结果为 `16GB`。
- 已验证: batch 1 / batch 2 单批哨兵通过,`step2_batch_input` 严格按日推进,`_step2_cell_input` 不存在,`cell_sliding_window` 无 2023/2024 脏跨度。
- 已推迟: pipelined runner。串行 bugfix 已跑通;流水线建议新脚本实现,不要污染串行 fallback。

## 1. 改动清单

| 文件 | 动作 | 对应 01 | 状态 |
| --- | --- | --- | --- |
| `rebuild5/scripts/run_citus_serial_batches.py` | import `materialize_step2_scope` | 01 §3 修复 A | 已完成 |
| `rebuild5/scripts/run_citus_serial_batches.py` | Step 1 后 drop `_step2_cell_input`,再物化 `step2_batch_input` | 01 §3 修复 A | 已完成 |
| `rebuild5/scripts/run_citus_serial_batches.py` | 单批/双批验证时不写 7 批 fullrun report | C 阶段验证兼容 | 已完成 |
| `rebuild5/backend/app/maintenance/window.py` | trim 删除从 `ctid` 改成 `(batch_id, source_row_uid, cell_id)` key delete | Citus 兼容,不改 retention 条件 | 已完成 |
| `rebuild5/backend/app/profile/pipeline.py` | fallback 过期保护 | 01 §3 修复 C | 未采纳;验证中 fallback 未触达 |

## 2. 逐段 diff

### 2.1 runner materialize_step2_scope

关键行:

```text
rebuild5/scripts/run_citus_serial_batches.py:35
from rebuild5.scripts.run_daily_increment_batch_loop import materialize_step2_scope

rebuild5/scripts/run_citus_serial_batches.py:830
execute("DROP TABLE IF EXISTS rb5._step2_cell_input")
scope_rows = materialize_step2_scope(day=day, input_relation="rb5.etl_cleaned")
_log({"event": "step2_scope_materialized", "day": day.isoformat(), "rows": scope_rows})
```

### 2.2 Citus trim 兼容

原 `ctid` 版本在 batch 1 Step 5 失败:

```text
cannot perform distributed planning for the given modification
DETAIL: Recursively planned distributed modifications with ctid on where clause are not supported.
```

已改为按 `cell_sliding_window` 主键删除。retention 条件未变:

```text
event_time_std >= latest_event_time - INTERVAL '14 days'
OR obs_rank <= 1000
```

关键行:

```text
rebuild5/backend/app/maintenance/window.py:148
delete_keys AS (
    SELECT batch_id, source_row_uid, cell_id
    FROM ranked
    WHERE NOT (...)
)
DELETE FROM rb5.cell_sliding_window w
USING delete_keys d
WHERE w.batch_id = d.batch_id
  AND w.source_row_uid = d.source_row_uid
  AND w.cell_id = d.cell_id
```

### 2.3 partial run report guard

`run_citus_serial_batches.py` 原 final report 只适合 7 批全量,单批验证会在所有业务步骤成功后抛:

```text
final batch coverage check failed: found batch_ids=[1]
```

已加 guard: planned batch ids 不是 1-7 时,只打印 `partial_run_no_final_report` 并正常返回。全量 D 阶段不受影响。

### 2.4 Citus 参数

执行:

```sql
ALTER SYSTEM SET citus.max_intermediate_result_size = '16GB';
SELECT pg_reload_conf();
SHOW citus.max_intermediate_result_size;
```

结果:

```text
pg_reload_conf: true
citus.max_intermediate_result_size: 16GB
```

### 2.5 auto_explain 运行条件

runner 首次 batch 1 在 Step 1 parse 阶段失败:

```text
EXPLAIN ANALYZE is currently not supported for INSERT ... SELECT commands via coordinator
```

检查结果:

```text
auto_explain.log_analyze = on
source = command line
```

`ALTER SYSTEM` 无法覆盖 command-line 来源。验证运行使用进程级:

```bash
PGOPTIONS='-c auto_explain.log_analyze=off'
```

这是运行环境覆盖,未在业务代码里添加 session SET。

## 3. 单批验证

### batch 1(day=2025-12-01)

runner 关键日志:

```text
raw_count=3,885,832
step2_scope_materialized rows=4,682,393
published_cell_count=79,453
duration_seconds=817.70
```

哨兵:

```text
step2_batch_input: 2025-12-01 00:00:00+00 -> 2025-12-01 23:59:59+00, rows=4,682,393
_step2_cell_input: NULL
cell_sliding_window span: 23:59:59, min=2025-12-01, max=2025-12-01
trusted_cell_library: stable=78,364, insufficient=1,089
label_results k_eff: 0=79,623, 1=51, 2=8
```

PG17 batch 1 对比:

```text
trusted_cell_library: total=79,682, stable=78,619, insufficient=1,063
label_results k_eff: 0=79,389, 1=57, 2=7
```

结论: pass。TCL 总量差约 -0.29%,stable 差约 -0.32%,在 ±5% 内。

### batch 2(day=2025-12-02)

runner 关键日志:

```text
raw_count=3,893,994
step2_scope_materialized rows=4,740,558
path_a_record_count=2,115,546
published_cell_count=158,068
multi_centroid_cell_count=1
duration_seconds=1026.54
```

哨兵:

```text
enriched_records batch 2: min=2025-12-02, max=2025-12-02, rows=2,115,546
step2_batch_input: 2025-12-02 00:00:00+00 -> 2025-12-02 23:59:59+00, rows=4,740,558
_step2_cell_input: NULL
cell_sliding_window span: 1 day 23:59:59, min=2025-12-01, max=2025-12-02
trusted_cell_library: stable=156,344, insufficient=1,724
label_results k_eff: 0=158,267, 1=190, 2=41, 3=1
```

PG17 batch 2 对比:

```text
trusted_cell_library: total=158,499, stable=156,821, insufficient=1,678
label_results k_eff: 0=157,834, 1=191, 2=42, 3=1
```

结论: pass。TCL 总量差约 -0.27%,stable 差约 -0.30%,在 ±5% 内;scope 已从 batch 1 推进到 batch 2。

## 4. 已知问题 / 交接 D 阶段

- D 阶段开始前建议再次执行 full reset,再跑 batch 1-7。
- D 阶段 runner 命令需要带 `PGOPTIONS='-c auto_explain.log_analyze=off'`,除非运维侧把 command-line 来源的 `auto_explain.log_analyze` 改掉。
- Pipelined 并行推迟。建议新建 `run_citus_pipelined_batches.py`,复用本次已验证的 per-batch scope 修复,不要重构串行 runner。
- `get_step2_input_relation()` fallback 过期保护未加。batch 1/2 验证中 `_step2_cell_input` 为 NULL,说明 runner scope 物化路径生效。

## 5. notes

- 早期因沙箱网络写过 `topic='fix5_C_blocker'`;该 blocker 后续已被用户配置调整解除。
- 本阶段完成后写入 `topic='fix5_C_done'`。
