# Prompt 22：UI 对齐收尾 + 8 个异常标签精确定义

> **创建日期**：2026-04-18
> **接手背景**：基础质心算法（方案 B：MAD + 设备-天去重）已经在全量数据上重跑完成（`trusted_cell_library` batch 7 = 404,326 个 cell），UI 侧做了初步精简。现在要把 UI 对齐工作收尾，然后进入下一阶段：**多质心及异常标签的精确定义**。
> **上下文已清理**：之前会话的对话窗口已满，需要在本 prompt 的自包含语境下继续。
> **核心基线文档**：
>
> - `rebuild5/docs/gps研究/06_k_mad参数选择与效果对比.md`（方案 B 最终决策）
> - `rebuild5/docs/gps研究/05_基础质心算法改进研究.md`（V7 算法研究过程）
> - `rebuild5/docs/gps研究/04_验证数据集说明.md`（720 个研究样例 cell 的口径）
> - `rebuild5/docs/gps研究/fix_ss1_gps.md`（ss1 污染修复说明，已落地）

---

## 背景信息（自包含，无需回看历史）

### 已完成的修订

1. **基础质心算法**：采用方案 B（MAD 自适应 k + 按 `(cell, dev_id, DATE(event_time_std))` 去重），实现在 `rebuild5/backend/app/maintenance/window.py:219-262`。
2. **Step 3 / Step 5 一致性**：Step 3 用同一 MAD 逻辑（`profile/pipeline.py:1039`）；Step 5 的 `cell_core_gps_stats` 是 MAD 结果。
3. **ss1 污染修复**：`etl/parse.py` 已在 ss1 解析时过滤 `gps_info_type IN ('1','gps')`，全量重跑后 `etl_cleaned` 已无污染。
4. **触发条件确认正确**：`publish_bs_lac.py:169` 的 `t.p90_radius_m >= candidate_min_p90_m (800)` 中 `t.p90_radius_m` 就是方案 B 输出，所以"p90 > 800m 触发多质心深度分析"的逻辑和设计一致。
5. **Step 3 → Step 5 数据口径**：`trusted_cell_library` 只包含 `lifecycle_state IN ('qualified','excellent')`，即**已通过 Step 3 晋升**的 cell。未晋升的 waiting/observing 不在库里、也不在 UI 上。这是已验证事实，不需要再查。
6. **UI 已做的修改**（`frontend/design/src/views/governance/CellMaintain.vue`）：
   - 列从 17 减到 12：去掉状态、设备量、窗口量、最后观测（仍保留在详情区）
   - `P90(m)` 列改名为「质心覆盖(m)」，按精度范围着色
   - 筛选加了「大覆盖」，去掉「休眠/退出」
   - 后端 `maintenance/queries.py` 加了 `kind = 'large_coverage'` 分支

### 关键数据指标（batch 7 全量）

| 标签 | cell 数 | p90 中位 | 说明 |
|------|---------|---------|------|
| standard | 271,993 | 104m | 多数正常 cell |
| large_coverage | 28,534 | 485m | 方案 B 下已经比较紧凑 |
| migration | 9,035 | 2264m | 偏大，需要后续细化 |
| multi_centroid | 6,147 | 359m | 已通过 DBSCAN 识别 |
| collision | 0 | — | **碰撞检测当前未产出数据**（已知盲点）|

p90 分布：70% < 200m，89% < 500m，92% < 800m（符合方案 B 设计预期）。

### 研究数据表（可复用）

- `rebuild5.research_gps_cells`（790 行 / 720 唯一 cell，已选样例）
- `rebuild5.research_gps_records`（299,049 点，含 `gps_valid_fixed` 字段）
- `rebuild5.research_gps_work`（251,427 点，已过滤 ss1 污染）
- `rebuild5.research_centroid_v7` 等（各 k_mad 实验结果）
- `rebuild5.research_centroid_adaptive_B`（方案 B 结果）
- `rebuild5.research_centroid_dedupB`（方案 B + 设备-天去重结果）

---

## 约束（重要，避免重复过去踩过的坑）

1. **SQL 必须拆小步**：每条 SQL 只做一件事，避免 6 层以上 CTE 或大范围笛卡尔 join。上次连接死了两次都是因为复杂 SQL。每步物化一个临时表并建索引。
2. **冒烟测试优先**：大表跑之前先在 10 个 cell 的子集上验证。
3. **禁止修改生产代码超出本 prompt 范围**：UI 小改动、后端 `queries.py` 添 kind 分支可以；算法主体不改（方案 B 已固定）。
4. **写研究型文档放 `rebuild5/docs/gps研究/`**；UI / 前端修改直接在 `frontend/design/` 下。

---

## 第一阶段：UI 对齐收尾（先做完再进第二阶段）

### 任务 1.1 — 新增两个筛选 tab

**前端**（`frontend/design/src/views/governance/CellMaintain.vue`）：
- 在 `filterKinds` 数组里补两个：
  - `{ key: 'stable', label: '稳定' }`
  - `{ key: 'insufficient', label: '证据不足' }`
- 更新 `selectedKind` 类型 union，加上 `'stable' | 'insufficient'`

**后端**（`backend/app/maintenance/queries.py` 的 `get_maintenance_cells_payload`）：
- 在 `if kind == ...` 链里追加：
  ```python
  elif kind == 'stable':
      where_clauses.append("drift_pattern = 'stable'")
  elif kind == 'insufficient':
      where_clauses.append("drift_pattern = 'insufficient'")
  ```

**验证**：
```bash
curl -s "http://127.0.0.1:47231/api/maintenance/cells?kind=stable&page=1&page_size=3"
curl -s "http://127.0.0.1:47231/api/maintenance/cells?kind=insufficient&page=1&page_size=3"
```
两个都应该返回对应类别的 cell。

**注意**：后端改动后需要重启 uvicorn（当前进程无 `--reload`）。告知用户重启命令：
```
python -m uvicorn rebuild5.backend.app.main:app --host 127.0.0.1 --port 47231 --reload
```

### 任务 1.2 — 证据不足 cell 显示判定依据

**仅限 insufficient 标签的 cell**（其他标签不需要展开判定依据）。

**修改位置**：`CellMaintain.vue` 详情区的「生命周期与退出管理」或新增一个小块。

**显示内容**：当 `item.drift_pattern === 'insufficient'` 时，额外显示一行：
```
判定依据：活跃 {{ item.active_days }} 天 < 阈值 {{ INSUFFICIENT_MIN_DAYS }} 天
```

阈值从 `rebuild5/config/antitoxin_params.yaml` 的 `drift.insufficient_min_days` 读（当前值是 2）。

**选项**：可以硬编码为 2，加个注释说明来源；也可以新增一个前端常量文件映射。推荐硬编码 + 注释，简单。

### 任务 1.3 — 研究 cell 5792399381

**现象**：该 cell 的 p50=183m，p90=11091m，差距 60 倍。user 认为不合理，要求分析。

**疑点**：
- MAD 过滤应该能剔除远端离群点，但这里显然没有
- 可能是 MAD 自身值很大（数据分布本身宽），或者主簇 + 极少量超远点
- 对比 research 数据集里类似 cell，看方案 B 在这类上是否存在系统性漏洞

**步骤**（必须拆小步）：

1. 查 `trusted_cell_library` 该 cell 完整记录：
   ```sql
   SELECT * FROM rebuild5.trusted_cell_library
   WHERE cell_id = 5792399381 AND batch_id = 7;
   ```
2. 查 `cell_sliding_window` 该 cell 的原始点（`gps_valid=true` 筛选后的）：
   - 总点数、设备数、天数
   - GPS 点空间分布（按 0.001° 或 200m 分桶）
   - 设备贡献 top 5：按 `dev_id` 分组的点数
3. 算 `(cell, dev, 日期)` 去重后剩多少点
4. 手工模拟 MAD 过滤：
   - 初始 marginal median 是多少
   - med_d 和 MAD 分别是多少
   - 按方案 B 的 k 值（`< 50 → 2.5`、`50-199 → 1.5`、`≥ 200 → 2.5`）算阈值
   - 有多少点被过滤，p50/p90 重新算
5. 判断：
   - 如果 MAD 值很大（数据本身散），p90=11091m 是合理的但标签应该是 large_coverage 或 migration，不是 standard
   - 如果 MAD 很小但有极少数 >10km 的点恰好 ≤ med_d + k*MAD，说明方案 B 的边界 case
   - 可能需要一个"绝对距离 guardrail"（比如 MAD 阈值不得超过 2000m）

**输出**：`rebuild5/docs/gps研究/07_cell_5792399381_分析.md`
- 数据特征
- 算法决策过程复盘
- 问题根源
- 改进建议（如果发现算法有系统性问题）

---

## 第二阶段：8 个异常标签精确定义

在第一阶段 UI 对齐完成后，开始这一阶段。

### 8 个标签清单

| 序号 | 标签 | 当前字段 | 业务含义（需细化）|
|------|------|---------|------|
| 1 | 稳定 | `drift_pattern='stable'` | 单一位置 + 足够数据 |
| 2 | 证据不足 | `drift_pattern='insufficient'` | 活跃天数不足 |
| 3 | 大覆盖 | `drift_pattern='large_coverage'` | 单一位置但覆盖范围大 |
| 4 | 双质心 | `centroid_pattern='dual_cluster'` | 两个稳定簇 |
| 5 | 多质心 | `is_multi_centroid=true` + `centroid_pattern='multi_cluster'` | 3+ 个稳定簇 |
| 6 | 动态 | `is_dynamic=true` | 持续移动 |
| 7 | 迁移 | `drift_pattern='migration'` / `centroid_pattern='migration'` | 从 A 位置整体迁到 B |
| 8 | 碰撞 | `is_collision=true` | 同 cell_id 在不同物理位置（当前为 0，设计阶段）|

### 每个标签需要交付的结构

产出 8 份文档：`rebuild5/docs/gps研究/08_labels/<label>.md`

每份文档含：

1. **业务定义**（1-2 句）：这个标签描述什么物理现象？
2. **判定条件**（精确 SQL 可执行的数学表达式）：
   - 主条件（必须满足）
   - 辅助条件（如果有）
   - 阈值（来自 `antitoxin_params.yaml`，明确配置项名）
3. **样例 cell**（3-5 个）：
   - 从 `rebuild5.research_gps_cells` 或 `trusted_cell_library` 中找典型
   - 每个样例附：cell_id、关键指标、为什么是这个标签
4. **与其他标签的关系**：
   - 互斥 vs 可共存
   - 优先级（若互斥，谁优先）
5. **当前实现代码位置**：
   - `publish_cell.py` 或 `publish_bs_lac.py` 的第几行
   - 当前判定逻辑是否符合"业务定义"
6. **改进建议**（如果有）

### 总对照表

最后汇总到 `rebuild5/docs/gps研究/08_标签定义总览.md`，包含：

| 标签 | 主条件 | 辅助条件 | 阈值 | batch 7 数量 | 互斥关系 | 当前实现合理性 |
|------|--------|---------|------|-------------|---------|---------------|
| ... | | | | | | |

### 研究方法

1. **先用研究样例**（`rebuild5.research_gps_cells`）定义，样本量小好理解
2. **再在全量验证**（`trusted_cell_library` batch 7），看分布是否合理
3. **重点关注边界 case**：一个 cell 同时满足多个条件时应该归哪个标签？
4. **碰撞（is_collision）特殊处理**：当前 batch 7 中为 0，说明**检测逻辑缺失**。需要：
   - 查 `publish_bs_lac.py` 里是否有碰撞检测代码
   - 如果没有或没跑起来，设计一个检测逻辑（提案 + 伪代码，不直接改生产）
   - 参考样例：cell 27132465 的 33km 跨度，cell 25275343 的 7km 跨度都疑似碰撞

---

## 执行顺序清单

按以下顺序执行，**每项完成向用户报告再继续下一项**：

### 第一阶段

1. 创建 TaskCreate 列出所有子任务
2. 任务 1.1：加筛选 tab（前后端）+ 让用户重启后端 + 验证
3. 任务 1.2：insufficient 判定依据显示
4. 任务 1.3：cell 5792399381 研究 → 出 `07_cell_5792399381_分析.md`
5. 向用户汇报第一阶段完成，**等用户确认再进入第二阶段**

### 第二阶段

6. 从稳定、证据不足（简单的）开始定义，每定义 1 个就拿 3-5 个样例验证
7. 再定义大覆盖、动态
8. 然后定义多质心、双质心（这两个联动）
9. 最后定义迁移、碰撞
10. 汇总总对照表
11. 向用户汇报整个第二阶段，等下一步指示

---

## 关键工具和表

**可直接查的数据库表**（`rebuild5.*` schema）：

- `trusted_cell_library` — 当前发布的 cell 数据（batch 7 = 404,326 行）
- `cell_sliding_window` — Step 5 输入的 GPS 点（batch_id 分批）
- `cell_centroid_detail` — DBSCAN 多质心分析结果
- `research_gps_*` 系列 — 研究样例
- `research_centroid_*` 系列 — 各算法实验结果

**后端 API**：`http://127.0.0.1:47231/api/maintenance/...`
**前端 UI**：`http://127.0.0.1:47232/governance/cell`

**关键代码文件**：
- `rebuild5/backend/app/maintenance/window.py` — 基础质心算法（方案 B）
- `rebuild5/backend/app/maintenance/publish_cell.py` — 发布 + 标签计算
- `rebuild5/backend/app/maintenance/publish_bs_lac.py` — DBSCAN 多质心 + 触发
- `rebuild5/backend/app/maintenance/queries.py` — API 查询
- `rebuild5/config/antitoxin_params.yaml` — 所有阈值配置

---

## 你开始时要做的第一件事

1. 读一遍 `rebuild5/docs/gps研究/06_k_mad参数选择与效果对比.md` 的第 6-10 章（本阶段决策、生产代码入口、变大 cell 分析）
2. 读一遍 `rebuild5/docs/gps研究/04_验证数据集说明.md`（理解研究样例口径）
3. 不用读其他历史文档，避免浪费上下文

然后按"执行顺序清单"开始做任务 1.1。

---

## 失败信号（遇到这些情况停下来求助）

- SQL 单次查询 > 5 分钟没返回 → 强制 kill，拆更小步骤
- 改动后 UI/API 行为和预期不符 → 先查 DB 是否对齐，再查代码
- 第二阶段某个标签的判定条件和现有数据对不上 → 不要硬给标签强行匹配数据，**应该把差异记下来作为"当前实现与设计偏离"的发现**，这本身就是本阶段的价值

---

## 交付物清单

完成本 prompt 后，应有：

1. ✅ `CellMaintain.vue` 新增两筛选 tab，insufficient 显示判定依据
2. ✅ `queries.py` 新增 stable / insufficient 两 kind 分支
3. ✅ `docs/gps研究/07_cell_5792399381_分析.md`
4. ✅ `docs/gps研究/08_labels/` 目录，8 份标签文档
5. ✅ `docs/gps研究/08_标签定义总览.md`
6. ✅ 如果碰撞检测需要补全，新增 `docs/gps研究/09_碰撞检测设计.md`（只提案，不改代码）
