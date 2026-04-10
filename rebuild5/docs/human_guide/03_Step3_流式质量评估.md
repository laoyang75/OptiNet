# Step 3：流式质量评估

> **核心目标**：接收 Step 2 输出的 `profile_base`，把当前批次新增的 Cell 证据与历史状态合并，对**候选域**（尚未进入正式发布库的对象）做全量重评估，批末产出冻结快照，供 Step 5 维护并发布正式库。

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

**关键角色分工**：
- Step 3 负责**候选域准入判定**，批末产出冻结快照
- Step 5 才负责**发布正式库**

两者分工明确：Step 3 说谁够格进可信链路，Step 5 才真正把它发出去。

---

## 候选域 vs 已发布域：两个不同的范围

```mermaid
graph LR
    subgraph 候选域["🔵 候选域（Step 3 的处理对象）"]
        C1["尚未进入正式库的对象\n→ 全量重评估\n按规则判定 lifecycle_state"]
    end

    subgraph 已发布域["🟢 已发布域（Step 5 的处理对象）"]
        C2["上一版已发布到\ntrusted_cell_library 的对象\n→ 在快照中 carry-forward\n当前批维护由 Step 5 负责"]
    end
```

> **为什么这样分**：Path A 命中正式库的记录不进入 Step 3，因此 Step 3 天然不具备对已发布对象做当前批维护的输入条件。

---

## 为什么要"候选域全量重评估"而不是只看新数据

```mermaid
flowchart TD
    REASON1["单批样本不足以稳定判断\n需要多批累计证据"]
    REASON2["新数据同时改变多个指标\nindependent_obs / distinct_dev_id /\nobserved_span_hours / 空间半径"]
    REASON3["BS / LAC 由 Cell 聚合\n任何 Cell 变化都要重新上卷计算"]
    REASON4["只有全量重评估\n才能保证 snapshot 是完整一致的视图"]

    CONCLUSION["∴ 候选域 Cell 全量重评估\n+ 已发布对象继承（carry-forward）\n+ 批末统一冻结"]

    REASON1 --> CONCLUSION
    REASON2 --> CONCLUSION
    REASON3 --> CONCLUSION
    REASON4 --> CONCLUSION

    style CONCLUSION fill:#e3f2fd,stroke:#1976d2
```

> ⚠️ **注意**：中位数质心、P90 半径、distinct_dev_id 等指标不支持增量拼接，必须基于保留的分钟级原始证据重算，不能直接把上批汇总值和本批增量数值相加。

---

## 入库前置过滤（可配置）

Step 3 在评估前先做过滤，控制哪些对象进入评估池：

| 过滤类型 | 默认配置 | 说明 |
|----------|----------|------|
| 制式过滤 | 只处理 `4G / 5G` | `2G / 3G` 可配置为放行 |
| 地区过滤 | 按当前数据集 LAC 白名单 | 开发阶段可只处理样本 LAC |
| GPS 有效性 | 无有效 GPS 不参与空间评估 | 无 GPS 不能计算质心和半径 |

---

## Cell 质量判定流程

### 合并证据 → 重判

```mermaid
flowchart TD
    PB["profile_base\n（本批新增指标）"]
    HIST["历史评估池\n（上一版快照候选对象累计证据）"]

    MERGE["按 (operator_code, lac, cell_id) 合并\n累计指标\n\n⚠️ 中位数/分位数必须基于原始明细重算\n不能直接拼上批汇总值"]

    JUDGE["按规则判定 lifecycle_state\n+ 三层资格（is_registered / anchor_eligible / baseline_eligible）"]

    SNAPSHOT["写入本批 Cell Snapshot"]

    PB --> MERGE
    HIST --> MERGE
    MERGE --> JUDGE --> SNAPSHOT
```

### Cell 晋级规则（可配置阈值来自 profile_params.yaml）

```mermaid
graph TD
    W["⚫ waiting\n证据不足\n独立观测<3 或 设备<2"]
    O["🟡 observing\n积累中\n有一定证据但不达标"]
    Q["🔵 qualified\n✅ 合格\n观测≥3, 设备≥2\nP90<1500m, 跨度≥24h, 无碰撞阻断"]
    E["🟢 excellent\n⭐ 优秀\n在qualified基础上:\n观测≥8, 设备≥3, P90<500m"]

    W -->|"继续积累"| O
    O -->|"满足条件"| Q
    Q -->|"进一步满足"| E

    NOTE["碰撞阻断：命中 collision_id_list 的 Cell\n不能进入 qualified，即使观测量够"]
    Q -.- NOTE
```

### 三层资格判定（独立于生命周期）

| 资格 | 判定规则 | 阈值来源 |
|------|----------|----------|
| `is_registered` | 首次出现可解析的 `(operator_code, lac, cell_id)` 即注册 | 结构规则 |
| `anchor_eligible` | `gps_valid_count ≥ 10` 且 `distinct_dev_id ≥ 2` 且 `p90_radius_m < 1500` 且 `observed_span_hours ≥ 24` 且无碰撞阻断 | `anchorable.*` |
| `baseline_eligible` | 已 `anchor_eligible=true`，且无防毒化异常，且满足成熟条件 | 逻辑冻结，成熟阈值在 Step 5 执行 |

**关键区分**：
- `is_registered=true` 只表示对象建档成功
- `anchor_eligible=true` 才表示它能被 Step 4 用作可信锚点
- `baseline_eligible=true` 表示它能参与 Step 5 画像刷新

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

## 定期清理（防止评估池无限膨胀）

| 清理场景 | 对象 | 处理方式 |
|----------|------|----------|
| 等待超时 | `waiting` 态且从未入库的 Cell，连续 N 天无新数据 | 从评估池删除，不走退出链路 |
| 已入库对象超时 | `qualified+` 对象长期无新数据 | 标记 `dormant`，交给 Step 5.4 接管 |

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
| 异常阻断 | `is_collision_id` |
| 空间 | `center_lon` / `center_lat` / `p50_radius_m` / `p90_radius_m` |
| 信号 | `rsrp_avg` / `rsrq_avg` / `sinr_avg` |
| 统计 | `independent_obs` / `distinct_dev_id` / `active_days` / `observed_span_hours` / `gps_valid_count` |
| 质量 | `position_grade` / `gps_confidence` / `signal_confidence` |

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
| 碰撞确认 | Step 5.1 / 5.5 | 全局键扫描，Step 3 只消费结果 |
| 多质心检测 | Step 5.5 | 高成本，只做异常子集 |
| 防毒化 | Step 5 | 可信库维护逻辑 |
| 发布 trusted_cell_library | Step 5 | Step 3 只产出冻结快照 |
| 退出确认（dormant → retired） | Step 5.4 | 属于长期维护链路 |

**Step 3 只回答一件事**：这个对象现在是否足以进入可信链路，以及它的冻结状态是什么。
