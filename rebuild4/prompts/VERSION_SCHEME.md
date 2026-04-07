# 数据版本体系

## 概述

rebuild4 的数据处理分为两个阶段，每个阶段独立版本化。加上数据范围（scope），形成三维版本标识。

## 三个维度

### 1. Scope（数据范围）

描述本次处理的输入数据覆盖范围。

| Scope | 含义 | 数据量级 |
|-------|------|----------|
| `sample` | 6 个样本 LAC（移动/联通/电信 × 4G/5G） | ~42 万条 fact_standardized |
| `7d` | 完整 7 天数据 | ~8200 万条 |
| `30d` | 30 天扩展数据 | 待定 |

Scope 不是版本号，而是**输入条件**。同一套处理逻辑可以在不同 scope 上运行。

### 2. Init Version（初始化版本）`i001`, `i002`...

描述第一阶段（初始化）的处理逻辑版本。

初始化是对某个数据源的一次性全量处理，包含完整的 11 步流程：
- STANDARDIZE → COMPLIANCE_CHECK → LAC_BOUNDARY → CELL_PROMOTE → DERIVE_BS → DERIVE_LAC → GOVERNANCE → ANOMALY_DETECT → REGRESSION → BASELINE_V1

每当初始化逻辑发生变化（如阈值调整、规则修改），递增版本号。

### 3. Stream Version（流式处理版本）`s001`, `s002`...

描述第二阶段（流式/滚动处理）的处理逻辑版本。

流式处理以固定时间间隔（当前规划 2 小时）重复执行规则链：
- 增量数据 ETL → Cell 累积更新 → 晋升规则 → 四分流 → 异常检测

每当流式处理的规则或参数变化，递增版本号。

## 版本组合

完整标识格式：`{scope}.{init_version}.{stream_version}`

示例：
- `sample.i001.s001` — 样本数据，第一版初始化，第一版流式规则
- `7d.i001.s001` — 7 天全量，沿用同一套逻辑
- `sample.i002.s001` — 样本数据，调整了初始化参数（如可信库阈值）
- `sample.i001.s002` — 样本数据，调整了流式规则（如异常检测参数）

## ETL 与版本的关系

ETL（原始数据解析 + ODS 清洗）是**通用基础设施**，不带版本号。

```
ETL（通用，无版本）
  ↓ 输入 scope: sample / 7d / 30d
初始化（i001, i002...）— 逻辑版本化
  ↓ 同一个 init 版本可以跑多套流式规则
流式处理（s001, s002...）— 逻辑版本化
```

ETL 的**执行记录**需要标记它处理的 scope，但 ETL 规则本身（JSON 解析、字段映射、ODS 清洗）是固定的。

## 数据库记录

### pipeline_run 表（rebuild4_meta schema）

每次管道执行记录一行：

```sql
CREATE TABLE IF NOT EXISTS rebuild4_meta.pipeline_run (
    run_id          TEXT PRIMARY KEY,           -- 如 'sample.i001.s001.20260407T120000'
    scope           TEXT NOT NULL,              -- 'sample' / '7d' / '30d'
    init_version    TEXT NOT NULL,              -- 'i001'
    stream_version  TEXT,                       -- 's001'（初始化阶段可为 NULL）
    phase           TEXT NOT NULL,              -- 'etl' / 'init' / 'stream'
    status          TEXT NOT NULL DEFAULT 'running', -- 'running' / 'completed' / 'failed'
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    input_count     BIGINT,
    output_count    BIGINT,
    metadata        JSONB                       -- 额外参数、阈值快照等
);
```

### 当前阶段

我们当前处于：**`sample.i001`**（样本数据，第一版初始化），尚未进入流式处理阶段。
