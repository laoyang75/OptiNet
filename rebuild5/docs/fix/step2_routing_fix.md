# Step 2 路由压缩错误修复说明

> 适用范围：`rebuild5` Step 2 基础画像与分流  
> 修复对象：`rebuild5/backend/app/profile/pipeline.py` 为主  
> 问题性质：开发中的典型错误 —— 过早压缩数据，导致路由判定和对象聚合失真

## 1. 问题概述

Step 2 当前存在两类典型的“错误压缩数据”问题：

1. **ID 碰撞回退时，把多候选提前压缩成单候选**
2. **Cell 聚合时，把不该参与主键的字段混入主链，导致对象被错误切分**

这两类问题都不属于业务规则本身错误，而是实现过程中为了简化处理，过早把数据压扁了，导致主流程判断失真。

## 2. 已确认业务规则

## 2.1 两类碰撞必须严格区分

### A 类：真碰撞（Step 5 负责）

真碰撞定义：

- `(operator_code, tech_norm, lac, cell_id)` 相同
- GPS 距离很大，至少超过 `20km`
- 并且形成两个稳定簇

说明：

- 如果簇很多，不应直接判为真碰撞，可能属于动态对象（例如高铁）
- 这类判断属于 Step 5 维护逻辑，不属于 Step 2

### B 类：ID 碰撞（Step 5 生成表，Step 2 消费）

ID 碰撞定义：

- 同一个 `cell_id` 在多个 `(operator_code, lac)` 组合中出现

说明：

- 这不等于真碰撞
- 它只是说明这个 `cell_id` 不能再被当成全局天然唯一
- Step 2 读取 `collision_id_list` 的目的，是在 Path A 命中时增加校验

## 2.2 Step 2 的正常工作方式

- 如果 `cell_id` **不在** `collision_id_list` 中：
  - 按普通分流逻辑处理
  - 不额外升级碰撞校验

- 如果 `cell_id` **在** `collision_id_list` 中：
  - 不能只凭 `cell_id` 直接认定命中
  - 必须做更多校验

## 2.3 Step 2 的 Cell 主键

Step 2 的 Cell 业务主键固定为：

```text
(operator_code, lac, cell_id)
```

说明：

- `bs_id` 不应参与 Cell 主键切分
- `bs_id` 和 Cell 本质上是派生关系，不能反向定义 Cell

## 3. 当前实现中的错误压缩

## 3.1 ID 碰撞 Layer 3 被错误压缩成单候选

当前 Layer 3 回退逻辑会先对正式库执行：

```sql
SELECT DISTINCT ON (cell_id) *
```

这意味着：

- 一个发生 ID 碰撞的 `cell_id`
- 明明在正式库里有多个 `(operator_code, lac)` 候选
- 但在真正比较前，先被压成了 **一条代表候选**

问题：

- Step 2 原本应该对“候选集合”做更多校验
- 现在却变成了“只和一个候选比距离”
- 这会把本来应当继续判定的记录，提前压扁成错误结论

这是 Step 2 当前最关键的问题。

## 3.2 Cell 聚合链路里混入了 `bs_id`

当前 Path B / `profile_base` 相关 SQL 里，`bs_id` 仍参与 GROUP BY / JOIN 主链。

问题：

- 这会让同一个 Cell 因为 `bs_id` 参与切分而被拆成多个对象
- 本质上也是一种错误压缩 / 错误切分
- 这不属于可接受的“实现偏好”，而是明确的实现错误

## 4. 正确修复目标

## 4.1 ID 碰撞回退必须基于候选集合

正确逻辑应为：

1. 对命中 `collision_id_list` 的记录，找出同 `cell_id` 的全部正式库候选
2. 若记录携带 `operator_code`，先按 `operator_code` 缩小候选
3. 若记录携带 `lac`，再按 `lac` 缩小候选
4. 若仍有多个候选，再基于 GPS 距离判断
5. 最终至少区分：
   - 唯一命中
   - 无候选接近
   - 多候选仍冲突

关键点：

- 不能先 `DISTINCT ON (cell_id)`
- 不能在真正判定前把候选集合压缩成单候选

## 4.2 Step 2 主键必须收回到 Cell 真实业务键

修复目标：

- Path B 的对象切分
- `profile_obs`
- `profile_base`

都应统一围绕：

```text
(operator_code, lac, cell_id)
```

执行。

`bs_id` 只能作为：

- 维度字段
- 派生字段
- 展示字段

不能继续作为 Cell 主链聚合字段。

## 5. 推荐修复方案

## 5.1 修复 ID 碰撞 Layer 3

建议把 Layer 3 从：

```text
单候选 GPS 回退
```

改成：

```text
候选集合 GPS 回退
```

推荐实现顺序：

- `collision_candidates`
  - 保留同 `cell_id` 的全部 combo
- `filtered_candidates`
  - 按记录已有的 `operator_code / lac` 缩小候选
- `distance_ranked_candidates`
  - 对剩余候选计算 GPS 距离并排序
- `final_collision_resolution`
  - 输出唯一命中 / 冲突 / 无命中

## 5.2 清理 `bs_id` 参与主键的实现残留

建议检查并修复：

- `build_path_b_cells`
- `build_profile_obs`
- `build_profile_base`

修复原则：

- 只保留 `(operator_code, lac, cell_id)` 作为 Cell 对象聚合主键
- `bs_id` 不再参与主对象切分

## 6. 验收标准

满足以下条件才算修复完成：

1. ID 碰撞回退不再使用单候选压缩
2. Step 2 在 `collision_id_list` 命中时，真正基于候选集合做额外校验
3. `bs_id` 不再参与 Step 2 的 Cell 主键切分
4. 同一 `(operator_code, lac, cell_id)` 不因 `bs_id` 被拆成多个 Step 2 对象
5. 真碰撞逻辑仍保留在 Step 5，不被混入 Step 2

## 7. 当前结论

这份修复文档对应的是 **Step 2 主流程级问题**。

它和 Step 1 补齐问题属于同一类典型错误：

- 开发中为了简化处理
- 过早压缩数据
- 最终导致主流程判断失真

因此该问题应单独修复，不与一般 UI、统计或文案问题混在一起处理。
