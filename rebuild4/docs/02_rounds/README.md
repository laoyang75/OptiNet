# rounds

这里是 3 轮评估 + 1 轮 finalization 冻结的协作区。

- `round1_plan/`：总体评估与计划
- `round2_detail/`：细化设计
- `round3_execution/`：最终执行任务草案
- `finalization/`：最终冻结与任务书生成输入

每一轮都遵循同一个模式：

- 同题 prompt
- 3 个 agent 独立输出
- 主控合并
- 必要时人类裁决

finalization 结束后，再编制到 `03_final/`。
