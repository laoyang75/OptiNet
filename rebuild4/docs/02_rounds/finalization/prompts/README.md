# prompts

本目录中的 prompt 使用顺序：

1. `00_共享约束.md`
2. `01_codex_prompt.md`
3. `02_claude_prompt.md`
4. `03_gemini_prompt.md`
5. `90_merge_prompt.md`
6. `91_decision_prompt.md`
7. `92_taskbook_generation_prompt.md`

说明：

- 前 4 个用于 3 个 agent 的同题冻结编制
- `90` 用于主控合并
- `91` 用于抽取需要人类裁决的问题
- `92` 用于把 finalization 合并稿编制成 `03_final/` 正式文件
