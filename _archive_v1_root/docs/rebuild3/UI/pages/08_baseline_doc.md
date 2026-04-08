# 基线管理设计说明

## 页面目标
管理 baseline 版本的完整生命周期，对比不同版本间的差异，评估基线质量和覆盖率

## 用户主要操作
1. 查看当前活跃 baseline 信息
2. 浏览版本历史
3. 对比两个版本间的差异
4. 查看覆盖分布和质量指标
5. 下钻查看差异对象详情

## 页面区块说明
| 区块名称 | 面积占比 | 核心作用 | 核心字段 |
|---------|---------|---------|---------|
| 当前基线卡 | 10% | 显示当前活跃版本 | version, frozen_at, coverage, status |
| 版本列表 | 25% | 浏览所有版本 | version, time, count, status |
| 版本对比 | 35% | 对比两版差异 | 新增/移除/变更数量, 差异对象列表 |
| 覆盖分布 | 15% | 当前版本分布 | health/lifecycle 分布图 |
| 质量指标 | 15% | 基线质量评估 | GPS可信度, 信号覆盖, 异常占比 |

## 筛选器 & 排序
- 版本对比: 选择两个版本进行对比
- 差异表格: 按变更类型筛选(新增/移除/变更)
- 覆盖分布: 按对象类型筛选

## 状态表达规则
- 活跃版本: 绿色"活跃"徽标
- 归档版本: 灰色"已归档"徽标
- 新增对象: 绿色 + 号
- 移除对象: 红色 - 号
- 状态变更: 橙色 ~ 号
- 质量指标: 绿色(好)/黄色(一般)/红色(差)

## 组件边界建议
- BaselineView.vue
  - CurrentBaselineCard
  - VersionList
  - VersionComparison
    - DiffSummaryCards
    - DiffTable
  - CoverageCharts (ECharts)
  - QualityMetrics (MetricCard)

## 读模型建议
- /api/v1/baseline/current — 当前版本详情
- /api/v1/baseline/list — 版本列表
- /api/v1/baseline/compare?v1=12&v2=11 — 版本对比
- /api/v1/baseline/:version/distribution — 分布统计
- /api/v1/baseline/:version/quality — 质量指标
- 对比结果应后端预计算，不让前端做大量 diff

## 空状态 / 错误状态
- 无基线: "暂无 baseline 版本，请先完成初始化运行"
- 只有一个版本: 对比功能不可用，提示"至少需要两个版本才能对比"
- 对比加载中: diff 区域显示骨架屏

## 开发注意事项
- 版本对比可能涉及大量对象，差异表格必须分页
- 分布图使用 ECharts，注意配色与状态色一致
- 质量指标数值需要后端预聚合
- 版本列表如果很长(>50)需要虚拟滚动或加载更多
