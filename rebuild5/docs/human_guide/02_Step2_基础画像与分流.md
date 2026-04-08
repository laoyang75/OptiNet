# Step 2：基础画像与分流

> **核心目标**：对 Step 1 产出的 `etl_cleaned` 做命中判断，将数据分成三条路径分别处理，同时为未命中但有 GPS 的记录计算基础画像指标。

---

## 这一步在整体流程中的位置

```mermaid
flowchart LR
    S1["Step 1\netl_cleaned"]
    S2["⚙️ Step 2\n基础画像 + 分流"]
    S3["Step 3\n质量评估"]
    S4["Step 4\n知识补数"]
    DISCARD["🗑️ 丢弃"]

    S1 --> S2
    S2 -->|"Path B"| S3
    S2 -->|"Path A"| S4
    S2 -->|"Path C"| DISCARD

    style S2 fill:#fff9c4,stroke:#f9a825
```

**从这一步开始进入「数据版本上下文」**：所有处理和产出都绑定到当前数据集（如 `sample_6lac`）。Step 1 是通用 ETL，Step 2 开始才和具体数据集挂钩。

---

## 三路分流：一条记录进来，走哪条路？

```mermaid
flowchart TD
    IN["etl_cleaned 中的一条记录"]

    CHECK1{"这条记录的 cell_id\n是否命中上一轮\n已发布可信库？"}

    CHECK2{"是否有有效 GPS？\n（lon_filled / lat_filled 非空）"}

    PATHA["✅ Path A\n→ Step 4 知识补数\n\n已是可信 Cell 的新数据\n不需要重新评估，直接补数后更新"]

    PATHB["🔵 Path B\n→ Step 3 质量评估\n\n新 Cell 或未入库的 Cell\n计算基础指标，等待积累晋级"]

    PATHC["❌ Path C\n→ 丢弃\n\n无 GPS 无法定位\n无法建立可信空间对象"]

    IN --> CHECK1
    CHECK1 -->|"命中"| PATHA
    CHECK1 -->|"未命中"| CHECK2
    CHECK2 -->|"有 GPS"| PATHB
    CHECK2 -->|"无 GPS"| PATHC

    style PATHA fill:#c8e6c9,stroke:#388e3c
    style PATHB fill:#cce5ff,stroke:#1976d2
    style PATHC fill:#ffcccc,stroke:#c62828
```

---

## 碰撞 cell_id 的特殊防护

当一个 `cell_id` 在历史上被多个不同 `(operator_code, lac)` 组合使用（碰撞），分流规则需要更严格的匹配：

```mermaid
flowchart TD
    HIT["命中上一轮可信库"]

    COLL{"该 cell_id 是否\n在碰撞列表中？\n（collision_id_list）"}

    NORMAL["正常 Path A 处理"]

    GPS_CHECK{"记录的 GPS 位置\n是否和对应组合\n的质心接近？\n（距离 < 2200m）"}

    ALLOW["允许进入 Path A"]
    DISCARD["丢弃\n（视为误命中）"]

    HIT --> COLL
    COLL -->|"否（普通 cell_id）"| NORMAL
    COLL -->|"是（碰撞 cell_id）"| GPS_CHECK
    GPS_CHECK -->|"接近"| ALLOW
    GPS_CHECK -->|"偏离"| DISCARD

    style DISCARD fill:#ffcccc,stroke:#c62828
    style ALLOW fill:#c8e6c9,stroke:#388e3c
```

> ⚠️ **碰撞列表（collision_id_list）** 由 Step 5 产出，在上一批结束时冻结，本批才能读取使用。

---

## Path B：基础指标计算

没有命中可信库但有 GPS 的记录，需要计算一组基础指标，作为 Step 3 的输入：

```mermaid
flowchart LR
    PB["Path B 记录集"]

    subgraph CALC["基础指标计算"]
        C1["独立观测点去重\n按 (cell_id, 分钟) 去重\n→ independent_obs"]
        C2["中位数质心\nPERCENTILE_CONT(0.5)\n→ center_lon / center_lat"]
        C3["空间半径\nP50 / P90 半径\n→ p50_radius_m / p90_radius_m"]
        C4["基础统计\n设备数 / 信号均值 /\n活跃天数 / 观测跨度"]
    end

    OUT["profile_base\n→ Step 3 输入"]

    PB --> CALC --> OUT

    style OUT fill:#cce5ff,stroke:#1976d2
```

**去重的意义**：同一分钟同一 Cell 的多条记录，只算一个独立观测点。这样可以防止设备密集上报导致数量虚高。

---

## 分流统计（帮助理解数据质量）

Step 2 记录以下统计，用于监控和调试：

```mermaid
pie title "典型分流比例（示意）"
    "Path A：命中可信库" : 60
    "Path B：未命中有GPS" : 35
    "Path C：丢弃（无GPS）" : 5
```

| 统计项 | 说明 |
|--------|------|
| 总数据量 | `etl_cleaned` 输入记录数 |
| Path A 命中率 | 系统成熟度的体现，越高说明可信库越完整 |
| Path B 有GPS率 | 新 Cell 数据质量 |
| Path C 丢弃率 | 无法使用的数据比例 |

---

## 这一步明确不做的事

| 不做项 | 原因 |
|--------|------|
| 漂移分析 | 需要多日历史轨迹，属于 Step 5 |
| 多质心检测 | 高成本分析，属于 Step 5 异常子集处理 |
| 全局碰撞检测 | 属于 Step 5.1，产出 collision_id_list |
| 分类标签（collision/migration 等） | 属于 Step 5 深度维护标签 |

Step 2 只回答一件事：**这条数据属于哪条路径？**

---

## 输入 / 输出总结

```mermaid
flowchart LR
    subgraph 输入
        I1["etl_cleaned\n（来自 Step 1）"]
        I2["trusted_cell_library\n上一轮已发布可信库\n（版本=trusted_snapshot_t-1）"]
        I3["collision_id_list\n（来自 Step 5，只读）"]
    end

    S2["Step 2"]

    subgraph 输出
        O1["Path A 记录\n→ Step 4"]
        O2["profile_base\n含基础指标\n→ Step 3"]
        O3["Path C\n→ 丢弃"]
    end

    输入 --> S2 --> 输出
```
