# Fix4 多质心裁决

## 1. 裁决结论

最终多质心方案采用：

- 当前主链 `publish_cell_centroid_detail()` + `_cell_centroid_classification`
- 不采用 `claude` 侧路脚本作为最终执行口径

当前 full-run 结论：

- 方案可继续做样例验证
- 方案还不能直接放行正式全量

原因：

- `dual_cluster` 仍明显偏多
- `moving / migration` 还没有在共同区间给出足够样例证据

## 2. 设计约束

多质心必须遵守当前设计文档边界：

1. 多质心只属于 Step5 异常子集，不是 Step3 全量准入逻辑
2. `cell_centroid_detail` 必须记录稳定簇，而不是只写 JSON 摘要
3. `migration` 不能脱离“双簇 + 大距离 + 低重叠”独立命中
4. `moving` 不能直接等价成“任何多簇”
5. BS 可以继承动态风险，但 LAC 不做多簇

## 3. Codex 当前实现为何更合理

### 3.1 候选集边界符合 Step5 职责

当前主链候选不只看过滤后的 `p90`，还同时看：

- `raw_p90_radius_m`
- `max_spread_m`
- `core_outlier_ratio`
- `gps_anomaly_type`
- 当前标签变化与上一版差异

这比“只看过滤后的 core p90”更符合 Step5 异常治理职责。

### 3.2 分类链路已实际执行

当前主链已经真实落地：

- `cell_centroid_detail`
- `_cell_centroid_daily_presence`
- `_cell_centroid_classification`
- `bs_centroid_detail`

Batch3 实际结果：

| pattern | count |
|---|---:|
| `<null>` | 9,681 |
| `dual_cluster` | 106 |
| `multi_cluster` | 7 |
| `moving` | 0 |
| `migration` | 0 |

这说明：

- 方案不是纸面分类器
- 当前真实问题是 `dual_cluster` 过多，而不是“根本没有多簇结果”

### 3.3 `moving / migration / dual_cluster / multi_cluster` 的边界基本正确

当前主链分类条件：

- `multi_cluster`：稳定簇数达到多簇阈值，且次簇占比达到下限
- `moving`：双簇 + 次簇占比达标 + 切换次数达标 + 重叠天数高
- `migration`：双簇 + 次簇占比达标 + 距离较大 + 重叠天数低
- `dual_cluster`：双簇 + 次簇占比达标 + 距离达到双簇阈值

这套顺序满足两个原则：

1. `migration` 建立在双簇基础上，不脱离双簇单独命中
2. `moving` 比 `dual_cluster` 更严格，不会把静态双簇误标成动态

## 4. Claude 当前方案为什么不能入选最终口径

`claude` 的 Python 侧路脚本确实写了 DBSCAN 和分类逻辑，但本轮审计不能据此直接采纳，原因有三：

1. 真实库 `rebuild5_fix4` 里没有 `claude_cell_centroid_detail`
2. 真实库也没有 `claude_bs_library`
3. 当前 runbook 实际执行的是 `c_window / c_cell_lib` 路线，不是 `claude_*` 路线

因此它现在最多证明：

- 研究者想这样做

但还没有证明：

- 这套 DBSCAN 分类已经在共享样例主链中真实跑通

## 5. 面积与多簇的联合判断

Batch3 focus cell `p90`：

| bucket | codex | claude |
|---|---:|---:|
| high_obs | 129.5m | 150.3m |
| high_p90 | 128.6m | 129.0m |
| moving | 818.4m | 779.3m |
| multi_cluster | 799.2m | 678.1m |

判断：

- 两边都能把极端大半径压下来
- 但 `claude` 在 `moving / multi_cluster` 上更激进
- 当前没有足够证据说明更激进就更正确

在多质心问题上，过度压平真实展布比“稍微保守一些”风险更高。

所以本轮裁决是：

- 位置收敛要保留
- 但动态/多簇桶不能追求一味更小

## 6. BS / LAC 的处理裁决

### 6.1 BS

BS 可以合理继承 Cell 的动态风险，但应以聚合标签表达：

- `dynamic_bs`
- `collision_bs`
- `multi_centroid`

而不是把 Cell 的 `moving` 原样照搬到 BS 主标签。

当前主链做法是：

- Cell 侧 `is_dynamic=true` 时，BS 聚合为 `dynamic_bs`

这个方向合理，应保留。

### 6.2 LAC

LAC 不做多簇。

理由：

1. 设计文档明确 LAC 是区域聚合层
2. LAC 的职责是区域面积、异常 BS 比例、边界稳定性
3. LAC 不应复用 Cell/BS 的多质心语义

当前主链 `publish_lac_library()` 只聚合 BS 指标，不做 LAC 多簇，符合设计边界，应保留。

## 7. 当前风险与下一步

当前最大风险不是“没有多簇算法”，而是：

- `dual_cluster` 占当前所有已分类对象的绝大多数

这意味着下一阶段要重点审：

1. 次簇占比 `0.10 ~ 0.20` 的边界样例
2. 双簇距离 `300m ~ 800m` 的边界样例
3. 重叠天数 `1 ~ 2` 天的边界样例

只有在 `batch4-7` 上确认：

- `dual_cluster` 不再一边倒
- `moving / migration` 开始出现合理分化

才允许把当前多质心口径带回主流程冻结。

## 8. 本文件结论

多质心最终口径：

- 采用主链当前实现
- 保留现有分类方向
- 暂不放行 full run
- 先做 `batch4-7` 样例边界验证

