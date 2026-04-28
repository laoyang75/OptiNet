# Runbook 全量执行问题记录与修复

> 记录 `runbook_beijing_7d.md` 首次全量执行（beijing_7d, 2542 万行）中暴露的所有问题、根因和修复方案。
> 后续重跑前必须逐条检查，避免同类问题再次出现。

## 执行环境

- PG 服务器：192.168.200.217（Debian Linux, Docker 容器 `pg17-test`）
- 硬件：40 核 E5-2660 v2 / 251GB RAM / 6.7TB RAID `/data`
- 数据集：beijing_7d, raw_gps 25,442,069 行 → etl_cleaned 45,314,465 行

---

## 一、致命性能问题

### P1: 全局禁用 PG 并行（8.5 小时未完成）

- **文件**：`rebuild5/backend/app/core/database.py:24`
- **现象**：Step 2 的 `build_profile_base()` 跑了 8.5 小时仍未完成
- **根因**：`get_conn()` 每个连接都执行 `SET max_parallel_workers_per_gather = 0`，注释说"macOS shared memory"，但 PG 跑在远程 Linux Docker 容器上
- **修复**：删除该 SET 语句，让 PG 使用服务器级配置（16 parallel workers）
- **效果**：profile_base 3 表 JOIN 从 8.5 小时 → **秒级完成**
- **教训**：连接级 SET 会覆盖服务器配置，且对所有查询生效。防御性禁用并行是错误的——应该在需要时限制，而不是默认禁用

### P2: Docker 容器 shm-size 64MB（并行 worker 内存不足）

- **现象**：启用并行后，`DiskFull: could not resize shared memory segment` 错误
- **根因**：Docker 默认 `--shm-size=64MB`，PG 并行 worker 的动态共享内存不够
- **修复**：重建容器 `--shm-size=8g`
- **教训**：Docker PG 容器必须设置足够的 shm-size，否则并行查询会失败

### P3: PG 配置未优化（251GB RAM 只用 8GB）

- **现象**：shared_buffers=8GB, max_parallel_workers=8, effective_io_concurrency=1
- **修复**：全面优化 postgresql.auto.conf：
  ```
  shared_buffers = 64GB
  effective_cache_size = 188GB
  work_mem = 512MB
  max_worker_processes = 40
  max_parallel_workers = 20
  max_parallel_workers_per_gather = 16
  effective_io_concurrency = 200
  parallel_tuple_cost = 0.01
  jit = off
  min_parallel_table_scan_size = 1MB
  ```
- **教训**：专用数据库服务器必须按硬件能力配置，不能用默认值

### P4: collision.py 碰撞检测 20 分钟（实际只有 2 对碰撞）

- **文件**：`rebuild5/backend/app/maintenance/collision.py:87-117`
- **现象**：53.8 万行 trusted_cell_library 自 JOIN，单核跑 20 分钟
- **根因**：
  1. 自 JOIN 扫描全表 53.8 万 × 53.8 万，但实际只有 2 个 cell 有多 bs_id
  2. UPDATE 语句不支持并行（PG 限制）
  3. 无索引
- **修复**：先用 `multi_bs` CTE 筛出有多 bs_id 的 cell（极少），只对这些做距离计算
- **教训**：自 JOIN 前必须先缩小范围。53.8 万行对 40 核应该秒级完成，跑 20 分钟就是明显的逻辑错误

### P5: 临时表无索引导致 JOIN 极慢

- **文件**：`rebuild5/backend/app/profile/pipeline.py` (Step 2), `rebuild5/backend/app/maintenance/pipeline.py` (Step 5)
- **现象**：profile_base 的 3 表 JOIN 8.5 小时（P1 的次要原因）；Step 5 各种 JOIN/UPDATE 慢
- **根因**：CTAS 创建临时表后没有建索引就开始 JOIN
- **修复**：
  - Step 2：`_profile_centroid`、`_profile_devs`、`_profile_radius` 创建后立即建索引
  - Step 5：pipeline.py 在每个子步骤之间加 7 个索引（cell_sliding_window / cell_daily_centroid / cell_metrics_window / cell_anomaly_summary / trusted_cell_library）
- **教训**：**每个 CTAS/INSERT 之后、被下游 JOIN 之前，必须加索引**。这是铁律。

### P6: publish_cell.py LATERAL 子查询逐行执行

- **文件**：`rebuild5/backend/app/maintenance/publish_cell.py:119-130`
- **根因**：`LEFT JOIN LATERAL (SELECT ... WHERE batch_id = (SELECT MAX(...) WHERE batch_id < %s) LIMIT 1)` 对每一行都执行子查询
- **修复**：改为预计算的普通 `LEFT JOIN`，前批次数据一次性加载
- **教训**：LATERAL 子查询在大表上是 O(N) 子查询，尽量用 CTE 预计算替代

---

## 二、Schema / 数据兼容性问题

### S1: `_profile_path_a_candidates` 空表缺 `match_layer` 列

- **文件**：`rebuild5/backend/app/profile/pipeline.py:514-516`
- **现象**：`write_step2_run_stats` 查询 `match_layer` 列，但首轮空表定义中没有这列
- **修复**：空表 CTAS 中增加 `NULL::text AS match_layer`

### S2: cell_id 碰撞导致 snapshot PK 冲突

- **文件**：`rebuild5/backend/app/evaluation/pipeline.py:217`
- **现象**：同一 cell_id 出现在不同 bs_id/tech_norm（4G vs 5G），PK `(batch_id, operator_code, lac, cell_id)` 冲突
- **修复**：用 `DISTINCT ON (batch_id, operator_code, lac, cell_id)` 去重，保留 independent_obs 最大的

### S3: `cell_metrics_window` 缺 drift 列

- **文件**：`rebuild5/backend/app/maintenance/schema.py:282-313`
- **现象**：`cell_maintain.py` UPDATE `max_spread_m`/`net_drift_m`/`drift_ratio` 但表定义中没有这些列
- **修复**：schema.py 中增加三列

### S4: `cell_daily_centroid` PK 含 lac 导致 NOT NULL 冲突

- **文件**：`rebuild5/backend/app/maintenance/schema.py:258-272`
- **现象**：PK `(batch_id, operator_code, lac, cell_id, obs_date)` 隐含 NOT NULL，但 cell_sliding_window 有 93,323 行 lac=NULL
- **修复**：去掉 PK 约束（cell_metrics_window 同理）

### S5: pressure 字段含多值字符串

- **文件**：`rebuild5/backend/app/enrichment/pipeline.py:167`
- **现象**：`p.pressure::double precision` 失败，因为 pressure 存了 `"6,1014.439453,"` 格式的逗号分隔值
- **修复**：安全转换 `CASE WHEN p.pressure ~ E'^-?[0-9]+\\.?[0-9]*$' THEN p.pressure::double precision ELSE NULL END`

---

## 三、架构 / 代码清理

### A1: 单源化未收口

- **现象**：source_prep 已把 GPS+LAC 合并为 raw_gps，但 parse.py 还建 4 张中间表（ci_gps/ci_lac/ss1_gps/ss1_lac），queries.py 展示 4 路统计
- **修复**：
  - `source_prep.py`：去掉空 raw_lac 创建
  - `parse.py`：4 路 → 2 路（etl_ci + etl_ss1）
  - `queries.py`：统计从 4 项改 2 项，兼容新旧 parse_details 格式
- **教训**：抽象必须和执行路径一起收口，伪多源壳层增加理解成本和维护风险

### A2: etl_clean_stage 90GB 长期保留

- **修复**：pipeline.py 中 fill 完成后 `DROP TABLE IF EXISTS rebuild5.etl_clean_stage`
- **同时清理**：etl_ci、etl_ss1 中间表

### A3: etl_cleaned(record_id) 重复索引

- **现象**：`idx_etl_cleaned_record`（runbook）和 `idx_etl_cleaned_record_id`（profile/pipeline.py）
- **修复**：统一为 `idx_etl_cleaned_record`

### A4: step1_run_stats 时间戳恒为 0

- **文件**：`rebuild5/backend/app/etl/pipeline.py:109`
- **现象**：`started_at` 和 `finished_at` 都是 `NOW()`，无法评估耗时
- **修复**：记录真实 `start_time = datetime.now()`，INSERT 时传入

### A5: `execute_serial()` 禁用 hashjoin + 并行

- **文件**：`rebuild5/backend/app/profile/pipeline.py:482-488`
- **修复**：删除函数，调用处改为普通 `execute()`

---

## 四、重跑前检查清单

下次重跑全流程前，**必须逐项确认**：

### 环境
- [ ] Docker shm-size >= 8GB：`docker inspect pg17-test --format '{{.HostConfig.ShmSize}}'`
- [ ] PG shared_buffers >= 64GB：`SHOW shared_buffers`
- [ ] PG max_parallel_workers_per_gather >= 8：`SHOW max_parallel_workers_per_gather`
- [ ] database.py 的 `get_conn()` 没有 SET 禁用并行的语句
- [ ] 磁盘空间 > 200GB：`df -h /data`

### 索引策略
- [ ] Step 1 完成后：etl_cleaned 上有 `idx_etl_cleaned_cell`、`idx_etl_cleaned_op_lac_cell`、`idx_etl_cleaned_bs`、`idx_etl_cleaned_record`、`idx_etl_cleaned_path_lookup`
- [ ] Step 2 profile_base 每个临时表创建后立即建索引
- [ ] Step 5 每个子步骤之间有索引创建（见 pipeline.py）

### 性能基线
- [ ] Step 2 profile_base JOIN：应 < 30 秒
- [ ] Step 3 评估：应 < 2 分钟
- [ ] Step 5 碰撞检测：应 < 10 秒
- [ ] 任何单步超过 10 分钟需要排查

### 数据校验
- [ ] etl_cleaned 的 lac 可以为 NULL（下游 schema 不能有 lac NOT NULL 约束）
- [ ] pressure 字段需要安全转换（非纯数字值过滤）
- [ ] cell_id 可能跨多个 bs_id/tech_norm（snapshot 去重）
