# ETL 管道设计文档

## 概述

ETL（Extract-Transform-Load）是 rebuild4 数据处理的基础设施。它将 SDK 上报的原始数据（27 列）转换为结构化的 L0 表（55 列），经过清洗和补齐后可供后续分析使用。

本文档描述 ETL 的完整流程、每一步的规则和预期产出。

## 数据流总览

```
┌─────────────────────────────────────────────────────┐
│  原始数据（27 列）                                    │
│  sample_raw_gps: 128,764 条                          │
│  sample_raw_lac: 120,437 条                          │
└────────────────────┬────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │  Step 1: 解析（炸开）  │
          │                      │
          │  cell_infos JSON     │──→ 每个 cell 一行
          │  ss1 文本            │──→ 按 ; 分组拆行
          │                      │
          │  统计: 1条 → N行      │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  Step 2: 清洗（ODS）  │
          │                      │
          │  9 条模块化规则        │
          │  逐条统计违规数        │
          │  标记或删除脏数据      │
          │                      │
          │  统计: 输入/通过/过滤  │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  Step 3: 补齐        │
          │                      │
          │  同报文 GPS 补齐      │
          │  同报文信号补齐       │
          │                      │
          │  统计: 补齐率         │
          └──────────┬──────────┘
                     │
          ┌──────────▼──────────┐
          │  L0 产出表            │
          │  结构化 55 列         │
          │  可供后续分析          │
          └─────────────────────┘
```

## Step 1: 解析（炸开）

### 输入
一条原始记录包含两个核心字段：
- `cell_infos`：JSON 格式，包含手机扫描到的所有基站信息
- `ss1`：分号分隔的文本，包含后台采集的信号/时间/GPS/基站数据

一条原始记录会"炸开"为多行 L0 记录。

### 1.1 cell_infos 解析

**格式**：JSON 对象，key 为序号，value 为基站信息
```json
{
  "1": {
    "isConnected": 1,
    "type": "nr",
    "cell_identity": { "mccString": "460", "mncString": "01", "Nci": 563347713, "Tac": 65546, "Pci": 515 },
    "signal_strength": { "SsRsrp": -88, "SsRsrq": -11, "SsSinr": 8, "Dbm": -88 },
    "timeStamp": 1437934151
  },
  "2": { ... }
}
```

**解析规则**：
1. `jsonb_each()` 拆开每个 cell
2. 只保留 `isConnected = 1` 的主服务基站（用于可信分析）
3. 制式映射：`lte→4G, nr→5G, gsm→2G, wcdma→3G`
4. 运营商编码：优先 `cell_identity.mno`，否则 `mccString + mncString`
5. LAC：`Tac / tac / lac / Lac`（bigint）
6. CellID：`Ci / Nci / nci / cid`（bigint）
7. BS_ID：4G → `cell_id / 256`，5G → `cell_id / 4096`
8. 信号：`rsrp/SsRsrp`, `rsrq/SsRsrq`, `rssnr/SsSinr`
9. GPS：来自原始记录的 `原始上报gps` 字段，标记 `gps_filled_from = 'raw_gps'`

### 1.2 ss1 解析

**格式**：分号分隔的文本，每组 4 段（`&` 分隔）
```
信号段&时间段&GPS段&基站段;信号段&时间段&GPS段&基站段;...
```

**每段内容**：
- **信号段**：逗号分隔的信号值，首字符标识制式（`l`=LTE, `n`=NR, `g`=GSM, `w`=WCDMA）
- **时间段**：毫秒时间戳
- **GPS段**：`经度,纬度` 或空
- **基站段**：
  - 正常值（以 `l` 或 `n` 开头）：`制式标识,cell_id,lac,...`
  - `1`：继承上一组的基站（forward-fill）
  - `0` 或空：无有效基站

**解析规则**：
1. 去尾部 `;`，按 `;` 分组，每组编号 `grp_idx`
2. 每组按 `&` 拆成 4 段
3. **基站继承**（forward-fill）：
   - 如果 `cell_block = '1'`，继承同一 record_id 内上一个有效 cell_block
   - 使用窗口函数 `MAX(cb_own) OVER (PARTITION BY record_id ORDER BY grp_idx)`
4. 从 cell_block 解析出 cell_id、lac、tech
5. 从 sig_block 解析信号值，按制式匹配到 cell
6. GPS 来自本组 gps_block，标记 `gps_filled_from = 'ss1_own'`

### 1.3 合并

cell_infos 行和 ss1 行合并为统一结构。需要统计：

| 指标 | 说明 |
|------|------|
| raw_records | 原始记录数 |
| ci_rows | cell_infos 解析出的行数 |
| ss1_rows | ss1 解析出的行数 |
| total_parsed | 合并后总行数 |
| expansion_ratio | total_parsed / raw_records |

---

## Step 2: 清洗（ODS）

清洗规则是**模块化**的，每条规则独立定义，可以单独启用/禁用/添加。

### 规则定义格式

```python
{
    "rule_id": "ODS-001",
    "category": "运营商",
    "name": "排除无效运营商编码",
    "field": "operator_code",
    "condition_sql": "operator_code NOT IN ('46000','46001',...,'46020')",
    "action": "delete",       # delete=删除行, nullify=置空字段, flag=标记
    "severity": "critical",   # critical/warning/info
    "description": "运营商编码必须在有效白名单内，否则无法归属到任何运营商"
}
```

### 当前 9 条规则

| ID | 类别 | 规则 | 字段 | 动作 | 说明 |
|----|------|------|------|------|------|
| ODS-001 | 运营商 | 垃圾运营商编码置空 | operator_code | nullify | '00000','0','000000','(null)(null)','' → NULL |
| ODS-002 | 运营商 | 非白名单运营商置空 | operator_code | nullify | 不在 46000/01/02/03/05/06/07/09/11/15/20 白名单 → NULL |
| ODS-003 | LAC | LAC=0 置空 | lac | nullify | 未获取到有效 LAC |
| ODS-004 | LAC | 4G LAC 保留值置空 | lac | nullify | 4G 的 65534/65535 是保留值 |
| ODS-005 | LAC | LAC 溢出值置空 | lac | nullify | 268435455 (0xFFFFFFF) 溢出 |
| ODS-006 | CellID | CellID=0 置空 | cell_id | nullify | 无有效小区标识 |
| ODS-007 | CellID | 5G CellID 溢出值置空 | cell_id | nullify | 5G 的 268435455 溢出 |
| ODS-008 | CellID | 4G CellID 溢出值置空 | cell_id | nullify | 4G 的 2147483647 (Integer.MAX_VALUE) 溢出 |
| ODS-009 | 信号 | RSRP 越界置空 | rsrp | nullify | 合理范围 -156~-1，0 和正数及 <-156 置空 |
| ODS-010 | 信号 | RSRQ 越界置空 | rsrq | nullify | 合理范围 -34~10 |
| ODS-011 | 信号 | SINR 越界置空 | sinr | nullify | 合理范围 -23~40 |
| ODS-012 | 信号 | Dbm 越界置空 | dbm | nullify | 应为负数，0 和正数置空 |
| ODS-013 | 位置 | 经度越界标记 | gps_valid | flag | 中国大陆 73~135，超出 → gps_valid=false |
| ODS-014 | 位置 | 纬度越界标记 | gps_valid | flag | 中国大陆 3~54，超出 → gps_valid=false |

**最终行过滤**：CellID 为 NULL 或 0 或溢出值的行 → 删除（这些行无法归属到任何小区）

### 统计

每条规则记录：违规数、违规率、动作（删除/标记）。
汇总记录：输入行数、删除行数、标记行数、通过行数、通过率。

---

## Step 3: 同报文补齐

在同一条原始记录内（相同 `record_id`），不同来源的行可以互相补齐。

### 3.1 GPS 补齐

**场景**：ss1 行可能没有 GPS，但同一 record_id 的 cell_infos 行有原始 GPS。

**补齐逻辑**：
1. cell_infos 行：GPS 来自 `原始上报gps` → `gps_filled_from = 'raw_gps'`
2. ss1 行本组有 GPS：使用本组 GPS → `gps_filled_from = 'ss1_own'`
3. ss1 行本组无 GPS：在同 record_id 内按时间就近取最近的有 GPS 的组 → `gps_filled_from = 'ss1_nearest'`
4. 仍无 GPS：`gps_filled_from = 'none'`

### 3.2 信号补齐

**场景**：cell_infos 行有完整信号（RSRP/RSRQ/SINR），ss1 行可能信号不全。

**补齐逻辑**：同制式、同 record_id 内信号互补。

### 统计

| 指标 | 说明 |
|------|------|
| gps_original | GPS 来自原始上报的行数 |
| gps_ss1_own | GPS 来自 ss1 本组的行数 |
| gps_ss1_nearest | GPS 就近补齐的行数 |
| gps_none | 无 GPS 的行数 |
| gps_fill_rate | 有 GPS 的行数 / 总行数 |

---

## 代码架构

```
rebuild4/backend/app/etl/
├── __init__.py
├── pipeline.py          # ETL 主入口：run_etl(scope, source_tables)
├── parser.py            # Step 1: 解析（cell_infos + ss1）
├── cleaner.py           # Step 2: 清洗（模块化规则引擎）
├── filler.py            # Step 3: 同报文补齐
├── rules/               # 清洗规则定义
│   └── ods_rules.py     # 当前 9 条 ODS 规则
└── stats.py             # 统计收集器
```

### 关键接口

```python
# pipeline.py
def run_etl(scope: str, source_gps: str, source_lac: str) -> EtlResult:
    """
    运行完整 ETL 管道。
    
    Args:
        scope: 数据范围标识（如 'sample'）
        source_gps: GPS 原始表名（如 'rebuild4.sample_raw_gps'）
        source_lac: LAC 原始表名（如 'rebuild4.sample_raw_lac'）
    
    Returns:
        EtlResult: 包含每步统计、产出表名、耗时
    """

# cleaner.py
class OdsRule:
    rule_id: str
    category: str
    name: str
    field: str
    condition_sql: str
    action: str  # 'delete' | 'flag'
    
class Cleaner:
    def __init__(self, rules: list[OdsRule]): ...
    def apply(self, table: str) -> CleanResult: ...
    def add_rule(self, rule: OdsRule): ...
```

---

## UI 页面对应

| ETL 步骤 | 页面 | 展示内容 |
|----------|------|----------|
| 输入 | 原始数据 · 字段挑选 | 27 列字段决策、源表行数 |
| Step 1 | L0 字段审计 | 55 列目标字段定义、来源类型 |
| Step 1 | L0 数据概览 | 解析统计、制式/运营商分布、扩展比 |
| Step 2 | ODS 清洗规则 | 规则列表、违规数、通过率 |
| Step 3 | 补齐统计 | GPS/信号补齐率、来源分布 |

---

## 实施步骤

1. **准备原始数据**（已完成）
   - sample_raw_gps: 128,764 条
   - sample_raw_lac: 120,437 条

2. **实现 Step 1: 解析**
   - 2a: cell_infos 解析（SQL 函数）
   - 2b: ss1 解析（SQL 函数，含 forward-fill）
   - 2c: 合并 + 统计

3. **实现 Step 2: 清洗**
   - 3a: 规则引擎框架（Python）
   - 3b: 9 条规则定义
   - 3c: 执行 + 统计

4. **实现 Step 3: 补齐**
   - 4a: GPS 补齐逻辑
   - 4b: 信号补齐逻辑
   - 4c: 统计

5. **UI 页面更新**
   - 去掉可信库页面
   - 加补齐统计页面
   - 各页面展示真实 ETL 产出数据

6. **封装为可复用模块**
   - `run_etl()` 一键执行
   - 支持不同 scope
   - 输出标准化统计

## 与 rebuild2 对比验证

ETL 完成后，产出的 L0 表应与 rebuild2 的 `sample_l0_gps/lac` 逐字段对比：
- 记录数应一致（误差 < 1%）
- 制式/运营商分布应一致
- GPS 补齐率应接近
- ODS 过滤数应接近
