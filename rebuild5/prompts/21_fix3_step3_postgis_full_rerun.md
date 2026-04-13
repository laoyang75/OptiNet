# Prompt: Fix3 Step 3 修复 + PostGIS 质心研究 + 全链重跑

你在 `/Users/yangcongan/cursor/WangYou_Data` 继续 `rebuild5`。

本轮任务不是延续上一个会话的局部修补，而是开启一轮新的主线工作。

必须严格按下面的顺序推进：

1. 修复 `Fix3` 中已经确认的 **Step 3 晋级规则与数据逻辑错误**
2. 修复 ETL 清洗与输入口径问题
3. 基于 **PostGIS** 重新研究并设计 GPS 质心 / 多质心 / 迁移质心方案，并先和人类确认
4. 把前面所有修改整合起来，用样例数据跑通完整流程
5. 最后再重跑 7 天完整正式数据

注意：

- 本轮不要机械“照抄建议文档实现”
- `rebuild5/docs/fix3/03_GPS质心计算调研建议.md` 只是参考，不是最终方案
- 你必须结合真实数据、统计分析和多 case 验证，构建自己的方案

---

## 0. 当前环境与边界

远程服务器：

- `ssh root@192.168.200.217`
- 密码：`111111`

数据库容器：

- Docker 容器名：`pg17-test`
- 镜像：`postgres:17`
- 当前唯一 PostgreSQL 容器

主要数据库：

- 正式库：`ip_loc2`
- 可用于隔离验证的 smoke 库：
  - `ip_loc2_step3_smoke`
  - `ip_loc2_step5_smoke`

当前状态：

- **主库 `ip_loc2` 已成功启用 PostGIS**
- `SELECT PostGIS_Version()` 已可用

约束：

- 当前 UI 仍在同步开发
- **不要随意重置正式库中的数据**
- 所有测试、验证、样例运行，优先放在 smoke 库中完成
- 如果你认为必须重启远程 PostgreSQL 容器，必须先明确说明原因和影响

---

## 1. 开始前必须先读

必须先读：

- `rebuild5/docs/fix3/02_晋级规则与数据逻辑修复.md`
- `rebuild5/docs/fix3/03_GPS质心计算调研建议.md`
- `rebuild5/docs/03_流式质量评估.md`
- `rebuild5/docs/05_画像维护.md`
- `rebuild5/docs/fix2/step5_optimization_validation_report.md`
- `rebuild5/docs/fix2/multicentroid_batch7_top100_report.md`
- `rebuild5/docs/fix2/batch7_multicentroid_processing_plan.md`
- `rebuild5/scripts/runbook_beijing_7d_daily_standard_v4.md`

如需看当前执行脚本与主链代码，重点看：

- `rebuild5/scripts/run_daily_increment_batch_loop.py`
- `rebuild5/scripts/run_step1_to_step5_daily_loop.py`
- `rebuild5/backend/app/evaluation/pipeline.py`
- `rebuild5/backend/app/profile/logic.py`
- `rebuild5/backend/app/etl/clean.py`
- `rebuild5/backend/app/maintenance/window.py`
- `rebuild5/backend/app/maintenance/pipeline.py`
- `rebuild5/backend/app/maintenance/publish_cell.py`
- `rebuild5/backend/app/maintenance/publish_bs_lac.py`

---

## 2. 本轮核心目标与顺序

### 2.1 第一步：Step 3 修复是最高优先级

本轮首先要解决：

- `Fix3-02` 中确认的 Step 3 候选池合并逻辑错误
- 晋级规则错误
- ETL 清洗规则缺失
- Cell / BS / LAC 晋级门槛调整

这里不是局部 patch，而是要确保：

- 新数据进入候选池后，与历史证据合并的逻辑正确
- 单次脏数据不会永久污染候选池
- 晋级规则和当前数据现实相匹配
- 修完后可以支撑重新跑数据

### 2.2 第二步：ETL 修复必须单独完成

Step 3 修复后，必须单独处理 ETL 清洗和输入口径问题。

原因：

- 如果 ETL 脏输入不先收口，后续的 Step 3 修复和质心研究都会继续被污染
- ETL 修复应作为一段独立工作完成，而不是混在质心研究或样例验证里

这里要覆盖：

- `operator_code = 0/''`
- `lac = 0`
- `cell_id = 0`
- 以及 `Fix3-02` 中所有明确要求补齐的 ETL 规则

### 2.3 第三步：质心方案必须重新研究，不是照建议文档照做

本轮质心研究的真正目标是：

1. **定位准确**
2. **尽量避免脏信号污染**
3. 对于非脏信号中的：
   - 明确多质心
   - 双质心
   - 迁移质心
   - 动态质心
   做出尽可能准确的区分和判断

你不能简单把 `03_GPS质心计算调研建议.md` 当作最后方案。

它只是参考方向。

你必须：

- 用更多真实数据做统计分析
- 选择一批覆盖范围大、观测量高、代表性强的 Cell 做研究
- 形成一套你自己验证过的质心方案

注意：

- 这一步不能直接把研究结果并入主链
- 必须先形成研究结论和方案
- **必须先和人类确认方案**

也就是说：

```text
先研究
  -> 出报告
  -> 和人类确认
  -> 确认后才允许整合进测试全流程
```

### 2.4 第四步和第五步：先样例全流程，后正式 7 天

本轮最终目标不是单独修 Step 3，也不是单独研究质心，而是：

- 修复所有当前发现的问题
- 把新的 PostGIS 质心方案纳入主链
- 在测试数据上跑通
- 最终形成一版“修复后 + PostGIS 质心方案”的有效数据与重跑方案

---

在 Step 3 / ETL / 质心方案都完成并确认前：

- 不能直接跑正式 7 天数据
- 只能在 smoke 库做整合测试

最终正式数据重跑必须放到最后。

---

## 3. 执行原则

### 3.1 先修 Step 3，再修 ETL，再研究质心

本轮顺序必须是：

```text
Step 3 修复
    -> ETL 修复
    -> PostGIS 质心研究
    -> 人类确认方案
    -> 样例全流程验证
    -> 正式 7 天重跑
```

不要跳步。

### 3.2 先隔离验证，后正式重跑

必须优先在 smoke 库完成：

- schema / 逻辑修复验证
- 测试数据全流程验证
- PostGIS 质心分析验证

不能一上来就在正式库 `ip_loc2` 上重跑。

### 3.3 质心研究要有统计性，而不是只看个案

至少要做到：

- 从当前数据中选出一批覆盖规模大的 Cell
- 样本量不能太少，不能只挑 3-5 个 case
- 最终报告必须有：
  - 样本选择逻辑
  - 分类统计
  - 代表 case
  - 参数敏感性
  - 为什么某些对象是脏信号，某些对象是多质心，某些对象是迁移

### 3.4 研究方案必须先确认，再整合进主链

这里是硬要求：

- 质心方案研究完成后，必须先给出报告
- 必须先和人类确认
- 在确认前，不能直接改正式链口径

### 3.5 PostGIS 研究必须落到 PG 内

当前主库已有 PostGIS。

因此本轮研究的最终目标应是：

- 把核心空间分析尽量落到 PostgreSQL / PostGIS 中
- 不是长期停留在 Python 离线脚本

允许：

- 前期用 Python 辅助做探索和可视化

但最终你需要形成：

- 可在 PG / PostGIS 内落地的实现路径
- 对应 SQL / 表结构 / 运行顺序建议

---

## 4. 第一部分：Fix3-02 Step 3 修复任务

严格覆盖以下内容：

### 4.1 Step 3 候选池合并逻辑

必须修：

- Bug 1：`p50/p90` 合并使用 `GREATEST`
- Bug 2：`observed_span_hours` 错误累加
- Bug 3：`independent_devs` 跨批虚增

要求：

- 给出代码修复
- 给出 schema 变更
- 给出为什么这样修
- 给出对现有流程的影响

### 4.2 ETL 清洗规则补充

必须修：

- `operator_code = 0/''`
- `lac = 0`
- `cell_id = 0`

要求：

- 明确哪些删行、哪些置空、哪些保留
- 保证 Step 1 输出口径统一

### 4.3 晋级规则调整

必须落实：

- Cell 新晋级规则
- BS 新晋级规则
- LAC 新晋级规则

要求：

- 修改 `profile_params.yaml`
- 修改代码中的 CASE 语句
- 确认 `logic.py` 和阈值加载适配

---

## 5. 第二部分：ETL 修复任务

### 5.1 ETL 清洗规则补充

必须单独完成：

- `operator_code = 0/''`
- `lac = 0`
- `cell_id = 0`

要求：

- 明确删行 / 置空 / 保留策略
- 修改对应代码
- 给出修复后对 Step 3 和质心研究的影响说明

### 5.2 ETL 修复后要做最小验证

至少确认：

- ETL 输出列口径正确
- 不会继续把明显脏值送进 Step 3 / Step 5

---

## 6. 第三部分：PostGIS 质心研究任务

### 6.1 研究对象

必须从当前真实数据中选出一批具有代表性的 Cell。

建议原则：

- 覆盖范围大
- 观测量高
- 活跃天数足够
- 包含多类对象：
  - stable / large_coverage / collision / migration / dynamic
  - 当前 `is_multi_centroid=true`
  - 当前 `gps_anomaly_type IS NOT NULL`

这里不要只取 100 个“最大 p90”就结束。

你需要自己设计更合理的抽样方式，确保研究覆盖面足够。

### 6.2 研究问题

你需要回答：

1. 什么样的点是脏信号？
2. 脏信号应该如何在质心计算前被过滤？
3. 什么样的对象是：
   - 单中心大覆盖
   - 双质心
   - 多质心
   - 迁移质心
   - 动态质心
   - 碰撞
4. 这些类别之间边界是什么？
5. 用什么 PostGIS 方法能较稳定地实现？

### 6.3 研究方法要求

必须包含：

- PostGIS 空间函数的实际实验
- 多组参数比较
- 统计汇总
- 代表样本拆解

推荐但不限于：

- `ST_ClusterDBSCAN`
- `ST_Collect`
- `ST_Centroid`
- `ST_ConvexHull`
- `ST_Area`
- `ST_Distance`
- `ST_SnapToGrid`

如果你认为还有更合适的 PostGIS 实现方式，可以自己设计。

### 6.4 研究输出要求

必须至少输出：

1. 样本选择方法
2. 研究用 SQL / 中间表设计
3. 参数敏感性分析
4. 分类结果统计
5. 代表 case 说明
6. 推荐的正式实现方案
7. 计算成本与增量化建议

---

### 6.5 研究完成后必须先请求人类确认

在你完成：

- PostGIS 研究
- 报告
- 分类方案
- 参数建议

之后，必须先等待人类确认。

确认前：

- 不要把研究方案并入正式主链
- 不要跑正式 7 天重跑

---

## 7. 第四部分：测试数据全流程验证

只有当以下三部分都完成后，才允许进入本阶段：

1. Step 3 修复完成
2. ETL 修复完成
3. PostGIS 质心方案研究完成并经人类确认

然后必须先在测试数据上跑通。

要求：

- 使用 smoke 库
- 先清理隔离库下游状态
- 跑测试数据全流程
- 明确每一步是否成功
- 明确跑到了哪个 batch

如果失败：

- 明确失败位置
- 明确是 Step 3 问题、Step 5 问题还是 PostGIS 方案问题
- 明确下一次继续跑应从哪里恢复

---

---

## 8. 第五部分：正式 7 天重跑

只有在测试数据完整跑通后，才允许执行正式 7 天重跑。

正式重跑前必须明确：

- 采用的是哪一版 Step 3 修复
- 采用的是哪一版 ETL 清洗规则
- 采用的是哪一版 PostGIS 质心方案

正式重跑后，必须给出：

- `step2/3/4/5` 各批统计
- 正式 `raw_gps / etl_cleaned` 行数
- `trusted_cell_library / trusted_bs_library / trusted_lac_library(batch7)` 行数
- 新标签或研究结果相关指标

---

## 9. 最终交付物

完成后，必须至少交付：

### 7.1 修复结果

- Step 3 修复清单
- ETL 规则修复清单
- 晋级规则修复清单

### 7.2 研究结果

- PostGIS 质心研究详细报告
- 分类方案
- 参数建议
- 实现建议

### 7.3 流程方案

- 一版新的 runbook（V4 或更高版本）
- 对当前数据做最终处理的方案
- 后续生产运行中如何降低成本的建议

### 7.4 数据结果

如果已经形成新的测试链结果，至少给出：

- 各 step 跑到的 batch
- 核心统计表结果
- 研究结果表或中间表规模

---

## 10. 关键提醒

### 8.1 不要把 fix3/03 当作“必须照做的方案”

它只是参考。

你真正要做的是：

- 用真实数据研究
- 找出更合理的质心实现方式
- 最终形成你自己验证过的方案

### 8.2 研究目标是“准确定位 + 抗脏信号 + 正确分类”

不是单纯提高 `is_multi_centroid` 命中率。

更重要的是：

- 先把脏信号排除掉
- 再在有效信号里做多质心 / 迁移 / 双质心判断

### 8.3 核心思路要开放

不要预设：

- 所有大半径 Cell 都是多质心
- 所有多簇都是迁移
- 所有远距离双簇都是碰撞

这些都必须让数据和分析结果自己说话。
