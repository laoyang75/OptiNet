# Step 1：数据源接入

> **核心目标**：把手机 SDK 上报的多种格式原始报文，转换成统一的、干净的结构化数据（`etl_cleaned`），为后续步骤提供唯一输入。

---

## 这一步在整体流程中的位置

```mermaid
flowchart LR
    RAW["📥 原始报文\n多种数据源格式"]
    S1["⚙️ Step 1\n数据源接入"]
    S2["Step 2\n基础画像"]

    RAW --> S1 --> S2

    style S1 fill:#fff9c4,stroke:#f9a825
```

**Step 1 的特殊性**：它是整个系统中**唯一不受冻结快照原则约束**的步骤。它只是一个通用 ETL 工具，不读取可信库，不做画像判断，只管"把原始数据转成结构"。

---

## 5 层处理流程

```mermaid
flowchart TD
    SRC["📋 原始数据表\n（1 张或多张，可配置）"]

    P1["1.1 数据源注册\n登记数据源元信息\n字段映射 / 导入规则"]
    P2["1.2 字段审计\n盘点字段覆盖率\n决定 keep / parse / drop"]
    P3["1.3 解析（炸开）\n一条原始报文 →\n多条结构化记录"]
    P4["1.4 清洗（ODS 过滤）\n19条规则去除无效值\n主键级错误才删行，其余置空"]
    P5["1.5 字段对齐\n同一条报文内互补\ncell_infos ↔ ss1 字段互补"]

    OUT["✅ etl_cleaned\n70列，Step 1 最终产出"]

    SRC --> P1 --> P2 --> P3 --> P4 --> P5 --> OUT

    style OUT fill:#c8e6c9,stroke:#388e3c
```

---

## 1.1 数据源注册

系统支持多个数据源（GPS 报文源、LAC 报文源等），每个数据源通过注册表接入，不硬编码表名。

**注册时需要登记的关键信息**：

| 配置项 | 说明 |
|--------|------|
| `source_id` | 数据源唯一标识 |
| `source_name` | 数据源名称 |
| `source_table` | 原始表名 |
| `source_type` | GPS 报文源 / LAC 报文源 / 其他 |
| `cell_infos_field` | JSON 格式的基站字段位置 |
| `ss1_field` | 文本格式的信号字段位置 |
| `status` | 待接入 / 已接入 / 已停用 |
| `row_count` | 记录数 |
| `time_range` | 数据时间范围 |

---

## 1.2 字段审计

在真正开始处理之前，先回答 4 个问题：

```mermaid
graph LR
    Q1["① 原始表有哪些字段？\n是否和注册配置一致？"]
    Q2["② 字段数据类型\n是否稳定？"]
    Q3["③ 字段覆盖率\n是否满足解析前提？"]
    Q4["④ 每个字段的处理决策\nkeep / parse / drop"]

    Q1 --> Q2 --> Q3 --> Q4

    RESULT["字段审计报告\n27 原始字段：\n17 keep\n3 parse（需展开解析）\n7 drop"]
    Q4 --> RESULT
```

---

## 1.3 解析（炸开）

原始报文里有两种复合字段需要展开：

```mermaid
flowchart LR
    RAW["1 条原始报文\n（249,201 条原始记录）"]

    CI["cell_infos\n（JSON格式）\n每个主服务基站 → 1行"]
    SS1["ss1\n（文本格式）\n每个信号组 → 1行"]

    OUT["etl_parsed\n689,361 行\n扩展比 ≈ 2.77x"]

    RAW -->|"展开"| CI
    RAW -->|"展开"| SS1
    CI --> OUT
    SS1 --> OUT

    NOTE["⚠️ 必须保留 record_id\n以便后续同报文对齐"]
    OUT -.- NOTE
```

**展开后要保留 `record_id`**，这是后续"同一条报文内互补"的核心依据。

---

## 1.4 清洗（ODS 规则）

19 条 ODS 规则（ODS-001 ~ ODS-018），分 6 类，两种动作：

```mermaid
flowchart TD
    IN["etl_parsed\n689,361 行"]

    R1["ODS-001~002\n运营商编码异常 → 置空"]
    R2["ODS-003~005\nLAC 异常 → 置空"]
    R3["ODS-006~008\ncell_id 不可解析/为0/溢出 → 置空\n最终删行条件：cell_id IS NULL 或 event_time_std IS NULL"]
    R4["ODS-009~012\nRSRP/RSRQ/SINR/Dbm 越界 → 置空"]
    R5["ODS-013~016\nGPS 越出中国边界 → 标记无效"]
    R6["ODS-017~018\n无效 WiFi 名称 / MAC → 置空"]

    OUT["etl_cleaned 基础列\n687,788 行\n通过率 99.77%"]

    IN --> R1 --> R2 --> R3 --> R4 --> R5 --> R6 --> OUT

    NOTE1["置空action：保留行，字段值设为 NULL"]
    NOTE2["删除行action：整行删除\n（cell_id IS NULL 或 event_time_std IS NULL）"]
    R1 -.- NOTE1
    R3 -.- NOTE2

    style OUT fill:#c8e6c9,stroke:#388e3c
```

**清洗原则**：能修正就修正，不能修正才删除。信号值越界→置空；`cell_id` 不可解析（已置空）且 `event_time_std` 为空→删除整行。

清洗阶段还负责派生 7 个字段：`bs_id`、`sector_id`、`operator_cn`、`report_ts`、`cell_ts_std`、`gps_ts`、`has_cell_id`。

---

## 1.5 字段对齐（同报文内互补）

同一次手机上报，`cell_infos` 和 `ss1` 会各产生自己的行，而它们其实描述的是同一个上报事件，字段可以互补：

```mermaid
flowchart TD
    CLEANED["etl_cleaned 基础列\n687,788 行"]

    RULE{"同一 record_id + 同一 cell_id 内"}

    FULL["cell_infos 行之间\n→ 全字段可互补"]

    SS1_60["ss1 行，时间差 ≤ 1分钟\n→ 全字段互补"]
    SS1_LONG["ss1 行，时间差 > 1分钟\n→ 只补运营商和LAC"]

    OUT["etl_cleaned 最终（66列）\n新增 14 个 _filled 字段 + 来源标记"]

    CLEANED --> RULE
    RULE --> FULL --> OUT
    RULE --> SS1_60 --> OUT
    RULE --> SS1_LONG --> OUT

    STAT["GPS 覆盖率：84.8% → 97.5% (+12.7%)\nRSRP 覆盖率：86.9% → 94.6% (+7.7%)"]
    OUT -.- STAT

    style OUT fill:#c8e6c9,stroke:#388e3c
```

**重要边界**：字段对齐只在"同一条原始报文内"发生，不跨报文。跨 Cell 的知识补数是 Step 4 的职责。

---

## 产出：etl_cleaned 的 70 列结构

| 分类 | 列数 | 说明 |
|------|------|------|
| 基础结构化列 | 47 | 解析直接产出（含 `dataset_key`、`source_table` 两个上下文字段） |
| 清洗派生列 | 9 | 清洗阶段补加（`bs_id`、`sector_id`、`operator_cn`、`report_ts`、`cell_ts_std`、`gps_ts`、`event_time_std`、`event_time_source`、`has_cell_id`） |
| 字段对齐结果列 | 14 | 同报文对齐阶段补加 |
| **最终输出总列数** | **70** | Step 1 最终 `etl_cleaned` |

**关键约定**：`*_raw` 字段代表原始真相，永远不被覆盖；`*_filled` 字段是对齐或补数后的可用值，供后续步骤使用。

---

## 与 Step 4 的区别（常见混淆点）

| 对比项 | Step 1 字段对齐 | Step 4 知识补数 |
|--------|----------------|----------------|
| 数据来源 | **同一条报文内**的其他字段 | **上一轮可信小区库**的历史知识 |
| 范围 | 仅同 `record_id` 的行 | 任何命中可信库的记录 |
| 可靠性 | 中（依赖原始报文质量） | 高（经过质量评估的可信对象） |
| 触发时机 | 数据入库时（现在） | 可信库建立后的持续运行 |
| 是否受冻结约束 | 否 | 是（只读上一轮发布版本） |

---

## 运行统计（step1_run_stats）

每次 Step 1 运行后记录一条统计快照，记录：
- 解析输入/输出行数、扩展比
- 每条 ODS 规则的命中数
- 字段对齐前后各字段覆盖率
- 补齐来源分布（`raw_gps / ss1_own / same_cell / none`）
