# Taskbook Generation Prompt - finalization

任务：基于 finalization 合并稿和已裁决问题，生成 `03_final/` 中的最终正式文件。

---

## 输入

- `rebuild4/docs/02_rounds/finalization/merged/01_最终冻结基线.md`
- `rebuild4/docs/02_rounds/finalization/merged/02_最终技术栈与基础框架约束.md`
- `rebuild4/docs/02_rounds/finalization/merged/03_数据生成与回灌策略.md`
- `rebuild4/docs/02_rounds/finalization/merged/04_本轮范围与降级说明.md`
- `rebuild4/docs/02_rounds/finalization/decisions/01_待裁决问题清单.md`
- 前三轮 merged 文档（**仅作历史回查**；与 finalization merged 有冲突时，以 finalization merged 为最终依据，不得直接摘录前轮草稿内容）

---

## 输出到：`rebuild4/docs/03_final/`

目标文件：

1. `00_最终冻结基线.md`
2. `01_最终技术栈与基础框架约束.md`
3. `02_数据生成与回灌策略.md`
4. `03_最终执行任务书.md`
5. `04_最终校验清单.md`
6. `05_本轮范围与降级说明.md`

---

## 硬约束

- 这是正式冻结输出，不是草案
- 不能遗漏任何已裁决项
- `03_最终执行任务书.md` 必须面向执行（定义见下文生成规范）
- `04_最终校验清单.md` 必须与任务书步骤一一对应（锚定方式见下文生成规范）

---

## 生成规范

### 1. 文件生成规则

**`00_最终冻结基线.md` / `01_最终技术栈与基础框架约束.md` / `02_数据生成与回灌策略.md` / `05_本轮范围与降级说明.md`**

- 以 finalization merged 对应文稿为权威输入
- 去掉所有过程性元数据（"状态：finalization merged 冻结稿"、"输入范围："、"本轮结论："等注释性节）
- 保留且仅保留冻结约束正文
- 以正式文件格式呈现，不含任何 draft / 草稿 标注
- `00_最终冻结基线.md` 末尾必须包含 `contract_version` manifest 节，列出六文件路径与版本标记，作为唯一正式冻结包标识

**`03_最终执行任务书.md`**

"面向执行"的操作化定义：每个执行步骤必须包含以下四项，缺一不可：
1. **Phase/Gate 归属**：如 `Phase 0 / G0`、`Phase 2A / G2`
2. **执行主体**：SQL / Python 脚本 / Playwright / 人工操作 —— 必须指明
3. **预期产出或可验证状态**：明确写出期望的表行数、返回值、页面状态或 schema 存在性
4. **停机条件**：若该步骤结果不符合预期，后续哪些步骤必须暂停

必须按以下 Phase 结构组织，不得跨级合并：

```
Phase 0 → Gate G0（合同与 Gate 冻结）
Phase 1 → Gate G1（治理快照与规则 seed）
Phase 2A → Gate G2（real full_initialization）
Phase 2B → Gate G3（real rolling）
Phase 3 → Gate G4 / G5 / G6（读模型 API / governance / baseline & profile）
Phase 4 → Gate G7（compare 降级验收）
Phase 5 → 总体验收（Playwright P00-P11）
```

步骤编号格式：`P<phase>-G<gate>-<seq>`，例：`P2A-G2-03`

**`04_最终校验清单.md`**

- 按 Gate G0-G7 + Playwright 分组
- 每条校验项格式：`[步骤编号锚点] 校验内容 | 验收方法（SQL / Playwright / 目测）| 通过标准`
- 步骤编号必须与 `03_最终执行任务书.md` 中的编号完全一致
- 不允许存在任务书有而校验清单没有的步骤，反之亦然

---

### 2. PG17 数字透传规则

凡涉及计数、比例、差集、缺口的正式说明，必须直接写入来自 `01_最终冻结基线.md` § 3 的 PG17 冻结值，**禁止用"以 PG17 为准"或"以数据库为准"代替具体数值**。

以下为必须透传的关键数字清单：

| 指标 | 冻结值 |
|---|---:|
| `rebuild2.l0_gps` | 38,433,729 |
| `rebuild2.l0_lac` | 43,771,306 |
| `filtered_with_lon_lat`（trusted 损耗正式口径） | 11,350,552 |
| `filtered_pct` | 31.27% |
| `rebuild2_meta.field_audit` 总计 | 27（keep=17 / parse=3 / drop=7） |
| `rebuild2_meta.target_field` | 55 |
| active `ods_clean_rule`（ODS 定义层） | 26 |
| `ods_clean_result` distinct `rule_code`（ODS 执行层） | 24 |
| ODS 差集 | `NULL_WIFI_MAC_INVALID`、`NULL_WIFI_NAME_INVALID` |
| `batch_snapshot` stage 数 | 4（input / routing / objects / baseline） |
| `batch_snapshot` metric 数 | 11 |

---

### 3. 口径收口规则

以下废弃表述禁止出现在任何 `03_final/` 文件中：

| 禁止使用 | 替代为 |
|---|---|
| `filtered_with_gps` | `filtered_with_lon_lat` |
| "有 GPS" | "被过滤且经纬同时非空" |
| "约 60 个字段" | `target_field = 55` |
| `01_rebuild4_*` / `02_rebuild4_*` 旧文件命名 | `03_final/00~05` 新命名 |
| `contract_version` = "两份文档 hash" | 六文件冻结包 manifest |

---

### 4. 收口项落地规则

`decisions/01_待裁决问题清单.md` § 5 中的 5 条不上抛收口项（FZ-001 ~ FZ-005）必须在以下对应文件中显式体现，不得遗漏：

| 编号 | 收口内容 | 必须体现的目标文件 |
|---|---|---|
| FZ-001 | 文件命名统一为 `03_最终执行任务书.md` 与 `04_最终校验清单.md` | `00_最终冻结基线.md`（manifest 节） |
| FZ-002 | `contract_version` 升级为六文件冻结包 manifest | `00_最终冻结基线.md` |
| FZ-003 | trusted 损耗固定为 `filtered_with_lon_lat` | `02_数据生成与回灌策略.md` + `03_最终执行任务书.md` |
| FZ-004 | launcher 明确为独立运维入口、不计入 G0-G7 | `01_最终技术栈与基础框架约束.md` + `05_本轮范围与降级说明.md` |
| FZ-005 | 数据生成与回灌策略独立成 `02_数据生成与回灌策略.md` | `02_数据生成与回灌策略.md`（独立文件本身即为落地） |
