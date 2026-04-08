# 原始数据字段契约

> 状态：**待审计** — 通过字段审计页逐一确认
> 数据来源：两张真正的原始表（结构一致，27 列，仅最后一列列名不同）

## 数据层次说明

```
原始源表（27列）               ← 我们在这里
  ├─ cell_infos（JSON）        → 解析出：cell_id, lac, plmn, tech, 信号强度等
  ├─ ss1（紧凑字符串）         → 解析出：cell_id, lac, plmn, GPS, 信号强度等
  └─ 其他 25 列（设备/时间/位置/元数据）
       ↓
Layer0 解析表（42列）           ← Y_codex_Layer0_* 就是这一层
       ↓
ODS 标准化表                    ← rebuild2 的 L1 目标
```

**关键认识**：`Y_codex_Layer0_*`（42 列、1.3 亿行）不是原始数据，
是从这 27 列表的 `cell_infos` / `ss1` 解析、展开后产出的。
每条原始记录可能展开成多条 Layer0 行（一条 cell_infos 含多个基站扫描结果）。

## 源表信息

| 表 | 行数 | 说明 |
|----|------|------|
| 网优项目_gps定位北京明细数据_20251201_20251207 | 2217 万 | GPS 定位明细 |
| 网优项目_lac定位北京明细数据_20251201_20251207 | 1796 万 | LAC 定位明细 |

## 27 列字段清单

### 核心解析字段（最重要，决定整个数仓的输入质量）

| # | 原始列名 | 类型 | 分类 | 说明 | cell_infos 非空率 | ss1 非空率 |
|---|---------|------|------|------|---|---|
| 16 | cell_infos | text | 核心 | 实时基站扫描 JSON：含多个基站的 cell_id/lac/plmn/信号/制式 | GPS 表 89%, LAC 表 99% | — |
| 17 | ss1 | text | 核心 | 后台采集紧凑串：信号+时间+GPS+基站+AP | GPS 表 31%, LAC 表 24% | — |

**解析规则**（参考 `Beijing_Source_Parse_Rules_v1.md`）：
- `cell_infos`：JSON 对象，每个 key 是一个基站扫描结果
  - `cell_identity`：Ci/Nci → cell_id, Tac/Lac → lac, mno/mccString+mncString → plmn
  - `signal_strength`：rsrp/rsrq/rssi/SsRsrp/SsSinr/Dbm 等
  - `type`：lte → 4G, nr → 5G
  - `isConnected`：1 = 当前连接
- `ss1`：以 `;` 分组，每组以 `&` 分 5 个元素
  - 元素1：信号块（l=LTE, n=NR, 逗号分隔 ss/rsrp/rsrq/sinr）
  - 元素2：时间戳（unix 秒）
  - 元素3：GPS（经度,纬度,时间）
  - 元素4：基站块（制式,cell_id,lac,plmn）
  - 元素5：AP 信息（bssid,ssid）

### 标识字段

| # | 原始列名 | 类型 | 决策 | ODS 名 | 说明 |
|---|---------|------|------|--------|------|
| 1 | 记录数唯一标识 | varchar | | | 原始记录唯一标识 |
| 3 | did | varchar | | | 设备唯一标识 |
| 5 | ip | varchar | | | 上报 IP |
| 25 | imei | varchar | | | 设备 IMEI |
| 26 | oaid | varchar | | | 开放匿名标识 |

### 时间字段

| # | 原始列名 | 类型 | 决策 | ODS 名 | 说明 |
|---|---------|------|------|--------|------|
| 4 | ts | varchar | | | 上报时间（原始文本，unix 毫秒） |
| 10 | gps上报时间 | varchar | | | GPS 上报时间（原始文本） |

### 网络字段

| # | 原始列名 | 类型 | 决策 | ODS 名 | 说明 |
|---|---------|------|------|--------|------|
| 11 | 主卡运营商id | varchar | | | 主卡 PLMN（46000 等） |
| 7 | wifi_name | varchar | | | WiFi SSID |
| 8 | wifi_mac | varchar | | | WiFi BSSID |
| 23 | arp_list | text | | | ARP 列表 |

### 位置字段

| # | 原始列名 | 类型 | 决策 | ODS 名 | 说明 |
|---|---------|------|------|--------|------|
| 14 | gps_info_type | varchar | | | GPS 信息类型 |
| 15 | 原始上报gps | varchar | | | GPS 原始字符串 |
| 18 | 当前数据最终经度 | float8 | | | 最终经度 |
| 19 | 当前数据最终纬度 | float8 | | | 最终纬度 |

### 元数据字段

| # | 原始列名 | 类型 | 决策 | ODS 名 | 说明 |
|---|---------|------|------|--------|------|
| 2 | 数据来源dna或daa | varchar | | | 数据来源标识 |
| 6 | pkg_name | varchar | | | 上报应用包名 |
| 9 | sdk_ver | varchar | | | SDK 版本 |
| 12 | 品牌 | varchar | | | 手机品牌 |
| 13 | 机型 | varchar | | | 手机机型 |
| 20 | android_ver | varchar | | | Android 版本 |
| 21 | cpu_info | varchar | | | CPU 信息 |
| 22 | 基带版本信息 | varchar | | | 基带版本 |
| 24 | 压力 | varchar | | | 气压传感器 |
| 27 | gps/lac定位北京来源ss1或daa | varchar | | | 北京来源标记（两表此列名不同） |
