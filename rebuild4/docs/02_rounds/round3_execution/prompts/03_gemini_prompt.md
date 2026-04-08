# Gemini Prompt - Round 3 Execution

请完成 rebuild4 第 3 轮“最终执行任务文档”的独立输出。

这是最高约束轮次。禁止偷懒，禁止只复述前两轮，禁止跳过页面检查，禁止只写概念任务。

## 你必须完成的动作

1. 列出你实际阅读的文档清单
2. 列出你实际检查过的页面清单
3. 列出你实际执行过的 PG17 查询主题
4. 再进入正式输出
5. 如果有任何一个动作没有完成，必须明确写 blocked，不允许补写推测内容

## 强制工具要求

- 你必须使用 Antigravity 浏览器检查页面
- 你必须使用 `PG17 MCP`
- 不允许假装已经检查页面
- 如果页面无法检查，必须明确写 blocked，不能编造结果

## 每个输出文件必须具备的结构

每一章都必须写：

- 结论
- 依据（文件路径 / 页面 / PG17）
- 风险
- 校验
- 若失败如何处理

## 页面证据硬要求

你必须至少对页面写出：

- 页面路径
- 页面主语是否明确
- `data_origin` 是否可见
- 是否符合 UI_v2 语义
- 是否能支撑最终执行任务的验收设计

## 最低页面覆盖要求

你至少必须检查这些页面或等价页面：

- `/runs`
- `/flow/overview`
- `/flow/snapshot`
- `/objects`
- `/baseline`
- `/initialization`
- `/governance`
- `/validation/compare`
- 至少 1 个画像页

并且至少要验证 1 条下钻链路：

- `/runs -> /flow/overview -> /flow/snapshot -> /objects -> detail -> /baseline`

## 你必须阅读：

- `rebuild4/docs/00_runbook/00_Runbook.md`
- `rebuild4/docs/02_rounds/round3_execution/00_round_goal.md`
- `rebuild4/docs/02_rounds/round3_execution/prompts/00_共享约束.md`
- `rebuild4/docs/02_rounds/round1_plan/merged/*`
- `rebuild4/docs/02_rounds/round2_detail/merged/*`
- `rebuild4/docs/02_rounds/round1_plan/decisions/*`（如果有）
- `rebuild4/docs/02_rounds/round2_detail/decisions/*`（如果有）
- `rebuild4/docs/01_inputs/*`

你必须生成到：`rebuild4/docs/02_rounds/round3_execution/outputs/gemini/`

文件：

1. `01_最终执行任务书草案.md`
2. `02_逐步校验与验收清单草案.md`
3. `03_候选裁决问题.md`

额外硬约束：

- 不允许省略页面证据表
- 不允许省略自检清单
- 不允许把“看起来合理”当成“已验证”
- `01_最终执行任务书草案.md` 至少必须包含：
  - 分阶段执行步骤
  - 每步输入/输出
  - 每步 PG17/API/页面校验
  - 每步失败回退动作
- `02_逐步校验与验收清单草案.md` 至少必须包含：
  - 文档检查
  - 数据检查
  - API 检查
  - 页面检查
  - 链路检查
- `03_候选裁决问题.md` 只能放真正卡住最终任务书的问题
- 最后一节必须写“我最可能遗漏的部分”
