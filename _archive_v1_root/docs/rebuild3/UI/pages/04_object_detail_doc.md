# 对象详情设计说明

## 页面目标
展示单个治理对象（Cell/BS/LAC）的完整信息，帮助用户理解对象当前状态、资格原因、历史变更和关联关系

## 用户主要操作
1. 查看对象基本信息和当前状态
2. 理解锚点/基线资格的具体原因
3. 查看对象画像（GPS/信号统计）
4. 查看状态变更历史时间线
5. 查看关联的父/子对象

## 页面区块说明
| 区块名称 | 面积占比 | 核心作用 | 核心字段 |
|---------|---------|---------|---------|
| 头部信息 | 10% | 对象标识和当前状态总览 | 主键, type, lifecycle, health, qualifications |
| 基本信息 | 20% | 结构化展示对象属性 | operator, tech, lac, cell_id, bs_id, 时间 |
| 关键指标 | 15% | 核心统计摘要 | GPS点数, 设备数, 活跃天数, 半径 |
| 资格详情 | 20% | 三层资格判定原因 | 存在/锚点/基线资格及各项条件 |
| Tab内容 | 35% | 画像/历史/关系/事实 | 按 tab 切换不同维度 |

## 筛选器 & 排序
- 历史 tab: 按时间正/倒序
- 事实 tab: 按事实层筛选
- 关系 tab: 按关系类型筛选

## 状态表达规则
- 头部徽标与列表页一致
- 资格详情使用绿色 ✓ / 红色 ✗ 逐项标注
- 历史时间线使用竖线+圆点+状态色

## 组件边界建议
- CellDetailDrawer.vue (抽屉容器)
  - DetailHeader (标识+状态+资格)
  - DetailTabs (概览/画像/历史/关系/事实)
  - BasicInfoCard
  - MetricMiniCards
  - QualificationDetail
  - StateTimeline
  - RelationGraph
  - FactDistribution

## 读模型建议
- /api/v1/objects/:type/:key — 对象完整快照
- /api/v1/objects/:type/:key/history — 状态历史
- /api/v1/objects/:type/:key/relations — 关系
- /api/v1/objects/:type/:key/facts?recent=true — 最近事实
- 概览 tab 数据可一次性加载，其他 tab 延迟加载

## 空状态 / 错误状态
- 对象不存在: "未找到该对象"
- 历史为空: "暂无状态变更记录"
- 关系为空: "暂无关联对象"

## 开发注意事项
- 抽屉动画建议 300ms ease-out 从右滑入
- Cell/BS/LAC 共用抽屉框架，内容区按类型差异化
- BS 详情需额外展示子 Cell 列表
- LAC 详情需额外展示区域健康统计
