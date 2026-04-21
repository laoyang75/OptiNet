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

## 8. 相关文档

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
