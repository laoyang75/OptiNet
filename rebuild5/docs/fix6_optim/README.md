# fix6_optim — OptiNet rebuild5 加速 + 结构稳健化

fix5 解决了 Citus 迁移**可行性**(7 批能跑通,数据对齐 PG17 ±2%)。
**fix6_optim 解决加速**:让"改一行代码 → 拿到新数据"的研究循环从 ~2 小时压到 < 30 分钟。

## 元目标(按重要性排序)

1. **加速研究循环** —— pipelined 并行 Step 1 / Step 2-5,目标全链路 < 30 分钟
2. **代码稳健** —— 抽 Citus 兼容层、补回归测试,让后续频繁改动不互相打架
3. **可迭代** —— runbook 标准化,"改 → 跑 → 验"有标准命令,不再现场拼 prompt

## 阶段表

| 阶段 | 谁 | Prompt | 产出 | 依赖 |
|---|---|---|---|---|
| **01 收尾** | agent | `01_finalize_and_commit_prompt.md` | `01_finalize_report.md` + GitHub 上的 commit | — |
| **02A 审计**(只读) | agent | `02A_audit_prompt.md` | `02A_audit_report.md` | 01 |
| **02B 重构**(改代码) | agent | `02B_refactor_prompt.md` ← 02A 完成后由 Claude 写 | `02B_refactor_report.md` + `core/citus_compat.py` | 02A |
| **02C 测试**(建测试) | agent | `02C_test_prompt.md` ← 02B 完成后由 Claude 写 | `02C_test_report.md` + `tests/` 套件 | 02B |
| **03 pipelined 加速** | agent | `03_pipelined_prompt.md` ← 02C 完成后由 Claude 写 | `03_pipelined_report.md` + `run_citus_pipelined_batches.py` | 02C |
| **04 Runbook** | agent | `04_runbook_prompt.md` ← 03 完成后由 Claude 写 | `04_runbook.md` + `scripts/runbook/*.sh` | 03 |
| **UI 跟进**(支线) | agent | `0X_ui_followup_prompt.md` ← 任何时候插 | `0X_ui_followup_report.md` + 前端 PR | — |

## 协作模式(2026-04-25 起调整,详见 `_prompt_template.md` § 11/§ 12)

- **Claude(我)**:写 prompt + review 上游 agent 报告 + 决定下一阶段范围
- **独立 agent**:执行 prompt + 自主判断(无需开跑前 ack)+ 完工自动 commit/push + 写报告 + 写 note
- **用户(你)**:只在阶段切换时介入("X 完成了")+ blocker 时拍板;不再每步 ack
- **上下游 agent 互相审核**:下游必读上游报告,发现误判要在自己报告 §0 显式修订

每个 prompt 都套 `_prompt_template.md`,12 字段不漏。

## 边界(整个 fix6_optim)

- ❌ 不动旧库 PG17(192.168.200.217:5433/ip_loc2,只读基线)
- ❌ 不重做 fix5 已交付的事(scope 物化 / trim / ALTER SYSTEM / publish_bs hotfix)
- ❌ 不在 main 分支以外的地方部署(本地研究,只 push GitHub)
- ❌ 不引入新依赖(除非 02 审计明确需要,且事先 ack)
- ✅ 每阶段产出报告 + notes 完工信号
- ✅ commit 必须分层级(代码 / 脚本 / 文档分开,见 01 阶段)

## 当前状态(2026-04-25)

- [x] 01 收尾 — `01_finalize_report.md` 已出,head=`4b23cd0`
- [x] 02A 审计(只读)— `02A_audit_report.md` 已出,head=`72cadc3`
- [x] 02B 重构 — `02B_refactor_report.md` 已出,新增 `core/citus_compat.py`,head=见 02B 完工 commit
- [x] 02C 测试 — `02C_test_report.md` 已出,5 个新增测试文件,head=见 02C 完工 commit
- [ ] 03 pipelined — 等 02C
- [ ] 04 Runbook — 等 03
- [ ] UI 支线 — 任何时候

## 引用 fix5 关键产出(整个 fix6_optim 期间共用)

- `rebuild5/docs/fix5/01_quality_diagnosis.md` —— 根因诊断
- `rebuild5/docs/fix5/04_code_fix_report.md` —— C 阶段代码改动清单
- `rebuild5/docs/fix5/06_rerun_validation.md` —— D 阶段验收 + hotfix 记录
- `rb5_bench.notes topic LIKE 'fix5_%'` —— 历史 blocker / 决策 trail

## 启动

第一次:开新对话 → 把 `01_finalize_and_commit_prompt.md` 贴进去给 agent。
后续:按 fix5 节奏,Claude 写 prompt → user 开 agent 对话 → Claude review。
