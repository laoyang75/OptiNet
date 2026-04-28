# Step 2：基础画像与分流

> **核心目标**：对 Step 1 产出的 `etl_cleaned` 做可信库命中判断，将数据分成三条路径分别处理，同时为未命中但有 GPS 的记录计算基础画像指标（`profile_base`）。

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
    S2 -->|"Path B\n→ profile_base"| S3
    S2 -->|"Path A\n→ path_a_records"| S4
    S2 -->|"Path C"| DISCARD

    style S2 fill:#fff9c4,stroke:#f9a825
```

**从这一步开始进入「数据版本上下文」**：所有处理和产出都绑定到当前数据集（如 `sample_6lac`）。Step 1 是通用 ETL，Step 2 开始才和具体数据集挂钩。

---

## 三路分流：一条记录进来，走哪条路？

```mermaid
flowchart TD
    IN["etl_cleaned 中的一条记录"]

    CHECK1{"这条记录的 cell_id\n是否命中上一轮\n已发布可信库？\n（trusted_cell_library）"}

    CHECK2{"是否有可用于\n空间计算的有效GPS\n（原始有效 GPS）"}

    PATHA["✅ Path A\n→ Step 4 知识补数\n→ 输出 path_a_records\n\n已是可信 Cell 的新数据\n不需要重新评估，直接补数后更新"]

    PATHB["🔵 Path B\n→ Step 3 质量评估\n→ 聚合为 profile_base\n\n新 Cell 或未入库的 Cell\n计算基础指标，等待积累晋级"]

    PATHC["❌ Path C\n→ 丢弃\n\n无可用GPS无法定位\n无法建立可信空间对象"]

    IN --> CHECK1
    CHECK1 -->|"命中"| PATHA
    CHECK1 -->|"未命中"| CHECK2
    CHECK2 -->|"有可用GPS"| PATHB
    CHECK2 -->|"无可用GPS"| PATHC

    style PATHA fill:#c8e6c9,stroke:#388e3c
    style PATHB fill:#cce5ff,stroke:#1976d2
    style PATHC fill:#ffcccc,stroke:#c62828
```

> 说明：Path B 的"有 GPS"指该 Cell 在本批次未命中记录中存在可用于空间统计的有效 GPS 观测；质心和半径计算只使用原始有效 GPS，不把 Step 1 的结构性补齐 GPS 当作真实定位证据。

---

## Path A 命中：三层匹配策略

命中上一轮可信库并不是简单的 cell_id 相等。Step 2 采用三层逐级放宽的匹配策略：

```mermaid
flowchart TD
    START["查上一轮 trusted_cell_library\n中是否存在同 cell_id 候选"]

    L1{"Layer 1: 精确匹配\ncell_id + operator_code + lac 全部非空且匹配"}
    L2{"Layer 2: 宽松匹配\ncell_id 匹配，operator_code / lac 为空\n且该 cell_id 不在 collision_id_list 中"}
    L3{"Layer 3: 碰撞回退\ncell_id 在碰撞列表中\n且 operator_code 为空\n但有 GPS 且距离可信质心 < 2200m"}
    DROP["❌ 丢弃\n（碰撞误命中，GPS 不接近）"]
    PATHB_C["继续走未命中分流\n→ Path B / C"]
    PATHA["✅ Path A"]

    START --> L1
    L1 -->|"匹配"| PATHA
    L1 -->|"不匹配"| L2
    L2 -->|"匹配（cell_id 全局唯一）"| PATHA
    L2 -->|"不匹配"| L3
    L3 -->|"GPS 接近 < 2200m"| PATHA
    L3 -->|"GPS 不接近 ≥ 2200m"| DROP
    L3 -->|"无可比 GPS"| PATHB_C
```

**Layer 2 的核心价值**：拯救大量缺运营商/LAC 信息的有效记录。对于 cell_id 全局唯一的 Cell，即使原始数据缺运营商也能安全匹配。

> ⚠️ **碰撞列表（collision_id_list）** 由 Step 5.1 产出，在上一批结束时冻结，本批才能读取使用。

---

## Path B：基础指标计算

没有命中可信库但有 GPS 的记录，聚合为 Cell 级的基础画像（`profile_base`），作为 Step 3 的输入：

```mermaid
flowchart LR
    PB["Path B 记录集"]

    subgraph CALC["基础指标计算"]
        C1["独立观测点去重\n按 (cell_id, 分钟) 去重\n→ independent_obs"]
        C2["中位数质心\nPERCENTILE_CONT(0.5)\n→ center_lon / center_lat"]
        C3["空间半径\nP50 / P90 半径\n→ p50_radius_m / p90_radius_m"]
        C4["基础统计\n设备数 / 信号均值 /\n活跃天数 / 观测跨度"]
    end

    OUT["profile_base\n（Cell 粒度聚合结果）\n→ Step 3 输入"]

    PB --> CALC --> OUT

    style OUT fill:#cce5ff,stroke:#1976d2
```

**去重的意义**：同一分钟同一 Cell 的多条记录，只算一个独立观测点。这样可以防止设备密集上报导致数量虚高。

**质心算法**：固定采用中位数（`PERCENTILE_CONT(0.5)`）而非均值，因为中位数天然抗碰撞和抗噪声。

---

## 分流统计（帮助理解数据质量）

Step 2 输出 `step2_run_stats`，记录以下统计：

| 统计项 | 说明 |
|--------|------|
| `input_record_count` | Step 2 输入总记录数 |
| `path_a_record_count` / `path_a_ratio` | Path A 命中数与占比 |
| `path_b_record_count` / `path_b_cell_count` / `path_b_ratio` | Path B 记录数、Cell 数与占比 |
| `path_c_drop_count` / `path_c_drop_ratio` | Path C 丢弃数与占比 |
| `collision_candidate_count` | 遇到的已标记碰撞 cell_id 记录数 |
| `collision_path_a_match_count` | 碰撞防护后成功进入 Path A 的记录数 |
| `collision_pending_count` | 缺少可比 GPS 未判定的记录数 |
| `collision_drop_count` | 因 GPS 不接近被丢弃的记录数 |

---

## 这一步明确不做的事

| 不做项 | 原因 |
|--------|------|
| 漂移分析 | 需要多日历史轨迹，属于 Step 5 |
| 多质心检测 | 高成本分析，属于 Step 5 异常子集处理 |
| 全局碰撞检测 | 属于 Step 5.1，产出 collision_id_list |
| 分类标签（collision/migration 等） | 属于 Step 5 深度维护标签 |
| 置信度分级、规模分级 | Step 2 只保留 Step 3 必需的基础统计子集 |

Step 2 只回答一件事：**这条数据属于哪条路径？**

---

## 输入 / 输出总结

```mermaid
flowchart LR
    subgraph 输入
        I1["etl_cleaned\n（来自 Step 1）"]
        I2["trusted_cell_library\n上一轮已发布可信库\n（版本=trusted_snapshot_t-1）"]
        I3["collision_id_list\n（来自 Step 5.1，只读）"]
    end

    S2["Step 2"]

    subgraph 输出
        O1["path_a_records\n命中可信库的记录\n→ Step 4"]
        O2["profile_base\n含基础指标（Cell粒度）\n→ Step 3"]
        O3["Path C\n→ 丢弃"]
        O4["step2_run_stats\n→ 分流统计"]
    end

    输入 --> S2 --> 输出
```
