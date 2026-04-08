# Gemini Prompt - Round 2 Detail

请完成 rebuild4 第 2 轮“细化设计”的独立输出。

这是一个高约束任务，禁止偷懒，禁止只写概要，禁止跳过表格和校验章节。

## 强制工作方式

1. 先列出你实际阅读的输入文件
2. 每一部分必须写：
   - 结论
   - 依据（文件路径或 PG17 查询对象）
   - 风险
   - 校验
3. 所有表/字段/API/Gate 都要落到明确结构
4. 不允许使用“后续再定”“视情况而定”之类模糊结论，除非明确列入裁决问题
5. 结尾必须写：
   - 自检清单
   - 可能遗漏点
   - 你认为最危险的 3 个未决问题
6. 你必须按固定章节输出，不允许跳过实体、字段、接口、Gate、校验任一章节

你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/round2_detail/00_round_goal.md`
- `rebuild4/docs/02_rounds/round2_detail/prompts/00_共享约束.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/*`
- `rebuild4/docs/02_rounds/round1_plan/decisions/*`（如果有）
- `rebuild4/docs/01_inputs/*`

你必须生成到：`rebuild4/docs/02_rounds/round2_detail/outputs/gemini/`

文件：

1. `01_细化设计总稿.md`
2. `02_实体字段接口与Gate细化.md`
3. `03_候选裁决问题.md`

额外硬约束：

- 本轮禁止访问页面
- 所有数据库事实必须用 `PG17 MCP execute_sql`
- 不允许省略字段级、接口级、Gate 级校验
- `01_细化设计总稿.md` 至少必须包含：
  - 实体清单
  - `data_origin` 合同
  - 页面/API/表主语对齐要求
- `02_实体字段接口与Gate细化.md` 至少必须包含：
  - 关键表与字段矩阵
  - API 输入输出约束
  - Gate 条件与阻断动作
- `03_候选裁决问题.md` 只允许列真正需要人类裁决的问题
