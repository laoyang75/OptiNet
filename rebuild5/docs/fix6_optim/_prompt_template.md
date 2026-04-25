# Prompt 标准模板(fix6_optim 通用)

> 所有 fix6_optim 阶段 prompt 套这份模板。10 个字段必填,缺一项就是 prompt 残缺。
> 用途:让独立 agent 没有上下文的情况下也能完整执行任务,不漏凭证、不漏关联文档、不漏验证标准。

---

## 模板结构(逐字段说明 + 范例)

### § 0 标题

格式:`# OptiNet rebuild5 / fix6_optim / <阶段编号> <阶段名>(agent <对话角色>)`

例:`# OptiNet rebuild5 / fix6_optim / 02 审计 + 结构优化 + 测试(agent 新实例对话)`

### § 1 元目标(一句话)

agent 读完这一段就知道"我为什么干这件事"。不超过 3 句。

例:
> 把 fix5 working tree 60+ 个未 commit 文件按"代码 / 脚本 / 文档"分层 commit 并 push 到 GitHub origin/main。本地研究项目,无服务器部署,不开 PR。

### § 2 上下文启动顺序(必读文件清单,按序)

agent 读完这段才有上下文,**列在最前的最优先**。每个文件加一句"读什么内容"。

例:
1. 仓库根目录 `AGENTS.md` —— 协作规约
2. `rebuild5/docs/fix6_optim/README.md` —— fix6_optim 全局边界
3. `rebuild5/docs/fix6_optim/_prompt_template.md` —— 本模板(检查本 prompt 是否完整)
4. `rebuild5/docs/fix5/06_rerun_validation.md` —— fix5 D 阶段交付,代码改动的 by-product
5. 本 prompt(你正在读的)

读完不立刻动手,先在对话报"我看到任务是 X,环境是 Y,我打算分 N 步做",ack 后再开工。

### § 3 环境硬信息

**所有 agent 必需的连接/路径信息**,不能假设 agent 已经知道。包含:

- **仓库路径**:`/Users/yangcongan/cursor/WangYou_Data`(完整读写权)
- **Git remote**:`git remote -v` 看到的 origin URL(本任务期 push 用)
- **旧库 PG17(只读基线)**:
  - DSN:`postgres://postgres:123456@192.168.200.217:5433/ip_loc2`
  - MCP:`mcp__PG17__execute_sql`
  - psql 兜底:`PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2`
- **Citus(主目标)**:
  - DSN:`postgres://postgres:123456@192.168.200.217:5488/yangca`
  - MCP:`mcp__PG_Citus__execute_sql`
  - psql 兜底:`PGPASSWORD=123456 PGGSSENCMODE=disable psql -h 192.168.200.217 -p 5488 -U postgres -d yangca`
  - Python runner env:`REBUILD5_PG_DSN='postgres://postgres:123456@192.168.200.217:5488/yangca'`
- **auto_explain workaround**:runner 调用必须前缀 `PGOPTIONS='-c auto_explain.log_analyze=off'`
- **集群规格**(如阶段需要):Citus 14.0-1 / PostGIS 3.6.3 / 1 coord + 4 worker / 每台 20 物理 / 251GB / `citus.max_intermediate_result_size=16GB`(已 ALTER SYSTEM)
- **沙箱**:claude code 沙箱可能 SIGKILL 长跑,>30 分钟任务用 host shell `nohup` 跑(fix5 D 阶段已踩坑)

不需要的字段可以删,但**默认所有数据库阶段都要有**。

### § 4 关联文档清单(必看必同步)

agent 容易忽略的:**这次任务可能要修改哪些已有 .md 文档**,以及**应当读哪些 .md 才能正确理解领域知识**。

格式:
| 路径 | 阅读 / 修改 | 备注 |
|---|---|---|
| `rebuild5/docs/01b_数据源接入_处理规则.md` | 修改 | ODS-023b/024b 新增清洗规则要补 |
| `rebuild5/docs/03_流式质量评估.md` | 阅读 | 了解评估流程 |
| `rebuild5/docs/05_画像维护.md` | 修改 | drift_pattern 三分类要补 |

写 prompt 前 grep 一遍:
```bash
grep -lE "<本阶段相关关键词>" rebuild5/docs/
```
把 hit 到的全部列入清单。

### § 5 任务清单

#### 必做

精确到**文件 + 行号 + 改动性质**。例:

1. 修改 `rebuild5/backend/app/maintenance/publish_bs_lac.py:894`
   - 把 `cur = conn.cursor()` 改成 `cur = ClientCursor(conn)`
   - 不动其他 caller

2. 新建 `rebuild5/backend/app/core/citus_compat.py`
   - 抽出统一 helper `execute_distributed_insert(sql, params=None, session_setup_sqls=None)`
   - 内部强制 ClientCursor

3. ...

#### 不做(显式禁止)

- ❌ 不 amend 已有 commit
- ❌ 不 force push
- ❌ 不开 subagent
- ❌ 不用 `python3 - <<'PY'` stdin heredoc
- ❌ 不引入新依赖
- ❌ 不动旧库 PG17
- ❌ 不 commit `.env` / `credentials.json` / 密钥
- ❌ 不删除 `rb5_bench.*` / `claude_diag.*`(历史诊断要用)

每个 prompt 至少列 5 条最贴近本任务的禁止项。

### § 6 验证标准

任务做完怎么算 done?**量化 + 可执行**。例:

- `git log --oneline origin/main..HEAD` 看到 N 个 commit,messages 符合约定式
- `git push --dry-run origin main` 显示能 push,无冲突
- 单批 batch 1 跑完后:`SELECT COUNT(*) FROM rb5.trusted_cell_library WHERE batch_id=1` 在 79,000 ~ 80,000 范围
- pytest `tests/test_step5_smoke.py` 全过

每个验证项必须能用 SQL / shell 命令 / pytest 直接验证,不允许"看起来 OK"这种主观判定。

### § 7 产出物

明确产出**文件路径 + 大致结构**。例:

- `rebuild5/docs/fix6_optim/02_audit_report.md`,结构:
  ```
  ## 0 TL;DR
  ## 1 改动清单
  ## 2 抽出的 helper
  ## 3 测试套件
  ## 4 已知限制
  ```
- `rebuild5/backend/app/core/citus_compat.py`(新文件)
- `rebuild5/tests/test_citus_compat.py`(新文件)

### § 8 notes 协议

`rb5_bench.notes` 是 Claude 和 agent 之间的异步通信通道。每阶段统一格式:

- 开跑前:`topic='fix6_<阶段编号>_<动作>_started'`,severity='info'
- 中间关键事件(可选):`topic='fix6_<阶段编号>_<具体事>'`,severity='info'
- 哨兵 / 验证挂:`topic='fix6_<阶段编号>_blocker_<原因>'`,severity='blocker'
- 完工:`topic='fix6_<阶段编号>_done'`,severity='info',body 含关键 metric
- 失败收尾:`topic='fix6_<阶段编号>_failed'`,severity='blocker'

注意 `rb5_bench.notes` 的 schema:`(id, run_id, topic, severity, body, created_at)`。**body 字段不是 message**(fix5 期间踩过)。

### § 9 完工话术(给 agent 现成的句子)

让 agent 拿模板填空回复,Claude 一眼看到关键数字。例:

成功:
> "fix6_<阶段> 完成。<产出文件路径> 已写入。关键指标:<X=Y, ...>。notes `topic='fix6_<阶段>_done'` 已插入。请上游 review。"

失败:
> "fix6_<阶段> 失败于 <步骤>。blocker=<一句话>。已停 + 写 notes `topic='fix6_<阶段>_failed'`。等上游处置。"

### § 10 失败兜底

每个 prompt 显式说明:**挂了不要硬扛、不要自作主张大改、不要重试碰运气**。

例:
- 任意验证项 fail → 停 + 写 blocker note + 在对话报告完整错误 + 等上游
- 沙箱 SIGKILL 长跑 → 切 host shell `nohup` 跑,不要在沙箱里反复重启
- 撞陌生 Citus 错误 → 完整复制错误信息 + traceback,不自己 google 修

---

## 写 prompt 时的 Claude 自检清单

在把 prompt 给 user 之前,过一遍:

- [ ] § 0 标题完整
- [ ] § 1 元目标 ≤ 3 句
- [ ] § 2 必读文件清单按序,每个有"读什么"
- [ ] § 3 环境信息全(仓库 / DB DSN / MCP / psql 兜底 / 凭证)
- [ ] § 4 关联文档清单 grep 过一遍(`grep -lE "<关键词>" rebuild5/docs/`)
- [ ] § 5 必做有文件 + 行号 + 改动性质
- [ ] § 5 不做 ≥ 5 条
- [ ] § 6 验证项可量化 / 可执行
- [ ] § 7 产出物含路径 + 结构骨架
- [ ] § 8 notes topic 命名一致(`fix6_<阶段编号>_*`)
- [ ] § 9 完工话术包含关键数字 placeholder
- [ ] § 10 失败兜底含"不自作主张"

漏一项 = prompt 不合格。
