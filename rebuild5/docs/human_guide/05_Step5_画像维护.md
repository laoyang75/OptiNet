# Step 5：画像维护

> **核心目标**：对已经进入可信赖库的 Cell/BS/LAC 做持续治理——检测碰撞、防止数据污染、管理退出、更新标签——最终发布新版本的正式可信库，供下一批运行使用。

---

## 这一步在整体流程中的位置

```mermaid
flowchart LR
    S3_OUT["trusted_snapshot_t\n（Step 3 本批冻结快照）"]
    S4_OUT["enriched_records\ngps_anomaly_log\n（Step 4 产出）"]
    PREV_LIB["上一版\ntrusted_cell_library\n（正式库）"]

    S5["⚙️ Step 5\n画像维护"]

    NEW_LIB["✅ 新版 trusted_cell/bs/lac_library\n发布正式库"]
    COLL_LIST["collision_id_list\n供下一批 Step 2/3 使用"]
    LOG["step5_maintenance_log\n维护统计"]

    S3_OUT --> S5
    S4_OUT --> S5
    PREV_LIB --> S5
    S5 --> NEW_LIB
    S5 --> COLL_LIST
    S5 --> LOG

    style S5 fill:#fff9c4,stroke:#f9a825
    style NEW_LIB fill:#c8e6c9,stroke:#388e3c
```

**Step 5 的角色**：Step 3 说"谁通过准入"，Step 5 做"深度治理 + 正式发布"。只有经过 Step 5 维护的正式库，才是系统对外提供服务和补数的依据。

---

## Step 5 的四大职责

```mermaid
mindmap
  root((Step 5\n画像维护))
    全局碰撞检测
      扫描全库的 cell_id 复用情况
      产出 collision_id_list
    异常治理
      汇总 GPS 异常时序
      判定漂移/迁移/碰撞类型
    特征标签完善
      drift_pattern
      is_collision
      is_dynamic
      is_multi_centroid
    退出管理
      滑动窗口保鲜
      dormant → retired
      重新激活语义
```

---

## 5.1 全局碰撞检测

```mermaid
flowchart TD
    LIB["trusted_cell_library\n全量 Cell"]

    SCAN["按 cell_id 聚合\n统计对应多少个\n(operator_code, lac) 组合"]

    JUDGE{"组合数 > 1？"}

    MARK_Y["is_collision_id = true\n记录各组合的质心 / 设备数 / 观测量\n确定主组合（dominant_combo）"]
    MARK_N["is_collision_id = false"]

    OUT["collision_id_list\n发布供下一批\nStep 2/3 使用"]

    LIB --> SCAN --> JUDGE
    JUDGE -->|"是"| MARK_Y --> OUT
    JUDGE -->|"否"| MARK_N

    NOTE["碰撞特征规律：\n远端簇通常只有 1-2 台设备\n且与主簇共享相同 PCI/freq"]
    MARK_Y -.- NOTE

    style OUT fill:#c8e6c9,stroke:#388e3c
```

> 这是 Step 5 中**唯一需要全库扫描**的逻辑。其他分析都只处理异常子集，不做全量计算。

---

## 5.2 Cell 维护流程总览

```mermaid
flowchart TD
    INPUTS["输入：\ntrusted_cell_library\n+ cell_sliding_window（历史观测窗口）\n+ enriched_records（本批新观测，来自 Step 4）\n+ gps_anomaly_log（GPS 异常记录）"]

    W1["窗口更新\n把 enriched_records 纳入滑动窗口"]
    W2["面积异常筛选\n找出 P90 过大或漂移明显的 Cell"]
    W3["多质心分析\n只对异常子集做空间聚类"]
    W4["GPS 异常时序判定\n按日聚合 anomaly_log\n判定 drift / migration / time_cluster"]
    W5["防毒化检测\n试算新画像 vs 上版画像\n是否在容忍范围？"]
    W6["漂移分类 + 动态识别\n产出 drift_pattern / is_dynamic 等标签"]
    W7["退出管理\n检测静默 → dormant → retired"]
    W8["更新 trusted_cell_library"]

    INPUTS --> W1 --> W2 --> W3 --> W4 --> W5 --> W6 --> W7 --> W8

    style W8 fill:#c8e6c9,stroke:#388e3c
```

---

## 滑动窗口：为什么 Cell 不能无限积累历史观测

```mermaid
graph LR
    PROBLEM["问题：\n如果无限累积历史观测\n画像会越来越像「长期平均」\n而不是「当前状态」"]

    SOLUTION["解决：\n每个 Cell 维护一个滑动窗口\n取「最近N天」和「最少M条」中的较大范围\n默认：N=7天，M=50条"]

    EXAMPLE["示例：\n最近7天有300条 → 只保留7天\n最近7天只有12条 → 向前回溯到凑够50条"]

    PROBLEM --> SOLUTION --> EXAMPLE
```

窗口内重算：质心 / P50 / P90 半径 / 漂移轨迹 / 窗口样本量。超出窗口的明细数据归档，不再参与当前画像计算。

---

## GPS 异常时序判定

Step 4 只标记"这条记录有异常（pending）"，Step 5 把多批次的记录串起来做时序判断：

```mermaid
flowchart TD
    LOG["gps_anomaly_log\n按 (cell_id, day) 聚合"]

    METRICS["计算：\nanomaly_days（异常天数）\nmax_consecutive_days（最大连续异常天数）\nanomaly_hour_concentration（异常时段集中度）\nanomaly_distance_trend（异常距离趋势）"]

    C1{"连续多批异常？"}

    DRIFT["🔵 drift\n偶发漂移\n整体质心仍稳定"]
    TIME_CLUS["🟡 time_cluster\n特定时段异常\nGPS 降权处理"]
    C2{"单向持续位移？"}
    MIGR["🔴 migration_suspect\n迁移嫌疑\n不立即改写主质心"]
    C3{"往返跳变？"}
    COLL_CONF["碰撞确认流程"]
    ONGOING["持续观察\n等待更多证据"]

    LOG --> METRICS --> C1
    C1 -->|"否"| DRIFT
    C1 -->|"否，集中时段"| TIME_CLUS
    C1 -->|"是"| C2
    C2 -->|"是"| MIGR
    C2 -->|"否"| C3
    C3 -->|"是"| COLL_CONF
    C3 -->|"否"| ONGOING

    style MIGR fill:#fff3e0,stroke:#f57c00
    style COLL_CONF fill:#ffcccc,stroke:#c62828
```

---

## 防毒化：防止异常数据污染已有画像

```mermaid
flowchart TD
    WIN["Cell 滑动窗口\n加入本批新数据"]

    TRY["试算新画像\n（不发布，只是试算）"]

    COMPARE{"与上版画像对比\n是否在容忍范围？"}

    PUBLISH["✅ 发布更新画像\nbaseline_eligible 保持"]

    BLOCK["🔒 防毒化阻断\nantitoxin_hit = true\nbaseline_eligible = false\n本批画像不生效，保留上版"]

    WIN --> TRY --> COMPARE
    COMPARE -->|"在范围内"| PUBLISH
    COMPARE -->|"超出容忍"| BLOCK

    subgraph 检测维度
        D1["质心漂移 > max_shift_m"]
        D2["P90 膨胀 > max_ratio 倍"]
        D3["设备数突增 > max_ratio 倍"]
        D4["单时段观测占比 > max_ratio"]
    end

    COMPARE -.- 检测维度

    NOTE["⚠️ 防毒化阻断的是「本批画像是否生效」\n不是「承认这个 Cell 是否存在」\n一个 Cell 可以是 qualified 但 baseline_eligible = false"]
    BLOCK -.- NOTE
```

---

## 漂移分类：给 Cell 打上空间行为标签

基于多日质心轨迹，判断 Cell 的空间行为模式：

```mermaid
graph TD
    METRICS["核心指标：\nmax_spread_m（最大跨度）\nnet_drift_m（首尾偏移）\nratio = net_drift_m / max_spread_m"]

    INSUF["insufficient\n参与计算天数 < 2"]
    STABLE["stable\n稳定\nmax_spread < 500m"]
    LARGE["large_coverage\n大覆盖\n500m ≤ max_spread < 2200m"]
    COLL["collision\n碰撞\nmax_spread ≥ 2200m\nratio < 0.3（往返跳变）"]
    MOD["moderate_drift\n中度漂移\nmax_spread ≥ 2200m\n0.3 ≤ ratio < 0.7"]
    MIGR["migration\n迁移\nmax_spread ≥ 2200m\nratio ≥ 0.7（单向移动）"]

    METRICS --> INSUF
    METRICS --> STABLE
    METRICS --> LARGE
    METRICS --> COLL
    METRICS --> MOD
    METRICS --> MIGR

    DYN["is_dynamic = true\n🚌 动态 Cell（移动基站/车载站）\nmax_spread > 1500m\n且 pattern 是 migration 或 large_coverage"]
    MIGR -.- DYN
    LARGE -.- DYN
```

---

## 退出管理

只有**已进入可信库**的 Cell 才走退出链路，从未入库的观察对象直接从评估池清理：

```mermaid
stateDiagram-v2
    qualified_excellent: qualified / excellent
    dormant: dormant 🟠
    retired: retired 🔴
    step2: Step 2 重新积累

    qualified_excellent --> dormant: 连续静默达到阈值\n（silent_days_to_dormant）

    dormant --> retired: dormant 持续到期\n（dormant_days_to_retired）

    dormant --> qualified_excellent: 恢复新数据\n→ 重新活跃

    retired --> step2: 再次出现新数据\n不恢复旧状态\n从头重建证据链
```

---

## BS / LAC 维护：复用 Cell 结果，不重看原始报文

```mermaid
flowchart TD
    CELL_RES["Cell 维护结果\n（质心 / 漂移标签 / 异常标记）"]

    BS_MAIN["BS 维护\n用已维护 Cell 质心重算 BS 质心\n（排除碰撞/动态/防毒化阻断的 Cell）\n检测异常子集的 BS 多质心\n产出 BS 分类标签"]

    LAC_MAIN["LAC 维护\n基于 BS 聚合视图\n监控区域完整性 / 异常BS占比\n面积变化 / 边界稳定性"]

    LIB_BS["trusted_bs_library"]
    LIB_LAC["trusted_lac_library"]

    CELL_RES --> BS_MAIN --> LIB_BS
    LIB_BS --> LAC_MAIN --> LIB_LAC

    style LIB_BS fill:#c8e6c9,stroke:#388e3c
    style LIB_LAC fill:#c8e6c9,stroke:#388e3c
```

**BS 分类标签**（`classification` 字段）：

| 标签 | 含义 |
|------|------|
| `normal_spread` | 正常 |
| `large_spread` | 下属 Cell 离散过大（> 2500m） |
| `collision_bs` | 受碰撞 Cell 污染 |
| `dynamic_bs` | 含动态 Cell |
| `multi_centroid` | 存在多个稳定质心簇 |

---

## Step 5 发布后，下一批才能读取

```mermaid
sequenceDiagram
    participant S5 as Step 5（本批）
    participant LIB as trusted_cell_library（新版）
    participant COLL as collision_id_list（新版）
    participant NEXT as 下一批 Step 2/3/4

    S5->>LIB: 批末发布新版正式库
    S5->>COLL: 批末发布新版碰撞列表

    Note over LIB,COLL: 本批 Step 2/3/4 不能读取\n正在维护的中间结果

    NEXT->>LIB: ✅ 下一批才允许读取
    NEXT->>COLL: ✅ 下一批才允许读取
```

---

## Step 5 只处理"已入库对象"

```mermaid
graph LR
    INLIB["已进入 trusted_cell_library\n的 Cell\n→ Step 5 深度维护"]
    NOTINLIB["尚在 waiting / observing\n从未入库的 Cell\n→ Step 3 继续积累，Step 5 不管"]

    NOTE["退出链路（dormant/retired）\n只作用于曾经入库的对象"]
    INLIB -.- NOTE
```

---

## 维护统计（step5_maintenance_log）

每次运行记录：
- 碰撞检测：发现了多少碰撞 `cell_id`，新增了多少
- 多质心：触发检测多少个，确认多质心多少个
- GPS 异常：漂移/时段集中/迁移嫌疑各多少条
- 防毒化：命中多少个，按维度分布
- 退出：新进入 dormant 多少，新 retired 多少，重新激活多少
- 数据窗口：平均窗口观测量，归档了多少条明细
