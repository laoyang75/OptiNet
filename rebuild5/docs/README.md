# Rebuild5 交付说明

本文件面向即将接手 `rebuild5` 的云端开发团队。

目标不是解释全部业务细节，而是帮助团队在最短时间内回答下面 5 个问题：

1. 这个系统在做什么
2. Step1 - Step5 各自负责什么
3. 当前哪些逻辑已经确认正确
4. 云端重构时哪些边界不能改坏
5. 如何先用样例跑通，再进入正式库

## 1. 项目是什么

`rebuild5` 是一套分步骤、按批次运行的网络位置画像处理链路。

主目标：

1. 从原始报文中清洗出结构化定位数据
2. 构建 Cell / BS / LAC 三层对象画像
3. 按批次累积证据，逐步让对象进入可信链路
4. 对已发布对象做补数、异常治理、多质心、碰撞、动态识别等维护

核心对象：

| 层级 | 说明 | 业务键 |
|---|---|---|
| Cell | 最小分析单元 | `(operator_code, tech_norm, lac, cell_id)` |
| BS | 基站聚合层 | `(operator_code, lac, bs_id)` |
| LAC | 区域聚合层 | `(operator_code, lac)` |

## 2. 当前正确的主线理解

这是最重要的部分。

### 2.1 Step1 - Step5 不是 5 个独立模块，而是一条状态机

正确主线：

```text
Step1 清洗
-> Step2 路由并确认 donor
-> Step3 评估候选域并冻结 snapshot
-> Step4 只用已确认 donor 补数
-> Step5 维护已发布对象并发布下一轮正式库
```

如果云端重构后，把某一步做成“局部更自洽”，但破坏了这条状态机，那就是错误。

### 2.2 最核心的职责边界

| 判断 / 动作 | 正确责任步骤 |
|---|---|
| 原始字段清洗、同报文互补 | Step 1 |
| 当前记录是否命中已发布对象 | Step 2 |
| donor 是谁 | Step 2 |
| 候选域生命周期评估 | Step 3 |
| Path A 记录补数 | Step 4 |
| 已发布对象维护、多质心、碰撞、动态 | Step 5 |

### 2.3 一个关键原则：上游决定的事，下游不能重复判断

最典型的是 Step4 donor 逻辑。

当前正确设计：

- Step 2 决定 donor 身份
- Step 4 直接消费 donor
- Step 4 不再重新判断 donor “够不够资格”

错误设计：

- Step 2 已确认 donor
- Step 4 又基于 `anchor_eligible` 再筛一遍 donor

这会打断 `Path A -> Step4` 闭环。

## 3. 当前已确认正确的逻辑

### 3.1 生命周期逻辑

当前确认有效的 Step3 生命周期口径是：

| 状态 | 规则 |
|---|---|
| `waiting` | `independent_obs < 3` |
| `observing` | `3 <= independent_obs < 10` |
| `qualified` | `independent_obs >= 10` |
| `excellent` | `independent_obs >= 30` |

说明：

- 生命周期只用于“晋级”
- `span24` 不再作为 Step3 晋级门槛
- 设备数、P90、跨度等仍然保留，但用于资格字段和后续治理，不再决定生命周期本身

### 3.2 `anchor_eligible` 的正确角色

`anchor_eligible` 仍然是重要字段，但当前主线里它的角色是：

- 高可信空间锚点资格
- 评估 / 治理 / 统计字段

它**不是**：

- Step4 donor 的二次准入门槛

### 3.3 GPS / 质心计算

当前主线里，GPS / 质心计算已经升级，不要再按旧的“全点直接中位数”理解。

当前实际逻辑：

1. 对分钟级独立观测点做 `SnapToGrid`
2. 选主热点 seed
3. 计算点到 seed 的距离
4. 根据 `core_position_filter` 计算 `keep_radius_m`
5. 只用核心点重算 `center_lon / center_lat / p50 / p90`

这套逻辑：

- Step2 用于稳住候选域输入
- Step5 在滑动窗口上再次使用，用于维护态重算

### 3.4 Step5 多质心 / 碰撞

当前主线里：

- A 类碰撞不是旧的 `COUNT(DISTINCT bs_id)` 逻辑
- 当前是基于 `cell_centroid_detail` 稳定簇之间的地理距离判断

多质心候选也不是只看过滤后的 `p90_radius_m`，还会联合：

- `raw_p90_radius_m`
- `max_spread_m`
- `core_outlier_ratio`
- `gps_anomaly_type`

## 4. 当前样例验证状态

当前本地主线已经在共享样例上验证了：

- `2025-12-01 ~ 2025-12-03`
- 样例库：`ip_loc2_fix4_codex`

当前有效样例结论：

`batch1`
- `waiting=3275`
- `qualified=3807`
- `excellent=1939`
- `published_cell=5746`

`batch2`
- `pathA=235711`
- `donor_matched=235711`
- `gps_filled=14362`
- `published_cell=8421`

`batch3`
- `pathA=247441`
- `donor_matched=247441`
- `published_cell=9794`
- `multi_centroid=113`

这说明：

1. `waiting` 重新有意义
2. `batch1` 没被卡死
3. `batch2 Path A` 和 donor 闭环成立

## 5. 云端重构时不要踩的坑

### 5.1 不要把 Step4 再改回 anchor 二次过滤

这是最容易被误改坏的点。

### 5.2 不要把 Step3 生命周期又改成“span24 决定晋级”

`span24` 是旧逻辑遗留，不适合当前流式晋级状态机。

如果云端团队要判断对象是否稳定，应该放到：

- Step5
- 或后续 Step6/统计质量层

而不是塞回 Step3 生命周期。

### 5.3 不要把 BS/LAC 重新当成原始观测对象

BS/LAC 只能自下而上派生：

```text
Cell -> BS -> LAC
```

不能跳过 Cell 重新定义一套原始规则。

### 5.4 不要把样例验证和正式全量混成同一个过程

推荐顺序必须是：

1. 样例验证
2. 样例指标核对
3. 备份正式库
4. 正式库重跑

## 6. 云端团队推荐上手顺序

建议按这个顺序阅读：

1. [处理流程总览.md](/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/处理流程总览.md)
2. [00_全局约定.md](/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/00_全局约定.md)
3. [03_流式质量评估.md](/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/03_流式质量评估.md)
4. [04_知识补数.md](/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/04_知识补数.md)
5. [05_画像维护.md](/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/05_画像维护.md)
6. [runbook_v5.md](/Users/yangcongan/cursor/WangYou_Data/rebuild5/docs/runbook_v5.md)

推荐按这个顺序理解代码：

1. `backend/app/profile/pipeline.py`
2. `backend/app/evaluation/pipeline.py`
3. `backend/app/enrichment/pipeline.py`
4. `backend/app/maintenance/window.py`
5. `backend/app/maintenance/collision.py`
6. `backend/app/maintenance/publish_bs_lac.py`

## 7. 云端改造建议

### 7.1 当前适合云端化的方向

云端团队的任务不应该是改业务语义，而应该是：

1. 把现在已经确认的主线逻辑稳定搬到云端
2. 把数据库访问、日志、重跑控制、调度方式云端化
3. 让样例验证、正式重跑、回滚备份更自动化

### 7.2 当前不建议优先做的事

不要优先在云端重构阶段做：

1. 生命周期业务语义重定义
2. 多质心分类大改
3. 全面分表重构
4. UI 逻辑改写

这些都应该放在“现有主线先稳定跑通”之后。

### 7.3 当前最适合云端团队先做的能力

1. 远端样例验证脚本化
2. 远端正式库备份与重跑脚本化
3. 完整日志落盘
4. 失败恢复
5. 参数化运行
6. 数据库连接与环境隔离

## 8. 最后的判断

对云端团队来说，当前最重要的不是“继续猜业务逻辑”，而是：

**先把已经确认正确的主线状态机和运行边界稳定搬到云端。**

如果后续需要继续做：

- 生命周期优化
- 参数验证
- 速度持续优化
- 分表重构

都应建立在“这条主线已在云端可靠可重放”的前提上。

