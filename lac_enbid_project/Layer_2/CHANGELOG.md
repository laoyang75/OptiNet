# Layer_2 Changelog

## 2025-12-18（LAC 溢出/占位值规则补齐）

- Step02（合规标记）补齐 LAC 明确异常值剔除：
  - `lac_enbid_project/Layer_2/sql/02_step2_compliance_mark.sql`：新增 `is_lac_overflow_sentinel`，并将 `FFFF/FFFE/FFFFFE/FFFFFF/7FFFFFFF` 作为硬过滤（同时联通/电信 LAC hex_len 收敛为 `[4,6]`）。
  - `lac_enbid_project/Layer_2/Step02_合规标记说明.md`、`lac_enbid_project/Layer_2/Data_Dictionary.md`：同步口径与原因枚举。
- Step04（可信 LAC）增加安全护栏：
  - `lac_enbid_project/Layer_2/sql/04_step4_master_lac_lib.sql`：在 `active_days=7` 的基础上明确排除 `65534/65535/16777214/16777215/2147483647`，避免异常值进入白名单。
- 现网补丁（不重跑流水线）：
  - `lac_enbid_project/补丁/补丁_20251218_LAC_溢出与占位值清理.sql`：可选，用于对已落地 Step03~Step06 的结果做最小清理（最终 LAC 不允许为上述异常值）。

## 2025-12-15（最终收尾修订 / 执行入口整理）

### Step06：补齐 LAC_RAW 基线

- 更新 `lac_enbid_project/Layer_2/sql/06_step6_apply_mapping_and_compare.sql`：在 `Y_codex_Layer2_Step06_GpsVsLac_Compare` 增加 `dataset='LAC_RAW'`（来源 `public."Y_codex_Layer2_Step00_Lac_Std"`），对比集变为 `GPS_RAW / GPS_COMPLIANT / LAC_RAW / LAC_FILTERED`。
- 同步更新文档与字典：
  - `lac_enbid_project/Layer_2/Step06_L0_Lac反哺与对比说明.md`：更新摘要查询与验收标准（四路数据集）。
  - `lac_enbid_project/Layer_2/Data_Dictionary.md`：更新 `数据集（dataset）` 枚举说明。
  - `lac_enbid_project/Layer_2/RUNBOOK_执行手册.md`：自检与描述同步为四路数据集。
  - `lac_enbid_project/Layer_2/README.md`：Step06 概览处补充 `dataset` 四路枚举说明（与字典/Step06 文档一致）。

### README 导航与未来接口

- 更新 `lac_enbid_project/Layer_2/README_人类可读版.md`：修复导航断链，改为可点击的相对链接。
- 保留独立未来接口说明文件：`lac_enbid_project/Layer_2/未来三大步骤_接口与字段说明.md`（无需跳转到其它章节）。

### 合规口径澄清（Step02）

- 更新 `lac_enbid_project/Layer_2/Step02_合规标记说明.md`：补充说明 `is_compliant = is_l1_cell_ok` 等价于（operator+tech+lac+cell）全合规（因为 cell_ok 建立在 lac_ok 之上）。

### 执行手册补齐（RUNBOOK）

- 更新 `lac_enbid_project/Layer_2/RUNBOOK_执行手册.md`：新增“冒烟落表模式（模板：复制 SQL + 加 report_date/operator_id_raw 过滤 + 跑完 drop 临时对象）”，避免仅靠附录 LIMIT 描述造成困惑。

### ValidCell 规则落地说明（Step01）

- 更新 `lac_enbid_project/Layer_2/Step01_基础统计说明.md`：明确列出 ValidCell 当前实现的规则子集（中文（English））。
