# 31 Citus 全量迁移 + rebuild5 pipeline 代码 Citus 化 + 7 批 rerun

> **更新日期**:2026-04-23(**v2.2**,已吸收 agent 两轮评审共 8 条反馈;v2.2 清理了 v2/v2.1 遗留的局部改动未同步到 §0/§5/§9 的问题)
> **数据库**:旧(只读)`postgresql://postgres:123456@192.168.200.217:5433/ip_loc2`;新(目标)`postgresql://postgres:123456@192.168.200.217:5488/yangca`
> **仓库**:`/Users/yangcongan/cursor/WangYou_Data`(你和这个目录的 git repo 有完整读写权)
> **接续**:Round 1/2 已验证集群能承接(`rb5_bench` 里数据);prompt 30c 已跳过 —— 用户选择走 B 路径,直接正式迁移;全量预期 ~92 分钟。
>
> **本次修订吸收的 agent 评审(id 13-18)**:
> - #13 DSN 环境变量改为代码实际的 `REBUILD5_PG_DSN`(见 §1.2 ④)
> - #14 数据流澄清:raw_gps_full_backup 是全量底表,Step 1 读 rb5.raw_gps 日级工作表(见 §3.0)
> - #15 Citus PK 必须含分布键;`cell_sliding_window` PK 扩展(见 §1.2 ③)
> - #16 **取消多天并发**,改严格串行(当前代码未并发安全,见 §6.1)
> - #17 ODS-024b 验收收紧为 `cell_origin='cell_infos'` 分支(见 §5 关 2)
> - #18 索引清单改为真实的 4 个 btree(见 §3.3)
>
> **本轮生效的关键规则**(继承 prompt 28 + 本轮在本地已落地的新规则):
> - **ODS-019**:cell_infos 陈旧缓存过滤,timeStamp 单位自动识别(≤13 位毫秒 / ≥14 位纳秒)
> - **ODS-020/021/022**:ss1 批内锚点 + tech 匹配 + 全 -1 sig 过滤
> - **ODS-023**:LTE TDD 占位 TA 剔除(TDD Earfcn 36000-43589 且 TA ≥ 16 置 NULL)
> - **ODS-023b(2026-04-23 新)**:LTE FDD 异常 TA 剔除(TA ≥ 255 或 < 0 置 NULL)
> - **ODS-024**:簇至少 2 个不同设备
> - **ODS-024b(2026-04-23 新)**:parse 阶段同 `(record_id, cell_id)` 按 age 最小去重
> - **DEDUP-V2.1**:ss1 按 `(cell, dev, record_id)` 去重;cell_infos 按 `(cell, dev, 5min_bucket)`
> - **方案 B 加权 p50/p90**:设备逆频加权
> - **label_engine k_eff 新规则(2026-04-23 新)**:k_eff=3-4 → uncertain;k_eff≥5 → dynamic(不再按 max_span/line_ratio 等动态特征)
> - **TA 透传 + trusted_cell_library 6 个 TA 字段**:`ta_n_obs / ta_p50 / ta_p90 / ta_dist_p90_m / freq_band / ta_verification`

---

## 0. 任务

1. **改本地代码** 让 `rebuild5/backend/app/` 下的 pipeline 能跑在 Citus 上
2. **迁移数据** 旧库 `ip_loc2.rebuild5.raw_gps_full_backup`(2544 万行) → 新库 `yangca.rb5.raw_gps_full_backup`
3. **跑 Step 1-5 全链 7 批** `dataset_key='beijing_7d'`(2025-12-01 ~ 12-07)
4. **产出** `yangca.rb5.trusted_cell_library / trusted_bs_library / trusted_lac_library` 各 7 批(batch_id=1..7)
5. **写报告 + 控制面数据** 到 `yangca.rb5_bench.*`
6. **不 commit** 你改的代码 —— 用户会在 Step C 手工 review + commit

### 预算与上限

- 代码改造:**2-4 小时**
- 数据迁移:**30-60 分钟**
- 冒烟 + 1 天预跑:**30 分钟**
- 正式 7 批 rerun:**~90 分钟**(**严格串行 day 1→7**,见 §6.1;原"可并发"已撤回)
- 验证 + 报告:**30 分钟**
- **总预算 6 小时**,超过 8 小时停下来写 `rb5_bench.notes` severity='blocker'

---

## 1. 代码 Citus 化改造(要求 + 验收)

你有 repo 读写权和代码修复能力,具体怎么改(sed / 手工 / 脚本)你定。下面只列**要求**和**验收点**。

### 1.1 改造范围(参考规模)

- ~10 个 .py 文件有 `CREATE TABLE ... AS` / `CREATE UNLOGGED TABLE ... AS`
- ~57 个文件引用 `rebuild5.*` / `rebuild5_meta.*` schema

### 1.2 改造要求

**① Schema rename**:`rebuild5.` → `rb5.`,`rebuild5_meta.` → `rb5_meta.`

不要误伤:Python 模块路径(`from rebuild5.backend...`)、`dataset_key = 'beijing_7d'` 等常量、中文列名。

**② CTAS → 预建 distributed + INSERT/SELECT**

Round 2 证明 "CTAS 后再 `create_distributed_table`" 每次有 ~30s 搬运税。本轮必须改模式:先 `CREATE TABLE ... (LIKE 或手写列)` → `SELECT create_distributed_table(...)` → `INSERT INTO ... SELECT`。

**③ Distribution key 策略(定好直接用)**

| 表 | 分布方式 | colocation group | 主键/唯一约束注意 |
|---|---|---|---|
| `rb5.raw_gps_full_backup` | **`did`** hash(旧库原列名) | **A** | 如有 PK,必须含 did |
| `rb5.raw_gps`(日级工作表) | **`did`** hash | A(colocate_with raw_gps_full_backup) | 同上 |
| `rb5.etl_parsed / etl_clean_stage / etl_cleaned / etl_filled` | **`dev_id`** hash(parse 后列名) | A(colocate_with raw_gps_full_backup,Citus 允许列名不同,要求类型兼容) | 如有 PK,含 dev_id |
| `rb5.cell_sliding_window` 及所有 cell 级中间表 | `cell_id` hash | **B** | **PK/UNIQUE 必须含 cell_id**(见下) |
| `rb5.label_results / _label_*` | `cell_id` hash | B | 同上 |
| `rb5.trusted_cell_library` | `cell_id` hash | B | 同上 |
| `rb5.trusted_bs_library` | `bs_id` hash | C(可独立也可作 reference) | 含 bs_id |
| `rb5.trusted_lac_library` | **reference table**(行数少) | — | — |
| `rb5_meta.*`(dataset_registry / run_logs / *_stats 等) | **reference table** | — | — |

**关键约束 — Citus 要求分布表的 PK/UNIQUE 必须包含分布键**

review 发现 `schema.py` 里 `cell_sliding_window` 的 PK 是 `(batch_id, source_row_uid)`,没有 cell_id。执行时 `create_distributed_table(..., 'cell_id')` 会失败。

处理原则:

1. **每个表创建前,先 grep `schema.py` 找 PK 定义**
2. 如果 PK 不含分布键:**扩展 PK** 为 `(现有列..., 分布键)`(Citus 接受 composite PK 包含分布键即可)
3. 如果扩展 PK 会破坏业务语义(比如真的要单列唯一),考虑改成 `UNIQUE INDEX` + 分布键一起,或者**重选分布键**(写 `rb5_bench.notes` 汇报)

**另外 — `cell_sliding_window` 有 retention DELETE / ctid 逻辑**

review 提到该表有跨全表的 `DELETE WHERE ctid ...` 之类的保留策略。在 Citus 分布表上:
- `ctid` 是 **shard-local** 的物理地址,跨 shard 无意义
- `DELETE` 本身 Citus 支持,但涉及 `ctid` 的 DELETE 需要改成基于分布键的 DELETE

**关 1 里专项验证**:检查 `maintenance/window.py` 或类似位置里所有 `DELETE` / `ctid` 用法,在 Citus 上跑一遍 EXPLAIN,失败就改成分布键/业务键。

**④ DSN 硬切到 Citus**:用户确认旧库 5433/ip_loc2 只在本次迁移做**只读数据源**,迁完作废,**不留双轨**。所以:

- `rebuild5/backend/app/core/settings.py:10` 的 `DEFAULT_DSN` 常量:直接改成 `postgres://postgres:123456@192.168.200.217:5488/yangca`
- `rebuild5/scripts/run_step1_step25_pipelined_temp.py` / `run_step1_to_step5_daily_loop.py` / `run_daily_increment_batch_loop.py` 等所有脚本里写死 5433 的地方,全部改到 5488/yangca
- 环境变量 `REBUILD5_PG_DSN` 保留(是代码现成的机制),但它的用途从"切不同 DB"变成了"调试时临时覆盖";**默认配置全部指向 yangca**

迁移时要从旧库读数据,**只**通过 §3 里显式写明的两行 psql 命令(旧库 `192.168.200.217:5433/ip_loc2`)连,**不走 `REBUILD5_PG_DSN`**。

**⑤ 不需要改的**:`CREATE INDEX` / `ANALYZE` / `DROP TABLE` 语句 — Citus 会自动在所有 shard 上执行。

### 1.3 改造验收(你自己跑一次,通过才进入 §2)

```bash
# 语法
python3 -m py_compile rebuild5/backend/app/**/*.py

# 没漏的 schema 引用
grep -rn "'rebuild5\." rebuild5/backend/ rebuild5/scripts/ 2>/dev/null \
  | grep -v __pycache__ | grep -v "rebuild5\.backend\|rebuild5\.scripts\|rebuild5\.frontend"
# 应无命中(只剩 Python import 路径,不应剩 SQL 字符串里的)

# 新 DSN 能连通
python3 -c "from rebuild5.backend.app.core.database import fetchone; \
            print(fetchone('SELECT current_database()'))"
# 期望 'yangca'
```

---

## 2. 数据库结构建立(yangca.rb5.*)

在 coordinator `psql -h 127.0.0.1 -p 5488 -U postgres -d yangca` 里:

```sql
-- 1. schema
CREATE SCHEMA IF NOT EXISTS rb5;
CREATE SCHEMA IF NOT EXISTS rb5_meta;

-- 2. 预建 raw_gps_full_backup(按旧库结构,不带数据)
-- 方法:从旧库 pg_dump --schema-only -t rebuild5.raw_gps_full_backup,改 rebuild5. → rb5.,apply
-- 完成后分布
SELECT create_distributed_table('rb5.raw_gps_full_backup', 'did');

-- 3. raw_lac(如果有)同样处理
CREATE TABLE rb5.raw_lac (LIKE ... );  -- 按旧库结构
-- 如果 raw_lac 行数 < 100k 做 reference table
SELECT create_reference_table('rb5.raw_lac');

-- 4. rb5_meta.* 所有元数据表做 reference(除非行数明显大)
-- dataset_registry / run_logs / step1_run_stats / step5_run_stats 等
```

Pipeline 里的中间表(etl_parsed / etl_cleaned / etl_filled / cell_sliding_window / ...)由**改造后的代码自己 CREATE + DISTRIBUTE**,你这里只做 raw 层 + meta。

---

## 3. 数据迁移(2544 万行一次性全量灌入底表,后续每关再 materialize 当日工作表)

### 3.0 数据流澄清(重要)

本 pipeline 的 **Step 1 读的是 `rb5.raw_gps`(日级工作表)**,不是 `rb5.raw_gps_full_backup`。
所以数据流是:

```
 旧库 ip_loc2.rebuild5.raw_gps_full_backup
     │  (一次性迁移,§3.1)
     ▼
 yangca.rb5.raw_gps_full_backup        ← 全量底表,只写一次,只读
     │  (每关前 materialize,按日期过滤)
     ▼
 yangca.rb5.raw_gps                    ← 日级工作表,每关重建,Step 1 读它
     │  (pipeline 跑 parse/clean/fill)
     ▼
 rb5.etl_parsed / etl_cleaned / etl_filled → ...
```

### 3.1 一次性迁移底表(2544 万行)

```bash
# 旧库 → 新库 raw_gps_full_backup(只做一次)
psql -h 192.168.200.217 -p 5433 -U postgres -d ip_loc2 \
  -c "\copy (SELECT * FROM rebuild5.raw_gps_full_backup) TO STDOUT" \
| psql -h 192.168.200.217 -p 5488 -U postgres -d yangca \
  -c "\copy rb5.raw_gps_full_backup FROM STDIN"

psql ... -c "SELECT COUNT(*) FROM rb5.raw_gps_full_backup;"  -- 期望 25,442,069
```

raw_lac **实际不存在**(review 发现),跳过。

### 3.2 rb5.raw_gps 工作表(每关 materialize)

也预建为 distributed(colocate with full_backup),但**每关前 TRUNCATE + INSERT**:

```sql
-- 关 1 前(150 万 TABLESAMPLE):
TRUNCATE rb5.raw_gps;
INSERT INTO rb5.raw_gps
SELECT * FROM rb5.raw_gps_full_backup TABLESAMPLE BERNOULLI(6) REPEATABLE(42);

-- 关 2 前(1 天):
TRUNCATE rb5.raw_gps;
INSERT INTO rb5.raw_gps SELECT * FROM rb5.raw_gps_full_backup WHERE ts::date = '2025-12-04';

-- 关 3 每批前(逐天 materialize,单日批次):
TRUNCATE rb5.raw_gps;
INSERT INTO rb5.raw_gps SELECT * FROM rb5.raw_gps_full_backup WHERE ts::date = '2025-12-0N';
-- 然后跑 Step 1-5 → 产出 batch_id=N
-- 下一天前再 TRUNCATE + INSERT
```

**注意**:
- 抽样迁完后看 shard 分布均匀度(±5% 内);不均匀写 `rb5_bench.notes` severity='warn',但不一定 blocker
- 迁完 ANALYZE 一遍:`psql ... -c "ANALYZE rb5.raw_gps_full_backup;"`

### 3.3 索引保留(必做)

review 确认旧库实际索引清单(别信我之前的"did、cell_infos GIN"猜测,那些不存在):

- `rebuild5.raw_gps_full_backup`:仅 **4 个 btree**
  - `idx_raw_gps_full_backup_ts`
  - `idx_raw_gps_full_backup_uid`
  - `idx_rebuild5_raw_gps_ts`(重复命名)
  - `idx_rebuild5_raw_gps_record_id`
- `rebuild5.raw_lac`:**不存在**(跳过)
- `rebuild5_meta.*`:各表 PK 存在

**做法**:在新库 `rb5.raw_gps_full_backup` 上重建 4 个 btree(schema 改到 rb5);`rb5_meta.*` 的 PK 由表结构迁移自动带来。

pipeline 代码里的 `CREATE INDEX IF NOT EXISTS` 会在各中间表上自动建,不用干预。

如果关 2/关 3 跑起来慢,可以**根据实测**新增本轮专用索引(比如按 `cell_id` 或 `did` 的 btree),新增的写 `rb5_bench.notes` topic='index_added' 记录。

完工后把已建索引列到 `rb5_bench.notes` topic='index_migration'。

---

## 4. 冒烟(必做)

### 4.1 集群健康

```sql
SELECT nodeid, nodename, nodeport, isactive FROM pg_dist_node;
-- 4 worker 都 isactive=true
SELECT extname, extversion FROM pg_extension WHERE extname IN ('citus','pg_stat_statements');
-- 都在
```

### 4.2 代码健康

```bash
# 所有 ETL/profile/maintenance 文件都能 import
cd /Users/yangcongan/cursor/WangYou_Data
python3 -c "from rebuild5.backend.app.etl import parse, clean, fill"
python3 -c "from rebuild5.backend.app.profile import pipeline as pp"
python3 -c "from rebuild5.backend.app.maintenance import pipeline as mp, label_engine, window, publish_cell, publish_bs_lac"
```

### 4.3 新 DSN 通

```bash
python3 -c "
from rebuild5.backend.app.core.database import fetchone
print(fetchone('SELECT current_database() AS db, current_user AS u'))
"
# 应该打印 {'db': 'yangca', 'u': 'postgres'}
```

### 4.4 规则落地冒烟

```bash
# 检查本地代码里新规则是否还在
grep -n "ODS-023b" /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/etl/clean.py
# 应该命中
grep -n "DISTINCT ON (record_id, cell_id)" /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/etl/parse.py
# 应该命中(ODS-024b)
grep -n "k_eff >= 5 THEN 'dynamic'" /Users/yangcongan/cursor/WangYou_Data/rebuild5/backend/app/maintenance/label_engine.py
# 应该命中
```

任何不命中 → blocker,停下来问用户。

---

## 5. 三道关(必须按顺序走,不许跳)

**重要铁律**:**小样本 → 1 天全链 → 7 天全量**,每关通过才进下一关。一旦某关失败,修完**重跑这关**,不要直接补下一关。

**前提**:§3.1 已把旧库 2544 万行一次性灌入 `rb5.raw_gps_full_backup`(底表,只读)。三道关都是从这张底表**按不同过滤条件 materialize 到 `rb5.raw_gps` 日级工作表**,pipeline 读 `rb5.raw_gps`(见 §3.0 数据流)。不再往 `raw_gps_full_backup` 灌新数据。

### 关 1 · 150 万样本跑通(预跑)

目的:在**小数据**上先验证代码改造没毛病、schema 正确、分布键对、索引到位。失败无成本,快速迭代修 bug。

**做法**:

1. 从 `rb5.raw_gps_full_backup` TABLESAMPLE 抽 ~150 万行到 `rb5.raw_gps`:
   ```sql
   TRUNCATE rb5.raw_gps;
   INSERT INTO rb5.raw_gps
   SELECT * FROM rb5.raw_gps_full_backup TABLESAMPLE BERNOULLI(6) REPEATABLE(42);
   ```
2. 跑 Step 1-5 **一次完整**(当成 1 个 batch 跑),DSN 默认已是 yangca(§1.2 ④)
3. 验收(全过才进关 2):

| 验收项 | 期望 |
|---|---|
| Step 1-5 全跑完无 Exception | ✓ |
| 最终产出 `rb5.trusted_cell_library` | 至少 1 批 |
| batch 里 cell 数 | 约 10-20 万(150 万样本的 1/7-1/3) |
| drift_pattern stable / large_coverage / uncertain 非 0 | ✓ |
| **drift_pattern dynamic**(k_eff≥5 新规则)| **期望 > 0**;如果 = 0 **不算 blocker**,但必须核查 label_engine 里 k_eff 分支 SQL 是否跑到,以及是否只是小样本随机性;结果写 `rb5_bench.notes` topic='gate1_dynamic_diagnosis'(关 2 的 1 天真实数据更可信) |
| pg_stat_statements Top 20 | **没有 create_distributed_table**(证明代码改造到位) |
| 总耗时 | < 20 分钟 |

**不通过**:修代码,重跑关 1,直到通过。在 `rb5_bench.notes` topic='phase1_issues' 记录修了什么。

### 关 2 · 1 天全链(~350 万行)

目的:用**真实 1 天数据**跑 1 批,证明生产规模下也跑得通、符合预期。

**做法**:

1. 从底表过滤 1 天(例如 2025-12-04)重建 `rb5.raw_gps`:
   ```sql
   TRUNCATE rb5.raw_gps;
   INSERT INTO rb5.raw_gps
   SELECT * FROM rb5.raw_gps_full_backup WHERE ts::date = '2025-12-04';
   ```
2. 跑 Step 1-5 产出 1 批
3. 验收:

| 验收项 | 期望 |
|---|---|
| batch 产出 | 1 批,cell ~30-40 万 |
| 新规则落地 | **dynamic > 0**(生产规模下必须有);xlarge 比本地少 30-40%;**cell_origin='cell_infos' 分支内**同 (cell_id, record_id) 无重复行(验收 SQL 要加 `WHERE cell_origin='cell_infos'`) |
| 耗时 | < 20 分钟(Round 2 外推 12.85 min/天) |

**不通过**:修,重跑关 2。关 1 通过不代表关 2 一定通过 — 生产规模才会暴露一些小样本掩盖的问题(某列 NULL 比例、长尾 did、JSON 异常值)。

### 关 3 · 7 天全量 rerun

**只有关 2 通过才能进本关**。

**做法**:

1. `TRUNCATE rb5.raw_gps` → 按 `ts::date = '2025-12-0N'` 从底表 INSERT 当日数据 → 跑 Step 1-5 产出 batch_id=N
2. 依次 N = 1, 2, 3, 4, 5, 6, 7 — **严格串行**(见 §6.1,多批不并发安全)
3. 最终产出 7 批 `rb5.trusted_cell_library`,验收见 §7

---

## 6. 关 3 执行细节 + 每批自检

### 6.1 严格串行(撤回之前的"可并发")

review 发现当前 Step 2-5 代码**不是多批并发安全**:
- `run_profile_pipeline` 用 `MAX(batch_id)+1` 派生批次号
- 共享中间表名:`step2_batch_input / path_a_records / _profile_* / enriched_records / cell_sliding_window / _label_*`
- `run_step1_step25_pipelined_temp.py` 只有一个 running_consumer

多批并发会撞车。**关 3 改为严格串行**,day 1 → day 7 一批接一批跑(和 prompt 28 一致)。并发改造不在本轮范围(写 `rb5_bench.notes` topic='future_work:batch_namespacing' 记录为后续事项即可)。

### 6.2 批次号规则

day 2025-12-01 → batch_id=1,day 02 → batch_id=2,... day 07 → batch_id=7(和本地 prompt 28 对齐,便于对比)

### 6.3 每批跑完立即自检

```sql
SELECT batch_id, COUNT(*) AS n_cells,
       COUNT(*) FILTER (WHERE drift_pattern='stable')        AS n_stable,
       COUNT(*) FILTER (WHERE drift_pattern='large_coverage') AS n_lc,
       COUNT(*) FILTER (WHERE drift_pattern='uncertain')     AS n_uncertain,
       COUNT(*) FILTER (WHERE drift_pattern='dynamic')       AS n_dynamic,
       COUNT(*) FILTER (WHERE ta_verification='xlarge')      AS ta_xl
FROM rb5.trusted_cell_library WHERE batch_id = <N>
GROUP BY batch_id;
```

期望(对比 Round 2 外推):
- n_cells:30-50 万
- stable:占 ~85%
- **dynamic > 0**(如果仍 0,k_eff 新规则没生效,blocker)
- **xlarge < 本地 batch 7 的 13,460 的 60-70%**(ODS-023b 清占位 TA 后预期降级)

单批不通过立即停下来查,不要继续往下一批推。

---

## 7. 验证(在 7 批全产出后)

```sql
-- 7.1 7 批齐全
SELECT batch_id, COUNT(*) AS n FROM rb5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
-- 期望 7 行,每行 n 在 30-50 万之间

-- 7.2 新规则效果验证
-- ODS-023b 效果:FDD TA=1282 应该几乎没有
SELECT COUNT(*) FILTER (WHERE ta_p90 = 1282) AS still_1282
FROM rb5.trusted_cell_library WHERE batch_id=7 AND freq_band='fdd';
-- 期望 0 或 < 100

-- k_eff 新规则效果:有 dynamic 了
SELECT batch_id, COUNT(*) FROM rb5.trusted_cell_library
WHERE drift_pattern='dynamic' GROUP BY batch_id ORDER BY batch_id;
-- 期望每批有几个到几十个

-- 7.3 xlarge 降级验证(对比本地 batch 7 = 13,460)
SELECT batch_id, COUNT(*) FILTER (WHERE ta_verification='xlarge') AS n_xl
FROM rb5.trusted_cell_library GROUP BY batch_id ORDER BY batch_id;
-- 期望比本地 13,460 少约 30-40%(ODS-023b 清掉占位 TA 后的降级)

-- 7.4 pg_stat_statements Top 20(确认 create_distributed_table 不在 Top)
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;
-- 期望 Top 20 里没有 create_distributed_table(说明代码改造成功)
```

---

## 8. 自主修复授权(继承 prompt 28)

### 能自主改

| 类 | 示例 |
|---|---|
| SQL 类型溢出 / 语法错误 | 加 `::numeric` 兜底、`::bigint` 溢出换类型 |
| Python `NoneType` / `KeyError` | 加 guard |
| 分布式查询跑太慢 | 建索引 / `ANALYZE` / 改 CTE 为 MATERIALIZED |
| Citus 特有错误 | 比如 `UPDATE` 不能对 dist col、修 colocation、改 `SET citus.multi_shard_modify_mode='parallel'` |
| `create_distributed_table` 失败 | 看分布键类型,改成兼容类型 |
| 代码改造漏了的 CTAS / 漏了 schema rename | 直接补 |

### 必须先问用户

| 类 | 为什么 |
|---|---|
| 调阈值(`max_age_sec`、`min_cluster_dev_count`、`dbscan_eps_m` 等) | 改变判定结果 |
| 改 ODS 规则语义 | 业务规则 |
| 改 `trusted_*_library` schema | 下游兼容 |
| `DELETE` / `UPDATE` 已有批次的持久化表 | 不可逆 |
| 跳过 §7 验收硬项 | 质量门槛 |
| 删除/修改旧库(5433/ip_loc2) | **严禁**,只读 |

### 自主修复流程

1. 报错 / 异常留记录(截图、精确报错行)
2. 最小改动
3. Python 语法校验:`python3 -m py_compile xxx.py`
4. 跑最小 SQL 验证
5. 继续原流程
6. 在 `rb5_bench.notes` 或报告里列:文件 + 行号 + 改动 diff 概要 + 影响面

---

## 9. 交付物

### 9.1 数据(yangca 库,保留)

| 产出 | 备注 |
|---|---|
| `rb5.raw_gps_full_backup`(2544 万行,底表) | distributed on `did` |
| `rb5.raw_gps`(日级工作表,每关重建) | distributed on `did`,colocate_with raw_gps_full_backup |
| `rb5.etl_parsed / etl_cleaned / etl_filled` | distributed on `dev_id`,colocate_with raw_gps_full_backup(列名不同,类型兼容) |
| `rb5.cell_sliding_window` / `cell_daily_centroid` / `cell_centroid_detail` / `cell_radius_stats` / `cell_core_gps_day_dedup` | distributed on cell_id |
| `rb5.label_results` / `_label_*` | distributed on cell_id |
| `rb5.trusted_cell_library` | 7 批,distributed on cell_id |
| `rb5.trusted_bs_library` | 7 批,distributed on bs_id 或 reference |
| `rb5.trusted_lac_library` | 7 批 |
| `rb5_meta.*` | reference tables |

### 9.2 控制面(`rb5_bench.*`)

- `rb5_bench.run_results` 新增行(run_id='r31_fullrun_dayN')记录每天的耗时、CPU、WAL
- `rb5_bench.notes` 记改造过程、发现、意外
- `rb5_bench.report` 新建行(report_name='optinet_rebuild5_fullrun_YYYYMMDD')

### 9.3 markdown 报告副本

在你工作目录(= repo 根)留一份:
`/Users/yangcongan/cursor/WangYou_Data/optinet_rebuild5_fullrun_YYYYMMDD.md`

### 9.4 代码改动

**不要 commit**。只是改文件。用户会在 Step C 手工 `git diff` + review + commit。
**不要 git add / git push**。

可以 `git status` / `git diff` 给自己看。

### 9.5 完成信号

```sql
INSERT INTO rb5_bench.notes (topic, severity, body) VALUES (
  'FULLRUN_COMPLETE','info',
  '全量 7 批重跑完成 + 代码 Citus 化改造完成(未 commit)。报告见 rb5_bench.report 最新一行。'
);
```

### 9.6 报告必答 6 问

1. **代码改造统计**:改了多少文件?多少行?grep 方式验证所有 rebuild5.* 都换成 rb5.*
2. **数据迁移耗时**:2544 万行从旧库灌到新库用了多久?shard 分布均匀度?
3. **7 批全量 rerun 总耗时**:对比 Round 2 外推的 92 分钟,实际多少?并发度多少?
4. **新规则落地效果**:ODS-023b / ODS-024b / k_eff 新规则,每条在 batch 7 上比本地原 batch 7 数据有什么差异(行数、分布)?
5. **Top 20 SQL**:有没有慢 SQL 漏掉优化?create_distributed_table 是否已经不在 Top 里?
6. **给 Step C 的交接清单**:你改了哪些代码文件?哪些文件有 TODO 让用户补?哪些地方用户 review 时要特别注意?

---

## 10. 不要做的事

- ❌ 不要 commit 任何代码改动
- ❌ 不要 git push
- ❌ 不要改 uvicorn / 前端(本轮只管 pipeline 代码)
- ❌ 不要动旧库 `5433/ip_loc2`(只读)
- ❌ 不要 DROP Round 1 的 `optinet_rebuild5_sandbox` 库
- ❌ 不要 DROP `yangca.rb5_src / rb5_etl / rb5_pipe / rb5_bench`(Round 2 数据保留)
- ❌ 不要改 `fsync` / `synchronous_commit`
- ❌ 不要跳过 §5 预跑就冲 §6 全量
- ❌ 不确定就停下来写 `rb5_bench.notes` severity='suspect'

---

## 11. 完成后

1. `rb5_bench.notes` 最后一条 `FULLRUN_COMPLETE`
2. `rb5_bench.report` 有完整 md
3. 仓库根目录有 `optinet_rebuild5_fullrun_YYYYMMDD.md`
4. 代码改动**在工作目录**但**未 commit**,用户能看到 `git status` 列出一批 modified

上游(Claude + 用户)会:
- MCP 验证 `rb5.trusted_cell_library` 7 批、新规则效果
- `git diff` review 代码改动
- `git commit` 归档
- 更新本地 `docs/` 里的相关文档
- 决定是否把 `backend/app/core/database.py` 的默认 DSN 彻底切到 Citus(prod 开关)
