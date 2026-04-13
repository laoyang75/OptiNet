# 第一阶段修改意见：Step 6 UI 小修复

## 目标

本阶段只对服务层页面做轻量收口，不扩展复杂查询能力。

目标是：

- 修复搜索结果点开详情时可能串详情的问题
- 把服务层文案往业务友好方向收一层
- 将未实现能力统一标注为待开发

## 本阶段不做

- 运营商筛选器
- 坐标范围查询
- 覆盖分析的区域选择 / 密度图 / 质量分布图
- 统计报表趋势图

## 建议修改项

### 1. 站点详情必须带上下文

当前问题：

- 搜索结果项已包含 `operator_code / lac / tech_norm`
- 但点开详情时如果只传 `cell_id / bs_id / lac`，会存在串详情风险

建议：

- Cell 详情携带 `operator_code + lac + tech_norm`
- BS 详情携带 `operator_code + lac`
- LAC 详情携带 `operator_code`

建议触达文件：

- `rebuild5/backend/app/service_query/queries.py`
- `rebuild5/backend/app/routers/service.py`
- `rebuild5/frontend/design/src/api/service.ts`
- `rebuild5/frontend/design/src/views/service/StationQuery.vue`

### 2. 服务层文案业务友好化

当前问题：

- 当前页面仍直接暴露部分治理字段
- 业务用户更需要“风险提示”和“可用性”表达

建议：

- 页面标题改成 `站点查询`
- 把 `anchor_eligible / baseline_eligible` 改成更业务友好的说明
- 把 `is_collision / is_dynamic / is_multi_centroid` 改成风险提示式命名

建议触达文件：

- `rebuild5/frontend/design/src/views/service/StationQuery.vue`
- `rebuild5/docs/06_服务层_运营商数据库与分析服务.md`
- `rebuild5/ui/08_服务层页面.md`

### 3. 未实现功能统一标待开发

当前问题：

- 文档里对查询、分析、报表能力写得比当前实现更强

建议：

- 站点查询页：
- 运营商筛选、LAC筛选、坐标范围查询待开发
- 覆盖分析页：
- 区域选择、筛选器、密度图、质量分布图待开发
- 统计报表页：
- 趋势图待开发

## 验收标准

- 搜索结果点开详情不再串记录
- 服务层页面文案比当前更业务友好
- 未实现能力不再被描述为现有能力
