# loop_optim / 02b artifact 分布键 hotfix 报告

## 0. TL;DR

- 修复 `freeze_step2_input_artifact` 的 artifact Citus 布局:从沿用 `etl_cleaned` 的 `dev_id` colocation group,改为显式 `cell_id` 分布并 `colocate_with rb5.cell_sliding_window`。
- smoke artifact `rb5_stage.step2_input_b99_20251203` 验证通过:`dist_col=cell_id`,`actual_colo=7`,`expected_colo=7`。
- 03 阶段残留 cleanup 完成:`rb5_stage` 表数 0,`rb5_meta.pipeline_artifacts` 行数 0。
- 03 阶段可直接使用原 `03_rerun_prompt.md` 重跑,不需要新 prompt。

## 1. 关键 diff

修改范围只限 `rebuild5/scripts/run_daily_increment_batch_loop.py` 的 `freeze_step2_input_artifact` 函数:

- 删除从 `source_relation` 继承分布键的逻辑。
- 固定 artifact 分布键为 `cell_id`。
- 优先 colocate 到 `rb5.cell_sliding_window`。
- 如果 `cell_sliding_window` 不存在,兜底使用 `rb5.trusted_cell_library`。
- 如果两个 cell colocation target 都不存在,降级为仅按 `cell_id` 创建 distributed table,不 colocate。
- 对存在的 colocation target 强校验:必须是 hash 分布且分布列为 `cell_id`,否则 fail-fast。

## 2. Smoke 结果

smoke 输入:

```text
batch_id=99
day=2025-12-03
artifact=rb5_stage.step2_input_b99_20251203
row_count=15
```

验证 SQL 输出:

```text
rel                                      dist_col  expected_colo  actual_colo
rb5_stage.step2_input_b99_20251203       cell_id   7              7
```

结论:artifact 分布键为 `cell_id`,且 colocationid 与 `rb5.cell_sliding_window` 匹配。

## 3. 03 阶段残留 cleanup

执行 cleanup:

- `DROP TABLE IF EXISTS rb5_stage.step2_input_b1_20251201` 到 `b7_20251207`
- `DELETE FROM rb5_meta.pipeline_artifacts`

smoke 后二次 cleanup:

- `DROP TABLE IF EXISTS rb5_stage.step2_input_b99_20251203`
- `DELETE FROM rb5_meta.pipeline_artifacts WHERE batch_id = 99`

最终验证:

```text
information_schema.tables WHERE table_schema='rb5_stage' = 0
rb5_meta.pipeline_artifacts = 0
```

## 4. 静态验证

```text
python3 -m py_compile rebuild5/scripts/run_daily_increment_batch_loop.py
PASS
```

## 5. 给 03 重跑的输入

- `rebuild5/docs/loop_optim/03_rerun_prompt.md` 无修改,直接重跑。
- 03 重跑前仍按 prompt 跑 reset SQL;reset 已在 02 阶段负责 drop `rb5_stage` 并 truncate state。
- 02b 已解除 03 blocker 中的 artifact distkey mismatch:`etl_cleaned/dev_id` 不再传染到 Step2 artifact。
