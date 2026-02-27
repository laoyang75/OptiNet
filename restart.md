# Restart Context (Phase1 可视化研究平台)

更新时间：2026-02-26
工作目录：`/Users/yangcongan/cursor/WangYou_Data`

## 1) 本轮已完成

### A. Phase1 审计与工程化主文档（已落盘）
- `docs/phase1/Phase1_基础审计与工程化方案_2026-02-25.md`
- 内容包含：
  - Layer_0~Layer_5 一致性矩阵
  - P0/P1/P2 问题清单
  - 门禁SQL建议
  - 实时化准备清单

### B. 无代码深度Agent输入包（已落盘）
- `prompts/phase1_可视化研究_无代码Agent提示词.md`
- `docs/phase1/deep_agent_brief/01_项目与问题摘要.md`
- `docs/phase1/deep_agent_brief/02_目标_边界_成功标准.md`
- `docs/phase1/deep_agent_brief/03_已知事实与当前风险清单.md`

### C. 下一步执行开发文档（已重写）
- `docs/phase1/codex.md`
- 当前已是“执行版”：
  - S0~S4 分阶段实施计划
  - MVP 架构（obs数据层/API/页面）
  - 开发门禁、验收、回滚策略
  - 立即执行清单

## 2) 关键结论（需延续）

### P0（必须先做）
1. Step43 指标汇总链路与当前 schema 漂移，导致 `_All` 与事实表口径不一致。
2. Layer5 BS/CELL 画像缺关键异常契约字段：
   - `is_bs_id_lt_256`
   - `is_multi_operator_shared`
   - `shared_operator_cnt`
   - `shared_operator_list`

### P1（随后做）
1. Layer_1 入口口径文档与实际对象不一致。
2. Step30 存在 `bs_id<=0` 桶，和主文档“入口止血”有偏差。
3. Layer_4 RUNBOOK 与 SQL 对 severe 策略描述冲突。

## 3) 重启后第一优先级（按顺序执行）

### S0-1：修 Step43 聚合口径
目标：让 `Y_codex_Layer4_Step40_Gps_Metrics_All` 与事实表一致。
动作：
1. 检查并修复 `lac_enbid_project/Layer_4/sql/43_step43_merge_metrics.sql` 列集合。
2. 重新生成 `_All` 表。
3. 执行对账SQL，确认差值归零或可解释。

### S0-2：补 Layer5 画像异常字段暴露
目标：让画像层具备关键风险可见性。
动作：
1. 修改 `lac_enbid_project/Layer_5/sql/51_step51_bs_profile.sql`
2. 修改 `lac_enbid_project/Layer_5/sql/52_step52_cell_profile.sql`
3. 如需同步英文视图，更新 `lac_enbid_project/Layer_5/sql/53_step53_rename_profile_columns_cn.sql`

### S0-3：修文档冲突
动作：
1. 更新 `lac_enbid_project/Layer_4/Layer_4_执行计划_RUNBOOK_v1.md` severe 策略表述
2. 在 `docs/phase1/codex.md` 标记“已修复状态”

## 4) 执行验收门禁（重启后可直接跑）

1. 行数守恒：Step40 vs Final 一致
2. 对账一致：`_All` vs 事实表差值
3. Layer5 字段存在性门禁（四个异常字段）
4. 无效LAC泄漏门禁
5. 标签闭环门禁（碰撞/严重/动态）

参考门禁SQL位置：
- `docs/phase1/Phase1_基础审计与工程化方案_2026-02-25.md` 第7节
- `docs/phase1/codex.md` 第9节

## 5) 注意事项
1. 当前还没有开始改 SQL 代码（只完成文档与计划）。
2. 先做 S0，再进入 S1（obs数据层）和 S2/S3（API/页面）。
3. 重启后请先让我读取：
   - `restart.md`
   - `docs/phase1/codex.md`
   - `docs/phase1/Phase1_基础审计与工程化方案_2026-02-25.md`
4. 新增会话辅助文档：
   - `docs/phase1/快速启动与日常使用.md`
   - `docs/phase1/新会话启动说明.md`
5. 启动器：根目录 `launcher.py`（支持 start/stop/status/open）。
6. 可点击控制台：`python3 launcher.py console`（支持按钮操作）。

## 6) 重启后可直接给我的一句话
“按 restart.md 执行 S0，从 Step43 修复开始，修完直接给我门禁结果。”
