# Phase 1 Prompt：字段治理与 ODS 标准化

> 用途：当字段规则需要优化时，启动新会话，读取此 prompt 继续工作
> 阶段：RAW 字段挑选 → L0 字段定义 → ODS 清洗规则 → 数据生成

---

## 1. 项目背景

你在做一个网优数仓的分层重构项目（rebuild2）。核心理念是**先看数据再建结构，每建一层用 UI 确认**。

技术栈：
- 数据库：PostgreSQL 17（192.168.200.217:5433/ip_loc2）
- 后端：FastAPI（端口 8100）
- 前端：原生 ES Modules（复用 rebuild 样式系统）
- 启动器：端口 9100

数据库 schema：
- `legacy`：原始数据（只读）
- `rebuild2`：L0 产出表
- `rebuild2_meta`：元数据（字段审计、目标字段定义、清洗规则）

---

## 2. 原始数据

两张源表，结构完全一致（27 列），定位不同：

| 表 | 行数 | 定位 |
|----|------|------|
| `legacy."网优项目_gps定位北京明细数据_20251201_20251207"` | 2217 万 | GPS 定位，数据多质量差，用于构建可信库 |
| `legacy."网优项目_lac定位北京明细数据_20251201_20251207"` | 1796 万 | LAC 定位，质量稳，作为全局表 |

核心两列需要解析：
- `cell_infos`（JSON）：前台使用 App 时扫描的基站列表，含完整信号但无 GPS
- `ss1`（紧凑字符串）：后台采集，含 GPS 和信号，格式 `{信号}+&{时间}&{GPS}&{基站}+&{AP};...`

每条原始记录按 cell_id 拆分成多行（一个 cell_id 一行），同条记录内 cell_infos 和 ss1 的相同 cell_id 合并互补。

---

## 3. 必须先读取的文件

### 元数据表（数据库）
1. `rebuild2_meta.field_audit` — RAW 层 27 个字段的决策（source_table='sdk_raw'）
2. `rebuild2_meta.target_field` — L0 目标字段定义（当前约 60 个）
3. `rebuild2_meta.ods_clean_rule` — ODS 清洗规则（24 条）
4. `rebuild2_meta.compliance_rule` — 合规规则（17 条）

### 代码文件
5. `rebuild2/backend/app/api/audit.py` — 字段审计 API
6. `rebuild2/backend/app/api/ods.py` — ODS 清洗规则 API
7. `rebuild2/frontend/js/pages/raw.js` — RAW 层字段挑选页面
8. `rebuild2/frontend/js/pages/audit.js` — L0 目标字段审计页面
9. `rebuild2/frontend/js/pages/ods.js` — ODS 标准化页面

### 文档
10. `rebuild2/docs/00_项目定义.md` — 项目定义与构建路径
11. `rebuild2/docs/01_字段契约_Layer0.md` — 字段契约
12. `rebuild2/docs/03_字段治理规则.md` — 完整的解析规则和合规定义

### 样本表
13. `rebuild2.l0_sample_10k` — 从 gps 表取 10000 条原始记录解析后的样本（约 65000 行）

---

## 4. 已完成的决策

### RAW 层字段决策（27 列）
- **keep（19 列）**：记录数唯一标识、数据来源dna或daa、did、ts、ip、pkg_name、wifi_name、wifi_mac、sdk_ver、gps上报时间、主卡运营商id、品牌、机型、原始上报gps、cpu_info、压力、oaid
- **parse（3 列）**：cell_infos、ss1、gps_info_type
- **drop（5 列）**：当前数据最终经度、当前数据最终纬度、android_ver、基带版本信息、arp_list、imei、gps定位北京来源ss1或daa

### 关键设计决策
1. **GPS 来源**：cell_infos 行用原始上报 GPS（前台同时采集）；ss1 行用本组自己的 GPS
2. **ss1 继承**：cell_block = "1" 时继承上一组的基站信息
3. **时间统一**：上报时间（文本 → timestamptz）、ss1 基站时间（unix 秒 → timestamptz）、cell_infos 基站时间（相对时间，置空）、GPS 时间（毫秒 → timestamptz）
4. **两张表分别生成 L0**：gps 表 → L0_gps（构建可信库用），lac 表 → L0_lac（全局表）

---

## 5. 你的任务

如果用户说"优化字段规则"或"修正某个字段"，你应该：

1. 读取 `rebuild2_meta` 中的当前规则状态
2. 读取样本表 `rebuild2.l0_sample_10k` 验证数据
3. 按用户要求修改规则（更新数据库 + 更新代码）
4. 在 UI 上验证修改效果
5. 不要跳过验证直接执行全量

如果用户说"重新生成样本"，你应该：
1. 从原始表取 10000 条
2. 按最新的解析逻辑生成 `rebuild2.l0_sample_10k`
3. 在 UI 上展示结果

---

## 6. 解析逻辑要点

### cell_infos 解析
- JSON 对象，每个 key 是一个基站扫描
- `cell_identity`：Ci/Nci → cell_id, Tac/tac → lac, mno/mccString+mncString → plmn
- `signal_strength`：LTE 用 rsrp/rsrq/rssnr, NR 用 SsRsrp/SsRsrq/SsSinr
- `type`：lte→4G, nr→5G, gsm→2G, wcdma→3G

### ss1 解析（见 docs/05_ss1解析规则.md）
- 按 `;` 分组，每组按 `&` 分 5 元素
- 元素1（信号块）：按 `+` 分多条，每条 `{tech},{SS},{RSRP},{RSRQ},{RSSNR}`
- 元素4（基站块）：按 `+` 分多条（双卡），每条 `{tech},{cell_id},{lac},{plmn}`
- **核心规则：信号按制式匹配基站**（l信号→l基站，n信号→n基站）
- cell_block = "1" 继承上一组，= "0"/"" 无基站，= "g,-1,-1" 无 cell_id
- CellID = -1 不产出行；RSRP/RSRQ/RSSNR = -1 置 NULL
- 邻区行（is_connected=2）已在 V2 中去除，不进入 L0

### ODS 清洗规则（26 条）
- 1 条删除规则：主服务无 CellID → 删行
- 17 条置空规则：CellID/LAC/运营商/RSRP/RSRQ/SINR/Dbm/ASU/SS/TA 异常值
- 4 条转换规则：时间格式统一
- 2 条运营商规则：无效编码和非白名单
