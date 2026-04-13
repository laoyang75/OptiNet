# Fix4 当前整合版 batch1-3 验证

时间：2026-04-13  
环境：`ip_loc2_fix4_codex`  
输入：`rebuild5_fix4_work.etl_cleaned_shared_sample_local`  
范围：完整重跑 `2025-12-01 ~ 2025-12-03`

## 结论

当前整合版在 `batch1-3` 上已经可以完整跑通，程序层面没有新的中断或卡死。

这次验证确认了两件事：

1. 工程闭环是通的：
   - `Step2 path A / path B` 分流正常
   - `Step4 donor` 已经起量，不再出现 `batch2 donor=0`
   - `Step5 PostGIS` 不再是分钟级瓶颈
2. 研究口径还没有最终定稿：
   - `batch3 multi_centroid_cell_count = 113`
   - 这说明质心/多质心触发边界仍需继续研究
   - 但这不影响“当前程序已经正常跑完 1-3 批”的工程结论

## 运行结果

### batch1

- `Step2`: `pathA=0`, `pathB=292,872`, `pathB_cell=13,490`, `pathC=334`
- `Step3`: `waiting=0`, `qualified=3,807`, `excellent=1,939`
- `Step4`: `donor_matched=0`, `gps_filled=0`
- `Step5`: `published_cell=5,746`, `multi_centroid=0`, `dynamic=0`, `done=7s`

### batch2

- `Step2`: `pathA=235,711`, `pathB=57,905`, `pathB_cell=7,672`, `pathC=184`
- `Step3`: `waiting=0`, `qualified=6,337`, `excellent=2,084`
- `Step4`: `donor_matched=235,711`, `gps_filled=14,362`
- `Step5`: `published_cell=8,421`, `multi_centroid=0`, `dynamic=0`, `done=10s`

### batch3

- `Step2`: `pathA=247,441`, `pathB=23,953`, `pathB_cell=4,748`, `pathC=210`
- `Step3`: `waiting=0`, `qualified=7,674`, `excellent=2,120`
- `Step4`: `donor_matched=247,441`, `gps_filled=15,161`
- `Step5`: `published_cell=9,794`, `multi_centroid=113`, `dynamic=0`, `done=13s`

## 工程判断

### 1. 分流正常

`pathA` 在 batch2 / batch3 已经大量起量，说明：

- 已发布对象能被 `Step2` 正常命中
- 当前链路不存在“Step2 没有把已入库对象转发给后续步骤”的程序性问题

### 2. donor 闭环正常

`batch2 donor_matched_count = 235,711`，`batch3 donor_matched_count = 247,441`。

这说明当前 donor gate 修复已经生效：

- `path A` 命中的 published donor 可以直接参与 Step4 补数
- 当前不会再出现“第二轮仍然完全没有补数”的工程异常

### 3. Step5 PostGIS 性能已回到可接受水平

这次完整跑里：

- `batch2 Step5 = 10s`
- `batch3 Step5 = 13s`

对比此前 `batch3 publish_cell_centroid_detail()` 约 `369.9s` 的旧瓶颈，说明分阶段物化已经显著生效。

## 当前仍需继续研究的点

这次 1-3 批验证通过，不代表质心口径已经最终定稿。

当前最主要的研究遗留是：

- `batch3 multi_centroid_cell_count = 113`

这意味着：

- 现在的“核心点过滤 + 候选触发 + PostGIS 多质心”组合，工程上能跑通
- 但研究上还需要继续确认 `dual_cluster / multi_cluster` 是否偏敏感

所以当前最合理的判断是：

- 工程：可继续生成阶段性报告
- 研究：仍需下一轮单独收敛多质心边界

## 当前结论怎么用

如果现在目标是“确认程序是否正常”，答案是：

- 是，当前整合版已经能稳定跑完 `batch1-3`

如果现在目标是“确认质心研究是否已经结束”，答案是：

- 还没有，当前只证明了方案能跑，不证明参数边界已经最终收敛
