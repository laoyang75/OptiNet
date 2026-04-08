# agent collaboration

这里用于多 agent 独立出稿与统一合并。

结构：

- `prompts/`：给 Codex / Claude / Gemini 的独立 prompt
- `outputs/`：三路 agent 的草案输出
- `merge/`：合并原则、冲突矩阵、收敛说明

规则：

- 三路 agent 先独立出稿，不互相覆盖
- 合并前不得直接把任一路草稿当最终结论
- 合并时必须保留冲突点记录
