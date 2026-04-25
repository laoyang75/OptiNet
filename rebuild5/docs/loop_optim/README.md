# loop_optim — 研究循环再优化(承接 fix6_optim 收档)

fix6_optim 实现了 Citus 兼容稳定 + pipelined 1.13× 加速 + runbook。
**loop_optim 目标:把研究循环再压一档**(目标全 7 批 ≤ 90 分钟,加速比 ~1.67×)。

## 元目标

1. **真正消除 Step1 / Step2-5 的虚假依赖** — 用 immutable artifact (`rb5_stage.step2_input_b<N>_<YYYYMMDD>`) 切断 Step2 对 etl_cleaned 全局表的隐式依赖,Step1 producer / Step2-5 consumer 完全解耦
2. **索引补全** — 大表 reader SQL 缺索引就建,加多了无害(用户决议)
3. **Step1 高 CPU 利用** — Step1 SQL 的 PG parallel 参数拉到 40 核
4. **UI 落地** — fix5/fix6 累积的清洗规则和 TA / 加权 p90 等在前端暴露

## 阶段表(按顺序执行)

| 阶段 | Prompt | 产出 | 依赖 | 估时 |
|---|---|---|---|---|
| **01 索引补全** | `01_index_additions_prompt.md` | `01_index_additions_report.md` + schema.py 多处 CREATE INDEX | fix6_optim 已收档 | ~半天 |
| **02 artifact pipelined + Step1 40 核** | `02_artifact_pipelined_prompt.md` | `02_artifact_pipelined_report.md` + `run_citus_artifact_pipelined.py` + `rb5_meta.pipeline_artifacts` 状态表 | 01 | ~2 天 |
| **03 全 7 批重跑验证** | `03_rerun_prompt.md` ← 02 完成后由 Claude 写 | `03_rerun_report.md` + 7 批数据 + 终点验收 | 02 | ~1.5 小时 |
| **04 UI 8 块** | `04_ui_prompt.md` ← 03 完成后由 Claude 写 | `04_ui_report.md` + 前端组件 | 03 | ~1-2 天 |

## 协作模式(继承 fix6_optim 的 §11/§12)

- **Claude(我)**:写 prompt + review 上游 agent 报告 + 决定下一阶段范围
- **独立 agent**:执行 prompt + 自主判断(无开跑前 ack)+ 完工自动 commit/push + 写报告 + 写 note
- **用户(你)**:阶段切换时只说 "X 完成了" + blocker 时拍板
- 上下游 agent 互相审核(下游必读上游报告)

每个 prompt 套 `rebuild5/docs/fix6_optim/_prompt_template.md`(模板复用,不重写),12 字段不漏。

## 边界(整个 loop_optim)

- ❌ 不动旧库 PG17(192.168.200.217:5433/ip_loc2)
- ❌ 不重做 fix5/fix6_optim 已交付的事(citus_compat.execute_distributed_insert / 02C 守护 / 串行+pipelined runner / runbook)
- ❌ 不引入新依赖
- ✅ 每阶段产出报告 + notes 完工信号
- ✅ 每阶段独立 commit + push(不跨阶段攒 commit)

## 当前状态(2026-04-25)

- [x] 01 索引补全 — `01_index_additions_report.md`
- [x] 02 artifact pipelined — `02_artifact_pipelined_report.md`
- [x] 02b artifact 分布键 hotfix — `02b_artifact_dist_fix_report.md`
- [ ] 03 重跑验证 — 等 02
- [ ] 04 UI — 等 03

## 引用 fix5/fix6 关键产出(loop_optim 期间共用)

- `rebuild5/docs/fix6_optim/02A_audit_report.md` —— helper 矩阵 + Citus 兼容隐患清单
- `rebuild5/docs/fix6_optim/02B_refactor_report.md` —— `core/citus_compat.py` 设计
- `rebuild5/docs/fix6_optim/03_pipelined_report.md` —— pipelined runner 设计 + 03 限制(speedup 1.13×)
- `rebuild5/docs/fix6_optim/04_runbook.md` —— 标准操作 runbook(loop_optim 完成后要更新)
- `rebuild5/docs/fix6_optim/_prompt_template.md` —— prompt 模板(12 字段)
- `rb5_bench.notes topic LIKE 'fix5_%' / 'fix6_%' / 'loop_optim_%'` —— 历史决策 trail
