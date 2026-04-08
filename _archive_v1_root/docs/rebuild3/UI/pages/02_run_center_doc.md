# 运行中心设计说明

## 页面目标
管理和监控 run/batch/baseline 的完整生命周期，是系统的时间轴和版本轴控制中心

## 用户主要操作
1. 查看当前运行状态和进度
2. 查看各批次的四分流结果
3. 切换和对比 baseline 版本
4. 查看历史运行记录
5. 触发新的批次或运行

## 页面区块说明
| 区块名称 | 面积占比 | 核心作用 | 核心字段 |
|---------|---------|---------|---------|
| 当前运行摘要 | 15% | 一眼看到运行全貌 | run_id, type, status, baseline, progress |
| 批次列表 | 45% | 查看每个批次的详细结果 | batch_id, window, 四分流数量, 晋升/降级, 耗时 |
| Baseline 历史 | 20% | 管理基线版本 | version, time, object_count, status |
| 运行历史 | 20% | 查看历史运行 | run_id, type, status, batch_count |

## 筛选器 & 排序
- 运行类型筛选：全部/初始化/增量
- 批次状态筛选：全部/运行中/已完成/失败
- 时间范围筛选

## 状态表达规则
- 运行中：绿色脉冲圆点
- 已完成：绿色实心对勾
- 失败：红色叉号
- 批次运行中行高亮 amber 背景

## 组件边界建议
- RunCenterView.vue
  - CurrentRunSummary
  - BatchTimeline (表格 + 行展开)
  - BaselineHistory (列表)
  - RunHistory (列表)

## 读模型建议
- /api/v1/run/current — 当前运行摘要
- /api/v1/run/:id/batches — 批次列表
- /api/v1/baseline/list — baseline 版本列表
- /api/v1/run/history — 运行历史

## 空状态 / 错误状态
- 无运行记录：显示"暂无运行记录，请启动初始化运行"
- 批次加载失败：表格显示错误提示，可重试

## 开发注意事项
- 运行中批次需要定时刷新状态（10s）
- 四分流数字建议用 sparkline 或 mini bar 辅助
- baseline 切换需要确认对话框
