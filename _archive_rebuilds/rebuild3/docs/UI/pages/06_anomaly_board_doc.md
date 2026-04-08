# 异常看板设计说明

## 页面目标
集中管理所有存在健康问题的对象，帮助用户快速识别、复核和处理各类异常

## 用户主要操作
1. 按异常类型筛选和浏览问题对象
2. 查看异常严重级别和影响范围
3. 确认或解除碰撞嫌疑
4. 确认迁移或维持观察
5. 复核 GPS 偏差

## 页面区块说明
| 区块名称 | 面积占比 | 核心作用 | 核心字段 |
|---------|---------|---------|---------|
| 类型汇总卡 | 10% | 各类异常数量概览 | 各类型异常数量 |
| 筛选栏 | 5% | 缩小范围 | type, severity, object_type, time |
| 异常表格 | 75% | 展示异常对象和操作 | 主键, 异常类型, severity, health, 资格, 影响, 操作 |
| 影响汇总 | 10% | 异常总体影响 | 禁锚数, 禁基线数, 涉及BS数 |

## 筛选器 & 排序
- 异常类型: 全部 + 5种类型
- 严重级别: 全部/高/中/低
- 对象类型: 全部/Cell/BS/LAC
- 时间: 全部/今日/近7天/近30天
- 排序: 严重级别(默认)/发现时间/影响范围

## 状态表达规则
- collision_suspect: 橙色三角警告
- collision_confirmed: 红色禁止图标
- dynamic: 蓝色移动箭头
- migration_suspect: 紫色迁移箭头
- gps_bias: 橙色定位偏移
- 严重级别: 红/橙/黄圆点
- 行左侧竖线颜色跟随异常类型

## 组件边界建议
- AnomalyBoardView.vue
  - AnomalySummaryCards (5个类型卡)
  - AnomalyFilter
  - AnomalyTable
    - AnomalyTableRow (含操作按钮)
  - ImpactSummary
  - -> 操作按钮触发 AnomalyDetailDrawer

## 读模型建议
- /api/v1/anomalies?type=&severity=&object_type=&page=
- /api/v1/anomalies/summary — 各类型计数
- /api/v1/anomalies/:id/impact — 影响范围
- 每个异常需返回: 对象主键, 类型, severity, health_state, 资格状态, 发现时间, 影响范围

## 空状态 / 错误状态
- 无异常: "当前没有异常对象" (绿色成功状态，显示对勾)
- 筛选无结果: "没有符合条件的异常"

## 开发注意事项
- 操作按钮(确认碰撞/解除等)需要二次确认
- 确认操作会级联影响关联对象，需显示影响预览
- collision 的确认/解除是高风险操作，按钮需突出警示
- 高严重级别的行建议自动置顶
