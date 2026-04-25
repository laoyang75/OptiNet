# 29 异常数据持续研究 + TA 专题（对话重启后接续）

> **更新日期**：2026-04-23
> **工作目录**：`/Users/yangcongan/cursor/WangYou_Data`
> **数据库**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **本 prompt 用途**：新对话从此处无缝接续"异常 cell 研究 + TA 字段应用研究"两条主线

---

## 0. 任务

本次对话接续**两条主线研究**：

### 主线 A：异常 cell 研究（历史主线，继续）
按需求挑选或轮换可疑 cell，追源到 raw_gps 层，判定污染类型（已知 vs 新类型），**新类型先得证据再讨论规则方向再授权动代码**。

### 主线 B：TA 字段应用研究（2026-04-23 新开）
TA 透传和 ta_verification 已经在 batch 7 落地。用户关心：
1. `ta_verification=xlarge` 的 13,460 个 cell —— 是否确实是**合法大覆盖基站**（郊区/农村）？有没有误判？
2. `ta_verification=large` 的 1,557 个 —— 边界情况
3. 这些大 cell 的实际 p90 是否和 TA 估算距离一致（交叉验证）
4. 反向异常：lib_p90 远大于 ta_dist_p90_m 的 cell（现系统漏判的嫌疑）

---

## 1. 前一轮（2026-04-22 ~ 04-23）已完成

**全库重跑已完成（batch 1-7 全部落地）**，以下关键规则都已生效：

| 规则 | 位置 | 作用 |
|---|---|---|
| `ODS-019` | `etl/parse.py::_parse_cell_infos` | cell_infos age > 300s 陈旧缓存过滤，timeStamp 单位自动识别 |
| `ODS-020/021/022` | `etl/parse.py::_parse_ss1` | ss1 批内锚点 + tech 匹配 + 全 -1 sig 过滤 |
| `ODS-024` | `maintenance/label_engine.py` | 簇最小设备数 ≥ 2 |
| **`ODS-023`（新）** | `etl/clean.py::ODS_RULES` | LTE TDD (earfcn 36000-43589) + TA ≥ 16 置 NULL |
| **`DEDUP-V2.1`（新）** | `profile/pipeline.py`、`maintenance/window.py` | ss1 按 record_id 去重，cell_infos 保持 5min_bucket |
| **方案 B 加权 p50/p90（新）** | `maintenance/window.py::build_cell_radius_stats` | 每点权重 `1/n_dev_core_pts`，累积权重百分位 |
| **`timing_advance / freq_channel / cell_origin` 透传（新）** | 7 张下游表 | 从 etl_cleaned 到 trusted_cell_library 全链路 |
| **trusted_cell_library 加 6 个 TA 字段（新）** | `maintenance/schema.py` | `ta_n_obs / ta_p50 / ta_p90 / ta_dist_p90_m / freq_band / ta_verification` |
| `etl_ss1.max_age_from_anchor_sec` | `config/antitoxin_params.yaml` | 3600 → **10800**（补偿 rid 去重） |

**ODS-020 ss1 锚点放宽到 3 小时**（原 1 小时），补偿 record_id 去重可能损失的合法样本。

---

## 2. 当前数据基线（接续时先跑）

```sql
-- 2.1 全库健康
SELECT 'cell' AS t, COUNT(DISTINCT batch_id) AS b, COUNT(*) AS rows
FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'label_results', NULL, COUNT(*) FROM rebuild5.label_results
UNION ALL SELECT 'centroid_detail', NULL, COUNT(*) FROM rebuild5.cell_centroid_detail;
-- 期望：batch 7 批，cell 数十万到百万级

-- 2.2 TA 字段填充情况
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE ta_n_obs > 0) AS with_ta,
  COUNT(*) FILTER (WHERE ta_verification IS NOT NULL) AS with_verify
FROM rebuild5.trusted_cell_library
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library);
-- 期望：with_ta 约 60% 以上；with_verify 接近 100%

-- 2.3 ta_verification 分布（上次 batch 7 实测）
SELECT ta_verification, freq_band, COUNT(*) AS n
FROM rebuild5.trusted_cell_library
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
GROUP BY ta_verification, freq_band
ORDER BY n DESC;
-- 上次实测结果：
--   ok           FDD   99,336 (29%)  小/中覆盖合理
--   insufficient FDD  179,475 (53%)  TA 样本不足（多是小样本 cell_infos）
--   not_checked  TDD   46,020 (13%)  TDD 跳过校验
--   xlarge       FDD   13,460 (4%)   超大覆盖 >2.3km（郊区/农村，重点研究对象）
--   large        FDD    1,557 (0.5%) 大覆盖 1.5-2.3km
--   not_checked  unk.   1,546 (0.5%)
--   not_applicable      66          multi_centroid/collision 不校验
```

---

## 3. 主线 A 工作方法（异常 cell 追源）

### 3.1 对每个可疑 cell 的追源流程（按顺序）

```sql
-- Step A: trusted_cell_library 看 7 批趋势（业务键 = operator+lac+bs_id+cell_id+tech_norm）
SELECT batch_id, drift_pattern, p50_radius_m::int AS p50, p90_radius_m::int AS p90,
       raw_p90_radius_m::int AS raw_p90,   -- 新：无权 p90 对照
       gps_valid_count, distinct_dev_id, active_days,
       ROUND(center_lon::numeric,5) AS lon, ROUND(center_lat::numeric,5) AS lat,
       is_collision, is_multi_centroid, antitoxin_hit, gps_anomaly_type,
       ta_n_obs, ta_p50, ta_p90, ta_dist_p90_m, freq_band, ta_verification  -- 新：TA 字段
FROM rebuild5.trusted_cell_library WHERE cell_id = <CELL_ID> ORDER BY batch_id;

-- Step B: label_results 看 label_engine 的判定细节
SELECT batch_id, k_raw, k_eff, pair_dist_m::int, pair_overlap_ratio, pair_no_comeback, label
FROM rebuild5.label_results WHERE cell_id = <CELL_ID> ORDER BY batch_id;

-- Step C: cell_centroid_detail 看多簇情况
SELECT batch_id, cluster_id, is_primary, ROUND(center_lon::numeric,5), ROUND(center_lat::numeric,5),
       obs_count, dev_count, share_ratio
FROM rebuild5.cell_centroid_detail WHERE cell_id = <CELL_ID> ORDER BY batch_id, cluster_id;

-- Step D: 按设备拆 batch 7 的 GPS 点分布 + TA 分布
SELECT dev_id, COUNT(*) AS pts,
       COUNT(*) FILTER (WHERE timing_advance IS NOT NULL) AS ta_pts,
       AVG(timing_advance)::int AS avg_ta,
       ROUND(AVG(lon_final)::numeric,4) AS avg_lon, ROUND(AVG(lat_final)::numeric,4) AS avg_lat
FROM rebuild5.cell_sliding_window
WHERE cell_id = <CELL_ID> AND tech_norm=<TECH> AND batch_id = 7
  AND lon_final IS NOT NULL AND gps_valid IS TRUE
GROUP BY dev_id ORDER BY pts DESC;

-- Step E: 某个可疑 dev 的 raw_gps 追源
SELECT r."ts", r."gps_info_type",
       LEFT(r."cell_infos", 500) AS ci_head, LEFT(r."ss1", 300) AS ss1_head
FROM rebuild5.raw_gps_full_backup r
WHERE r."did" = '<DEV_ID>' AND r."cell_infos" LIKE '%<CELL_ID>%'
ORDER BY r."ts" LIMIT 3;
```

### 3.2 已知污染模式识别库

| 现象 | 原因 | 已修规则 |
|---|---|---|
| cell_infos 某对象 age > 300s | 设备启动后历史缓存 | ODS-019 |
| cell_infos timeStamp 是 14+ 位大数 | 纳秒单位 | ODS-019 单位识别 |
| ss1 同 cell_block 里出现远方 cell | SDK 缓存邻区 cell_id | ODS-020/021 |
| 一个 cell 的点绝大多数来自一个设备 (dev_count=1) | 单设备假簇 | ODS-024 |
| cell_id ≤ 0 | 非法 cell | ODS-006 |
| **LTE TDD 基站 TA 固化 16-23** | **中国移动 TDD 占位值（69% cell）** | **ODS-023** |
| **ss1 forward-fill 放大同报文内重复** | **parse 继承机制 + tech 配对** | **DEDUP-V2.1** |
| **单设备大量远点污染 p90** | **GPS 漂移设备（如 GGUC53）** | **方案 B 加权 p50/p90（部分缓解）** |

---

## 4. 主线 B 工作方法（TA 专题）

### 4.1 验证 xlarge cell 的合理性（13,460 个）

**核心研究问题**：这些 cell 真的是郊区/农村大覆盖基站，还是有误判？

```sql
-- 随机抽 20 个 xlarge cell 看它们的分布特征
SELECT cell_id, lac, operator_code,
       ta_p90, ta_dist_p90_m, p90_radius_m::int AS p90,
       raw_p90_radius_m::int AS raw_p90,
       gps_valid_count, distinct_dev_id,
       ROUND(center_lon::numeric, 3) AS lon, ROUND(center_lat::numeric, 3) AS lat
FROM rebuild5.trusted_cell_library
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
  AND ta_verification = 'xlarge'
ORDER BY RANDOM() LIMIT 20;
```

**判定准则**：
- **真大 cell**：`ta_p90` 大（> 30），`p90_radius_m` 也大（> 2km），两者比率接近 1-2（FDD 的 TA 和 p90 吻合）
- **疑似误判**：`ta_p90` 大但 `p90_radius_m` 很小（< 500m）—— 可能是 cell 其实小但 TA 有异常（FDD 偶发 TA 占位？）或统计样本不均

### 4.2 反向异常检测（lib >> ta×78）

历史研究（2026-04-22）发现 53 个 cell 的 `lib_p90 / (ta_p90 × 78) > 5`，其中 26 个已被现系统识别为多质心/碰撞/大覆盖，**还有 27 个标 stable 但 TA 说应该是小 cell** —— 漏判。

```sql
-- 重新跑这个反向异常检测（DEDUP-V2.1 + 加权 p90 后的新结果）
SELECT cell_id, lac, operator_code, drift_pattern,
       ta_verification, ta_p90, ta_dist_p90_m,
       p90_radius_m::int AS p90_weighted,
       raw_p90_radius_m::int AS p90_raw,
       ROUND((p90_radius_m / NULLIF(ta_dist_p90_m, 0))::numeric, 1) AS over_ratio,
       gps_valid_count, distinct_dev_id
FROM rebuild5.trusted_cell_library
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
  AND freq_band = 'fdd' AND ta_n_obs >= 10
  AND ta_dist_p90_m > 0
  AND p90_radius_m > ta_dist_p90_m * 5     -- lib >> TA
ORDER BY over_ratio DESC LIMIT 30;
```

### 4.3 加权 p90 vs raw_p90 对比（方案 B 效果）

```sql
-- 看加权 p90 压了多少 cell
SELECT
  COUNT(*) AS n,
  COUNT(*) FILTER (WHERE raw_p90_radius_m > p90_radius_m * 1.5) AS reduced_30pct,
  COUNT(*) FILTER (WHERE raw_p90_radius_m > p90_radius_m * 3) AS reduced_66pct,
  ROUND(AVG(p90_radius_m)::numeric, 0) AS avg_p90_w,
  ROUND(AVG(raw_p90_radius_m)::numeric, 0) AS avg_p90_raw
FROM rebuild5.cell_radius_stats;
-- 期望 reduced_30pct / reduced_66pct 有一定数量（证明方案 B 生效）
```

### 4.4 已知历史案例重检

```sql
-- cell 19450676（GGUC53 GPS 漂移污染案例）
SELECT batch_id, drift_pattern, p90_radius_m::int AS p90_w, raw_p90_radius_m::int AS p90_raw,
       ta_verification, ta_n_obs, ta_p90, ta_dist_p90_m,
       gps_valid_count, distinct_dev_id
FROM rebuild5.trusted_cell_library
WHERE cell_id = 19450676 AND lac = 4427 AND operator_code = '46000'
ORDER BY batch_id;
-- 期望：方案 B 后 p90_w 从原 6478m 降到 ~4700m；raw_p90 保留 6000+
-- 但由于只有 7 设备 1 个污染，根治需要方案 D，本轮不期望完美解决

-- cell 20752955（最早的示范案例）
SELECT batch_id, drift_pattern, p90_radius_m::int AS p90_w, raw_p90_radius_m::int AS p90_raw,
       ta_verification, ta_n_obs, ta_p90,
       gps_valid_count, distinct_dev_id, active_days
FROM rebuild5.trusted_cell_library
WHERE cell_id = 20752955 AND lac = 4277 AND operator_code = '46000'
ORDER BY batch_id;
-- 期望：DEDUP-V2.1 让样本恢复，p90 < 500m，drift_pattern 不再 insufficient
```

---

## 5. 工作守则（强约束）

- **不动数据库**：只做 `SELECT`；`INSERT/UPDATE/DELETE/DROP` 都必须用户明确授权
- **SQL 必须拆小步**：禁 ≥3 层 CTE、禁复杂自 JOIN、禁一句 SQL 多目的
- **避免全库扫描**：采样用 `random() < 0.003` + `LIMIT`，先拿证据再放大
- **查一条 cell 用完整业务键**（`operator_code, lac, bs_id, cell_id, tech_norm`），不只 `cell_id`（存在跨运营商复用）
- **代码改动前先给用户看方案和影响面**，不擅自 Edit
- **uvicorn 重启**需要明确授权
- **任何"怀疑污染"的结论必须有原始报文证据**（追到 `raw_gps_full_backup` 层 cell_infos / ss1 字段）

---

## 6. 环境上下文

- **原始数据**：`rebuild5.raw_gps_full_backup`（25,510,168 行 pristine，7 天齐全 2025-12-01 ~ 12-07 CST）
- **当前 batch 7 产出完整**：`trusted_cell_library / trusted_bs_library / trusted_lac_library` 都 7 批
- **uvicorn 运行在 127.0.0.1:47231**，前端 vite 在 127.0.0.1:47232
- **MCP PG17 可用**，通过 `mcp__PG17__execute_sql` 查询
- **后端日志**：`/Users/yangcongan/cursor/WangYou_Data/rebuild5/runtime/backend.log`

---

## 7. 可能的下一步研究候选（按模式分类）

### 7.1 TA 专题候选

- **xlarge 合理性验证**：随机 20 cell，逐个看 p90 vs TA 估算是否一致，哪些可能误判
- **lib >> TA×78 的 stable cell**：找那些 TA 说小 cell 但系统判 stable + p90 大的，疑似漏判
- **cell 19450676 + 20752955 的当前状态**：确认 DEDUP-V2.1 + 方案 B 的修复效果
- **LTE TDD cell（46020 个 not_checked）**：有没有办法借助别的信号（如 RSRP 分布）做 coverage 推断？

### 7.2 异常 cell 候选（原 §6 沿用）

```sql
-- "假 stable" 翻转 cell（batch 5/6/7 p90 波动大）
WITH spans AS (
  SELECT cell_id, tech_norm,
         MAX(p90_radius_m) - MIN(p90_radius_m) AS p90_range
  FROM rebuild5.trusted_cell_library
  WHERE batch_id IN (5,6,7) AND p90_radius_m IS NOT NULL
  GROUP BY cell_id, tech_norm
  HAVING COUNT(*) >= 2
)
SELECT * FROM spans ORDER BY p90_range DESC LIMIT 20;
```

- `lifecycle_state = 'excellent'` 但 `p90 > 10km` 的 cell（高等级 + 大半径，矛盾）
- `antitoxin_hit = true` 但 `drift_pattern = 'stable'` 的 cell（反毒命中但稳定）
- BS 层的 `classification != 'normal'` 审查
- Lac 7106/7108/7110/7105 片区集中异常 cell（之前发现，未深挖）

---

## 8. 关键文件索引

| 文件 | 用途 |
|---|---|
| `rebuild5/prompts/28_rerun_full_chain_pipelined.md` | 重跑执行 prompt（本轮已用）|
| `rebuild5/docs/gps研究/cell漂移问题分析.md` | 污染研究主文档（案例 1-4）|
| **`rebuild5/docs/gps研究/11_TA字段应用可行性研究.md`** | **TA 研究主文档 + 实施规范** |
| **`rebuild5/docs/gps研究/12_单设备污染与加权p90方案.md`** | **方案 B 加权 p90 + DEDUP-V2.1 设计记录** |
| `rebuild5/docs/01b_数据源接入_处理规则.md` | ETL 清洗规则总览（含 ODS-023 + DEDUP-V2.1） |
| `rebuild5/docs/05_画像维护.md` | Step 5 维护描述（含方案 B + TA 字段） |
| `rebuild5/docs/03_流式质量评估.md` | Step 3 描述 |
| `rebuild5/backend/app/etl/parse.py` | Step 1 parse（含 ODS-019/020/021/022） |
| `rebuild5/backend/app/etl/clean.py` | Step 1 clean（含 **ODS-023**） |
| `rebuild5/backend/app/profile/pipeline.py` | Step 2（TA 透传） |
| `rebuild5/backend/app/enrichment/pipeline.py` | Step 4（TA 透传） |
| `rebuild5/backend/app/maintenance/window.py` | Step 5 maintenance（含 DEDUP-V2.1 + 方案 B + build_cell_ta_stats） |
| `rebuild5/backend/app/maintenance/publish_cell.py` | trusted_cell_library 写入（含 ta_verification 判定） |
| `rebuild5/backend/app/maintenance/schema.py` | trusted_cell_library 结构（新加 6 TA 字段） |
| `rebuild5/config/antitoxin_params.yaml` | 所有清洗/分簇参数 |

---

## 9. 接续流程（首次接续时先做）

1. 读本 prompt 全部
2. 读 `11_TA字段应用可行性研究.md` §6（实施规范）+ `12_单设备污染与加权p90方案.md`
3. 跑 §2 三个基线 SQL 验证数据就绪
4. 向用户打招呼："接续研究，请指定研究方向：
   - **TA 专题**（xlarge 验证 / 反向异常检测 / 已知案例重检）
   - **异常 cell**（§7.2 候选 / 指定 cell_id）
   - **其他新方向**"

---

## 10. 不在本 prompt 范围

- 启动新一轮重跑（由 prompt 28 处理）
- 前端（Vue）功能开发
- 数据库备份恢复
- 方案 D 设备一致性过滤（如需引入，要单独规划）
- 5G NR cell 的 TA 处理（等 4G 走顺再扩展）
