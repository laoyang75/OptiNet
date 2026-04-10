# rebuild5 开发审计记录

> 本文件记录每个模块的审计进度和结果。新会话开始时先读此文件确认进度。

## 审计进度

| # | 文档 | 状态 | 最后更新 |
|---|------|------|----------|
| 0 | 00_全局约定 | ✅ 完成 | 2026-04-09 |
| 1 | dev/00_工程约束 | 跳过 | - |
| 2 | dev/01_数据准备 | ⚠️ 已审查，代码待清理 | 2026-04-09 |
| 3 | dev/02_数据库schema | 未开始 | - |
| 4 | 01_数据源接入 (Step 1) | ✅ 完成 | 2026-04-09 |
| 5 | 02_基础画像 (Step 2) | ✅ 完成 | 2026-04-09 |
| 6 | 03_流式质量评估 (Step 3) | ✅ 完成 | 2026-04-09 |
| 7 | 04_知识补数 (Step 4) | ✅ 完成 | 2026-04-09 |
| 8 | 05_画像维护 (Step 5) | ✅ 完成 | 2026-04-09 |
| 9 | 06_服务层_运营商数据库与分析服务 | ✅ 文档重写 | 2026-04-09 |
| 10 | 07_数据集选择与运行管理 | ✅ 确认保持 | 2026-04-09 |
| 11 | 09_控制操作_初始化重算与回归 | ✅ 文档简化 | 2026-04-09 |

## 已完成的前置修复（本轮审计前已处理）

以下问题在 2026-04-09 的初轮审计中已修复，不需重新检查：

- 侧边栏按 Step 分组
- API 前缀 /api/profile → /api/routing
- 补充 evaluation/run、pipeline/run 端点
- 补充 :id 详情端点
- 分页 page/page_size 支持（后端 + 前端）
- evaluation/trend 端点
- ETL pipeline.py 拆分 parse/clean/fill
- profile/pipeline.py 拆分 + evaluation 独立目录
- 碰撞两层体系（A 类绝对碰撞 + B 类映射表）
- Step 2 三层匹配（Layer1/2/3）
- 漂移分类阈值对齐（stable<500m, insufficient<2天）
- 多质心触发改为 P90≥800m
- ETL 邻区 LAC 清理（数据问题，非代码 bug）
- 字段审计页 55 字段分 9 类（对齐 rebuild4）
- 清洗页补充 WiFi 规则 ODS-017/018
- 补齐页添加 WiFi + 绝对数量展示
- Cell/BS/LAC 画像维护页行展开详情
- Cell 画像添加物理位置（关联 rebuild4.sample_cell_profile）
- Step 5 Cell 从 enriched_records 重算质心
- Step 5 BS 从 Cell 中位数重算质心
- Step 5 LAC 从 BS 重算
- BS/LAC 可信库只发布 qualified（去掉 observing）
- source_prep.py 去掉硬编码，配置化 dataset.yaml
- 2G/3G 过滤配置化 path_b_tech_whitelist

---

## 详细审计记录

### #0 全局约定 (2026-04-09)

**维度 A — 文档 vs 代码对齐**

| # | 偏差 | 处理 |
|---|------|------|
| A1 | `maintenance/pipeline.py:558` 经度系数 85000，应为 85300 | ✅ 已修复 |
| A2 | gps_confidence 用比率(>=0.9/0.6)判定，文档定义为计数(>=20/10/1/0) + 设备数 | ✅ 已修复 evaluation/pipeline.py，改为计数逻辑，增加 none 级别 |
| A3 | signal_confidence 同上，用比率判定，文档为计数(>=20/5/1/0) | ✅ 已修复，profile_base 增加 signal_original_count 列 |
| A4 | cell_scale 阈值完全不同（代码 400/100/30/10 vs 文档 50/20/10/3），且缺 devs 判定 | ✅ 已修复 maintenance/pipeline.py，对齐文档阈值+设备数 |
| A5 | is_dynamic 判定逻辑与文档不同（代码用 anomaly_count>=3，文档用 drift_pattern） | ✅ 已修复，改为 spread>1500 AND drift_pattern∈(migration,large_coverage) |
| A6 | 信号范围：RSRQ 文档 -50~0 vs 代码 -34~10，SINR 文档 -30~50 vs 代码 -23~40 | ✅ 文档已更新为工程经验值 |

**维度 A — 配置外化补齐**

| # | 缺失参数 | 处理 |
|---|----------|------|
| A7 | profile_params.yaml 缺 gps_confidence/signal_confidence 阈值 | ✅ 已添加 |
| A8 | antitoxin_params.yaml 缺 is_dynamic.min_spread_m、cell_scale 阈值 | ✅ 已添加 |
| A9 | logic.py flatten 函数缺对应参数解析 | ✅ 已添加 |

**维度 A — 枚举值拼写**：全部一致，无偏差。lifecycle_state / drift_pattern / position_grade / tech_norm 等均正确。

**已知遗留（待 #8 Step 5 审计）**：
- drift_pattern 分类使用 p90_radius_m 作为 max_spread_m 的代理，不使用 ratio（迁移比），与文档定义有本质差异
- 文档的 collision drift 类别 (max_spread>=2200, ratio<0.3) 在代码中从未产出
- 文档的 large_coverage 定义为 500-2200m，代码实现为 >=2500m

**维度 B — 代码质量**：本模块为文档审查，无额外代码质量问题。

**维度 C — 数据正确性**：枚举值、距离系数为配置/常量层检查，不涉及运行时数据验证。

---

### #4 Step 1 数据源接入 — 01a/01b (2026-04-09)

**维度 A — 文档 vs 代码对齐**

| # | 偏差 | 处理 |
|---|------|------|
| A1 | ODS 规则数：文档 16 条，代码 18 条（+ODS-017/018 WiFi） | ✅ 文档已更新为 19 条 |
| A2 | ODS-005：文档只写 `lac=268435455`，代码还有 `2147483647` | ✅ 文档已更新 |
| A3 | 5G LAC 24bit 溢出值 (16777214/16777215) 未清洗 | ✅ 新增 ODS-004b 规则（代码+文档） |
| A4 | event_time_std：文档用 `ts_std`，代码用 `report_ts` | ✅ 文档统一为 `report_ts`（00_全局约定 + 01a + 01b） |
| A5 | 最终删行：文档只提 cell_id IS NULL，代码还删 event_time_std IS NULL | ✅ 文档已更新 |

**维度 A — 解析/清洗/补齐逻辑核验**

- parse.py：cell_infos jsonb_each + isConnected=1 + gps_valid 逻辑 ✓；ss1 forward-fill + 制式匹配 ✓；tech_norm 映射完整 ✓
- clean.py：19 条 ODS 规则执行正确 ✓；派生字段 bs_id/sector_id/operator_cn/has_cell_id ✓；event_time_std COALESCE 正确 ✓
- fill.py：record_id+cell_id 匹配 ✓；<=60s 时间约束 ✓；>1min 只补 operator/lac ✓；14 对齐列完整 ✓；不增减行 ✓

**维度 C — 数据验证**

- LAC 溢出值：当前样本未命中（5G max LAC=2097233 < 16777215），ODS-004b 作为防护规则
- 运营商白名单 11 个编码对齐 ✓

---

### #5 Step 2 基础画像 — 02_基础画像.md (2026-04-09)

**维度 A — 文档 vs 代码对齐**

| # | 偏差 | 处理 |
|---|------|------|
| A1 | 去重时间字段：文档写 `ts_std`，代码用 `event_time_std` | ✅ 文档已更新为 event_time_std |
| A2 | signal_original_count：文档说不要求在 profile_base 暴露，但已作为输出字段 | ✅ 文档已更新 |
| A3 | 信号有效范围：文档用旧全局值 (-156~0/-50~0/-30~50)，应与 ODS 边界一致 | ✅ 文档已更新为 ODS 值 |

**维度 A — 核心逻辑核验**

- 三层 Path A 匹配 (Layer1 精确 / Layer2 非碰撞宽松 / Layer3 碰撞GPS回退) ✓
- Path B/C 分流 (有GPS→B, 无GPS→C丢弃) ✓
- 分钟级去重 date_trunc('minute', event_time_std) ✓
- 中位数质心 PERCENTILE_CONT(0.5) ✓
- P50/P90 半径 85300/111000 系数 ✓
- 2G/3G 过滤 path_b_tech_whitelist ✓
- 冻结快照：只读 MAX(batch_id) 的 trusted_cell_library ✓
- step2_run_stats 统计完整 ✓

**维度 C — 数据验证**

- profile_base: 1,427 cells，center_lon 116~123°，center_lat 39~42°（北京周边 ✓）
- path_a: 541,715 + path_b+c: 55,494 = 597,209 = etl_cleaned 总数 ✓
- avg_obs=8.8, avg_devs=2.4, avg_span=42h — 合理
- 注意: profile_base DB 尚缺 signal_original_count 列（代码已改，需重跑 pipeline 生效）

---

### #6 Step 3 流式质量评估 — 03_流式质量评估.md (2026-04-09)

**维度 A — 文档 vs 代码对齐（代码修复）**

| # | 偏差 | 处理 |
|---|------|------|
| A1 | collision_flags CTE 空桩 (WHERE false)，collision_id_list 有 2,695 条数据未使用 | ✅ 已修复：改为读取 collision_id_list（含 cold start 防护） |
| A2 | carry-forward 引用 `l.is_collision`，snapshot schema 用 `is_collision_id` | ✅ 已修复：加 `AS is_collision_id` 别名 |
| A3 | baseline_eligible UPDATE 覆盖 carry-forward 行（文档要求只继承不重评） | ✅ 已修复：WHERE EXISTS profile_base 限定只更新 current_candidates |

**维度 A — 核心逻辑核验**

- Cell lifecycle 判定 (waiting/observing/qualified/excellent) ✓，阈值从 yaml 加载
- 三层资格 (is_registered/anchor_eligible/baseline_eligible) ✓
- position_grade (unqualified/qualified/good/excellent) ✓
- gps/signal confidence 计数判定 + none 级别 ✓（#0 修复已生效）
- Carry-forward 从 trusted_cell_library MAX(batch_id) 只读 ✓
- BS 级联：lifecycle 从子 Cell 上卷，centroid 中位数，BOOL_OR 资格 ✓
- LAC 级联：lifecycle 从子 BS 上卷，area_km2，BOOL_OR 资格 ✓
- Diff 计算：new/promoted/demoted/removed/eligibility_changed/geometry_changed ✓
- 冻结快照原则 ✓
- step3_run_stats 统计完整 ✓

**维度 C — 数据验证**

- Cell: excellent=2,549 / qualified=1,492 / observing=301 / waiting=1,126（总 5,468）
- BS: qualified=1,054 / observing=641（总 1,695）
- LAC: qualified=12 / observing=2（总 14）
- position_grade: excellent=2,549 / good=1,492 / qualified=301 / unqualified=1,126 ✓
- anchor_eligible: true=2,798 / false=2,670 ✓
- 级联方向正确：Cell→BS→LAC 数量逐级递减 ✓

---

### #7 Step 4 知识补数 — 04_知识补数.md (2026-04-09)

**维度 A — 文档 vs 代码对齐（代码修复）**

| # | 偏差 | 处理 |
|---|------|------|
| A1 | donor JOIN 缺 `anchor_eligible=true` 过滤 | ✅ 已修复：JOIN 条件加 `AND d.anchor_eligible = true` |
| A2 | 碰撞 cell_id 未跳过 GPS 异常检测 | ✅ 已修复：加 `NOT EXISTS collision_id_list` 过滤 |
| A3 | anomaly_type 写死 `'drift'`，文档要求 `'pending'` | ✅ 已修复 |
| A4 | RSRQ/SINR 补数缺失（只补了 RSRP） | ✅ 已修复：enriched_records 新增 rsrq_final/sinr_final + 来源标记 |
| A5 | 气压补数：trusted_cell_library 当前无 pressure_avg 列 | ✅ Step 4 预留 pressure_final/pressure_fill_source_final；pressure_avg 由 Step 5 维护写入（同 center_lon/center_lat 链路），**待 #8 审计时修复** |
| A6 | gps_anomaly_log 字段不全 | ✅ 已修复：新增 lon_raw/lat_raw/donor_center_lon/donor_center_lat/anomaly_threshold_m/anomaly_source/is_collision_id |
| A7 | enriched_records 缺审计字段 | ✅ 已修复：新增 gps_fill_confidence/donor_cell_id/donor_baseline_eligible |
| A8 | step4_run_stats 统计不全 | ✅ 已修复：拆为 rsrp/rsrq/sinr/lac/tech_filled + collision_skip_anomaly_count + remaining_none_* |
| A9 | JOIN 键多 bs_id | ✅ 已修复：去掉 bs_id，保留 tech_norm（防 2G/3G 开放后制式混淆） |

**维度 A — 补数字段完整性**

enriched_records 现在覆盖 7 类补数，每类带来源标记：
- GPS：lon_final/lat_final + gps_fill_source_final + gps_fill_confidence
- RSRP：rsrp_final + rsrp_fill_source_final
- RSRQ：rsrq_final + rsrq_fill_source_final
- SINR：sinr_final + sinr_fill_source_final
- 气压：pressure_final + pressure_fill_source_final（预留，待 Step 5 补 pressure_avg）
- 运营商：operator_final + operator_fill_source_final
- LAC：lac_final + lac_fill_source_final
- 制式：tech_final + tech_fill_source_final

**维度 B — 代码质量**

- pipeline.py 拆分为 pipeline.py (336行) + schema.py (230行)，均在 400 行以内 ✓
- SQL 参数化：阈值通过 %s 传入，f-string 仅用于碰撞过滤子句拼接（无用户输入） ✓
- 幂等性：DROP + CREATE 模式 ✓
- 配置外化：anomaly_threshold 从 antitoxin_params.yaml 读取 ✓

**维度 C — 数据验证**：待重跑 pipeline 后验证（schema 变更需 DROP 重建）

**已知遗留（待 #8 Step 5 审计）**：

- **trusted_cell_library 缺 pressure_avg 列**：Step 5 维护重算链路（与 center_lon/center_lat 同链路）需新增 pressure_avg 聚合并写入。这是 Step 4 气压补数生效的前置条件。
- **重点审计 Step 5 的值来源链路**：确认 trusted_cell_library 中所有聚合值（center_lon/center_lat/rsrp_avg/rsrq_avg/sinr_avg/pressure_avg）都由 Step 5 从 enriched_records 重算，而非仅继承 Step 2/3 的初始值。

---

### #8 Step 5 画像维护 — 05_画像维护.md (2026-04-09)

**维度 A — 文档 vs 代码对齐（代码修复）**

| # | 偏差 | 处理 |
|---|------|------|
| A1 | Cell 质心重算用 lon_raw 而非 lon_final | ✅ 已修复：window.py 用 lon_final/lat_final 重算质心 |
| A2 | rsrq_avg / sinr_avg 未从 enriched_records 重算 | ✅ 已修复：window.py 从 sliding_window 重算全部信号均值 |
| A3 | pressure_avg 缺失（#7 遗留） | ✅ 已修复：window.py 计算 pressure_avg，trusted_cell_library 新增列 |
| A4 | 漂移分类用 p90_radius_m 代替 max_spread_m | ✅ 已修复：cell_maintain.py 从日质心计算 max_spread/net_drift/ratio，publish_cell.py 用 6 类分类含 collision(ratio<0.3)/migration(ratio>=0.7) |
| A5 | gps_anomaly_log schema 冲突 | ✅ 已修复：Step 5 schema.py 不再重新定义 gps_anomaly_log（由 Step 4 schema.py 统一） |
| A6 | baseline_eligible 判定逻辑不符 | ✅ 已修复：publish_cell.py 实现三维度防毒化对比（质心偏移/P90膨胀/设备突增） |
| A7 | is_dynamic 判定偏离 | ✅ 已修复：改为 max_spread > 1500 AND drift_pattern IN (migration, large_coverage) |
| A8 | BS classification 缺 collision_bs 和 multi_centroid | ✅ 已修复：publish_bs_lac.py 实现完整 5 类 |
| A9 | cell/bs centroid_detail 假数据 | ✅ 已改为单簇 primary stub（真聚类待 multi_centroid.py 专项） |
| A10 | collision_id_list 缺 is_collision_id 列 | ✅ 已修复：schema.py 新增列 |
| A11 | trusted_bs_library 缺字段 | ✅ 已修复：新增 is_multi_centroid / window_active_cell_count |
| A12 | trusted_lac_library 缺字段 | ✅ 已修复：新增 boundary_stability_score / active_bs_count / retired_bs_count |
| A13 | 退出管理未实现 | ✅ 已修复：publish_cell.py 基于 active_days_30d 密度分级 + consecutive_inactive_days → dormant/retired |
| A14 | GPS 异常时序判定未实现 | ⚠️ 部分实现：cell_maintain.py 聚合 anomaly_count → migration_suspect/drift；完整时序分析（time_cluster/方向性判定）待数据增长后专项 |
| A15 | 防毒化未实现完整对比 | ✅ 已修复：publish_cell.py 实现质心偏移/P90膨胀/设备突增三维度，阈值配置化 |
| A16 | 文件 928 行超标 | ✅ 已修复：拆为 9 个文件，最大 313 行 |

**维度 A — 结构重组**

Step 5 从 1 个文件 (928行) 拆为 9 个文件：

| 文件 | 行数 | 子步骤 |
|------|------|--------|
| pipeline.py | 137 | 编排器 |
| schema.py | 313 | 所有表 DDL |
| window.py | 215 | 5.0 滑动窗口 + 指标重算 |
| cell_maintain.py | 145 | 5.2 日质心漂移 + GPS 异常聚合 |
| publish_cell.py | 277 | 5.3 Cell 发布（漂移分类/防毒化/退出） |
| collision.py | 117 | 5.1 碰撞两层检测 |
| publish_bs_lac.py | 279 | 5.4 BS + LAC 发布 |
| writers.py | 87 | stats + run_log |
| queries.py | 266 | 前端查询（未改动） |

**维度 A — 配置更新**

antitoxin_params.yaml 新增三组参数：
- `drift_classification`: collision_max_ratio=0.3, migration_min_ratio=0.7, large_coverage_max_spread_m=2200
- `antitoxin_compare`: max_centroid_shift_m=500, max_p90_ratio=2.0, max_dev_ratio=3.0
- `exit`: dormant_inactive_days 按密度分级 (3/7/14 天), retired_after_dormant_days=30

**维度 B — 代码质量**

- 所有文件 ≤ 313 行 ✓
- publish_cell.py / publish_bs_lac.py 全部 %s 参数化 ✓（legacy f-string 已清除）
- 幂等性：DROP + CREATE 模式 ✓
- 配置外化：漂移/防毒化/退出阈值从 yaml 读取 ✓
- 单一职责：每个文件对应一个子步骤 ✓

**维度 C — 数据验证**：待重跑 pipeline 后验证（schema 变更需 DROP 重建）

**已知遗留**：

- **GPS 异常时序完整分析**（A14）：当前只用 anomaly_count 做简单分类；完整的 time_cluster/方向性/连续性分析待数据量增大后专项实现
- **多质心空间聚类**（A9）：当前为单簇 primary stub；真正的 DBSCAN/K-Medoids 聚类待 multi_centroid.py 专项
- **cell_centroid_detail / bs_centroid_detail**：当前为 stub 数据，待多质心专项后替换为真实聚类结果

---

### #2 数据准备 — dev/01_数据准备.md (2026-04-09)

**维度 A — 文档 vs 代码 vs 数据库三方对比**

| # | 发现 | 处理 |
|---|------|------|
| A1 | dataset.yaml 写 beijing_7d，DB 实际为 sample_6lac | ℹ️ 不是冲突：两个独立数据集版本，sample_6lac 先跑验证，beijing_7d 后续放大。通过全局配置切换 |
| A2 | source_prep.py 合并两表到 raw_gps（raw_lac 留空），DB 中两表各有数据 | ℹ️ source_prep.py 是为 beijing_7d 场景重写的（全量不需 LAC 过滤），sample_6lac 数据由旧版代码构建 |
| A3 | parse.py 仍分别读 raw_gps 和 raw_lac | ⚠️ 待清理：未来统一为单表（raw_gps），parse.py 中 raw_lac 相关代码路径应移除 |
| A4 | source_prep.py 选 26 列，DB 实际 27 列 | 低优先级：第 27 列（来源标识）下游未使用 |

**结论**：文档与代码的"不一致"源于两个数据集版本的演进，不是 bug。待清理项是 parse.py 的双表读取代码。

**维度 C — 数据验证**

- raw_gps: 178,945 行，raw_lac: 175,203 行，合计 354,148 = dataset_registry.record_count ✓
- lac_scope 覆盖 6 个 LAC ✓
- 两表各 27 列，结构与 legacy 一致 ✓

---

### #9 服务层 — 06_服务层_运营商数据库与分析服务.md (2026-04-09)

**文档重写**

原文档将结果库查询包装为独立"服务层"概念，引入了不必要的复杂度（省市区汇总、多数据源对比、API 对外服务）。

重写为"结果库浏览与查询"，聚焦实际需求：
- 6.1 基站查询：按 Cell/BS/LAC 搜索 + 详情
- 6.2 覆盖统计：总览卡片 + 运营商对比
- 6.3 LAC 报表：按 LAC 汇总 + CSV 导出

**代码现状**：后端 queries.py (274行) + router service.py (56行)，前端 3 个页面（StationQuery/CoverageAnalysis/StatsReport），API 层完整。代码与重写后文档基本对齐。

enriched_records 浏览、坐标范围查询等列入"待扩展"。

---

### #10 数据集选择与运行管理 — 07_数据集选择与运行管理.md (2026-04-09)

**确认保持现状**。简单的数据集切换管理功能，开发验证阶段使用，正式运行后弱化。

小偏差记录（不影响功能）：
- 文档表名 `dataset_run_log` vs 代码实际 `rebuild5_meta.run_log`
- "Step 1 产出可复用"仅适用于同数据集换参数重跑场景

---

### #11 控制操作 — 09_控制操作_初始化重算与回归.md (2026-04-09)

**文档简化**

原文档定义了四种操作（初始化/局部重算/完整回归/对比验证）和复杂的编排逻辑。简化为最小功能：

- 全量初始化（冷启动）：Step 0-5 + 推荐二轮
- 参数调整后重跑：Step 2-5
- 规则变更后全量回归：Step 1-5

砍掉：局部重算、对比验证、数据分支、定时调度（列入"待扩展"）。

**代码现状**：`POST /api/pipeline/run` 全流程串联、`run_beijing_7d.py` 脚本、`run_log` 记录。`control/` 目录不存在（文档不再要求）。
