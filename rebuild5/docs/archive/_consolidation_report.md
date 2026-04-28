# docs consolidation report

完成时间: 2026-04-28  
范围: `rebuild5/docs/`

## 1. 结果摘要

| 指标 | 数值 |
|---|---:|
| 整合前 Markdown 文件数 | 161 |
| 整合后 Markdown 文件数 | 165 |
| 整合前顶层 Markdown 文件数 | 29 |
| 整合后顶层 Markdown 文件数 | 19 |
| 13 篇核心开发文档总改动行 | 312 |
| 阶段 commit 数(含最终阶段) | 7 |

## 2. 本轮完成的事

1. 建立 `archive/` 基线清单与阶段 notes。
2. 把历史 trail 目录、顶层散文件和老 prompt 物理归档到 `archive/`。
3. 修复 active 区域对 `fix* / fix6_optim / loop_optim / upgrade / runbook_v5` 的交叉引用。
4. 逐篇审改 13 篇核心开发文档,统一补文首“更新声明”,只改环境/schema/量化/路径四类内容。
5. 重写顶层 `README.md` 为扁平导航。
6. 对齐 `PROJECT_STATUS.md` / `runbook.md` 等权威文档的最终状态口径。
7. 归档本轮 prompt 到 `archive/_consolidation_prompt.md`。

## 3. 4 条验证扫描

| 扫描 | 结果 |
|---|---:|
| legacy cross-reference links | 0 |
| outdated env and schema keywords | 0 |
| legacy meta or tmp schema | 0 |
| direct `runbook_v5` reference | 0 |

说明:
- 所有扫描均显式排除了 `DOC_CONSOLIDATION_PROMPT.md`
- `archive/` 冷冻区未纳入修复或残留判定

## 4. 核心审改说明

- `11_核心表说明.md` 已从旧 `rebuild5.* / rebuild5_meta.* / rebuild5_tmp.*` 对齐到当前 `rb5.* / rb5_meta.* / rb5_stage.*`
- `05_画像维护.md`、`09_控制操作_初始化重算与回归.md`、`10_调试期结果保留与字段口径提示.md` 的示例 SQL / schema / runbook 路径已对齐当前口径
- 保守未改且显式标注的点只有 1 处: `06_服务层_运营商数据库与分析服务.md` 中 `rebuild4_meta.lac_location_snapshot` 的长期口径,标记为“待 user 二审”

## 5. 阶段 commit 链

| 阶段 | Commit |
|---|---|
| phase 0 | `0753bcc` |
| phase 1 | `6f8ac93` |
| phase 2 | `5869292` |
| phase 3 | `aa1e239` |
| phase 4 | `123810e` |
| phase 5 | `ee2018d` |
| phase 6 | `ce18b61` |

最终阶段 commit SHA 见本文件提交后的最新一条提交记录。
