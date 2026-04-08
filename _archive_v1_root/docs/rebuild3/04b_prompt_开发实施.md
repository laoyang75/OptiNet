# Prompt B：rebuild3 开发实施（UI 审查确认后使用）

> **使用前提**：本 Prompt 必须在 Prompt A 的 UI 设计方案经人工审查并确认后才能启动。  
> **使用顺序**：先完成 Prompt A → 人工审查 UI → 确认后使用本 Prompt 进入开发。

---

## 你的角色

你现在扮演 **首席架构师 + 技术负责人 + 全栈实现负责人**。

**以下文档已存在，请直接读取（不需要等待提供）：**

1. `docs/rebuild3/01_rebuild3_说明_最终冻结版.md`（迁移后为 `rebuild3/docs/01_rebuild3_说明_最终冻结版.md`）
2. `docs/rebuild3/02_rebuild3_预实施任务书_最终冻结版.md`（迁移后为 `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md`）
3. `docs/rebuild3/03_rebuild3_技术栈要求_最终冻结版.md`（迁移后为 `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md`）
4. `docs/rebuild3/UI_v2/` — 已审查确认并完成修复的 UI v2 设计方案（迁移后为 `rebuild3/docs/UI_v2/`）
5. `docs/rebuild3/UI_v2/design_notes.md` — 整体信息架构与组件边界说明（迁移后为 `rebuild3/docs/UI_v2/design_notes.md`）
6. `docs/rebuild3/Docs/UI_v2_审计后修改执行清单.md` — UI 修正执行清单（迁移后为 `rebuild3/docs/Docs/UI_v2_审计后修改执行清单.md`）
7. `docs/rebuild3/Docs/rebuild3_开发文档最终修订补丁.md` — UI 确认后的最终开发补丁（迁移后为 `rebuild3/docs/Docs/rebuild3_开发文档最终修订补丁.md`）

> 注意：在第 0 步完成目录迁移之前，请先从 `docs/rebuild3/` 读取；迁移完成后，后续所有引用统一改为 `rebuild3/docs/`。  
> 若 UI 原型中仍有少量命名残留（如 `pending_obs`、`rule_version`），以“最终冻结文档 + 开发文档最终修订补丁”为准完成归一化，不再回退重做 UI 方案。

你的任务是：先建立正确的目录结构与项目基础，再根据冻结文档和已确认 UI 方案，分阶段完成 rebuild3 的完整开发与验证。

---

## 第 0 步：建立项目目录结构（必须最先执行）

**在写任何业务代码之前，你必须先完成项目目录的初始化和文档迁移。**

### 0.1 在项目根目录创建 `rebuild3/`

在项目根目录（即与 `rebuild2/`、`docs/` 同级的位置）创建以下目录结构：

```
rebuild3/
├── docs/                        # 从 docs/rebuild3/ 迁移过来的全部文档
│   ├── UI/                      # 旧版 UI 产物（保留只读）
│   ├── UI_v2/                   # 当前已确认的 UI v2 产物（开发以此为准）
│   └── Docs/                    # 审计、修正清单、开发补丁
│
├── backend/                     # Python + FastAPI 后端
│   ├── app/
│   │   ├── api/                 # FastAPI 路由
│   │   ├── core/                # 配置、数据库连接
│   │   ├── models/              # Pydantic 模型
│   │   ├── services/            # 业务逻辑层
│   │   └── main.py
│   ├── sql/                     # 所有 SQL 文件（按阶段分目录）
│   │   ├── schema/              # DDL：schema、table、index
│   │   ├── init/                # 初始化阶段 SQL
│   │   ├── increment/           # 增量处理 SQL
│   │   ├── govern/              # 治理逻辑 SQL
│   │   └── baseline/            # Baseline 生成与刷新 SQL
│   ├── scripts/                 # 工具脚本（数据导入、验证等）
│   └── requirements.txt
│
├── frontend/                    # Vue 3 + Vite + TypeScript 前端
│   ├── src/
│   │   ├── views/               # 页面级组件
│   │   ├── components/          # 共享组件
│   │   ├── stores/              # Pinia 状态
│   │   ├── api/                 # API 接入层
│   │   ├── types/               # TypeScript 类型定义
│   │   └── router/              # Vue Router
│   └── package.json
│
├── launcher/                    # 独立启动器
│   ├── launcher.py              # Python 启动脚本
│   ├── launcher_ui/             # 启动器前端（独立静态页面）
│   │   └── index.html
│   └── README.md
│
├── config/                      # 配置文件
│   ├── thresholds.yaml          # 阈值配置（资格矩阵、四分流参数等）
│   ├── versions.yaml            # 版本绑定配置
│   └── services.yaml            # 启动器服务配置（端口、命令等）
│
└── README.md                    # 项目说明
```

### 0.2 迁移 `docs/rebuild3/` → `rebuild3/docs/`

将当前 `docs/rebuild3/` 目录下的**所有文件**迁移到 `rebuild3/docs/` 下：

```bash
# 迁移文档（保留原目录结构）
cp -r docs/rebuild3/* rebuild3/docs/

# 验证迁移完整性
ls rebuild3/docs/
```

**迁移后验证清单：**
- [ ] `rebuild3/docs/01_rebuild3_说明_最终冻结版.md` 存在
- [ ] `rebuild3/docs/02_rebuild3_预实施任务书_最终冻结版.md` 存在
- [ ] `rebuild3/docs/03_rebuild3_技术栈要求_最终冻结版.md` 存在
- [ ] `rebuild3/docs/UI_v2/` 目录及所有 HTML / _doc.md 存在
- [ ] `rebuild3/docs/UI_v2/design_notes.md` 存在
- [ ] `rebuild3/docs/Docs/UI_v2_审计后修改执行清单.md` 存在
- [ ] `rebuild3/docs/Docs/rebuild3_开发文档最终修订补丁.md` 存在

> ⚠️ 迁移完成并验证后，原 `docs/rebuild3/` 目录可保留（只读），不删除。  
> 后续所有开发引用的文档路径均以 `rebuild3/docs/` 为准。

### 0.3 初始化配置文件

在 `rebuild3/config/` 下创建以下配置文件（从冻结文档中提取所有阈值参数落入配置）：

**`thresholds.yaml`** — 至少包含：
- 四分流判定阈值
- 晋升 / 降级窗口参数
- 异常检测阈值
- 资格矩阵参数

**`versions.yaml`** — 至少包含：
- `contract_version`
- `rule_set_version`
- `baseline_version` 初始值

**`services.yaml`** — 启动器服务定义（每个服务的名称、命令、端口、工作目录）

---

## 总原则（必须遵守）

1. 以最终冻结文档（`rebuild3/docs/`）作为**业务语义来源**
2. 以已确认的 UI v2 方案（`rebuild3/docs/UI_v2/`）作为**页面结构与读模型来源**
3. 以 `rebuild3/docs/Docs/rebuild3_开发文档最终修订补丁.md` 作为**实现级统一补丁来源**
4. 发现文档与 UI 存在冲突时，先显式列出冲突并给出收敛方案，再进入实现
5. 不允许回退到 rebuild2 的旧 Step 页面思路
6. 必须坚持：SQL-first / 本地 PG17 / Python + FastAPI / Vue 3 + TypeScript + Vite
7. `rebuild2 / rebuild2_meta / legacy` schema 一律只读，不可改写
8. 所有关键阈值、资格矩阵、版本绑定、幂等口径必须显式配置化（写入 `config/`）
9. 先样本后全量，先可回放后优化性能
10. 当前批次只看上一版冻结 baseline，不能边判边刷
11. “基础数据治理”是首轮正式页面，不是后补页面
12. 对 UI v2 中残留的 `pending_obs`、`rule_version`、缺失版本上下文条等问题，必须在实现阶段统一归一化

---

## 第 1 步：实施前对齐

完成目录初始化后，输出一份**实施前对齐结果**，至少包含：

1. 你如何理解 rebuild3 的业务主语
2. 文档与 UI 方案之间是否存在冲突（逐条列出）
3. 哪些地方已经足够冻结，可以直接开发
4. 哪些地方仍然只是参数，需要在 `config/` 中落地
5. 哪些地方要先做样本验证，不能直接全量开跑

---

## 第 2 步：最终实施任务书

输出真正可执行的 backlog，每个任务必须包含：**输入 / 输出 / 依赖 / 验收标准 / 回归风险 / 推荐实施顺序**

### A. 数据库与元数据任务

- `rebuild3 / rebuild3_meta` schema 创建
- 对象快照表（Cell / BS / LAC）
- 状态历史与关系历史表
- 标准事件层表
- 四层事实表（governed / pending_observation / pending_issue / rejected）
- 热层 / 长层 / 归档层设计
- run / batch / baseline / version 表
- batch 快照与批次汇总表（`batch_snapshot`、`batch_flow_summary` 等）
- 基础数据治理元数据表（字段目录 / 表目录 / 使用映射 / 迁移决策）
- 幂等键与索引策略
- 分区策略

### B. 后端核心模块任务

- 源适配（rebuild2 / legacy 只读接入）
- 标准化事件生成（`fact_standardized`）
- 初始化对象链路
- 增量四分流
- 等待池与观察池管理
- Cell 晋升与级联
- GPS 修正与信号补齐
- 异常检测模块
- baseline / profile 生成与刷新
- 回放对比引擎

### C. API 与读模型任务

- 运行中心读模型
- 对象列表与对象详情读模型
- 等待池读模型
- 异常看板读模型
- baseline / profile 读模型
- 基础数据治理读模型
- 回放对比读模型
- 分页、筛选、缓存与聚合策略

### D. 前端任务

- Vue 3 + Vite + TypeScript 工程初始化
- 路由与状态管理（Vue Router + Pinia）
- 页面级组件（严格按已确认 UI 方案实现）
- 共享组件（状态徽标、筛选器、对象卡片等）
- `VersionContext` 共享组件
- 详情抽屉组件
- 图表组件
- API 接入层
- 状态表达一致性验证

### E. 启动器任务

实现独立 Python 启动器 (`launcher/launcher.py`)：

- 读取 `config/services.yaml` 获取服务定义
- 提供 HTTP API 供启动器前端调用：
  - `POST /service/{name}/start` — 启动服务
  - `POST /service/{name}/stop` — 停止服务
  - `POST /service/{name}/restart` — 重启服务
  - `POST /service/{name}/kill-port` — 强制杀掉端口占用进程
  - `GET /service/{name}/status` — 获取服务状态（运行中/已停止/错误，PID，运行时长）
  - `GET /service/{name}/logs` — 获取服务实时日志（SSE 流）
  - `POST /service/{name}/logs/clear` — 清空日志缓冲
- 启动时自动在浏览器打开 `launcher/launcher_ui/index.html`
- 将已审查确认的启动器 UI 设计（`rebuild3/docs/UI/launcher/launcher.html`，若后续迁移到 `UI_v2` 以最终确认版本为准）移植为实际可用的启动器前端

### F. 验证与回归任务

- 样本数据验证（3 天初始化样本）
- 3 天初始化最小闭环验证
- 4 天增量回放验证
- 7 天直接初始化 vs 3+4 天对比
- 收敛指标输出
- 性能基准与慢 SQL 排查

---

## 第 3 步：推荐开发顺序

```
Phase 0：目录初始化 + 文档迁移 + schema/metadata/config
Phase 1：standardize + init bootstrap 最小闭环（样本级）
Phase 2：increment route + waiting pool + cascade（四分流完整链路）
Phase 3：govern + anomaly + profile（治理核心）
Phase 4：API / read model（FastAPI 读模型层）
Phase 5：前端页面（严格按已确认 UI 方案）
Phase 5.5：启动器（launcher.py + 启动器前端）
Phase 6：replay validation + convergence comparison（回放验证收敛）
```

你可以根据实际情况调整顺序，但必须说明原因。

---

## 第 4 步：进入实现

在输出最终实施任务书之后，**不要停在纸面计划**，继续进入实现阶段：

1. 先做样本级闭环，再做全量
2. 每完成一个阶段都做最小可验证结果（输出验证报告）
3. 所有 SQL 和代码都要与最终冻结文档保持一致
4. 所有前端页面都要与已确认 UI 方案保持一致
5. 如需改动任何冻结口径，必须先显式说明改动原因和影响范围

---

## 第 5 步：持续文档维护

在开发过程中持续维护以下文档（写入 `rebuild3/docs/`）：

1. `impl_plan.md` — 最终实施任务书（如有变更要更新）
2. `param_matrix.md` — 参数与资格矩阵清单
3. `api_models.md` — API / 读模型清单
4. `replay_log.md` — 回放与验证记录
5. `issues.md` — 已知问题与待优化项清单

---

## 实现约束（硬性约束，不可违反）

### 状态与资格

- 不允许把生命周期和健康状态重新混成一个枚举
- 不允许省略 `anchorable` / `baseline_eligible`
- `watch` 只允许做 UI 派生状态，不做 DB 主状态

### 事实分层

- 不允许只落一张总事实表
- 必须保留全部五层：
  - `fact_standardized`
  - `fact_governed`
  - `fact_pending_observation`
  - `fact_pending_issue`
  - `fact_rejected`

### 版本与幂等

- 必须显式落库：`run_id` / `contract_version` / `rule_set_version` / `baseline_version`
- `run_id` 与 `batch_id` 不可混用
- 标准事件幂等键必须显式存在

### 数据层

- 不允许只有 per-Cell 热明细，而没有长层 / 归档层边界
- 不允许直接修改 `rebuild2 / rebuild2_meta / legacy`

### 前端

- 不允许退回旧 Step 页面心智
- 不允许在没有读模型的情况下直接拼底层表
- 不允许在 UI 已确认后随意改页面结构而不说明原因
- 不允许继续在实现代码中使用 `pending_obs`、`fact_pending_obs`、`rule_version` 这类残留命名
- 核心页面必须统一接入版本上下文条；若 UI 原型缺失，也要在实现阶段补齐

---

## 你的输出风格要求

1. 先收敛（对齐），再计划（任务书），再实现
2. 不要只给抽象建议，要给结构化输出
3. 不要停在"我建议"，落实到可执行任务和实现顺序
4. 计划后继续推进实现，不要停在 backlog
5. 所有内容都以 `rebuild3/docs/` 中的冻结文档和已确认 UI 方案为准

---

> **下一步**：本 Prompt 完成后，rebuild3 项目应达到：目录结构完整、所有服务可通过启动器管理、核心数据链路可通过样本验证、前端与 UI 方案完全一致。
