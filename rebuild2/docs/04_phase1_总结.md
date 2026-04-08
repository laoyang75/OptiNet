# Phase 1 工作总结：字段治理与 ODS 标准化

> 完成日期：2026-03-31
> 覆盖范围：RAW 字段挑选 → L0 字段定义 → ODS 清洗规则 → 数据生成

---

## 1. 完成事项

### 1.1 RAW 层字段挑选

对两张原始源表（27 列，结构一致）完成字段决策：

| 决策 | 数量 | 字段 |
|------|------|------|
| keep | 19 | 记录数唯一标识、数据来源dna或daa、did、ts、ip、pkg_name、wifi_name、wifi_mac、sdk_ver、gps上报时间、主卡运营商id、品牌、机型、原始上报gps、cpu_info、压力、oaid |
| parse | 3 | cell_infos、ss1、gps_info_type |
| drop | 5 | 当前数据最终经度/纬度、android_ver、基带版本信息、arp_list、imei、gps定位北京来源 |

### 1.2 原始数据解析

**cell_infos 解析**（JSON → 按基站拆行）：
- 提取：cell_id、lac、plmn、制式、PCI、频点、带宽、全部信号字段（RSRP/RSRQ/SINR/RSSI/Dbm/ASU/Level/TA/CSI/CQI）
- GPS：使用原始上报 GPS（与 cell_infos 同时前台采集）

**ss1 解析**（紧凑字符串 → 按组拆行）：
- 格式：`{信号}+&{时间}&{GPS}&{基站}+&{AP};...`
- 继承逻辑：cell_block = "1" 继承上一组的基站信息
- GPS：每组有自己独立的 GPS + 时间戳

### 1.3 全量执行结果

| 表 | 原始记录 | L0 行数 | cell_infos 行 | ss1 行 |
|----|---------|---------|-------------|--------|
| l0_gps | 1654 万 | **3843 万** | 2541 万 | 1302 万 |
| l0_lac | 1786 万 | **4377 万** | 2747 万 | 1630 万 |

### 1.4 GPS 来源逻辑

| 行来源 | GPS 优先级 |
|--------|-----------|
| cell_infos | 原始上报 GPS（前台同时采集） |
| ss1 | 本组自己的 GPS（后台独立采集） |
| 无 GPS 时 | 按时间最近的其他组补齐（待执行时实现） |

### 1.5 ss1 解析评估

- ss1 非空率约 30.5%，平均每条 3.23 组
- 50% 的 ss1 记录无有效基站（只有运营商级信息 `g,-1,-1,plmn`、空组、或无前置组可继承）
- 有产出的记录平均每条 3.86 行
- 推算值（1281万）与实际值（1300万）吻合，**解析逻辑正确**

### 1.6 CellID 覆盖率说明

总覆盖率 34.5% 是口径问题：73.6% 的行是邻区扫描（is_connected=2），邻区只报 PCI 不报 CellID。
- **主服务基站 CellID 覆盖率：100%**
- ss1 CellID 覆盖率：99.7%
- 邻区 CellID 覆盖率：11%（正常）

### 1.7 ODS 清洗规则（26 条）

| 类型 | 数量 | 覆盖 |
|------|------|------|
| 删除行 | 1 | 主服务基站无 CellID |
| 置空 | 19 | CellID(0/占位)、LAC(0/溢出)、运营商(无效/非白名单)、RSRP(正值/零值/超低)、RSRQ(>10/<-34)、SINR(>40/<-23)、Dbm(正值/零值)、ASU(<0/>99)、SS(INT_MAX/正值)、TA(>63/<0)、**WiFi名称(unknown)、WiFi MAC(隐私假地址)** |
| 转换 | 4 | 上报时间→timestamptz、ss1基站时间→timestamptz、cell_infos基站时间置空(相对时间)、GPS时间→timestamptz |
| 运营商 | 2 | 无效编码置空、非五大运营商置空 |

### 1.5 L0 目标字段（约 60 个）

按分类：
- **标识**(2)：l0_id, record_id
- **来源**(2)：data_source, data_source_detail
- **解析**(2)：cell_origin, is_connected
- **补齐**(5)：gps_filled_from, signal_filled_from, time_filled_from, fill_time_delta_ms, has_cell_id
- **网络**(13)：cell_id_dec, lac_dec, bs_id, sector_id, operator_id_raw/cn, tech_raw/norm, pci, freq_channel, bandwidth
- **信号**(13)：rsrp, rsrq, sinr, rssi, dbm, asu_level, level, ss, timing_advance, csi_rsrp/rsrq/sinr, cqi
- **时间**(6)：ts_raw/std, cell_ts_raw/std, gps_ts_raw, gps_ts
- **位置**(5)：gps_info_type, gps_valid, lon_raw, lat_raw, gps_filled_from
- **元数据**(12)：did, ip, plmn_main, brand, model, sdk_ver, oaid, pkg_name, wifi_name/mac, cpu_info, pressure

---

## 2. 关键设计决策

| # | 决策 | 理由 |
|---|------|------|
| 1 | 两张原始表分别生成 L0，不合并 | gps 表用于构建可信库，lac 表作为全局表 |
| 2 | GPS 原始串不单独保留 | 经纬度直接从 ss1/原始 GPS 解析为 float8 |
| 3 | LAC/CellID 不保留原始文本列 | 转 bigint 100% 无损 |
| 4 | cell_infos 的 timeStamp 置空 | 是设备启动后的相对毫秒数，不是绝对时间 |
| 5 | ss1 的 cell_block="1" 做继承 | 后续组继承上一组的基站信息 |
| 6 | SINR > 40 全部置空 | 含 ss1 的 100~300 段，不做 /10 换算 |
| 7 | 邻区无 CellID 的行保留 | 标记 NULL，信号值仍有价值 |

---

## 3. 数据库对象

### Schema
- `legacy` — 原始数据（只读）
- `rebuild2` — L0 产出表
- `rebuild2_meta` — 元数据

### 元数据表
- `rebuild2_meta.field_audit` — RAW 字段决策（27 行）
- `rebuild2_meta.target_field` — L0 目标字段定义（~60 行）
- `rebuild2_meta.parse_rule` — 解析映射规则（64 行）
- `rebuild2_meta.compliance_rule` — 合规规则（17 行）
- `rebuild2_meta.ods_clean_rule` — ODS 清洗规则（24 行）
- `rebuild2_meta.ods_clean_result` — ODS 执行统计

### 产出表
- `rebuild2.l0_sample_10k` — 样本表（约 65000 行）
- `rebuild2.l0_gps` — GPS 表解析产出（待生成）
- `rebuild2.l0_lac` — LAC 表解析产出（待生成）

---

## 4. 技术架构

```
rebuild2/
├── backend/app/
│   ├── main.py          — FastAPI 入口（端口 8100）
│   ├── api/audit.py     — RAW 字段审计 + L0 字段定义 API
│   ├── api/ods.py       — ODS 清洗规则 API
│   └── core/            — config + database
├── frontend/
│   ├── index.html       — 侧栏导航（RAW / L0 / L1 / L2 / L3 / L4 / L5）
│   └── js/pages/
│       ├── raw.js       — 原始数据·字段挑选页
│       ├── audit.js     — L0 字段定义审计页
│       └── ods.js       — ODS 标准化页（规则审核 + 执行结果）
├── prompts/             — 阶段 prompt
├── docs/                — 文档
└── launcher_web.py      — 启动器（端口 9100）
```

---

## 5. 下一步

Phase 2：可信库构建（见 `prompts/phase2_trusted_library.md`）
- 从 `rebuild2.l0_gps` 构建可信 LAC → Cell → BS
- 用可信库回到 `rebuild2.l0_lac` 提取最终明细
