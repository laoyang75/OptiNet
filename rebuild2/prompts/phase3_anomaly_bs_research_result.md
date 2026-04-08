# Phase 3 异常研究：BS 碰撞与分类 — 完成报告

> 本文档记录 Phase 3 Part B（异常研究）的完整过程、算法逻辑和最终结论。
> 产出：`rebuild2._research_bs_classification_v2` 分类标记表
> 状态：已完成，等待 Phase 4 画像阶段使用

---

## 1. 研究背景

Phase 3 Step 1-5 完成了正常数据处理（BS 精算、Cell 校验、GPS 修正、信号补齐、回算），产出了 `dwd_fact_enriched`（3008 万行）、`dim_bs_refined`（193,036 BS）、`dim_cell_refined`（573,561 Cell）。

在此基础上，发现部分 BS 存在空间散布异常（P90 偏移 > 1500m），需要分析原因并分类标记，为 Phase 4 画像做准备。

---

## 2. 分析漏斗

### 第一层：数据充分性过滤

| 类别 | 条件 | 数量 | 记录数 | 处理 |
|------|------|------|--------|------|
| 数据不足 | GPS 点 ≤ 3 或 单设备(GPS≥4) | 39,096 | 269,559 | 标记 gps_confidence=low/none |
| 正常 BS | 数据充足且空间不异常 | 144,348 | 27,317,770 | 直接进入画像 |
| 异常候选 | GPS≥10, 设备≥2, 空间散布异常 | 9,591 | 2,484,315 | 进入 Cell 质心分析 |

异常候选筛选条件（从 `dim_bs_refined`）：
- `total_gps_points >= 10 AND distinct_gps_devices >= 2`
- 且满足以下任一：
  - `gps_p90_dist_m > 1500`
  - `gps_max_dist_m > 5000`
  - `had_outlier_removal = true AND gps_p90_dist_m > 1000`

### 第二层：Cell 质心法分类

#### 算法概述

**核心思路**：对每个 Cell 独立分析空间特征，再在 BS 级对比各 Cell 质心位置。

为什么不用 BS 级 GPS 点直接聚类（网格峰值法）：
- GPS 飘点会在远处形成假峰值 → 假阳性（误判为碰撞）
- 不同 Cell 的 GPS 混在一起，无法区分是碰撞还是移动 Cell → 假阴性
- Cell 质心（加权平均）天然抗噪声，更准确反映物理位置

#### Step 1：提取 GPS 数据（含 CellID）

从 `l0_lac` 提取 9,591 个候选 BS 的有效 GPS 记录：
- 条件：`GPS有效 = true`，经纬度在中国范围内（70-140°E, 15-55°N）
- 产出：`_research_cand_gps_v2`（203 万行，含 CellID、设备标识、上报日期）

#### Step 2：Cell 级网格聚合

按 0.005° 网格（≈500m）对每个 Cell 独立聚合：
- 产出：`_research_cell_grid`（208,607 个网格单元）
- 每个网格记录：点数、设备数、活跃日期

#### Step 3：Cell 质心 + 空间跨度

对每个有 ≥ 3 个 GPS 点的 Cell 计算：
- **质心**：加权平均经纬度（按网格点数加权）
- **空间跨度**：网格 min/max 经纬度换算距离（米）

分类规则：
- 跨度 > 1500m → **移动 Cell**（高铁/车载/移动基站）
- 跨度 ≤ 1500m → **固定 Cell**

产出：`_research_cell_centroid_v2`（44,157 个有效 Cell）
- 固定 Cell：19,420 个
- 移动 Cell：24,737 个

#### Step 4：BS 级固定 Cell 质心对比

对每个 BS，只看固定 Cell 的质心分布：
- 计算同 BS 下所有固定 Cell 质心的最大跨度（min/max 经纬度差换算距离）

| 固定 Cell 质心最大间距 | 判定 |
|----------------------|------|
| BS 无固定 Cell（全部 Cell 都是移动的） | 动态 BS |
| < 500m | 正常（GPS 噪声导致初始异常标记） |
| 500 - 1500m | 面积大 / 低精度 |
| > 1500m | 潜在碰撞 → 进入设备分裂验证 |
| 仅 1 个固定 Cell | 面积大 / 低精度 |

#### Step 5：设备分裂验证（碰撞确认）

对固定 Cell 质心间距 > 1500m 的 BS（2,199 个），验证是否真碰撞：

1. 以 BS 级质心经度为分界，将固定 Cell 分为 A/B 两组
2. 检查每个设备（设备标识）出现在哪些组
3. 计算交叉率 = 同时出现在两组的设备数 / 总设备数

| 交叉率 | 判定 | 数量 |
|--------|------|------|
| < 5% | 确认碰撞 | 2,013 |
| 5-20% | 疑似碰撞 | 173 |
| > 20% | 不确定 | 13 |

### 最终分类结果

| 分类 | BS 数 | 记录数 | Phase 4 处理 |
|------|-------|--------|-------------|
| **dynamic_bs** | 5,124 | 983,153 | 标记，含移动Cell，GPS画像精度低 |
| **collision_confirmed** | 2,013 | 726,109 | **标记，第二轮拆分重算** |
| **collision_suspected** | 173 | 77,567 | **标记，第二轮拆分重算** |
| **single_large** | 1,360 | 429,450 | 标记低精度 |
| **normal_spread** | 908 | 265,621 | 回归正常（GPS 噪声） |
| **collision_uncertain** | 13 | 2,415 | 标记不确定 |

**需拆分（第二轮处理）：2,186 BS (1.1%)，80.4 万条 (2.7%)**

---

## 3. 碰撞判断算法（完整）

### 碰撞的本质

运营商 BS 编码碰撞 = 不同物理基站共用同一个 `(运营商编码, 标准制式, LAC, 基站ID)` 组合键。

### 判断依据

碰撞的特征是**不同物理位置的不同设备群和不同 CellID 群**共享一个 BS ID。

核心判据是**设备标识的空间分布**：
- 设备分裂（交叉率 < 5%）→ 不同物理位置有各自的用户群 → 碰撞
- 设备不分裂 → 同一批用户出现在多个位置 → 移动/漫游

### 验证结论

已验证碰撞不是由数据处理造成的：
- **GPS 补齐（ss1_own）**：主副质心的补齐比例一致（~32%），不是补齐导致
- **Cell/LAC 补齐**：主副质心的 Cell 来源分布一致（~68% cell_infos），不是 Cell 分配问题
- **CellID 分裂**：碰撞 BS 下的 CellID 也完全分裂（173 个 Cell 只在 A 组，140 个只在 B 组）
- **结论**：确认是运营商 BS 编码复用

### 算法步骤总结

```
输入: 异常候选 BS (GPS≥10, 设备≥2, 空间散布异常)

1. 提取 GPS + CellID → _research_cand_gps_v2
2. Cell 级 500m 网格聚合 → _research_cell_grid
3. 每个 Cell: 加权质心 + 空间跨度 → _research_cell_centroid_v2
   - 跨度 > 1500m → 移动 Cell
   - 跨度 ≤ 1500m → 固定 Cell
4. BS 级: 固定 Cell 质心最大间距 → _research_bs_classification_v2
   - 无固定 Cell → dynamic_bs
   - < 500m → normal_spread
   - 500-1500m → single_large
   - > 1500m → 潜在碰撞
5. 设备分裂验证 (交叉率)
   - < 5% → collision_confirmed
   - 5-20% → collision_suspected
   - > 20% → collision_uncertain
```

---

## 4. 算法演进记录

### v1：网格峰值法（已弃用）

对 BS 的所有 GPS 点做 500m 网格聚类，贪心找峰值。

问题：
- 假阳性 ~2,800 个：GPS 飘点形成假峰值，误判为碰撞
- 假阴性 ~415 个：网格聚类没找到第二峰，但 Cell 质心实际割裂
- 判定碰撞 ~4,972 个（过高）

### v2：Cell 质心法（当前使用）

先对每个 Cell 独立分析，区分固定/移动 Cell，再用固定 Cell 质心做 BS 级对比。

改进：
- 排除移动 Cell 的干扰（5,124 个动态 BS）
- 排除 GPS 噪声的误判（908 个 normal_spread）
- 判定碰撞 2,186 个（更准确）

---

## 5. 产出表清单

| 表名 | 说明 | 行数 | 用途 |
|------|------|------|------|
| `_research_cand_bs` | 异常候选 BS 列表 | 9,592 | 中间表 |
| `_research_cand_gps_v2` | 候选 BS 的 GPS + CellID | 2,033,948 | 核心数据 |
| `_research_cell_grid` | Cell 级网格聚合 | 208,607 | 中间表 |
| `_research_cell_centroid_v2` | Cell 质心 + 跨度 | 44,157 | 核心结果 |
| `_research_bs_classification_v2` | **最终 BS 分类** | 9,591 | **Phase 4 读取** |
| `_research_bs_classification` | v1 分类（已弃用） | 9,592 | 历史参考 |
| `_research_collision_sample` | 碰撞样本（50个） | 50 | 验证用 |
| `_research_collision_detail` | 碰撞样本详情 | 121,852 | 验证用 |
| `_research_uncertain_bs` | 多质心待分析 BS | 198 | 验证用 |
| `_research_uncertain_gps` | 待分析 BS 的 GPS | 32,045 | 验证用 |
| `_research_multi_collision_bs` | 多质心碰撞 BS | 2,567 | 验证用 |
| `_research_multi_collision_gps` | 多质心碰撞 GPS | 777,529 | 验证用 |

---

## 6. Phase 4 衔接

### 第一轮画像（正常处理）

读取 `_research_bs_classification_v2`，将 `classification_v2` 作为标记字段附到画像上：
- LAC 画像：汇总该 LAC 下各分类 BS 的数量和占比
- BS 画像：附加 `classification_v2` 字段
- Cell 画像：附加所属 BS 的分类标记

不做任何特殊处理，碰撞 BS 的画像也正常生成（数据是混合的）。

### 第二轮异常处理

对标记为 `collision_confirmed` / `collision_suspected` 的 2,186 个 BS：
1. 读取 `_research_cell_centroid_v2`，按固定 Cell 质心空间聚类分组
2. 每组 Cell 作为一个虚拟 BS
3. 用正常算法对虚拟 BS 重新计算画像
4. 替换原碰撞 BS 的画像

对动态 BS、噪声大的 BS：具体分析后决定处理方式。
