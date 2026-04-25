# 28 全链路重跑（Step 1-5 pipelined）

> **数据库**：`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`
> **仓库**：`/Users/yangcongan/cursor/WangYou_Data`
> **脚本**：`rebuild5/scripts/run_step1_step25_pipelined_temp.py`
>
> **本轮生效的关键规则**（冒烟 §1.2 会校验是否落地）：
> - **ODS-019**：cell_infos 陈旧缓存过滤，timeStamp 单位**自动识别**（≤13 位毫秒 / ≥14 位纳秒，实测约 9% 设备用纳秒）
> - **ODS-020/021/022**：ss1 批内锚点陈旧过滤 + tech 匹配 INNER JOIN + 全 -1 sig 过滤
> - **`ODS-023`**（2026-04-23 新增）：LTE TDD 占位 TA 剔除 —— `cell_origin='cell_infos' AND tech_norm='4G' AND freq_channel BETWEEN 36000 AND 43589 AND timing_advance >= 16` 置 NULL。基于发现中国移动 TDD 基站约 69% TA 固化在 16-23 占位值（非距离信号），剔除占位后 TDD 有效 TA 保留约 23%。规则详见 `rebuild5/docs/gps研究/11_TA字段应用可行性研究.md`。
> - **ODS-024**：簇至少需要 `min_cluster_dev_count=2` 个不同设备（防单设备跨天刷成假簇）
> - **DBSCAN 参数调整**：`dbscan_eps_m` **250 → 500**（原 250m 对城市 cell 偏严，典型亦庄 7 点 2.5km 分散聚不成簇案例表明放宽更合理）
> - **`DEDUP-V2.1`**（2026-04-23 修订 V2）：Step 2 `_profile_gps_day_dedup` 和 Step 5 `cell_core_gps_day_dedup` 按 `cell_origin` 分两套去重键：`cell_infos` 用 `(cell, dev, 5min_bucket)`；**`ss1` 用 `(cell, dev, record_id)`**（每 raw_gps 报文 1 点，消除 forward-fill 冗余）。配套 `etl_ss1.max_age_from_anchor_sec: 3600→10800`。修复 cell 20752955 类"单远点污染 + 样本稀释"，同时压 ss1 冗余约 50%。规则详见 `rebuild5/docs/01b_数据源接入_处理规则.md § 下游去重策略`。
> - **方案 B 加权 p90**（2026-04-23 新增）：`build_cell_radius_stats` 产出的 p50/p90 改为**设备逆频加权**（每设备总权重归一化为 1，防单设备刷屏主导）。cell 19450676 实测 p90 从 6478m 降到 4718m（-30%）。`raw_p90_radius_m` 保留无权口径对照。
> - **TA 透传 + cell_origin 透传**（2026-04-23 新增）：`timing_advance / freq_channel / cell_origin` 3 字段从 `etl_cleaned` 透传到 7 张下游表，最终 `trusted_cell_library` 新增 6 个 TA 字段：`ta_n_obs / ta_p50 / ta_p90 / ta_dist_p90_m / freq_band / ta_verification`。`ta_verification ∈ {ok, large, xlarge, not_applicable, not_checked, insufficient}`，用于识别合法大覆盖 cell（`xlarge` = TA_p90 > 30 即 >2.3km 郊区/农村）。

---

## 0. 任务

完成 Step 1-5 全链路重跑 `dataset_key = beijing_7d`（日期范围 **2025-12-01 ~ 2025-12-07**），最终产出：

- `rebuild5.trusted_cell_library`、`rebuild5.trusted_bs_library`、`rebuild5.trusted_lac_library` 各 7 批（`batch_id = 1..7`）
- `rebuild5_meta.step1_run_stats / step5_run_stats` 有完整记录

### 执行模式（pipelined）

- **Step 1（producer）**：day 1 → day 7 **顺序跑**
- **Step 2-5（consumer）**：流水线跟进；每跑 day N 前检查 day N 的 Step 1 已完成，未完成则等
- **脚本自带该流水线语义**，`--skip-prepare` 表示不调 `prepare_current_dataset()`，数据源直接取挂载到 `rebuild5.raw_gps_full_backup` 的内容

### 执行顺序

1. **§1 冒烟** — 代码、配置、索引、源头数据健康检查
2. **§2 启动检测 + 环境重置** — 确认 DB 干净、无外部写入、跑 reset 脚本
3. **§3 测试集 7 天预跑 + 性能评估** — 用约 150 万行样本完整跑 7 批，验证流程通 + 测耗时 + 最多 2 轮优化
4. **§4 环境恢复 + 正式全量重跑** — 清测试挂载，恢复原始数据源，跑正式 7 天
5. **§5 正式验收** — 批次齐、垃圾 cell 为 0、drift/classification 分布合理
6. **§6 汇报**

### 自主修复授权（2026-04-21 扩展）

为了减少"每次遇到代码问题就停下问用户"的低效循环，以下类型的修复**允许自主进行**（改完必须在 §6 汇报里列明"改了什么+原因+影响面"）：

| 可以自主修 | 示例 |
|---|---|
| SQL 类型溢出 / 语法错误 | `::bigint` 被异常大值溢出 → 换 `::numeric` 或加长度兜底 |
| Python 解析异常 / 空值错误 | 未 guard 的 NoneType / KeyError |
| 重复 `WHERE` 条件、缺失索引导致单 SQL > 30 分钟 | 按需补索引 / `ANALYZE` / 改 CTE 为 MATERIALIZED |
| 明显的注释错误、类型注解错位 | 直接修 |
| 由于数据异常（非代码）产生的兜底条件 | 例如加 `length(x) > 19 → KEEP` 这种保守兜底 |
| `pg_terminate_backend` 自己当前会话遗留的挂起查询 | 不影响其他会话即可 |
| `cell_origin` / `timing_advance` / `freq_channel` 透传链路中漏 column / 漏 ALTER / SELECT 少选 | 直接补齐，确保 7 张下游表 + trusted_cell_library 字段一致 |
| `DEDUP-V2.1` SQL 里 ss1 rid 去重分支 / 5min_bucket 表达式小错 | 补括号 / 类型转换，保持分支语义 |
| 加权 p50/p90 窗口函数语法错 | 补 `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` 之类 |
| `build_cell_ta_stats` 聚合函数兼容问题 | `MODE()` / `PERCENTILE_CONT()` 的 FILTER 语法，按 PG 版本调整 |
| pipeline 状态不一致（如 `etl_parsed` 陈旧于 `etl_cleaned`）| 主 pipeline step1 必须 parse+clean+fill 顺序跑完，不允许单独跳 parse |
| `raw_gps_full_backup` 缺失但 `raw_gps` 健康（≥ 25M 行）| RENAME `raw_gps` → `raw_gps_full_backup`（详见 §1.4 的状态分支表；是上轮重跑收尾 RENAME 回 raw_gps 的已知副作用）|
| `raw_gps_full_backup_prod_hold` 残留（上次测试集挂载未收回）| RENAME `_prod_hold` → `raw_gps_full_backup`（详见 §1.4）|

**必须先问用户才能改**：

| 需要授权 | 为什么 |
|---|---|
| 调阈值（如 `max_age_sec`、`min_cluster_dev_count`、`dbscan_eps_m`、`max_anomaly_ratio`、`max_anomaly_count`）| 会改变判定结果，影响研究结论 |
| 改 `DEDUP-V2` 的桶粒度 / 去重键（如 5min → 1min / 加/减维度）| 改变样本密度 / 口径，影响 p50/p90 判定 |
| 删除或重新定义已有 ODS 规则 / DEDUP-V2 规则 | 改变业务语义 |
| 修改 `trusted_*_library` / `label_results` 等产出表的 schema | 下游兼容性 |
| `DELETE` / `UPDATE` 任何持久化表的数据 | 不可逆 |
| 跳过 §5 验收里任何"硬要求"条目 | 质量门槛 |
| 修改 `raw_gps_full_backup` 内容 | 原始数据保护 |

**自主修复的流程**：

1. 记录"改之前的报错/异常行" + 你的诊断结论
2. 最小改动（只改必要处，不顺手重构其他代码）
3. 语法校验（`python3 -c "import ast; ast.parse(...)"`）
4. 只跑一次最小验证（例如模拟异常输入看新 SQL 不报错）
5. 继续执行原流程（重跑 / 验证）
6. 汇报里加一条：文件 + 行号 + 改动 diff 概述 + 预计影响面

**禁止**：任何"授权清单"外的修改都要先停下问用户。

### 禁区（仍然禁止，任何情况不可突破）

- **不能损坏 `rebuild5.raw_gps_full_backup` 的内容**；允许 RENAME 暂存，但最终必须恢复（§4.1 硬校验）
- **单条 SQL 单任务**，禁 ≥ 3 层 CTE / 复杂自 JOIN
- **不追日志文件**；进度监测只用本文档给的短 SQL
- **卡住 > 30 分钟先停下汇报**，不自行 `pg_terminate_backend` 其他会话 / `kill` 重跑主进程
- **数据库写操作**（`DELETE/UPDATE/TRUNCATE/DROP` 到非临时表）全部需要用户授权，**自主修复授权不涵盖 DB 写**

---

## 1. 冒烟（≤ 5 分钟，任一失败停下）

### 1.1 Python 语法

```bash
cd /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend
python3 -c "
import ast
for f in ['app/etl/clean.py','app/etl/parse.py','app/etl/pipeline.py',
         'app/profile/pipeline.py','app/evaluation/pipeline.py',
         'app/enrichment/pipeline.py','app/enrichment/schema.py',
         'app/maintenance/pipeline.py']:
    ast.parse(open(f).read())
print('OK')
"
```

### 1.2 ODS 清洗规则到位

```bash
# 主清洗规则（ODS-001 ~ ODS-018 + 005a / 006a / 006b）
python3 -c "
from app.etl.clean import ODS_RULES
ids = {r['id'] for r in ODS_RULES}
assert {'ODS-005a','ODS-006a','ODS-006b'}.issubset(ids)
print('ODS clean rules ok:', sorted(ids))
"

# ODS-019 (cell_infos 陈旧缓存过滤) 配置 + SQL 注释
python3 -c "
from app.etl.parse import _load_cell_infos_cfg
cfg = _load_cell_infos_cfg()
assert cfg.get('max_age_sec', 0) >= 1, f'max_age_sec 异常: {cfg}'
print('ODS-019 config ok:', cfg)
"
grep -n 'ODS-019' app/etl/parse.py               # WHERE 子句应带该注释
grep -n '^etl_cell_infos:' ../config/antitoxin_params.yaml
# ODS-019 timeStamp 单位自动识别（2025-04-21 新增）：长度 <=13 按毫秒 / 10^3，>=14 按纳秒 / 10^9
grep -n 'ELSE.*timeStamp.*1000000000' app/etl/parse.py    # 应能匹配到新规则

# ODS-024 簇最小设备数（2025-04-21 新增，防单设备跨天伪簇）
python3 -c "
from app.profile.logic import load_multi_centroid_v2_params
cfg = load_multi_centroid_v2_params()
assert cfg.get('min_cluster_dev_count', 0) >= 1, f'min_cluster_dev_count 异常: {cfg}'
print('ODS-024 config ok: min_cluster_dev_count =', cfg['min_cluster_dev_count'])
"
grep -n 'min_cluster_dev_count' app/maintenance/label_engine.py   # k_eff / valid_clusters 都应引用

# ODS-020/021/022 (ss1 解析清洗) 配置 + SQL 注释
python3 -c "
from app.etl.parse import _load_ss1_cfg
cfg = _load_ss1_cfg()
assert cfg.get('max_age_from_anchor_sec', 0) >= 1, f'ss1 max_age 异常: {cfg}'
assert cfg.get('require_sig_cell_tech_match') is True, 'ss1 tech 匹配应开启'
assert cfg.get('drop_sig_all_minus1') is True, 'ss1 全 -1 过滤应开启'
print('ODS-020/021/022 config ok:', cfg)
"
grep -n 'ODS-020' app/etl/parse.py               # ts_sec 注释
grep -n 'ODS-021' app/etl/parse.py               # INNER JOIN 注释
grep -n 'ODS-022' app/etl/parse.py               # sig 全 -1 过滤注释
grep -n '^etl_ss1:' ../config/antitoxin_params.yaml

# DEDUP-V2（2026-04-22 新增）：新去重键 + cell_origin 透传
# 1. Step 2 / Step 5 的 DISTINCT ON 都包含 cell_origin + 5min_bucket
grep -n 'cell_origin' app/profile/pipeline.py | head -5        # _profile_path_b_records / dedup
grep -n '5 \* INTERVAL' app/profile/pipeline.py                # 5min 桶表达式
grep -n 'cell_origin' app/maintenance/window.py | head -5      # cell_sliding_window INSERT + dedup
grep -n '5 \* INTERVAL' app/maintenance/window.py              # 5min 桶表达式
# 2. 持久表 schema 都包含 cell_origin 列
grep -n 'cell_origin TEXT' app/enrichment/schema.py            # enriched_records + snapshot_seed_records
grep -n 'cell_origin TEXT' app/maintenance/schema.py           # cell_sliding_window
grep -n 'cell_origin TEXT' app/profile/pipeline.py             # candidate_seed_history

# DEDUP-V2.1（2026-04-23 新增）：ss1 按 record_id 去重 + 加权 p90
# 1. ss1 专用的 rid 去重分支
grep -n "cell_origin = 'ss1'" app/maintenance/window.py        # 应能 grep 到 CASE WHEN ss1 THEN 'rid:'
grep -n "'rid:'" app/maintenance/window.py                     # 应 grep 到 record_id 前缀
# 2. 加权 p50/p90
grep -n '方案 B' app/maintenance/window.py                      # build_cell_radius_stats 注释
grep -n 'w_core' app/maintenance/window.py                      # 逆频权重计算
grep -n 'cum_w >=' app/maintenance/window.py                    # 累积权重判定
# 3. ODS-020 阈值放到 3h
grep -n 'max_age_from_anchor_sec: 10800' ../config/antitoxin_params.yaml

# ODS-023 & TA 透传（2026-04-23 新增）
# 1. clean.py 里的 ODS-023 规则
grep -n 'ODS-023' app/etl/clean.py                             # 应能 grep 到规则
grep -n '36000 AND 43589' app/etl/clean.py                     # TDD earfcn 范围
# 2. timing_advance 列在所有下游表
grep -n 'timing_advance INTEGER' app/enrichment/schema.py
grep -n 'timing_advance INTEGER' app/maintenance/schema.py
grep -n 'timing_advance INTEGER' app/profile/pipeline.py
# 3. TA 统计聚合和 trusted_cell_library 字段
grep -n 'cell_ta_stats' app/maintenance/window.py              # 新 build_cell_ta_stats 函数
grep -n 'build_cell_ta_stats' app/maintenance/pipeline.py      # 被 pipeline 调用
grep -n 'ta_verification' app/maintenance/publish_cell.py      # INSERT 带上
grep -n 'ta_n_obs BIGINT' app/maintenance/schema.py            # trusted_cell_library 字段
```

**可调参数提示**：`etl_ss1.max_age_from_anchor_sec` 默认 3600（1 小时）。如需放宽到 3 小时，直接改 yaml 为 10800 即可，**不要改代码**。

### 1.3 下游 SQL 优化到位（fix4 三处）

```bash
grep -n 'idx_enriched_batch_record_cell' app/enrichment/schema.py
grep -n 'idx_csh_join_batch' app/enrichment/pipeline.py
grep -n 'new_snapshot_cells AS MATERIALIZED' app/enrichment/pipeline.py
# 三行都应 grep 到
```

### 1.4 源头数据规模（MCP PG17）

**先做命名状态兜底修复**（2026-04-22 新增）：上一轮重跑收尾的脚本会把 `raw_gps_full_backup` RENAME 回 `raw_gps`，导致本轮启动时 `raw_gps_full_backup` 缺失。这是**预期的可自动修复状态**，无需停下问用户：

```sql
-- 探测当前状态
SELECT to_regclass('rebuild5.raw_gps') AS raw_gps_exists,
       to_regclass('rebuild5.raw_gps_full_backup') AS backup_exists,
       to_regclass('rebuild5.raw_gps_full_backup_prod_hold') AS prod_hold_exists;
```

按下表自动分支（授权范围内的状态修复）：

| 当前状态 | 动作 |
|---|---|
| `backup_exists = NULL` AND `raw_gps ≥ 25M 行` AND `prod_hold = NULL` | **自动 RENAME**：`ALTER TABLE rebuild5.raw_gps RENAME TO raw_gps_full_backup`，然后继续 §1.4 的规模校验。这属于"自主修复授权"范围，无需问用户。 |
| `backup_exists ≠ NULL` | 状态正常，跳过修复直接做下面的规模校验 |
| `prod_hold_exists ≠ NULL` AND `backup_exists = NULL` | 上次测试集挂载没收回来，先 `ALTER TABLE ..._prod_hold RENAME TO raw_gps_full_backup` 复位（同属自主修复） |
| `raw_gps_exists ≠ NULL` AND `backup_exists ≠ NULL` | **异常双份状态**，停下汇报（避免误删活跃表）|
| `raw_gps_exists = NULL` AND `backup_exists = NULL` | 无源头数据，停下汇报 |

自动 RENAME 前必须先跑探测 + 验证 `raw_gps ≥ 25,000,000`，跑完 RENAME 后在 §6 汇报里记一笔"执行了 backup 复名修复"。

**规模校验**：

```sql
SELECT COUNT(*) AS rows FROM rebuild5.raw_gps_full_backup;
-- 应 >= 25,000,000，低于此值说明源头数据异常，停下汇报
```

```sql
-- 北京时间语义：12-01 ~ 12-07 共 7 天
SELECT ts::date AS day, COUNT(*) AS rows
FROM rebuild5.raw_gps_full_backup
WHERE ts >= '2025-12-01' AND ts < '2025-12-08'
GROUP BY ts::date ORDER BY day;
-- 应返回 7 行；每天 340-390 万；任一天 < 200 万停下汇报
```

---

## 2. 启动检测 + 环境重置

### 2.0 启动检测（任一不过停下）

```sql
-- 无外部活跃写入（防止重跑过程中被第三方会话干扰）
SELECT pid, client_addr, state,
       LEFT(regexp_replace(query,'\s+',' ','g'), 150) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active';
-- 若有 UPDATE / INSERT / TRUNCATE / DROP / ALTER 出现，停下汇报

-- 样例挂载保护位必须为空；非空说明上次测试集未恢复干净
-- （§1.4 的自动修复分支会处理 "backup 缺失+prod_hold 残留" 情形；到这里仍非空说明两份都在，停下）
SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold');
-- 应返回 NULL；非 NULL 停下汇报

-- full_backup 必须就位（§1.4 修复后应存在）
SELECT to_regclass('rebuild5.raw_gps_full_backup');
-- 应返回 rebuild5.raw_gps_full_backup；NULL 说明 §1.4 没跑到或修复失败，停下汇报
```

### 2.1 环境重置

```bash
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -f /Users/yangcongan/cursor/WangYou_Data/rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

确认清理生效：

```sql
SELECT 'trusted_cell' AS t, COUNT(*) FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'trusted_bs', COUNT(*) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'trusted_lac', COUNT(*) FROM rebuild5.trusted_lac_library
UNION ALL SELECT 'step1_stats', COUNT(*) FROM rebuild5_meta.step1_run_stats
UNION ALL SELECT 'step5_stats', COUNT(*) FROM rebuild5_meta.step5_run_stats
UNION ALL SELECT 'cell_sliding_window', COUNT(*) FROM rebuild5.cell_sliding_window
UNION ALL SELECT 'cell_centroid_detail', COUNT(*) FROM rebuild5.cell_centroid_detail
UNION ALL SELECT 'raw_gps_full_backup', COUNT(*) FROM rebuild5.raw_gps_full_backup;
-- 前 7 行应全为 0；raw_gps_full_backup 必须 >= 25,000,000
```

---

## 3. 测试集 7 天预跑 + 性能评估

**目的**：用小数据集（~150 万行 × 7 天每天都有）完整跑通 pipelined 流水线，**只验证流程畅通 + 各阶段耗时合理**。**不要求与全量数据对数，不验证业务正确性**。

### 3.1 准备测试集（表：`rebuild5_stage.raw_gps_sample_7d`）

先检查现有表是否可复用：

```sql
-- 若已存在且合规则复用
SELECT COUNT(*) AS rows,
       COUNT(DISTINCT ts::date) AS days,
       MIN(ts::date) AS min_day,
       MAX(ts::date) AS max_day
FROM rebuild5_stage.raw_gps_sample_7d;
```

**复用条件**：`rows ∈ [1,200,000, 1,800,000]` **且** `days >= 7` **且** `min_day <= '2025-12-01'` **且** `max_day >= '2025-12-07'`。满足 → 跳到 §3.2。

否则重建：

```sql
CREATE SCHEMA IF NOT EXISTS rebuild5_stage;
DROP TABLE IF EXISTS rebuild5_stage.raw_gps_sample_7d;

-- 每天按随机抽样取 ~21.5 万行，7 天合计 ~150 万
CREATE TABLE rebuild5_stage.raw_gps_sample_7d AS
SELECT r.* FROM (
  SELECT r.*,
         ROW_NUMBER() OVER (PARTITION BY r.ts::date ORDER BY random()) AS rn
  FROM rebuild5.raw_gps_full_backup r
  WHERE r.ts >= '2025-12-01' AND r.ts < '2025-12-08'
) r
WHERE r.rn <= 215000;

-- 验收：应约 150 万行 + 7 行（每天）
SELECT COUNT(*) AS rows FROM rebuild5_stage.raw_gps_sample_7d;
SELECT ts::date AS day, COUNT(*) AS rows
FROM rebuild5_stage.raw_gps_sample_7d
GROUP BY ts::date ORDER BY day;
-- rows ∈ [1,200,000, 1,800,000]；7 行，每天 15-22 万
```

### 3.2 挂载测试集（保护原始表）

```sql
-- 把原始 full_backup 暂存到保护位
ALTER TABLE rebuild5.raw_gps_full_backup RENAME TO raw_gps_full_backup_prod_hold;

-- 把测试集复制到脚本默认读的位置
CREATE TABLE rebuild5.raw_gps_full_backup AS
SELECT * FROM rebuild5_stage.raw_gps_sample_7d;

CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_uid
  ON rebuild5.raw_gps_full_backup ("记录数唯一标识");
CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_ts
  ON rebuild5.raw_gps_full_backup (ts);

ANALYZE rebuild5.raw_gps_full_backup;

-- 验证挂载
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup;  -- 约 150 万
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup_prod_hold;  -- 原始，>= 2500 万
```

### 3.3 启动预跑

```bash
cd /Users/yangcongan/cursor/WangYou_Data
LOG=rebuild5/runtime/logs/sample_rerun_$(date +%Y%m%d_%H%M%S).log
nohup python3 rebuild5/scripts/run_step1_step25_pipelined_temp.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  --skip-prepare \
  > $LOG 2>&1 &
echo $! > rebuild5/runtime/sample_rerun.pid
echo "PID=$(cat rebuild5/runtime/sample_rerun.pid)  LOG=$LOG"
```

### 3.4 监控（短 SQL 轮询）

**Step 1 每天进度**：

```sql
SELECT run_id, status, started_at, finished_at,
       raw_record_count, cleaned_record_count, clean_pass_rate,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at DESC LIMIT 10;
```

**Step 2-5 批次进度**：

```sql
SELECT 'cell' AS t, batch_id, COUNT(*) AS rows FROM rebuild5.trusted_cell_library GROUP BY batch_id
UNION ALL SELECT 'bs',  batch_id, COUNT(*) FROM rebuild5.trusted_bs_library  GROUP BY batch_id
UNION ALL SELECT 'lac', batch_id, COUNT(*) FROM rebuild5.trusted_lac_library GROUP BY batch_id
ORDER BY t, batch_id;
```

**卡住排查**（单 SQL > 30 分钟未完成停下汇报）：

```sql
SELECT pid, client_addr, state,
       EXTRACT(EPOCH FROM (NOW() - query_start))::int AS secs,
       LEFT(regexp_replace(query,'\s+',' ','g'), 200) AS q
FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active'
ORDER BY query_start LIMIT 3;
```

**进程存活**：

```bash
ps -p $(cat rebuild5/runtime/sample_rerun.pid) && echo alive || echo exited
```

### 3.5 预跑验收（只验"流程通"）

```sql
-- 三层都应有 7 批
SELECT 'cell' AS t, COUNT(DISTINCT batch_id) AS b FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs',  COUNT(DISTINCT batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_lac_library;
-- 三行都应 = 7

-- 垃圾 cell 全为 0（ETL 过滤规则生效）
SELECT batch_id,
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm='4G') AS g4g,
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm='5G') AS g5g,
  COUNT(*) FILTER (WHERE lac < 100) AS glac
FROM rebuild5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
-- g4g / g5g / glac 每批都应 = 0

-- ODS-019（cell_infos 陈旧缓存）drop 量 > 0
SELECT run_id,
       (parse_details->'ods_019'->>'dropped_stale_count')::bigint AS dropped,
       (parse_details->'ods_019'->>'drop_rate')::float AS drop_rate
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;
-- 每行 dropped > 0；drop_rate 小数据集波动允许（不硬要求区间）

-- ODS-020 / ODS-022 (ss1 解析清洗) drop 量 > 0
SELECT run_id,
       (parse_details->'ss1_rules'->'ods_020'->>'dropped_subrec')::bigint AS ods020_drop,
       (parse_details->'ss1_rules'->'ods_020'->>'drop_rate')::float AS ods020_rate,
       (parse_details->'ss1_rules'->'ods_022'->>'dropped_sigs')::bigint AS ods022_drop,
       (parse_details->'ss1_rules'->'ods_022'->>'drop_rate')::float AS ods022_rate
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;
-- 每行 ods020_drop / ods022_drop 应 > 0（规则生效）；rate 小数据集不硬要求区间

-- DEDUP-V2 校验 1：cell_origin 透传到 cell_sliding_window（非空率应接近 100%）
SELECT COUNT(*) AS total,
       COUNT(cell_origin) AS with_origin,
       ROUND(COUNT(cell_origin)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS origin_rate_pct
FROM rebuild5.cell_sliding_window;
-- origin_rate_pct 应 ≥ 95%（历史 batch 的极少量 snapshot_seed 可能缺失，可接受）

-- DEDUP-V2 校验 2：dedup 后点数远超老策略（按样本量而不是全库对比，只取一个参考 cell）
-- 选 batch 7 中 gps_valid_count > 50 的任一 cell，看去重结构
SELECT cell_id, lac, operator_code, gps_valid_count, distinct_dev_id, active_days
FROM rebuild5.trusted_cell_library
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
  AND gps_valid_count::int > 50
ORDER BY gps_valid_count::int DESC
LIMIT 3;
-- 预期：活跃正常 cell 的 gps_valid_count 相比 DEDUP-V2 前大致翻倍（旧策略下典型值约 20~60，新策略 40~200）
```

任一项未通过停下汇报。

### 3.6 性能评估（样本跑通后必做）

**目的**：发现瓶颈、决定是否优化。**仅允许**加索引 / 把 CTE 改 `MATERIALIZED` / 补 `ANALYZE`。**不改业务逻辑**。

记录每阶段耗时基线：

```sql
SELECT run_id, batch_id,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step5_run_stats ORDER BY batch_id;

SELECT run_id,
       raw_record_count, cleaned_record_count,
       EXTRACT(EPOCH FROM (finished_at - started_at))::int AS secs
FROM rebuild5_meta.step1_run_stats ORDER BY started_at;
```

**判定标准**：
- 若各批 Step 5 耗时 ≤ 120 秒 **且** 各日 Step 1 耗时 ≤ 180 秒 → 流程健康，直接进 §3.7
- 若有阶段超出 2×基线（如某批 Step 5 > 240 秒）→ 取最耗时那条 SQL 的 EXPLAIN，定位瓶颈；加一个索引 / 改一处 MATERIALIZED；**再跑一次 §3.3** 复验
- 最多 2 轮优化复验；仍超标 → 停下汇报，不自行继续

### 3.7 清理测试挂载 + 恢复原始数据源

```bash
# 再跑 reset 清除测试产出的 Step 1-5 状态
PGPASSWORD=123456 psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -f /Users/yangcongan/cursor/WangYou_Data/rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql
```

```sql
-- 丢弃测试挂载，把保护位的原始表改回默认名
DROP TABLE IF EXISTS rebuild5.raw_gps_full_backup;
ALTER TABLE rebuild5.raw_gps_full_backup_prod_hold RENAME TO raw_gps_full_backup;

-- 重建原始表索引（保护位 RENAME 过来后索引名可能带 prod_hold 前缀，以旧名重建）
CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_uid
  ON rebuild5.raw_gps_full_backup ("记录数唯一标识");
CREATE INDEX IF NOT EXISTS idx_raw_gps_full_backup_ts
  ON rebuild5.raw_gps_full_backup (ts);
ANALYZE rebuild5.raw_gps_full_backup;

-- 强制硬校验
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup;
-- 应 >= 25,000,000；低于此值立即停下汇报（原始数据疑似受损）

SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold');
-- 应 NULL（保护位已清）
```

**§3.7 任一校验未通过，禁止进入 §4**。

---

## 4. 正式全量 7 天重跑

### 4.1 正式启动前再次检测

```sql
-- 原始数据完好
SELECT COUNT(*) FROM rebuild5.raw_gps_full_backup;            -- >= 2500 万
SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold'); -- NULL

-- 目标表全空（§3.7 reset 生效）
SELECT 'cell' AS t, COUNT(*) FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs',  COUNT(*) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(*) FROM rebuild5.trusted_lac_library
UNION ALL SELECT 'step1_stats', COUNT(*) FROM rebuild5_meta.step1_run_stats
UNION ALL SELECT 'step5_stats', COUNT(*) FROM rebuild5_meta.step5_run_stats;
-- 前 5 项都应 = 0

-- 无外部活跃写入
SELECT pid, state FROM pg_stat_activity
WHERE datname='ip_loc2' AND pid != pg_backend_pid() AND state='active';
-- 只应看到自己的查询
```

任一项未过停下汇报。

### 4.2 启动正式流水线

```bash
cd /Users/yangcongan/cursor/WangYou_Data
LOG=rebuild5/runtime/logs/full_rerun_$(date +%Y%m%d_%H%M%S).log
nohup python3 rebuild5/scripts/run_step1_step25_pipelined_temp.py \
  --start-day 2025-12-01 --end-day 2025-12-07 \
  --start-batch-id 1 \
  --skip-prepare \
  > $LOG 2>&1 &
echo $! > rebuild5/runtime/full_rerun.pid
echo "PID=$(cat rebuild5/runtime/full_rerun.pid)  LOG=$LOG"
```

**预计耗时**：60-150 分钟（Step 1 先跑完 7 天后 Step 2-5 跟进；具体取决于 §3.6 的基线）。

### 4.3 监控

同 §3.4 的 SQL（换成看 `full_rerun.pid`）。

---

## 5. 正式验收（全部 7 批完成后）

### 5.1 三层都有 7 批

```sql
SELECT 'cell' AS t, COUNT(DISTINCT batch_id) AS b FROM rebuild5.trusted_cell_library
UNION ALL SELECT 'bs',  COUNT(DISTINCT batch_id) FROM rebuild5.trusted_bs_library
UNION ALL SELECT 'lac', COUNT(DISTINCT batch_id) FROM rebuild5.trusted_lac_library;
-- 三行都应 = 7
```

### 5.2 垃圾 cell = 0（硬要求）

```sql
SELECT batch_id,
  COUNT(*) FILTER (WHERE cell_id < 1000 AND tech_norm='4G') AS g4g,
  COUNT(*) FILTER (WHERE cell_id < 4096 AND tech_norm='5G') AS g5g,
  COUNT(*) FILTER (WHERE lac < 100) AS glac
FROM rebuild5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
-- g4g / g5g / glac 每批都应 = 0；任一项 > 0 停下汇报
```

### 5.3 batch 7 drift 分布

```sql
SELECT drift_pattern, COUNT(*) AS cnt,
  ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(), 2) AS pct
FROM rebuild5.trusted_cell_library WHERE batch_id = 7
GROUP BY drift_pattern ORDER BY cnt DESC;
```

期望：`stable` 93-96% / `insufficient` 2-4% / 其他合计 < 1%。偏离 > 3 个百分点记录到汇报。

### 5.4 BS classification（batch 7）

```sql
SELECT classification, COUNT(*) AS cnt
FROM rebuild5.trusted_bs_library WHERE batch_id = 7
GROUP BY classification ORDER BY cnt DESC;
```

期望：`normal` ≥ 95%、`insufficient` 3-5%、其他合计数量级百位以内。

### 5.5 ODS-019 / ODS-020 / ODS-022 过滤量分布

```sql
-- ODS-019: cell_infos 陈旧缓存
SELECT run_id,
       (parse_details->'ods_019'->>'total_connected_objects')::bigint AS total,
       (parse_details->'ods_019'->>'dropped_stale_count')::bigint AS dropped,
       (parse_details->'ods_019'->>'drop_rate')::float AS drop_rate,
       (parse_details->'ods_019'->>'max_age_sec')::int AS max_age_sec
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;
```

期望：每天 `drop_rate` 在 **10-25%** 之间。若某日 = 0 → 新规则未生效；某日 > 50% → 可能阈值问题。任一异常停下汇报。

```sql
-- ODS-020: ss1 批内锚点陈旧过滤
SELECT run_id,
       (parse_details->'ss1_rules'->'ods_020'->>'total_subrec')::bigint AS total,
       (parse_details->'ss1_rules'->'ods_020'->>'dropped_subrec')::bigint AS dropped,
       (parse_details->'ss1_rules'->'ods_020'->>'drop_rate')::float AS drop_rate,
       (parse_details->'ss1_rules'->>'max_age_from_anchor_sec')::int AS max_age_sec
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;
```

期望：`drop_rate` 在 **5-20%** 之间（抽样基线 ~14%）。`dropped = 0` 或 `drop_rate > 40%` 异常。

```sql
-- ODS-022: ss1 全 -1 sig 条目
SELECT run_id,
       (parse_details->'ss1_rules'->'ods_022'->>'total_sigs')::bigint AS total,
       (parse_details->'ss1_rules'->'ods_022'->>'dropped_sigs')::bigint AS dropped,
       (parse_details->'ss1_rules'->'ods_022'->>'drop_rate')::float AS drop_rate
FROM rebuild5_meta.step1_run_stats
ORDER BY started_at;
```

期望：`drop_rate` 在 **2-8%** 之间（抽样基线 ~4.6%）。

**UI 观察**（非必需）：访问前端 `/etl/clean` 页，表格末尾应有 `ODS-019 / ODS-020 / ODS-021 / ODS-022` 四行，其中 019 / 020 / 022 命中数非零，021 只是规则说明（无量化统计）。

### 5.6 ODS-024 簇最小设备数门槛（2025-04-21 新增）

```sql
-- 抽样看 label_results 里 k_eff 分布（应几乎没 dev_count=1 的单设备簇了）
-- 此查询仅快速估算，不硬要求精确
SELECT batch_id, label, COUNT(*) AS cnt
FROM rebuild5.label_results
WHERE batch_id = 7
GROUP BY batch_id, label
ORDER BY cnt DESC;
```

期望：`insufficient` 比例相比修复前略升（原本由"单设备跨天假簇"支撑的 stable/oversize_single 会回归 insufficient）。

### 5.7 UI 验收（非必需但推荐）

- **维护页**（Cell / BS / LAC 三 Tab）：SummaryCard 有数、表格无空页
- **评估页**：`/api/evaluation/overview` 返回 `snapshot_version='v7'`，`published_cell_count` 与 §5.1 的 cell batch 7 一致

### 5.8 DEDUP-V2.1 + TA 透传验收（2026-04-23 更新）

```sql
-- 1) cell_origin / timing_advance / freq_channel 透传到 cell_sliding_window
SELECT
  ROUND(COUNT(cell_origin)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS origin_rate_pct,
  ROUND(COUNT(timing_advance)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS ta_rate_pct,
  ROUND(COUNT(freq_channel)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS freq_rate_pct
FROM rebuild5.cell_sliding_window;
-- origin_rate_pct 硬要求 ≥ 95%
-- ta_rate_pct 约 15-25%（ss1 本就无 TA，cell_infos 里 TDD 约一半被 ODS-023 置 NULL）
-- freq_rate_pct 约 80-95%（ss1 行可能为 NULL）

-- 2) 参考异常 cell 修复
SELECT cell_id, lac, operator_code, batch_id,
       drift_pattern, p50_radius_m::int AS p50, p90_radius_m::int AS p90,
       raw_gps_valid_count, gps_valid_count, distinct_dev_id,
       ta_n_obs, ta_p90, freq_band, ta_verification
FROM rebuild5.trusted_cell_library
WHERE cell_id IN (20752955, 17539075, 4855663)
  AND batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
ORDER BY cell_id;
-- 期望：p90 显著下降（6478m 级降到百米级或小几千米）；drift_pattern 不再是 insufficient

-- 3) 正常 cell 未误伤
SELECT cell_id, lac, drift_pattern,
       p90_radius_m::int AS p90_weighted,
       gps_valid_count,
       ta_verification
FROM rebuild5.trusted_cell_library
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
  AND drift_pattern = 'stable'
  AND gps_valid_count::int >= 50
ORDER BY p90_radius_m DESC
LIMIT 10;
-- 期望：p90 基本 ≤ 1000m；gps_valid_count 相比 V1 天去重前翻倍左右

-- 4) ODS-023 效果：TDD cell 的 timing_advance 应以 ≤15 为主
SELECT
  CASE WHEN timing_advance IS NULL THEN 'null'
       WHEN timing_advance BETWEEN 0 AND 15 THEN 'tdd_valid (0-15)'
       WHEN timing_advance >= 16 THEN 'tdd_placeholder (应被清空!)' END AS bucket,
  COUNT(*) AS n
FROM rebuild5.cell_sliding_window
WHERE cell_origin = 'cell_infos' AND tech_norm = '4G'
  AND freq_channel BETWEEN 36000 AND 43589
GROUP BY bucket;
-- 期望：tdd_placeholder 桶为 0 或极少（ODS-023 应把它们清掉）

-- 5) ta_verification 分布
SELECT ta_verification, COUNT(*) AS n,
       ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER () * 100, 1) AS pct
FROM rebuild5.trusted_cell_library
WHERE batch_id = (SELECT MAX(batch_id) FROM rebuild5.trusted_cell_library)
GROUP BY ta_verification
ORDER BY n DESC;
-- 期望：
--   ok             主体（FDD 小/中覆盖）
--   not_checked    中等比例（TDD + 5G + unknown）
--   insufficient   小比例
--   large / xlarge 少数（识别出郊区大覆盖 cell）
--   not_applicable 少量（multi_centroid / collision）

-- 6) 加权 p90 vs raw_p90 对比（方案 B 生效证据）
SELECT
  COUNT(*) AS cells,
  COUNT(*) FILTER (WHERE raw_p90_radius_m > p90_radius_m * 1.5) AS weighted_reduced,
  ROUND(AVG(p90_radius_m)::numeric, 0) AS avg_p90_w,
  ROUND(AVG(raw_p90_radius_m)::numeric, 0) AS avg_p90_raw
FROM rebuild5.cell_radius_stats;
-- 期望：weighted_reduced > 0（至少一些 cell 的加权 p90 显著小于 raw_p90）
```

任一项未通过停下汇报。

---

## 6. 汇报

写到 `rebuild5/docs/rerun_delivery_<YYYY-MM-DD>_full.md`：

1. **总耗时**：正式全量起止时间；每天 Step 1 起止；每批 Step 2-5 起止
2. **性能基线**：§3.6 记录的样例耗时、是否有优化轮次、做了什么优化
3. **行数**：每批 trusted_cell / trusted_bs / trusted_lac 行数
4. **drift 分布**：batch 7 的 drift_pattern 分布
5. **BS classification**：batch 7 分布
6. **ODS-019 / ODS-020 / ODS-022 drop 量**：每日 `drop_rate`（§5.5）
7. **异常告警**：任何停下汇报的节点 / 遇到的问题 / 卡死 SQL

---

## 7. 失败处理

### 7.1 进程异常退出但未通过 §5

```bash
tail -200 $(ls -t rebuild5/runtime/logs/*.log | head -1)
```

根据日志定位卡在哪一天 / 哪一步，**报告给人工裁决**；不自行二次启动。

### 7.2 DB 查询卡住 > 30 分钟

用 §3.4 的卡住排查 SQL 抓取当前 query，报告；不自行 `pg_cancel_backend` / `pg_terminate_backend`。

### 7.3 原始数据疑似受损（`raw_gps_full_backup < 2500 万` 或被意外修改）

**立刻停下**，报告当前状态：

```sql
SELECT COUNT(*) AS rows FROM rebuild5.raw_gps_full_backup;
SELECT to_regclass('rebuild5.raw_gps_full_backup_prod_hold');
```

等人工评估后再决定下一步（从 `prod_hold` 还原 / 从上游重建 / 其他），**不自行恢复**。

### 7.4 §3.6 优化 2 轮后仍超标

停下汇报。提供：
- 最耗时的单条 SQL（从 §3.4 卡住排查 SQL 捞到的）
- 该 SQL 的 `EXPLAIN ANALYZE` 输出
- 两轮优化做了什么

由人工决定是否放宽阈值或进一步改动。

---

## 附：关键位置索引

| 项 | 路径 |
|---|---|
| Pipelined 脚本 | `rebuild5/scripts/run_step1_step25_pipelined_temp.py` |
| Reset 脚本 | `rebuild5/scripts/reset_step1_to_step5_for_full_rerun_v3.sql` |
| ETL 过滤规则 | `rebuild5/docs/01b_数据源接入_处理规则.md` |
| ETL clean 主规则列表 | `rebuild5/backend/app/etl/clean.py::ODS_RULES` |
| ETL parse `ODS-019` | `rebuild5/backend/app/etl/parse.py::_parse_cell_infos` |
| ETL parse `ODS-020/021/022` | `rebuild5/backend/app/etl/parse.py::_parse_ss1` |
| 配置 | `rebuild5/config/antitoxin_params.yaml` |
| fix4 优化 | `rebuild5/docs/fix4/snapshot_seed_sql_optimization.md` |
