# Step 01b: BS 和 LAC 画像优化

## 背景

画像管道已完成三层初版构建（Cell → BS → LAC），需要继续优化。

## 前置条件

- 阅读 `99_系统上下文.md` 了解数据库和工具要求
- 阅读 `docs/02_profile/00_总览.md` 了解画像管道整体设计
- 阅读 `docs/02_profile/01_cell.md` 了解 Cell 画像字段和算法
- 阅读 `docs/02_profile/04_cell_research.md` 了解研究结论（质心算法、碰撞分析等）

## 当前状态

### 已完成的表

| 表 | 数量 | 说明 |
|----|------|------|
| `rebuild4.etl_filled` | 687,788 | ETL 产出（输入） |
| `rebuild4.etl_dim_cell` | 21,898 | Cell 画像（40+ 字段） |
| `rebuild4.etl_dim_bs` | 12,371 | BS 画像（已构建初版） |
| `rebuild4.etl_dim_lac` | 1,246 | LAC 画像（已构建初版） |
| `rebuild4.tmp_cell_obs_v2` | 153,400 | 1min 独立观测点（中间表） |

### Cell 画像核心算法（已验证，BS/LAC 继承）

- **独立观测点**: `(cell_id, minute)` 去重，不含设备维度
- **质心**: 中位数（PERCENTILE_CONT 0.5），比 AVG 精度高 7-70 倍
- **质量门槛**: >= 1 合格(93.4%), >= 3 良好(93.2%), >= 8+3设备+P90<500m 优秀(94.5%)
- **漂移分类**: 基于日质心的 net_drift / max_spread 比率
  - collision: >2km, ratio<0.3（碰撞，来回跳）
  - migration: >2km, ratio>0.7, 多设备（搬迁）
  - dynamic: >2km, ratio>0.7, <=3设备（火车/移动基站）
  - low_collision: 500m-2km, ratio<0.2

### 碰撞研究结论

- PCI 和 freq_channel 在两个位置完全相同，无法用射频参数区分
- 远端全部只有 1 台设备，近端多台 → 设备数投票可确定主位置
- ss1 来源的 GPS 全在正常位置，碰撞只出现在 cell_infos 中
- 碰撞处理策略待实施：用主位置质心重算

## etl_dim_bs 当前字段

operator_code, operator_cn, lac, bs_id, tech_norm,
cell_count, record_count, gps_valid_count, total_devices, active_days, independent_obs,
center_lon, center_lat, gps_p50_dist_m, gps_p90_dist_m, area_km2,
rsrp_avg, rsrq_avg, sinr_avg, gps_original_ratio, signal_original_ratio,
collision_cell_count, dynamic_cell_count, migration_cell_count, large_coverage_cell_count, active_cell_count, good_cell_count,
classification (normal_spread/moderate_spread/large_spread/collision_bs/dynamic_bs),
position_grade, gps_confidence, signal_confidence, cell_scale, lifecycle_state, anchorable,
province_name, city_name, district_name

### BS 分类分布（2026-04-08 修订）

| 分类 | 数量 | 说明 |
|------|------|------|
| normal_spread | 11,778 | 正常 |
| moderate_spread | 410 | 中度散布 |
| large_spread | 108 | 大覆盖（写字楼等） |
| multi_centroid | 38 | 多质心（同一 BS 下 Cell 分布在两个物理位置） |
| collision_bs | 35 | 有碰撞 Cell（max_spread >= 2.2km） |
| dynamic_bs | 2 | 全部 Cell 动态（高铁等） |

变更记录：
- 取消 `low_collision` 分类（45 个 Cell），重分类为 `large_coverage`。碰撞门槛从 500m 提高至 **2.2km**（低于此距离的日质心振荡属于城市 GPS 漂移，非跨区碰撞）。此门槛基于数据自然断层（1,993m-2,225m 无 Cell），未来可随样本增大调整。
- 新增 `multi_centroid` 分类（38 个 BS），识别远端≥2 Cell 且近端≥2 Cell（>1.5km）的多站点 BS。详情存入 `etl_dim_bs_centroid` 表。
- 41 个原 `collision_bs`（因 low_collision Cell 被取消而 collision_cell_count 归零）降级为对应的正常分类。

## etl_dim_lac 当前字段

operator_code, operator_cn, lac, tech_norm,
bs_count, cell_count, record_count, total_devices, active_days, independent_obs,
center_lon, center_lat, area_km2, rsrp_avg,
gps_original_ratio, signal_original_ratio,
collision_cell_count, dynamic_cell_count, collision_bs_count, dynamic_bs_count, large_spread_bs_count, active_bs_count,
anomaly_bs_ratio, position_grade, lifecycle_state,
province_name, city_name, district_name

## BS 继承关系

BS 从 Cell 继承异常标记：
- 碰撞：任一 Cell 碰撞 → BS 标记碰撞
- 动态：所有 Cell 都动态 → BS 动态（如高铁）
- 搬迁：多数 Cell 搬迁 → BS 搬迁

BS 独有模式：
- **写字楼型**：BS 覆盖面积大（Cell 分散），但单个 Cell 覆盖正常
- **高铁型**：所有 Cell 都是动态，BS 范围极大
- **正常型**：Cell 紧凑聚合

## 待优化方向

1. **BS 设备交叉率**：跨 Cell 活跃的设备比例（需要从 etl_filled 计算，当前未实现）
2. **碰撞 BS 的主位置选取**：用设备数投票，丢弃远端数据重算质心
3. **BS/LAC 与 rebuild2 对比验证**（sample_bs_profile, sample_dim_bs）
4. **BS 画像更多指标**：参考 rebuild2 的 classification_v2（normal_spread/single_large/dynamic_bs）
5. **LAC 画像优化**：区域统计、跨区分布

## 对比参考

- `rebuild4.sample_bs_profile`（rebuild2 BS 完整画像，1,096 条）
- `rebuild4.sample_dim_cell`（rebuild2 Cell 维度，3,750 条）

## UI

- 后端: `backend/app/routers/profiles.py`
- 前端: `frontend/src/pages/BsProfilePage.vue`, `LacProfilePage.vue`
- 侧边栏: "画像管道" 分组下 Cell / BS / LAC 三个页面
