# OptiNet rebuild5 / 文档整合收尾 — 一气呵成(agent 新实例对话)

## § 1 元目标

`rebuild5/docs/` 经过 fix5 / fix6_optim / loop_optim / upgrade / kernel 升级 / UI 04 等多轮迭代后,**文档结构已经混乱**(顶层 24+ 散文件,12 个嵌套子目录,~60+ md 文件,主题重复,内容部分过时)。在重启研究(gps1)前,**做一次彻底的文档收尾**,让 docs/ 变成"打开就能用"的状态。

**user 已拍板的 6 个决策**:

1. **00-11 核心开发文档留顶层**(不移到 spec/ 子目录)
2. **老子目录(fix1/fix2/fix3/fix4/fix5/fix6_optim/loop_optim/upgrade/dev/human_guide/gps研究)** → 全部 `archive/`
3. **顶层散文件(rerun_delivery_*.md / 重跑Prompt_*.md / 样例速度优化评估*.md / 速度优化评估_claude.md)** → 全部 `archive/`
4. **00-11 内容更新深度** → **深度逐篇审改**(对齐 PG18 / 内核 6.6.12 / 5488 / yangca / rb5.*)
5. **fix5/6/loop/upgrade 移动**:整体 mv 到 `archive/` (链接修复)
6. **prompt 形态**:**phase 2 一气呵成**(本 prompt 既分析也实施)

**这是 60+ 文件级别的工作,~1-2 天工程量。要求 agent 内部分多个阶段 + 每阶段 1 个 commit**(即使外部是 phase 2,git history 内部要清晰可回滚)。

## § 2 上下文启动顺序

按序读完直接开干:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/PROJECT_STATUS.md` —— 当前状态(基线对账标尺)
3. `rebuild5/docs/CLUSTER_USAGE.md` —— 集群使用原则(开发文档应该对齐这个)
4. `rebuild5/docs/runbook.md` —— 操作手册
5. `rebuild5/docs/README.md` —— 旧顶层入口(要重写)
6. `rebuild5/docs/处理流程总览.md` —— 流程主线
7. `rebuild5/docs/术语对照表.md` —— 术语
8. `rebuild5/docs/fix6_optim/_prompt_template.md` § 11/§ 12 —— 模板复用
9. 13 个核心开发文档(00-11,含 01a/01b)各**第一节** + 末节(每篇先扫第一/末几页定位过时点,不全读 ~5500 行)
10. 本 prompt

读完直接开工。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`
- **当前 git 头**:`a3a1ae9`(kernel upgrade all 210)
- **Git remote**:`https://github.com/laoyang75/OptiNet.git`(SSL 抖动等 60s 重试)
- **生产**:PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3 / 5488 / yangca
- **不连数据库** — 本阶段是文档整理,不需要

### 当前 docs/ 实测清单(按类型分)

#### Tier 1 — 顶层权威文件(保留 + 维护)
- `README.md`(待重写为扁平 navigation)
- `PROJECT_STATUS.md`
- `CLUSTER_USAGE.md`
- `runbook.md`
- `处理流程总览.md`
- `术语对照表.md`

#### Tier 1.5 — 顶层 13 篇核心开发文档(深度审改)
- `00_全局约定.md` (608 行)
- `01a_数据源接入_功能要求.md` (386 行)
- `01b_数据源接入_处理规则.md` (700 行)
- `02_基础画像.md` (510 行)
- `03_流式质量评估.md` (652 行)
- `04_知识补数.md` (582 行)
- `05_画像维护.md` (994 行)
- `06_服务层_运营商数据库与分析服务.md` (153 行)
- `07_数据集选择与运行管理.md` (105 行)
- `08_UI设计.md` (348 行)
- `09_控制操作_初始化重算与回归.md` (201 行)
- `10_调试期结果保留与字段口径提示.md` (46 行)
- `11_核心表说明.md` (299 行)
- 共 5584 行

#### Tier 2 — 历史 trail(整体移到 archive/)
- `fix1/` `fix2/` `fix3/` `fix4/` `fix5/` `fix6_optim/` `loop_optim/` `upgrade/`
- `dev/` `human_guide/` `gps研究/`
- `fix/`(顶层有个老 fix/ 目录,也归 archive)

#### Tier 3 — 顶层散文件(整体移到 archive/)
- `rerun_delivery_2026-04-19.md` / `2026-04-21_full.md` / `2026-04-22_full.md` / `2026-04-23_full.md`
- `重跑Prompt_优化验证与重跑.md`
- `重跑监督Prompt.md`
- `样例速度优化评估Prompt_claude.md`
- `速度优化评估_claude.md`
- `runbook_v5.md`(被新 runbook.md 替代)

#### Tier 4 — 当前研究(active,保留不动)
- `gps1/`(刚建,新分析周期工作空间)
- `DOC_CONSOLIDATION_PROMPT.md`(本 prompt,完工后归 archive/)

## § 4 关联文档清单

整个 `docs/` 目录都是本阶段范围。**核心是不要改坏业务规则**(00-11 的算法 / 状态机 / 术语)。只改:

- 环境信息(PG 版本 / 端口 / 库名 / 路径)
- SQL 例子里的 schema(rebuild5.* → rb5.*)
- 量化基线(行数 / 时长 / 版本)
- 操作命令(指向新 runbook / archive 后的链接)

## § 5 任务清单(按子阶段,每阶段 1 commit)

### 阶段 0:全局扫描 + 现状分析(~30 分钟,不移动业务文档)

#### 5.0.1 创建 archive 目录结构

```bash
mkdir -p rebuild5/docs/archive/{fix_history,delivery_reports,old_prompts}
```

#### 5.0.2 git mtime + 文件分类清单

跑一次扫描,生成`docs/archive/_consolidation_inventory.md`(临时清单):

```bash
# 列出每个 .md 文件的最后 commit 时间
cd /Users/yangcongan/cursor/WangYou_Data
for f in $(find rebuild5/docs -name "*.md" -type f | sort); do
  last_commit=$(git log -1 --format='%ai' -- "$f" 2>/dev/null || echo "untracked")
  echo "$last_commit | $f"
done > /tmp/_consolidation_inventory.txt
```

把输出整理成表格(file / last_commit_time / 推荐处理 / 理由)写到`docs/archive/_consolidation_inventory.md`。

**这个 inventory 是 ground truth,后续每个移动决策都要回看它**。

#### 5.0.3 grep 过时关键词

```bash
# 找出所有提到 "PG17 / 5433 / fix4_codex / rebuild5.* schema" 的位置
grep -rn "PG17\|5433\|fix4_codex\|rebuild5\.\(raw_gps\|etl_\|trusted_\|cell_\)" rebuild5/docs/0*.md rebuild5/docs/1*.md > /tmp/_outdated_refs.txt
# 注意:rebuild5.* schema 是 PG17 时代,新版本是 rb5.*
```

把每个命中点列入 inventory,作为阶段 3 的 todo 输入。

#### 5.0.4 grep cross-reference 链接

```bash
# 找出所有 .md 文件之间的 link
grep -rnE "\[.*\]\(\.\./|\[.*\]\(\.\/|\[.*\]\(rebuild5/docs" rebuild5/docs/ > /tmp/_links.txt
```

记录"指向被 archive 文件的 link",阶段 2 用来修复。

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_phase0_done` 记录,body 含 inventory 行数 + 过时 hits 数 + link 数。

**阶段 0 commit**:
```bash
git add rebuild5/docs/archive/_consolidation_inventory.md rebuild5/docs/archive/_consolidation_notes.md
git commit -m "docs(rebuild5): doc consolidation phase 0 inventory and outdated refs scan"
```

### 阶段 1:archive 物理移动(~30 分钟)

#### 5.1.1 移动历史 trail 子目录到 archive/fix_history/

```bash
# 用 git mv 保留历史
git mv rebuild5/docs/fix rebuild5/docs/archive/fix_history/fix_legacy
git mv rebuild5/docs/fix1 rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/fix2 rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/fix3 rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/fix4 rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/fix5 rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/fix6_optim rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/loop_optim rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/upgrade rebuild5/docs/archive/fix_history/
git mv rebuild5/docs/dev rebuild5/docs/archive/
git mv rebuild5/docs/human_guide rebuild5/docs/archive/
git mv rebuild5/docs/gps研究 rebuild5/docs/archive/
```

#### 5.1.2 移动顶层散文件

```bash
# 4 个 rerun_delivery → archive/delivery_reports/
git mv rebuild5/docs/rerun_delivery_2026-04-19.md rebuild5/docs/archive/delivery_reports/
git mv rebuild5/docs/rerun_delivery_2026-04-21_full.md rebuild5/docs/archive/delivery_reports/
git mv rebuild5/docs/rerun_delivery_2026-04-22_full.md rebuild5/docs/archive/delivery_reports/
git mv rebuild5/docs/rerun_delivery_2026-04-23_full.md rebuild5/docs/archive/delivery_reports/

# 老 prompt → archive/old_prompts/
git mv rebuild5/docs/重跑Prompt_优化验证与重跑.md rebuild5/docs/archive/old_prompts/
git mv rebuild5/docs/重跑监督Prompt.md rebuild5/docs/archive/old_prompts/
git mv rebuild5/docs/样例速度优化评估Prompt_claude.md rebuild5/docs/archive/old_prompts/
git mv rebuild5/docs/速度优化评估_claude.md rebuild5/docs/archive/old_prompts/

# runbook_v5 → archive(被 runbook.md 替代)
git mv rebuild5/docs/runbook_v5.md rebuild5/docs/archive/old_prompts/runbook_v5.md
```

#### 5.1.3 archive 顶层加 README

写 `rebuild5/docs/archive/README.md`:

```markdown
# archive — 历史 trail(只读)

本目录是项目演进过程中产生的历史文档,**已归档,不再 active 维护**。

## 子目录

- `fix_history/` — fix1/2/3/4/fix_legacy/fix5/fix6_optim/loop_optim/upgrade 各阶段修复 trail
- `delivery_reports/` — 历史交付报告(rerun_delivery_*)
- `old_prompts/` — 老 prompt 模板(已被 PROJECT_STATUS / runbook / fix6_optim/_prompt_template 替代)
- `dev/` — 开发期调试笔记
- `human_guide/` — 老操作指南
- `gps研究/` — 老 GPS 研究

## 当前状态

完整的项目当前状态见上层 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)。
当前业务规则见上层 [`../00_全局约定.md`](../00_全局约定.md) ~ [`../11_核心表说明.md`](../11_核心表说明.md)。
当前操作手册见上层 [`../runbook.md`](../runbook.md)。
当前集群使用见上层 [`../CLUSTER_USAGE.md`](../CLUSTER_USAGE.md)。

## 内部链接说明

archive 内各子目录之间的相对引用(如 fix6_optim 引用 fix5)**已保留**,因为它们都被整体移动到 archive 下,内部相对路径不变。

如果发现 archive 内部链接有损坏(因为某些路径变化),**不修复**,因为 archive 是冷冻态。

## 不在 archive 的当前 active 工作

- `../gps1/` — 当前研究分析周期(2026-04-28 启动)
```

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_phase1_done` 记录,body 含移动文件数。

**阶段 1 commit**:
```bash
git add rebuild5/docs/archive/
git commit -m "docs(rebuild5): doc consolidation phase 1 archive historical trails"
```

### 阶段 2:修复 cross-reference 链接(~30 分钟)

#### 5.2.1 找所有指向被移动文件的 link

```bash
# 在剩余顶层文件 + gps1/ 里找
grep -rnE --exclude='DOC_CONSOLIDATION_PROMPT.md' "\[.*\]\((\./)?(fix[0-9]?|fix5|fix6_optim|loop_optim|upgrade|dev|human_guide|gps研究|rerun_delivery_|重跑|样例速度|速度优化|runbook_v5)" \
  rebuild5/docs/*.md rebuild5/docs/gps1/ 2>/dev/null
```

#### 5.2.2 逐个修复(改成 `archive/...` 路径)

例:
- `[fix5/...](./fix5/...)` → `[fix5/...](./archive/fix_history/fix5/...)`
- `[runbook_v5.md](./runbook_v5.md)` → `[runbook_v5.md](./archive/old_prompts/runbook_v5.md)`

**特别注意**:
- `PROJECT_STATUS.md` 大量引用 fix5 / fix6_optim / loop_optim / upgrade,要全部改路径
- `runbook.md` 引用 fix6_optim/04_runbook.md → 改成 `archive/fix_history/fix6_optim/04_runbook.md`
- `CLUSTER_USAGE.md` 引用 archive 内文件 → 改路径

**不修复**:
- archive 内部子目录之间的相对链接(整体移动后相对路径不变)
- 老 markdown 里的指向路径(archive 是冷冻态,不动)

#### 5.2.3 markdown link 验证

```bash
# 简单验证:跑一次完整 grep,确认没有指向"原始未 archive 路径"的残留
grep -rnE --exclude='DOC_CONSOLIDATION_PROMPT.md' "\]\(\./fix([0-9])?(/|\b)|\]\(\./fix5/|\]\(\./fix6_optim/|\]\(\./loop_optim/|\]\(\./upgrade/|\]\(\./dev/|\]\(\./human_guide/|\]\(\./gps研究/|\]\(\./runbook_v5|\]\(\./rerun_delivery|\]\(\./重跑|\]\(\./样例速度|\]\(\./速度优化" \
  rebuild5/docs/*.md rebuild5/docs/gps1/ 2>/dev/null
# 期待:无命中(全部已改成 archive/...)
```

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_phase2_done` 记录,body 含修复 link 数。

**阶段 2 commit**:
```bash
git add rebuild5/docs/*.md rebuild5/docs/gps1/ rebuild5/docs/archive/_consolidation_notes.md
git commit -m "docs(rebuild5): doc consolidation phase 2 fix cross-references"
```

### 阶段 3:13 篇核心开发文档逐篇深度审改(~5-8 小时,核心阶段)

#### 5.3.0 审改原则(必须严格遵守)

**改的(类 A-D)**:
- **类 A 环境信息**:`PG17` → `PG 18.3`,`5433` → `5488`,`ip_loc2_fix4_codex` → `yangca`,`postgres://postgres:123456@host:5433/...` → 新 DSN
- **类 B SQL 表名 schema**:`rebuild5.raw_gps` → `rb5.raw_gps`,`rebuild5.etl_*` → `rb5.etl_*`,`rebuild5.trusted_*` → `rb5.trusted_*`,`rebuild5.cell_*` → `rb5.cell_*`(注意:`rebuild5` 在文档里作"项目名" vs schema 名两种,只改 schema 名)
- **类 C 量化基线**:旧 TCL 数 / sliding 行数 / 时长 → 当前(TCL b7=340,766 / sliding=24,017,207 / wall clock ~128min)
- **类 D 操作命令 / 路径**:旧 `runbook_v5.md` 引用 → `runbook.md`,旧 fix5 引用 → `archive/fix_history/fix5/...`

**不改的(类 E-F)**:
- **类 E 业务规则 / 算法 / 状态机**:Step1-5 流程、生命周期晋级规则、donor 路由、core_position_filter、DBSCAN 聚类、collision 判断、quality 阈值等 — **完全不动**
- **类 F 术语 / 概念定义**:已有的 anchor_eligible / Path A/B/C / snapshot / drift_pattern 等 — **完全不动**

**模糊点**:某段是规则 vs 环境界限不清时,**默认不动**(保守),在最终报告 §3 标 "未改 — 待 user 二次审"。

**开头加注释**:每篇文档**第 1 行**(在 # 标题之后)加一段 "更新声明":

```markdown
> **本文最后审改**:2026-04-28(文档收尾整合)
> **当前生产环境**:PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3 / 5488 / yangca / rb5.* schema
> **业务规则部分**未改动,**环境前置 / SQL 例子 / 量化基线**已对齐当前生产
> 历史 trail 见 [`archive/`](./archive/)
```

#### 5.3.1 13 篇逐一审改(阶段 3 合并为 1 个 commit)

**顺序**(按依赖顺序,先环境基础后业务):

1. `00_全局约定.md`(608 行,字段命名 / 状态定义,基础最广)
2. `11_核心表说明.md`(299 行,表结构 + schema)
3. `01a_数据源接入_功能要求.md`(386 行)
4. `01b_数据源接入_处理规则.md`(700 行,Step1)
5. `02_基础画像.md`(510 行,Step2)
6. `03_流式质量评估.md`(652 行,Step3)
7. `04_知识补数.md`(582 行,Step4)
8. `05_画像维护.md`(994 行,Step5,最长)
9. `06_服务层_运营商数据库与分析服务.md`(153 行)
10. `07_数据集选择与运行管理.md`(105 行)
11. `08_UI设计.md`(348 行)
12. `09_控制操作_初始化重算与回归.md`(201 行)
13. `10_调试期结果保留与字段口径提示.md`(46 行)

**每篇审改流程**:

```
1. 完整读一遍(理解业务规则,避免误改)
2. grep 关键词:PG17 / 5433 / fix4_codex / ip_loc2 / rebuild5\.\([a-z_]+\) / 老路径 / 老命令
3. 判断每个命中点属于类 A-F 哪类
4. 改类 A-D,标类 E-F 不动
5. 加文首"更新声明"(不动 # 标题本身,在标题后加 blockquote)
6. 跑一次 markdown 链接验证(指向其他 docs 的 link 是否还正确)
7. 在临时报告里记本篇改了多少处 / 几类
8. 暂不逐篇 commit;每篇记录改动分类和行数,阶段 3 全部完成后统一 commit
```

**特别提醒**:
- 5584 行不要全文重写,**只改有命中的位置**(打 patch 风格)
- 业务概念解释 / 算法描述 / 状态机图 — **一字不动**
- 看不懂某段在写什么 → **不改**(默认保留)
- SQL 例子如果看不出是 PG17 还是 PG18 时代 → **看 schema 名**(`rebuild5.*` = PG17,`rb5.*` = 当前)

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_phase3_done` 记录,body 含每篇改动行数清单。

**阶段 3 commit**:
```bash
git add rebuild5/docs/0*.md rebuild5/docs/1*.md rebuild5/docs/archive/_consolidation_notes.md
git commit -m "docs(rebuild5): doc consolidation phase 3 refresh core docs for PG18 era"
```

### 阶段 4:重写顶层 README.md(~30 分钟)

`README.md` 重写为**扁平 navigation**,作 single entry point。结构:

```markdown
# Rebuild5 项目文档入口

> 当前生产:PG 18.3 / Citus 14.0-1 / PostGIS 3.6.3 / 192.168.200.217:5488/yangca
> 最后更新:2026-04-28(文档收尾整合)

## 我是新人/AI,从哪开始?

按以下顺序读完即可上手:

1. **本文(导航)** — 你在这里
2. [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) — 当前状态总览
3. [`CLUSTER_USAGE.md`](./CLUSTER_USAGE.md) — 集群使用原则(写代码必读)
4. [`处理流程总览.md`](./处理流程总览.md) — Step1-5 状态机全貌
5. [`00_全局约定.md`](./00_全局约定.md) — 字段 / 状态 / 边界
6. [`术语对照表.md`](./术语对照表.md) — 内部术语 → 中文含义
7. [`runbook.md`](./runbook.md) — 跑数 / 操作集群

## 核心开发文档(13 篇,业务规则源)

按 Step1-Step5 流程展开:

| 文档 | 主题 | 行数 |
|---|---|---:|
| [00_全局约定.md](./00_全局约定.md) | 字段命名 / 状态定义 / 关键边界 | 608 |
| [11_核心表说明.md](./11_核心表说明.md) | 表结构 + 字段口径 | 299 |
| [01a_数据源接入_功能要求.md](./01a_数据源接入_功能要求.md) | Step1 ETL 模块职责 | 386 |
| [01b_数据源接入_处理规则.md](./01b_数据源接入_处理规则.md) | Step1 清洗规则细节 | 700 |
| [02_基础画像.md](./02_基础画像.md) | Step2 路由 / donor 确认 | 510 |
| [03_流式质量评估.md](./03_流式质量评估.md) | Step3 生命周期评估 | 652 |
| [04_知识补数.md](./04_知识补数.md) | Step4 补数 | 582 |
| [05_画像维护.md](./05_画像维护.md) | Step5 维护 / 多质心 / 碰撞 | 994 |
| [06_服务层_运营商数据库与分析服务.md](./06_服务层_运营商数据库与分析服务.md) | Step6 查询服务 | 153 |
| [07_数据集选择与运行管理.md](./07_数据集选择与运行管理.md) | 数据集元数据 | 105 |
| [08_UI设计.md](./08_UI设计.md) | UI 设计总纲 | 348 |
| [09_控制操作_初始化重算与回归.md](./09_控制操作_初始化重算与回归.md) | 重跑控制 | 201 |
| [10_调试期结果保留与字段口径提示.md](./10_调试期结果保留与字段口径提示.md) | 调试期口径 | 46 |

## 当前 active 工作

- [`gps1/`](./gps1/) — 当前研究分析周期(2026-04-28 启动)

## 历史 trail(只读)

- [`archive/`](./archive/) — fix1-fix5 / fix6_optim / loop_optim / upgrade / dev / 等历史 trail

## 文档约定

- **业务规则源** = 13 篇核心开发文档(单一权威)
- **当前状态** = PROJECT_STATUS.md(单一权威)
- **操作手册** = runbook.md(单一权威)
- **使用原则** = CLUSTER_USAGE.md(单一权威)
- 历史 trail 不维护,只在 archive/ 留档
- 当前研究周期(gps1)产出新议题 .md,不污染主线

## 仓库根目录

如果你是工程师从仓库根开始,先看仓库根 [`AGENTS.md`](../../AGENTS.md)。
```

**保留主 README 的 § 8 / § 9 业务总结部分(项目做什么 / Step1-5 不是 5 个独立模块)**,这是有价值的引导内容。

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_phase4_done` 记录。

**阶段 4 commit**:
```bash
git add rebuild5/docs/README.md rebuild5/docs/archive/_consolidation_notes.md
git commit -m "docs(rebuild5): doc consolidation phase 4 rewrite top-level README as flat navigation"
```

### 阶段 5:顶层 6 个权威文件去重 + 对齐(~1 小时)

确认以下 6 个顶层文件**没有重复定义同一概念**,且互相 reference 一致:

1. README.md(navigation only,不含具体内容)
2. PROJECT_STATUS.md(当前状态 + 历史 trail 索引)
3. CLUSTER_USAGE.md(集群原则 + 写代码不踩坑)
4. runbook.md(操作命令)
5. 处理流程总览.md(Step1-5 状态机)
6. 术语对照表.md(术语速查)

**消除重复**:
- 主 README 内嵌的"术语速查"(如果还有)→ 删除,指向 术语对照表
- 主 README 内嵌的"操作命令"→ 删除,指向 runbook
- PROJECT_STATUS 的 Step1-5 描述 → 简化,指向 处理流程总览
- CLUSTER_USAGE 的"操作命令"重复 → 简化,指向 runbook

**确认每个文件聚焦自己的主题**:
- README:导航
- PROJECT_STATUS:当前状态 / 历史 trail / 决策记录
- CLUSTER_USAGE:集群原则 / 不踩坑指南
- runbook:操作命令 / 故障决策树
- 处理流程总览:业务流程
- 术语对照表:术语

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_phase5_done` 记录。

**阶段 5 commit**:
```bash
git add rebuild5/docs/README.md rebuild5/docs/PROJECT_STATUS.md rebuild5/docs/CLUSTER_USAGE.md rebuild5/docs/runbook.md rebuild5/docs/处理流程总览.md rebuild5/docs/术语对照表.md rebuild5/docs/archive/_consolidation_notes.md
git commit -m "docs(rebuild5): doc consolidation phase 5 deduplicate top-level files"
```

### 阶段 6:link 验证 + 终版扫描(~15 分钟)

```bash
# 1. 确认 docs/ 顶层只剩权威文件 + 13 个开发文档 + active 目录(gps1) + archive
ls rebuild5/docs/*.md | wc -l
# 阶段 6 时期待 ~20 个 .md(6 权威 + 13 开发 + 本 prompt;阶段 7 后本 prompt 归档)
ls -d rebuild5/docs/*/  # 期待:archive/ + gps1/

# 2. grep 残留的指向"未 archive 路径"的 link
grep -rnE --exclude='DOC_CONSOLIDATION_PROMPT.md' "\]\(\./fix([0-9])?(/|\b)|\]\(\./fix5/|\]\(\./fix6_optim/|\]\(\./loop_optim/|\]\(\./upgrade/|\]\(\./dev/|\]\(\./human_guide/|\]\(\./gps研究/|\]\(\./runbook_v5|\]\(\./rerun_delivery|\]\(\./重跑|\]\(\./样例速度|\]\(\./速度优化" \
  rebuild5/docs/*.md rebuild5/docs/gps1/ 2>/dev/null
# 期待:无命中

# 3. grep 残留的过时关键词在主线文档(00-11 + 6 权威)
grep -rn --exclude='DOC_CONSOLIDATION_PROMPT.md' "PG17\|5433\|fix4_codex\|ip_loc2_fix4_codex" \
  rebuild5/docs/*.md 2>/dev/null
# 期待:仅在 PROJECT_STATUS / archive 引用 / "升级前 PG17 → 升级后 PG18" 这种历史叙述里出现
# 不应在 00-11 / runbook / CLUSTER_USAGE / README 主线导航里出现作"当前环境"

# 4. grep 残留的 schema 引用
grep -rn "rebuild5\.raw_gps\|rebuild5\.etl_\|rebuild5\.trusted_\|rebuild5\.cell_" \
  rebuild5/docs/0*.md rebuild5/docs/1*.md 2>/dev/null
# 期待:无命中(全部改成 rb5.*)
```

把 4 条扫描的输出贴到最终报告 §6。

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_phase6_done` 记录,body 含 4 条扫描结果摘要。

### 阶段 7:最终报告 + 完工 commit + push(~10 分钟)

#### 5.7.1 写 `rebuild5/docs/archive/_consolidation_report.md`(最终报告)

结构:

```markdown
# 文档整合收尾报告(2026-04-28)

## 0. TL;DR
- 整合前:docs/ 顶层 24+ 散文件,12 个嵌套子目录,~60 .md 文件
- 整合后:docs/ 顶层 19 个 .md(6 权威 + 13 开发),archive/ + gps1/ 两个目录
- archive 移动文件数:N(包括 X 个目录 + Y 个散文件)
- 13 篇核心开发文档审改:每篇改动行数清单
- 链接修复:M 处
- commit 数:7-8(每阶段独立 commit)
- 业务规则改动:0(只改环境/SQL/量化/路径,业务规则一字不动)

## 1. 阶段 0 现状清单(摘要)
- 总文件数 / 各类型分布

## 2. 阶段 1 archive 移动清单
| 原路径 | 新路径 |
| ... | ... |

## 3. 阶段 2 链接修复清单
| 文件 | 改动行 | diff 节选 |

## 4. 阶段 3 13 篇核心开发文档审改(关键!)
### 4.1 00_全局约定.md
- 改了几处 类 A / B / C / D
- diff 节选

### 4.2 ~ 4.13 同结构

## 5. 阶段 4 README 重写
- 关键 diff 节选

## 6. 阶段 6 link 验证 4 个 grep 输出

## 7. 整合后 docs/ 目录树
\`\`\`
docs/
├── README.md
├── PROJECT_STATUS.md
├── CLUSTER_USAGE.md
├── runbook.md
├── 处理流程总览.md
├── 术语对照表.md
├── 00_全局约定.md
├── ... 11_核心表说明.md
├── gps1/
└── archive/
    ├── README.md
    ├── _consolidation_prompt.md
    ├── _consolidation_report.md
    ├── fix_history/
    ├── delivery_reports/
    ├── old_prompts/
    ├── dev/
    ├── human_guide/
    ├── gps研究/
    └── _consolidation_inventory.md
\`\`\`

## 8. 已知限制 / 未做
- 模糊点(类 E vs A 边界)未改的清单,等 user 二次审
- archive 内部链接是否完全保留(冷冻态)
```

#### 5.7.2 把本 prompt 移到 archive

```bash
git mv rebuild5/docs/DOC_CONSOLIDATION_PROMPT.md rebuild5/docs/archive/_consolidation_prompt.md
```

#### 5.7.3 final commit + push

```bash
git add rebuild5/docs/archive/_consolidation_report.md rebuild5/docs/archive/_consolidation_prompt.md rebuild5/docs/archive/_consolidation_notes.md
git commit -m "docs(rebuild5): doc consolidation phase 7 final report and archive self"
git push origin main
```

向 `rebuild5/docs/archive/_consolidation_notes.md` 追加 `doc_consolidation_done` 记录,用 § 9 完工话术汇报。

### 不做(显式禁止)

- ❌ 不改 13 篇核心开发文档的**业务规则 / 算法 / 状态机 / 术语**(只改环境/SQL/量化/路径)
- ❌ 不删任何文件(全部 archive 保留,即使过时)
- ❌ 不动 `gps1/`(当前 active 工作空间)
- ❌ 不动 `rebuild5/scripts/` / `rebuild5/backend/` / `rebuild5/tests/`(本阶段是文档整理,不动代码)
- ❌ 不动 `rebuild5/docs/` 之外的目录(`AGENTS.md` / 仓库根的 .md 等)
- ❌ archive 内部链接不修复(冷冻态)
- ❌ 不引入新依赖
- ❌ 不开 PR / 不开分支 / 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc
- ❌ 撞模糊点(类 E vs A 边界)→ **保守不改**,在报告 §8 标"待 user 二次审"
- ❌ 不一次性 commit 所有阶段(必须每阶段 1 commit;阶段 3 覆盖 13 篇核心文档,user 可以逐阶段 review)

## § 6 验证标准

1. **目录结构**:`docs/` 顶层只剩 6 权威 + 13 开发 + archive/ + gps1/;本 prompt 已归档为 `docs/archive/_consolidation_prompt.md`
2. **archive 完整**:被移动的所有目录 / 散文件 在 archive/ 下找得到,git mv 历史保留
3. **链接无残留**:阶段 6 的 4 条 grep 命令期待全部 0 命中(或 user 接受的"历史叙述"残留)
4. **13 篇核心文档每篇都有"更新声明"块**:grep "本文最后审改:2026-04-28" 在 13 篇里都命中
5. **业务规则零改动**:agent 报告 §4 列出所有改动都属于类 A-D,没有改类 E-F 的 case
6. **commit 数**:`git log a3a1ae9..HEAD --oneline` 显示 7-8 个 commit(每阶段 1 个;如某篇核心文档超过 1 小时且按 §10 拆分,允许多出少量阶段 3 子 commit)
7. **push**:`git rev-parse HEAD == git rev-parse origin/main`(允许标 push pending)
8. **阶段记录**:`rebuild5/docs/archive/_consolidation_notes.md` 写入 `doc_consolidation_done`

## § 7 产出物

最终落到 `rebuild5/docs/archive/_consolidation_report.md`(详 § 5.7.1 结构)。

## § 8 阶段记录协议

不使用外部 notes 系统。所有阶段记录统一追加到:

`rebuild5/docs/archive/_consolidation_notes.md`

每阶段完成后追加:

```markdown
## doc_consolidation_phase<N>_done

- time: <ISO 时间>
- commit: <commit sha 或 pending>
- summary: <本阶段完成内容>
- metrics:
  - <关键计数>
```

完工追加:

```markdown
## doc_consolidation_done

- time: <ISO 时间>
- head: <HEAD sha>
- pushed: true/false
- before: <整合前摘要>
- after: <整合后摘要>
- core_docs_changed: <N>
- link_fixes: <M>
- commit_count: <N>
```

失败追加:

```markdown
## doc_consolidation_failed

- time: <ISO 时间>
- phase: <N>
- blocker: <一句话>
- completed_phases: <列表>
- traceback_or_command_output: <必要输出>
```

## § 9 完工话术

成功:
> "文档整合收尾完成。`docs/archive/_consolidation_report.md` 已写入。
> 整合前:24+ 顶层散文件 / 12 嵌套子目录 / 60+ .md;整合后:6 权威 + 13 开发 / 1 archive / 1 gps1。
> 13 篇核心开发文档逐篇审改,共改 <N> 处(全属类 A-D 环境/SQL/量化/路径,业务规则零改动)。
> link 修复 <M> 处,4 条扫描验证全过。
> 7-8 个 commit 已 push,head=<SHA>。
> 阶段记录 `docs/archive/_consolidation_notes.md` 已写入 `doc_consolidation_done`。
> 重启研究(gps1)的文档基础已就绪。"

失败:
> "文档整合失败于阶段 <N>:<step>。blocker=<一句话>。已停 + 写入 `docs/archive/_consolidation_notes.md`,等上游处置。已完成阶段:<列>。"

## § 10 失败兜底

- **某篇核心文档审改撞业务规则边界**:**默认不改**,标"待 user 二次审"加进报告 §8
- **archive 移动后破坏内部链接**:**不修**,archive 是冷冻态;在报告 §8 列出来,user 知道即可
- **link 修复后某文件路径仍 broken**:回到阶段 2 重做,**不允许跳过 link 修复**
- **某篇 5.3 审改时间超 1 小时**(说明文档过长 / 改动过多):分多个 commit,在那一篇内部分 batch 改;不要一次性提交太大改动
- **撞 git 冲突**(可能 user 同时在改):停 + blocker,不 force push
- **GitHub HTTPS SSL 抖动**:等 60s 重试,push pending 不算 blocker
- **任何挂** → `doc_consolidation_failed` 阶段记录 + 完整 traceback + 不擅自大改
- **绝不**改业务规则 / 算法 / 状态机 / 术语(类 E-F)
- **绝不**删除文件(只移动)
