# docs consolidation inventory

生成时间: 2026-04-28  
范围: `rebuild5/docs/`  
用途: 作为本轮文档整合的 ground truth,后续每个移动/修订决策都回看本文件。

## 1. 扫描摘要

| 项目 | 数值 | 说明 |
|---|---:|---|
| Markdown 文件总数 | 161 | `find rebuild5/docs -name "*.md"` 实测 |
| 顶层权威文件 | 6 | `README / PROJECT_STATUS / CLUSTER_USAGE / runbook / 处理流程总览 / 术语对照表` |
| 顶层核心开发文档 | 13 | `00-11`(含 `01a/01b`) |
| 历史 trail 目录文件数 | 130 | `fix* / fix6_optim / loop_optim / upgrade / dev / human_guide / gps研究` 内全部 `.md` |
| 顶层待归档散文件 | 9 | `rerun_delivery_* / 重跑* / 样例速度优化* / 速度优化评估* / runbook_v5.md` |
| 当前 active 研究文件 | 2 | `gps1/README.md` + `gps1/01_research_restart_prompt.md` |
| 工作 prompt | 1 | `DOC_CONSOLIDATION_PROMPT.md`,阶段 7 再归档 |
| 过时关键词命中 | 39 | 阶段 3 的修订输入 |
| 目录内 Markdown 链接命中 | 104 | 阶段 2/6 的修链与验证输入 |

## 2. 推荐处理总表

| Scope / File | Last Commit Time | Recommended Handling | Reason |
|---|---|---|---|
| `rebuild5/docs/README.md` | 2026-04-13 19:30:05 +0800 | phase 4 重写 + phase 5 对齐 | 顶层入口仍保留 PG17/`runbook_v5` 时代内容,需要改成扁平 navigation。 |
| `rebuild5/docs/PROJECT_STATUS.md` | untracked in current worktree | phase 2/5 修链对齐 | 顶层状态标尺,大量指向将被归档的目录。 |
| `rebuild5/docs/CLUSTER_USAGE.md` | 2026-04-28 11:39:52 +0800 | phase 2/5 修链对齐 | 当前集群原则权威文档,少量链接将改指向 `archive/`。 |
| `rebuild5/docs/runbook.md` | untracked in current worktree | phase 2/5 修链对齐 | 顶层操作入口,当前仍直接指向 `fix6_optim/` / `upgrade/`。 |
| `rebuild5/docs/处理流程总览.md` | 2026-04-21 11:22:01 +0800 | keep authority | 业务状态机主线,当前未见 A-D 类过时环境信息。 |
| `rebuild5/docs/术语对照表.md` | 2026-04-13 19:30:05 +0800 | keep authority | 术语权威文档,业务规则类内容不动。 |
| `rebuild5/docs/00_全局约定.md` | 2026-04-13 18:53:57 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/01a_数据源接入_功能要求.md` | 2026-04-13 11:05:04 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/01b_数据源接入_处理规则.md` | 2026-04-25 16:22:46 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/02_基础画像.md` | 2026-04-13 18:53:57 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/03_流式质量评估.md` | 2026-04-25 16:22:46 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/04_知识补数.md` | 2026-04-13 18:53:57 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/05_画像维护.md` | 2026-04-25 16:22:46 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,命中 2 处旧 schema 示例。 |
| `rebuild5/docs/06_服务层_运营商数据库与分析服务.md` | 2026-04-13 11:05:04 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/07_数据集选择与运行管理.md` | 2026-04-10 17:37:48 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/08_UI设计.md` | 2026-04-09 01:56:37 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,只改 A-D 类信息。 |
| `rebuild5/docs/09_控制操作_初始化重算与回归.md` | 2026-04-13 18:53:57 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,修正 runbook/脚本路径和环境说明。 |
| `rebuild5/docs/10_调试期结果保留与字段口径提示.md` | 2026-04-13 11:05:04 +0800 | phase 3 deep revise | 核心开发文档,补更新声明,修正文中 schema 前缀。 |
| `rebuild5/docs/11_核心表说明.md` | 2026-04-21 11:22:01 +0800 | phase 3 deep revise | 核心开发文档,命中 37 处旧 schema 示例,需保守替换。 |
| `rebuild5/docs/gps1/README.md` | untracked in current worktree | keep active | 当前研究工作空间,只在 phase 2 需要修复其外链时改动。 |
| `rebuild5/docs/gps1/01_research_restart_prompt.md` | untracked in current worktree | keep active | 当前研究 prompt,不移动。 |
| `rebuild5/docs/DOC_CONSOLIDATION_PROMPT.md` | untracked in current worktree | archive in phase 7 | 本轮工作 prompt,最终 `git mv` 到 `archive/_consolidation_prompt.md`。 |

## 3. 目录级移动决策

| Scope | Last Commit Time | Recommended Handling | Reason |
|---|---|---|---|
| `rebuild5/docs/fix/` | mixed, latest 2026-04-13 | phase 1 `git mv` -> `archive/fix_history/fix_legacy/` | 老 fix 目录,已被后续 fix5/6/loop/upgrade 历史 trail 覆盖。 |
| `rebuild5/docs/fix1/` | 2026-04-13 | phase 1 `git mv` -> `archive/fix_history/fix1/` | UI 小修复历史 trail。 |
| `rebuild5/docs/fix2/` | 2026-04-13 | phase 1 `git mv` -> `archive/fix_history/fix2/` | Step5 优化历史 trail。 |
| `rebuild5/docs/fix3/` | 2026-04-13 | phase 1 `git mv` -> `archive/fix_history/fix3/` | fix3 历史 trail。 |
| `rebuild5/docs/fix4/` | mixed, latest 2026-04-21 | phase 1 `git mv` -> `archive/fix_history/fix4/` | fix4 历史 trail。 |
| `rebuild5/docs/fix5/` | mixed, latest 2026-04-27 | phase 1 `git mv` -> `archive/fix_history/fix5/` | Citus 迁移 trail,已收档。 |
| `rebuild5/docs/fix6_optim/` | mixed, latest 2026-04-27 | phase 1 `git mv` -> `archive/fix_history/fix6_optim/` | helper/test/runbook trail,已收档。 |
| `rebuild5/docs/loop_optim/` | mixed, latest 2026-04-27 | phase 1 `git mv` -> `archive/fix_history/loop_optim/` | artifact runner trail,已收档。 |
| `rebuild5/docs/upgrade/` | mixed, latest 2026-04-28 | phase 1 `git mv` -> `archive/fix_history/upgrade/` | PG18/内核升级 trail,已收档。 |
| `rebuild5/docs/dev/` | mixed, latest 2026-04-21 | phase 1 `git mv` -> `archive/dev/` | 开发期调试笔记,不再 active。 |
| `rebuild5/docs/human_guide/` | mixed, latest 2026-04-13 | phase 1 `git mv` -> `archive/human_guide/` | 老操作指南,被顶层权威文档替代。 |
| `rebuild5/docs/gps研究/` | mixed, latest 2026-04-25 | phase 1 `git mv` -> `archive/gps研究/` | 老 GPS 研究目录,当前 active 改为 `gps1/`。 |

## 4. 顶层散文件移动决策

| File | Last Commit Time | Recommended Handling | Reason |
|---|---|---|---|
| `rebuild5/docs/rerun_delivery_2026-04-19.md` | 2026-04-21 11:22:01 +0800 | phase 1 `git mv` -> `archive/delivery_reports/` | 历史交付报告。 |
| `rebuild5/docs/rerun_delivery_2026-04-21_full.md` | 2026-04-21 17:24:16 +0800 | phase 1 `git mv` -> `archive/delivery_reports/` | 历史交付报告。 |
| `rebuild5/docs/rerun_delivery_2026-04-22_full.md` | 2026-04-25 16:22:46 +0800 | phase 1 `git mv` -> `archive/delivery_reports/` | 历史交付报告。 |
| `rebuild5/docs/rerun_delivery_2026-04-23_full.md` | 2026-04-25 16:22:46 +0800 | phase 1 `git mv` -> `archive/delivery_reports/` | 历史交付报告。 |
| `rebuild5/docs/重跑Prompt_优化验证与重跑.md` | 2026-04-21 11:22:01 +0800 | phase 1 `git mv` -> `archive/old_prompts/` | 老 prompt,已被顶层 authority docs 替代。 |
| `rebuild5/docs/重跑监督Prompt.md` | 2026-04-21 11:22:01 +0800 | phase 1 `git mv` -> `archive/old_prompts/` | 老 prompt,已被顶层 authority docs 替代。 |
| `rebuild5/docs/样例速度优化评估Prompt_claude.md` | 2026-04-21 11:22:01 +0800 | phase 1 `git mv` -> `archive/old_prompts/` | 老 prompt,已被顶层 authority docs 替代。 |
| `rebuild5/docs/速度优化评估_claude.md` | 2026-04-21 11:22:01 +0800 | phase 1 `git mv` -> `archive/old_prompts/` | 老评估文档,不再 active。 |
| `rebuild5/docs/runbook_v5.md` | 2026-04-21 11:22:01 +0800 | phase 1 `git mv` -> `archive/old_prompts/runbook_v5.md` | 已被顶层 `runbook.md` 替代。 |

## 5. 过时关键词命中(阶段 3 todo 输入)

| File | Hit Count | 初步判断 |
|---|---:|---|
| `rebuild5/docs/05_画像维护.md` | 2 | 命中旧 schema 写法 `rebuild5.trusted_cell_library`,应在不改业务逻辑前提下替换为当前 schema 示例。 |
| `rebuild5/docs/11_核心表说明.md` | 37 | 大量表名前缀仍为 `rebuild5.*` / `rebuild5_meta.*`;需统一核对当前 `rb5.*` / `rb5_meta.*` 口径,保守改写。 |

### 5.1 注意事项

- 本 grep 只抓了 `PG17 / 5433 / fix4_codex / rebuild5.(raw_gps|etl_|trusted_|cell_)`。
- 没命中的文档不代表完全无需修订;阶段 3 仍要逐篇首尾 + 局部全文审改。
- `11_核心表说明.md` 的命中多数是表名前缀示例,属于 A-D 类可改项,但字段语义与状态机描述属于 E-F 类,不能动。

## 6. 链接修复输入(阶段 2)

### 6.1 明确需要修复的上层文件

| File | 主要残留链接 |
|---|---|
| `PROJECT_STATUS.md` | `./fix5/`, `./fix6_optim/`, `./loop_optim/`, `./upgrade/` |
| `CLUSTER_USAGE.md` | `./fix6_optim/04_runbook.md` |
| `runbook.md` | `./fix6_optim/04_runbook.md`, `./upgrade/*.md` |
| `README.md` | `./runbook_v5.md`, `./fix5/`, `./fix6_optim/`, `./loop_optim/`, `./upgrade/` |
| `gps1/README.md` | 目前均指向顶层权威文档,无需 archive 路径修复 |

### 6.2 明确不修复的范围

- `archive/` 内部子目录之间的相对链接
- 将被归档的老文档内部链接
- 本工作 prompt 自身(`DOC_CONSOLIDATION_PROMPT.md`)在阶段 2/6 的 grep 验证中显式排除

## 7. 阶段结论

阶段 0 完成后,后续执行顺序明确:

1. phase 1 做纯 `git mv` 和 `archive/README.md`
2. phase 2 修剩余 active 文档对 archive 的交叉引用
3. phase 3 对 13 篇核心开发文档做 A-D 类保守更新,业务规则零改动
4. phase 4/5 完成顶层导航重写与 6 份权威文件对齐
5. phase 6 做排除 prompt 的 grep/link 验证
6. phase 7 写最终报告并归档本 prompt
