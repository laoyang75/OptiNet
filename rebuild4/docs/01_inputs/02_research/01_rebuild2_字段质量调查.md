# rebuild2 字段质量调查

状态：已调查  
更新时间：2026-04-06  
调查方式：文档核对 + `PG17 MCP` 实时查询（`execute_sql` 为主，`search_objects` 仅作结构辅助）

---

## 1. 结论摘要

rebuild2 的字段质量资产是有价值的，但当前不是单一真相源。

数据库数值口径说明：

- 涉及计数、分布、缺口的事实，统一以 `PG17 MCP execute_sql` 查询结果为准
- `search_objects` 只用于确认字段结构、索引、表存在性，不作为最终计数真相源

当前至少存在四类口径分裂：

1. 原始字段 keep / parse / drop 的文档口径与数据库元数据不一致
2. `parse_rule` / `compliance_rule` 文档宣称存在，但当前元数据表为空
3. ODS 清洗规则的“定义数、分类数、执行数”不一致
4. 目标字段数量文档常写“约 60”，实际元数据表当前为 55 行

因此 rebuild4 不能直接把 rebuild2 文档当唯一事实，而必须先重建一份“字段质量真相表”。

---

## 2. 当前真实口径

### 2.1 `field_audit`

数据库：`rebuild2_meta.field_audit`

当前统计：

- 总字段数：27
- `keep`：17
- `parse`：3
- `drop`：7

当前 `drop` 字段：

- `当前数据最终经度`
- `当前数据最终纬度`
- `android_ver`
- `基带版本信息`
- `arp_list`
- `imei`
- `gps定位北京来源ss1或daa`

问题：

- `rebuild2/docs/04_phase1_总结.md` 写的是 `keep 19 / parse 3 / drop 5`
- `rebuild2/docs/03_字段治理规则.md` 又把 `ip / pkg_name / wifi_name / wifi_mac / cpu_info / 压力` 写成丢弃项
- 但数据库真实结果中，上述字段当前都属于 `keep`

结论：

- rebuild4 继承字段决策时，应以 `rebuild2_meta.field_audit` 和实际目标字段表为主
- 旧文档只能作为历史说明，不能直接用作正式口径

### 2.2 `target_field`

数据库：`rebuild2_meta.target_field`

当前统计：

- 当前真实行数：55
- 类别分布：
  - 信号：13
  - 元数据：12
  - 网络：11
  - 时间：5
  - 补齐：5
  - 位置：4
  - 来源：2
  - 标识：2
  - 解析：1

问题：

- 多份文档写“约 60 个字段”或 “~60”
- 当前数据库真实结果是 55 行

结论：

- rebuild4 必须直接冻结一份真实字段清单，不再使用“约 60 个字段”这种宽泛表达

### 2.3 `parse_rule` 与 `compliance_rule`

数据库：

- `rebuild2_meta.parse_rule`
- `rebuild2_meta.compliance_rule`

当前统计：

- `parse_rule = 0`
- `compliance_rule = 0`

问题：

- 文档中多次声称存在 `parse_rule 64 行`、`compliance_rule 17 行`
- 当前元数据表实际为空

结论：

- rebuild2 的“解析规则 / 合规规则”目前主要存在于文档与脚本，不存在完整可复用元数据底座
- rebuild4 若要继承这部分，必须补做可计算、可查询、可审计的正式元数据表

### 2.4 `ods_clean_rule` 与 `ods_clean_result`

数据库：

- `rebuild2_meta.ods_clean_rule`
- `rebuild2_meta.ods_clean_result`

当前统计：

- 规则定义：26 条
- 当前分类：
  - `delete`：1
  - `nullify`：22
  - `convert`：3
- 执行统计：48 行（`l0_gps` 24 + `l0_lac` 24）
- 实际覆盖 rule_code：每张表 24 条

已定义但未进入执行统计的 rule：

- `NULL_WIFI_NAME_INVALID`
- `NULL_WIFI_MAC_INVALID`

问题：

- 文档里存在多个版本：
  - 26 条 = `1 + 19 + 4 + 2`
  - 26 条 = `1 + 17 + 4 + 2`
- 数据库真实分类是 `1 + 22 + 3`
- 执行层目前只覆盖 24 条

结论：

- rebuild4 必须把“规则定义层”和“规则执行层”拆开表达
- 任务书中要明确说明：哪些规则只是定义了，哪些已经进入统计闭环

---

## 3. 当前 L0 字段质量真实结果

### 3.1 `rebuild2_meta.l0_stats_cache`

当前存在 8 行缓存，覆盖：

- `l0_gps.summary`
- `l0_gps.field_quality`
- `l0_lac.summary`
- `l0_lac.field_quality`
- 以及少量按来源/运营商聚合缓存

### 3.2 `l0_gps` 字段质量

- 总行数：38,433,729
- `operator_null`：0.53%
- `lac_null`：0.12%
- `cellid_null`：0.00%
- `gps_null`：11.85%
- `rsrp_null`：11.32%
- `rsrq_null`：19.01%
- `sinr_null`：41.32%
- `dbm_null`：38.67%
- `cell_ts_null`：62.50%

### 3.3 `l0_lac` 字段质量

- 总行数：43,771,306
- `operator_null`：10.17%
- `lac_null`：0.11%
- `cellid_null`：0.00%
- `gps_null`：13.11%（直接聚合时经纬同时为空约 13.73%）
- `rsrp_null`：11.35%
- `rsrq_null`：18.86%
- `sinr_null`：43.12%
- `dbm_null`：41.40%
- `cell_ts_null`：59.71%

### 3.4 解释

这里最值得继承到 rebuild4 的，不是“CellID 全对了”这类结论，而是：

- `operator` 空值率在 `l0_lac` 显著更高
- `GPS / SINR / Dbm / cell_ts` 才是需要重点解释的质量字段
- `cell_infos` 与 `ss1` 的质量差异明显
- 2G / 3G 下 RSRP / SINR 大面积为空是技术性现象，不能简单当作脏数据

---

## 4. 来源与制式维度的质量差异

### 4.1 按 `Cell来源`

`l0_gps`：

- `cell_infos`：23,994,418 行，`gps_null=0.88%`，`rsrp_null=3.31%`
- `ss1`：14,439,311 行，`gps_null=30.08%`，`rsrp_null=24.63%`

`l0_lac`：

- `cell_infos`：26,103,312 行，`gps_null=1.06%`，`rsrp_null=3.13%`
- `ss1`：17,667,994 行，`gps_null=32.45%`，`rsrp_null=23.49%`

结论：

- `ss1` 明显更差，但又是重要补充来源
- rebuild4 必须保留“按来源通道解释质量”的能力

### 4.2 按 `标准制式`

值得注意的几个事实：

- 2G / 3G 的 `RSRP / SINR` 基本天然为空
- 4G 的 `SINR` 空值率高于 5G
- 5G 的 `Dbm` 和 `RSRP` 也并非全量可用

结论：

- rebuild4 的字段质量页不能只展示“空值率排行”
- 必须同时给出制式语义解释，否则会误导用户把协议差异当成数据质量问题

---

## 5. trusted 过滤损耗（必须进入 rebuild4）

以 `rebuild2.l0_lac` 左连接 `rebuild2.dim_lac_trusted` 为准：

- 总行数：43,771,306
- trusted 命中：30,082,381
- 被过滤：13,688,925
- 被过滤比例：31.27%

被过滤数据中仍然保有大量有效信息：

- 有 `RSRP`：12,017,352
- 有 GPS：11,350,552
- `2G`：233,772
- `3G`：92,937
- `4G`：10,004,716
- `5G`：3,357,500

来源分布：

- `sdk / daa / cell_infos`：7,015,342
- `sdk / daa / ss1`：5,951,068
- `sdk / dna / cell_infos`：722,515

结论：

- 被过滤数据并不只是垃圾数据
- rebuild4 必须明确说明：为什么这些仍有 GPS / 信号的记录会被排除
- 这部分正是你要求补回 rebuild4 的“清理细节解释层”

---

## 6. 对 rebuild4 的直接要求

### 必须继承

- `field_audit` 的真实结果
- `target_field` 的真实字段清单
- `ods_clean_rule` 定义与 `ods_clean_result` 执行统计
- `l0_stats_cache` 中已经存在的字段质量统计
- trusted 过滤前后损耗及来源分布

### 必须补建

- 可计算的 `parse_rule` 元数据
- 可计算的 `compliance_rule` 元数据
- 规则定义层与执行层的差异说明
- 按来源/制式/字段三维展开的统一质量读模型

### 不能再模糊处理

- “约 60 个字段”
- “26 条规则”但不区分定义和执行
- “字段质量已完成”但没有真实闭环统计

---

## 7. 一句话结论

rebuild2 的字段质量成果值得继承，但 rebuild4 必须先把它从“文档描述”提升成“真相统一、可查询、可审计”的正式底座。
