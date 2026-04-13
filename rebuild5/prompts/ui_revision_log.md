# rebuild5 UI 分阶段修订记录

> 本文件用于记录 `14b_UI分阶段交互修订.md` 的执行进度。  
> 新会话开始时，先读本文件确认当前阶段，再决定继续哪个页面组。  
> 当前策略：**先出逐页意见单，再进入代码实施**。

## 当前总状态

- 全局语义基线：done
- 术语底表：done
- 逐页修订：pending
- 当前执行模式：review-first（先意见，后实施）
- 最后更新时间：2026-04-10

## 已确认的基础文件

| 文件 | 作用 | 状态 |
|------|------|------|
| `rebuild5/docs/fix/ui_global_alignment.md` | 全局语义对齐基线 | done |
| `rebuild5/docs/fix/ui_alignment_questions.md` | 待决策问题清单 | done |
| `rebuild5/docs/fix/ui_term_glossary.md` | 最终 UI 术语底表 | done |
| `rebuild5/prompts/14b_UI分阶段交互修订.md` | 逐页推进 prompt | done |

## 当前已确认的执行原则

1. 不再采用“先把所有页面代码一起改掉”的方式。
2. 默认流程改为：
   - 先处理一个页面组
   - 先输出该页面组的逐页意见单
   - 用户审阅方向后，再进入实施阶段
3. 每轮必须更新本记录文件，保证中断后可继续。
4. 术语以 `ui_term_glossary.md` 为底表，但逐页意见允许根据页面角色做轻微语气调整。
5. 不矫枉过正：
   - `Cell / BS / LAC` 可保留
   - 但 `donor`、`Path A/B/C`、`active` 不应继续作为 UI 一级表达
6. Tag 允许缩写，但前提是标准中文已经统一。

## 页面组总进度

| 页面组 | 意见单状态 | 实施状态 | 备注 |
|--------|------------|----------|------|
| 全局运行控制页面组 | pending | pending | 含数据集、运行历史、版本条 |
| ETL 页面组 | pending | pending | 含数据源、字段审计、解析、清洗、补齐 |
| 路由页面组 | pending | pending | 含基础画像与分流 |
| 评估页面组 | pending | pending | 含总览、Cell、BS、LAC |
| 知识补数页面组 | pending | pending | 含 Step 4 页面 |
| 治理页面组 | pending | pending | 含总览、Cell、BS、LAC 维护 |
| 服务层页面组 | pending | pending | 含查询、覆盖、报表 |

## 当前建议的推进方式

- 每次只推进一个页面组
- 页面组内必须拆成逐页意见
- 每页至少给出：
  - 页面真实职责
  - 当前主要问题
  - 推荐标题
  - 推荐卡片/表头/tag/tooltip
  - 需要替换的关键术语
  - 是否涉及待决策问题

## 最新结论（阶段切换记录）

### 2026-04-10 — 建立逐页推进工作流

- 背景：用户明确要求不要直接全面改代码，而是先修改 prompt，然后像之前一样逐页推进，并且必须保留可续跑记录。
- 已完成：
  - 收敛最终术语底表 `rebuild5/docs/fix/ui_term_glossary.md`
  - 改写 `rebuild5/prompts/14b_UI分阶段交互修订.md`
  - 建立本记录文件 `rebuild5/prompts/ui_revision_log.md`
- 当前结论：
  - 后续工作以“页面组意见单 -> 页面组实施”双阶段执行
  - 本文件作为恢复执行入口
- 下一步建议：
  - 选择一个页面组，开始输出逐页意见单

## 恢复执行说明

如果会话中断，下一次继续时按下面顺序操作：

1. 先读本文件
2. 确认上次停在哪个页面组、哪个阶段（意见单 / 实施）
3. 再读：
   - `rebuild5/docs/fix/ui_term_glossary.md`
   - `rebuild5/docs/fix/ui_global_alignment.md`
   - `rebuild5/docs/fix/ui_alignment_questions.md`
4. 从“下一步建议”的页面组继续推进
