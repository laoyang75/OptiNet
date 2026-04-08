# rebuild4 冻结包六文件综合评估报告

> 评估时间：2026-04-06  
> 评估范围：`rebuild4/docs/03_final/00_05` 六文件 + `rebuild4_冻结包修复建议文档.md`  
> 评估方法：逐条对照修复建议文档，检查六文件现版本是否已修复各问题；并独立评估六文件是否存在遗留或新增问题。

---

## 一、修复建议文档各问题的修复状态

### 阻断级问题（FR）

| 编号 | 问题摘要 | 修复状态 | 核查依据 |
|---|---|---|---|
| **FR-01** | G0 与 G1 顺序矛盾（P0-G0-02 要求写 rebuild4_meta，但 schema 在 G1 才建） | ✅ **已修复** | `00.md` L120 明确"G0 只读，首个 DB 写动作在 G1 bootstrap 后"；`03.md` P0-G0-02 改为"校验 G0 只读性质与升版规则"，不再有写库动作；P1-G1-01 才建 schema；P1-G1-03 才写入 contract_version |
| **FR-02** | 冻结包伪封口：任务书仍允许执行期重新生成正式包 | ✅ **已修复** | `00.md` §2.3 明确包外裁决文件只作历史留档；P0-G0-01 改为"只读校验"；P0-G0-03 改为校验"无新增裁决且执行期不依赖包外文件"；package 升版规则写入 §4.2 |
| **FR-03** | API envelope `context.*` 歧义，诚实空状态 JSON 未定义 | ✅ **已修复** | `01.md` §3.1 补了强制 JSON 样例，明确 `context` 必须是对象；§3.2 诚实空状态合同表精确到每类 API、HTTP 状态码、`data` 形状、附加规则 |
| **FR-04** | `subject_scope` 与页面主语矩阵缺失 | ✅ **已修复** | `01.md` §3.3 写明 flow/runs/objects 等 8 类页面各自的主语；`03.md` 附录 C page_api_subject_matrix 完整落地（page_id / route / API / subject_scope / context 键 / empty-state / 是否允许 compare / gate） |
| **FR-05** | G4/G5/G6 在校验清单中脱节，验收流于抽检 | ✅ **已修复** | `04.md` §1 使用规则第 4 条明确"G4 只验 envelope 语义，G5 才验 governance 完整性，G6 才验 baseline/profile 完整性"；G4/G5/G6 校验项分别点名 endpoint 与字段，不再写"抽检/至少" |

### 高优先级修复项（FR-06 至 FR-13）

| 编号 | 问题摘要 | 修复状态 | 核查依据 |
|---|---|---|---|
| **FR-06** | 12 个页面与实际路由数量对不上 | ✅ **已修复** | `05.md` §1.3 给出唯一解释：逐条列出 12 条，明确 `/objects/:id` 不单独计页、`batches` 是子资源、compare 和 P00 不计入 |
| **FR-07** | 观察工作台"三段式"表述与实际四状态矛盾 | ✅ **已修复** | `02.md` §6.1 固定为"三阶段 + 第三阶段双结果桶"，明确命名 `promoted_this_batch` / `converted_to_issue_this_batch`；`03.md` P5-GPW-05 与附录 A PF-05 都使用该固定口径 |
| **FR-08** | 异常工作台数据合同未冻结（字段/枚举/双视角） | ✅ **已修复** | `02.md` §6.2 补全对象级/记录级/影响链三组最小字段；`severity` 固定 `high/medium/low`；`forbid_anchor`/`forbid_baseline`/`downstream_impact` 正式命名；双视角明确绑定 API-07 |
| **FR-09** | rolling 窗口合同未冻结（时区/粒度/边界/late data） | ✅ **已修复** | `02.md` §5.2 rolling_window_contract 表：字段=`event_time(ts_std)`、时区=`Asia/Shanghai`、粒度=2h、边界=左闭右开、late data=rerun batch、幂等键、禁止手工切片 |
| **FR-10** | seed 来源还是"文档/SQL/Python"多源，无优先级 | ✅ **已修复** | `02.md` §3.3 seed_source_manifest 表给出 5 级优先级白名单；规定"正式执行只承认 canonical seed 导入结果"；conflict 必须先在 canonical seed 裁平 |
| **FR-11** | launcher 既像范围内又像范围外，没有唯一解释 | ✅ **已修复** | `01.md` §4.2 launcher 落点表明确"本轮实现义务 = 仅冻结接口保留名，不进入执行/验收闭环"；`05.md` §3 和 §4.2 明确 launcher 独立、不影响 G0-G7 |
| **FR-12** | "不重新跑页面"与 Phase 5 Playwright 逻辑冲突未澄清 | ✅ **已修复** | `00.md` §1.3 专门拆分"冻结期页面依据"与"执行期页面验收"两个概念，明确 Playwright 证据只用于验证冻结结论，不反向改口径 |
| **FR-13** | 六文件缺 DDL 最小合同与 API 路径合同 | ✅ **已修复** | `03.md` 附录 B（12 个核心 API 家族表：path/subject_scope/context 键/空态/Gate）和附录 D（DDL 最小合同：每表列集、PK/UK/FK 约束）已补全 |

### 待确认问题（FC）

| 编号 | 问题摘要 | 修复状态 | 核查依据 |
|---|---|---|---|
| **FC-01** | `trusted_filter` 是否为旧口径残留 | ✅ **已澄清** | `02.md` §8.3 明确"`trusted_filter` 视为旧命名，不再作为正式接口或页面模块名称"；`01.md` §4.1 强制 `trusted_loss` |
| **FC-02** | `batches` 是独立 API 还是 `/runs` 的子资源 | ✅ **已澄清** | `05.md` §1.3 + `03.md` 附录 A PF-03：`/api/batches/:id/detail` 是 `/runs` 的子资源，无独立页面 |
| **FC-03** | 冻结包内部矛盾是否触发第 4 类上抛条件 | ✅ **已澄清** | `00.md` §4.1 规则 4 + `05.md` §5：上抛只 3 类；本次修订已把矛盾关闭在正式文件里，不增加第 4 类 |

---

## 二、修复建议文档 13 个问题全部修复——结论

修复建议文档中提出的 **5 个阻断级 + 8 个高优先级 + 3 个待确认问题**，在当前六文件版本（`rebuild4-final-freeze-2026-04-06-v2`）中**已全部得到修复或澄清**，无遗漏。

---

## 三、六文件现版本的残留与新增问题

### 3.1 仍需关注的问题（非阻断，但有执行风险）

#### 问题 N-01：`/api/batches/:id/detail` 子路径的主语未单独注册

- **所在位置**：`03.md` 附录 B API-03 / 附录 C PF-03
- **问题描述**：API-03 和 PF-03 的 `subject_scope` 统一写为 `run`。但 `/api/batches/:id/detail` 是 batch 详情，其 envelope 的主语理论上应为 `batch` 而非 `run`。目前附录 B/C 对这个子路径没有单独注册主语，可能导致后端对 batch 详情 API 的 envelope 使用 `run` 还是 `batch` 产生歧义。
- **建议**：在附录 B API-03 的备注中补一行："`/api/batches/:id/detail` 的 `subject_scope` 为 `batch`，不继承父路径的 `run`"。

#### 问题 N-02：附录 D DDL 未覆盖主链五张事实表（fact_*）

- **所在位置**：`03.md` 附录 D
- **问题描述**：附录 D 列出了控制层、元数据层的关键表，但未包含 `fact_standardized`、`fact_governed`、`fact_pending_observation`、`fact_pending_issue`、`fact_rejected` 五张主链事实表的最小列集与约束。这五张表是 G2 四分流守恒约束的主体，但 DDL 合同缺列。
- **风险**：G2 守恒约束 `fact_standardized = fact_governed + ...` 的前提是这些表有统一的主键与 FK，但当前附录 D 没有为此冻结任何约束，各数据工程师可能自行设计列名。
- **建议**：在附录 D 补充这五张表的最小列集（至少包含主键、`run_id`、`batch_id`、`data_origin`、`record_count` 与防回写约束）。

#### 问题 N-03：G0 校验项仍为"目测"，未改为可执行断言

- **所在位置**：`04.md` G0 检查项 P0-G0-01/02/03
- **问题描述**：G0 的三个检查项验收方式全部写为"目测"，而其他 Gate 已经改为 SQL / Playwright / 逐字段检查。G0 的校验完全可以写成"Python 脚本验证文件存在 + YAML lint manifest"的自动化形式。
- **风险**：执行期如果忽视目测，G0 可能成为橡皮图章，无法对执行期非法改文形成阻断。
- **建议**：将 P0-G0-01 的验收方式从"目测"改为"Python 脚本"，具体断言为：列举六文件文件名 + 检查 manifest yaml 中所有 version 字段值均等于 `rebuild4-final-freeze-2026-04-06-v2`。

#### 问题 N-04：governance 12 个子路径的 query 参数未全部展开

- **所在位置**：`03.md` 附录 B API-11
- **问题描述**：API-11 的"正式路径"将 12 个 governance endpoint 合并在一行，各子路径的 query 参数（分页、过滤、is_active 等）没有独立列出。例如：`ods_rules` 是否支持分页？`parse_rules` 是否需要 `is_active` 过滤？
- **风险**：这 12 个 governance endpoint 的参数细节留给了实现者自行约定，等于在 G5 门口留了一个自由发挥窗口。
- **建议**：将 API-11 拆成 12 行，每行单独列出路径、query 参数与响应形状，或者在 `01.md` 新增"governance API 参数约束"小节。

#### 问题 N-05：API 错误响应格式（4xx/5xx）未冻结

- **所在位置**：`03.md` 整体 / `01.md` §3
- **问题描述**：六文件对"成功态"的 envelope 做了详细约束，但对 4xx/5xx 错误响应的统一格式没有任何约束。P3-G4-02 中提到"显式 key 不存在时返回 404"，但 404 的 body 格式未定义（`data=null`？还是 `{error: "..."}`？）。
- **风险**：不同后端实现者可能返回完全不同的错误格式，前端需要适配多种格式，增加联调成本。
- **建议**：在 `01.md` §3 增加"统一错误响应格式"小节，至少冻结：HTTP 状态码枚举（400/404/500）、错误 body 最小结构（`{error_code, error_message}`）、是否要封装在 envelope 内。

#### 问题 N-06：`fact_standardized` 数据时间范围能否支持 G3 ">1 个 completed batch"未预评估

- **所在位置**：`02.md` §5.1 / `05.md` §5
- **问题描述**：G3 完成标准是"completed batch > 1"（即至少 2 个完成批次）。但 `fact_standardized` 的数据来源是 `l0_lac`（43,771,306 条），如果这批数据的时间跨度不足 4 小时（即不足以切出 2 个 2 小时窗口），G3 将永远无法满足 ">1"。
- **风险**：`02.md` §5.1 将此列为"异常上抛条件"，但没有预先给出评估结论。这是执行期最高概率的阻断风险点。
- **建议**：在 G1 完成之前，对 `rebuild2.l0_lac` 执行一次时间范围查询（`SELECT MIN(ts_std), MAX(ts_std) FROM rebuild2.l0_lac`），确认是否覆盖 ≥4 小时跨度，并把结论写回 `00.md` 的 PG17 事实冻结基线表。

---

## 四、子 Agent 使用机会评估

### 4.1 当前文档设计对子 Agent 的支持度

当前六文件的附录 A/B/C/D 已经构成高质量的"机器可读合同"，为引入子 Agent 提供了良好基础。以下评估在**开发执行阶段**哪些环节可以引入子 Agent 模式，提升并行度和可审计性。

### 4.2 强烈建议引入子 Agent 的 6 个场景

| 场景 | 建议的子 Agent | 输入（驱动合同） | 输出 | 优势 |
|---|---|---|---|---|
| **G0 冻结包校验** | `Gate-Checker-Agent` | 六文件 manifest yaml | 文件名核验 + yaml lint 报告 | 消除"目测"依赖，G0 变为可重复执行的自动化入口 |
| **G1 DDL 自动化建表** | `DDL-Bootstrap-Agent` | 附录 D DDL 最小合同 + PG17 连接 | SQL 建表脚本 + 执行结果 | 直接以附录 D 为合同驱动建表，消除人工编写 DDL 的偏差 |
| **G1 canonical seed 生成** | `Seed-Generation-Agent` | `seed_source_manifest` 白名单（优先级 1-5）+ PG17 查询权限 | canonical seed CSV/SQL + `source_reference` 字段 | 自动从白名单来源抽取并合并，有冲突时报告人工裁决，不留给开发时临场处理 |
| **G2/G3 数据守恒校验** | `Data-Consistency-Agent` | 当前 `batch_id`、四分流表名、11 metric 约束 | 守恒校验报告 + 通过/失败 | 可在每个 batch 完成后自动触发，替代人工 SQL 检查 |
| **G4/G5/G6 API 合同验收** | `API-Contract-Agent` | 附录 B/C API 合同 + FastAPI 服务地址 | 逐 endpoint 断言报告（envelope/status/数据形状）| 后端 API 部署后自动跑完整合同验收，不依赖人工目测 |
| **Phase 5 Playwright 验收** | `Playwright-Agent` | 附录 A 12 个页面规格 + 前端 URL | 截图 + 逐 case 通过/失败报告 | 附录 A 已完全参数化，可并行跑 12 个页面 |

此外，建议增加一个 **`Gate-Audit-Agent`**：在各 Gate 通过后，自动把结果写入 `gate_run_result` 表，把 Gate 从"文档口头验收"升级为"有数据库记录的可审计验收"。

### 4.3 子 Agent 协作架构建议

```
Orchestrator（主控 Agent）
├── Phase 0:
│   └── Gate-Checker-Agent（自动验证六文件 manifest）
├── Phase 1:
│   ├── DDL-Bootstrap-Agent（建库建表，以附录 D 为合同）
│   └── Seed-Generation-Agent（canonical seed 生成，以 seed_source_manifest 为白名单）
├── Phase 2A:
│   ├── Initialization-Run-Agent（执行 full_init 主链）
│   └── Data-Consistency-Agent（四分流守恒校验）
├── Phase 2B:
│   ├── Rolling-Window-Agent（按 rolling_window_contract 切窗并执行）
│   └── Data-Consistency-Agent（每批 snapshot 校验）
├── Phase 3（G4/G5/G6 可并行）：
│   ├── API-Bootstrap-Agent（生成 FastAPI routes/handlers 骨架，以附录 B 为合同）
│   └── API-Contract-Agent（合同验收，以附录 B/C 为驱动）
├── Phase 4:
│   └── Compare-Validation-Agent（验证 compare 降级身份与 banner 规则）
└── Phase 5:
    └── Playwright-Agent（页面验收，以附录 A 12 个页面为驱动）

（横切关注点）
    └── Gate-Audit-Agent（各 Gate 通过后写入 gate_run_result，生成可审计证据链）
```

### 4.4 当前文档对子 Agent 的四个障碍

在正式引入子 Agent 之前，以下四个问题是障碍，需要先在文档层面修复：

| 障碍 | 来源问题 | 影响的 Agent | 建议修复方式 |
|---|---|---|---|
| `fact_*` 五表无 DDL 合同 | N-02 | DDL-Bootstrap-Agent 无法建主链事实表 | 补充附录 D 对应五行 |
| G0 校验为"目测" | N-03 | Gate-Checker-Agent 无法自动化 G0 | 改为 Python 脚本断言规格 |
| governance 参数未展开 | N-04 | API-Contract-Agent 无法自动生成 governance 完整测试 | 补充 API-11 子路径参数 |
| 错误响应格式未冻结 | N-05 | API-Contract-Agent 无法验证 4xx 行为 | 补充统一错误响应格式 |

### 4.5 子 Agent 引入顺序建议

建议按以下顺序逐步引入，而不是一次性全上：

1. **第一步（G1 之前）**：先引入 `Gate-Checker-Agent` + `DDL-Bootstrap-Agent`，验证附录 D 的可执行性。
2. **第二步（G1 期间）**：引入 `Seed-Generation-Agent`，验证 seed_source_manifest 白名单的完备性。
3. **第三步（G2/G3 期间）**：引入 `Data-Consistency-Agent`，每批次自动守恒校验。
4. **第四步（G4 期间）**：引入 `API-Contract-Agent`，以附录 B/C 为合同驱动自动验收。
5. **第五步（Phase 5）**：引入 `Playwright-Agent`，以附录 A 驱动页面验收。

每步引入前，先验证对应附录的可执行性，发现歧义立即修正文档，不带歧义进下一步。

---

## 五、综合结论

| 维度 | 结论 |
|---|---|
| 修复建议文档问题修复状态 | ✅ **13/13 全部已修复**，无遗漏 |
| 六文件现版本整体质量 | 🟡 **良好，有 6 个仍需关注的风险点**（N-01 至 N-06） |
| 最高优先级风险 | **N-02**（fact_* DDL 缺失）+ **N-06**（G3 时间跨度未预评估） |
| 子 Agent 强烈建议场景 | ✅ **6 个场景 + 1 个横切 Agent**，附录 A/B/C/D 已具备驱动条件 |
| 子 Agent 引入的主要障碍 | N-02/N-03/N-04/N-05 四个文档缺口需先修复 |
| 是否可进入执行阶段 | 🟢 **可进入**；N-01 至 N-05 建议在 G1/G4 内部消化，N-06 建议 G1 前先跑一次时间范围查询再决定 |
