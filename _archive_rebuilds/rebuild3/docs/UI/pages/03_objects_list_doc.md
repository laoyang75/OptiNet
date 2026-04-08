# 对象浏览设计说明

## 页面目标
浏览和搜索系统中所有已注册的治理对象（Cell/BS/LAC），快速了解每个对象的生命周期、健康状态和资格

## 用户主要操作
1. 按类型/状态/资格筛选对象
2. 搜索特定对象主键
3. 查看对象列表和关键指标
4. 点击对象打开详情抽屉
5. 识别需要关注的 WATCH 对象

## 页面区块说明
| 区块名称 | 面积占比 | 核心作用 | 核心字段 |
|---------|---------|---------|---------|
| 筛选器栏 | 10% | 快速缩小范围 | type, lifecycle, health, qualification |
| 对象表格 | 80% | 展示对象列表和状态 | 主键, 类型, lifecycle, health, anchorable, baseline_eligible, 样本数, 设备数 |
| 分页器 | 5% | 翻页 | page, per_page, total |
| WATCH 指示 | inline | 标记 active 但异常的对象 | lifecycle=active && health!=healthy |

## 筛选器 & 排序
- 对象类型: Cell / BS / LAC / 全部
- lifecycle_state: 全部 + 6个状态
- health_state: 全部 + 7个状态
- 资格: 可锚定/锚点禁用/可进基线/基线禁用
- 搜索: 对象主键模糊搜索
- 排序: 最后活跃时间(默认) / 样本数 / 设备数 / 活跃天数

## 状态表达规则
- lifecycle: 彩色圆点+文字徽标
- health: 彩色图标+文字
- anchorable: green ✓ / red 🔒 / gray ✗
- baseline_eligible: green ✓ / red ⊘ / gray ✗
- WATCH: 行左侧橙色竖线 + 右侧橙色小标签
- rejected: 整行文字灰色 + 删除线

## 组件边界建议
- ObjectsListView.vue
  - ObjectFilter (筛选器栏)
  - ObjectTable (表格, 支持 table/card 视图切换)
  - ObjectTableRow (单行, 含状态徽标)
  - Pagination
  - -> 点击行触发 CellDetailDrawer / BsDetailDrawer / LacDetailDrawer

## 读模型建议
- /api/v1/objects?type=&lifecycle=&health=&page=&per_page= 
- 支持排序和搜索参数
- 后端预 JOIN 状态和资格字段，不要前端多次请求
- 大列表必须分页，每页 20-50

## 空状态 / 错误状态
- 无对象: "暂无已注册对象，请先完成初始化运行"
- 筛选无结果: "没有符合条件的对象，请调整筛选条件"
- 加载失败: 表格区域显示错误提示+重试按钮

## 开发注意事项
- 表格行要支持虚拟滚动(当数据量大时)
- WATCH 状态由前端从 lifecycle+health 组合派生
- 卡片视图适合快速扫视，表格视图适合批量操作
