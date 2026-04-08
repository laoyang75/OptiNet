# Layer_1：合规筛选层总览（LAC / Cell / ENBID / GPS）

> 作用：统一说明 Layer_1 下各子目录的职责，并约定 **所有新任务在编写 SQL 前，必须先确认所在子目录并在其中补齐 README / 规则文件**，避免规则散落在根目录或 `Agent_Workspace`。

---

## 1. Layer_1 的整体定位

Layer_1 负责从原始大表中抽取“格式与范围合规”的子集，为上层分析（Layer_2）提供稳定输入。当前规划包括：

- `Layer_1/Lac/`：L1-LAC 合规（已完成 v1 规则）；  
- `Layer_1/Cell/`：L1-CELL 合规（已完成 v1 规则）；  
- `Layer_1/Enbid/`：L1-ENBID / 基站结构与碰撞分析（本次新增根目录）；  
- `Layer_1/GPS/`：L1-GPS 合规（预留）。

所有 L1 层的正式规则文件，命名统一为：

- `*_Filter_Rules_v1.md`（可直接执行的规则和视图定义），  
- 对应的 `README.md` 负责解释背景与使用方法。

---

## 2. 目录职责与入口文件

- `Layer_1/Lac/`  
  - 说明：LAC 数值合规与 4G/5G 制式约束；  
  - 入口：`Layer_1/Lac/README.md`、`Layer_1/Lac/Lac_Filter_Rules_v1.md`；  
  - 核心输出：`public.v_lac_L1_stage1`。

- `Layer_1/Cell/`  
  - 说明：在 L1-LAC 范围内，对 `cell_id` 做格式 + 无效值过滤；  
  - 入口：`Layer_1/Cell/README.md`、`Layer_1/Cell/Cell_Filter_Rules_v1.md`；  
  - 核心输出：`public.v_cell_L1_stage1`。

- `Layer_1/Enbid/`  
  - 说明：在 L1-CELL 基础上研究 ENBID / 基站结构、`cell_id` 碰撞及共建逻辑；  
  - 入口：`Layer_1/Enbid/README.md`、`Layer_1/Enbid/Enbid_Filter_Rules_v1.md`；  
  - 核心约定：
    - Cell 级主键：`(运营商id, 原始lac, cell_id)`；  
    - ENBID / 基站 ID 仅作为从 `cell_id` 派生的站级聚合字段；  
    - 所有 ENBID/基站相关正式规则都必须写在本目录下。

- `Layer_1/GPS/`（预留）  
  - 说明：在 L1-LAC / L1-CELL 范围内，对 GPS 做基础过滤与合规判断；  
  - 入口文件待后续补充。

---

## 3. 新任务的统一起步动作（防止目录再次混乱）

以后在 Layer_1 层启动任何新任务（无论是 LAC / Cell / ENBID / GPS），第一步统一为：

1. **确认所属子目录**
   - LAC 相关 → `Layer_1/Lac/`  
   - Cell 相关 → `Layer_1/Cell/`  
   - ENBID / 基站相关 → `Layer_1/Enbid/`  
   - GPS 相关 → `Layer_1/GPS/`

2. **检查 / 补齐 README 与 v1 规则文件**
   - 若子目录中缺少对应的 `README.md` 或 `*_Filter_Rules_v1.md`，先补这个文件，写清：  
     - 本任务的输入视图、输出视图；  
     - 主键约定；  
     - 与其他 Layer 的依赖关系。

3. **正式规则写在 Layer_1，临时脚本写在 Agent_Workspace**
   - 一次性 SQL / 调试脚本 → 放在 `Agent_Workspace/sql/`，文件名可带 `_tmp` / `_inspect`；  
   - 经过验证、需要长期复用的规则（过滤条件、视图定义） → 回写到对应 `Layer_1/*/*_Filter_Rules_v1.md` 中。

通过这三个步骤，确保后续重启 ENBID 或其他子任务时，都能快速找到入口和规则，不再出现“目录乱七八糟”的情况。

---

## 4. 当前阶段小结（LAC / Cell / ENBID）

为方便后续重启或接力，简要记录当前三块工作的状态与关键结论：

- **LAC（L1-LAC）**  
  - 已完成 v1 规则与视图：`public.v_lac_L1_stage1`。  
  - 统一限定 5 个国内 PLMN，仅保留 `原始lac` 数值合规且制式为 4G/5G 的记录。  
  - 4G LAC 在不同运营商间存在数值重叠，不能单独作为运营商或物理区域的唯一标识。

- **Cell（L1-CELL）**  
  - 已完成 v1 规则：`public.v_cell_L1_stage1`。  
  - 2G/3G 的 `cell_id` 基本为 0/-1 等默认值，本轮整体视为无效；  
  - 4G/5G 的 `cell_id` 格式基本合规，仅剔除空值、非数字、≤0 以及溢出默认值 `2147483647`。

- **ENBID / 基站（L1-ENBID）**  
  - 已建立根目录与 v1 约定文档：`Layer_1/Enbid/README.md`、`Enbid_Filter_Rules_v1.md`。  
  - 基于 4G TOP10 `cell_id` 的实证分析表明：  
    - ENBID 下挂载的 cell 数量处于正常范围（1–6），不存在超大站是导致 TOP 的主要原因；  
    - `cell_id` 在不同运营商之间存在数值复用/共建（特别是联通+电信、移动+广电家族），少数 `cell_id` 在同一运营商内跨多 LAC；  
  - 因此，后续 ENBID 研究统一采用 `(运营商id, 原始lac, cell_id)` 作为 Cell 级主键，ENBID 仅作为派生聚合字段。
