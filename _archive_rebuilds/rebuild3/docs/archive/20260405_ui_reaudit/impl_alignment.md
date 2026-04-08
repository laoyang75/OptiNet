# 实施前对齐结果（Gate A）

## 1. 我对 rebuild3 业务主语的理解

rebuild3 不是 rebuild2 的表面改版，而是把“对象、决策、事实、基线、版本绑定”变成同一套动态治理骨架。核心主语如下：

- `Cell`：动态治理最小主语，负责注册、等待、观察、晋升、退化与迁移判定
- `BS`：空间锚点主语，负责 GPS 修正、信号补齐、空间风险传播与锚点资格控制
- `LAC`：区域边界/区域健康主语，负责区域视角的聚合、异常占比与画像解释
- `fact_standardized`：不可变标准事件层，是后续四分流的唯一输入契约
- 四分流事实层：`fact_governed`、`fact_pending_observation`、`fact_pending_issue`、`fact_rejected`
- `baseline_version`：冻结基线版本，只允许批后生成、供下一批使用

## 2. UI v2 与冻结文档的残余冲突判断

基于 `UI_v2` 修复稿、审计报告、待决策清单、执行清单与最终补丁，我确认：

- 主体冲突已收敛，当前可以进入实施
- 仍需在开发阶段强制归一化的残余项只有三类：
  - 全称命名：不得再出现 `pending_obs` / `fact_pending_obs`
  - 版本命名：不得再出现 `rule_version`，统一为 `rule_set_version`
  - 版本上下文组件：核心页面一律接入 `VersionContext`
- LAC 页面允许 `region_quality_label` 作为解释层，但主状态仍必须是统一的 `health_state`
- 旧 `classification_v2 / gps_confidence / signal_confidence` 只能做解释层与迁移参考，不能回到主状态

结论：Gate A 通过，不存在阻塞编码的语义冲突。

## 3. 实现阶段需要统一归一化的命名

必须统一：

- 事实层：
  - `fact_governed`
  - `fact_pending_observation`
  - `fact_pending_issue`
  - `fact_rejected`
- 版本字段：
  - `contract_version`
  - `rule_set_version`
  - `baseline_version`
  - `run_id`
  - `batch_id`
- 状态字段：
  - `lifecycle_state`
  - `health_state`
  - `anchorable`
  - `baseline_eligible`
- 解释层字段：
  - `classification_v2`
  - `gps_confidence`
  - `signal_confidence`
  - `region_quality_label`

## 4. 应进入 `config/` 的参数

必须配置化的参数包括：

- Cell 存在资格阈值
- anchorable / baseline_eligible 阈值
- BS GPS usable/risk 判定阈值
- GPS 中国区范围与 raw keep 距离阈值
- 旧分类到 `health_state` 的映射规则
- 记录级异常标签集合
- 样本/全量对比维度、容差、严重度与门禁规则
- 版本号、样本 run/batch/baseline 标识

## 5. 只读数据依赖

当前样本阶段依赖如下只读资产：

- `rebuild2.l0_lac` / `rebuild2.l0_gps`：作为“rebuild2 标准化结果快路径”样本输入
- `rebuild2._research_bs_classification_v2`：作为旧系统对象异常参考映射
- `rebuild2.dim_bs_refined` / `rebuild2.dim_cell_refined` / `rebuild2.dim_lac_trusted`：用于抽样与对照校验，不写回
- `legacy`：本阶段不直接写入，仅保留后续全量回放可回到原始 27 列契约的入口

## 6. 样本验证切片策略

本轮样本切片覆盖以下治理路径：

- healthy active 4G BS / 5G BS：验证 governed + baseline 主路径
- `collision_suspect` / `collision_confirmed` / `dynamic`：验证对象级异常进入 `fact_pending_issue`
- `single_large` / `normal_spread`：验证记录级异常仍进入 `fact_governed` 但保留异常标签
- waiting / observing 候选 Cell：验证三层资格推进与 observation 路径
- null operator / null lac 记录：验证 `fact_rejected`

未覆盖项：

- `migration_suspect`
- 真正 2 小时粒度的多批增量承接
- 全量性能/索引压力

这些项保留到 Gate F/G 之前补齐。
