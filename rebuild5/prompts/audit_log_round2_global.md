# rebuild5 二轮总纲审计记录

> 本文件用于记录 `10a_全局总纲审计.md` 的进度与结论。新会话开始时先读本文件确认进度。

## 审计进度

- G0 系统定位：done
- G1 核心原则：done
- G2 实体模型：done
- G3 生命周期与资格：done
- G4 全局常量：done
- G5 数据集与版本：done
- G6 模块边界：done
- G7 README 角色：done
- GX 跨步骤逻辑审查：done

## 详细记录

## G0 系统定位

- 状态：done
- 当前判断：三分法（运行主链 / 控制侧链 / 服务层）仍然准确且有效
- 关键证据：
  - 代码结构严格对应：etl→profile→evaluation→enrichment→maintenance = Step 1-5 运行主链；pipeline_router 的 `from_step` 参数化 = 控制侧链（冷启动/参数重跑/全量回归）；service_router = 服务层
  - 控制侧链不是独立代码模块，而是同一管道的不同编排模式（`POST /api/pipeline/run?from_step=N`），doc 09 已准确描述
  - DB 验证：Step 1 已跑通（etl_cleaned 45M 行），Step 2-5 表结构就绪但数据为空，trusted_cell_library 等 Step 5/6 产出表尚未创建
  - 服务层（doc 06）明确定义为"只读消费层"，与管道层读写分离
- 建议动作：**保留**
- 已修改文档：无
- 下一步：无需修改

## G1 核心原则

- 状态：done
- 当前判断：三条核心原则（Frozen Snapshot / Cell-First / Correct Before Drop）仍然是最高优先级约束，表述准确
- 关键证据：
  - **Frozen Snapshot**：evaluation/pipeline.py:421-434 用 `WHERE batch_id = previous_batch_id` 严格隔离读取范围；enrichment/pipeline.py:194-199 用 `MAX(batch_id)` 锁定上一版可信库；maintenance/publish_cell.py:100-125 只读冻结快照中 qualified/excellent 状态
  - **Cell-First**：evaluation/pipeline.py:33→40→48 严格按 build_current_cell_snapshot → build_current_bs_snapshot → build_current_lac_snapshot 顺序执行；BS/LAC 的 lifecycle_state 由下属实体聚合派生
  - **Correct Before Drop**：clean.py ODS 规则全部为 nullify（置空）或 flag_gps（标记），不直接删行；仅 cell_id=NULL 或 event_time_std=NULL 时才在最终过滤中删除行（clean.py:9 FINAL_ROW_FILTER）
- 建议动作：**保留**
- 已修改文档：无
- 下一步：无需修改

## G2 实体模型

- 状态：done
- 当前判断：三层实体定义（LAC/BS/Cell）、唯一键和上卷关系仍然准确
- 关键证据：
  - 代码中实际 PK：Cell=(batch_id, operator_code, lac, cell_id)，BS=(batch_id, operator_code, lac, bs_id)，LAC=(batch_id, operator_code, lac)
  - 业务唯一键与总纲一致：Cell=(operator_code, lac, cell_id)，BS=(operator_code, lac, bs_id)，LAC=(operator_code, lac)；batch_id 仅为版本维度
  - 层级上卷关系在代码中通过 GROUP BY 和 JOIN 严格实现：Cell→BS 用 (operator_code, lac, bs_id) 聚合，BS→LAC 用 (operator_code, lac) 聚合
  - 总纲补充约定中"tech_norm 不进入全局业务唯一键"在代码中得到确认：PK 中不包含 tech_norm
- 建议动作：**保留**
- 已修改文档：无
- 下一步：无需修改

## G3 生命周期与资格

- 状态：done
- 当前判断：状态定义和三层资格的总纲描述基本准确，有两处需要修订
- 关键证据：
  - 6 个状态在代码中均定义（profile/logic.py:13-20），排名准确
  - BS/LAC 当前评估代码只产生 waiting/observing/qualified，**不产生 excellent**（evaluation/pipeline.py:298-304、369-374）。总纲写的"先保留为状态位"与实际一致，不是错误
  - dormant/retired 在 maintenance/publish_cell.py:131-137 中实现，用 active_days_30d 和 consecutive_inactive_days 判定
  - **baseline_eligible 实现偏差**：总纲写的是"已 anchor_eligible + 无防毒化异常 + 成熟条件"，但代码实际是 `anchor_eligible AND lifecycle_state = 'excellent'`（evaluation/pipeline.py:225-226）。代码更简洁，防毒化异常检查实际在 Step 5 维护阶段执行而非 Step 3 资格判定时
  - BS/LAC 的 anchor_eligible 和 baseline_eligible 使用 BOOL_OR 上卷，与总纲描述一致
- 建议动作：**修订**
  - `00_全局约定.md` Cell baseline_eligible 规则应对齐代码：改为"已 anchor_eligible=true 且 lifecycle_state='excellent'"
  - 补充说明"防毒化检查在 Step 5 维护阶段执行，不在 Step 3 资格判定时"
- 已修改文档：待执行
- 下一步：更新 00_全局约定.md 第 239-240 行

## G4 全局常量

- 状态：done
- 当前判断：00_全局约定.md 中的常量与代码一致；README.md 中的信号范围**过时**
- 关键证据：
  - 坐标常量 85300/111000：代码中广泛使用（30+ 处），与总纲一致
  - 坐标有效范围 73~135 / 3~54：clean.py ODS-015/016 与总纲一致
  - 信号范围对照：

    | 字段 | README | 00_全局约定 | 代码 (clean.py) | 判定 |
    |------|--------|-------------|-----------------|------|
    | RSRP | -156~0 | -156~-1 | -156~-1 (0 视为无效) | README 过时 |
    | RSRQ | -50~0 | -34~10 | -34~10 | README 过时 |
    | SINR | -30~50 | -23~40 | -23~40 | README 过时 |

  - 85300 的适用性说明：00_全局约定.md 已注明"北京纬度近似，全国范围应按纬度带修正"，表述合理
- 建议动作：**修订** README.md 信号范围，与 00_全局约定.md 和代码对齐
- 已修改文档：待执行
- 下一步：更新 README.md 信号范围表

## G5 数据集与版本

- 状态：done
- 当前判断：单活数据集模式的描述在总纲和 README 中都准确
- 关键证据：
  - 代码中 `prepare_current_dataset()` 从 `config/dataset.yaml` 读取当前数据集，无多数据集切换 API
  - pipeline_router 的 `/run` 不接受 dataset 参数，默认使用当前活跃数据集
  - README 和 doc 07 均准确描述了"修改 yaml → 清理 → 重跑"的工作流
  - DB 中只有一套 rebuild5.* 表，没有按数据集隔离的 schema
  - 总纲中关于数据版本的表述"数据版本 = 数据集标记"在当前单活模式下准确
- 建议动作：**保留**
- 已修改文档：无
- 下一步：无需修改

## G6 模块边界

- 状态：done
- 当前判断：00_全局约定.md 承载了过多模块级细节，部分内容应下放
- 关键证据：
  - **应下放的内容**：
    - Cell/BS/LAC 晋升条件详细阈值表（行 159-202）→ 已在 `03_流式质量评估.md` 中有对应详细描述
    - 质量分级体系（position_grade/gps_confidence/signal_confidence/cell_scale，行 262-301）→ 属于 Step 3 评估的模块级细节
    - 漂移分类详细规则（行 303-329）→ 属于 Step 5 维护模块
    - 统一事件时间的具体 COALESCE 优先级和 source 枚举（行 332-362）→ 属于 Step 1 ETL 模块
  - **应保留的内容**：
    - 三条核心原则（Frozen Snapshot / Cell-First / Correct Before Drop）
    - 实体模型三层定义 + 唯一键 + 层级关系
    - 生命周期状态定义 + 状态流转图（不含阈值）
    - 三层资格的语义定义 + 关系表（不含具体阈值）
    - 物理常量（坐标范围、距离系数）
    - 运营商编码主表
    - 命名规范
  - 当前总纲 460+ 行，约 40% 内容属于模块级细节
- 建议动作：**下放**（标记哪些段落应移交，但本轮不执行大规模重组，避免破坏已有引用链）
- 已修改文档：无（本轮只标记，不执行大规模文档重组）
- 下一步：后续文档重构时参考此清单

## G7 README 角色

- 状态：done
- 当前判断：README 当前同时承担"产品总览"和"详细设计入口"两个角色，内容过多但结构清晰
- 关键证据：
  - README 540+ 行，包含完整的 Step 1-6 处理流程描述、控制侧链说明、UI 设计、与 rebuild4 的关系、目录结构
  - Step 描述与 detail docs 有大量重复，但 README 版本是简化版（ASCII 流程图 + 要点），detail docs 是展开版
  - 作为"agent 最高层理解入口"，README 提供了足够的全景视角，适合新 agent 快速建立上下文
  - 与 00_全局约定.md 的分工：README 偏"流程和产品"，00 偏"约束和规则"，分工合理
  - README 中信号范围值过时（已在 G4 记录），其余内容与当前实现一致
- 建议动作：**修订**（仅修 README 信号范围；不建议大幅削减 README 篇幅，因为其"全景入口"职能仍有价值）
- 已修改文档：待执行
- 下一步：修 README 信号范围

## GX 跨步骤逻辑审查

- 状态：done
- 发现三个跨步骤逻辑问题，均已修复：

### 问题 1（关键）：Library carry-forward 缺失导致 Cell 振荡

- **根因**：`publish_cell_library` 只从当前 batch 的 `trusted_snapshot_cell`（Path B 新 Cell）发布，不 carry-forward 上一轮已发布但本轮走 Path A 的 Cell。由于路由和补数查询都用 `MAX(batch_id)` 读 library，旧 Cell 在新 batch 中不可见，下一轮回退为"未知"重新走 Path B，形成振荡。
- **修复**：在 `publish_cell.py` 添加 `_carry_forward_previous_cells()` 函数，在主 publish 之后将上一轮 library 中有效（非 retired）且不在当前 snapshot 中的 Cell carry-forward 到当前 batch_id，合并 `cell_metrics_window` 更新指标，应用退出管理和防毒化检查。
- 已修改文档：`rebuild5/backend/app/maintenance/publish_cell.py`

### 问题 2（中等）：profile_obs 信号 FILTER 范围不一致

- **根因**：`profile/pipeline.py` 的 `build_profile_obs` 中 RSRP 用 `-156~0`（应为 `-156~-1`），RSRQ 用 `-50~10`（应为 `-34~10`），SINR 用 `-30~50`（应为 `-23~40`）。虽然 `clean.py` 已将越界值置空，运行时无影响，但常量不一致。
- **修复**：对齐为 RSRP `-156~-1`，RSRQ `-34~10`，SINR `-23~40`。
- 已修改文档：`rebuild5/backend/app/profile/pipeline.py`

### 问题 3（低）：window.py RSRP 范围含 0

- **根因**：`window.py` 的 `recalculate_cell_metrics` 中 RSRP FILTER 用 `BETWEEN -156 AND 0`，0 在 `clean.py` 中已被视为无效。
- **修复**：改为 `BETWEEN -156 AND -1`。
- 已修改文档：`rebuild5/backend/app/maintenance/window.py`
