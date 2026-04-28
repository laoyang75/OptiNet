# OptiNet rebuild5 / fix6_optim / 02B 重构 — 抽 Citus 兼容统一入口(agent 新实例对话)

## § 1 元目标

基于 02A 审计报告 §2.2 / §5,落地 `rebuild5/backend/app/core/citus_compat.py`(新文件),把当前唯一已修的 `publish_bs_lac._execute_with_session_settings`(ClientCursor + mogrify)抽出为**全局统一入口**,把 P1 清单里 5 处参数化 `INSERT...SELECT` 在 `rb5.*` 主结果表上的 caller 全部迁移到这个入口。**目标 = 03 pipelined 加速前消除 P0 复发面**。

## § 2 上下文启动顺序

按序读完再开工:

1. 仓库根目录 `AGENTS.md`
2. `rebuild5/docs/fix6_optim/README.md` —— 全局阶段表 + 协作约定
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— **特别注意 § 11(完工流程)+ § 12(上下游互审)**,本阶段必须按这两节走
4. `rebuild5/docs/fix6_optim/02A_audit_report.md` —— 上游报告,这是你设计输入
5. `rebuild5/backend/app/maintenance/publish_bs_lac.py` L890-L915 —— 当前 ClientCursor 实现,提取参考
6. 02A 报告 §5 必做 6 条对应的每个文件:行号(下面 §5.2 列出),先读再改
7. 本 prompt(你正在读的)

读完**直接开工**(按 § 11 不再要求开跑前 ack)。但如果你在读上游报告时发现问题(不可行的设计、误判的命中、漏掉的 caller),**先在本阶段报告 §0 写"对 02A 的修订",再实施**;不要悄悄绕过上游建议。

## § 3 环境硬信息

- **仓库**:`/Users/yangcongan/cursor/WangYou_Data`(完整读写权)
- **当前 git 头**:`4b23cd0`(01 阶段交付)
- **Git remote**:`https://github.com/laoyang75/OptiNet.git`(直接 push main,private repo + 局域网,不脱敏)
- **本阶段不连数据库**,纯静态重构
- **可选**:psycopg3 是已安装依赖(publish_bs_lac.py 已 `from psycopg import ClientCursor`),不需要新增依赖

## § 4 关联文档清单

| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `rebuild5/docs/fix6_optim/02A_audit_report.md` | 阅读 | 上游报告,设计输入 |
| `rebuild5/docs/fix5/04_code_fix_report.md` | 阅读 | C 阶段 helper 抽取背景 |
| `rebuild5/docs/fix5/06_rerun_validation.md` §5 附录 | 阅读 | publish_bs hotfix 实施细节 |
| `rebuild5/docs/05_画像维护.md` | 不修改 | maintenance 模块业务规则,理解 caller 上下文用 |
| 本阶段产出:`02B_refactor_report.md` | 新建 | § 7 结构 |

**本阶段不修改任何已有 .md 文档**,只新建 02B_refactor_report.md。

## § 5 任务清单

### 必做(按顺序)

#### 5.0 先 commit + push 上游遗留产物

工作区当前有 4 个未 commit 的文件(01_finalize_report.md / 02A_audit_prompt.md / 02A_audit_report.md / README.md modified)。**开干前先 commit + push 这些**,避免和你 02B 的改动混在一起:

```bash
git add rebuild5/docs/fix6_optim/01_finalize_report.md \
        rebuild5/docs/fix6_optim/02A_audit_prompt.md \
        rebuild5/docs/fix6_optim/02A_audit_report.md \
        rebuild5/docs/fix6_optim/README.md \
        rebuild5/docs/fix6_optim/_prompt_template.md
# 注意 _prompt_template.md 也修改过(加了 §11/§12),一起进
git status --short  # 验证 working tree 只剩你即将改的文件

git commit -m "$(cat <<'EOF'
docs(rebuild5): fix6_optim 01/02A reports + workflow update (auto commit, peer review)

- 01_finalize_report.md: phase 01 finalize report after pushing fix5 deliverables
- 02A_audit_prompt.md + 02A_audit_report.md: audit phase prompt and report
  (P0=0/P1=7/P2=6, helper matrix, fix5 4 root cause vs current tests)
- _prompt_template.md: add §11 (auto commit/push, no ack-on-start) and §12
  (downstream peer review of upstream report)
- README.md: reflect collaboration mode update and phase status

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin main
```

**push 完之后**再开始 5.1。

#### 5.1 实现 `core/citus_compat.py`(新文件)

按 02A §2.2 草案签名实现:

```python
# rebuild5/backend/app/core/citus_compat.py
"""Citus-safe DML helper.

抽自 maintenance/publish_bs_lac._execute_with_session_settings(fix5 D hotfix)。
原因:psycopg3 默认 cursor 使用 server-side prepared statement,Citus distributed
planner 在大数据量 + 多 CTE INSERT...SELECT 上撞 "could not create distributed plan
/ use of parameters in SQL functions" 限制(fix5 D batch 4 案例)。

ClientCursor 强制客户端 binding(整条 SQL 在 client 拼好再发);mogrify 显式 inline
params 作为双保险。
"""

from __future__ import annotations
from typing import Any

from psycopg import ClientCursor

from .database import get_conn


def execute_distributed_insert(
    sql: str,
    *,
    params: tuple[Any, ...] | None = None,
    session_setup_sqls: list[str] | None = None,
) -> None:
    """Citus-safe INSERT...SELECT / DML 入口。

    使用场景:
    - INSERT INTO rb5.<distributed_table> SELECT ... 含 CTE
    - 任何带 params 且 target 是分布式表的 DML
    - 需要临时 SET enable_nestloop=off 等 session-level 设置的 DML

    不适用:
    - 普通 SELECT fetch(用 core.database.fetchone / fetchall)
    - 元数据函数调用如 create_distributed_table / create_reference_table
    - 无 params 的 CTAS / 简单 INSERT(用 core.database.execute)
    """
    setup = list(session_setup_sqls or [])
    with get_conn() as conn:
        with ClientCursor(conn) as cur:
            for stmt in setup:
                cur.execute(stmt)
            if params:
                cur.execute(cur.mogrify(sql, params))
            else:
                cur.execute(sql)
            for stmt in reversed(setup):
                if stmt.upper().lstrip().startswith('SET '):
                    cur.execute(f"RESET {stmt.split()[1]}")
```

**关键点**:
- session_setup_sqls 顺序执行,完成后逆序 RESET(只 RESET `SET key value` 形式,跳过非 SET 语句)
- params 存在 → mogrify 客户端 inline;不存在 → 直接 execute
- 用 `from psycopg import ClientCursor`(已是依赖)
- 不要为了"扩展性"加无用参数(autocommit / fetch_result / 等),后续真需要再加

#### 5.2 替换 5 处 caller

按 02A §5 必做清单逐一替换(精确文件 + 行号见 02A 报告):

1. **`rebuild5/backend/app/maintenance/publish_bs_lac.py`**:
   - 删除模块内 `_execute_with_session_settings` 函数(L894-L912)
   - 删除模块顶部 `from psycopg import ClientCursor`(L16)
   - publish_bs_library 调用从 `_execute_with_session_settings(...)` 改为 `execute_distributed_insert(...)`
   - publish_lac_library(L1240 附近)同样改用 `execute_distributed_insert(sql=..., params=(...))`(LAC 当前可能仍是 `execute(sql, params)`,02A §1.2 P1 #4 标注为 2/3 hit)
   - publish_cell_centroid_detail(L267 附近,02A 提到使用旧 helper)同步改用统一入口
   - `from .core.citus_compat import execute_distributed_insert`(顶部 import)

2. **`rebuild5/backend/app/maintenance/publish_cell.py:56`**:
   - `INSERT INTO rb5.trusted_cell_library ... WITH merged AS ...` 这条 `execute(sql, params)` → `execute_distributed_insert(sql, params=...)`
   - 顶部 import

3. **`rebuild5/backend/app/profile/pipeline.py:1546`**:
   - `INSERT INTO rb5.candidate_seed_history ... SELECT ...` 的 `execute(...)` → `execute_distributed_insert(...)`
   - 顶部 import

4. **`rebuild5/backend/app/enrichment/pipeline.py:413`**:
   - `INSERT INTO rb5.snapshot_seed_records ... SELECT ...` 的 `execute(...)` → `execute_distributed_insert(...)`
   - 顶部 import

5. **`rebuild5/backend/app/core/database.py:207/209`**(02A §5 必做 #6):
   - CTAS split helper 中 params DML 分支:**走统一入口**(不是禁止)
   - 实现方式:在 `_execute_ctas_as_distributed`(或对应函数)里检测到 split SQL 是 INSERT...SELECT 且 params 非空 → 调 `execute_distributed_insert`
   - 注意:`citus_compat.py` import `core.database.get_conn`,如果 `database.py` 反向 import `citus_compat`,会循环。**用本地 import**(在函数体里 `from .citus_compat import execute_distributed_insert`)

#### 5.3 不动(02A 已确认 P2 / 不在范围)

- ❌ `maintenance/label_engine.py:103` 的 `INSERT WITH`(params 已内联,Citus 安全)
- ❌ `etl/fill.py` 的 `ctid::text` 投影
- ❌ `scripts/fix4_claude_pipeline.py` / `scripts/bench_parallel.py` / `scripts/research_*.py`(研究/benchmark 脚本,不在生产 surface)
- ❌ `relation_exists` 从 profile.pipeline 下沉到 core(02A §5 应做 #2,**纯重构,不在 Citus 兼容范围,本阶段不做**)
- ❌ `SET enable_nestloop` 等 session 设置统一入口(02A §5 应做 #3,本阶段只做必要 caller 的 setup_sqls 透传,不重构 session 管理)
- ❌ 不删除 / 不改 `core/database.execute` 本身(它仍是 SELECT / 简单 INSERT 的入口)

#### 5.4 静态验证

每改一个 caller,做静态 check(不连数据库):

```bash
# 语法检查
python3 -m py_compile rebuild5/backend/app/core/citus_compat.py
python3 -m py_compile rebuild5/backend/app/maintenance/publish_bs_lac.py
python3 -m py_compile rebuild5/backend/app/maintenance/publish_cell.py
python3 -m py_compile rebuild5/backend/app/profile/pipeline.py
python3 -m py_compile rebuild5/backend/app/enrichment/pipeline.py
python3 -m py_compile rebuild5/backend/app/core/database.py

# 守护:确保所有 5 个 P1 caller 都不再直接 cur.execute / execute 带 params
grep -n "execute([^)]*params" rebuild5/backend/app/maintenance/publish_bs_lac.py
grep -n "execute([^)]*params" rebuild5/backend/app/maintenance/publish_cell.py
grep -n "execute([^)]*params" rebuild5/backend/app/profile/pipeline.py | grep -v "execute_distributed_insert"
grep -n "execute([^)]*params" rebuild5/backend/app/enrichment/pipeline.py | grep -v "execute_distributed_insert"

# 确认 _execute_with_session_settings 已被删除
grep -rn "_execute_with_session_settings" rebuild5/backend  # 期待无命中
```

#### 5.5 完工后流程(按 _prompt_template.md § 11)

1. `git add` 显式列:
   - `rebuild5/backend/app/core/citus_compat.py`(新)
   - 5 个被改的 caller 文件
   - `rebuild5/docs/fix6_optim/02B_refactor_prompt.md`(本 prompt)
   - `rebuild5/docs/fix6_optim/02B_refactor_report.md`(产出)
   - `rebuild5/docs/fix6_optim/README.md`(更新阶段状态)
2. 一个 commit:
   ```
   refactor(rebuild5): fix6_optim 02B unified Citus-safe INSERT helper

   - Add core/citus_compat.execute_distributed_insert (ClientCursor + mogrify
     + RESET session-level SET) extracted from publish_bs_lac fix5 D hotfix
   - Replace 5 P1 callers (publish_cell, publish_lac, publish_bs centroid,
     candidate_seed_history persist, snapshot_seed_records insert) to use
     unified entry; remove obsolete _execute_with_session_settings local helper
   - Wire core/database CTAS split helper params-DML branch through unified
     entry to prevent future P0 recurrence
   - References fix6_optim/02A_audit_report.md §1.2/§5

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   ```
3. `git push origin main`
4. 写 note `topic='fix6_02B_done'`
5. 用 § 9 完工话术汇报

### 不做(显式禁止)

- ❌ 不动 02A 标 P2 的任何项(label_engine / fill.py ctid / 历史脚本 / relation_exists 下沉)
- ❌ 不重构 `core/database.execute`,它仍是 SELECT / 简单 INSERT 的入口
- ❌ 不改分布键 / 不改 schema / 不改 SQL 业务逻辑(只换执行入口)
- ❌ 不引入新依赖(psycopg3 已有)
- ❌ 不动数据库(不连 PG17 / Citus)
- ❌ 不跑 pipeline / runner(本阶段是静态重构)
- ❌ 不开 PR / 不开分支
- ❌ 不 amend / 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc

## § 6 验证标准

任务 done 的硬标准:

1. **新文件存在**:`ls rebuild5/backend/app/core/citus_compat.py` 显示文件
2. **接口签名匹配草案**:`grep "def execute_distributed_insert" rebuild5/backend/app/core/citus_compat.py` 显示与 02A §2.2 一致(允许扩展但不允许缺参数)
3. **5 caller 全部迁移**:
   - publish_bs_lac.py 内部 `_execute_with_session_settings` 已删除
   - 5 个 P1 caller 都 `import execute_distributed_insert`
   - grep `execute(.*params` 在这 5 个文件里无残留(允许 `execute_distributed_insert(..., params=)`)
4. **py_compile 全过**:6 个文件 `python3 -m py_compile` 全部 0 退出码
5. **commit 内容**:`git show --stat HEAD` 显示 ~7 个文件改动(1 新 + 5 caller + 报告 + README + 本 prompt)
6. **push 远端同步**:`git rev-parse HEAD == git rev-parse origin/main`
7. **报告 §0 含上游审核结论**:对 02A 的修订(若有)显式列出;若无修订,显式写 "对 02A 报告全部采纳,无修订"
8. **note 已写**:`SELECT body FROM rb5_bench.notes WHERE topic='fix6_02B_done'` 返回非空

## § 7 产出物 `02B_refactor_report.md`

```markdown
# fix6_optim / 02B 重构报告

## 0. TL;DR + 对 02A 的修订
- 新增 core/citus_compat.py(N 行)
- 迁移 caller:M 个(列表)
- 删除旧 helper:_execute_with_session_settings
- 对 02A 报告的修订:<显式列;无修订就写"全部采纳,无修订">
- commit SHA:<sha>
- push 状态:<status>

## 1. core/citus_compat.py 设计
- 完整签名 + docstring
- 与 02A §2.2 草案的差异(如有)

## 2. Caller 迁移逐项
| caller | 原 helper | 现入口 | 备注 |
| --- | --- | --- | --- |
| publish_bs_lac.publish_bs_library | _execute_with_session_settings | execute_distributed_insert | session_setup_sqls=['SET enable_nestloop = off'] 透传 |
| publish_bs_lac.publish_lac_library | core.database.execute | execute_distributed_insert | ... |
| publish_bs_lac.publish_cell_centroid_detail | _execute_with_session_settings | execute_distributed_insert | ... |
| publish_cell.publish_cell_library | core.database.execute | execute_distributed_insert | ... |
| profile.pipeline._insert_candidate_seed_history(或方法名) | core.database.execute | execute_distributed_insert | ... |
| enrichment.pipeline._insert_snapshot_seed_records(或方法名) | core.database.execute | execute_distributed_insert | ... |
| core.database CTAS split params 分支 | self.execute | execute_distributed_insert | 本地 import 防循环 |

每行附:替换前后 ~5 行 diff 节选。

## 3. 静态验证结果
- py_compile 全 6 个文件输出
- grep 守护 SQL 输出
- _execute_with_session_settings 残留扫描

## 4. 已知限制 / 未做
- session 管理统一入口(02A §5 应做 #3):未做,理由
- relation_exists 下沉(02A §5 应做 #2):未做,理由
- 任何动态行为差异(连接池 / 事务边界 / autocommit):本阶段未做实测,02C 测试 + 03 pipelined 跑通后再确认

## 5. 给 02C 的输入
- 02C 必做 5 条 regression 中的"parameterized distributed plan caller guard" 现在有具体 grep 守护目标(execute_distributed_insert 入口)
- smoke test 应当 import core/citus_compat 并断言 ClientCursor 路径
```

## § 8 notes 协议

- 完工:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_02B_done', 'info',
    'unified citus_compat entry, callers migrated=<n>, head=<sha>, py_compile pass, no upstream revisions OR <list>');
  ```
- 失败:
  ```sql
  INSERT INTO rb5_bench.notes (topic, severity, body)
  VALUES ('fix6_02B_failed', 'blocker', 'failed at <step>: <reason>');
  ```

## § 9 完工话术

成功:
> "fix6_optim 02B 完成。02B_refactor_report.md 已写入。新建 core/citus_compat.py,迁移 <N> 个 P1 caller,删除旧 _execute_with_session_settings。对 02A 修订:<无 / 列表>。commit=<SHA>,GitHub:<url>。py_compile 全过,grep 守护通过。notes `topic='fix6_02B_done'` 已插入。"

失败:
> "fix6_optim 02B 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='fix6_02B_failed'`。等上游处置。"

## § 10 失败兜底

- **导入循环**(`citus_compat` ↔ `database`):用函数体内 local import 解(`def f(): from .citus_compat import ...`)
- **ClientCursor API 差异**(psycopg3 版本不一致):看 `pip show psycopg`,在 venv 里跑 `python3 -c "from psycopg import ClientCursor; help(ClientCursor.execute)"`,把版本贴报告 §4
- **caller 上下文需要返回值**(如 `execute(sql, params)` 之后 `cur.fetchone()`):**报告 §0 修订 02A**,把 helper 加 `return_rowcount` 或 `fetch_one` 参数,**不要**在 caller 处绕开统一入口
- **session_setup_sqls 顺序敏感**:在报告 §1 注明 RESET 顺序约束,02C 写 unit 测试时覆盖
- **撞陌生 Citus 错误**:复制完整 traceback 到报告 §4,不自己调
- **任何挂** → blocker note + 对话报告 + 等上游
