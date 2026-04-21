# 继续工作 Prompt：Step5 MAD 基础质心修正与重跑

你在仓库：

`/Users/yangcongan/cursor/WangYou_Data`

继续 `rebuild5` 的 GPS 基础质心修正后续工作。

## 1. 当前任务背景

当前已经完成的工作：

1. 已评估并确认 `rebuild5/docs/gps研究/06_k_mad参数选择与效果对比.md` 的研究方向可继续推进。
2. 已根据该研究把 **Step5 的基础质心算法** 从旧的 `core_position_filter` 路线，切到 **MAD 过滤路线**。
3. 本次修改**不要求 Step3 重跑**；Step3 只要求测试兼容性通过。
4. 已新增 **Step5-only 重跑脚本**，用于在保留 Step3/4 结果的前提下，仅重跑 Step5 发布结果。

## 2. 已完成的代码改动

当前工作区内已经改过这些文件：

- `rebuild5/backend/app/profile/logic.py`
  - 新增 `load_core_mad_filter_params()`
- `rebuild5/config/antitoxin_params.yaml`
  - 新增：
    - `core_mad_filter.k_mad`
    - `core_mad_filter.min_pts`
    - `postgis_centroid.candidate_min_raw_p90_m`
- `rebuild5/backend/app/maintenance/window.py`
  - `build_cell_core_gps_stats()` 改为 MAD 路线
  - `build_cell_radius_stats()` 改为基于 MAD 结果计算 `p50/p90/raw_p90/core_outlier_ratio`
- `rebuild5/backend/app/maintenance/pipeline.py`
  - 增加 Step5 中间表清理
  - 新增 `run_maintenance_pipeline_for_batch(batch_id=...)`
- `rebuild5/backend/app/maintenance/publish_bs_lac.py`
  - `candidate_min_raw_p90_m` 接入配置读取与 SQL
- `rebuild5/scripts/rerun_step5_only.py`
  - 新增，仅重跑 Step5 的脚本
- `rebuild5/tests/test_pipeline_version_guards.py`
  - 增加 Step5 MAD 路线相关测试
- `rebuild5/tests/test_publish_bs_lac.py`
  - 增加 `candidate_min_raw_p90_m` 断言

## 3. 已完成的验证

这些测试已经通过：

```bash
pytest rebuild5/tests/test_pipeline_version_guards.py \
       rebuild5/tests/test_publish_bs_lac.py \
       rebuild5/tests/test_profile_logic.py \
       rebuild5/tests/test_maintenance_queries.py \
       rebuild5/tests/test_publish_cell.py \
       rebuild5/tests/test_enrichment_queries.py
```

结果：

- `36 passed`

说明：

- Step3 兼容性测试已通过
- Step5 新逻辑相关测试已通过

## 4. 数据库与重跑现状

正式库：

- `ip_loc2`

Step5-only 重跑脚本：

```bash
python3 rebuild5/scripts/rerun_step5_only.py
```

这轮 Step5-only 重跑已经在正式库跑完到 `batch7`。

最新 `batch7` 结果为：

- `published_cell_count = 410373`
- `published_bs_count = 196401`
- `published_lac_count = 16803`
- `multi_centroid_cell_count = 6585`
- `dynamic_cell_count = 2755`
- `anomaly_bs_count = 1061`

日志文件：

- `rebuild5/runtime/logs/rebuild5_step5_rerun_20260417.log`

## 5. 当前用户要求

用户明确说：

- 上下文太长，要重开会话
- **仍然需要重新跑数据**

因此你在新会话里，不要只做总结，而要准备继续执行重跑工作。

## 6. 新会话中的建议起手动作

先做这几件事：

1. 读取本文件
2. 检查当前工作区改动是否仍在
3. 检查正式库 `ip_loc2` 当前 `step5_run_stats` 是否仍为最新一轮结果
4. 根据用户最新要求，决定是：
   - 继续沿用当前代码直接重跑
   - 还是先做额外验证后再跑

## 7. 如果用户要求“重新跑数据”，优先使用的入口

### 方案 A：只重跑 Step5

如果用户只需要基于当前 Step3/4 结果重新生成基础质心和发布结果，优先用：

```bash
python3 rebuild5/scripts/rerun_step5_only.py
```

### 方案 B：如果用户要求全链重跑

若用户明确要求从更前面的步骤重跑，再根据当前需求决定是否：

- 跑 `run_daily_increment_batch_loop.py`
- 或跑全链脚本

但当前上下文里，**Step3 不要求重跑**，因此默认不应主动扩大重跑范围。

## 8. 重要边界

1. 这次工作的主目标是：
   - 让新基础质心算法生效
   - 生成新的 Step5 发布结果

2. 不要默认改动 Step3 逻辑

3. 如果需要再次重跑正式库，优先从 Step5-only 入口开始

4. 继续工作前，建议先核对这些文件是否仍然保持本次改动：

- `rebuild5/backend/app/maintenance/window.py`
- `rebuild5/backend/app/maintenance/pipeline.py`
- `rebuild5/backend/app/maintenance/publish_bs_lac.py`
- `rebuild5/backend/app/profile/logic.py`
- `rebuild5/config/antitoxin_params.yaml`
- `rebuild5/scripts/rerun_step5_only.py`

## 9. 如果需要再次向用户汇报

优先汇报：

1. 当前库里最新 batch 是否已经是新算法结果
2. 是否准备开始新一轮重跑
3. 准备用哪个脚本重跑
4. 是否只重跑 Step5，还是用户明确要求更大范围
