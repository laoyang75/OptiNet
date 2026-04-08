# 流式架构调整 — 执行方案（Phase 7）

## 你的角色

你是**执行 agent**。你的任务是按照已审批的修改方案，对 rebuild4 系统进行结构调整。

---

## 核心背景

本轮调整的核心目标是**把流式评估实验固化成可观察的流式画像模块**：

1. `profile.py` 当前只能全量一次性计算画像，没有中间过程
2. 流式评估实验（`docs/02_profile/06_流式评估.md`）已经证明逐天累积 = 批量结果（Day 7 偏差 0.00m）
3. 本轮要把这个实验逻辑固化到 `profile.py` 的 streaming 模式，产出 snapshot 序列和 diff
4. 流转页面（流转总览/快照/观察工作台）改接 snapshot 数据，让流转过程可观察
5. 对象浏览/详情切到 `etl_dim_*`，结束双数据体系割裂

**不是重构，是在已验证的成果上完成对接。**

---

## 输入材料

按顺序读取：

1. `rebuild4/docs/two_stage_ass/final_plan.md` — **最终修改方案**（阶段一 7 个任务 + 阶段二 3 个任务）
2. `rebuild4/docs/two_stage_ass/decision_questions.md` — 人类决策（Q1=A, Q2=A, Q3=B, Q4=B, Q5=C）

技术参考（按需查阅，不需要全读）：

3. `rebuild4/docs/02_profile/05_pipeline.md` — 画像管道实现（6 步 SQL + 全部阈值清单）
4. `rebuild4/docs/02_profile/06_流式评估.md` — 流式评估实验（收敛曲线 + 对比方法 + SQL 模式）
5. `rebuild4/docs/02_profile/00_总览.md` — 画像管道总览

> ⚠️ 在执行前，请确认 `final_plan.md` 存在且包含完整的阶段一（任务 1.1-1.7）和阶段二（任务 2.1-2.3）。

---

## 执行原则

### 必须遵守

1. **严格按 final_plan.md 执行**：不跳过任务，不添加方案外的变更
2. **profile.py 全量模式不动**：`run_profile()` 是已验证的正确实现，streaming 模式是**新增**，不替代
3. **复用流式评估实验的 SQL 模式**：实验中逐天累积的逻辑已跑通验证（eval_stream_cell_profiles），不要从零设计新算法
4. **逐阶段执行**：先完成阶段一全部任务，验证通过后再进入阶段二
5. **每个任务执行后立即验证**：按方案中的"验证方式"确认修改有效

### 应当遵守

6. **最小改动**：能改 3 行不改 30 行。特别是任务 1.1——给现有 step 函数加日期窗口参数，不要重构成通用模板
7. **不引入新依赖**：不加新 npm 包、不加新 Python 库（YAML 用标准库 yaml 即可）
8. **保持现有风格**：后端 SQL 驱动 Python 编排、前端 Vue 3 + TS、文档中文
9. **新建文件要标注**：方案中标注了"**新建**"的文件（如 `DataOriginBanner.vue`、`profile_params.yaml`），注意是新建不是修改

### 关键实现提示

任务 1.1 是最核心也最容易过度工程化的任务。正确的实现路径：

```python
# 不要这样做（过度重构）：
def _step1_with_params(source_table, date_filter, output_table):
    ...

# 应该这样做（最小改动）：
def run_profile_streaming(date_windows: list[str]):
    """按天累积运行 streaming 模式。"""
    for i, end_date in enumerate(date_windows):
        # 复用现有 step 函数的 SQL，加 WHERE DATE(ts_std) <= end_date
        # 存 snapshot
        # 计算与上一个 snapshot 的 diff
    # 最后一个 snapshot 写入 etl_dim_cell/bs/lac
```

---

## 执行流程

### Step 1: 理解方案

读取 `final_plan.md`，列出所有任务：

```
阶段一（必须做 — 流式模块 + 页面对接）:
  1.1 streaming 模式固化到 profile.py
  1.2 snapshot + diff 落盘表
  1.3 flow / observation API 改接 snapshot
  1.4 前端 flow / snapshot / observation 页面改接
  1.5 对象浏览/详情切到 etl_dim_*
  1.6 修复保留页面的已知前端 bug（GovernancePage 字段漂移 + CellProfilePage low_collision）
  1.7 清理主导航

阶段二（应该做 — 参数外化 + 版本追溯）:
  2.1 YAML 参数外化
  2.2 etl_profile_run_log 版本日志
  2.3 旧 Run/Baseline 页改造

阶段三：搁置
```

### Step 2: 检查当前状态

在开始修改前，确认系统当前状态：

```sql
-- 画像表存在且有数据
SELECT COUNT(*) FROM rebuild4.etl_dim_cell;
SELECT COUNT(*) FROM rebuild4.etl_dim_bs;
SELECT COUNT(*) FROM rebuild4.etl_dim_lac;

-- 流式评估数据仍在（作为参考基准）
SELECT COUNT(*) FROM rebuild4.eval_stream_convergence;

-- meta schema 表列表
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'rebuild4_meta' ORDER BY table_name;
```

确认后端能启动：
```bash
cd rebuild4/backend && python3 -c "from app.main import app; print('OK')"
```

确认前端现有代码能理解：
```bash
ls rebuild4/frontend/src/pages/*.vue
```

### Step 3: 逐任务执行

对每个任务：

1. **标记开始**：用 TaskCreate 创建任务
2. **读取相关文件**：先读再改，特别是被修改的 router 和 vue 文件
3. **执行修改**：按方案描述修改代码/数据库
4. **验证**：按方案的"验证方式"确认
5. **标记完成**：TaskUpdate 标记完成

**任务依赖关系**（必须按序执行）：
```
1.1 → 1.2 → 1.3 → 1.4  (streaming 链路：代码 → 存储 → API → 前端)
1.5, 1.6, 1.7 可在 1.4 完成后并行
```

### Step 4: 阶段验收

每个阶段全部任务完成后：

1. 确认后端启动无报错
2. 运行 streaming 模式，确认 snapshot 和 diff 数据正确产出
3. 用数据库查询确认：
   - `etl_profile_snapshot` 有 7 行（7 天）
   - `etl_profile_snapshot_diff` 有 6 行（6 个 diff）
   - `etl_dim_cell` 的 lifecycle 分布与最后一个 snapshot 一致
4. 确认保留页面都能正常打开、有数据
5. 向用户报告阶段完成情况，确认是否继续下一阶段

### Step 5: 落成文档

所有阶段完成后：

1. 更新 `rebuild4/docs/02_profile/00_总览.md` — 反映 streaming 模式
2. 更新 `rebuild4/docs/02_profile/05_pipeline.md` — 补充 streaming 模式说明
3. 列出所有变更的文件清单和新建的数据库表

---

## 参考文件

按需查阅，不需要全读：

**后端核心**：
- `rebuild4/backend/app/main.py` — 路由注册
- `rebuild4/backend/app/core/database.py` — 数据库工具（execute, fetchone, fetchall）
- `rebuild4/backend/app/core/context.py` — 系统上下文
- `rebuild4/backend/app/etl/profile.py` — 画像管道（任务 1.1 的主要修改对象）
- `rebuild4/backend/app/etl/pipeline.py` — ETL 主入口
- `rebuild4/backend/app/routers/flow.py` — 流转 API（任务 1.3 改接）
- `rebuild4/backend/app/routers/workspaces.py` — 工作台 API（任务 1.3 改接）
- `rebuild4/backend/app/routers/objects.py` — 对象 API（任务 1.5 改接）
- `rebuild4/backend/app/routers/profiles.py` — 画像 API（只读参考，不改）
- `rebuild4/backend/app/routers/runs.py` — 运行中心 API（阶段二任务 2.3）
- `rebuild4/backend/app/routers/baseline.py` — 基线 API（阶段二任务 2.3）

**前端核心**：
- `rebuild4/frontend/src/App.vue` — 侧边栏
- `rebuild4/frontend/src/router.ts` — 路由
- `rebuild4/frontend/src/lib/api.ts` — API 客户端
- `rebuild4/frontend/src/pages/FlowOverviewPage.vue` — 流转总览
- `rebuild4/frontend/src/pages/FlowSnapshotPage.vue` — 流转快照
- `rebuild4/frontend/src/pages/ObservationWorkspacePage.vue` — 观察工作台
- `rebuild4/frontend/src/pages/ObjectsPage.vue` — 对象浏览
- `rebuild4/frontend/src/pages/ObjectDetailPage.vue` — 对象详情
- `rebuild4/frontend/src/pages/GovernancePage.vue` — 治理（修 bug）
- `rebuild4/frontend/src/pages/CellProfilePage.vue` — Cell 画像（修 bug）

**文档**：
- `rebuild4/docs/02_profile/05_pipeline.md` — 画像管道实现（阈值清单在这里）
- `rebuild4/docs/02_profile/06_流式评估.md` — 流式评估实验（SQL 模式可复用）

---

## 输出

执行完成后，向用户报告：

1. 每个阶段的完成状态
2. 所有修改的文件清单（区分修改/新建/删除）
3. 数据库变更清单（新建的表及其字段）
4. streaming 模式运行结果：snapshot 数、最终 cell/bs/lac 行数、lifecycle 分布
5. 遗留问题（如有）

---

## 约束

- **不做方案以外的事**：看到代码不顺眼也不要"顺手"改
- **不优化现有代码**：不重构、不加注释、不改命名、不加类型标注
- **遇到方案描述模糊时**：停下来问用户，不自行解释
- **遇到方案与实际代码冲突时**：报告冲突，等待用户决策
- **streaming 模式的算法必须与全量模式一致**：不能引入第二套计算逻辑。验证方法：streaming 最后一个 snapshot 的 lifecycle 分布应与 `run_profile()` 全量结果接近（允许因边界处理有微小差异）
