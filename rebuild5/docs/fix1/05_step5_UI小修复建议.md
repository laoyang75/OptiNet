# 第一阶段修改意见：Step 5 UI 小修复

## 目标

本阶段只做 Step 5 治理页面的轻量对齐，不扩展重度治理工作台能力。

目标是：

- 把当前已支持的异常筛选、列表展开和摘要能力表达清楚
- 把仍未实现的深度钻取能力标注为待开发
- 修正页面里与当前状态机不一致的 `active` 旧术语

## 本阶段不做

- 单对象完整时间演化面板
- BS / LAC 深度来源钻取
- 归档数据单独页面
- 多质心研究结果固化后的深度图形化展示

## 建议修改项

### 1. 统一状态文案

当前问题：

- 部分页面仍用 `Active` 旧术语
- 当前生命周期体系已经统一为 `waiting / observing / qualified / excellent / dormant / retired`

建议：

- BS / LAC 页面把 `Active` 卡片统一改为 `Qualified`
- 避免和旧实现术语混用

建议触达文件：

- `rebuild5/frontend/design/src/views/governance/BSMaintain.vue`
- `rebuild5/frontend/design/src/views/governance/LACMaintain.vue`

### 2. Cell 页启用 dormant / retired 过滤

当前问题：

- 页面上已有 `dormant / retired` 过滤按钮
- 如果后端不处理，这两个按钮就是假能力

建议：

- 后端查询层补齐 `dormant / retired` 过滤
- 页面保留这些按钮，作为当前已支持能力

建议触达文件：

- `rebuild5/backend/app/maintenance/queries.py`
- `rebuild5/frontend/design/src/views/governance/CellMaintain.vue`

### 3. 文档补充“当前支持 / 待开发”边界

当前问题：

- 文档容易让人以为 Cell / BS / LAC 页已经具备完整治理工作台能力
- 当前实现更接近“摘要 + 列表展开”

建议：

- 文档中明确：
- 当前已支持：摘要卡片、异常筛选、列表展开、关键字段查看
- 待开发：完整单对象时间演化、下属对象深度来源钻取、归档治理面板

建议触达文件：

- `rebuild5/ui/06_知识补数与治理页面.md`

## 验收标准

- Step 5 页面不再混用 `active` 旧术语
- `dormant / retired` 过滤真正可用
- 文档不再把未实现的深度治理能力描述成现有能力
