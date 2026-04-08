# 流转线 API 与流程验收清单（Claude 草案）

状态：可合并草案  
更新时间：2026-04-06

## 1. 总原则

每个流程模块都必须同时通过三层检查：

1. 数据库层：主语与数量真实
2. API 层：返回结构与 `data_origin` 合同真实
3. 页面层：Playwright 验证页面主语、上下文、状态展示真实

## 2. `runs`

### 数据库检查
- `run`、`batch` 记录存在
- run/batch 关系正确
- `data_origin` 有明确值

### API 检查
- `/runs` 返回 run 列表、批次列表、当前选中详情
- 返回结构包含 `run_id`、`batch_id`、`data_origin`、状态摘要

### 页面检查
- Playwright 打开 `/runs`
- 断言列表非空
- 切换 run 后详情区同步更新
- `data_origin` 标签可见

## 3. `flow overview`

### 数据库检查
- 批次级四分流统计存在
- overview 主语对应某个 batch

### API 检查
- `/flow/overview` 返回单一 batch 上下文
- 返回结构包含 `batch_id`、`run_id`、`data_origin`、baseline 引用、四分流摘要

### 页面检查
- Playwright 打开 `/flow/overview`
- 检查页面显示批次上下文
- 检查流程节点与统计块可见
- 若为 synthetic，必须出现评估提示

## 4. `flow snapshot`

### 数据库检查
- 存在 `snapshot_timepoint`
- timepoint 归属到具体 batch

### API 检查
- `/flow/snapshot` 返回 batch + timepoint 维度上下文
- 返回结构包含 `snapshot_id`、`phase_code`、`data_origin`

### 页面检查
- Playwright 打开 `/flow/snapshot`
- 检查时间点选择器可见
- 切换时间点后表格/指标变化
- 若没有 real snapshot，只允许 honest empty 或 synthetic 评估模式

## 5. `baseline`

### 数据库检查
- `baseline_version_in / out` 可追溯

### API 检查
- `/baseline` 返回当前查看版本与上一版关系

### 页面检查
- Playwright 检查版本号、来源、摘要可见
- 不允许把“上一版对比”写成无来源说明的临时差异

## 6. `objects` / `object detail` / profiles

### 数据库检查
- LAC / BS / Cell 对象结果存在
- 对象记录可追到 batch 与 baseline

### API 检查
- 对象列表与详情接口返回对象主键、状态、资格、来源

### 页面检查
- Playwright 检查对象列表可筛选
- 点击进入详情页后主键与状态上下文一致
- 画像页字段名与口径符合冻结文档

## 7. `initialization`

### 数据库检查
- 数据准备状态可追溯到 P0/P1 实体

### API 检查
- `/initialization` 返回准备项与完成状态

### 页面检查
- Playwright 检查准备项列表存在
- 如关键前置未满足，不得显示“已完成”

## 8. `compare` / `governance`

### 数据库检查
- 确认真实数据或降级来源状态

### API 检查
- 返回结构必须暴露 `data_origin`
- 若是 fallback，必须显式返回降级说明

### 页面检查
- Playwright 检查 banner / badge / 提示文案
- 不允许无提示展示 fallback 数据

## 9. 流程级联验收

必须存在至少一条贯穿链路：

`runs -> flow overview -> flow snapshot -> objects -> object detail -> baseline`

通过标准：
- 页面能逐步打开
- 上下文主语连续
- `run_id / batch_id / baseline_version / data_origin` 能贯穿核对

未通过处理：
- 回到映射矩阵修正页面/API/表绑定，不允许只修 UI 文案
