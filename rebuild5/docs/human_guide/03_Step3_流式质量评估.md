# Step 3：流式质量评估

> **核心目标**：把 Step 2 计算的基础指标，结合历史累计证据，判断每个 Cell/BS/LAC 当前处于哪个质量等级，批末产出冻结快照，供 Step 5 维护并发布正式库。

---

## 这一步在整体流程中的位置

```mermaid
flowchart LR
    S2["Step 2\nprofile_base\n（Path B 输出）"]
    SNAP["trusted_snapshot_t-1\n上一批冻结快照"]
    COLL["collision_id_list\n（Step 5 产出，只读）"]

    S3["⚙️ Step 3\n流式质量评估"]

    OUT1["trusted_snapshot_t\n本批冻结快照"]
    OUT2["snapshot_diff\n本批变化记录"]

    S5["Step 5\n画像维护 + 发布正式库"]

    S2 --> S3
    SNAP --> S3
    COLL --> S3
    S3 --> OUT1 --> S5
    S3 --> OUT2

    style S3 fill:#fff9c4,stroke:#f9a825
    style OUT1 fill:#c8e6c9,stroke:#388e3c
```

**关键角色**：Step 3 负责"准入判定"，Step 5 才负责"发布正式库"。两者分工明确：Step 3 说谁够格，Step 5 才真正把它发出去。

---

## 为什么要"全量重评估"而不是只看新数据

每批新数据进来，Step 3 必须对**候选域所有已注册 Cell** 重新评估，而不是只看这批新增的：

```mermaid
flowchart TD
    REASON1["单批样本不足以稳定判断\n需要多批累计证据"]
    REASON2["新数据同时改变多个指标\nindependent_obs / distinct_dev_id /\nobserved_span_hours / 空间半径"]
    REASON3["BS / LAC 由 Cell 聚合\n任何 Cell 变化都要重新上卷计算"]
    REASON4["只有全量重评估\n才能保证 snapshot 是完整一致的视图"]

    CONCLUSION["∴ Cell 候选域全量重评估\n+ 已发布对象继承（carry-forward）\n+ 批末统一冻结"]

    REASON1 --> CONCLUSION
    REASON2 --> CONCLUSION
    REASON3 --> CONCLUSION
    REASON4 --> CONCLUSION

    style CONCLUSION fill:#e3f2fd,stroke:#1976d2
```

> **已发布到正式库的对象**不在此重评估范围内，它们以"继承上一版状态"的方式出现在快照中，当前批的维护由 Step 5 负责。

---

## Cell 质量判定流程

### 合并证据 → 重判

```mermaid
flowchart TD
    PB["profile_base\n（本批新增指标）"]
    HIST["历史评估池\n（上一版快照累计证据）"]

    MERGE["按 (operator_code, lac, cell_id) 合并\n累计指标\n\n⚠️ 中位数/分位数必须基于原始明细重算\n不能直接拼上批汇总值"]

    JUDGE["按规则判定 lifecycle_state\n+ 三层资格（is_registered / anchor_eligible / baseline_eligible）"]

    SNAPSHOT["写入本批 Cell Snapshot"]

    PB --> MERGE
    HIST --> MERGE
    MERGE --> JUDGE --> SNAPSHOT
```

### Cell 晋级规则（可配置）

```mermaid
graph TD
    W["⚫ waiting\n证据不足\n观测<3 或 设备<2"]
    O["🟡 observing\n积累中\n有一定证据但不达标"]
    Q["🔵 qualified\n✅ 合格\n观测≥3, 设备≥2\nP90<1500m, 跨度≥24h, 无碰撞"]
    E["🟢 excellent\n⭐ 优秀\n在qualified基础上:\n观测≥8, 设备≥3, P90<500m"]

    W -->|"继续积累"| O
    O -->|"满足条件"| Q
    Q -->|"进一步满足"| E

    NOTE["碰撞阻断：命中 collision_id_list 的 Cell\n不能进入 qualified，即使观测量够"]
    Q -.- NOTE
```

### 三层资格判定（独立于生命周期）

```mermaid
graph LR
    REG["is_registered\n首次出现即获得"]
    ANC["anchor_eligible\nGPS≥10 且 设备≥2\n且 P90<1500m\n且 跨度≥24h\n且 无碰撞阻断"]
    BASE["baseline_eligible\n已是锚点\n且 无防毒化异常\n且 满足成熟条件"]

    REG -->|"门槛提升"| ANC -->|"门槛提升"| BASE

    ANC -->|"Step 4 使用"| U1["作为 donor 补数\n其他报文缺GPS时用它的质心"]
    BASE -->|"Step 5 使用"| U2["参与画像刷新\n影响基线更新"]
```

---

## Cell → BS → LAC 三层级联

质量判断永远自下而上：先判 Cell，才能聚合出 BS，才能聚合出 LAC。

```mermaid
flowchart TD
    CELL["Cell 评估结果\nlifecycle_state + 三层资格"]

    BS_AGG["BS 聚合规则\n- observing：≥1 个下属 Cell 有 GPS 证据\n- qualified：≥1 个 excellent Cell\n  或 ≥3 个 qualified+ Cell"]

    LAC_AGG["LAC 聚合规则\n- observing：≥1 个下属 BS 非 waiting\n- qualified：≥3 个 qualified BS\n  或 qualified BS 占比 ≥ 10%"]

    BS_SNAP["BS Snapshot\n+ 质心 + 离散度 + 分类"]
    LAC_SNAP["LAC Snapshot\n+ 质心 + 面积 + 异常BS占比"]

    CELL --> BS_AGG --> BS_SNAP
    BS_SNAP --> LAC_AGG --> LAC_SNAP

    NOTE["BS 和 LAC 不重新看原始报文\n完全由下层聚合结果派生"]
    BS_AGG -.- NOTE
```

---

## 冻结快照：批末统一产出

```mermaid
sequenceDiagram
    participant 批次处理 as 批次内处理
    participant 快照T-1 as trusted_snapshot_t-1（只读）
    participant 快照T as trusted_snapshot_t（本批产出）

    批次处理->>快照T-1: 读取上一版作为参考基线
    Note over 批次处理: 在内存/临时区域计算\n本批所有 Cell/BS/LAC 状态

    批次处理->>批次处理: ❌ 禁止边算边写本批快照
    批次处理->>批次处理: ❌ 禁止让本批刚晋升的Cell\n参与本批判断

    批次处理->>快照T: 批末一次性冻结写入
    Note over 快照T: 下一批才可读取
```

**快照内容（Cell 层核心字段）**：

| 分组 | 字段 |
|------|------|
| 状态 | `lifecycle_state` / `is_registered` / `anchor_eligible` / `baseline_eligible` |
| 空间 | `center_lon` / `center_lat` / `p50_radius_m` / `p90_radius_m` |
| 信号 | `rsrp_avg` / `rsrq_avg` / `sinr_avg` |
| 统计 | `independent_obs` / `distinct_dev_id` / `active_days` / `observed_span_hours` |

---

## Diff：本批相对上批发生了什么

除快照外，Step 3 还产出一份 `snapshot_diff`，记录变化：

```mermaid
graph LR
    SNAP_T1["快照 t-1"]
    SNAP_T["快照 t"]

    DIFF["snapshot_diff\n\nnew：新增 Cell/BS/LAC\npromoted：状态晋升\ndemoted：状态降级\nremoved：被清理\neligibility_changed：资格变化\ngeometry_changed：质心/半径变化"]

    SNAP_T1 --> DIFF
    SNAP_T --> DIFF

    style DIFF fill:#e8f4f8,stroke:#2196F3
```

Diff 用于 UI 的"流转总览"和"流转快照"页面，让运维人员一眼看到本批系统状态如何变化。

---

## 等待对象的进度展示

对于仍处于 `waiting / observing` 的 Cell，UI 要展示"还差什么才能晋级"：

```mermaid
graph TD
    CELL_OBS["🟡 observing Cell\n当前 Cell 状况"]

    GAP1["观测量：已有 2 个，还需 1 个"]
    GAP2["设备数：已有 1 台，还需 1 台"]
    GAP3["跨度：已有 18h，还需 6h"]
    GAP4["P90：当前 2100m，需降到 1500m 以下"]
    GAP5["碰撞阻断：命中 collision_id_list，\n即使达标也无法晋级"]

    CELL_OBS --> GAP1
    CELL_OBS --> GAP2
    CELL_OBS --> GAP3
    CELL_OBS --> GAP4
    CELL_OBS --> GAP5
```

---

## 流式评估 = 批量计算（已验证）

rebuild4 实验已验证：**逐天累积的流式评估和全量批量计算在数学上等价**。

| 指标 | Day 7 流式 vs 批量 |
|------|-------------------|
| 质心偏差 | 0.00m |
| 生命周期一致率 | 98.9% |
| P90 差异 | 0.00m |

> Day 3 已达可用水平，Day 5 已达生产水平，Day 7 与批量等价。

这是 rebuild5 采用流式主链而非批量重跑的核心依据。

---

## Step 3 明确不做的事

| 不做项 | 负责步骤 | 原因 |
|--------|----------|------|
| 漂移分类（collision/migration/stable） | Step 5 | 需多日质心轨迹计算 |
| 碰撞确认 | Step 5 | 全局键扫描，Step 3 只消费结果 |
| 多质心检测 | Step 5 | 高成本，只做异常子集 |
| 防毒化 | Step 5 | 可信库维护逻辑 |
| 发布 trusted_cell_library | Step 5 | Step 3 只产出冻结快照 |

**Step 3 只回答一件事**：这个对象现在处于哪个质量等级，快照里记录什么。
