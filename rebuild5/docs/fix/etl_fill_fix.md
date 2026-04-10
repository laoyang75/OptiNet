# ETL 同 Cell 补齐修复说明

> 适用范围：`rebuild5` Step 1 ETL 补齐阶段  
> 修复对象：`rebuild5/backend/app/etl/fill.py` 为主，必要时联动 `queries.py`、相关文档和统计输出

## 1. 问题定位

当前 ETL 补齐属于 **Step 1 结构性补齐**，不是 Step 4 的知识补数。

补齐边界应明确为：

- 只发生在同一次采集上下文内
- 只允许同 `record_id + cell_id` 的记录互相补齐
- 不跨 `record_id`
- 不读取可信库

当前实现的主要问题不是“要不要补齐”，而是**补齐实现粒度不对**：

- 目前更像“先选 1 条 donor 行，再拿 donor 上的字段统一去补”
- 但业务上需要的是“同 `record_id + cell_id` 的信息池按字段拉通补齐”

## 2. 已确认业务规则

### 2.1 基本原则

- `cell_infos` 是一次采集，属于即时信息
- `ss1` 是延后持续执行，会独立采集 GPS 和网络信息
- 在同一个小范围采集上下文内，`cell_id` 不会重复指向不同对象
- 因此在同 `record_id + cell_id` 范围内，可以做结构性补齐

### 2.2 补齐主键

补齐唯一范围固定为：

```text
record_id + cell_id
```

说明：

- 不能只按全局 `cell_id`
- 不能跨报文补
- 不能进入知识库逻辑

### 2.3 稳定字段补齐规则

以下字段属于稳定网络字段，只要同 `record_id + cell_id` 即可拉通补齐，不受 60 秒限制：

- `lac`
- `operator_code`
- `tech_raw`
- `tech_norm`
- 以及同类稳定网络字段（后续实现时按同口径收敛）

### 2.4 时效字段补齐规则

以下字段属于时效字段：

- GPS：`lon_raw` / `lat_raw`
- 信号：`rsrp` / `rsrq` / `sinr`
- Wi-Fi：`wifi_name` / `wifi_mac`

规则如下：

- 如果 donor 来自 `cell_infos`：可直接参与补齐
- 如果 donor 来自 `ss1`：必须满足 `60 秒` 的时间限制

也就是说：

- `cell_infos -> 同 cell_id` 的时效字段补齐：允许
- `ss1 -> 同 cell_id` 的时效字段补齐：仅在 `<= 60s` 时允许

## 3. 当前实现存在的问题

### 3.1 单 donor 行模型不符合业务语义

当前实现先按 `record_id + cell_id` 选出一条 donor，再统一拿 donor 上的字段补齐。

问题：

- 同一组里不同字段可能分散在不同记录上
- 只选一条 donor，会漏掉本来可补的信息

### 3.2 时间限制作用粒度过粗

当前实现更像“整行 donor 是否允许 full fill”。

问题：

- 业务要求是**字段类别级别**的限制，不是 donor 整行级限制
- `lac / operator / tech` 不应受 60 秒限制
- `gps / signal / wifi` 才应在 donor 为 `ss1` 时受 60 秒限制

### 3.3 补齐字段覆盖还不完整

当前补齐重点仍集中在：

- `operator`
- `lac`
- `gps`
- `rsrp / rsrq / sinr`
- `wifi`

但根据已确认规则，`tech_raw / tech_norm` 等稳定网络字段也应纳入同 Cell 补齐逻辑。

## 4. 目标修复方案

## 4.1 修复目标

把补齐从：

```text
单 donor 行补齐
```

改成：

```text
同 record_id + cell_id 的字段级信息池补齐
```

### 4.2 推荐实现结构

按 `record_id + cell_id` 构建三类补齐池：

#### A. 稳定字段池

用于：

- `lac`
- `operator_code`
- `tech_raw`
- `tech_norm`

规则：

- 同组任意非空值都可作为候选
- 不受 60 秒限制

#### B. 即时 `cell_infos` 字段池

用于：

- GPS
- 信号
- Wi-Fi

规则：

- donor 来自 `cell_infos`
- 可直接参与补齐

#### C. 即时 `ss1` 字段池

用于：

- GPS
- 信号
- Wi-Fi

规则：

- donor 来自 `ss1`
- 仅在时间差 `<= 60s` 时允许参与补齐

### 4.3 字段级补齐顺序

推荐优先级：

```text
原值
-> cell_infos donor
-> ss1 donor（仅限 <= 60s）
```

稳定字段推荐优先级：

```text
原值
-> 同组稳定字段池
```

### 4.4 输出要求

修复后仍应保持以下原则：

- 原始字段保留，不覆盖真相
- 补齐结果写入 `*_filled`
- 补齐来源写入 `*_fill_source`
- 不跨报文补齐
- 不进入知识补数逻辑

## 5. 需要联动检查的内容

修复补齐逻辑时，同时检查：

- 是否需要新增 `tech_raw_filled` / `tech_norm_filled` 等字段
- `operator_cn`、`bs_id`、`sector_id` 是否需要基于 filled 结果重算
- `queries.py` 中的覆盖率统计和来源分布是否要同步调整
- 文档中 Step 1 补齐说明是否要和代码口径重新对齐

## 6. 验收标准

满足以下条件才算修复完成：

1. 同 `record_id + cell_id` 的稳定网络字段可完整拉通补齐
2. `ss1` 参与 GPS / 信号 / Wi-Fi 补齐时，严格受 `60s` 限制
3. `cell_infos` 参与即时字段补齐时，不额外受 `60s` 限制
4. 补齐逻辑为字段级，而不是单 donor 行级
5. 不跨 `record_id`
6. 不污染 Step 4 知识补数边界

## 7. 当前结论

该问题属于 **Step 1 主流程基础问题**，优先级高于一般 UI 对齐问题。

它不是是否“要补齐”的争议，而是：

- 补齐边界已经确认
- 当前实现方式还没有完整落到这套边界上

因此本修复文档用于后续单独实施 ETL 补齐重构。
