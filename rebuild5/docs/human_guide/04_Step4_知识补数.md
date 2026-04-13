# Step 4：知识补数

> **核心目标**：用上一轮已验证的可信 Cell 库，为命中可信库的新报文补充缺失字段（GPS / 信号 / 运营商），同时对自带 GPS 的记录做初步异常标记。

---

## 这一步在整体流程中的位置

```mermaid
flowchart LR
    S2_A["Step 2\nPath A 记录\n（path_a_records）"]
    LIB["trusted_cell_library\n上一轮已发布可信库\n仅取 anchor_eligible=true 子集"]

    S4["⚙️ Step 4\n知识补数"]

    ER["enriched_records\n治理后事实候选层\n→ Step 5 消费"]
    AL["gps_anomaly_log\nGPS 异常初始标记\n→ Step 5 时序判定"]

    S2_A --> S4
    LIB --> S4
    S4 --> ER
    S4 --> AL

    style S4 fill:#fff9c4,stroke:#f9a825
    style ER fill:#c8e6c9,stroke:#388e3c
```

**Step 4 只处理 Path A 记录**（已命中可信库的那批数据）。Path B 的数据去了 Step 3，不经过 Step 4。GPS 异常初筛只对原始且有效的 GPS 证据做比对，不使用 Step 4 补出来的 GPS 反向自比对。

---

## 补数源确认责任的归属

Step 4 是一个**简单补数步骤**，不应自己重新承担复杂匹配责任。正确分工：

| 步骤 | 责任 |
|------|------|
| **Step 2** | 判断当前记录命中哪个可信 Cell，确认所引用的可信库版本 |
| **Step 4** | 直接使用 Step 2 已确认的补数源 Cell，补齐缺失字段，并基于同一补数源做 GPS 异常初筛 |

因此 `path_a_records` 应显式携带补数源标识（source cell 主键、source batch/version），Step 4 不重新"猜"命中了哪个可信 Cell。

---

## 知识补数的本质：用历史可信知识填补当前缺口

```mermaid
flowchart TD
    REPORT["新到的一条报文\n命中了可信 Cell A"]

    subgraph MISSING["报文里缺少什么"]
        M1["GPS 为空\n（这条手机报文没带位置）"]
        M2["RSRP 为空\n（信号强度字段缺失）"]
        M3["运营商 为空\n（归属字段缺失）"]
    end

    subgraph DONOR["可信 Cell A 知道什么"]
        D1["center_lon / center_lat\n历史积累的精确质心位置"]
        D2["rsrp_avg\n历史平均信号强度"]
        D3["operator_code\n归属运营商"]
    end

    OUT["enriched_records\n补数后完整记录\n（原始字段保留不变）"]

    REPORT --> MISSING
    DONOR -->|"补入"| OUT
    MISSING --> OUT

    NOTE["⚠️ 原始字段（lon_raw, rsrp 等）\n永远不被覆盖！\n补数值写入 *_filled 列"]
    OUT -.- NOTE
```

---

## 谁可以作为 donor？

不是可信库里所有 Cell 都可以用来补数，需要满足资格：

```mermaid
graph TD
    ALL["trusted_cell_library\n所有可信 Cell"]

    FILTER["过滤条件：\nanchor_eligible = true\n（是否具备锚点资格）"]

    DONOR["✅ 可用 donor Cell\n来源可靠，历史积累的空间质量达标"]

    NOT_DONOR["❌ 不可用\n（虽在可信库但锚点资格不足）"]

    ALL --> FILTER
    FILTER -->|"通过"| DONOR
    FILTER -->|"未通过"| NOT_DONOR

    QUAL["donor 质量分级：\nexcellent → 高置信度补数\nqualified → 中置信度补数"]
    DONOR --> QUAL
```

---

## 各字段补数矩阵

| 字段 | 补数条件 | 来源 | 来源标记 |
|------|----------|------|----------|
| GPS | `lon_filled / lat_filled` 仍为空 | `center_lon / center_lat` | `gps_fill_source = 'trusted_cell'` |
| RSRP | `rsrp_filled` 为空 | `rsrp_avg` | `rsrp_fill_source = 'trusted_cell'` |
| RSRQ | `rsrq_filled` 为空 | `rsrq_avg` | `rsrq_fill_source = 'trusted_cell'` |
| SINR | `sinr_filled` 为空 | `sinr_avg` | `sinr_fill_source = 'trusted_cell'` |
| 气压 | `pressure_filled` 为空，且 donor 有 `pressure_avg` | `pressure_avg` | `pressure_fill_source = 'trusted_cell'`（置信度固定 `low`） |
| 运营商 | `operator_filled` 为空 | `operator_code` | `operator_fill_source = 'trusted_cell'` |
| LAC | `lac_filled` 为空 | `lac` | `lac_fill_source = 'trusted_cell'` |

**注意**：
- Step 4 只补 Step 1 之后仍为空的字段，不覆盖 Step 1 已有值
- 信号三字段（RSRP/RSRQ/SINR）**独立补，互不依赖**
- 气压补数固定置信度 `low`（气压受天气/高度影响大）

**绝对不补的字段**：`cell_id`（主键）、`dev_id/ip/brand`（设备元数据只能来自报文本身）、时间字段、射频参数（`pci/freq_channel`，变化太快）、`wifi_name/wifi_mac`（非 Cell 稳定属性）

---

## GPS 异常初筛

Step 4 不只补空值，还对"自带 GPS"的记录做一次距离核验：

```mermaid
flowchart TD
    REC["Path A 记录\n自带了 GPS 数据"]

    C1{"donor 是碰撞 cell_id？\n（is_collision_id=true）"}
    SKIP["跳过异常检测\n（Step 2 已有防护）"]

    C2{"记录有原始 GPS？\n（lon_raw / lat_raw 非空）"}
    SKIP2["跳过\n（无原生GPS可比较）"]

    C3{"donor 有可信质心？\n（center_lon / center_lat 非空）"}
    SKIP3["跳过"]

    CALC["计算偏差距离\ndx = (lon_raw - center_lon) × 85300m/°\ndy = (lat_raw - center_lat) × 111000m/°\ndist = √(dx² + dy²)"]

    JUDGE{"dist > 2200m？\n（可配置阈值）"}

    MARK_Y["gps_anomaly = true\ngps_anomaly_type = 'pending'\n→ 写入 gps_anomaly_log"]
    MARK_N["gps_anomaly = false\n正常"]

    REC --> C1
    C1 -->|"是"| SKIP
    C1 -->|"否"| C2
    C2 -->|"否"| SKIP2
    C2 -->|"是"| C3
    C3 -->|"否"| SKIP3
    C3 -->|"是"| CALC --> JUDGE
    JUDGE -->|"是，偏离过大"| MARK_Y
    JUDGE -->|"否，正常范围"| MARK_N

    style MARK_Y fill:#fff3e0,stroke:#f57c00
```

> **为什么只标记 `pending`，不给最终分类**？因为单条记录的偏差可能是偶发噪声，也可能是迁移的开始。需要多批次时间序列累积后，才能在 Step 5 中判断是漂移/迁移/碰撞。

---

## 补数来源标记体系

每个被补的字段，都要留下来源痕迹，支持完整审计追溯：

| 来源值 | 含义 |
|--------|------|
| `raw_gps` | 报文原生 GPS |
| `ss1_own` | ss1 字段自带 GPS |
| `same_cell` | Step 1 同报文对齐 |
| `trusted_cell` | Step 4 知识补数 ← 本步新增 |
| `none` | 仍未补成功 |

> UI 展示时可把 `raw_gps / ss1_own / same_cell` 归并显示为 `original`，便于和 `trusted_cell` 对比。

**donor 审计字段**（enriched_records 额外携带）：

| 字段 | 说明 |
|------|------|
| `trusted_donor_cell_id` | donor Cell 标识 |
| `trusted_donor_position_grade` | donor 画像等级（补数置信度参考） |
| `trusted_donor_anchor_eligible` | donor 是否具备锚点资格 |
| `trusted_donor_baseline_eligible` | donor 是否具备基线资格 |

---

## 补数不回灌本批主链

```mermaid
flowchart LR
    S4_OUT["enriched_records\n（Step 4 产出）"]

    S5["Step 5\n画像维护\n（消费 enriched_records\n作为已发布对象当前批有效观测）"]

    S2_NEXT["下一批 Step 2\n（才允许把这些补数记录\n重新纳入主链）"]

    CUR_S2["❌ 本批 Step 2 / Step 3\n不能读取本批 Step 4 的输出\n禁止回灌"]

    S4_OUT --> S5
    S4_OUT --> S2_NEXT
    S4_OUT -. "禁止" .-> CUR_S2

    style CUR_S2 fill:#ffcccc,stroke:#c62828
    style S2_NEXT fill:#c8e6c9,stroke:#388e3c
```

---

## 与 Step 1 字段对齐的区别（常被混淆）

| 对比维度 | Step 1 字段对齐 | Step 4 知识补数 |
|----------|----------------|----------------|
| **依据** | 同一条报文内的其他字段 | 历史积累的可信 Cell 画像 |
| **范围** | 只能同 `record_id` | 任何命中可信库的记录 |
| **可靠性** | 中（报文本身质量） | 高（多批次验证的可信对象） |
| **发生时机** | 数据入库时 | 可信库建立后的持续运行 |
| **是否受冻结约束** | 否 | 是（只读上一轮发布版本） |

---

## Step 4 明确不做的事

| 不做项 | 负责步骤 |
|--------|----------|
| GPS 异常最终分类（drift/migration/collision） | Step 5 时序判定 |
| 对象生命周期判定（waiting/qualified 等） | Step 3 |
| 防毒化、基线刷新 | Step 5 |
| 修改原始字段真相（lon_raw 等） | 永远不允许 |
| 重新判断命中了哪个可信 Cell | Step 2 已负责 |

**Step 4 只回答两件事**：①这条命中记录缺什么、能补什么；②它自带的 GPS 是否明显偏离可信质心。
