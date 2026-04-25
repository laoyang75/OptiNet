# cell_infos 远漂问题分析与修复

> **创建日期**：2026-04-21
> **范围**：ETL Step 1 `parse.py::_parse_cell_infos`
> **严重度**：P1 — 系统性污染下游 cell drift / collision 判定
> **代表性 case**：cell 5751357441（46000 / lac=2097279 / bs_id=1404140 / 5G）

---

## 0. TL;DR

- **现象**：多个 cell 被错误判为 `collision / dual_cluster / migration / uncertain`，根源是远漂点污染了质心
- **根因**：ETL 把 `cell_infos` JSON 里"标 `isConnected=1` 但其实是设备启动后的历史缓存"的对象当成"当前连接" emit 了记录
- **过滤字段存在，但维度不在单条 cell 字段上** — 要用 `past_time - timeStamp/1000` 差值判定"数据年龄"
- **修复**：`age > max_age_sec (默认 300s)` 视为旧缓存，不 emit
- **抽样验证**：1% 全库 228,629 条报文，方案生效将过滤 15.6% 的 emit 行
- **参数化**：`max_age_sec` 写入 `config/antitoxin_params.yaml` 的新 section `etl_cell_infos`，不硬编码

---

## 1. 问题案例

### 1.1 cell 5751357441 的 6 批表现

| batch | p50 | p90 | center | drift_pattern | k_eff | 副簇 obs/dev |
|---|---|---|---|---|---|---|
| 2 | 55 | 23,991 | 117.249, 40.634 | insufficient | 0 | — |
| 3 | 48 | 14,901 | 117.249, 40.634 | oversize_single | 1 | — |
| 4 | 46,723 | 63,132 | 116.834, 40.360 | oversize_single | 1 | — |
| 5 | 23,577 | 82,971 | 117.041, 40.503 | oversize_single | 1 | — |
| 6 | **50** | **83** | 117.249, 40.634 | **stable** | 0 | — |
| 7 | 88 | **69,443** | 117.249, 40.634 | **collision** | 2 | **5 obs / 1 dev** |

batch 7 被判 collision 的证据（`cell_centroid_detail`）：

| cluster | center | obs | dev | share | 距主簇 |
|---|---|---|---|---|---|
| 0 主 | 117.249, 40.634（密云/怀柔） | 14 | 12 | 73.7% | — |
| 1 副 | 116.695, 39.801（房山/大兴） | 5 | **1** | 26.3% | **103.8 km** |

### 1.2 副簇的全部 5 个点追到同一台设备

`RALR2TC3G4910Q53S` 在 batch 2/3/4/6/7 每批 1 个点，坐标**精确一致**（116.69513, 39.80112），距主簇中心 103.8 km，物理上不可能是 5G 基站覆盖范围。

### 1.3 原始报文追源

从 `rebuild5.raw_gps` 取出这 5 条报文的 `cell_infos` JSON，每条都是如下结构：

```json
{
  "1": {
    "timeStamp": 3381708859,          // ← 当次新测量（设备启动后毫秒）
    "isConnected": 1,
    "past_time": "3381717.276370415", // ← 上报时刻设备启动秒数
    "cell_identity": { "Nci": 5749874690, ... }   // ← 真实当前连接
  },
  "2": {
    "timeStamp": 3362512568,          // ← 5 批完全一致的旧值
    "isConnected": 1,
    "past_time": "3381717.276370415", // ← 与对象 1 相同
    "cell_identity": { "Nci": 5751357441, ... }   // ← 旧缓存，但被标连接
  }
}
```

"数据年龄" `age = past_time - timeStamp / 1000`：

| ts | obj 1 age | obj 2 age | 判定（阈值 300s） |
|---|---|---|---|
| 2025-12-02 15:25:39 | 8.42 s | 19,204.71 s (5.3 h) | obj 2 DROP |
| 2025-12-03 06:10:23 | 8.02 s | 72,288.01 s (20.1 h) | obj 2 DROP |
| 2025-12-04 06:36:57 | 7.40 s | 160,282.82 s (1.85 d) | obj 2 DROP |
| 2025-12-06 06:41:16 | 9.00 s | 333,342.29 s (3.86 d) | obj 2 DROP |
| 2025-12-07 07:09:20 | 6.44 s | 421,425.39 s (4.88 d) | obj 2 DROP |

对象 "2" 的 `timeStamp` 五天不变，`past_time` 线性增长 → 这是设备启动后一次测量被缓存，之后从未刷新，却每次都被上报。

---

## 2. 根因分析

### 2.1 cell_infos 字段语义

| 字段 | 单位 | 含义 | 基准 |
|---|---|---|---|
| `timeStamp` | 毫秒 | 设备启动到该 cell 测量的时间 | 设备内部单调时钟 |
| `past_time` | 秒 | 当次上报时设备启动经过的秒数 | 设备内部单调时钟 |
| `isConnected` | 0/1 | 是否标记为连接 | SDK 自己判断 |

**关键事实**：`timeStamp` 和 `past_time` 都基于设备启动后的**单调计数器**，不依赖用户手机的壁钟时间。因此 `past_time - timeStamp/1000` 即使用户系统时间错乱也仍然准确反映"数据新鲜度"。

### 2.2 ETL 当前逻辑（`parse.py::_parse_cell_infos`）

```sql
FROM rebuild5.raw_gps r,
     jsonb_each(NULLIF(btrim(r."cell_infos"), '')::jsonb) AS e(key, cell)
WHERE r."cell_infos" IS NOT NULL
  AND length(r."cell_infos") > 5
  AND (e.cell->>'isConnected')::int = 1    -- ★ 只看 isConnected，没有 age 校验
  AND COALESCE(Ci/Nci/nci/cid) IS NOT NULL
```

**问题**：只要 `isConnected=1` 就 emit。SDK 把"启动后的历史缓存"也标 `isConnected=1`，ETL 不校验，全部进入 `etl_cleaned`。

### 2.3 下游连锁反应

```
cell_infos 残留 isConnected=1 缓存
  ↓ emit 一条 etl_cleaned 行，关联设备当前真实 GPS（远点）
Step 2 snapshot_seed_records
  ↓ 视为该 cell 的观测证据
Step 3 cell_sliding_window
  ↓ 远点进入质心计算
Step 4 cell_centroid_detail
  ↓ 2 个质心位置 > 100km
Step 5 label_engine.drift_pattern = collision
```

---

## 3. 修复原理（通用，不依赖具体实现）

### 3.1 核心判定规则

对 `cell_infos` JSON 的每个对象，仅当**同时满足**以下条件才作为"当前连接" emit 一条记录：

```
isConnected == 1
AND past_time - timeStamp / 1000 <= max_age_sec   # 数据年龄不超过阈值
```

`max_age_sec` 默认 300 秒（5 分钟），必须**可配置**。

### 3.2 为什么不用"取 MAX(timeStamp) 一条"

- **误伤 NSA 双连接**：5G 非独立组网场景下 4G 锚点 + 5G NR 可能同时有效，两个对象的 `timeStamp` 接近但不等，若强制取最大会丢一个合法连接
- **不考虑 age**：如果多个对象都是新鲜的，只取最大没道理把另一个去掉

### 3.3 为什么不用"取 key = '1'"

- SDK 不保证 key "1" 一定是当前连接（观察到部分报文里 "1" 就是缓存）
- 依赖实现细节，不鲁棒

### 3.4 为什么阈值选 300 秒（5 分钟）

- 设备移动 5 分钟最远覆盖几百米，cell 切换频繁但不会跨城
- 实测本 case 的 stale 对象 age 在 5 小时~4.9 天，远高于 300 秒
- 全库 1% 抽样显示"多连接含 stale"的 age 几乎全部远超此值（见 §5.2）
- 300 秒是安全起点，上线后可按实际分布调整

### 3.5 边界处理（保守原则）

| 场景 | 处理 | 理由 |
|---|---|---|
| `timeStamp` 字段缺失 | **KEEP** | 宁可放行，不因字段缺失误杀 |
| `past_time` 字段缺失 | **KEEP** | 同上 |
| 字段非数字格式 | **KEEP** | 数据畸形，交由下游清洗 |
| `age < 0`（数据矛盾）| **KEEP** | 小概率数值扰动不误伤 |
| `age <= max_age_sec` | **KEEP** | 新鲜数据 |
| `age > max_age_sec` | **DROP** | 确认旧缓存 |

"字段缺失 = KEEP"保证**最大限度不破坏现有行为**，只在明确的"旧缓存"证据上做减法。

### 3.6 参数必须可配置

- **不要硬编码 300**：不同数据集、不同 SDK 版本、不同业务场景可能需要不同阈值
- 变更阈值不应需要改代码、发版
- 建议通过项目现有 YAML 配置机制暴露

### 3.7 ss1 通道无此问题（对照参考）

`ss1` 字段格式：`l,-90,-90,-7,4+&1764808564&0&0&0;l,-89,-89,-5,9+&1764808694&0&0&0;...`

每条子记录自带 unix 毫秒时间戳（壁钟时间），各条独立，没有 `isConnected` / 缓存语义，**无需做等价过滤**。ss1 层本就是"过去一段时间的信号强度时序"，多条是应有行为。

---

## 4. rebuild5 当前代码的修复方案

### 4.1 修改点

| 文件 | 改动 |
|---|---|
| `rebuild5/config/antitoxin_params.yaml` | 新增顶层 section `etl_cell_infos:` |
| `rebuild5/backend/app/etl/parse.py` | 引入配置加载 + SQL WHERE 子句加 age 过滤 |

不改 `ss1` 相关代码。

### 4.2 配置增量

在 `rebuild5/config/antitoxin_params.yaml` 末尾追加（顶层 section）：

```yaml
etl_cell_infos:
  # 单条报文内，cell_infos 的每个对象，past_time - timeStamp/1000 > max_age_sec
  # 视为"设备启动后的历史缓存"，不 emit 到 etl_ci。
  # past_time 和 timeStamp 都基于设备内部单调计数器，不受用户壁钟时间影响。
  # 2026-04-21 新增（修复 cell_infos 旧缓存被误判为当前连接的问题）
  max_age_sec: 300
```

### 4.3 代码 diff（`parse.py`）

顶部新增一个轻量加载函数（不跨模块引用以保持 ETL 独立性）：

```python
# parse.py 顶部
from pathlib import Path
import yaml

from .source_prep import DATASET_KEY
from ..core.database import execute, fetchone
from ..core.settings import settings


_CELL_INFOS_CFG_CACHE: dict | None = None


def _load_cell_infos_cfg() -> dict:
    global _CELL_INFOS_CFG_CACHE
    if _CELL_INFOS_CFG_CACHE is not None:
        return _CELL_INFOS_CFG_CACHE
    path = settings.antitoxin_params_path
    if not path.exists():
        _CELL_INFOS_CFG_CACHE = {'max_age_sec': 300.0}
        return _CELL_INFOS_CFG_CACHE
    with path.open('r', encoding='utf-8') as f:
        payload = yaml.safe_load(f) or {}
    cfg = payload.get('etl_cell_infos', {}) or {}
    _CELL_INFOS_CFG_CACHE = {
        'max_age_sec': float(cfg.get('max_age_sec', 300)),
    }
    return _CELL_INFOS_CFG_CACHE
```

在 `_parse_cell_infos()` 内把 `max_age_sec` 嵌入 WHERE 子句（**在现有 `isConnected=1` 条件后追加，不改动任何其他列）：

```python
def _parse_cell_infos(source_table: str, source_tag: str, target_table: str) -> None:
    max_age_sec = _load_cell_infos_cfg()['max_age_sec']
    execute(f'DROP TABLE IF EXISTS {target_table}')
    execute(
        f"""
        CREATE TABLE {target_table} AS
        SELECT
            ... -- 现有所有列保持不变
        FROM {source_table} r,
            jsonb_each(NULLIF(btrim(r."cell_infos"), '')::jsonb) AS e(key, cell)
        WHERE r."cell_infos" IS NOT NULL
          AND length(r."cell_infos") > 5
          AND (e.cell->>'isConnected')::int = 1
          AND COALESCE(
                e.cell->'cell_identity'->>'Ci',
                e.cell->'cell_identity'->>'Nci',
                e.cell->'cell_identity'->>'nci',
                e.cell->'cell_identity'->>'cid'
              ) IS NOT NULL
          -- ★ 新增：旧缓存过滤（字段缺失或格式异常时 KEEP）
          AND (
              e.cell->>'timeStamp' IS NULL
              OR e.cell->>'past_time' IS NULL
              OR NOT (e.cell->>'timeStamp' ~ '^[0-9]+$')
              OR NOT (e.cell->>'past_time' ~ '^[0-9]+(\\.[0-9]+)?$')
              OR (
                  (e.cell->>'past_time')::numeric
                  - (e.cell->>'timeStamp')::numeric / 1000.0
                  <= {max_age_sec}
              )
          )
        """
    )
```

### 4.4 变更范围承诺

- 不改 `_parse_ss1` 任何行为
- 不改 `etl_ci` / `etl_parsed` 的列 schema
- 不改下游 Step 2-5 任何代码
- 可通过调整 YAML 阈值回退（`max_age_sec: 99999999` 等效退回当前行为）

---

## 5. 验证

### 5.1 精确 case 验证（已知问题的 5 条报文）

脚本逻辑（只读 SQL，不改数据）：

```sql
WITH target AS (
  SELECT * FROM rebuild5.raw_gps
  WHERE "did" = 'RALR2TC3G4910Q53S'
    AND "ts" IN ('2025-12-02 15:25:39','2025-12-03 06:10:23','2025-12-04 06:36:57',
                 '2025-12-06 06:41:16','2025-12-07 07:09:20')
),
expanded AS (
  SELECT r."记录数唯一标识" AS uid, r."ts" AS ts, e.key AS obj_key,
         (e.cell->>'timeStamp')::bigint AS ts_ms,
         (e.cell->>'past_time')::float AS past_sec,
         (e.cell->'cell_identity'->>'Nci')::bigint AS nci,
         (e.cell->>'isConnected')::int AS connected,
         (e.cell->>'past_time')::float
         - (e.cell->>'timeStamp')::bigint / 1000.0 AS age_sec
  FROM target r, jsonb_each(NULLIF(btrim(r."cell_infos"), '')::jsonb) AS e(key, cell)
)
SELECT ts, obj_key, nci, connected, ROUND(age_sec::numeric, 2) AS age_sec,
       CASE WHEN connected = 1 AND age_sec <= 300 THEN 'KEEP'
            WHEN connected = 1 AND age_sec > 300 THEN 'DROP (stale cache)'
            ELSE 'DROP (not connected)' END AS decision_300s
FROM expanded ORDER BY ts, obj_key;
```

**结果**：10 个对象里 5 个 "当前连接" (Nci=5749874690, age 6.4~9.0 s) 全部 KEEP，5 个 "旧缓存" (Nci=5751357441, age 5.3 h ~ 4.9 d) 全部 DROP。**方案对 cell 5751357441 的污染点 100% 识别**。

### 5.2 全库影响面（1% 随机抽样）

```sql
-- 简化版（完整版见 §附）
WITH sample AS (
  SELECT * FROM rebuild5.raw_gps
  WHERE "cell_infos" IS NOT NULL AND length("cell_infos") > 5
    AND random() < 0.01
),
expanded AS (
  SELECT r."记录数唯一标识" AS uid,
         CASE WHEN e.cell->>'timeStamp' ~ '^[0-9]+$'
              THEN (e.cell->>'timeStamp')::numeric END AS ts_ms,
         CASE WHEN e.cell->>'past_time' ~ '^[0-9]+(\.[0-9]+)?$'
              THEN (e.cell->>'past_time')::numeric END AS past_sec,
         (e.cell->>'isConnected')::int AS connected
  FROM sample r, jsonb_each(NULLIF(btrim(r."cell_infos"), '')::jsonb) AS e(key, cell)
),
per_record AS (
  SELECT uid,
         COUNT(*) FILTER (WHERE connected = 1) AS conn_cnt,
         COUNT(*) FILTER (WHERE connected = 1
                          AND ts_ms IS NOT NULL AND past_sec IS NOT NULL
                          AND past_sec - ts_ms/1000.0 <= 300) AS fresh_cnt,
         COUNT(*) FILTER (WHERE connected = 1
                          AND ts_ms IS NOT NULL AND past_sec IS NOT NULL
                          AND past_sec - ts_ms/1000.0 > 300) AS stale_cnt
  FROM expanded GROUP BY uid
)
SELECT ... FROM per_record;
```

**抽样结果（228,629 条报文）**：

| 指标 | 数值 | 占比 |
|---|---|---|
| 零连接报文（所有对象 isConnected=0）| 33,562 | 14.7% |
| 单连接报文（仅 1 个 isConnected=1）| 102,429 | 44.8% |
| 多连接报文（≥ 2 个 isConnected=1）| 92,638 | 40.5% |
| ├ 其中含 stale（age>300s）| 30,928 | 13.5%（占多连接的 33.4%）|
| └ 全 stale（无 fresh）| 14,008 | 6.1% |
| 总 emit 行数 | 287,729 | — |
| **方案 C 会 drop 的行数** | **44,936** | **15.6%** |
| 字段缺失无法判 age（按 KEEP）| 2,407 | 0.84% |

### 5.3 预期 downstream 效果

- cell 5751357441 batch 7 的副簇消失 → `k_eff = 1` → `drift_pattern = oversize_single` 或回到更合理状态，不再触发 collision
- batch 6 的"假 stable"问题部分缓解（但 stable 判定还有其他因素，不完全解决）
- 大量"单设备多天同坐标"污染型 case 系统性消除

---

## 6. 部署路径

1. **Step A**：在样例数据集上先跑（按 `rebuild5/prompts/28_rerun_full_chain_pipelined.md` §2.5 流程）
2. **Step B**：对比指标
   - `etl_cleaned` 行数变化应接近 -15.6%
   - `cell 5751357441` 的 batch 7 drift_pattern 不应再为 collision
   - `drift_distribution` 整体 stable 比例应微升
3. **Step C**：样例通过后再启动 7 天全量重跑
4. **Step D**：观察 2-3 个批次后决定是否需要调整 `max_age_sec`

---

## 7. 遗留问题

1. **"全 stale 报文"** 6.1%：方案生效后它们产出 0 条 cell 记录。这些设备在那段时间"看不见"，需观察是否对某些 cell 的可见性造成影响。
2. **字段缺失 KEEP** 0.84%：这些点仍然进入下游，如果它们集中在某些 cell 上仍可能造成漂移，但量级很小。
3. **"单设备一次性真实飞跃"**：若设备真的飞到远点（飞机/地铁快速移动），一条报文的 age 就是新鲜的，本方案不过滤。需另用簇层面的 `dev_count ≥ 2` 门槛等机制（见 `multi_centroid_v2.min_cluster_dev_day_pts` 的后续讨论）。
4. **NSA 双连接场景保留**：方案允许同报文多条新鲜连接。这是有意为之，但需观察双连接点对质心计算的影响（正常情况下 4G/5G 同点物理位置相同，不会放大质心半径）。

---

## 8. 案例 2：cell 1353583（SS1 通道缓存污染）

ODS-019（cell_infos 陈旧缓存过滤）在全量重跑里每天 drop 60+ 万对象（15.6%）已生效，但 cell `1353583` 在 batch 7 仍被判 `insufficient` 且 p90=1438 km —— 追源发现污染从**另一条通道 `ss1`** 进来，ODS-019 覆盖不到。

### 8.1 现象

| batch | drift_pattern | p90 (m) | gps_valid | devs | k_eff | label |
|---|---|---|---|---|---|---|
| 5 | insufficient | 1,438,278 | 5 | 5 | 0 | insufficient |
| 6 | insufficient | 1,438,232 | 7 | 6 | 0 | insufficient |
| 7 | insufficient | 1,438,226 | 9 | 7 | 0 | insufficient |

`independent_obs=217`（所有观察点数）看起来够，但 label 判定用的 `gps_valid_count=9` 很少，且这 9 个 raw_gps 点 p50=248m / p90=1438km 极端分散，DBSCAN eps=250m 聚不出簇。

### 8.2 根因 — `ss1` 的 `cell_block` 混入 SDK 缓存

设备 `A3JS3I8PTCORK0GOB` 实际在重庆，但该设备每条 `ss1` 子记录的 `cell_block` 都携带：

```
n,13707288577,2490382,46000   ← 卡1 NR 5G，真实连接（重庆）
+ l,1353583,6423,46001          ← 卡2 LTE 4G，cell_id=1353583（北京，SDK 历史缓存）
```

一台手机的双卡不可能相距 1400 km，但 SDK 在卡2 实际未活跃时仍在 `cell_block` 里保留了"上次卡2 连过的 cell_id"。原 ETL 的 `LEFT JOIN` 把两张卡的 cell 都 emit，卡2 被错误地关联到卡1 的真实 GPS（重庆），污染北京 cell 1353583。

### 8.3 实测数据分布（决策依据）

| 形态 | 占比 | 含义 |
|---|---|---|
| 单卡 `(cell=1, sig=1)` | 38.4% | 正常 |
| 双卡单信号 `(cell=2, sig=1)` | **29.4%** | ★ cell 1353583 类污染 |
| 双卡双信号 `(cell=2, sig=2)` | **0.31%** | 真 NSA 双连接（罕见）|
| 其他 | 32% | 空 cell / 空 sig 等 |

真"双卡同时报双信号"只占 0.31% → 绝大多数双卡场景的第二张 cell 是缓存 cell_id。

### 8.4 修复 — ODS-020 / 021 / 022

| 规则 | 动作 |
|---|---|
| **ODS-020** | `ss1` 批内以 `max(ts_sec)` 为锚点，age > 3600s 的子记录（SDK 隔夜残留）丢弃 |
| **ODS-021** | `cells × sigs` `LEFT JOIN` → `INNER JOIN`，无配套 sig 的 cell 不 emit（直接清除卡2 缓存 cell_id 类污染）|
| **ODS-022** | sig 条目四值全 -1 视为无效，丢整条 sig |

### 8.5 预期效果

- cell 1353583 在 batch 7 的 8 条重庆点（来自卡2 LTE 无配套 sig）在 ODS-021 被直接丢
- 下次重跑后 cell 1353583 的 `gps_valid_count` 会显著下降（约剩 1-2 个真正来自卡1 的点），结果是 **p90 回归合理范围**
- `insufficient` 判定可能保留（因真实数据不足），但不再有 p90=1438km 的误导性显示

### 8.6 与 ODS-019 的关系

| 维度 | ODS-019 | ODS-020 / 021 / 022 |
|---|---|---|
| 通道 | `cell_infos` | `ss1` |
| 过滤粒度 | 单对象（JSON 里 `isConnected=1` 的历史缓存）| 子记录（批内锚点外）+ cell（无配套 sig）+ sig（全 -1）|
| 时间依据 | 设备内部单调计数器（`past_time` - `timeStamp/1000`）| unix 壁钟时间戳（`batch_max_ts_sec` - `ts_sec`）|
| 互相关系 | 独立，两条通道都要分别治理，下游并存 | 同上 |

两套规则互补，共同治理 SDK 层的 cache 污染问题。

---

## 9. 案例 3：cell 21330987（纳秒 timeStamp + 单设备跨天簇）

ODS-019 + ODS-020/021/022 已修复"cell_infos 对象陈旧缓存"和"ss1 缓存 cell"两类污染，但 cell `21330987` 在 batch 7 仍被判 `oversize_single`（p90=20km），追源发现**两个新的规则缺口**：

### 9.1 现象

| batch | p90 | drift_pattern | 中心 | 说明 |
|---|---|---|---|---|
| 5 | 53 m | stable | 海淀 | 假 stable（只有 E781VF 一个设备连续 5 天）|
| 6 | 52 m | stable | 海淀 | 同上 |
| 7 | 20,233 m | oversize_single | 亦庄 | 其他 7 个设备显现 + E781VF 12-07 去了大兴 |

### 9.2 根因 A：cell_infos 的 timeStamp 是**纳秒**，ODS-019 原按毫秒处理失效

E781VF 的一条 cell_infos JSON：

```json
{
  "1": {
    "timeStamp": 71904320400064,         // 14 位 → 是纳秒！按毫秒解读得荒谬大数
    "isConnected": 1,
    "past_time": "490628.900239044",      // 约 5.7 天
    "cell_identity": { "Ci": 21330987 }
  },
  "2": {
    "timeStamp": 490512095858853,         // 15 位纳秒（当前真实连接）
    "cell_identity": { "Ci": 127845763 }  // 设备当前真连的 cell
  }
}
```

按纳秒 `/ 10^9`：
- 对象 "1" age = 490,628 - 71,904 = **418,724 秒 ≈ 4.85 天** → **应被 ODS-019 丢弃**
- 对象 "2" age = 490,628 - 490,512 = 116 秒 → KEEP（真实当前连接）

但原 ODS-019 按毫秒 `/ 10^3`：
- 对象 "1" age = 490628 - 71,904,320,400 = **-71,903,829,772**（巨大负数）→ 负数 ≤ 300 → **漏判 KEEP** ❌

### 9.3 根因 B：单设备跨多天贡献多个 dev-day，DBSCAN 成"假簇"

cell 21330987 batch 7 的 14 个 dev-day 点分布：

| 位置 | dev-day 数 | 不同设备数 | 含义 |
|---|---|---|---|
| 海淀主心 | 6 | **1**（全 E781VF）| 单设备跨 6 天反复刷 |
| 亦庄群 | 7 | **7**（7 个不同 dev）| 多样性真实位置 |
| 大兴 | 1 | 1（E781VF 12-07 出行）| 离群 |

按旧规则 `dev_day_pts >= 4` 成簇 → 海淀 6 点（全 E781VF）成簇 `dev_day_pts=6` ✓ → **错判为有效簇**

问题本质：**"同一设备多天重复" 不应等同于 "多个独立设备共同确认"**。

### 9.4 全库统计证据

| timeStamp 长度 | 占比 | 单位 |
|---|---|---|
| 5-13 位 | 约 91% | 毫秒 |
| **14-16 位** | **约 9%** | **纳秒** |
| ≥17 位 | < 0.3% | 纳秒或更大 |

约 9% 的设备使用纳秒级 timeStamp，ODS-019 原实现对这部分完全失效。

### 9.5 修复（2025-04-21）

**修复 1 — ODS-019 timeStamp 单位自动识别**：

```sql
-- parse.py::_parse_cell_infos WHERE 子句
CASE
  WHEN length(e.cell->>'timeStamp') <= 13
       THEN (e.cell->>'timeStamp')::bigint / 1000         -- 毫秒 → 秒
  ELSE (e.cell->>'timeStamp')::bigint / 1000000000        -- 纳秒 → 秒
END
```

**修复 2 — ODS-024 簇最小设备数门槛**：

```sql
-- label_engine.py::valid_clusters WHERE + k_eff FILTER
WHERE c.dev_day_pts >= {min_cluster_dev_day_pts}
  AND c.dev_count >= {min_cluster_dev_count}   -- ★ 默认 2
```

配置项：`antitoxin_params.yaml::multi_centroid_v2.min_cluster_dev_count: 2`

**修复 3 — DBSCAN eps 放宽**：`250m → 500m`（应对城市 cell 覆盖实际半径）

### 9.6 修复后对 cell 21330987 batch 7 的预期

- 对象 "1" 纳秒识别生效 → E781VF 海淀 6 个 dev-day 全是陈旧缓存 → ODS-019 在 parse 阶段丢
- 即使个别缓存漏过，DBSCAN 成簇时也受 `dev_count >= 2` 制约，单设备簇作废
- 亦庄 7 个不同设备，DBSCAN eps=500 可能聚成簇（之前 250m 聚不到）
- **结果**：drift_pattern 应回归 `stable`（亦庄成主簇）或 `insufficient`（如果 ODS-019 清除太多）

### 9.7 相关规则总览

| 规则 | 作用 | 位置 |
|---|---|---|
| ODS-019 | cell_infos 对象 age 过滤 | `parse.py::_parse_cell_infos` |
| ODS-020 | ss1 批内锚点陈旧过滤 | `parse.py::_parse_ss1` |
| ODS-021 | ss1 无信号 cell 过滤 | `parse.py::_parse_ss1` |
| ODS-022 | ss1 全 -1 sig 过滤 | `parse.py::_parse_ss1` |
| **ODS-024** | **簇最小设备数门槛** | `label_engine.py::_label_ranked_clusters + _label_cell_kstats` |

---

## 案例 4：cell 20752955（天去重过严 + 10% anomaly_filter 失效）

### 基线

- **业务键**：`operator=46000, lac=4277, bs_id=81066, cell_id=20752955, tech=4G`
- **batch 7 trusted_cell_library 状态**：`drift_pattern=insufficient`、`gps_valid_count=3`、`p50=3m`、`p90=1,571,955m`（约 1572km）
- **真实位置**：北京 `(116.520, 39.942)`
- **污染点**：深圳 `(114.195, 22.330)` 单点

### 数据流追溯

raw_gps 阶段 cell 20752955 共 11 条记录，展开到 `etl_parsed` 后有 21 个子记录（gps_valid=true 18 条），涉及 3 个设备：

| 设备 | 上报次数 | 位置 | cell_infos 字段 age | rsrp |
|---|---|---|---|---|
| `AO96U2259IZ3GF4UB` | 17 次（北京）| (116.520, 39.942) | 20~60s 新鲜 | -101~-106 |
| `N3AKB283DMY0K7FDO` | 2 次（北京，batch 1 历史）| (116.520, 39.942) | 20s 新鲜 | -106 |
| `2JK1PT:0KAE:IDIH:4P000` | **1 次**（深圳）| (114.195, 22.330) | **11s 新鲜** | -77 |

三设备上报的 `(Ci, Pci, Tac, Earfcn) = (20752955, 252, 4277, 1350)` 完全一致，age 都新鲜、rsrp 都强 —— **不是陈旧缓存、不是 ss1 邻区混入、不是 ODS-024 单设备假簇**。

### 关键洞察：异常占比被 day dedup 人工放大

| 数据层 | 北京点 | 深圳点 | 异常占比 |
|---|---|---|---|
| raw_gps (gps_valid) | 19 | 1 | **5%** ✓ 低于 10% 兜底阈值 |
| `cell_core_gps_day_dedup`（dev+day）| **2** | **1** | **33%** ✗ 远超 10% |

`cell_core_gps_day_dedup` 把 AO96U 的 17 条同日同设备真实点压成 1 点，AO96U+N3AKB 只剩 2 个"北京点"，深圳 1 点占 33% → `gps_anomaly_filter.max_anomaly_ratio=10%` 条件不满足 → **不排除**异常 → DBSCAN 的 3 个千公里互距点全判 noise → `k_raw=0, k_eff=0, label=insufficient`，p90 直接取全部 3 点的 90 分位，被深圳点拉爆到 1572km。

### 20 cell 策略对比评估

设计实验：8 异常 cell + 12 正常 cell，每 cell 从 raw_gps 重新解析拿 cell_origin（规避 etl_parsed 陈旧问题），对比 4 个时间桶 × 2 个 origin 分离模式。

**关键结论**（详见附评估 SQL）：

| 策略 | cell 20752955 保留点 | p90 | 备注 |
|---|---|---|---|
| 现状 `(dev, date)` | 3 | 1576km | 异常占比 33%，10% 阈值不生效 |
| `(dev, 1d, split_origin)` | 3 | 1572km | 仍被 day 压缩 |
| `(dev, 1h, split_origin)` | 5 | ~ | 样本恢复，但 20% 仍超阈值 |
| **`(dev, 5min, split_origin)`** | **15** | **104m** | **样本恢复 5x，异常占比 ~5%，10% 阈值生效** |
| raw 全保留 | 18 | 9m | 单设备主导风险重现 |

**全 20 cell 扩大评估**：
- 异常组 8 个里 3 个完美修复（20752955 / 17539075 / 4855663）—— 都是"单远点污染 + 样本稀释"模式
- 其他 5 个异常 cell 没改善（真 collision 或单设备 dev=1）—— 需独立规则（设备观察门槛 / insufficient 兜底 collision）
- 正常组 12 个样本恢复 1.5~4.4x，p90 波动 ±10~15%，设备数 100% 不变，无误伤

### 修复（`DEDUP-V2` 规则，2026-04-22 合入）

把 Step 2 `_profile_gps_day_dedup` 和 Step 5 `cell_core_gps_day_dedup` 的 DISTINCT ON 键从：

```
(operator, lac, bs_id, cell_id, tech, dev_id, DATE(event_time_std))
```

改为：

```
(operator, lac, bs_id, cell_id, tech, dev_id, cell_origin, 5min_bucket_utc)
```

其中 `5min_bucket_utc = date_trunc('minute', ts) - ((EXTRACT(MINUTE FROM ts)::int % 5) * INTERVAL '1 minute')`。

为此需要把 `cell_origin TEXT` 字段从 `etl_cleaned` 透传到 7 张下游表（`path_a_records / _profile_path_b_records / profile_obs / profile_base / candidate_seed_history / enriched_records / snapshot_seed_records / cell_sliding_window`）。

其余不变：
- `gps_anomaly_filter.max_anomaly_ratio=10%` 保持（新语义下分母扩大 2~10x，10% 在真实密度下生效）
- `ODS-024 min_cluster_dev_count=2` 保持
- Step 3 `profile_base.p50/p90/center` 自动承接新口径，与 Step 5 精确计算对齐
- Step 3 准入判定基于 `independent_obs`（per-minute 口径，不受本规则影响）

### 未解决 / 后续方向

本规则只治"单远点污染 + day 去重稀释"这一类问题。其他尚需独立规则处理：

- **方向 A**：一次性 did（`device_total_reports = 1`）的远离主簇点降权 / 剥离 —— 针对 cell 20752955 的深圳那 1 点根治
- **方向 B**：`insufficient` 分支的 collision 兜底（`k_raw=0` 但点间最大距离 > `collision_min_dist_m` → 直接判 collision）—— 让样本不足的碰撞 cell 也能识别出来

---

## 10. 相关文档

- 案例深度分析：`rebuild5/docs/gps研究/03_Cell5731057665深度分析_修正.md`
- GPS 噪声过滤综述：`rebuild5/docs/gps研究/02_GPS噪声过滤策略汇总.md`
- 标签规则：`rebuild5/docs/gps研究/09_标签规则重构方案7_4.md`
- 异常数据研究：`rebuild5/docs/gps研究/10_异常数据研究_方案7_4后.md`
- 重跑 prompt：`rebuild5/prompts/28_rerun_full_chain_pipelined.md`

---

## 附：完整验证 SQL

（用于后续复核 / 审阅，只读，不改数据）

```sql
-- 精确 case：RALR2TC3G4910Q53S 的 5 条远漂报文
-- 见 §5.1 上文完整 SQL

-- 全库影响面抽样
WITH sample AS (
  SELECT * FROM rebuild5.raw_gps
  WHERE "cell_infos" IS NOT NULL AND length("cell_infos") > 5
    AND random() < 0.01
),
expanded AS (
  SELECT r."记录数唯一标识" AS uid,
         CASE WHEN e.cell->>'timeStamp' ~ '^[0-9]+$'
              THEN (e.cell->>'timeStamp')::numeric END AS ts_ms,
         CASE WHEN e.cell->>'past_time' ~ '^[0-9]+(\.[0-9]+)?$'
              THEN (e.cell->>'past_time')::numeric END AS past_sec,
         (e.cell->>'isConnected')::int AS connected
  FROM sample r, jsonb_each(NULLIF(btrim(r."cell_infos"), '')::jsonb) AS e(key, cell)
),
per_record AS (
  SELECT uid,
         COUNT(*) FILTER (WHERE connected = 1) AS conn_cnt,
         COUNT(*) FILTER (WHERE connected = 1 AND ts_ms IS NOT NULL AND past_sec IS NOT NULL
                          AND past_sec - ts_ms/1000.0 <= 300) AS fresh_cnt,
         COUNT(*) FILTER (WHERE connected = 1 AND ts_ms IS NOT NULL AND past_sec IS NOT NULL
                          AND past_sec - ts_ms/1000.0 > 300) AS stale_cnt,
         COUNT(*) FILTER (WHERE connected = 1 AND (ts_ms IS NULL OR past_sec IS NULL)) AS unknown_cnt
  FROM expanded GROUP BY uid
)
SELECT
  COUNT(*) AS total_reports,
  COUNT(*) FILTER (WHERE conn_cnt = 0) AS zero_connected,
  COUNT(*) FILTER (WHERE conn_cnt = 1) AS single_connected,
  COUNT(*) FILTER (WHERE conn_cnt >= 2) AS multi_connected,
  COUNT(*) FILTER (WHERE conn_cnt >= 2 AND stale_cnt > 0) AS multi_with_stale,
  COUNT(*) FILTER (WHERE fresh_cnt = 0 AND stale_cnt > 0) AS all_stale_only,
  SUM(conn_cnt) AS total_emit,
  SUM(stale_cnt) AS would_drop,
  SUM(unknown_cnt) AS unknown_age
FROM per_record;
```
