# loop_optim / 04 UI 跟进报告

## 0. TL;DR

- C 块(ODS 规则 hit count):后端 endpoint + 前端页面 `RuleStats.vue` 已落地;hit count 数据来源 = 选项 A,落 `rb5_meta.etl_rule_stats` reference table。
- D 块(device-weighted p90):后端 endpoint + `CellMaintain` "加权 P90" tab 已落地。
- E 块(TA 筛选):4 个筛选控件已加,client-side 过滤当前页内存数据。
- A/B 验证 OK:Claude 的 `GovernanceOverview.vue` 版本条和 drift 8 类对齐保留;仅补了 build 所需的未使用 import 清理。
- commit SHA / push 状态:见最终回复。

## 1. C 块实现细节

- schema 决策:选项 A,新增 `rb5_meta.etl_rule_stats(batch_id, rule_code, rule_desc, hit_count, total_rows, recorded_at)`,当前 Citus 已确认为 reference table (`partmethod='n'`)。
- ETL 保存入口:`etl.pipeline._save_rule_stats()` 在 Step 1 完成后写入 ODS-019/020/021/022/023b/024b 六类统计;真实 hit count 需要下次 Step 1 重跑 backfill。
- endpoint:`GET /api/etl/rule-stats?batch_id=<n>&rule_code=<str>`。
- 前端:`frontend/design/src/views/etl/RuleStats.vue`,路由 `/etl/rule-stats`,导航位于 Step 1 菜单。

## 2. D 块实现细节

- 后端算法依据:`maintenance/window.py::build_cell_radius_stats()` 已把 `p90_radius_m` 作为设备加权 p90 写入维护链路。
- endpoint:`GET /api/maintenance/device-weighted-p90?cell_id=<id>`。
- endpoint 展示层从当前 TCL 质心 + `cell_sliding_window` GPS 点计算无权 P90、设备归一权重 P90、top 5 远距设备贡献。
- 验证样例:`cell_id=47261081712` 返回 `point_count=7672`, `top_polluting_devices=5`,无权 P90 约 346m,加权 P90 约 258m。

## 3. E 块实现细节

- `CellMaintain.vue` 新增 TA 估距区间、freq_band、ta_verification、timing_advance 三态 4 类筛选控件。
- 筛选逻辑为 client-side,作用于当前页已加载 rows,筛选区显示当前页命中数。
- 详情面板新增 tab:概览 / 加权 P90;加权 P90 tab 懒加载 endpoint,展示双 bar、delta、top 5 设备列表。

## 4. 前端构建验证

- `python3 -m py_compile` 覆盖本阶段后端修改文件:PASS。
- `cd rebuild5/frontend/design && npm run build`:PASS。
- `get_rule_stats_payload()` 返回 6 条 ODS scaffold rows。

## 5. 已知限制

- `rb5_meta.etl_rule_stats` 已建表,但历史批次真实 hit count 要等 user 触发 Step 1 reset/rerun 后写入。
- D 块 top 设备解释层使用当前 `cell_sliding_window` 的 GPS 点重算展示数据;持久化的生产 p90 仍以 Step 5 已有 `p90_radius_m` 为准。
