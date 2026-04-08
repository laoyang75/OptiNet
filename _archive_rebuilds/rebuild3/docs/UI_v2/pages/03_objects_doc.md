# 对象浏览 设计说明

## 页面目标
浏览和筛选所有治理对象，快速识别异常、资格禁用和状态变化。

## 这个页面主要回答什么问题
1. 哪些对象健康/异常/等待中
2. 哪些对象锚点或基线被禁用
3. 对象的样本量和活跃度分布
4. 哪些 active 对象需要重点关注（WATCH）

## 用户主要操作
1. 按类型/状态/健康/资格筛选
2. 搜索特定主键
3. 扫描表格识别异常行（橙色边框=WATCH）
4. 点击行下钻到对象详情

## 页面区块说明
| 区块名称 | 面积占比 | 核心作用 | 必须字段 | 是否需要 delta | 是否支持下钻 |
|---------|---------|---------|---------|---------------|-------------|
| 筛选栏 | 5% | 类型/状态/资格过滤 | 类型tab/lifecycle/health/qualification | 否 | 否 |
| 汇总条 | 5% | 总量+分布+delta | 总数/各状态数/delta | 是 | 否 |
| 对象表格 | 85% | 浏览+识别异常 | 主键/lifecycle/health/锚点/基线/样本/设备/天数/活跃时间/异常 | 否 | 是(→详情) |
| 分页 | 5% | 翻页 | 页码/总页数 | 否 | 否 |

## 筛选器与切换器
- 对象类型 tab: Cell / BS / LAC
- 生命周期: 全部/waiting/observing/active/dormant/retired/rejected
- 健康状态: 全部 + 7种health_state
- 资格: 全部/锚点可用/锚点禁用/基线可用/基线禁用
- 搜索: 主键模糊搜索
- 排序: 主键/样本数/活跃天数/最近活跃时间

## 状态表达规则
- lifecycle_state: 彩色圆点 + 文字徽标
- health_state: 图标 + 颜色
- anchorable/baseline_eligible: ✓绿色 / ✗灰色锁
- WATCH: 橙色左边框 + 橙色WATCH小徽标（active且health!=healthy时）

## 下钻路径
- 行点击 → 对象详情页

## 组件边界建议
- ObjectsListView.vue (页面)
- ObjectTypeTab.vue / ObjectFilter.vue (筛选)
- ObjectSummaryBar.vue (汇总条)
- ObjectTable.vue (表格)
- LifecycleBadge.vue / HealthBadge.vue / QualificationTags.vue (共享)

## 读模型建议
- GET /api/objects?type=cell&lifecycle=active&health=all&page=1&size=20
- 汇总: GET /api/objects/summary?type=cell (各状态计数+delta)

## 空状态 / 错误状态 / 重跑中状态
- 空: 筛选无结果时"未找到匹配的对象，请调整筛选条件"
- 错误: API失败时表格区域显示错误+重试
- 重跑: 顶部提示"部分对象状态可能因重跑更新"

## 开发注意事项
- 对象数量可达万级，必须分页
- WATCH 状态由前端根据 lifecycle=active && health!=healthy 派生
- 表格行hover高亮，点击整行跳转
