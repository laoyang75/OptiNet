# 第一阶段修改意见：Step 2 UI 小修复

## 目标

本阶段只对 Step 2 页面做轻量 UI 收口，不调整 Step 2 核心路由逻辑。

目标是：

- 把当前页面已经支持的能力展示清楚
- 把尚未支持的筛选、样本、跳转能力显式标成待开发
- 修正文案中会在非冷启动场景下失真的静态描述
- 补充当前规则口径和 Path C 统计说明，减少误读

## 本阶段不做

- 新增运营商 / LAC 筛选器
- 新增碰撞样本列表
- 新增 Path B 明细表
- 新增跳转 Step 3 / Step 4 的联动能力
- 改写 Step 2 后端统计口径

## 建议修改项

### 1. Path A 文案改为动态表达

当前问题：

- 页面把“冷启动，Path A = 0”写成固定说明
- 一旦正式库存在，这句就会直接失真

建议：

- 根据 `snapshot_version_prev` 和 `path_a_record_count` 动态展示
- 冷启动时说明“上一轮正式库为空”
- 非冷启动时说明“当前按上一轮正式库执行命中判定”

建议触达文件：

- `rebuild5/frontend/design/src/views/profile/Routing.vue`

### 2. Path C 口径增加说明

当前问题：

- 当前 Path C 展示的是汇总剩余丢弃量
- 页面上容易被理解成“纯无 GPS 丢弃”

建议：

- 在规则说明区补一句：
- `当前 Path C 为汇总丢弃量；若碰撞局部防护触发，请结合 collision_drop_count 一并解释`

建议触达文件：

- `rebuild5/frontend/design/src/views/profile/Routing.vue`

### 3. 当前支持 / 待开发分区

当前问题：

- 文档里提到筛选、样本、跳转等能力
- 当前页面实际只支持路由总览和基础统计摘要

建议：

- 在页面内新增“当前支持 / 待开发”区块
- 当前支持：
- 数据版本头部、A/B/C 概览、碰撞防护摘要、Path B 摘要、规则口径只读展示
- 待开发：
- 运营商 / LAC 筛选、碰撞样本、Path B 列表、跳转 Step 3 / Step 4、在线改参数

建议触达文件：

- `rebuild5/frontend/design/src/views/profile/Routing.vue`
- `rebuild5/ui/04_基础画像与分流页面.md`

### 4. Path B 摘要补足已支持指标

当前问题：

- 后端已有 `avg_observed_span_hours`、`avg_p50_radius_m`、`avg_gps_original_ratio`、`avg_signal_original_ratio`
- 页面当前没有全部展示

建议：

- 在现有摘要区补齐：
- 平均跨度
- 平均 P50
- 平均 GPS 原始覆盖率
- 平均信号原始覆盖率

建议触达文件：

- `rebuild5/frontend/design/src/views/profile/Routing.vue`

### 5. 规则配置改成“当前规则口径（只读）”

当前问题：

- 文档中曾以“规则配置区”表述，容易让人理解成页面上可在线修改参数
- 当前实际只适合展示口径，不适合开放在线调整

建议：

- 页面用“当前规则口径”代替“规则配置”
- 展示：
- 碰撞 GPS 阈值
- 观测去重窗口
- 质心算法
- 并明确“当前为只读展示”

建议触达文件：

- `rebuild5/frontend/design/src/views/profile/Routing.vue`
- `rebuild5/ui/04_基础画像与分流页面.md`

## 验收标准

- 页面不再把“冷启动 Path A=0”写死
- 页面明确说明 Path C 的当前口径
- 页面显式区分“当前支持”和“待开发”
- 页面能够展示后端已经提供的 Step 2 核心摘要指标
- 不新增新的后端依赖，不改变 Step 2 核心路由逻辑
