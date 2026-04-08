# rebuild4 续接修复 Prompt

## 你的任务

继续修复 rebuild4 流式治理工作台的数据质量和页面显示问题。框架层（后端 API、前端 14 页面、数据库 schema）已完成，当前需要从 Cell 数据维度开始，逐页修复数据真实性。

---

## 当前系统状态

### 已运行的服务
- **后端**: `rebuild4/backend/`, FastAPI, 端口 47131, 入口 `app/main.py`
- **前端**: `rebuild4/frontend/`, Vue 3 + Vite, 端口 47132
- **rebuild3 参考**: 前端 47122, 后端 47121（rebuild3 schema 数据）

### 数据库连接
- Host: 192.168.200.217, Port: 5433, User: postgres, Password: 123456, DB: ip_loc2
- **rebuild4** schema: 业务表（fact_standardized, 四分流, obj_cell/bs/lac, baseline_*）
- **rebuild4_meta** schema: 控制层（run, batch, current_pointer, batch_snapshot, 治理快照等）
- **rebuild2** schema: 参考数据源（dim_bs_refined, dim_cell_refined, _sample_* 画像表, _research_* 碰撞/分类表）
- **rebuild2_meta** schema: 治理元数据（field_audit, target_field, ods_clean_rule 等）

### 关键数据现状
- `rebuild4.fact_standardized`: 82,205,035 条（来自 l0_gps 38M + l0_lac 43M）
- 四分流守恒: 67,963,244 + 9,493,333 + 1,461 + 4,746,997 = 82,205,035
- `obj_cell`: 1,286,825 | `obj_bs`: 228,536 | `obj_lac`: 13,480
- 2 个 run: RUN-INIT-001 (full_initialization) + RUN-ROLL-001 (rolling, 3 batch)
- current_pointer → RUN-ROLL-001 / BATCH-ROLL-003 / g3_handoff
- trusted_loss: 43,771,306 / 31.27% / 11,350,552

### 已知数据质量问题
1. **obj_cell 字段空值多**: 短 LAC 对象（10003 等）没有匹配到 rebuild2 的 dim_cell_refined（rebuild2 用 6 位 LAC 如 102401）
2. **健康状态不够真实**: 很多 BS 的 health_state 来自随机分配而非真实碰撞/迁移计算
3. **GPS 质量/信号质量**: gps_original_ratio/signal_original_ratio 部分是随机生成的
4. **初始化各步骤缺少 input_count/output_count**: step_log 只有名称和 status
5. **observation_workspace_snapshot 数据不够丰富**: 三阶段进度值可能不真实
6. **位置数据**: 4,552/13,480 LAC 有位置，其余缺失

### 后端关键文件
- `backend/app/main.py` — FastAPI 入口
- `backend/app/core/database.py` — PG17 连接
- `backend/app/core/envelope.py` — six-field envelope
- `backend/app/core/context.py` — current_pointer / contract_version
- `backend/app/routers/flow.py` — flow-overview, flow-snapshot
- `backend/app/routers/runs.py` — runs/current, batches
- `backend/app/routers/objects.py` — objects list/summary/detail
- `backend/app/routers/workspaces.py` — observation/anomaly workspace
- `backend/app/routers/baseline.py` — baseline current/diff/history
- `backend/app/routers/profiles.py` — LAC/BS/Cell profiles
- `backend/app/routers/initialization.py` — initialization
- `backend/app/routers/governance.py` — 12 组 governance endpoints
- `backend/app/routers/compare.py` — compare fallback

### 前端关键文件
- `frontend/src/router.ts` — 14 路由
- `frontend/src/App.vue` — 侧边栏导航
- `frontend/src/lib/api.ts` — API 调用层
- `frontend/src/components/` — 10 个共享组件
- `frontend/src/pages/` — 14 个页面组件

### rebuild2 关键参考表
- `dim_cell_refined` (573,561): cell_id, bs_id, gps_center, gps_anomaly, dist_to_bs_m, active_days
- `dim_bs_refined` (193,036): bs_id, gps_center, gps_quality, gps_p50/p90, cell_count, max_active_days
- `dim_lac_trusted` (1,057): record_count, avg_daily_records, active_days, cv
- `_sample_bs_profile_summary` (1,096): 完整 BS 画像（GPS/信号质量/分类/面积）
- `_sample_cell_profile_summary` (3,751): 完整 Cell 画像
- `_research_bs_classification_v2` (9,591): BS 分类（normal_spread/single_large/dynamic_bs）
- `_research_collision_detail` (121,852): 碰撞详情
- `_research_multi_detail` (1,324,609): 多质心碰撞详情
- `dim_admin_area` (2,874): 行政区划（province/city/district + center_lon/lat）
- `lac_stats_summary` (11,475): LAC 中位数坐标
- `dwd_fact_enriched` (30,082,381): 已增强的事实表

### 冻结文档
- 冻结包: `rebuild4/docs/03_final/` 6 个文件, 版本 v7
- UI 参考: rebuild3 前端 `rebuild3/frontend/src/pages/*.vue`

---

## 修复策略

按自底向上顺序修复:
1. **Cell 数据维度** — 基于 rebuild2 的 dim_cell_refined + dwd_fact_enriched 重新计算 Cell 对象的核心指标
2. **初始化 11 步** — 让每一步有真实的 input/output 计数
3. **四分流评估** — 基于真实的规则逻辑重新评估分流参数
4. **逐页面比对 rebuild3** — 确保每个页面的数据和 UI 与 rebuild3 UI_v2 结构一致

---

## 启动后端/前端

```bash
# 后端
cd /Users/yangcongan/cursor/WangYou_Data/rebuild4/backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 47131 --reload

# 前端
cd /Users/yangcongan/cursor/WangYou_Data/rebuild4/frontend
npx vite --host 0.0.0.0 --port 47132
```
