# Fix4 代码改动决策

## 1. 最终决策

主流程后续代码变更应以当前主链整合版为准。

原则：

1. 保留已经接进主链且已在样例链路验证过的改动
2. 不把侧路研究脚本直接升格为正式执行路径
3. full run 之前先完成 `batch4-7` 样例验证

## 2. 必须保留的改动

### 2.1 Step2 核心点过滤

保留文件：

- `rebuild5/backend/app/profile/pipeline.py`

保留原因：

- 已真实接入主链
- 能显著压制离群点导致的极端半径
- 不改变 Step2/Step3 的职责边界

### 2.2 Step5 滑动窗口核心点过滤

保留文件：

- `rebuild5/backend/app/maintenance/window.py`

保留原因：

- 与 Step2 形成前后协同
- 让维护态质心和半径不再被窗口内极端点拉偏

### 2.3 地理碰撞替代旧绝对碰撞

保留文件：

- `rebuild5/backend/app/maintenance/collision.py`

保留原因：

- 旧 `COUNT(DISTINCT bs_id) > 1` 在现有表结构下是结构性失效
- 新 `_detect_geographic_collision` 基于 `cell_centroid_detail` 稳定簇，符合文档定义

### 2.4 Step4 donor gate 修复

保留文件：

- `rebuild5/backend/app/profile/pipeline.py`
- `rebuild5/backend/app/enrichment/pipeline.py`

保留原因：

- 已在样例链路上证明修复 `batch2 donor=0`
- donor 应以“已命中 published donor”为准，不应再二次缩成 `anchor_eligible` 子池

### 2.5 Step5 PostGIS 分阶段物化

保留文件：

- `rebuild5/backend/app/maintenance/publish_bs_lac.py`

保留原因：

- 真实样例上已把 `_cell_centroid_valid_clusters` 瓶颈从分钟级打回秒级
- 这是结构性优化，不是临时调参

### 2.6 多质心候选扩大

保留文件：

- `rebuild5/backend/app/maintenance/publish_bs_lac.py`
- `rebuild5/config/antitoxin_params.yaml`

保留原因：

- 候选不再只看过滤后 `p90`
- 引入 `raw_p90 / max_spread / core_outlier_ratio / gps_anomaly_type` 后，更符合 Step5 异常治理职责

## 3. 保留但暂不视为最终定稿的改动

### 3.1 多质心分类阈值

保留文件：

- `rebuild5/backend/app/maintenance/publish_bs_lac.py`
- `rebuild5/config/antitoxin_params.yaml`

当前状态：

- 作为样例验证默认值保留
- 不在 full run 前冻结为最终定稿

原因：

- 当前 `dual_cluster` 仍偏多
- 需要 `batch4-7` 再判断 `moving / migration / dual_cluster / multi_cluster` 的边界

### 3.2 `candidate_drift_patterns` 包含 `large_coverage`

保留文件：

- `rebuild5/config/antitoxin_params.yaml`

原因：

- 这是合理修复
- 但最终候选是否继续扩展，还要看 `batch4-7` 误触发率

## 4. 不应作为正式主流程采纳的改动

### 4.1 Claude 侧路 runbook

不采纳为正式执行路径的文件：

- `rebuild5/scripts/fix4_claude_batch4to7.sh`
- `rebuild5/scripts/fix4_claude_pipeline.py`

原因：

1. 绕过主链 Step2 Path split
2. 绕过 Step4 donor
3. 当前真实库没有可审计的 DBSCAN / BS / LAC 发布结果
4. 脚本命名与真实落表状态不一致

处理建议：

- 保留为研究参考
- 不写入最终 sample runbook
- 不作为后续正式库执行入口

### 4.2 Claude 的 anchor proxy

不采纳为正式口径：

- `active_days >= 2` 替代 `observed_span_hours >= 24`

原因：

- 偏离当前 Step3 设计
- 会放大 donor 可用池
- 破坏与主链资格定义的一致性

## 5. 建议回退或降级为研究附件的内容

### 5.1 与真实库状态不一致的 Claude Python 全流程脚本

建议：

- 不从仓库物理删除
- 但明确标注为 research-only
- 不再让最终文档引用它作为实际执行器

### 5.2 任何跳过 Step2/Step4 的 sample runbook

建议：

- 从最终交付链路中移除
- 若保留，需单独放到研究附录中，并注明“不代表主链验证”

## 6. 下一步代码动作

在完成 `batch4-7` 样例验证之前，后续代码动作应是：

1. 保持主链当前整合实现不回退
2. 只对多质心边界做小范围可回滚调参
3. 补一个样例集成测试，覆盖：
   - batch2 `donor_matched_count = total_path_a`
   - batch3 `multi_centroid_cell_count > 0`
   - LAC 不做多簇
4. 等 `batch4-7` 通过后，再冻结正式 runbook

## 7. 本文件结论

当前主流程代码的正确处理方式是：

- 保留主链整合修复
- 不回退 donor gate、核心点过滤、地理碰撞、PostGIS 分阶段物化
- 不采纳 Claude 侧路脚本为最终执行流程

