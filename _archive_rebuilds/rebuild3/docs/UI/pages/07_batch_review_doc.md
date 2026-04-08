# 批次审查设计说明

## 页面目标
审查单个批次的完整决策结果，包括四分流统计、晋升/降级/级联更新，以及各层事实明细

## 用户主要操作
1. 选择批次查看决策结果
2. 查看四分流比例和趋势
3. 审查晋升/降级/级联决策
4. 浏览各层事实明细
5. 查看拒收记录和原因

## 页面区块说明
| 区块名称 | 面积占比 | 核心作用 | 核心字段 |
|---------|---------|---------|---------|
| 批次选择器 | 5% | 切换批次 | batch_id, window, input_count, status |
| 四分流漏斗 | 15% | 可视化分流结果 | 4层事实数量和占比 |
| 决策摘要 | 25% | 查看晋升/降级/级联 | 对象, 变更前后状态, 原因 |
| 事实明细 | 45% | 浏览各层事实 | event_key, cell, gps_source, signal_source, tags |
| 拒收记录 | 10% | 查看拒收原因 | event_key, record, reason |

## 筛选器 & 排序
- 批次选择: 下拉列表
- 事实层 tab 切换
- 事实明细内支持搜索和排序

## 状态表达规则
- 四分流: governed绿/pending_obs黄/pending_issue橙/rejected红
- 晋升行: 绿色左侧线
- 降级行: 灰色左侧线
- 级联行: 蓝色左侧线
- gps_source/signal_source: original显绿色, 回填显灰色

## 组件边界建议
- BatchReviewView.vue
  - BatchSelector
  - FourWayFunnel (四分流可视化)
  - DecisionSummary
    - PromotionTable
    - CascadeTable
  - FactDetailTabs
    - FactTable (各层复用)
  - RejectedRecords

## 读模型建议
- /api/v1/batch/:id/summary — 四分流统计
- /api/v1/batch/:id/decisions — 晋升/降级/级联
- /api/v1/batch/:id/facts?layer=governed&page= — 分层事实
- /api/v1/batch/:id/rejected — 拒收记录

## 空状态 / 错误状态
- 无批次: "当前运行暂无完成的批次"
- 批次运行中: 四分流区域显示"批次运行中..."动画
- 事实明细为空: "该层暂无事实记录"

## 开发注意事项
- 四分流用 ECharts 水平漏斗图或堆叠条形图
- 事实明细可能很多(数万行)，必须分页+延迟加载
- 批次切换时需清空并重新加载数据
- 运行中批次需显示实时进度
