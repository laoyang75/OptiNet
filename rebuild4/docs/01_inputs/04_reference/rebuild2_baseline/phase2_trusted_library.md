# Phase 2 Prompt：可信库构建

> 用途：L0 数据生成完成后，启动新会话读取此 prompt 开始可信库构建
> 阶段：L0 数据 → L2 可信 LAC → L2 可信 Cell → L2 可信 BS → 全局表回写

---

## 1. 环境信息

- **数据库**：PostgreSQL 17 @ 192.168.200.217:5433/ip_loc2（用户 postgres，密码 123456）
- **SSH**：root@192.168.200.217，密码 111111
- **后端**：FastAPI 端口 8100（rebuild2/backend）
- **启动器**：端口 9100（rebuild2/launcher_web.py）
- **大表操作**：先用 MCP（mcp__PG17__execute_sql）小规模测试，再 SSH 到服务器用 psql 全量执行

---

## 2. 前置条件

Phase 1 已完成，产出两张 L0 表：

| 表 | 行数 | 原始记录数 | 用途 |
|----|------|-----------|------|
| `rebuild2.l0_gps` | **3843 万** | 1654 万 | GPS 定位表，**用于构建可信库** |
| `rebuild2.l0_lac` | **4377 万** | 1786 万 | LAC 定位表，全局表，可信库确定后从中提取最终数据 |

两张表字段结构一致，已应用 26 条 ODS 清洗规则。

### 关键字段结构要点

- **CellID 覆盖率**：V2 重建后 **100%**（邻区行已去除，所有行都有 CellID）
- **行组成**：cell_infos 主服务 + ss1（无邻区行）
- **is_connected 列已移除**
- ss1 信号按制式匹配基站（详见 `docs/05_ss1解析规则.md`）
- 已有索引：LAC、CellID、基站ID、运营商+制式、原始记录ID、上报时间

---

## 3. 必须先读取的文件

### 上下文
1. `rebuild2/prompts/phase1_field_governance.md` — Phase 1 完整规则
2. `rebuild2/docs/04_phase1_总结.md` — Phase 1 总结（含全量执行结果、ss1 评估、CellID 口径说明）
3. `docs/data_warehouse/00_业务逻辑与设计原则.md` — 四个核心业务原则

### 数据库
4. `rebuild2.l0_gps` — 查看字段结构（用 `SELECT * FROM rebuild2.l0_gps LIMIT 5`）
5. `rebuild2_meta.target_field` — L0 字段定义（60 个字段）
6. `rebuild2_meta.ods_clean_rule` — 已应用的 26 条清洗规则
7. `rebuild2_meta.l0_stats_cache` — L0 统计缓存（毫秒级读取）

### 历史参考（可选）
8. `legacy."Y_codex_Layer2_Step04_Master_Lac_Lib"` — 上一轮可信 LAC 库（881 行）
9. `legacy."Y_codex_Layer2_Step05_CellId_Stats_DB"` — 上一轮 Cell 统计（50 万行）
10. `legacy."Y_codex_Layer3_Step30_Master_BS_Library"` — 上一轮 BS 库（13.8 万行）

---

## 4. 业务原则（必须遵守）

1. **有效 cell_id = 有效记录** — 不因 GPS 漂移丢弃记录
2. **修正优于丢弃** — 优先修正、补齐、标记
3. **层层收敛、互相印证** — 正向 LAC→Cell→BS→GPS，反向 BS→Cell
4. **基线驱动日更** — 冷启动建基线，后续撞基线

---

## 5. 原始设计路径（来自 docs/data_warehouse/00_业务逻辑与设计原则.md）

用户的原始设计是一个 8 步冷启动链路。Phase 2 覆盖前 4 步。**你必须理解每一步的原因，向用户确认参数后再执行。**

### Step 1：可信 LAC — 画出可信地盘边界

**为什么先做 LAC**：LAC 是最大粒度的网络分区，一个假 LAC 下面所有 Cell/BS 都不可信。

**输入**：`rebuild2.l0_gps`（全部行都有 CellID）
**逻辑**：
1. 按 `(运营商编码, 标准制式, LAC)` 聚合
2. 筛选条件（参数化，用户在 UI 上确认）：
   - 运营商过滤：只保留五大运营商
   - LAC 编码过滤：剔除 NULL、已知黑名单值
   - 位置过滤：只保留 GPS 落在目标区域（北京）的数据
   - 稳定性过滤：活跃天数 ≥ 阈值（如 7 天）且上报量 ≥ 阈值
3. **产出**：`rebuild2.dim_lac_trusted`
4. **参考**：上一轮 881 个可信 LAC

### Step 2：可信 Cell — 在可信 LAC 范围内筛选稳定 Cell

**为什么在 LAC 之后**：Cell 挂在 LAC 下面，先限定在可信 LAC 范围内分析，避免垃圾传播。

**输入**：`rebuild2.l0_gps` + `rebuild2.dim_lac_trusted`
**逻辑**：
1. 只在可信 LAC 的明细中，按 `(运营商, 制式, CellID, LAC)` 聚合
2. 统计每个 Cell 的活跃天数、GPS 空间分布、上报量
3. 剔除：位置离散、偶尔出现、样本量太小的 Cell
4. 标记异常（一个 Cell 出现在多个 LAC → 映射异常）
5. **产出**：`rebuild2.dim_cell_stats`

### Step 3：可信 BS — 从 Cell 反推基站，碰撞检测

**为什么是 Cell→BS**：原始数据有 cell_id，bs_id 是推算的（4G: /256, 5G: /4096），所以物理上先有 Cell 再聚合出 BS。

**输入**：`rebuild2.dim_cell_stats`
**逻辑**：
1. 按 `(制式, 基站ID, LAC)` 聚合所有可信 Cell
2. 计算 BS 中心点（GPS **中位数**，不是平均——中位数抗离群点更强）
3. 计算覆盖半径（GPS 到中心距离的 P50/P90）
4. 碰撞检测：同 bs_id 下的 Cell 的 GPS 聚落分成不连通的几簇 → 编码碰撞
5. 标注风险等级（碰撞/编码异常/正常）
6. **产出**：`rebuild2.dim_bs_trusted`（含中心点/范围/碰撞标记/风险等级）

### Step 4：全局表回写 — 用可信库过滤全局 LAC 表

**为什么用 l0_lac 而不是 l0_gps**：l0_gps 用于构建可信库（GPS 数据多），l0_lac 是全局表（质量稳），可信库确定后从 l0_lac 中提取最终数据。

**输入**：`rebuild2.l0_lac` + 可信库
**逻辑**：
1. 用可信 LAC 范围过滤全局表
2. 回写 LAC 纠偏结果
3. **产出**：`rebuild2.dwd_fact_filtered`

### 后续步骤（Phase 3+，不在本阶段）

| Step | 名称 | 说明 |
|------|------|------|
| 5 | GPS 修正 | 用 BS 中心点修正/回填 GPS（距离 > 阈值 → 钉成 BS 中心点） |
| 6 | 信号补齐 | 二阶段：同 Cell 时间最近 → 同 BS 最大 Cell 时间最近 |
| 7 | 完整回归 | 用纯化后的规则从 L0 全量重跑一遍，确保一致性 |
| 8 | 三级基线 | LAC/BS/Cell 画像聚合，作为日常运营的对比基准 |

---

## 6. 工作方式

**与 Phase 1 相同**：定义规则 → UI 审核 → 确认执行 → 查看结果。

你需要：
1. 在 `rebuild2/backend/app/api/` 下创建路由
2. 在 `rebuild2/frontend/js/pages/` 下创建页面
3. 每一步的参数（阈值）在 UI 上展示，用户确认后执行
4. **大表聚合用预算缓存**（参考 `rebuild2_meta.l0_stats_cache` 模式），避免页面超时
5. 执行结果在 UI 上展示（行数、漏斗统计、与上一轮对比）

**不要一次性做完所有步骤。** 先做 Step 1（可信 LAC），用户确认后再做 Step 2。

---

## 7. 数据库 schema 规划

| Schema | 表 | 说明 |
|--------|-----|------|
| `rebuild2` | `dim_lac_trusted` | 可信 LAC 维表 |
| `rebuild2` | `dim_cell_stats` | Cell 统计维表 |
| `rebuild2` | `dim_bs_trusted` | 可信 BS 维表 |
| `rebuild2` | `dwd_fact_filtered` | 合规过滤后的全局明细 |
| `rebuild2_meta` | `trusted_build_rule` | 可信库构建参数 |
| `rebuild2_meta` | `trusted_build_result` | 构建统计结果 |
| `rebuild2_meta` | `trusted_stats_cache` | 聚合统计缓存（避免页面超时） |

---

## 8. 注意事项

- L0 表是 1.3~1.4 亿行，任何 GROUP BY 都要几十秒到几分钟，**页面不能直接查大表**
- 统计结果必须预算到缓存表，页面读缓存
- 构建可信库时 `SET statement_timeout = 0; SET work_mem = '256MB';`
- 每步产出后建必要索引
- UI 风格与 Phase 1 一致（复用 rebuild2 的样式系统和组件）
