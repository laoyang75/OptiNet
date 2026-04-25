# OptiNet rebuild5 / fix6_optim / 01 收尾 — 按层级拆 commit + push GitHub(agent 新实例对话)

## § 1 元目标

把 fix5 working tree(83 个未提交文件)按"代码 / 脚本 / 文档"三层拆 commit,push 到 GitHub `origin/main`。本地研究项目,**不开 PR、不开分支**,直接在 main 上 commit。push 之前必须等用户 ack。

## § 2 上下文启动顺序

按序读完再动手:

1. 仓库根目录 `AGENTS.md` —— 协作规约(必读,所有 fix6 阶段共用)
2. `rebuild5/docs/fix6_optim/README.md` —— fix6_optim 全局介绍 + 阶段表
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— prompt 模板,验证本 prompt 是否完整
4. `rebuild5/docs/fix5/06_rerun_validation.md` —— 知道 fix5 D 阶段交付了什么(commit message 要引用)
5. `rebuild5/docs/fix5/04_code_fix_report.md` —— C 阶段代码改动清单,commit message 引用
6. 本 prompt(你正在读的)

读完不要立刻动手。先在对话报告:
- 你计划的 commit 拆分(几条 commit、每条包含哪些路径)
- 你识别到的潜在敏感文件(`.env`、`.gemini/`、`/tmp/*`)
- 你计划的 commit message 草稿(每条一行 subject + 简短 body)

等用户 ack 再动手。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`(完整读写权)
- **当前分支**:`main`
- **Git remote origin**:`https://github.com/laoyang75/OptiNet.git`(fetch + push)
- **Git user**:`yangca`(已配置)
- **当前未提交规模**:`git status --short | wc -l` ≈ 83 个文件(60+ modified + 20+ untracked)
- **Push 目标**:`origin/main`

**本阶段不需要数据库连接**,不读不写 PG17 / Citus。

## § 4 关联文档清单(本阶段不修改文档,只 commit 已有的)

本阶段是"机械 commit",不修改任何 .md 内容。但要确保以下都进 commit 3(文档):

| 路径模式 | 状态 | 归到哪个 commit |
|---|---|---|
| `rebuild5/docs/fix5/*.md` | 大部分 untracked(6 个产出 + README + 3 个 prompt) | commit 3 |
| `rebuild5/docs/fix6_optim/*.md` | 全部 untracked(README + 模板 + 本 prompt) | commit 3 |
| `rebuild5/docs/gps研究/11_*.md`、`12_*.md` | untracked(TA 研究 + 加权 p90) | commit 3 |
| `rebuild5/docs/01b_*.md`、`03_*.md`、`05_*.md`、`gps研究/cell漂移问题分析.md` | modified | commit 3 |
| `rebuild5/docs/rerun_delivery_2026-04-22_full.md`、`2026-04-23_full.md` | untracked | commit 3 |
| `rebuild5/prompts/28_*.md` | modified | commit 3(归"文档+prompts" 一起) |
| `rebuild5/prompts/29_*.md`、`30*.md`、`31_*.md`、`jixu.md` | untracked | commit 3 |
| `docs/数仓重构讨论记录_20260424.md`(顶层 `docs/`) | untracked | commit 3 |
| `optinet_rebuild5_citus_*.md`(仓库根 3 个) | untracked | commit 3 |

## § 5 任务清单

### 必做(按顺序)

#### 步骤 0:全量 survey

```bash
git status --short > /tmp/fix6_01_status_pre.txt
wc -l /tmp/fix6_01_status_pre.txt
```

读这份文件,在对话里给用户一个**分类表**:每个改动文件归到 commit 1/2/3,加 4 个 sanity 检查:
- 有没有任何 `.env` / `credentials*` / `*.key` / `*.pem`?
- 有没有 `node_modules/` / `__pycache__/` / `*.pyc`?
- 有没有 `/tmp/*` 或绝对路径的日志文件被仓库跟踪?
- `.gemini/settings.json` 是不是个人 IDE 配置(让用户决定 commit 还是 .gitignore)?

任何"不确定该不该 commit"的文件,**列出来在对话里问用户**,不要自作主张 add 或 ignore。

#### 步骤 1:三层 commit 拆分(推荐,可微调)

**Commit 1 — 代码**(`feat(rebuild5): citus migration + step2 scope materialization + publish_bs ClientCursor hotfix`)
- `rebuild5/backend/app/**/*.py`
- `rebuild5/frontend/**/*`(TA 字段 UI 暴露 + cell 页面字段调整)
- `rebuild5/config/*.yaml`

**Commit 2 — 脚本**(`feat(rebuild5): add citus runner, reset SQL, ta evaluation scripts`)
- `rebuild5/scripts/*.py`、`rebuild5/scripts/*.sql`
- `rebuild5/run_*.py`(顶层运行脚本)

**Commit 3 — 文档**(`docs(rebuild5): fix5 diagnosis/audit/fix/rerun reports + TA research + ODS rules sync`)
- `rebuild5/docs/**/*.md`
- `rebuild5/prompts/*.md`
- 仓库根 `optinet_rebuild5_citus_*.md`(3 个)
- 顶层 `docs/数仓重构讨论记录_20260424.md`

每个 commit 用 HEREDOC 写 message,subject ≤ 70 字符,body 列 3-5 个 bullet 说明变更性质 + 引用 fix5 docs。Co-Authored-By 用:`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

#### 步骤 2:每个 commit 前自检

```bash
# 在 git add 之前
git diff --stat <要 add 的路径>  # 确认改动量级合理,无意外文件
```

不要用 `git add -A` 或 `git add .`(会把不想要的捎带上)。**显式 `git add <path>`**。

#### 步骤 3:commit 完成后,push 前停下

```bash
git log --oneline origin/main..HEAD
git push --dry-run origin main 2>&1 | head -20
```

把上面两个命令的输出贴在对话里,**等用户 ack 才执行真正的 push**。

#### 步骤 4:用户 ack 后 push

```bash
git push origin main
```

push 完后:
- `git log --oneline -5` 看远端是否同步
- `git status` 应当 clean(假设全部已 commit)
- 若有遗漏的未跟踪,在产出报告中列出来等用户决定

#### 步骤 5:写产出报告 `rebuild5/docs/fix6_optim/01_finalize_report.md`(§ 7 结构)

#### 步骤 6:写完工 note(§ 8 协议)

### 不做(显式禁止)

- ❌ 不开 PR、不开分支(直接 main commit)
- ❌ 不 amend 已有 commit
- ❌ 不 force push、不 `git push -f`
- ❌ 不 `git reset --hard`、不 `git checkout -- <file>`、不 `git stash`
- ❌ 不 `git rm` 任何文件(本阶段只新增 / 修改,不删除)
- ❌ 不 `git add -A` / `git add .`(显式列路径)
- ❌ 不 commit `.env` / `credentials*` / `*.key` / `*.pem` / 任何看起来像凭证的文件
- ❌ 不 commit `__pycache__/` / `*.pyc` / `node_modules/`(若有,先 .gitignore 再 commit .gitignore)
- ❌ 不擅自决定 `.gemini/settings.json` 怎么处理 —— 列出来问用户
- ❌ 不在 commit message 里写"Generated with Claude Code"或类似营销文案
- ❌ 不 push 之前不要等到用户 ack(push 是不可逆操作)
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc

## § 6 验证标准

任务 done 的硬标准(每条可执行验证):

1. **commit 数量**:`git log --oneline origin/main..HEAD` 显示恰好 **3 条**(或你和用户 ack 后的数量)
2. **没有遗漏**:`git status` 输出为空,或剩下的全部是用户明确决定不 commit 的(如 `.gemini/settings.json`)
3. **push 成功**:`git log origin/main..HEAD` 显示空(本地 = 远端)
4. **远端可见**:`git ls-remote origin main` 的 SHA == 本地 `git rev-parse main`
5. **commit message 格式**:每条 subject ≤ 70 字符,有 body,body 至少 3 个 bullet
6. **无敏感文件**:`git log -p origin/main..HEAD | grep -iE "(password|api[_-]?key|secret|token).*=" ` 无意外命中(允许文档里讨论这些词,但不允许实际 key/value)

## § 7 产出物

`rebuild5/docs/fix6_optim/01_finalize_report.md`,结构:

```markdown
# fix6_optim / 01 收尾报告

## 0. TL;DR
- commit 数:N
- push 状态:成功 / 失败原因
- 遗留文件:M(列表 + 用户决议)

## 1. Commit 拆分
| commit | SHA | message subject | 文件数 | 主要路径 |
| --- | --- | --- | --- | --- |
| 1 | abc1234 | feat(rebuild5): citus ... | X | backend/* frontend/* config/* |
| 2 | ... | feat(rebuild5): scripts ... | Y | scripts/* run_*.py |
| 3 | ... | docs(rebuild5): fix5 ... | Z | docs/* prompts/* |

## 2. 每条 commit 完整 message(贴 git log -1 --format=fuller 的输出)

## 3. 敏感文件检查
- .env / credentials / key 扫描结果
- .gemini/settings.json 处置
- 其他 untracked 决议

## 4. Push 验证
- git log --oneline origin/main..HEAD 输出(应为空)
- git ls-remote origin main 的 SHA
- 远端 GitHub URL(可点)

## 5. 遗留 / 未来事
- 仓库根 3 个 optinet_rebuild5_citus_*.md(commit 完后是否考虑移到 docs/?)
- .gitignore 是否要补(__pycache__ / .gemini / .DS_Store / etc)
- 任何 sanity check 抓到但本次未处理的事
```

## § 8 notes 协议

`rb5_bench.notes` schema 是 `(id, run_id, topic, severity, body, created_at)`。**body 字段不是 message**(fix5 期间踩过坑,别再写错)。

写 note 用 Citus MCP:`mcp__PG_Citus__execute_sql`

- 开跑前(读完所有 §2 文件、给出 commit 拆分计划之后):
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_01_started', 'info',
    'finalize commit + push, planned <N> commits, awaiting user ack');
  ```

- 完工(push 成功之后):
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_01_done', 'info',
    'pushed <N> commits to origin/main, head=<SHA>, remaining_uncommitted=<M>');
  ```

- 失败(任何步骤挂):
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_01_failed', 'blocker',
    'failed at <step>: <one-line reason>');
  ```

## § 9 完工话术

成功:
> "fix6_optim 01 完成。01_finalize_report.md 已写入。3 条 commit 已 push 到 origin/main,head=<SHA>。遗留 <M> 个未 commit(详见报告 §5)。notes `topic='fix6_01_done'` 已插入。请上游 review。"

失败:
> "fix6_optim 01 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='fix6_01_failed'`。等上游处置。"

## § 10 失败兜底

- **commit 阶段挂**(pre-commit hook、merge conflict、unexpected staged files):停 + 报告完整错误。**不要 git reset --hard 救场**,可以用 `git restore --staged <path>` 撤销 staging 但不撤销改动
- **push 挂**(non-fast-forward、auth fail):
  - non-fast-forward → 远端有别人 push 过,**不要 force push**,先 `git fetch && git log HEAD..origin/main` 看远端有什么,在对话报告
  - auth fail → 报告 + 让用户处理(可能是 token 过期)
- **撞陌生 git 错误**:完整复制 stderr,不自己 google 修
- **凭证泄漏怀疑**:任何 commit 前的 grep 抓到 password/key,**立刻停**,在对话报告完整命中行,等用户决定

任何挂都写 `severity='blocker'` 的 note,不硬扛。
