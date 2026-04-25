# fix5 — OptiNet rebuild5 Citus 迁移质量诊断与修复

Gate 3(2026-04-24)跑完 7 批 Citus 全量重跑后,MCP 校验发现数据质量严重异常。
本目录是**诊断 → 审计 → 修复 → 重跑**的 4 阶段工作空间。

## 如何启动新上下文

- A 阶段直接把 `NEXT_SESSION_PROMPT.md` 作为新 Claude 对话的首条消息。
- B 阶段必须等 A 阶段产出 `01_quality_diagnosis.md` 后,再把 `agent_audit_prompt.md` 作为新 agent 对话的首条消息。
- C/D 阶段 prompt 当前尚未生成;必须基于 A+B/C 的实际产出再写,不要直接凭 README 开工。
- 启动后先读仓库根目录 `AGENTS.md`,然后按对应 prompt 执行。

## 账号与访问面

- A/B 阶段只需要数据库/MCP 访问,不需要 Web/UI 登录账号,也不需要 SSH 登录运行机。
- PG17 旧库账号:`postgres / 123456`,地址 `192.168.200.217:5433/ip_loc2`,只读。
- Citus 新集群账号:`postgres / 123456`,地址 `192.168.200.217:5488/yangca`。
- 如未来 D 阶段需要监督远端进程或日志,另参考 `rebuild5/docs/重跑监督Prompt.md`;不要在 A/B 阶段使用 SSH。

## 阶段分工

| 阶段 | 谁 | Prompt | 产出 |
|---|---|---|---|
| **A · 诊断** | Claude(上游) | `NEXT_SESSION_PROMPT.md` | `01_quality_diagnosis.md` |
| **B · 审计** | agent(独立) | `agent_audit_prompt.md` | `02_agent_change_audit.md` |
| **C · 修复 + 战术优化** | agent(新实例) | `03_fix_and_optimize_prompt.md` | `04_code_fix_report.md` |
| **D · 重跑验收(终点)** | agent(新实例) | `05_rerun_prompt.md` | `06_rerun_validation.md` + batch 1-7 产出 |

## C 阶段已定的边界(2026-04-24 用户拍板)

**不做结构大改**。这轮目标就是**跑通可信数据**,不是 Citus 原生化。C 阶段只做三件事:

1. **修 bug**:基于 01 诊断 + 02 审计,回滚/修复 sliding_window 断档、多质心链路失效等具体根因
2. **`citus.max_intermediate_result_size` 全局调大**:`ALTER SYSTEM SET ... = 16GB` + `pg_reload_conf()`(服务器 251GB 内存,1GB 默认值太保守)。不要 session 级到处撒。
3. **Step 1 和 Step 2-5 pipelined 并行**:恢复本地 `run_step1_step25_pipelined_temp.py` 的模式,Step 1 一跑完 day N 就触发 Step 2-5 day N,预计压缩 ~1/3 时长

**不做**:
- 不改分布键 / colocation group(所有表保持 agent 迁移时的分布)
- 不重写 sliding_window 的 retention 逻辑
- 不重构 label_engine 的候选池构建
- 不按时间分区 / 不按 cell 逐个 materialize input

结构级优化推迟到未来新项目重新规划阶段。

## 当前状态(2026-04-24)

- [x] Gate 3 跑完,产出不可信
- [x] A 诊断 — `01_quality_diagnosis.md` 已出,根因 = Citus runner 未物化 per-batch `step2_batch_input`
- [x] B 审计 — `02_agent_change_audit.md` 已出,4 段 B 类 + 4 段 C 类已回滚
- [x] C 修复 + 优化 — `04_code_fix_report.md` 已出,batch 1/2 对齐 PG17 ±0.3%,pipelined 推迟
- [ ] D 重跑验收(**终点**)— agent 新对话用 `05_rerun_prompt.md`,产出 `06_rerun_validation.md` 后 fix5 结束

## 异常摘要(给三阶段都看)

### 4 个铁证异常

1. **sliding_window batch 5 后锁死**:batch 6/7 `cell_sliding_window` 和 batch 5 完全相同(distinct_cells=340,453)
2. **k_eff=2 的 6 个 cell 跨批不变**:候选池增长 3 倍,DBSCAN 产出不动
3. **sliding_window 混入 2023/2024 年垃圾时间戳**:retention 没生效
4. **多质心链路全崩**:Citus batch 7 large_coverage/dual_cluster/uncertain 全 0(本地 batch 7 分别 745/442/82)

### 嫌疑代码文件

- `rebuild5/backend/app/enrichment/pipeline.py`
- `rebuild5/backend/app/maintenance/window.py`
- `rebuild5/backend/app/maintenance/label_engine.py`
- 以及 Gate 3 过程中任何其他未 commit 改动

## 协作规则

- **严格串行**:A → B → C → D,每一阶段完成后下一位才开工
- A 完成产出 01 后,B 开始前**必须先读 01**(诊断结论能让 B 的代码分类判断更精准)
- **C 必须等 A+B 都完成才开始**,在 bug 代码上叠优化是反模式
- **D 必须等 C 的改动经过上游 review**

## 核心原则(整个 fix5 过程)

- 不 git commit / push(用户 review 后统一做)
- 不动旧库 5433/ip_loc2
- 不 DROP `rb5_bench.*` / `claude_diag.*`(诊断要用)
- `rb5_bench.notes` 是上游 Claude 和下游 agent 之间的唯一通信通道
- 有疑问先写 `severity='suspect'` notes,不要硬推

## 环境硬信息(所有阶段公用)

仓库:  `/Users/yangcongan/cursor/WangYou_Data`

旧库(PG17,只读基线):
- `postgres://postgres:123456@192.168.200.217:5433/ip_loc2`
- MCP:`mcp__PG17__execute_sql`

新集群(Citus,主目标):
- `postgres://postgres:123456@192.168.200.217:5488/yangca`
- MCP:`mcp__PG_Citus__execute_sql`

Citus 14.0-1 / postgis 3.6.3 / pg_stat_statements / auto_explain
1 coordinator(217)+ 4 worker(216/219/220/221)
每台 20 物理核 / 40 逻辑核 / 251GB 内存
