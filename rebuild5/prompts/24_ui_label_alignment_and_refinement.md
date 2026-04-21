# 24 UI 标签对齐 + 多质心算法精调 + 异常数据研究

> **创建日期**：2026-04-19
> **仓库**：`/Users/yangcongan/cursor/WangYou_Data`
> **数据库**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **本 prompt 用途**：独立新对话从此处继续工作，**不需要回看历史对话**，所有必要上下文都在本文件 + 已有文档里
> **前置要求**：开始前必须阅读 §3 列出的 3 份已有文档

---

## 0. 当前已经完成的事（不要重做）

这轮 rebuild5 改造已经走过的阶段，详见对应文档：

1. **Step 5 标准质心算法修复**
   - `min_pts` 兜底改 4（原 10 误用 Step 3 资格门槛）
   - Step 4 异常协同 B 方案（`gps_anomaly_filter` + `cell_core_gps_day_dedup` CTE 改造）
   - 详见 `rebuild5/docs/gps研究/标准质心修复.md`

2. **Step 3 → Step 5 数据桥**（`snapshot_seed_records`）
   - 解决首次晋级 cell 的当前批事实层接入
   - 详见 `rebuild5/docs/gps研究/数据错误问题.md §10`
   - Step 1 基线已恢复，跨 batch 数据不再出现"历史断崖"

3. **8 标签规则 + 引擎**
   - `label_engine.py`（权威标签重写）
   - yaml 配置 `label_rules` + `multi_centroid_v2`
   - collision 规则已补（k=2 + 距离>100km）
   - 详见 `rebuild5/docs/gps研究/08_标签定义总览.md`

4. **UI 中文化 + 列/筛选改造**（部分完成，需要本轮继续对齐 — §4）

---

## 1. 本轮要做的 4 件事

### 1.1 UI 标签筛选与真实数据对齐
**现象**：UI 上的标签筛选 tab、分布条、SummaryCard 跟 `trusted_cell_library.drift_pattern` 的真实分布对不上（比如旧标签还在、某些新标签没显示、筛选 tab 顺序混乱、字段命名不一致）。

**要做**：
- 审核 `rebuild5/frontend/design/src/views/governance/CellMaintain.vue`
- 审核 `rebuild5/frontend/design/src/types/index.ts`（`DriftPattern` / `DRIFT_LABELS`）
- 审核 `rebuild5/backend/app/maintenance/queries.py` 的 `kind` 分支（`get_maintenance_cells_payload`）
- 确认前后端三层（DB 值 / API kind / UI 展示）完全对齐 8 标签（含 collision）+ 1 兜底（oversize_single）+ insufficient
- 筛选 tab 顺序建议：全量 / 正常(stable) / 覆盖大 / 双质心 / 迁移 / 碰撞 / 动态 / 多质心(uncertain) / 单簇超大 / 证据不足 / 全部异常

### 1.2 多质心算法阈值重新评估
**现象**：当前 batch 7 分布里 `large_coverage` 只有 310 个（0.07%），`dual_cluster` 2,159（0.5%），`uncertain` 76（0.02%） — 显著偏低。怀疑 `min_cluster_dev_day_pts = 10` 对于当前数据量还是太严。

**要做**：
- 在当前 `trusted_cell_library` / `trusted_snapshot_cell` 基础上重做 Phase B-1 数据调研
- 具体：各 cell 的 `total_dev_day_pts`（dedup 后的 raw_gps 点数）分布，每 bucket 内各标签占比
- 评估是否放宽到 `min_cluster_dev_day_pts = 5` 或 `7`，或者按 total 分档（参考历史讨论：`<=8 → 3`, `9-15 → 5`, `16-30 → 7`, `>30 → 10`）
- **数据驱动** — 不要先定阈值，跑数据看自然断点再建议
- **不要直接修 yaml / 重跑**，先产出调研报告，等用户拍板

### 1.3 调查现行标签是否真的有效执行
**现象**：`collision` 命中 **0 个**、`dynamic` 命中 **0 个**、`migration` 只命中 **1 个** — 这几个规则是否真的被执行？是不是规则实现有问题，导致逻辑上永远不满足？

**要做**：
- 对 `label_engine.py` 的 CASE WHEN 链做**逐条追踪**：对几个典型 cell，验证判定路径
- 具体验证：
  - 找 k_eff=2 且两簇距离 > 100km 的 cell，看是否被标 collision
  - 找 k_eff=2 且时间完全不重叠的 cell，看是否被标 migration
  - 找 k_eff≥3 且 dwell≤2 天的 cell，看是否被标 dynamic
- 如果命中 0 是"规则正确但无 case"，说明数据里这类 cell 真的罕见（可接受）
- 如果命中 0 是"规则实现有 bug"，必须修

### 1.4 异常数据继续研究
**现象**：当前 `insufficient` 占 35%（146,926 / 418,834），比预期仍高；`oversize_single` 还有 10 个。

**要做**：
- 对 `oversize_single` 10 个 cell 深挖：是残留飞跃？还是真的大范围？
- 对 `insufficient` 分段：
  - total_dev_day_pts=0 的（真空）占多少？
  - total 1-4（极稀）占多少？
  - total ≥ 5 但主簇没达门槛的（"有数据但聚不出"）占多少？
- 产出 `rebuild5/docs/gps研究/异常数据研究_v2.md`（或追加到现有文档）

---

## 2. 当前数据基线（batch 7 快照）

```
trusted_cell_library batch 7 总行数: 418,834

drift_pattern 分布：
  stable              269,352   (64.3%)
  insufficient        146,926   (35.1%)
  dual_cluster          2,159   ( 0.5%)
  large_coverage          310   ( 0.07%)
  uncertain                76   ( 0.02%)
  oversize_single          10
  migration                 1
  collision                 0
  dynamic                   0
```

**特征**：
- `stable + insufficient = 99.4%`，其他标签命中极低
- `collision` / `dynamic` 命中 0（可能是规则未生效或真无 case，§1.3 要查清）
- 发布数 = snapshot_cell 里 qualified+excellent 的 418,834，**数据链路已对齐**

---

## 3. 必读文档（启动前）

### 3.1 `rebuild5/docs/gps研究/标准质心修复.md`
**不要读全文**，重点章节：
- §1-§2：Step 5 的两个 bug 背景（min_pts 与 Step 4→5 断链）
- §5：代码改动位置清单
- §9：标签规则简表（§9 的表是最简干版）
- §11：已知遗留问题

### 3.2 `rebuild5/docs/gps研究/08_标签定义总览.md`
**必读**：
- §1 9 标签清单
- §2 判定流程图
- §3 每个标签的精确 SQL 条件
- §5 完整 SQL 管道（`label_engine.py` 的实现参考）

### 3.3 `rebuild5/docs/gps研究/数据错误问题.md`
**重点读**：
- §10.4-§10.5：snapshot_seed_records 机制原理
- §10.8：重跑范围说明

### 3.4 可选（如果做 §1.4）
- `rebuild5/docs/gps研究/位置物理位置丢失研究.md`（已解决，可跳过）

---

## 4. 关键代码位置

| 层 | 文件 | 关键点 |
|---|------|-------|
| yaml 配置 | `rebuild5/config/antitoxin_params.yaml` | `label_rules` + `multi_centroid_v2` + `gps_anomaly_filter` |
| 参数加载 | `rebuild5/backend/app/profile/logic.py` | `load_label_rules_params` / `load_multi_centroid_v2_params` |
| 标签引擎 | `rebuild5/backend/app/maintenance/label_engine.py` | CASE WHEN 判定链（§1.3 要审这个）|
| 发布逻辑 | `rebuild5/backend/app/maintenance/publish_cell.py` | 已验证正确（不要动）|
| Step 5 质心 | `rebuild5/backend/app/maintenance/window.py` | `build_cell_core_gps_stats` |
| 后端 API | `rebuild5/backend/app/maintenance/queries.py` | `get_maintenance_cells_payload` kind 分支（§1.1 要对齐）|
| 前端类型 | `rebuild5/frontend/design/src/types/index.ts` | `DriftPattern` / `DRIFT_LABELS` |
| 前端页面 | `rebuild5/frontend/design/src/views/governance/CellMaintain.vue` | SummaryCard / filterKinds / 分类条 / 表头 |

---

## 5. 关键约束（务必遵守）

### 5.1 SQL 必须拆小步
- 每条 SQL 只做一件事（一个 CREATE TABLE 或 GROUP BY 查询）
- 执行后立即检查行数确认成功
- **禁止**：≥3 层 CTE、`EXISTS (SELECT …)` 子查询、JOIN 超过 3 张表
- 需要多表关联时，先物化 `_tmp_*` 小表（UNLOGGED + 索引），再用简单 JOIN
- 有过先大 SQL 跑卡死的教训，用户会立即中断

### 5.2 业务键是 5 元组
- 查单个 cell 时必须用 `(operator_code, lac, bs_id, cell_id, tech_norm)` 完整键
- **不要**只用 `cell_id` — 同 cell_id 可能对应多个业务组合（`1353583` 就是典型：46001/4G 是 excellent，另一组是 waiting）
- 单 cell_id 查询只用于初步诊断，结论必须用完整键复核

### 5.3 核对数据前确认基线正确
- 查询前先看 `rebuild5_meta.run_log` 最近 `step1/pipeline/enrichment/maintenance` 的状态
- 看最大 batch_id / snapshot_version
- 避免在"中间坏基线残留"上做判断（上轮讨论就因此误判过一次）

### 5.4 先研究再工程
- 任何阈值调整、规则变更，先在小样本上跑 SQL 模拟
- 产出结论后让用户拍板
- **不要直接改 yaml/重跑**

### 5.5 分批验证
- 改动后先跑 batch 7 验证
- 不要一开始就跑全 7 batch

---

## 6. 不在本轮范围（明确排除）

1. **publish_cell.py 改造** — 已验证正确（发布逻辑对齐 snapshot 里 qualified+excellent），不要动
2. **Step 3 显式退出逻辑**（dormant/retired 剔除）— 后续独立工作
3. **物理位置丢失** — 已解决
4. **enriched_records 补齐** — snapshot_seed_records 机制已覆盖
5. **Step 1/2/3/4 代码改动** — 仅研究和分析，不要改源代码

---

## 7. 执行顺序建议

按以下顺序做，**每项完成后向用户报告再进下一项**：

1. **先做 §1.1 UI 对齐**（不涉及数据，改前端 + queries.py 即可，风险最低）
2. **然后 §1.3 标签是否有效执行**（诊断性，不改代码）
3. **然后 §1.2 多质心阈值调研**（数据研究，产出报告）
4. **最后 §1.4 异常数据研究**（产出研究文档）

---

## 8. 启动第一步

启动后先做两件事：

1. 执行下面 SQL 确认当前基线没变（小心别跑全量聚合）：
   ```sql
   SELECT run_type, MAX(finished_at) FROM rebuild5_meta.run_log
   WHERE started_at > '2026-04-19 00:00' GROUP BY run_type;
   ```

2. 执行 §2 的 drift_pattern 分布 SQL，看数字是否跟基线一致：
   ```sql
   SELECT drift_pattern, COUNT(*) FROM rebuild5.trusted_cell_library
   WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
   GROUP BY drift_pattern ORDER BY 2 DESC;
   ```

**如果分布与 §2 吻合** → 按 §7 顺序开始做第一步。
**如果分布明显不同** → 说明 agent 又重跑了 / 数据有变动，暂停动手，先汇报数据现状给用户。

---

## 9. 汇报节奏

- 每项任务完成给用户一份简短结论（2-5 句 + 数据表）
- 发现意外现象**立即停下汇报**，不要自行修补
- 涉及规则 / 阈值变更前，**数据驱动的建议先拿出，用户拍板后再实施**
